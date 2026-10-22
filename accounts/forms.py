from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .constants import SEMESTER_CHOICES, Branch
from .models import StudentProfile, TeacherProfile, User, username_validator


def _clean_username(value, exclude_pk=None):
    value = (value or "").strip().lower()
    username_validator(value)
    qs = User.objects.filter(username=value)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError("That username is taken.")
    return value


def _clean_email(value, exclude_pk=None):
    value = (value or "").strip().lower()
    qs = User.objects.filter(email=value)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError("An account with this email already exists.")
    return value


class StudentSignupForm(forms.Form):
    """Public signup. There is intentionally no role field: the view always creates a
    student, so extra POST data such as role=admin is ignored."""

    full_name = forms.CharField(max_length=120)
    username = forms.CharField(
        max_length=30, help_text="3–30 lowercase letters, numbers, dots or underscores."
    )
    email = forms.EmailField()
    branch = forms.ChoiceField(choices=[("", "Select your branch")] + list(Branch.choices))
    semester = forms.TypedChoiceField(
        choices=[("", "Select your semester")] + SEMESTER_CHOICES, coerce=int
    )
    password1 = forms.CharField(
        label="Password",
        help_text="At least 10 characters.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_full_name(self):
        return self.cleaned_data["full_name"].strip()

    def clean_username(self):
        return _clean_username(self.cleaned_data["username"])

    def clean_email(self):
        return _clean_email(self.cleaned_data["email"])

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                candidate = User(username=cleaned.get("username", ""), email=cleaned.get("email", ""),
                                 full_name=cleaned.get("full_name", ""))
                try:
                    validate_password(p1, user=candidate)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned


class LoginForm(forms.Form):
    identifier = forms.CharField(label="Username or email", max_length=254,
                                 widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class DifferentPasswordChangeForm(PasswordChangeForm):
    """Also rejects reusing the old (or temporary) password."""

    def clean_new_password1(self):
        new = self.cleaned_data.get("new_password1")
        old = self.cleaned_data.get("old_password")
        if new and old and new == old:
            raise ValidationError("Choose a password different from your current one.")
        return new


class _AccountProfileForm(forms.ModelForm):
    """Profile form that also edits the account fields on User. Never exposes the role
    or public ID. Changing the email requires the current password."""

    full_name = forms.CharField(max_length=120)
    username = forms.CharField(max_length=30)
    email = forms.EmailField()
    current_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Only needed if you change your email address.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        for name in ("full_name", "username", "email"):
            self.fields[name].initial = getattr(user, name)

    def clean_username(self):
        return _clean_username(self.cleaned_data["username"], exclude_pk=self.user.pk)

    def clean_email(self):
        return _clean_email(self.cleaned_data["email"], exclude_pk=self.user.pk)

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        if email and email != self.user.email:
            if not self.user.check_password(cleaned.get("current_password") or ""):
                self.add_error("current_password", "Enter your current password to change your email.")
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = self.user
        user.full_name = self.cleaned_data["full_name"].strip()
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=["full_name", "username", "email"])
            profile.save()
        return profile


class StudentProfileForm(_AccountProfileForm):
    field_order = ["full_name", "username", "email", "current_password", "phone", "branch", "semester",
                   "academic_details", "github_url", "linkedin_url", "portfolio_url",
                   "leetcode_username", "codeforces_username", "codechef_username", "hackerrank_username",
                   "hide_email", "hide_phone", "hide_student_id"]

    class Meta:
        model = StudentProfile
        fields = ["phone", "branch", "semester", "academic_details", "github_url", "linkedin_url",
                  "portfolio_url", "leetcode_username", "codeforces_username", "codechef_username",
                  "hackerrank_username", "hide_email", "hide_phone", "hide_student_id"]
        widgets = {"academic_details": forms.Textarea(attrs={"rows": 3})}
        labels = {
            "hide_email": "Hide my email from peers and student directory",
            "hide_phone": "Hide my phone number from peers and student directory",
            "hide_student_id": "Hide my Student ID from public profile directories"
        }


class TeacherProfileForm(_AccountProfileForm):
    field_order = ["full_name", "username", "email", "current_password", "phone", "department",
                   "designation", "bio", "hide_email", "hide_phone", "hide_teacher_id"]

    class Meta:
        model = TeacherProfile
        fields = ["phone", "department", "designation", "bio",
                  "hide_email", "hide_phone", "hide_teacher_id"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}
        labels = {
            "hide_email": "Hide my email from students and public directories",
            "hide_phone": "Hide my phone number from students and public directories",
            "hide_teacher_id": "Hide my Teacher ID from student directories"
        }


class TeacherCreateForm(forms.Form):
    """Used by administrators only. Teachers cannot self-register."""

    full_name = forms.CharField(max_length=120)
    username = forms.CharField(max_length=30)
    email = forms.EmailField()
    department = forms.ChoiceField(choices=[("", "Not set")] + list(Branch.choices), required=False)
    designation = forms.CharField(max_length=80, required=False)

    def clean_username(self):
        return _clean_username(self.cleaned_data["username"])

    def clean_email(self):
        return _clean_email(self.cleaned_data["email"])
