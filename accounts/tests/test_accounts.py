import re
from urllib.parse import urlparse

from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import AuditEvent, User

from .helpers import NEW_PW, PW, BaseTestCase, make_admin, make_student, make_teacher

SIGNUP = {"full_name": "Asha Verma", "username": "asha", "email": "asha@example.test",
          "branch": "ECE", "semester": "4", "password1": PW, "password2": PW}


class SignupTests(BaseTestCase):
    def test_signup_creates_a_student_with_an_id_and_signs_in(self):
        response = self.client.post(reverse("accounts:signup"), SIGNUP)
        self.assertRedirects(response, reverse("student_dashboard"))
        user = User.objects.get(username="asha")
        self.assertEqual((user.role, user.public_id), ("student", "S1001"))
        self.assertEqual(user.student_profile.branch, "ECE")
        self.assertEqual(self.client.get("/api/me/").json()["public_id"], "S1001")

    def test_public_signup_cannot_choose_a_privileged_role(self):
        for role in ("admin", "teacher"):
            data = {**SIGNUP, "username": f"x{role}", "email": f"{role}@example.test",
                    "role": role, "public_id": "T1", "is_active": "on"}
            Client().post(reverse("accounts:signup"), data)
            self.assertEqual(User.objects.get(username=f"x{role}").role, "student")
        self.assertFalse(User.objects.filter(role="admin").exists())

    def test_passwords_are_hashed_with_pbkdf2(self):
        with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"]):
            Client().post(reverse("accounts:signup"), SIGNUP)
        user = User.objects.get(username="asha")
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertNotIn(PW, user.password)

    def test_duplicate_email_and_username_are_rejected_case_insensitively(self):
        make_student("asha", email="asha@example.test")
        response = Client().post(reverse("accounts:signup"), {**SIGNUP, "username": "ASHA", "email": "ASHA@Example.test"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is taken.")
        self.assertContains(response, "An account with this email already exists.")

    def test_weak_passwords_are_rejected(self):
        for weak in ("short1!", "password1234", "1234567890123"):
            response = Client().post(reverse("accounts:signup"), {**SIGNUP, "password1": weak, "password2": weak})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(User.objects.filter(username="asha").exists())

    def test_signup_is_rate_limited(self):
        for _ in range(10):
            Client().post(reverse("accounts:signup"), {**SIGNUP, "password2": "mismatch"})
        self.assertEqual(Client().post(reverse("accounts:signup"), SIGNUP).status_code, 429)
        self.assertFalse(User.objects.filter(username="asha").exists())


class LoginTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.student = make_student("stu1")

    def login(self, identifier="stu1", password=PW, client=None, **extra):
        return (client or self.client).post(reverse("accounts:login"),
                                            {"identifier": identifier, "password": password, **extra})

    def test_login_by_username_or_email_goes_to_role_dashboard(self):
        self.assertRedirects(self.login(), reverse("student_dashboard"))
        self.client.post(reverse("accounts:logout"))
        self.assertRedirects(self.login("STU1@example.test"), reverse("student_dashboard"))

    def test_each_role_lands_on_its_own_dashboard(self):
        make_teacher("teach1"); make_admin("boss")
        self.assertRedirects(self.login("teach1"), reverse("teacher_dashboard"))
        self.assertRedirects(self.login("boss", client=Client()), reverse("admin_dashboard"))

    def test_wrong_password_is_generic_and_audited_without_the_identifier(self):
        response = self.login(password="wrong-password-1")
        self.assertContains(response, "Username or password is incorrect.")
        unknown = self.login("nobody", "whatever-123")
        self.assertContains(unknown, "Username or password is incorrect.")
        event = AuditEvent.objects.filter(action="login_failed").first()
        self.assertNotIn("stu1", str(event.detail))

    def test_repeated_failures_lock_out_even_the_right_password(self):
        for _ in range(5):
            self.assertEqual(self.login(password="wrong-password-1").status_code, 200)
        response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(AuditEvent.objects.filter(action="login_blocked").exists())

    def test_suspended_account_cannot_sign_in(self):
        User.objects.filter(pk=self.student.pk).update(is_active=False)
        response = self.login()
        self.assertContains(response, "suspended")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_key_changes_on_login(self):
        session = self.client.session  # pre-login session, as an attacker could have planted
        session["probe"] = 1
        session.save()
        before = session.session_key
        self.login()
        self.assertNotEqual(self.client.session.session_key, before)

    def test_logout_requires_post_and_ends_the_session(self):
        self.login()
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(self.client.get("/student/").status_code, 302)

    def test_csrf_is_enforced_on_login(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(self.login(client=strict).status_code, 403)

    def test_next_parameter_cannot_redirect_off_site_or_into_forbidden_areas(self):
        self.assertRedirects(self.login(next="https://evil.example/"), reverse("student_dashboard"), fetch_redirect_response=False)
        self.client.post(reverse("accounts:logout"))
        self.assertRedirects(self.login(next="/administration/"), reverse("student_dashboard"), fetch_redirect_response=False)
        self.client.post(reverse("accounts:logout"))
        self.assertRedirects(self.login(next="/student/profile/"), "/student/profile/", fetch_redirect_response=False)


class TemporaryPasswordTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.teacher = make_teacher("teach1", must_change_password=True)
        self.client.force_login(self.teacher)

    def test_must_change_password_blocks_everything_else(self):
        response = self.client.get("/teacher/")
        self.assertRedirects(response, reverse("accounts:password_change"), fetch_redirect_response=False)
        api = self.client.get("/api/teacher/profile/")
        self.assertEqual((api.status_code, api.json()["error"]), (403, "password_change_required"))
        self.assertEqual(self.client.get(reverse("accounts:password_change")).status_code, 200)

    def test_changing_the_password_unlocks_the_account(self):
        url = reverse("accounts:password_change")
        same = self.client.post(url, {"old_password": PW, "new_password1": PW, "new_password2": PW})
        self.assertEqual(same.status_code, 200)  # reuse rejected
        self.client.post(url, {"old_password": PW, "new_password1": NEW_PW, "new_password2": NEW_PW})
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.must_change_password)
        self.assertTrue(self.teacher.check_password(NEW_PW))
        self.assertEqual(self.client.get("/teacher/").status_code, 200)  # still signed in


class PasswordResetTests(BaseTestCase):
    def request_reset(self, email):
        return self.client.post(reverse("accounts:password_reset"), {"email": email})

    def test_reset_flow_replaces_the_password(self):
        user = make_student("stu1")
        response = self.request_reset("stu1@example.test")
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"http://testserver(/accounts/reset/\S+)", mail.outbox[0].body).group(1)
        page = self.client.get(link, follow=True)
        confirm_url = page.redirect_chain[-1][0]
        done = self.client.post(confirm_url, {"new_password1": NEW_PW, "new_password2": NEW_PW})
        self.assertRedirects(done, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PW))
        self.assertTrue(AuditEvent.objects.filter(action="password_reset_completed").exists())

    def test_unknown_email_gets_the_same_response_and_no_email(self):
        response = self.request_reset("nobody@example.test")
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_requests_are_rate_limited(self):
        for _ in range(5):
            self.request_reset("nobody@example.test")
        self.assertEqual(self.request_reset("nobody@example.test").status_code, 429)


class ProfileTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.student = make_student("stu1")
        self.client.force_login(self.student)
        self.url = reverse("student_profile")

    def data(self, **overrides):
        base = {"full_name": "Stu Dent", "username": "stu1", "email": "stu1@example.test", "current_password": "",
                "phone": "", "branch": "CSE", "semester": "3", "academic_details": "", "github_url": "",
                "linkedin_url": "", "portfolio_url": "", "leetcode_username": "", "codeforces_username": "",
                "codechef_username": "", "hackerrank_username": ""}
        return {**base, **overrides}

    def test_profile_updates_and_completion_indicator(self):
        self.assertEqual(self.student.student_profile.completion()[0], 33)
        response = self.client.post(self.url, self.data(phone="+91 98765 43210", academic_details="Section B",
                                                        github_url="https://github.com/stu1", leetcode_username="stu1"))
        self.assertRedirects(response, self.url)
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.completion()[0], 100)

    def test_role_and_id_cannot_be_edited(self):
        self.client.post(self.url, self.data(role="admin", public_id="S9999", is_active=""))
        self.student.refresh_from_db()
        self.assertEqual((self.student.role, self.student.public_id, self.student.is_active), ("student", "S1001", True))

    def test_unsafe_link_schemes_are_rejected(self):
        for bad in ("javascript:alert(1)", "ftp://example.test/x"):
            response = self.client.post(self.url, self.data(github_url=bad))
            self.assertEqual(response.status_code, 200)
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.github_url, "")

    def test_changing_email_needs_the_current_password(self):
        response = self.client.post(self.url, self.data(email="new@example.test"))
        self.assertContains(response, "Enter your current password")
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "stu1@example.test")
        self.client.post(self.url, self.data(email="new@example.test", current_password=PW))
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "new@example.test")

    def test_cannot_take_another_users_username(self):
        make_student("taken")
        response = self.client.post(self.url, self.data(username="taken"))
        self.assertContains(response, "That username is taken.")
