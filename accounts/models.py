from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator, URLValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .constants import SEMESTER_CHOICES, Branch, Role

username_validator = RegexValidator(
    r"^[a-z0-9_.]{3,30}\Z", "Use 3–30 lowercase letters, numbers, dots or underscores."
)
phone_validator = RegexValidator(r"^\+?[0-9][0-9 \-]{6,14}[0-9]\Z", "Enter a valid phone number.")
web_url_validator = URLValidator(schemes=["http", "https"])


class UserManager(BaseUserManager):
    use_in_migrations = True


class User(AbstractBaseUser):
    """Single account table for all three roles.

    The role lives only in the database and is read on every request, never from the
    session or from anything the browser sends. Admin accounts have no public ID.
    """

    username = models.CharField(max_length=30, unique=True, validators=[username_validator])
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=10, choices=Role.choices, db_index=True)
    public_id = models.CharField(max_length=12, unique=True, null=True, blank=True, editable=False)
    is_active = models.BooleanField(default=True)  # False = suspended
    must_change_password = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email", "full_name", "role"]

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=Role.values), name="user_role_is_valid"
            ),
            # S-prefixed IDs for students, T-prefixed for teachers, none for admins.
            models.CheckConstraint(
                condition=(
                    Q(role="student", public_id__startswith="S")
                    | Q(role="teacher", public_id__startswith="T")
                    | Q(role="admin", public_id__isnull=True)
                ),
                name="user_public_id_matches_role",
            ),
        ]

    def save(self, *args, **kwargs):
        self.username = (self.username or "").strip().lower()
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.public_id or self.username

    @property
    def is_student(self):
        return self.role == Role.STUDENT.value

    @property
    def is_teacher(self):
        return self.role == Role.TEACHER.value

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN.value


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    branch = models.CharField(max_length=5, choices=Branch.choices)
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(8)]
    )
    academic_details = models.TextField(
        max_length=1000, blank=True, help_text="Section, roll number, CGPA, interests — anything relevant."
    )
    github_url = models.URLField(blank=True, validators=[web_url_validator], verbose_name="GitHub URL")
    linkedin_url = models.URLField(blank=True, validators=[web_url_validator], verbose_name="LinkedIn URL")
    portfolio_url = models.URLField(blank=True, validators=[web_url_validator], verbose_name="Portfolio URL")
    leetcode_username = models.CharField(max_length=40, blank=True, verbose_name="LeetCode username")
    codeforces_username = models.CharField(max_length=40, blank=True, verbose_name="Codeforces username")
    codechef_username = models.CharField(max_length=40, blank=True, verbose_name="CodeChef username")
    hackerrank_username = models.CharField(max_length=40, blank=True, verbose_name="HackerRank username")
    # Privacy & Credential Concealment Controls
    hide_email = models.BooleanField(default=False, help_text="Hide email address from public directories")
    hide_phone = models.BooleanField(default=False, help_text="Hide phone number from public directories")
    hide_student_id = models.BooleanField(default=False, help_text="Hide Student ID from public directories")
    updated_at = models.DateTimeField(auto_now=True)

    def completion(self):
        """Return (percent, labels of missing items)."""
        checks = [
            ("Phone number", bool(self.phone)),
            ("Branch", bool(self.branch)),
            ("Semester", bool(self.semester)),
            ("Academic details", bool(self.academic_details.strip())),
            (
                "A personal link (GitHub, LinkedIn or portfolio)",
                any([self.github_url, self.linkedin_url, self.portfolio_url]),
            ),
            (
                "A coding profile (LeetCode, Codeforces, CodeChef or HackerRank)",
                any([self.leetcode_username, self.codeforces_username,
                     self.codechef_username, self.hackerrank_username]),
            ),
        ]
        done = sum(1 for _, ok in checks if ok)
        return round(100 * done / len(checks)), [label for label, ok in checks if not ok]

    def __str__(self):
        return f"Student profile of {self.user}"


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    department = models.CharField(max_length=5, choices=Branch.choices, blank=True)
    designation = models.CharField(max_length=80, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    # Privacy & Credential Concealment Controls
    hide_email = models.BooleanField(default=False, help_text="Hide email address from public directories")
    hide_phone = models.BooleanField(default=False, help_text="Hide phone number from public directories")
    hide_teacher_id = models.BooleanField(default=False, help_text="Hide Teacher ID from public directories")
    updated_at = models.DateTimeField(auto_now=True)

    def completion(self):
        checks = [
            ("Phone number", bool(self.phone)),
            ("Department", bool(self.department)),
            ("Designation", bool(self.designation.strip())),
            ("Short bio", bool(self.bio.strip())),
        ]
        done = sum(1 for _, ok in checks if ok)
        return round(100 * done / len(checks)), [label for label, ok in checks if not ok]

    def __str__(self):
        return f"Teacher profile of {self.user}"


class IdSequence(models.Model):
    """One row per ID prefix ('S', 'T'); also a lock row ('A') for admin bootstrap.

    Rows are locked with SELECT ... FOR UPDATE inside the same transaction that creates
    the user, so concurrent signups never receive the same number. The unique index on
    User.public_id is the backstop.
    """

    prefix = models.CharField(max_length=1, primary_key=True)
    last_value = models.PositiveIntegerField(default=0)


class AuditEvent(models.Model):
    """Append-only (at the application layer) record of security-relevant events.

    Never store passwords, tokens or free-form personal data in `detail`.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_label = models.CharField(max_length=80, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
