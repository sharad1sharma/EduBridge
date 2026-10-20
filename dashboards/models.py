from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone

from accounts.constants import SEMESTER_CHOICES, Branch

web_url_validator = URLValidator(schemes=["http", "https"])


class AcademicBranch(models.Model):
    """B.Tech academic branches, configurable by the administrator."""
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Academic Branch"
        verbose_name_plural = "Academic Branches"

    def __str__(self):
        return f"{self.code} - {self.name}"


class Subject(models.Model):
    """Institutional subjects/courses linked to branches and semesters."""
    code = models.CharField(max_length=20, unique=True, db_index=True)
    title = models.CharField(max_length=150)
    branch = models.CharField(max_length=10, choices=Branch.choices)
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(8)]
    )
    credits = models.DecimalField(max_digits=3, decimal_places=1, default=4.0)
    is_elective = models.BooleanField(default=False)
    syllabus_summary = models.TextField(blank=True)
    assigned_teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="assigned_subjects"
    )
    enrolled_students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="enrolled_subjects",
        help_text="Explicit student enrollments for this subject"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["semester", "code"]

    def __str__(self):
        return f"{self.code} {self.title} (Sem {self.semester})"


class Assessment(models.Model):
    """Daily assignments and weekly tests created by faculty or administration."""
    class AssessmentType(models.TextChoices):
        DAILY_ASSIGNMENT = "daily_assignment", "Daily Assignment"
        WEEKLY_TEST = "weekly_test", "Weekly Test"
        MIXED = "mixed", "Mixed Assessment (MCQ + Coding)"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SCHEDULED = "scheduled", "Scheduled"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    topic = models.CharField(max_length=150, blank=True)
    difficulty = models.CharField(max_length=20, default="Medium")
    assessment_type = models.CharField(max_length=25, choices=AssessmentType.choices)
    branch = models.CharField(max_length=10, choices=Branch.choices)
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(8)]
    )
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="assessments")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_assessments"
    )
    target_students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="targeted_assessments",
        help_text="Optional specific students or student cohort"
    )
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=45, help_text="Total duration allowed for attempt")
    total_marks = models.PositiveIntegerField(default=100)
    start_date = models.DateTimeField(default=timezone.now, help_text="Date/time when assessment becomes open")
    deadline = models.DateTimeField()
    max_attempts = models.PositiveSmallIntegerField(default=1)
    negative_marking = models.DecimalField(max_digits=4, decimal_places=2, default=0.00, help_text="Negative marks per wrong MCQ")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    
    # Structured Questions: Daily assignment >= 10 MCQs; Weekly test = 25 MCQs + 5 Coding problems
    questions_data = models.JSONField(
        default=list, blank=True,
        help_text="List of MCQ objects: {id, question, options: [A, B, C, D], correct: 'A', marks: 4, explanation: ''}"
    )
    coding_problems_data = models.JSONField(
        default=list, blank=True,
        help_text="List of coding exercises: {id, title, description, constraints, sample_input, sample_output, test_cases: [], lang: 'python', marks: 10}"
    )
    
    # Integrity and anti-cheating policy config
    auto_submit_on_tab_switch = models.BooleanField(default=True, help_text="Enforce automatic submission when student tab switches exceed limit")
    max_tab_switches_allowed = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-deadline", "-created_at"]

    def __str__(self):
        return f"[{self.get_assessment_type_display()}] {self.title} ({self.branch} Sem {self.semester})"

    @property
    def is_available(self):
        now = timezone.now()
        if self.status in [self.Status.PUBLISHED, self.Status.SCHEDULED]:
            return self.start_date <= now <= self.deadline
        return False

    @property
    def is_scheduled_future(self):
        now = timezone.now()
        return self.status in [self.Status.PUBLISHED, self.Status.SCHEDULED] and self.start_date > now

    @property
    def mcq_count(self):
        return len(self.questions_data) if isinstance(self.questions_data, list) else 0

    @property
    def coding_count(self):
        return len(self.coding_problems_data) if isinstance(self.coding_problems_data, list) else 0


