"""Comprehensive Master Test Suite for EduBridge Upgrades.

Covers:
1. Enrolled subjects resolution (verifying 4 enrolled subjects)
2. Sandboxed Code Execution Engine (Mode A & Mode B)
3. Hidden test-case security (hidden inputs/outputs never exposed to client)
4. Role permissions (students cannot create/edit DSA questions; teachers only access authorized cohorts)
5. Teacher Coding Analytics (Individual search by Student ID + Cohort aggregate)
6. Admin Coding Telemetry
7. Notification read/read-all flow and unread count decrement
8. AI Assistant topic switching without repeating old answers
"""
import json
from django.test import TestCase
from django.urls import reverse

from accounts.constants import Role
from accounts.models import StudentProfile, TeacherProfile, User
from accounts.services import create_user
from dashboards.analytics_service import get_student_enrolled_subjects
from dashboards.coding_service import (
    execute_sandboxed_code,
    grade_dsa_submission,
    get_student_coding_analytics,
    get_teacher_coding_overview,
    get_teacher_individual_student_coding,
    get_admin_coding_overview,
    seed_standard_dsa_questions,
)
from dashboards.models import CodingSubmission, DSAQuestion, DSATopic, PlatformNotification, Subject


class CodingAndMasterUpgradesTest(TestCase):
    def setUp(self):
        # Create Student
        self.student = create_user(
            username="test_student_cse",
            email="student_cse@edubridge.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            full_name="Jane CSE Student",
            profile={"branch": "CSE", "semester": 1}
        )
        self.student.student_profile.student_id = "S1001"
        self.student.student_profile.save()

        # Create Teacher
        self.teacher = create_user(
            username="test_faculty_cse",
            email="faculty_cse@edubridge.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            full_name="Prof. Sharma",
            profile={"department": "CSE"}
        )

        # Create Admin
        self.admin = create_user(
            username="test_admin_super",
            email="admin@edubridge.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
            full_name="Admin Director",
            profile={}
        )

        # Create 4 CSE Curriculum Subjects
        self.subj1 = Subject.objects.create(code="CS301", title="Data Structures & Algorithms", branch="CSE", semester=3, credits=4.0)
        self.subj2 = Subject.objects.create(code="CS302", title="Discrete Mathematics", branch="CSE", semester=3, credits=4.0)
        self.subj3 = Subject.objects.create(code="CS304", title="Computer Organization", branch="CSE", semester=3, credits=4.0)
        self.subj4 = Subject.objects.create(code="CS401", title="Operating Systems", branch="CSE", semester=4, credits=4.0)

        # Teacher assigned subject
        self.teacher.assigned_subjects.add(self.subj1, self.subj2)

        # Explicit enrollment of student into all 4 subjects
        self.subj1.enrolled_students.add(self.student)
        self.subj2.enrolled_students.add(self.student)
        self.subj3.enrolled_students.add(self.student)
        self.subj4.enrolled_students.add(self.student)

        # Seed standard DSA questions
        seed_standard_dsa_questions()

    def test_enrolled_subjects_resolution_returns_four_subjects(self):
        """Verify get_student_enrolled_subjects accurately resolves 4 subjects."""
        enrolled = get_student_enrolled_subjects(self.student)
        self.assertEqual(enrolled.count(), 4)
        codes = list(enrolled.values_list("code", flat=True))
        self.assertIn("CS301", codes)
        self.assertIn("CS302", codes)
        self.assertIn("CS304", codes)
        self.assertIn("CS401", codes)

    def test_sandboxed_python_code_execution(self):
        """Mode A: Execute isolated Python code and verify stdout capture and exit code."""
        code = "print('EduBridge Sandbox Online')\nprint(2 + 2)"
        res = execute_sandboxed_code("python", code, timeout_sec=3.0)
        self.assertEqual(res["status"], "success")
        self.assertIn("EduBridge Sandbox Online", res["stdout"])
        self.assertIn("4", res["stdout"])
        self.assertEqual(res["exit_code"], 0)
        self.assertGreater(res["execution_time_ms"], 0.0)

    def test_sandboxed_python_syntax_error(self):
        """Mode A: Syntax errors are properly categorized as compilation_error."""
        code = "def broken(:\n    pass"
        res = execute_sandboxed_code("python", code, timeout_sec=3.0)
        self.assertEqual(res["status"], "compilation_error")
        self.assertIn("SyntaxError", res["stderr"])

    def test_dsa_submission_grading_and_hidden_test_case_protection(self):
        """Mode B: Grade DSA submission, verify DB record and hidden test-case confidentiality."""
        question = DSAQuestion.objects.filter(topic=DSATopic.ARRAYS).first()
        self.assertIsNotNone(question)

        # Correct solution for array reversal
        solution_code = """import sys
def solve():
    lines = sys.stdin.read().split()
    if not lines: return
    n = int(lines[0])
    arr = lines[1:n+1]
    print(' '.join(arr[::-1]))
solve()
"""
        result = grade_dsa_submission(
            student=self.student,
            question=question,
            language="python",
            source_code=solution_code
        )
        self.assertEqual(result["status"], "accepted")
        self.assertGreater(result["passed_test_cases"], 0)
        self.assertEqual(result["passed_test_cases"], result["total_test_cases"])

        # Security check: hidden test case input/output must not be exposed to student
        for tc in result["test_case_results"]:
            if tc.get("hidden"):
                self.assertNotIn("input", tc)
                self.assertNotIn("actual_output", tc)

        # Verify DB persistence
        sub = CodingSubmission.objects.get(id=result["submission_id"])
        self.assertEqual(sub.status, "accepted")
        self.assertEqual(sub.student, self.student)

    def test_student_cannot_create_dsa_questions(self):
        """Security: Students are forbidden from creating or modifying DSA questions."""
        self.client.force_login(self.student)
        resp = self.client.post(reverse("api_teacher_dsa_create"), {
            "title": "Hacked Question",
            "topic": "arrays",
            "problem_statement": "Student injection test"
        })
        self.assertEqual(resp.status_code, 403)

    def test_teacher_can_create_and_publish_dsa_question(self):
        """Faculty can create and publish new questions."""
        self.client.force_login(self.teacher)
        payload = {
            "title": "Faculty Test Linked List",
            "topic": DSATopic.LINKED_LISTS,
            "difficulty": "Medium",
            "problem_statement": "Detect cycle in a singly linked list.",
            "sample_input": "3\n1 2 3",
            "sample_output": "true",
            "public_test_cases": [{"input": "3\n1 2 3", "output": "true", "explanation": "Cycle test"}]
        }
        resp = self.client.post(
            reverse("api_teacher_dsa_create"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(DSAQuestion.objects.filter(title="Faculty Test Linked List").exists())

    def test_teacher_individual_student_search_authorization(self):
        """Teacher can search authorized students; unauthorized student search returns 403."""
        # 1. Search student in authorized CSE branch
        res_auth = get_teacher_individual_student_coding(self.teacher, "S1001")
        self.assertTrue(res_auth["success"])
        self.assertEqual(res_auth["student_name"], self.student.full_name)

        # 2. Create student in Mechanical Engineering
        mech_student = create_user(
            username="student_me_other",
            email="student_me@edubridge.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            full_name="Other Student",
            profile={"branch": "ME", "semester": 1}
        )
        res_unauth = get_teacher_individual_student_coding(self.teacher, mech_student.public_id)
        self.assertFalse(res_unauth["success"])
        self.assertEqual(res_unauth["error"], "unauthorized")

    def test_teacher_and_admin_coding_overview(self):
        """Verify aggregate coding telemetry calculation."""
        teacher_overview = get_teacher_coding_overview(self.teacher)
        self.assertIn("cohort_summary", teacher_overview)
        self.assertIn("questions_table", teacher_overview)

        admin_overview = get_admin_coding_overview()
        self.assertIn("institution_summary", admin_overview)
        self.assertIn("questions_table", admin_overview)

    def test_notifications_read_and_red_dot_decrement(self):
        """Notification center updates unread counts and persists read status."""
        self.client.force_login(self.student)
        notif1 = PlatformNotification.objects.create(
            recipient=self.student,
            title="Assignment Graded",
            message="Your submission in CS301 was graded.",
            is_read=False
        )
        notif2 = PlatformNotification.objects.create(
            recipient=self.student,
            title="Live Lecture Alert",
            message="Prof. Sharma started a meeting.",
            is_read=False
        )

        # List notifications
        resp = self.client.get(reverse("api_notifications_list"))
        data = resp.json()
        self.assertEqual(data["unread_count"], 2)

        # Mark notif1 as read
        resp_read = self.client.post(reverse("api_notification_mark_read", kwargs={"pk": notif1.id}))
        self.assertEqual(resp_read.status_code, 200)

        # Verify unread count is now 1
        resp2 = self.client.get(reverse("api_notifications_list"))
        self.assertEqual(resp2.json()["unread_count"], 1)

        # Mark all read
        resp_all = self.client.post(reverse("api_notification_mark_all_read"))
        self.assertEqual(resp_all.status_code, 200)

        resp3 = self.client.get(reverse("api_notifications_list"))
        self.assertEqual(resp3.json()["unread_count"], 0)

    def test_ai_assistant_does_not_repeat_answers_on_topic_change(self):
        """AI Assistant dynamically addresses the new topic rather than repeating prior response."""
        self.client.force_login(self.student)

        # Turn 1: Ask about Python
        resp1 = self.client.post(
            reverse("student_ai_api"),
            data=json.dumps({"prompt": "What is Python?"}),
            content_type="application/json"
        )
        self.assertEqual(resp1.status_code, 200)
        reply1 = resp1.json()["reply"]
        self.assertIn("Python", reply1)

        # Turn 2: Switch topic completely to Dijkstra's algorithm
        history = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": reply1}
        ]
        resp2 = self.client.post(
            reverse("student_ai_api"),
            data=json.dumps({"prompt": "Can you explain Dijkstra's algorithm?", "history": history}),
            content_type="application/json"
        )
        self.assertEqual(resp2.status_code, 200)
        reply2 = resp2.json()["reply"]
        self.assertIn("Dijkstra", reply2)
        # Must NOT repeat the Python overview
        self.assertNotIn("What is Python?", reply2)
