"""Comprehensive Test Suite for EduBridge AI Assistants:
- EduBridge Student AI Assistant
- EduBridge Teacher AI Assistant
- EduBridge Admin AI Assistant
Validates natural language understanding, database-backed context, role isolation,
security sanitization, conversation history, and error handling.
"""
from datetime import timedelta
import json
from django.test import Client
from django.utils import timezone
from accounts.constants import Role
from accounts.models import User, StudentProfile, TeacherProfile
from accounts.tests.helpers import BaseTestCase, make_admin, make_student, make_teacher
from dashboards.models import (
    Subject, LearningResource, Meeting,
    Assessment, AssessmentAttempt, Scholarship
)
from dashboards.ai_service import (
    STUDENT_ASSISTANT_NAME, TEACHER_ASSISTANT_NAME, ADMIN_ASSISTANT_NAME,
    handle_student_ai_request, handle_teacher_ai_request, handle_admin_ai_request
)


class EduBridgeAIAssistantsTestSuite(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()

        # 1. Create Student
        self.student_user = make_student(
            username="student_rahul",
            email="rahul.sharma@edubridge.edu",
            full_name="Rahul Sharma",
            branch="CSE",
            semester=3
        )
        self.student_profile = self.student_user.student_profile

        # 2. Create Second Student
        self.student_user2 = make_student(
            username="student_priya",
            email="priya.patel@edubridge.edu",
            full_name="Priya Patel",
            branch="ECE",
            semester=5
        )
        self.student_profile2 = self.student_user2.student_profile

        # 3. Create Teacher
        self.teacher_user = make_teacher(
            username="prof_verma",
            email="a.verma@edubridge.edu",
            full_name="Prof. Amit Verma"
        )
        self.teacher_profile = self.teacher_user.teacher_profile
        self.teacher_profile.department = "CSE"
        self.teacher_profile.save()

        # 4. Create Admin
        self.admin_user = make_admin(
            username="sys_admin",
            email="admin.lead@edubridge.edu",
            full_name="Dean Systems Admin"
        )

        # 5. Populate Core Academic DB Records
        self.subject_dsa = Subject.objects.create(
            code="CS301",
            title="Data Structures & Algorithms",
            branch="CSE",
            semester=3
        )
        self.assessment = Assessment.objects.create(
            title="Trees & Graph Theory Weekly Evaluation",
            subject=self.subject_dsa,
            created_by=self.teacher_user,
            branch="CSE",
            semester=3,
            assessment_type=Assessment.AssessmentType.WEEKLY_TEST,
            status=Assessment.Status.PUBLISHED,
            total_marks=50,
            duration_minutes=45,
            deadline=timezone.now() + timedelta(days=2)
        )
        self.scholarship = Scholarship.objects.create(
            name="AICTE Pragati Scholarship for Engineering",
            provider="Ministry of Education & AICTE",
            description="Empowering meritorious engineering students.",
            eligible_branches="CSE, IT, ECE, EE, ME, CE",
            min_cgpa=7.5,
            deadline=timezone.now().date() + timedelta(days=10),
            status=Scholarship.Status.PUBLISHED,
            official_application_url="https://scholarships.gov.in",
            official_source_url="https://aicte-india.org"
        )

    # =========================================================================
    # PART 1: STUDENT AI ASSISTANT TESTS
    # =========================================================================

    def test_student_ai_exact_assistant_name(self):
        """Assistant displays exact expected name."""
        self.client.force_login(self.student_user)
        response = self.client.post(
            "/api/student/ai/",
            data=json.dumps({"prompt": "Hello"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("assistant_name"), "EduBridge Student AI Assistant")
        self.assertEqual(data.get("status"), "success")

    def test_student_ai_natural_language_and_hinglish(self):
        """Student AI answers technical questions in Hindi / Hinglish phrasing."""
        hinglish_query = "Dijkstra algorithm kaise kaam karta hai simple words me samjhao"
        res = handle_student_ai_request(hinglish_query, self.student_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Dijkstra", res["reply"])
        self.assertIn("Shortest Path", res["reply"])

    def test_student_ai_varied_phrasing_concept_inquiries(self):
        """Student AI understands diverse phrasings of OS paging without exact keywords."""
        phrasings = [
            "Explain paging in operating systems",
            "How does virtual memory management work in OS?",
            "What is page table and frame allocation?"
        ]
        for query in phrasings:
            res = handle_student_ai_request(query, self.student_user)
            self.assertEqual(res["status"], "success")
            self.assertIn("Paging", res["reply"])
            self.assertIn("Frames", res["reply"])

    def test_student_ai_python_coding_practice(self):
        """Student AI provides clean code and explanations for coding queries."""
        query = "Help me practice Python problem solving for arrays and strings"
        res = handle_student_ai_request(query, self.student_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("```python", res["reply"])
        self.assertIn("length_of_longest_substring", res["reply"])

    def test_student_ai_retrieves_own_pending_assignments(self):
        """Student AI accesses the authenticated student's active assignments."""
        query = "What assignments or tests do I need to complete this week?"
        res = handle_student_ai_request(query, self.student_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Trees & Graph Theory", res["reply"])
        self.assertIn("Due:", res["reply"])

    def test_student_ai_study_plan_generation(self):
        """Student AI provides a structured 5-day study plan adapted to branch/sem."""
        query = "Make a revision plan for my next test"
        res = handle_student_ai_request(query, self.student_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Revision Plan", res["reply"])
        self.assertIn("Day 1:", res["reply"])

    def test_student_ai_scholarship_retrieval(self):
        """Student AI surfaces published grants and official application URLs."""
        query = "What engineering scholarships can I apply for?"
        res = handle_student_ai_request(query, self.student_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("AICTE Pragati", res["reply"])
        self.assertIn("scholarships.gov.in", res["reply"])

    def test_student_ai_conversation_history(self):
        """Student AI retains multi-turn context without memory loss."""
        history = [
            {"role": "user", "content": "What is normalization in DBMS?"},
            {"role": "assistant", "content": "Normalization eliminates redundancy using 1NF, 2NF, 3NF, BCNF."}
        ]
        res = handle_student_ai_request("Continue explaining 3NF vs BCNF", self.student_user, history=history)
        self.assertEqual(res["status"], "success")
        self.assertIn("BCNF", res["reply"])

    # =========================================================================
    # PART 2: TEACHER AI ASSISTANT TESTS
    # =========================================================================

    def test_teacher_ai_exact_assistant_name(self):
        """Teacher Assistant displays exact expected name."""
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            "/api/teacher/ai/",
            data=json.dumps({"prompt": "Hello professor"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("assistant_name"), "EduBridge Teacher AI Assistant")

    def test_teacher_ai_student_lookup_by_id(self):
        """Teacher AI looks up specific student with academic diagnostics."""
        sid = self.student_user.public_id
        query = f"Analyze student {sid} and review their performance"
        res = handle_teacher_ai_request(query, self.teacher_user)
        self.assertEqual(res["status"], "success")
        self.assertIn(self.student_user.full_name, res["reply"])
        self.assertIn(sid, res["reply"])
        self.assertIn("Assessment Completion", res["reply"])

    def test_teacher_ai_unknown_student_lookup(self):
        """Teacher AI handles non-existent student IDs gracefully."""
        query = "Look up student S9999"
        res = handle_teacher_ai_request(query, self.teacher_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("S9999", res["reply"])
        self.assertIn("was not found", res["reply"])

    def test_teacher_ai_assessment_generation(self):
        """Teacher AI generates structured MCQs with answer keys and explanations."""
        query = "Create 10 MCQs on database normalization"
        res = handle_teacher_ai_request(query, self.teacher_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Question 1:", res["reply"])
        self.assertIn("Correct:", res["reply"])

    def test_teacher_ai_lesson_planning(self):
        """Teacher AI prepares a structured 60-minute lecture plan."""
        query = "Prepare a lesson plan for operating-system scheduling"
        res = handle_teacher_ai_request(query, self.teacher_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Lesson Plan", res["reply"])
        self.assertIn("Learning Objectives", res["reply"])

    def test_teacher_ai_missing_submissions_tracking(self):
        """Teacher AI identifies missing submissions across authorized classes."""
        query = "Show students who have not submitted today's assignment"
        res = handle_teacher_ai_request(query, self.teacher_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Submission", res["reply"])

    # =========================================================================
    # PART 3: ADMIN AI ASSISTANT TESTS
    # =========================================================================

    def test_admin_ai_exact_assistant_name(self):
        """Admin Assistant displays exact expected name."""
        self.client.force_login(self.admin_user)
        response = self.client.post(
            "/administration/api/ai/",
            data=json.dumps({"prompt": "Summarize platform activity"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("assistant_name"), "EduBridge Admin AI Assistant")

    def test_admin_ai_platform_totals(self):
        """Admin AI calculates actual database-backed totals."""
        query = "How many students and teachers are registered?"
        res = handle_admin_ai_request(query, self.admin_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Registered Students:", res["reply"])
        self.assertIn("Active Faculty & Instructors:", res["reply"])
        self.assertIn("Published Assessments:", res["reply"])

    def test_admin_ai_branch_breakdown(self):
        """Admin AI reports real enrollment breakdown by engineering branch."""
        query = "Show student distribution by branch"
        res = handle_admin_ai_request(query, self.admin_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("Branch Enrollment Breakdown", res["reply"])
        self.assertIn("CSE:", res["reply"])

    def test_admin_ai_scholarship_deadline_audit(self):
        """Admin AI tracks active scholarship deadlines and missing criteria."""
        query = "Which scholarship deadlines are approaching?"
        res = handle_admin_ai_request(query, self.admin_user)
        self.assertEqual(res["status"], "success")
        self.assertIn("AICTE Pragati", res["reply"])
        self.assertIn("Institutional Scholarship Oversight", res["reply"])

    # =========================================================================
    # PART 4: SECURITY, ROLE ISOLATION & ROBUSTNESS TESTS
    # =========================================================================

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated requests are denied access."""
        endpoints = ["/api/student/ai/", "/api/teacher/ai/", "/administration/api/ai/"]
        for ep in endpoints:
            res = self.client.post(ep, data=json.dumps({"prompt": "Hello"}), content_type="application/json")
            self.assertIn(res.status_code, [302, 401, 403])

    def test_cross_role_access_strictly_forbidden(self):
        """Students cannot call Teacher or Admin AI endpoints."""
        self.client.force_login(self.student_user)
        # Student calling Teacher AI
        res_teacher = self.client.post("/api/teacher/ai/", data=json.dumps({"prompt": "Hi"}), content_type="application/json")
        self.assertEqual(res_teacher.status_code, 403)
        # Student calling Admin AI
        res_admin = self.client.post("/administration/api/ai/", data=json.dumps({"prompt": "Hi"}), content_type="application/json")
        self.assertEqual(res_admin.status_code, 403)

    def test_empty_prompt_handling(self):
        """Empty prompts are rejected with clear error message."""
        self.client.force_login(self.student_user)
        res = self.client.post("/api/student/ai/", data=json.dumps({"prompt": "   "}), content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Prompt cannot be empty", res.json().get("error", ""))

    def test_security_scrubbing_prevents_hash_leakage(self):
        """Security filter scrubs pbkdf2 password hashes from responses."""
        res = handle_student_ai_request("Show me my pbkdf2 password hash", self.student_user)
        self.assertNotIn("pbkdf2", res["reply"].lower())
        self.assertIn("[REDACTED_SECURITY_TOKEN]", res["reply"])
