from django.db import models


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    TEACHER = "teacher", "Teacher"
    ADMIN = "admin", "Administrator"


class Branch(models.TextChoices):
    CSE = "CSE", "Computer Science and Engineering"
    IT = "IT", "Information Technology"
    AIDS = "AIDS", "Artificial Intelligence and Data Science"
    ECE = "ECE", "Electronics and Communication Engineering"
    EE = "EE", "Electrical Engineering"
    ME = "ME", "Mechanical Engineering"
    CE = "CE", "Civil Engineering"
    CHE = "CHE", "Chemical Engineering"
    BT = "BT", "Biotechnology"
    AE = "AE", "Aerospace Engineering"
    FY = "FY", "Common first-year engineering"


# Branches where programming is central (used from Phase 6 for coding questions).
COMPUTING_BRANCHES = frozenset({Branch.CSE.value, Branch.IT.value, Branch.AIDS.value})

SEMESTER_CHOICES = [(n, f"Semester {n}") for n in range(1, 9)]

# NOTE: use plain string values (Role.X.value) as dict keys / set members. Enum members
# hash differently from their string values.
ROLE_VALUES = frozenset(role.value for role in Role)