class AssessmentAttempt(models.Model):
    """Student submission record for an assessment."""
    class AttemptStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        DISPUTED = "disputed", "Disputed"

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assessment_attempts")
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0.0)
    is_auto_submitted = models.BooleanField(default=False)
    tab_switches_recorded = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS)
    answers = models.JSONField(default=dict, blank=True)
    coding_evaluations = models.JSONField(default=dict, blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at", "-started_at"]
        constraints = [
            models.UniqueConstraint(fields=["assessment", "student"], name="unique_student_assessment_attempt")
        ]

    def __str__(self):
        return f"{self.student.public_id} - {self.assessment.title} ({self.score}/{self.assessment.total_marks})"


class LearningResource(models.Model):
    """Study materials, lecture notes, lab manuals, and videos."""
    class ResourceType(models.TextChoices):
        NOTES = "notes", "Lecture Notes"
        PDF = "pdf", "PDF Document"
        LAB_MANUAL = "lab_manual", "Lab Manual"
        VIDEO = "video", "Educational Video Link"
        CODE = "code", "Coding Exercise / Archive"

    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        DRAFT = "draft", "Draft"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    branch = models.CharField(max_length=10, choices=Branch.choices)
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(8)]
    )
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="resources")
    topic = models.CharField(max_length=120, blank=True)
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices, default=ResourceType.PDF)
    external_url = models.URLField(blank=True, validators=[web_url_validator])
    file = models.FileField(upload_to="resources/%Y/%m/", blank=True, null=True)
    thumbnail_url = models.URLField(blank=True, help_text="Validated external thumbnail image URL")
    thumbnail_image = models.ImageField(upload_to="resources/thumbs/%Y/%m/", blank=True, null=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="authored_resources"
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    download_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def target_url(self):
        if self.file:
            try:
                return self.file.url
            except ValueError:
                pass
        return self.external_url or "#"

    @property
    def display_thumbnail(self):
        if self.thumbnail_image:
            try:
                return self.thumbnail_image.url
            except ValueError:
                pass
        if self.thumbnail_url:
            return self.thumbnail_url
        title_lower = (self.title or "").lower()
        subj_code = getattr(getattr(self, "subject", None), "code", "").upper()
        if "os" in title_lower or "thread" in title_lower or "mutex" in title_lower or "302" in subj_code:
            return "/static/img/thumbnails/os_concurrency.jpg"
        if "database" in title_lower or "sql" in title_lower or "304" in subj_code:
            return "/static/img/thumbnails/db_sql.jpg"
        if "network" in title_lower or "wireshark" in title_lower or "303" in subj_code:
            return "/static/img/thumbnails/net_protocols.jpg"
        return "/static/img/thumbnails/algo_master_theorem.jpg"

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_resource_type_display()}] {self.title}"


class Scholarship(models.Model):
    """Scholarships strictly administered by the platform administrator."""
    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        DRAFT = "draft", "Draft"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=220)
    provider = models.CharField(max_length=180, help_text="Official organization or government body")
    description = models.TextField()
    education_level = models.CharField(max_length=80, default="B.Tech Undergraduate")
    eligible_branches = models.CharField(
        max_length=255, default="All Branches", help_text="Comma-separated branches or 'All Branches'"
    )
    academic_year = models.CharField(max_length=80, default="1st to 4th Year")
    income_criteria = models.CharField(max_length=150, blank=True, help_text="e.g. Annual family income < 8 LPA")
    min_cgpa = models.DecimalField(max_digits=4, decimal_places=2, default=0.00, help_text="Minimum CGPA if required")
    required_documents = models.TextField(blank=True, help_text="Income cert, Marksheet, Bonafide, etc.")
    opening_date = models.DateField(default=timezone.now)
    deadline = models.DateField(db_index=True)
    official_application_url = models.URLField(validators=[web_url_validator])
    official_source_url = models.URLField(validators=[web_url_validator])
    last_verified_at = models.DateField(default=timezone.now)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["deadline", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.provider}) - Due {self.deadline}"

    @property
    def is_deadline_near(self):
        today = timezone.now().date()
        return 0 <= (self.deadline - today).days <= 14


class Meeting(models.Model):
    """Platform-wide online lecture, tutorial, and doubt-clearing sessions."""
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    host_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hosted_meetings"
    )
    branch = models.CharField(max_length=10, choices=Branch.choices)
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(8)]
    )
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="meetings")
    scheduled_at = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    meeting_link = models.URLField(validators=[web_url_validator])
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"{self.title} with {self.host_teacher.full_name} ({self.scheduled_at:%d %b, %H:%M})"


