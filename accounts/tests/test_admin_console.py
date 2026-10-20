from django.test import Client
from django.urls import reverse

from accounts.models import AuditEvent, User

from .helpers import NEW_PW, BaseTestCase, make_admin, make_student, make_teacher


class AdminConsoleTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_admin_creates_a_teacher_with_a_temporary_password(self):
        response = self.client.post(reverse("admin_teacher_new"), {
            "full_name": "Ravi Kumar", "username": "ravi", "email": "ravi@example.test",
            "department": "CSE", "designation": "Assistant Professor"})
        self.assertEqual(response.status_code, 200)
        teacher = User.objects.get(username="ravi")
        temp = response.context["temp_password"]
        self.assertEqual((teacher.role, teacher.public_id, teacher.must_change_password), ("teacher", "T1001", True))
        self.assertTrue(teacher.check_password(temp))
        self.assertContains(response, temp)
        self.assertEqual(teacher.teacher_profile.department, "CSE")
        # The temporary password is never written to the audit trail.
        event = AuditEvent.objects.get(action="teacher_account_created")
        self.assertNotIn(temp, str(event.detail))
        self.assertEqual(event.actor, self.admin)

    def test_new_teacher_must_change_password_then_works(self):
        response = self.client.post(reverse("admin_teacher_new"), {
            "full_name": "Ravi Kumar", "username": "ravi", "email": "ravi@example.test"})
        temp = response.context["temp_password"]
        teacher_client = Client()
        teacher_client.post(reverse("accounts:login"), {"identifier": "ravi", "password": temp})
        self.assertEqual(teacher_client.get("/teacher/").status_code, 302)
        teacher_client.post(reverse("accounts:password_change"),
                            {"old_password": temp, "new_password1": NEW_PW, "new_password2": NEW_PW})
        self.assertEqual(teacher_client.get("/teacher/").status_code, 200)

    def test_suspend_and_reactivate_with_audit_trail(self):
        student = make_student("stu1")
        student_client = Client()
        student_client.force_login(student)
        self.client.post(reverse("admin_user_status", args=[student.pk]), {"action": "suspend"})
        student.refresh_from_db()
        self.assertFalse(student.is_active)
        self.assertEqual(student_client.get("/student/").status_code, 302)  # existing session ended
        self.client.post(reverse("admin_user_status", args=[student.pk]), {"action": "reactivate"})
        student.refresh_from_db()
        self.assertTrue(student.is_active)
        self.assertEqual(list(AuditEvent.objects.filter(target_id=str(student.pk)).values_list("action", flat=True).order_by("id")),
                         ["account_suspended", "account_reactivated"])

    def test_admin_accounts_cannot_be_suspended_through_the_console(self):
        response = self.client.post(reverse("admin_user_status", args=[self.admin.pk]), {"action": "suspend"})
        self.assertEqual(response.status_code, 404)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_status_endpoint_rejects_get_and_unknown_actions(self):
        student = make_student("stu1")
        self.assertEqual(self.client.get(reverse("admin_user_status", args=[student.pk])).status_code, 405)
        self.client.post(reverse("admin_user_status", args=[student.pk]), {"action": "delete"})
        self.assertTrue(User.objects.filter(pk=student.pk, is_active=True).exists())

    def test_account_list_search_and_filters(self):
        make_student("stu1"); make_student("stu2", full_name="Meera Rao"); make_teacher("teach1")
        listing = lambda **q: [u.public_id for u in self.client.get(reverse("admin_users"), q).context["page"].object_list]
        self.assertEqual(listing(), ["S1001", "S1002", "T1001"])
        self.assertEqual(listing(q="meera"), ["S1002"])
        self.assertEqual(listing(q="t1001"), ["T1001"])
        self.assertEqual(listing(role="teacher"), ["T1001"])
        User.objects.filter(username="stu1").update(is_active=False)
        self.assertEqual(listing(status="suspended"), ["S1001"])

    def test_dashboard_counts_come_from_the_database(self):
        make_student("stu1", branch="ECE"); make_student("stu2", branch="ECE"); make_teacher("teach1")
        stats = self.client.get(reverse("admin_dashboard")).context
        self.assertEqual((stats["stats"]["students"], stats["stats"]["teachers"]), (2, 1))
        by_code = {b["code"]: b["count"] for b in stats["branches"]}
        self.assertEqual((by_code["ECE"], by_code["CSE"]), (2, 0))
        self.assertEqual(self.client.get("/api/admin/stats/").json(), {"students": 2, "teachers": 1, "suspended": 0})

    def test_audit_log_page_lists_events(self):
        make_student("stu1")
        self.client.post(reverse("admin_user_status", args=[User.objects.get(username="stu1").pk]), {"action": "suspend"})
        response = self.client.get(reverse("admin_audit"), {"action": "account_suspended"})
        self.assertContains(response, "account_suspended")
