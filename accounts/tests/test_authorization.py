from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import AuditEvent, User

from .helpers import BaseTestCase, make_admin, make_student, make_teacher

PAGES = {
    "student": ["/student/", "/student/profile/"],
    "teacher": ["/teacher/", "/teacher/profile/"],
    "admin": ["/administration/", "/administration/users/",
              "/administration/users/new-teacher/", "/administration/audit/"],
}
APIS = {
    "student": ["/api/student/profile/"],
    "teacher": ["/api/teacher/profile/"],
    "admin": ["/api/admin/stats/", "/api/admin/users/"],
}


class RoleIsolationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.users = {"student": make_student(), "teacher": make_teacher(), "admin": make_admin()}

    def client_for(self, role):
        client = Client()
        client.force_login(self.users[role])
        return client

    def test_each_role_reaches_only_its_own_pages_and_apis(self):
        for role in self.users:
            client = self.client_for(role)
            for owner, urls in {**{k: PAGES[k] for k in PAGES}}.items():
                for url in urls:
                    expected = 200 if owner == role else 403
                    self.assertEqual(client.get(url).status_code, expected, f"{role} -> {url}")
            for owner, urls in APIS.items():
                for url in urls:
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200 if owner == role else 403, f"{role} -> {url}")
                    if owner != role:
                        self.assertEqual(response.json(), {"error": "forbidden"})

    def test_anonymous_users_are_redirected_or_get_401(self):
        client = Client()
        for urls in PAGES.values():
            for url in urls:
                response = client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("accounts:login")))
        for urls in APIS.values():
            for url in urls:
                self.assertEqual(client.get(url).status_code, 401)

    def test_student_and_teacher_cannot_use_admin_actions(self):
        victim = make_student("victim")
        for role in ("student", "teacher"):
            client = self.client_for(role)
            response = client.post(reverse("admin_user_status", args=[victim.pk]), {"action": "suspend"})
            self.assertEqual(response.status_code, 403)
            response = client.post(reverse("admin_teacher_new"), {
                "full_name": "Evil", "username": "evil", "email": "evil@example.test"})
            self.assertEqual(response.status_code, 403)
        victim.refresh_from_db()
        self.assertTrue(victim.is_active)
        self.assertFalse(User.objects.filter(username="evil").exists())

    def test_denied_attempts_are_audited(self):
        self.client_for("student").get("/administration/")
        event = AuditEvent.objects.get(action="authz_denied")
        self.assertEqual(event.actor, self.users["student"])
        self.assertEqual(event.detail["path"], "/administration/")

    def test_browser_supplied_role_claims_are_ignored(self):
        client = self.client_for("student")
        client.cookies["role"] = "admin"
        session = client.session
        session["role"] = "admin"
        session.save()
        response = client.get("/administration/?role=admin", HTTP_X_ROLE="admin")
        self.assertEqual(response.status_code, 403)

    def test_role_is_read_from_the_database_on_every_request(self):
        client = self.client_for("student")
        self.assertEqual(client.get("/student/").status_code, 200)
        User.objects.filter(pk=self.users["student"].pk).update(role="teacher", public_id="T9999")
        self.assertEqual(client.get("/student/").status_code, 403)
        self.assertEqual(client.get("/api/me/").json()["role"], "teacher")

    def test_suspended_users_lose_access_immediately(self):
        client = self.client_for("student")
        self.assertEqual(client.get("/student/").status_code, 200)
        User.objects.filter(pk=self.users["student"].pk).update(is_active=False)
        self.assertEqual(client.get("/student/").status_code, 302)  # session no longer valid

    def test_pages_are_not_cacheable(self):
        response = self.client_for("student").get("/student/")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])

    def test_students_have_no_way_to_name_another_student(self):
        # The student API takes no ID parameter: a query string cannot redirect it.
        other = make_student("other")
        data = self.client_for("student").get(f"/api/student/profile/?id={other.pk}&student_id={other.public_id}").json()
        self.assertEqual(data["student_id"], self.users["student"].public_id)


@override_settings(ROOT_URLCONF="accounts.tests.urls_undeclared")
class DefaultDenyTests(BaseTestCase):
    def test_view_without_declared_policy_is_refused_for_everyone(self):
        admin = make_admin()
        self.assertEqual(Client().get("/forgot/").status_code, 403)
        client = Client()
        client.force_login(admin)
        self.assertEqual(client.get("/forgot/").status_code, 403)
        self.assertTrue(AuditEvent.objects.filter(action="authz_denied", detail__reason="view_without_policy").exists())

    def test_declared_public_view_works(self):
        self.assertEqual(Client().get("/declared/").status_code, 200)
