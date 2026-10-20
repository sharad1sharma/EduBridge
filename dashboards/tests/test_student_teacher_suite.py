import json
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone

from accounts import services
from accounts.constants import Role
from accounts.models import IdSequence, User
from accounts.tests.helpers import BaseTestCase, make_admin, make_student, make_teacher
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    LearningResource,
    Meeting,
    PlatformNotification,
    Scholarship,
    Subject,
)


class StudentTeacherModuleTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin(username="boss_admin")
        self.teacher = make_teacher(username="prof_sharma_test")
        self.student = make_student(username="student_rahul", branch="CSE", semester=3)
        self.other_student = make_student(username="student_anita", branch="ME", semester=3)

        # Setup core academic branch and subject
        self.branch_cse = AcademicBranch.objects.create(code="CSE", name="Computer Science and Engineering")
        self.subject = Subject.objects.create(
            code="CS301",
            title="Data Structures & Algorithms",
            branch="CSE",
            semester=3,
            credits=4.0
        )
        self.subject.assigned_teachers.add(self.teacher)

        # Setup standard 10-MCQ daily assignment
        self.daily_assessment = Assessment.objects.create(
            title="Trees and Graphs Daily Quiz",
            assessment_type=Assessment.AssessmentType.DAILY_ASSIGNMENT,
            branch="CSE",
            semester=3,
            subject=self.subject,
            created_by=self.teacher,
            duration_minutes=30,
            total_marks=40,
            deadline=timezone.now() + timedelta(days=2),
            questions_data=[
                {"id": 1, "question": "What is the worst-case search time in BST?", "options": ["O(1)", "O(log n)", "O(n)", "O(n log n)"], "correct": "C", "marks": 4},
                {"id": 2, "question": "Which traversal yields sorted sequence in BST?", "options": ["Preorder", "Inorder", "Postorder", "Levelorder"], "correct": "B", "marks": 4},
                {"id": 3, "question": "Balance factor range in AVL tree is:", "options": ["-1, 0, 1", "0, 1, 2", "-2, 0, 2", "Any integer"], "correct": "A", "marks": 4},
            ],
            auto_submit_on_tab_switch=True,
            max_tab_switches_allowed=3,
            status=Assessment.Status.PUBLISHED
        )

        # Setup standard published scholarship
        self.scholarship = Scholarship.objects.create(
            name="Merit Engineering Grant",
            provider="National Foundation",
            description="Excellence grant for engineering undergraduates",
            deadline=timezone.now().date() + timedelta(days=30),
            eligible_branches="CSE, IT",
            status=Scholarship.Status.PUBLISHED,
            official_application_url="https://gov.in/apply",
            official_source_url="https://gov.in"
        )

    # 1. Role Isolation & Access Boundaries
    def test_student_cannot_access_teacher_or_admin_views(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("teacher_students")).status_code, 403)
        self.assertEqual(self.client.get(reverse("teacher_assessments")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

    def test_teacher_cannot_access_admin_or_student_assessment_views(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("student_assessment", kwargs={"pk": self.daily_assessment.pk})).status_code, 403)

    def test_student_cannot_access_teacher_ai(self):
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse("teacher_ai_api"),
            data=json.dumps({"prompt": "Analyze students"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_access_student_ai(self):
        self.client.force_login(self.teacher)
        resp = self.client.post(
            reverse("student_ai_api"),
            data=json.dumps({"prompt": "My assignments"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 403)

    # 2. Student Read-Only Restrictions & Resource Views
    def test_teacher_resources_page_renders_with_null_file(self):
        self.client.force_login(self.teacher)
        # Create a resource without a file (external_url only)
        LearningResource.objects.create(
            title="Algorithm Analysis Notes",
            branch="CSE",
            semester=3,
            resource_type="pdf",
            external_url="https://example.com/algo-notes",
            file=None,
            author=self.teacher,
            status=LearningResource.Status.PUBLISHED
        )
        resp = self.client.get(reverse("teacher_resources"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Algorithm Analysis Notes")

    def test_student_resources_page_renders_with_null_file(self):
        self.client.force_login(self.student)
        LearningResource.objects.create(
            title="Database Architecture Guide",
            branch="CSE",
            semester=3,
            resource_type="notes",
            external_url="https://example.com/db-guide",
            file=None,
            author=self.teacher,
            status=LearningResource.Status.PUBLISHED
        )
        resp = self.client.get(reverse("student_resources"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Database Architecture Guide")

    def test_student_cannot_post_or_create_resources(self):
        self.client.force_login(self.student)
        resp = self.client.post(reverse("student_resources"), data={"title": "Hacked Note"})
        self.assertEqual(resp.status_code, 403)

    def test_student_and_teacher_cannot_manage_scholarships(self):
        self.client.force_login(self.student)
        # Student POST to student_scholarships forbidden
        self.assertEqual(self.client.post(reverse("student_scholarships"), data={"name": "Fake"}).status_code, 403)

        # Teacher POST to admin_scholarships forbidden
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(reverse("admin_scholarships"), data={"name": "Fake"}).status_code, 403)

    # 3. Assessment Player, Autosave & Anti-Cheating Policy
    def test_student_assessment_countdown_and_autosave(self):
        self.client.force_login(self.student)
        # Open assessment view
        resp = self.client.get(reverse("student_assessment", kwargs={"pk": self.daily_assessment.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Trees and Graphs Daily Quiz")
        self.assertContains(resp, "What is the worst-case search time in BST?")

        attempt = AssessmentAttempt.objects.get(assessment=self.daily_assessment, student=self.student)
        self.assertEqual(attempt.status, AssessmentAttempt.AttemptStatus.IN_PROGRESS)

        # Test autosave endpoint
        autosave_resp = self.client.post(
            reverse("student_assessment_autosave", kwargs={"pk": self.daily_assessment.pk}),
            data=json.dumps({"answers": {"1": "C", "2": "B"}, "tab_switch": False}),
            content_type="application/json"
        )
        self.assertEqual(autosave_resp.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.answers.get("1"), "C")
        self.assertEqual(attempt.answers.get("2"), "B")

    def test_tab_switch_auto_submission_when_threshold_exceeded(self):
        self.client.force_login(self.student)
        # Initialize attempt
        self.client.get(reverse("student_assessment", kwargs={"pk": self.daily_assessment.pk}))

        # Send repeated tab switch violations (threshold = 3)
        for i in range(3):
            resp = self.client.post(
                reverse("student_assessment_autosave", kwargs={"pk": self.daily_assessment.pk}),
                data=json.dumps({"answers": {"1": "C"}, "tab_switch": True}),
                content_type="application/json"
            )

        data = resp.json()
        self.assertEqual(data["status"], "auto_submitted")
        attempt = AssessmentAttempt.objects.get(assessment=self.daily_assessment, student=self.student)
        self.assertEqual(attempt.status, AssessmentAttempt.AttemptStatus.COMPLETED)
        self.assertTrue(attempt.is_auto_submitted)

    def test_duplicate_submission_prevented(self):
        self.client.force_login(self.student)
        # First submission
        self.client.get(reverse("student_assessment", kwargs={"pk": self.daily_assessment.pk}))
        submit_resp = self.client.post(
            reverse("student_assessment_submit", kwargs={"pk": self.daily_assessment.pk}),
            data={"q_1": "C", "q_2": "B"}
        )
        self.assertEqual(submit_resp.status_code, 302)

        attempt = AssessmentAttempt.objects.get(assessment=self.daily_assessment, student=self.student)
        self.assertEqual(attempt.status, AssessmentAttempt.AttemptStatus.COMPLETED)

        # Attempt to access player again after completion redirects to results
        replay_resp = self.client.get(reverse("student_assessment", kwargs={"pk": self.daily_assessment.pk}))
        self.assertEqual(replay_resp.status_code, 302)
        self.assertIn("/student/results/", replay_resp.url)

    # 4. Teacher Meeting Scheduling & Notification Dispatch
    def test_teacher_meeting_creates_notification_for_cohort(self):
        self.client.force_login(self.teacher)
        meet_time = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post(
            reverse("teacher_meeting_new"),
            data={
                "title": "Algorithms Doubt Clearing Session",
                "branch": "CSE",
                "semester": "3",
                "subject_id": self.subject.id,
                "scheduled_at": meet_time,
                "duration_minutes": "60",
                "meeting_link": "https://meet.google.com/test-room",
                "description": "Tutorial clarification for recursion tree"
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Meeting.objects.filter(title="Algorithms Doubt Clearing Session").exists())

        # Check that CSE student received the notification
        self.assertTrue(
            PlatformNotification.objects.filter(
                recipient=self.student,
                title__contains="Live Class Scheduled"
            ).exists()
        )
        # Check that ME student did NOT receive the notification
        self.assertFalse(
            PlatformNotification.objects.filter(
                recipient=self.other_student,
                title__contains="Live Class Scheduled"
            ).exists()
        )

    # 5. Teacher Student Directory & Diagnostics
    def test_teacher_student_directory_and_diagnostics(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("teacher_students"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.student.public_id)

        # Inspect student diagnostics
        diag_resp = self.client.get(reverse("teacher_student_detail", kwargs={"pk": self.student.pk}))
        self.assertEqual(diag_resp.status_code, 200)
        self.assertContains(diag_resp, self.student.full_name)
        self.assertContains(diag_resp, "Academic Diagnostics")

    # 6. Student AI & Teacher AI Assistants
    def test_student_ai_answers_from_database(self):
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse("student_ai_api"),
            data=json.dumps({"prompt": "What assignments do I have pending?"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("trees and graphs daily quiz", data["reply"].lower())

    def test_teacher_ai_answers_from_database(self):
        self.client.force_login(self.teacher)
        resp = self.client.post(
            reverse("teacher_ai_api"),
            data=json.dumps({"prompt": f"Analyze student {self.student.public_id}'s performance"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn(self.student.public_id, data["reply"])

    # 7. 4-Digit ID Exhaustion
    def test_id_range_exhaustion_handled(self):
        IdSequence.objects.filter(prefix="S").update(last_value=9999)
        with self.assertRaises(RuntimeError):
            services.allocate_public_id(Role.STUDENT.value)