class PlatformNotification(models.Model):
    """Persistent notification record for students, teachers, and admins."""
    class NotificationType(models.TextChoices):
        ASSIGNMENT = "assignment", "New Assignment"
        TEST = "test", "Weekly Test"
        DEADLINE = "deadline", "Assessment Deadline"
        MEETING = "meeting", "Meeting Scheduled"
        MEETING_CANCEL = "meeting_cancel", "Meeting Cancelled"
        RESOURCE = "resource", "New Resource Published"
        PLATFORM = "platform", "Platform Notice"

    class DeliveryStatus(models.TextChoices):
        DELIVERED = "delivered", "Delivered"
        PENDING = "pending", "Pending"
        FAILED = "failed", "Failed"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="platform_notifications"
    )
    notification_type = models.CharField(max_length=25, choices=NotificationType.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    delivery_status = models.CharField(max_length=15, choices=DeliveryStatus.choices, default=DeliveryStatus.DELIVERED)
    is_read = models.BooleanField(default=False)
    retry_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] To: {self.recipient.username} - {self.title}"


class PlatformSetting(models.Model):
    """Safe, non-secret configuration manageable by administrators."""
    key = models.CharField(max_length=80, unique=True, db_index=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class DSATopic(models.TextChoices):
    ARRAYS = "arrays", "Arrays"
    STRINGS = "strings", "Strings"
    SEARCHING = "searching", "Searching"
    SORTING = "sorting", "Sorting"
    LINKED_LISTS = "linked_lists", "Linked Lists"
    STACKS = "stacks", "Stacks"
    QUEUES = "queues", "Queues"
    HASHING = "hashing", "Hashing"
    RECURSION = "recursion", "Recursion"
    TREES = "trees", "Trees"
    GRAPHS = "graphs", "Graphs"
    GREEDY = "greedy", "Greedy Algorithms"
    DP = "dp", "Dynamic Programming"


class DSAQuestion(models.Model):
    """Teacher-curated and managed Data Structures & Algorithms practice questions."""
    title = models.CharField(max_length=200)
    topic = models.CharField(max_length=50, choices=DSATopic.choices, default=DSATopic.ARRAYS, db_index=True)
    difficulty = models.CharField(
        max_length=15,
        choices=[("Easy", "Easy"), ("Medium", "Medium"), ("Hard", "Hard")],
        default="Medium",
        db_index=True
    )
    problem_statement = models.TextField(help_text="Detailed problem description")
    branch = models.CharField(max_length=10, choices=Branch.choices, default="CSE")
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(8)], default=3
    )
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="dsa_questions")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_dsa_questions"
    )
    supported_languages = models.JSONField(
        default=list,
        help_text="List of supported language codes, e.g. ['python', 'java', 'c']"
    )
    input_format = models.TextField(blank=True)
    output_format = models.TextField(blank=True)
    constraints = models.TextField(blank=True)
    sample_input = models.TextField(blank=True)
    sample_output = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    starter_code = models.JSONField(
        default=dict,
        help_text="Dict mapping language to initial code template"
    )
    # Public vs Hidden Test Cases (Security: Hidden test cases are never transmitted to students)
    public_test_cases = models.JSONField(
        default=list,
        help_text="List of public test cases: [{'input': '...', 'output': '...', 'explanation': '...'}]"
    )
    hidden_test_cases = models.JSONField(
        default=list,
        help_text="List of evaluation test cases: [{'input': '...', 'output': '...'}]"
    )
    time_limit_ms = models.PositiveIntegerField(default=2000, help_text="Execution timeout per test case in milliseconds")
    memory_limit_mb = models.PositiveIntegerField(default=128, help_text="RAM limit in MB")
    status = models.CharField(
        max_length=15,
        choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
        default="published",
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.difficulty}] {self.title} ({self.get_topic_display()})"


class CodingSubmission(models.Model):
    """Persistent student code execution and submission records."""
    class SubmissionStatus(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        WRONG_ANSWER = "wrong_answer", "Wrong Answer"
        COMPILATION_ERROR = "compilation_error", "Compilation Error"
        RUNTIME_ERROR = "runtime_error", "Runtime Error"
        TIMEOUT = "timeout", "Time Limit Exceeded"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coding_submissions"
    )
    question = models.ForeignKey(
        DSAQuestion, on_delete=models.CASCADE, null=True, blank=True, related_name="submissions"
    )
    language = models.CharField(max_length=20, default="python")
    source_code = models.TextField()
    status = models.CharField(
        max_length=25, choices=SubmissionStatus.choices, default=SubmissionStatus.WRONG_ANSWER, db_index=True
    )
    passed_test_cases = models.PositiveIntegerField(default=0)
    total_test_cases = models.PositiveIntegerField(default=0)
    execution_time_ms = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True)
    test_case_results = models.JSONField(default=list, blank=True)
    is_practice = models.BooleanField(default=False, help_text="True for freeform sandbox Mode A practice")
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        q_label = self.question.title if self.question else "Sandbox Practice"
        return f"{self.student.username} - {q_label} [{self.status}]"


