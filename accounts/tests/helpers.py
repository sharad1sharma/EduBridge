from django.core.cache import cache
from django.test import TestCase

from accounts import services
from accounts.constants import Role

PW = "Correct-Horse-Battery-9"
NEW_PW = "Another-Strong-Pass-42"


def make_student(username="stu1", email=None, branch="CSE", semester=3, **kw):
    return services.create_user(
        role=Role.STUDENT, username=username, email=email or f"{username}@example.test",
        full_name=kw.pop("full_name", "Stu Dent"), password=kw.pop("password", PW),
        profile={"branch": branch, "semester": semester}, **kw)


def make_teacher(username="teach1", email=None, **kw):
    return services.create_user(
        role=Role.TEACHER, username=username, email=email or f"{username}@example.test",
        full_name=kw.pop("full_name", "Tea Cher"), password=kw.pop("password", PW), **kw)


def make_admin(username="boss", email=None, **kw):
    return services.create_user(
        role=Role.ADMIN, username=username, email=email or f"{username}@example.test",
        full_name=kw.pop("full_name", "Ad Min"), password=kw.pop("password", PW), **kw)


class BaseTestCase(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit counters live in the cache
        super().setUp()
