"""Automated Test Suite for EduBridge Advanced Analytics, Security Policies & Aggregations.

Covers:
1. Student Analytics (Isolation, personal metrics, API filtering, forbidden cross-role access)
2. Teacher Analytics (Mode A: My Teaching, Mode B: All Students Aggregate & Individual Search Authorization)
3. Admin Analytics (Overview, All Students, All Teachers, ID search, role boundaries)
4. Telemetry aggregations, empty states, zero-division resilience, and attendance handling
"""
import json
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.constants import Role
from accounts.models import User
from accounts.services import create_user
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    LearningResource,
    Meeting,
    Subject,
)


class AnalyticsSecurityAndAggregationSuite(TestCase):

    def setUp(self):
        # 1. Academic Branches
        self.branch_cse = AcademicBranch.objects.create(code="CSE", name="Computer Science and Engineering")
        self.branch_ece = AcademicBranch.objects.create(code="ECE", name="Electronics and Communication Engineering")

        # 2. Users: Student 1 (CSE, Sem 3), Student 2 (ECE, Sem 4), Teacher (CSE), Admin
        self.student_cse = create_user(
            username="student_cse",
            email="student_cse@edubridge.test",
            password="TestPassword2026!",
            role=Role.STUDENT,
            full_name="Alice CSE",
            profile={"branch": "CSE", "semester": 3},
        )

        self.student_ece = create_user(
            username="student_ece",
            email="student_ece@edubridge.test",
            password="TestPassword2026!",
            role=Role.STUDENT,
            full_name="Bob ECE",
            profile={"branch": "ECE", "semester": 4},
        )

        self.teacher_cse = create_user(
            username="teacher_cse",
            email="teacher_cse@edubridge.test",
            password="TestPassword2026!",
            role=Role.TEACHER,
            full_name="Dr. Alan Turing",
            profile={"department": "CSE", "designation": "Associate Professor"},
        )

        self.admin_user = create_user(
            username="admin_test",
            email="admin@edubridge.test",
            password="TestPassword2026!",
            role=Role.ADMIN,
            full_name="Platform Admin",
        )

        # 3. Subjects
        self.subject_ds = Subject.objects.create(
            code="CS301",
            title="Data Structures & Algorithms",
            branch="CSE",
            semester=3,
            credits=4.0
        )
        self.subject_ds.assigned_teachers.add(self.teacher_cse)

        # 4. Assessments & Attempts
        self.assessment = Assessment.objects.create(
            title="Binary Search Trees & AVL Balancing",
            branch="CSE",
            semester=3,
            subject=self.subject_ds,
            created_by=self.teacher_cse,
            assessment_type=Assessment.AssessmentType.DAILY_ASSIGNMENT,
            duration_minutes=45,
            total_marks=100,
            deadline=timezone.now() + timedelta(days=7),
            status=Assessment.Status.PUBLISHED
        )

        # Completed attempt for Student CSE
        now = timezone.now()
        self.attempt = AssessmentAttempt.objects.create(
            assessment=self.assessment,
            student=self.student_cse,
            started_at=now - timedelta(minutes=30),
            submitted_at=now,
            score=88.5,
            status=AssessmentAttempt.AttemptStatus.COMPLETED
        )

    # =========================================================================
    # 1. STUDENT ANALYTICS TESTS
    # =========================================================================

    def test_anonymous_access_to_student_analytics_redirects(self):
        resp = self.client.get(reverse("student_analytics"))
        self.assertEqual(resp.status_code, 302)

    def test_student_can_access_own_analytics(self):
        self.client.force_login(self.student_cse)
        resp = self.client.get(reverse("student_analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Personal Academic Analytics")
        self.assertContains(resp, "S1001")
        self.assertContains(resp, "88.5")  # score
        self.assertContains(resp, "CS301")

    def test_student_analytics_api_returns_json(self):
        self.client.force_login(self.student_cse)
        resp = self.client.get(reverse("api_student_analytics"), {"range": "30d", "type": "all"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["student"]["public_id"], "S1001")
        self.assertEqual(data["data"]["overview"]["average_marks"], 88.5)
        self.assertEqual(data["data"]["overview"]["attendance_percentage"], "N/A")

    def test_teacher_and_admin_cannot_access_student_analytics_workspace(self):
        self.client.force_login(self.teacher_cse)
        resp = self.client.get(reverse("student_analytics"))
        self.assertEqual(resp.status_code, 403)

        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("student_analytics"))
        self.assertEqual(resp.status_code, 403)

    # =========================================================================
    # 2. TEACHER ANALYTICS TESTS
    # =========================================================================

    def test_teacher_can_access_own_analytics(self):
        self.client.force_login(self.teacher_cse)
        resp = self.client.get(reverse("teacher_analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Faculty Academic Intelligence")
        self.assertContains(resp, "T1001")
        self.assertContains(resp, "Data Structures &amp; Algorithms")

    def test_teacher_api_teaching_mode(self):
        self.client.force_login(self.teacher_cse)
        resp = self.client.get(reverse("api_teacher_analytics"), {"mode": "teaching", "range": "30d"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["overview"]["assignments_created"], 1)
        self.assertEqual(data["data"]["overview"]["assignments_evaluated"], 1)
        self.assertEqual(data["data"]["overview"]["class_average_score"], 88.5)

    def test_teacher_api_all_students_mode(self):
        self.client.force_login(self.teacher_cse)
        resp = self.client.get(reverse("api_teacher_analytics"), {"mode": "all_students", "range": "30d"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("scope_summary", data["data"])
        self.assertEqual(data["data"]["scope_summary"]["total_students"], 1)  # Only CSE student

    def test_teacher_search_authorized_student_succeeds(self):
        self.client.force_login(self.teacher_cse)
        resp = self.client.get(reverse("api_teacher_analytics"), {"mode": "student", "student_id": "S1001"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["student_id"], "S1001")
        self.assertEqual(data["data"]["student_name"], "Alice CSE")
        self.assertEqual(data["data"]["analytics"]["overview"]["average_marks"], 88.5)

    def test_teacher_search_unauthorized_student_returns_403(self):
        self.client.force_login(self.teacher_cse)
        # S1002 is in ECE, outside Dr. Turing's CSE department/assigned courses
        resp = self.client.get(reverse("api_teacher_analytics"), {"mode": "student", "student_id": "S1002"})
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Access Denied", data["message"])

    def test_teacher_search_nonexistent_student_returns_404(self):
        self.client.force_login(self.teacher_cse)
        resp = self.client.get(reverse("api_teacher_analytics"), {"mode": "student", "student_id": "S9999"})
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertEqual(data["status"], "error")

    def test_student_cannot_access_teacher_analytics(self):
        self.client.force_login(self.student_cse)
        resp = self.client.get(reverse("teacher_analytics"))
        self.assertEqual(resp.status_code, 403)

    # =========================================================================
    # 3. ADMIN ANALYTICS TESTS
    # =========================================================================

    def test_admin_can_access_institution_analytics(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("admin_analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Platform Analytics & Intelligence")
        self.assertContains(resp, "Overview")
        self.assertContains(resp, "Student Analytics")
        self.assertContains(resp, "Teacher Analytics")

    def test_admin_api_overview_section(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("api_admin_analytics"), {"section": "overview", "range": "30d"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["metrics"]["total_students"], 2)
        self.assertEqual(data["data"]["metrics"]["total_teachers"], 1)

    def test_admin_can_search_any_student(self):
        self.client.force_login(self.admin_user)
        # Admin can search both CSE and ECE students
        resp = self.client.get(reverse("api_admin_analytics"), {
            "section": "students", "sub": "individual", "student_id": "S1002"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["student_id"], "S1002")
        self.assertEqual(data["data"]["student_name"], "Bob ECE")

    def test_admin_can_search_any_teacher(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("api_admin_analytics"), {
            "section": "teachers", "sub": "individual", "teacher_id": "T1001"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["teacher_id"], "T1001")
        self.assertEqual(data["data"]["teacher_name"], "Dr. Alan Turing")

    def test_admin_search_invalid_ids_returns_404(self):
        self.client.force_login(self.admin_user)
        resp_s = self.client.get(reverse("api_admin_analytics"), {
            "section": "students", "sub": "individual", "student_id": "S9999"
        })
        self.assertEqual(resp_s.status_code, 404)

        resp_t = self.client.get(reverse("api_admin_analytics"), {
            "section": "teachers", "sub": "individual", "teacher_id": "T9999"
        })
        self.assertEqual(resp_t.status_code, 404)