class CodingResource(models.Model):
    """External coding practice questions, topics, and online compilers for students."""
    class ResourceType(models.TextChoices):
        DSA_QUESTION = "dsa_question", "DSA Question"
        DSA_TOPIC = "dsa_topic", "DSA Topic"
        COMPILER = "compiler", "Online Compiler"

    class Difficulty(models.TextChoices):
        BEGINNER = "Beginner", "Beginner"
        EASY = "Easy", "Easy"
        MEDIUM = "Medium", "Medium"
        HARD = "Hard", "Hard"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    resource_type = models.CharField(
        max_length=25,
        choices=ResourceType.choices,
        default=ResourceType.DSA_QUESTION,
        db_index=True
    )
    topic_category = models.CharField(
        max_length=80,
        default="Arrays and Strings",
        db_index=True,
        help_text="e.g. Arrays and Strings, Searching and Sorting, Dynamic Programming, etc."
    )
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    description = models.TextField(blank=True)
    external_url = models.URLField(validators=[web_url_validator], help_text="Direct verified URL to external practice question or compiler")
    thumbnail_url = models.URLField(blank=True, help_text="Direct link to topic/platform thumbnail")
    thumbnail_image = models.ImageField(upload_to="coding_thumbs/%Y/%m/", blank=True, null=True)
    supported_languages = models.CharField(max_length=150, default="Python, Java, C++", blank=True, help_text="e.g. Python, Java, C")
    platform_name = models.CharField(max_length=100, blank=True, help_text="e.g. LeetCode, HackerRank, GeeksforGeeks, Programiz, OnlineGDB")
    branch = models.CharField(max_length=10, choices=Branch.choices, default="CSE", blank=True)
    semester = models.PositiveSmallIntegerField(choices=SEMESTER_CHOICES, default=3, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_coding_resources"
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["resource_type", "topic_category", "title"]

    def __str__(self):
        return f"[{self.get_resource_type_display()}] {self.title} ({self.platform_name or self.topic_category})"

    @property
    def display_thumbnail(self):
        if self.thumbnail_image:
            try:
                return self.thumbnail_image.url
            except ValueError:
                pass
        if self.thumbnail_url:
            return self.thumbnail_url
        if self.resource_type == self.ResourceType.COMPILER:
            return "/static/img/thumbnails/cloud_compiler.jpg"
        cat_lower = (self.topic_category or "").lower()
        title_lower = (self.title or "").lower()
        if "search" in cat_lower or "search" in title_lower:
            return "/static/img/thumbnails/dsa_binary_search.jpg"
        if "tree" in cat_lower or "graph" in cat_lower or "tree" in title_lower or "island" in title_lower:
            return "/static/img/thumbnails/dsa_trees_graphs.jpg"
        if "dynamic" in cat_lower or "knapsack" in title_lower or "dp" in cat_lower:
            return "/static/img/thumbnails/dsa_dynamic_programming.jpg"
        if "linked" in cat_lower or "list" in title_lower:
            return "/static/img/thumbnails/dsa_linked_lists.jpg"
        return "/static/img/thumbnails/dsa_two_sum.jpg"


class AttendanceRecord(models.Model):
    """Institutional attendance tracking for students across sessions and login events."""
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late Arrival"

    class SessionType(models.TextChoices):
        CLASS = "class", "Class Session"
        LAB = "lab", "Practical / Lab"
        TUTORIAL = "tutorial", "Tutorial"
        PLATFORM_LOGIN = "platform_login", "Platform Activity"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_records"
    )
    session_title = models.CharField(max_length=150, default="Lecture Session")
    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.CLASS,
        db_index=True
    )
    date = models.DateField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PRESENT, db_index=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_attendance"
    )
    is_auto_marked = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "date", "session_type"],
                name="unique_student_daily_session_attendance"
            )
        ]

    def __str__(self):
        subj_code = self.subject.code if self.subject else "General"
        return f"{self.student.public_id} - {self.date} [{self.status.upper()}] ({subj_code})"


