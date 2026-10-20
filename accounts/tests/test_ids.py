import threading

from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase

from accounts import services
from accounts.constants import Role
from accounts.models import User

from .helpers import PW, BaseTestCase, make_admin, make_student, make_teacher


class IdAllocationTests(BaseTestCase):
    def test_ids_are_sequential_and_separate_per_role(self):
        self.assertEqual([make_student(f"s{i}").public_id for i in range(3)], ["S1001", "S1002", "S1003"])
        self.assertEqual(make_teacher("t1").public_id, "T1001")
        self.assertEqual(make_student("s9").public_id, "S1004")

    def test_admins_get_no_public_id(self):
        self.assertIsNone(make_admin().public_id)

    def test_database_rejects_duplicate_ids(self):
        first = make_student("a")
        second = make_student("b")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=second.pk).update(public_id=first.public_id)

    def test_database_rejects_ids_that_do_not_match_the_role(self):
        student = make_student("a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=student.pk).update(public_id="T5000")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=student.pk).update(role="admin")  # admin must have no ID


class ConcurrentSignupTests(TransactionTestCase):
    def test_parallel_signups_never_share_an_id(self):
        ids, errors = [], []
        lock = threading.Lock()

        def worker(n):
            try:
                for i in range(5):
                    user = services.create_user(
                        role=Role.STUDENT, username=f"w{n}_{i}", email=f"w{n}_{i}@example.test",
                        full_name="Worker", password=PW, profile={"branch": "CSE", "semester": 1})
                    with lock:
                        ids.append(user.public_id)
            except Exception as exc:  # noqa: BLE001 - report any failure to the main thread
                with lock:
                    errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        self.assertEqual(sorted(int(i[1:]) for i in ids), list(range(1001, 1041)))
