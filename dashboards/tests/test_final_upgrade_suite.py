import json
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse

from accounts.constants import Role
from accounts.models import User, StudentProfile, TeacherProfile
from accounts.services import create_user
from dashboards.models import Subject, CodingResource, AttendanceRecord
from dashboards.analytics_service import get_student_enrolled_subjects, get_student_personal_analytics
from dashboards.attendance_service import record_platform_login_activity, update_attendance_record, get_student_attendance_summary


class FinalUpgradeSuiteTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Setup Student
        self.student = create_user(
            username="final_student",
            email="final_student@edubridge.edu",
            password="DemoPassword123!",
            role=Role.STUDENT,
            full_name="Final Test Student",
            profile={"branch": "CSE", "semester": 3}
        )
        self.student.student_profile.student_id = "S9999"
        self.student.student_profile.save()

        # 2. Setup Teacher
        self.teacher = create_user(
            username="final_teacher",
            email="final_teacher@edubridge.edu",
            password="DemoPassword123!",
            role=Role.TEACHER,
            full_name="Prof. Final Test",
            profile={"department": "CSE"}
        )

        # 3. Setup Admin
        self.admin = create_user(
            username="final_admin",
            email="final_admin@edubridge.edu",
            password="DemoPassword123!",
            role=Role.ADMIN,
            full_name="Dean Final Admin",
            profile={}
        )

        # 4. Setup 4 Subjects
        self.sub1 = Subject.objects.create(code="CS301", title="Data Structures", branch="CSE", semester=3, credits=4.0)
        self.sub2 = Subject.objects.create(code="CS302", title="Discrete Math", branch="CSE", semester=3, credits=4.0)
        self.sub3 = Subject.objects.create(code="CS303", title="DBMS", branch="CSE", semester=3, credits=4.0)
        self.sub4 = Subject.objects.create(code="CS304", title="Computer Org", branch="CSE", semester=3, credits=4.0)

        self.sub1.enrolled_students.add(self.student)
        self.sub2.enrolled_students.add(self.student)
        self.sub3.enrolled_students.add(self.student)
        self.sub4.enrolled_students.add(self.student)

        self.teacher.assigned_subjects.add(self.sub1, self.sub2)

    def test_enrolled_subjects_count_is_four(self):
        """Verify enrolled subjects bug is solved and resolves all 4 subjects."""
        enrolled = get_student_enrolled_subjects(self.student)
        self.assertEqual(enrolled.count(), 4)
        codes = list(enrolled.values_list("code", flat=True))
        self.assertIn("CS301", codes)
        self.assertIn("CS302", codes)
        self.assertIn("CS303", codes)
        self.assertIn("CS304", codes)

    def test_student_coding_hub_view_renders_areas_a_and_b(self):
        """Verify student coding page renders Area A (DSA) and Area B (Compilers) without embedded runner."""
        # Create published coding resources
        CodingResource.objects.create(
            title="Two Sum Problem",
            resource_type="dsa_question",
            topic_category="Arrays and Strings",
            difficulty="Easy",
            external_url="https://leetcode.com/problems/two-sum/",
            status="published",
            created_by=self.teacher
        )
        CodingResource.objects.create(
            title="Programiz Python Compiler",
            resource_type="compiler",
            platform_name="Programiz",
            supported_languages="Python 3",
            external_url="https://www.programiz.com/python-programming/online-compiler/",
            status="published",
            created_by=self.admin
        )

        self.client.force_login(self.student)
        resp = self.client.get(reverse("student_coding"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Coding Resources & DSA Practice Hub", content)
        self.assertIn("Two Sum Problem", content)
        self.assertIn("Programiz Python Compiler", content)
        self.assertIn("https://leetcode.com/problems/two-sum/", content)
        self.assertIn("target=\"_blank\"", content)
        self.assertIn("rel=\"noopener noreferrer\"", content)
        # Check in-platform runner is decommissioned
        self.assertNotIn("ace-editor", content)
        self.assertNotIn("Run Code (Sandbox)", content)

    def test_student_cannot_execute_or_submit_in_platform(self):
        """Legacy execution and submission endpoints return 403 Forbidden to students."""
        self.client.force_login(self.student)
        resp_run = self.client.post(reverse("api_coding_run"), data=json.dumps({"code": "print(1)"}), content_type="application/json")
        self.assertEqual(resp_run.status_code, 403)

        resp_sub = self.client.post(reverse("api_coding_submit"), data=json.dumps({"question_id": 1, "code": "print(1)"}), content_type="application/json")
        self.assertEqual(resp_sub.status_code, 403)

    def test_student_cannot_create_or_delete_coding_resources(self):
        """Students cannot create, edit, or delete coding resources."""
        self.client.force_login(self.student)
        resp_create = self.client.post(reverse("teacher_coding_resource_save"), data={"title": "Hacked Resource"})
        self.assertEqual(resp_create.status_code, 403)

        resp_admin_create = self.client.post(reverse("admin_coding_resource_save"), data={"title": "Hacked Resource"})
        self.assertEqual(resp_admin_create.status_code, 403)

    def test_teacher_coding_resource_lifecycle(self):
        """Teacher can create, publish, toggle status, and delete/archive coding resources."""
        self.client.force_login(self.teacher)

        # 1. Create a DSA Question via AJAX/JSON
        resp = self.client.post(
            reverse("teacher_coding_resource_save"),
            data={
                "title": "Reverse Linked List",
                "resource_type": "dsa_question",
                "topic_category": "Linked Lists",
                "difficulty": "Easy",
                "external_url": "https://leetcode.com/problems/reverse-linked-list/",
                "description": "Reverse a singly linked list in-place.",
                "status": "published"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        res_id = data.get("resource_id")
        self.assertTrue(CodingResource.objects.filter(id=res_id, title="Reverse Linked List").exists())

        # 2. Toggle status to draft
        resp_toggle = self.client.post(reverse("teacher_coding_resource_toggle_status", kwargs={"pk": res_id}))
        self.assertEqual(resp_toggle.status_code, 200)
        resource = CodingResource.objects.get(id=res_id)
        self.assertEqual(resource.status, "draft")

        # 3. Delete/Archive resource
        resp_del = self.client.post(reverse("teacher_coding_resource_delete", kwargs={"pk": res_id}))
        self.assertEqual(resp_del.status_code, 200)
        # Verify resource is removed or archived
        self.assertFalse(CodingResource.objects.filter(id=res_id, status="published").exists())

    def test_attendance_login_tracking_and_deduplication(self):
        """Automatic login creates platform_login attendance and does not duplicate on repeat login."""
        rec1 = record_platform_login_activity(self.student)
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1.session_type, "platform_login")
        self.assertEqual(rec1.status, "present")

        # Repeat login on same date should deduplicate and return same record
        rec2 = record_platform_login_activity(self.student)
        self.assertIsNotNone(rec2)
        self.assertEqual(rec1.id, rec2.id)

    def test_attendance_teacher_marking_and_student_read_only(self):
        """Teacher can mark class attendance, student cannot modify."""
        self.client.force_login(self.teacher)
        resp_mark = self.client.post(
            reverse("api_teacher_attendance_mark"),
            data=json.dumps({
                "student_id": self.student.id,
                "subject_id": self.sub1.id,
                "date": str(date.today()),
                "status": "present",
                "session_type": "class",
                "session_title": "Lecture 1: Intro"
            }),
            content_type="application/json"
        )
        self.assertEqual(resp_mark.status_code, 200)
        data = resp_mark.json()
        self.assertEqual(data.get("status"), "success")

        # Verify Student view is read-only
        self.client.force_login(self.student)
        resp_student = self.client.get(reverse("student_attendance"))
        self.assertEqual(resp_student.status_code, 200)
        self.assertIn("Personal Attendance Telemetry", resp_student.content.decode("utf-8"))

        # Student cannot mark attendance
        resp_hack = self.client.post(
            reverse("api_teacher_attendance_mark"),
            data=json.dumps({"student_id": self.student.id, "subject_id": self.sub1.id, "status": "present"}),
            content_type="application/json"
        )
        self.assertEqual(resp_hack.status_code, 403)

    def test_admin_attendance_correction_and_audit(self):
        """Admin can correct attendance records with audit tracking."""
        # Create an attendance record
        rec = AttendanceRecord.objects.create(
            student=self.student,
            subject=self.sub1,
            session_title="Lab 1",
            session_type="lab",
            date=date.today(),
            status="absent",
            recorded_by=self.teacher
        )

        self.client.force_login(self.admin)
        resp_correct = self.client.post(
            reverse("api_admin_attendance_correct"),
            data=json.dumps({
                "record_id": rec.id,
                "status": "present",
                "remarks": "Medical certificate submitted and verified."
            }),
            content_type="application/json"
        )
        self.assertEqual(resp_correct.status_code, 200)
        rec.refresh_from_db()
        self.assertEqual(rec.status, "present")
        self.assertIn("Admin Correction", rec.remarks)
        self.assertIn("Medical certificate", rec.remarks)

    def test_teacher_attendance_roster_does_not_raise_field_error(self):
        """Regression test: verify get_teacher_attendance_roster uses public_id on User correctly."""
        from dashboards.attendance_service import get_teacher_attendance_roster
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("teacher_attendance"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Class Attendance Roster", resp.content.decode("utf-8"))

        # Verify underlying service call returns valid structure without FieldError
        roster_data = get_teacher_attendance_roster(self.teacher)
        self.assertIn("roster", roster_data)
        self.assertIn("assigned_subjects", roster_data)
        self.assertIn("selected_subject", roster_data)

    def test_dark_mode_theme_script_and_toggle_present_in_base_template(self):
        """Verify dark mode initialization script and toggle button are rendered."""
        self.client.force_login(self.student)
        resp = self.client.get(reverse("student_dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("id=\"themeToggleBtn\"", content)
        self.assertIn("data-theme", content)
        self.assertIn("theme-icon-sun", content)
        self.assertIn("theme-icon-moon", content)

    def test_notifications_closed_by_default_and_endpoint(self):
        """Verify notifications API returns valid JSON and template specifies closed popover."""
        self.client.force_login(self.student)
        resp = self.client.get(reverse("student_dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("id=\"notificationPopover\" style=\"display: none;\"", content)

        # Call notification listing API
        resp_api = self.client.get(reverse("api_notifications_list"))
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json()
        self.assertIn("unread_count", data)
        self.assertIn("notifications", data)
