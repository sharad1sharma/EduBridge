"""Automatic bootstrap and fallback verification for EduBridge evaluation accounts.

Ensures official demo accounts for Students, Faculty, and Administrators are always
guaranteed to exist with documented credentials, correct roles, and matching profiles.
"""
from django.db.models import Q
from accounts.constants import Role
from accounts.models import StudentProfile, TeacherProfile, User
from dashboards.models import Subject

DEMO_ACCOUNTS = {
    "admin": {
        "username": "admin",
        "email": "admin@edubridge.edu",
        "full_name": "Institution Administrator",
        "role": Role.ADMIN.value,
        "public_id": None,
        "aliases": ["admin", "admin@edubridge.edu", "a1001"],
        "passwords": ["AdminPassword123!", "EduBridgeAdmin2026!", "Demo@12345", "admin123"],
    },
    "prof_sharma": {
        "username": "prof_sharma",
        "email": "sharma@edubridge.edu",
        "full_name": "Prof. Rajesh Sharma",
        "role": Role.TEACHER.value,
        "public_id": "T1001",
        "aliases": [
            "prof_sharma",
            "t1001",
            "t2001",
            "sharma@edubridge.edu",
            "prof.sharma@edubridge.edu",
            "teacher@edubridge.edu",
        ],
        "passwords": ["TeacherPass123!", "EduBridgeTeacher2026!", "Demo@12345"],
        "profile": {
            "department": "CSE",
            "designation": "Professor & Head of Department",
            "bio": "Specialization: Data Structures & Algorithm Design",
        },
    },
    "prof_verma": {
        "username": "prof_verma",
        "email": "verma@edubridge.edu",
        "full_name": "Dr. Sunita Verma",
        "role": Role.TEACHER.value,
        "public_id": "T1002",
        "aliases": ["prof_verma", "t1002", "t2002", "verma@edubridge.edu"],
        "passwords": ["Demo@12345", "EduBridgeTeacher2026!"],
        "profile": {
            "department": "CSE",
            "designation": "Associate Professor",
            "bio": "Specialization: Operating Systems & Distributed Computing",
        },
    },
    "student_rahul": {
        "username": "student_rahul",
        "email": "rahul.sharma@edubridge.edu",
        "full_name": "Rahul Sharma",
        "role": Role.STUDENT.value,
        "public_id": "S1001",
        "aliases": ["student_rahul", "s1001", "rahul.sharma@edubridge.edu"],
        "passwords": ["Demo@12345", "EduBridgeStudent2026!", "TestPassword123!"],
        "profile": {
            "branch": "CSE",
            "semester": 3,
            "academic_details": "Roll: S1001. B.Tech Computer Science cohort.",
        },
    },
    "jane_wick_099": {
        "username": "jane_wick_099",
        "email": "jane.wick@edubridge.edu",
        "full_name": "Jane Wick",
        "role": Role.STUDENT.value,
        "public_id": "S1099",
        "aliases": ["jane_wick_099", "jane_wick", "s1099", "jane.wick@edubridge.edu"],
        "passwords": ["EduBridgeStudent2026!", "Demo@12345", "TestPassword123!"],
        "profile": {
            "branch": "CSE",
            "semester": 3,
            "academic_details": "Roll: S1099. B.Tech Computer Science cohort.",
        },
    },
    "student_priya": {
        "username": "student_priya",
        "email": "priya.patel@edubridge.edu",
        "full_name": "Priya Patel",
        "role": Role.STUDENT.value,
        "public_id": "S1002",
        "aliases": ["student_priya", "s1002", "priya.patel@edubridge.edu"],
        "passwords": ["Demo@12345", "EduBridgeStudent2026!"],
        "profile": {
            "branch": "CSE",
            "semester": 3,
            "academic_details": "Roll: S1002. B.Tech Computer Science cohort.",
        },
    },
}


def find_demo_config(identifier: str):
    clean = (identifier or "").strip().lower()
    for key, cfg in DEMO_ACCOUNTS.items():
        if clean == key or clean in [a.lower() for a in cfg.get("aliases", [])]:
            return cfg
    return None


def ensure_demo_user(identifier: str) -> User | None:
    cfg = find_demo_config(identifier)
    if not cfg:
        return None

    username = cfg["username"]
    public_id = cfg["public_id"]

    query = Q(username=username)
    if public_id:
        query |= Q(public_id=public_id)

    user = User.objects.filter(query).first()
    if not user:
        user = User(
            username=username,
            email=cfg["email"],
            full_name=cfg["full_name"],
            public_id=public_id,
            role=cfg["role"],
            is_active=True,
        )

    user.username = username
    user.email = cfg["email"]
    user.full_name = cfg["full_name"]
    user.role = cfg["role"]
    user.public_id = public_id
    user.is_active = True
    user.set_password(cfg["passwords"][0])
    user.save()

    if cfg["role"] == Role.STUDENT.value:
        sp, _ = StudentProfile.objects.get_or_create(
            user=user,
            defaults=cfg.get("profile", {"branch": "CSE", "semester": 3}),
        )
        for s in Subject.objects.filter(code__in=["CS301", "CS302", "CS303", "CS304", "MATHS1"]):
            user.enrolled_subjects.add(s)
    elif cfg["role"] == Role.TEACHER.value:
        TeacherProfile.objects.get_or_create(
            user=user,
            defaults=cfg.get("profile", {"department": "CSE"}),
        )

    return user


def ensure_all_demo_users():
    """Ensure all core evaluation accounts exist."""
    for key in DEMO_ACCOUNTS:
        ensure_demo_user(key)
