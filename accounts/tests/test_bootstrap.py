import os
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command

from accounts.models import User

from .helpers import PW, BaseTestCase, make_admin


class BootstrapAdminTests(BaseTestCase):
    def run_command(self, password=PW, **overrides):
        args = {"username": "founder", "email": "founder@example.test", "full_name": "Founding Admin", **overrides}
        with mock.patch.dict(os.environ, {"EDUBRIDGE_ADMIN_PASSWORD": password}):
            call_command("bootstrap_admin", stdout=StringIO(), **args)

    def test_no_administrator_exists_until_bootstrap_runs(self):
        self.assertFalse(User.objects.filter(role="admin").exists())

    def test_creates_one_admin_with_a_hashed_password_and_no_public_id(self):
        self.run_command()
        admin = User.objects.get(role="admin")
        self.assertEqual((admin.username, admin.public_id), ("founder", None))
        self.assertTrue(admin.check_password(PW))
        self.assertNotIn(PW, admin.password)

    def test_refuses_a_second_run(self):
        self.run_command()
        with self.assertRaisesMessage(CommandError, "already exists"):
            self.run_command(username="second", email="second@example.test")
        self.assertEqual(User.objects.filter(role="admin").count(), 1)

    def test_refuses_weak_passwords(self):
        with self.assertRaises(CommandError):
            self.run_command(password="admin123")
        self.assertFalse(User.objects.filter(role="admin").exists())

    def test_refuses_when_an_admin_was_created_another_way(self):
        make_admin()
        with self.assertRaises(CommandError):
            self.run_command()
