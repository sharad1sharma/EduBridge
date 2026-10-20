import json
from django.urls import reverse
from accounts.constants import Role
from accounts.models import AuditEvent, User
from accounts.tests.helpers import BaseTestCase, make_admin, make_student, make_teacher
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    LearningResource,
    Meeting,
    PlatformNotification,
    PlatformSetting,
    Scholarship,
    Subject,
)


class AdminSuiteTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin(username="test_admin")
        self.teacher = make_teacher(username="test_teacher")
        self.student = make_student(username="test_student", branch="CSE", semester=3)

        # Setup basic academic data
        self.branch_cse = AcademicBranch.objects.create(code="CSE", name="Computer Science and Engineering")
        self.subject = Subject.objects.create(
            code="CS301",
            title="Data Structures & Algorithms",
            branch="CSE",
            semester=3,
            credits=4.0
        )
        self.scholarship = Scholarship.objects.create(
            name="Merit Engineering Scholarship",
            provider="National Science Foundation",
            description="Excellence in engineering merit grant",
            deadline="2026-12-31",
            min_cgpa=8.5,
            eligible_branches="CSE, IT",
            status=Scholarship.Status.PUBLISHED,
        )

    # 1 & 2: Students and Teachers cannot access Admin pages or APIs
    def test_student_cannot_access_admin_dashboard(self):
        self.client.force_login(self.student)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_access_admin_analytics(self):
        self.client.force_login(self.student)
        resp = self.client.get(reverse("admin_analytics"))
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_access_admin_scholarships(self):
        self.client.force_login(self.student)
        resp = self.client.get(reverse("admin_scholarships"))
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_access_admin_ai_api(self):
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse("admin_ai_api"),
            data=json.dumps({"prompt": "How many students are there?"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_access_admin_dashboard(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_access_admin_students(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("admin_students"))
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_access_admin_scholarships(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("admin_scholarships"))
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_access_admin_ai_api(self):
        self.client.force_login(self.teacher)
        resp = self.client.post(
            reverse("admin_ai_api"),
            data=json.dumps({"prompt": "How many teachers are registered?"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 403)

    # 3 & 4: Only authorized administrators can manage scholarship records
    def test_admin_can_view_and_manage_scholarships(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_scholarships"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Merit Engineering Scholarship")

        # Admin creates new scholarship
        create_resp = self.client.post(
            reverse("admin_scholarships"),
            data={
                "action": "add_scholarship",
                "name": "Tata Tech Scholarship",
                "provider": "Tata Trust",
                "description": "Female engineers advancement scholarship",
                "official_application_url": "https://tatatrust.org/apply",
                "official_source_url": "https://tatatrust.org",
                "deadline": "2026-11-30",
                "min_cgpa": "8.0",
                "eligible_branches": "All Branches"
            }
        )
        self.assertEqual(create_resp.status_code, 302)
        self.assertTrue(Scholarship.objects.filter(name="Tata Tech Scholarship").exists())

    # 5: Account changes persist correctly (suspend/reactivate)
    def test_admin_student_status_toggle(self):
        self.client.force_login(self.admin)
        # Suspend student
        resp = self.client.post(
            reverse("admin_student_detail", kwargs={"pk": self.student.pk}),
            data={"action": "toggle_status"}
        )
        self.assertEqual(resp.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

        # Reactivate student
        resp2 = self.client.post(
            reverse("admin_student_detail", kwargs={"pk": self.student.pk}),
            data={"action": "toggle_status"}
        )
        self.assertEqual(resp2.status_code, 302)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    # 11: Destructive operations require confirmation
    def test_deliberate_confirmation_required_for_student_deletion(self):
        self.client.force_login(self.admin)
        sid = self.student.public_id
        # Attempt deletion with WRONG typed ID
        resp = self.client.post(
            reverse("admin_student_detail", kwargs={"pk": self.student.pk}),
            data={"action": "delete_account", "confirm_student_id": "WRONG_ID"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())

        # Now delete with EXACT matching public_id
        del_resp = self.client.post(
            reverse("admin_student_detail", kwargs={"pk": self.student.pk}),
            data={"action": "delete_account", "confirm_student_id": sid}
        )
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.student.pk).exists())

    # 8 & 9: Admin AI retrieves real database records & preserves safety
    def test_admin_ai_retrieves_platform_records(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("admin_ai_api"),
            data=json.dumps({"prompt": "How many students are registered?"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("student", data["reply"].lower())
        # Ensure passwords or hash secrets are NOT leaked in reply
        self.assertNotIn("pbkdf2", data["reply"])
        self.assertNotIn("password", data["reply"].lower())

    # 10: Audit logs record sensitive administrative actions
    def test_audit_logs_record_actions(self):
        self.client.force_login(self.admin)
        initial_count = AuditEvent.objects.count()
        self.client.post(
            reverse("admin_academic"),
            data={
                "action": "add_branch",
                "code": "AERO",
                "name": "Aerospace Engineering",
                "description": "Flight dynamics and avionics"
            }
        )
        self.assertGreater(AuditEvent.objects.count(), initial_count)
        self.assertTrue(AuditEvent.objects.filter(action="admin_branch_added").exists())

    # 12: Analytics match actual database records & CSV export works
    def test_analytics_and_csv_export(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Total Students")

        # Test CSV Export
        csv_resp = self.client.get(reverse("admin_export_csv", kwargs={"report_type": "students"}))
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp["Content-Type"], "text/csv")
        self.assertIn("Student ID", csv_resp.content.decode("utf-8"))
