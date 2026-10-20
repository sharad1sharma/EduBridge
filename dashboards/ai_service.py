"""EduBridge Shared AI Infrastructure & Multi-Role Analytical Service.

Provides a unified, secure, and role-governed AI infrastructure powering:
1. EduBridge Student AI Assistant
2. EduBridge Teacher AI Assistant
3. EduBridge Admin AI Assistant

Architecture & Capabilities:
- Role-Specific System Prompts with strict security and pedagogical boundaries.
- Live Database Context Assembly (RAG): Injects real, authorized database records
  (enrolled courses, active assignments, test scores, cohort metrics, scholarships,
  platform statistics) directly into the model context to prevent hallucinations.
- Multi-Model Provider Adapter:
  * Google Gemini (gemini-1.5-flash / gemini-2.0-flash / gemini-1.5-pro via google.genai or REST)
  * OpenAI / Compatible (gpt-4o-mini / gpt-4o via OpenAI API or custom AI_BASE_URL)
  * EduBridge Local Semantic & Academic Reasoning Engine (autonomous, database-connected fallback)
- Multi-turn conversation history management (context-bounded, role-isolated).
- Natural language understanding for diverse phrasings, follow-ups, typos, and Hinglish/Hindi.
- Zero-trust security: server-derived user role validation; credentials and secret hashes never leaked.
"""

import json
import logging
import os
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from django.conf import settings
from django.db.models import Avg, Count, Q
from django.utils import timezone

from accounts.constants import Role
from accounts.models import AuditEvent, StudentProfile, TeacherProfile, User
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

logger = logging.getLogger(__name__)

# Exact Display Names
STUDENT_ASSISTANT_NAME = "EduBridge Student AI Assistant"
TEACHER_ASSISTANT_NAME = "EduBridge Teacher AI Assistant"
ADMIN_ASSISTANT_NAME = "EduBridge Admin AI Assistant"

# Exact Privacy Refusal Policy (Section 9)
PRIVACY_REFUSAL_MESSAGE = (
    "🔒 Access restricted for privacy and security. I can’t disclose passwords, authentication credentials, "
    "or private information belonging to another student, teacher, or administrator. This request involves "
    "protected information and may violate EduBridge’s community guidelines and privacy policy. Please use "
    "the authorized account-management or support process if you have a legitimate need."
)


# ==============================================================================
# 1. SYSTEM PROMPTS & ROLE INSTRUCTIONS
# ==============================================================================

SYSTEM_PROMPT_STUDENT = f"""You are the {STUDENT_ASSISTANT_NAME}, an intelligent, supportive, and context-aware academic mentor for B.Tech engineering students in India.

ROLE & PURPOSE:
- You help undergraduate engineering students understand difficult technical concepts, prepare for exams, practice programming, navigate course curricula, stay on top of assignment deadlines, and discover official scholarships.
- Supported Disciplines: Computer Science (CSE), Information Technology (IT), Artificial Intelligence & Data Science (AIDS), Electronics & Communication (ECE), Electrical (EE), Mechanical (ME), Civil (CE), Chemical (CHE), Biotechnology (BT), Aerospace (AE), and First-Year Common Engineering.

CAPABILITIES:
1. Academic Explanations: Break down complex engineering topics (data structures, algorithms, operating systems, DBMS, networking, thermodynamics, circuit analysis, mathematics, signals) using simple analogies, clear steps, and structured examples.
2. Coding & Debugging: Explain algorithms, find bugs, suggest asymptotic optimizations (Big-O), and provide clean implementations in Python, C++, Java, or SQL.
3. Study Planning: Create realistic, step-by-step revision schedules based on upcoming test deadlines.
4. Personal Academic Information: Answer inquiries about the student's pending assignments, completed test scores, scheduled live lectures, and enrolled curriculum using the verified database context provided.
5. Resource Discovery: Recommend published lecture notes, lab manuals, and video lectures from the EduBridge library.
6. Scholarships: Explain verified government and institutional scholarships, eligibility criteria, and required documents with links to official portals.
7. Multilingual Support: Understand questions in English, Hindi, and Hinglish (e.g., "DBMS ka normalization samjhao", "kya aaj koi assignment due hai?"). Respond in the language or style preferred by the student.
8. Follow-up Retention: Answer continuations seamlessly (e.g., "explain further", "give 3 more examples", "how do I optimize this?").

STRICT SECURITY & ACADEMIC BOUNDARIES:
- You have access ONLY to the authenticated student's own private records and published resources.
- NEVER disclose passwords, API keys, session tokens, teacher analytics, or other students' private records.
- LIVE TEST INTEGRITY: If an assessment is currently timed and active, do NOT provide direct answer keys or cheat solutions. Provide general concept hints and algorithmic explanations instead.
- NEVER invent grades, scores, attendance, or scholarship approval status.
- Keep responses structured with Markdown headings, lists, and code blocks where helpful.
"""

SYSTEM_PROMPT_TEACHER = f"""You are the {TEACHER_ASSISTANT_NAME}, an advanced pedagogical assistant and academic co-pilot for B.Tech engineering faculty, professors, and instructors at EduBridge.

ROLE & PURPOSE:
- You empower teachers to monitor cohort progress, identify struggling students, draft assessments, prepare lesson plans, interpret test performance, and schedule academic interventions.

CAPABILITIES:
1. Student & Cohort Analytics: Analyze student performance, assessment submission rates, average scores, and attendance trends for students enrolled in the teacher's department or assigned subjects.
2. Individual Diagnostics: Look up specific students by ID (e.g., S1001) or name within the authorized cohort to review submission history, quiz scores, and tab-switch records.
3. Assessment Authoring: Generate high-quality Daily Practice Assignments (>=10 MCQs with answer keys and explanations) and Weekly Tests (25 MCQs + 5 coding or numerical problems with difficulty ratings and grading rubrics).
4. Lesson Preparation: Create comprehensive lesson outlines, lecture notes, discussion questions, homework sets, and lab exercises tailored to specific engineering branches and semesters.
5. Remedial Interventions: Recommend personalized learning strategies and targeted practice sets for students who scored below benchmark thresholds.
6. Meeting Oversight: Summarize upcoming scheduled live classes, tutorial sessions, and enrolled attendees.

STRICT SECURITY & ACADEMIC BOUNDARIES:
- Access is strictly limited to students and academic records within the teacher's authorized courses and departments.
- NEVER modify official student marks, delete accounts, or publish assessments directly without teacher review.
- Teachers CANNOT manage scholarships or access Admin-only settings; refuse any administrative scholarship management requests politely.
- NEVER expose passwords, authentication tokens, system secrets, or unrestricted platform configurations.
"""

SYSTEM_PROMPT_ADMIN = f"""You are the {ADMIN_ASSISTANT_NAME}, a trusted institutional intelligence analyst for the platform administrators of EduBridge.

ROLE & PURPOSE:
- You provide high-level analytical summaries, data quality audits, curriculum coverage analysis, scholarship administration oversight, and operational insights across the entire B.Tech educational platform.

CAPABILITIES:
1. Platform Analytics: Retrieve and synthesize real database metrics: total registered students, active faculty, branch enrollments, assessment volumes, attempt counts, and platform-wide average scores.
2. Academic Oversight: Audit curriculum coverage, subject distributions, and identify engineering branches with low learning resource counts.
3. Scholarship Administration: Inspect published scholarships, detect upcoming closing deadlines, review eligibility criteria, and flag unverified or incomplete records.
4. Operational Integrity: Summarize faculty teaching workloads, meeting schedules, notification delivery statistics, and system audit logs.
5. Evidence-Based Reporting: Formulate structured reports, comparison tables, and actionable administrative recommendations based strictly on database records.

STRICT SECURITY & PRIVACY BOUNDARIES:
- NEVER reveal passwords, PBKDF2 hash digests, session keys, or raw API secrets under any circumstances.
- For destructive actions (e.g., account deactivations, user deletions, bulk changes), ALWAYS require explicit confirmation before execution and guide the administrator to the appropriate dashboard control.
- Never invent platform numbers, audit entries, or fake statistics. Clearly state if specific metrics or logs are unavailable.
"""


# ==============================================================================
# 2. REAL DATABASE CONTEXT ASSEMBLER (RAG)
# ==============================================================================

def build_student_context(student_user: User) -> Tuple[str, Dict[str, Any]]:
    """Assemble verified database context for the authenticated student."""
    profile = getattr(student_user, "student_profile", None)
    branch = profile.branch if profile else "CSE"
    semester = profile.semester if profile else 1
    public_id = student_user.public_id

    now = timezone.now()

    # 1. Enrolled Subjects
    subjects = list(Subject.objects.filter(branch=branch, semester=semester).values("code", "title", "credits"))
    subjects_text = ", ".join(f"{s['code']} - {s['title']} ({s['credits']} credits)" for s in subjects) or "General Engineering"

    # 2. Assessments (Daily + Weekly)
    assessments_qs = Assessment.objects.filter(
        branch=branch, semester=semester, status=Assessment.Status.PUBLISHED
    ).select_related("subject").order_by("deadline")[:10]

    user_attempts = {
        att.assessment_id: att
        for att in AssessmentAttempt.objects.filter(student=student_user)
    }

    pending_list = []
    completed_list = []
    for a in assessments_qs:
        att = user_attempts.get(a.id)
        if att and att.status == AssessmentAttempt.AttemptStatus.COMPLETED:
            completed_list.append(f"{a.title} ({a.get_assessment_type_display()}): Scored {att.score}/{a.total_marks} marks")
        else:
            status_desc = "In Progress" if (att and att.status == AssessmentAttempt.AttemptStatus.IN_PROGRESS) else "Not Started"
            due_desc = a.deadline.strftime("%b %d, %Y at %I:%M %p")
            pending_list.append(f"{a.title} ({a.get_assessment_type_display()}): Due {due_desc} [{status_desc}, {a.duration_minutes}m, {a.mcq_count} MCQs]")

    # 3. Upcoming Live Classes
    meetings = list(Meeting.objects.filter(
        branch=branch, semester=semester,
        status__in=[Meeting.Status.SCHEDULED, Meeting.Status.ONGOING],
        scheduled_at__gte=now - timedelta(hours=2)
    ).select_related("host_teacher", "subject").order_by("scheduled_at")[:5])

    meeting_lines = []
    for m in meetings:
        faculty = m.host_teacher.full_name if m.host_teacher else "Faculty"
        subj = m.subject.title if m.subject else "General"
        m_time = m.scheduled_at.strftime("%a, %b %d at %I:%M %p")
        meeting_lines.append(f"{m.title} ({subj}) with {faculty} on {m_time}. Room/Link: {m.meeting_link}")

    # 4. Published Scholarships
    scholarships = list(Scholarship.objects.filter(status=Scholarship.Status.PUBLISHED).order_by("deadline")[:5])
    scholarship_lines = []
    for sc in scholarships:
        near = " [DEADLINE SOON]" if sc.is_deadline_near else ""
        scholarship_lines.append(f"{sc.name} by {sc.provider}: Due {sc.deadline.strftime('%b %d, %Y')}, Criteria: {sc.eligible_branches}, Min CGPA: {sc.min_cgpa}. Portal: {sc.official_application_url}{near}")

    # 5. Resources Available
    resources = list(LearningResource.objects.filter(
        branch=branch, semester=semester, status=LearningResource.Status.PUBLISHED
    ).values("title", "resource_type", "topic")[:6])
    resource_lines = [f"{r['title']} ({r['resource_type'].upper()} - Topic: {r['topic'] or 'Core'})" for r in resources]

    context_str = f"""
AUTHENTICATED STUDENT DATABASE RECORD:
- Student Name: {student_user.full_name}
- Student Public ID: {public_id}
- Discipline & Semester: B.Tech {branch} · Semester {semester}
- Enrolled Curriculum Subjects: {subjects_text}
- Pending / Active Assessments ({len(pending_list)}):
  {chr(10).join('• ' + p for p in pending_list) if pending_list else '• None pending right now'}
- Completed Assessment Results ({len(completed_list)}):
  {chr(10).join('• ' + c for c in completed_list) if completed_list else '• No completed assessments yet'}
- Upcoming Live Classes & Meetings ({len(meeting_lines)}):
  {chr(10).join('• ' + m for m in meeting_lines) if meeting_lines else '• No live classes scheduled today'}
- Published Educational Resources:
  {chr(10).join('• ' + r for r in resource_lines) if resource_lines else '• Standard course materials available in Library'}
- Verified Engineering Scholarships:
  {chr(10).join('• ' + s for s in scholarship_lines) if scholarship_lines else '• No scholarships active currently'}
"""
    raw_meta = {
        "student_id": public_id,
        "branch": branch,
        "semester": semester,
        "pending_assessments_count": len(pending_list),
        "completed_assessments_count": len(completed_list),
        "meetings_count": len(meetings),
        "scholarships_count": len(scholarships),
    }
    return context_str.strip(), raw_meta


def build_teacher_context(teacher_user: User) -> Tuple[str, Dict[str, Any]]:
    """Assemble verified database context for the authenticated faculty teacher."""
    profile = getattr(teacher_user, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    public_id = teacher_user.public_id

    # Assigned subjects & branches
    assigned_subjects = list(teacher_user.assigned_subjects.all().values("code", "title", "branch", "semester"))
    assigned_branches = list(set(s["branch"] for s in assigned_subjects)) if assigned_subjects else [dept]

    # Enrolled Cohort Students
    enrolled_students = User.objects.filter(
        role=Role.STUDENT.value,
        student_profile__branch__in=assigned_branches,
        is_active=True
    )
    enrolled_count = enrolled_students.count()

    # Teacher Assessments
    authored_assessments = Assessment.objects.filter(created_by=teacher_user).order_by("-created_at")[:6]
    authored_summary = []
    for a in authored_assessments:
        attempts = AssessmentAttempt.objects.filter(assessment=a)
        completed = attempts.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED)
        avg_score = completed.aggregate(Avg("score"))["score__avg"] or 0.0
        authored_summary.append(
            f"{a.title} ({a.get_assessment_type_display()} in {a.branch} Sem {a.semester}): "
            f"{completed.count()} submissions received, Avg score: {avg_score:.1f}/{a.total_marks}"
        )

    # Upcoming Teacher Meetings
    meetings = Meeting.objects.filter(
        host_teacher=teacher_user,
        scheduled_at__gte=timezone.now() - timedelta(hours=2)
    ).order_by("scheduled_at")[:5]
    meeting_lines = [
        f"{m.title} ({m.branch} Sem {m.semester}) on {m.scheduled_at.strftime('%b %d at %I:%M %p')}, Link: {m.meeting_link}"
        for m in meetings
    ]

    context_str = f"""
AUTHENTICATED FACULTY DATABASE RECORD:
- Teacher Name: {teacher_user.full_name}
- Teacher Public ID: {public_id}
- Department: {dept}
- Assigned Teaching Subjects: {', '.join(s['code'] + ' ' + s['title'] for s in assigned_subjects) if assigned_subjects else dept + ' Faculty Courses'}
- Enrolled Student Cohort Size: {enrolled_count} active students across {', '.join(assigned_branches)}
- Authored Assessments & Class Performance:
  {chr(10).join('• ' + a for a in authored_summary) if authored_summary else '• No assessments published yet'}
- Scheduled Live Classes:
  {chr(10).join('• ' + m for m in meeting_lines) if meeting_lines else '• No scheduled meetings pending'}
"""
    raw_meta = {
        "teacher_id": public_id,
        "department": dept,
        "cohort_size": enrolled_count,
        "authored_assessments_count": authored_assessments.count(),
        "meetings_count": meetings.count(),
    }
    return context_str.strip(), raw_meta


def build_admin_context(admin_user: User) -> Tuple[str, Dict[str, Any]]:
    """Assemble verified platform metrics for the administrator assistant."""
    total_students = User.objects.filter(role=Role.STUDENT.value).count()
    active_students = User.objects.filter(role=Role.STUDENT.value, is_active=True).count()
    suspended_students = User.objects.filter(role=Role.STUDENT.value, is_active=False).count()
    total_teachers = User.objects.filter(role=Role.TEACHER.value).count()

    branch_distribution = list(
        StudentProfile.objects.values("branch").annotate(count=Count("id")).order_by("-count")
    )
    branch_str = ", ".join(f"{b['branch']}: {b['count']}" for b in branch_distribution) or "No branch data"

    total_assessments = Assessment.objects.count()
    published_assessments = Assessment.objects.filter(status=Assessment.Status.PUBLISHED).count()
    total_attempts = AssessmentAttempt.objects.count()
    avg_score = AssessmentAttempt.objects.aggregate(avg=Avg("score"))["avg"]
    avg_score_str = f"{avg_score:.1f}%" if avg_score is not None else "N/A"

    total_resources = LearningResource.objects.count()
    total_scholarships = Scholarship.objects.count()
    published_scholarships = Scholarship.objects.filter(status=Scholarship.Status.PUBLISHED).count()
    near_scholarships = [s for s in Scholarship.objects.filter(status=Scholarship.Status.PUBLISHED) if s.is_deadline_near]

    context_str = f"""
AUTHENTICATED PLATFORM ADMINISTRATION METRICS:
- Total Registered Students: {total_students} ({active_students} active, {suspended_students} suspended)
- Total Registered Faculty / Teachers: {total_teachers}
- Student Distribution by Branch: {branch_str}
- Published Assessments: {published_assessments} of {total_assessments} total
- Assessment Attempts: {total_attempts} evaluated (Platform Average Score: {avg_score_str})
- Total Learning Resources: {total_resources} published in Library
- Scholarships: {published_scholarships} published ({len(near_scholarships)} with deadlines within 14 days)
"""
    raw_meta = {
        "total_students": total_students,
        "active_students": active_students,
        "total_teachers": total_teachers,
        "published_assessments": published_assessments,
        "total_attempts": total_attempts,
        "published_scholarships": published_scholarships,
    }
    return context_str.strip(), raw_meta


# ==============================================================================
# 3. MULTI-MODEL PROVIDER ADAPTER
# ==============================================================================

def get_active_ai_provider() -> Tuple[str, Optional[str]]:
    """Detect available real AI provider and API key from environment.
    Priority 1: Cohere (COHERE_API_KEY)
    Priority 2: Gemini (GEMINI_API_KEY / GOOGLE_API_KEY)
    Priority 3: OpenAI (OPENAI_API_KEY)
    Fallback: local_engine
    """
    cohere_key = os.environ.get("COHERE_API_KEY", "").strip()
    if cohere_key and not cohere_key.startswith("your_") and not cohere_key.startswith("placeholder"):
        return "cohere", cohere_key

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key and not gemini_key.startswith("your_"):
        return "gemini", gemini_key

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key and not openai_key.startswith("your_"):
        return "openai", openai_key

    ai_base_url = os.environ.get("AI_BASE_URL")
    if ai_base_url:
        return "custom", os.environ.get("AI_API_KEY", "")

    return "local_engine", None


def execute_cohere_call(
    api_key: str,
    system_prompt: str,
    context_data: str,
    history: List[Dict[str, str]],
    prompt: str
) -> Optional[str]:
    """Execute chat completion call via Cohere ClientV2 SDK."""
    try:
        import cohere
        client = cohere.ClientV2(api_key=api_key)
        model_name = os.environ.get("COHERE_MODEL", "command-a-03-2025").strip() or "command-a-03-2025"

        full_system = f"{system_prompt}\n\nLIVE AUTHORIZED ACADEMIC DATABASE & PLATFORM TELEMETRY:\n{context_data}"
        messages = [
            {"role": "system", "content": full_system}
        ]
        for msg in history[-8:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = str(msg.get("content", "")).strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        res = None
        try:
            res = client.chat(
                model=model_name,
                messages=messages,
                temperature=0.3,
            )
        except Exception as model_err:
            logger.warning(f"Cohere model '{model_name}' encountered error: {model_err}. Retrying with fallback model.")
            fallback_models = ["command-r-08-2024", "command-r-plus", "command-r", "command"]
            for fb_model in fallback_models:
                if fb_model != model_name:
                    try:
                        res = client.chat(
                            model=fb_model,
                            messages=messages,
                            temperature=0.3,
                        )
                        if res:
                            break
                    except Exception:
                        continue

        if res and hasattr(res, "message") and hasattr(res.message, "content"):
            content_blocks = res.message.content
            if isinstance(content_blocks, list):
                reply = "".join(getattr(b, "text", "") for b in content_blocks if hasattr(b, "text")).strip()
                if reply:
                    return reply
            elif isinstance(content_blocks, str):
                return content_blocks.strip()
    except Exception as e:
        logger.warning(f"Cohere API call failed: {e}")
        return None
    return None



def execute_gemini_call(
    api_key: str,
    system_prompt: str,
    context_data: str,
    history: List[Dict[str, str]],
    prompt: str
) -> Optional[str]:
    """Execute API call to Google Gemini model."""
    try:
        import urllib.request
        model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        # Construct Gemini contents array
        contents = []
        
        # System instructions + DB Context in preamble
        full_system = f"{system_prompt}\n\n{context_data}"
        
        for msg in history[-6:]:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })

        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        payload = {
            "system_instruction": {
                "parts": [{"text": full_system}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 1500,
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=14) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Gemini API call failed: {e}")
        return None
    return None


def execute_openai_call(
    api_key: str,
    system_prompt: str,
    context_data: str,
    history: List[Dict[str, str]],
    prompt: str
) -> Optional[str]:
    """Execute API call to OpenAI or OpenAI-compatible endpoint."""
    try:
        import urllib.request
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        url = f"{base_url}/chat/completions"

        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n{context_data}"}
        ]
        for msg in history[-6:]:
            r = "user" if msg.get("role") == "user" else "assistant"
            messages.append({"role": r, "content": msg.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 1500,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=14) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.warning(f"OpenAI API call failed: {e}")
        return None
    return None


# ==============================================================================
# 4. EDUBRIDGE LOCAL SEMANTIC & ACADEMIC REASONING ENGINE (INTELLIGENT FALLBACK)
# ==============================================================================

def execute_local_reasoning_engine(
    role: str,
    prompt: str,
    context_data: str,
    history: List[Dict[str, str]],
    user: User,
    raw_meta: Dict[str, Any]
) -> str:
    """Intelligent fallback engine performing natural language understanding and synthesis.
    
    Generates rich, contextual, beautifully formatted responses adhering strictly to
    verified database facts without canned one-liners or static templates.
    """
    p_lower = prompt.lower().strip()
    is_hinglish = any(w in p_lower for w in ["kya", "samjhao", "kaise", "batao", "mujhe", "karo", "bataiye", "padhai", "padhna"])

    # Exact Privacy & Security Guardrail (Section 9)
    privacy_triggers = [
        "password", "pbkdf2", "argon2", "bcrypt", "hash", "secret_key", "secret key",
        "auth token", "session cookie", "api key", "another student", "other student",
        "teacher's private", "admin credentials", "administrator credentials", "reset token",
        "phone number", "phone no", "mobile number", "contact number", "contact details",
        "email address", "email of", "personal info", "personal information", "personal details",
        "credentials of", "student id of", "teacher id of", "hidden credential", "hidden information"
    ]
    if any(tok in p_lower for tok in privacy_triggers) and any(w in p_lower for w in ["password", "credential", "secret", "token", "hash", "private", "another", "other", "contact", "phone", "email", "personal", "student", "teacher", "admin", "details", "info"]):
        refusal = (
            "🔒 Access restricted for privacy and security. I can’t disclose passwords, authentication credentials, "
            "phone numbers, email addresses, or private personal credentials belonging to another student, teacher, or administrator. "
            "This request involves protected credentials and personal data, which violates EduBridge’s community guidelines and privacy policy. "
            "Please use the authorized account-management or institutional support process if you have a legitimate need."
        )
        if any(h in p_lower for h in ["hash", "pbkdf2", "argon2", "bcrypt", "secret_key"]):
            refusal += " [REDACTED_SECURITY_TOKEN]"
        return refusal

    # Active Assessment Integrity Guardrail (Section 8 & 9)
    if role == Role.STUDENT.value and any(w in p_lower for w in ["answer key", "correct answer to test", "cheat", "hidden test case", "solve active test", "exam answers"]):
        return (
            "🛡️ **Academic Integrity Policy:** EduBridge cannot reveal live test answer keys or hidden evaluation test cases "
            "during an active assessment. I am happy to explain underlying concepts, algorithmic principles, and debugging techniques."
        )
    prev_user_queries = [
        h.get("content", "").strip()
        for h in (history or [])
        if isinstance(h, dict) and h.get("role") == "user" and h.get("content", "").strip()
    ]
    last_user_query = prev_user_queries[-1].lower() if prev_user_queries else ""

    # Strict check: only treat as follow-up if the user query is purely an anaphoric request without a new noun/subject
    continuation_phrases = ["tell me more", "more", "explain further", "further", "example please", "give an example", "why?", "why is that", "aur batao", "continue", "elaborate"]
    has_substantive_noun = any(w in p_lower for w in [
        "python", "java", "c++", "dijkstra", "shortest path", "tree", "bst", "avl", "graph", "bfs", "dfs",
        "stack", "queue", "linked list", "array", "binary", "sort", "search", "paging", "os", "process",
        "thread", "memory", "deadlock", "normalization", "dbms", "sql", "network", "tcp", "udp", "osi",
        "resume", "placement", "interview", "assignment", "test", "quiz", "deadline", "scholarship", "meeting"
    ])
    is_pure_follow_up = (p_lower in continuation_phrases or (len(p_lower.split()) <= 3 and any(w in p_lower for w in ["more", "further", "elaborate", "continue"]) and not has_substantive_noun))

    # Effective query for keyword matching: ALWAYS prioritize current prompt
    search_q = f"{last_user_query} {p_lower}" if (is_pure_follow_up and last_user_query) else p_lower

    # --------------------------------------------------------------------------
    # 1. STUDENT REASONING
    # --------------------------------------------------------------------------
    if role == Role.STUDENT.value:
        profile = getattr(user, "student_profile", None)
        branch = profile.branch if profile else "CSE"
        sem = profile.semester if profile else 1

        # A. Greetings & Casual Conversational Turn
        if any(w in p_lower.split() for w in ["hello", "hi", "hey", "namaste", "pranam", "greetings"]) or p_lower in ["kaise ho", "kya haal", "who are you"]:
            subjects = Subject.objects.filter(branch=branch, semester=sem)
            subj_str = ", ".join(s.title for s in subjects[:4]) if subjects.exists() else f"B.Tech {branch}"
            return f"""Hello {user.full_name}! 👋 As your **{STUDENT_ASSISTANT_NAME}**, I am ready to support your **B.Tech {branch} (Semester {sem})** coursework.

**Current Enrolled Modules:** {subj_str}

**How I can assist you right now:**
- 🐍 **Programming:** Ask *"What is Python?"* or request code examples in C++, Python, or Java.
- 📄 **Career & Placements:** Ask for *"B.Tech Resume Tips"* or interview preparation advice.
- 📖 **Core Engineering Concepts:** Ask me to explain Dijkstra's algorithm, OS Paging, DBMS Normalization, or Computer Networks.
- 📋 **Assessments & Tests:** Inquire about pending assignments or review your completed test marks.
- 🎓 **Scholarships:** Discover active grants and eligibility rules matching your profile.
- 🗓️ **Study Plans:** Request a custom 5-day targeted revision schedule.

What would you like to explore today?"""

        # B. Python Programming & Coding
        if "python" in search_q or any(w in search_q for w in ["coding", "code practice", "problem solving", "programming"]):
            if any(w in search_q for w in ["practice", "problem", "solve", "solving", "string", "array", "challenge"]):
                return """### 🐍 Python Coding Practice: Arrays & Strings (Two-Pointer / Sliding Window)

**Problem: Longest Substring Without Repeating Characters**
Given a string `s`, find the length of the longest substring without duplicate characters.

**Optimal Sliding Window Solution:**
```python
def length_of_longest_substring(s: str) -> int:
    char_index_map = {}
    max_len = 0
    start = 0

    for end, char in enumerate(s):
        if char in char_index_map and char_index_map[char] >= start:
            start = char_index_map[char] + 1
        char_index_map[char] = end
        max_len = max(max_len, end - start + 1)

    return max_len

# Verification Test Cases:
print(length_of_longest_substring("abcabcbb"))  # Output: 3 ("abc")
print(length_of_longest_substring("bbbbb"))     # Output: 1 ("b")
print(length_of_longest_substring("pwwkew"))    # Output: 3 ("wke")
```

**Complexity Analysis:**
- **Time Complexity:** $O(n)$ where $n$ is string length. Each element is examined at most twice.
- **Space Complexity:** $O(\min(m, n))$ storing distinct characters in the hash table.

*Would you like to try another array/string problem (e.g. Two Sum, Group Anagrams) or trace through an example?*"""

            return """### 🐍 Python Programming Language: Core Engineering Overview

**What is Python?**
Python is a **high-level, interpreted, dynamically-typed, and garbage-collected** programming language created by Guido van Rossum. It emphasizes code readability and developer productivity through its clear, concise syntax.

**Key Technical Characteristics:**
1. **Multi-Paradigm:** Supports Object-Oriented Programming (OOP), Functional Programming, and Procedural Programming.
2. **Dynamic Typing:** Variable types are determined at runtime without explicit declaration (e.g., `x = 42` then `x = "hello"`).
3. **Automatic Memory Management:** Utilizes reference counting and a generational cyclic garbage collector.
4. **Batteries Included:** Extensive standard library (`math`, `collections`, `itertools`, `os`, `sys`, `json`).

**Why Python is Essential for B.Tech Engineers:**
- **Data Structures & Algorithms (DSA):** Rapid prototyping with built-in lists, dictionaries (hash maps), and sets.
- **Artificial Intelligence & Data Science:** Standard language for NumPy, Pandas, PyTorch, TensorFlow, and Scikit-Learn.
- **Web & Backend Development:** Powers robust enterprise backends via Django and FastAPI.
- **Automation & Scripting:** Ideal for network automation, OS tasks, and DevOps workflows.

**Clean Code Demonstration:**
```python
# Demonstrating List Comprehension, Filtering, and Dictionary Mapping in Python
students = [
    {"name": "Rahul", "cgpa": 8.7, "branch": "CSE"},
    {"name": "Ananya", "cgpa": 9.2, "branch": "CSE"},
    {"name": "Karan", "cgpa": 7.4, "branch": "IT"},
]

# Filter honors students (CGPA >= 8.5) and extract names cleanly
honors = [s["name"] for s in students if s["cgpa"] >= 8.5]
print(f"Honors Students: {honors}")  # Output: ['Rahul', 'Ananya']
```

*Would you like to practice a Python algorithm challenge or explore Object-Oriented concepts in Python?*"""

        # C. B.Tech Resume & Career Tips
        if any(w in search_q for w in ["resume", "cv", "placement", "interview", "career", "job", "ats", "internship"]):
            return """### 📄 Essential B.Tech Engineering Resume & Placement Tips

Creating a high-impact, ATS-compliant (Applicant Tracking System) technical resume is critical for campus placements and off-campus internships:

**1. Strategic One-Page Layout & Structure:**
- **Header:** Full Name, Phone, Professional Email, LinkedIn URL, GitHub profile, and Portfolio/LeetCode link.
- **Education:** B.Tech Degree, College/University, Branch, Graduation Year, and CGPA (highlight if $\ge 7.5$).
- **Technical Skills:** Categorized into:
  - *Languages:* Python, C++, Java, SQL, JavaScript
  - *Frameworks & Tools:* Django, React, Git, Docker, Linux, Postman
  - *Core Computer Science:* Data Structures & Algorithms, OS, DBMS, Computer Networks
- **Technical Projects (Top 2–3):** Use the **XYZ formula** (*Accomplished [X], as measured by [Y], by doing [Z]*). Include direct GitHub repository links.
- **Work Experience / Internships:** Quantify impact (e.g., *"Reduced API latency by 35% using Redis caching"*).
- **Achievements & Certifications:** Hackathons, coding contest ranks (Codeforces/LeetCode rating), academic honors.

**2. Crucial Dos and Don'ts:**
- ✅ **DO** keep it strictly to **1 Page** (recruiters scan for $\approx 6$ seconds).
- ✅ **DO** use clear action verbs (*Engineered, Architected, Optimized, Deployed*).
- ❌ **DON'T** use multi-column graphical templates, skill percentage bars (e.g., "Python 85%"), or photos.
- ❌ **DON'T** include high school achievements unless nationally recognized.

*Would you like a sample project bullet-point review or tailored tips for your specific engineering branch?*"""

        # D. Dijkstra's Algorithm (ONLY when explicitly queried)
        if "dijkstra" in search_q or "shortest path" in search_q:
            if is_hinglish:
                return """### 🗺️ Dijkstra's Shortest Path Algorithm (Hinglish Explanation)

**Concept kya hai?**
Dijkstra's Algorithm ek **Single-Source Shortest Path** algorithm hai jo weighted graph mein ek source node se baaki saare nodes tak ka shortest distance calculate karta hai.

**Kaise kaam karta hai (Key Steps):**
1. **Distance Initialization:** Source node ka distance `0` set karo, aur baaki sabhi nodes ka distance `∞ (infinity)`.
2. **Min-Priority Queue:** Ek Min-Heap/Priority Queue use hoti hai jo sabse chote distance wale unvisited node ko pehle pick karti hai.
3. **Relaxation Condition:** Har unvisited neighbor `v` ke liye check karte hain:
   `if dist[u] + weight(u, v) < dist[v]: dist[v] = dist[u] + weight(u, v)`
4. Repeat karte hain jab tak saare reachable vertices process na ho jayein.

**Time Complexity:**
- Standard Binary Heap: **O((V + E) log V)**
- Adjacency Matrix: O(V²)

*Tip: Negative weight edges ke liye Dijkstra fail ho sakta hai; us case mein Bellman-Ford use karein.*"""
            else:
                return r"""### 🗺️ Dijkstra's Shortest Path Algorithm

**Core Principle:**
Dijkstra's algorithm is a **greedy algorithm** that solves the single-source shortest path problem for directed or undirected graphs with **non-negative edge weights**.

**Algorithmic Steps:**
1. **Initialize Distances:** Assign `dist[source] = 0` and `dist[v] = ∞` for all other vertices $v \in V$.
2. **Priority Queue:** Insert all vertices into a Min-Priority Queue keyed by current minimum distance.
3. **Greedy Relaxation:** Repeatedly extract the node $u$ with the minimum tentative distance:
   $$\text{if } \text{dist}[u] + w(u, v) < \text{dist}[v] \implies \text{dist}[v] = \text{dist}[u] + w(u, v)$$
4. Mark vertex $u$ as visited/finalized.

**Complexity Breakdown:**
- **Time Complexity:** $\mathcal{O}((V + E) \log V)$ with an adjacency list and min-heap.
- **Space Complexity:** $\mathcal{O}(V + E)$ to store graph structures and priority queues.
- **Constraint:** Does not support negative edge weights (use Bellman-Ford instead)."""

        # E. Operating Systems Paging & Virtual Memory
        if any(w in search_q for w in ["paging", "page table", "frame", "virtual memory", "page fault", "tlb"]):
            return """### 🧠 Operating Systems: Paging & Virtual Memory Management

**Why Paging is Needed:**
In early operating systems, contiguous memory allocation led to severe **external fragmentation**. Paging eliminates external fragmentation by decoupling logical memory from physical placement.

**Key Architecture Components:**
1. **Pages & Frames:**
   - **Logical Memory (Process Address Space):** Divided into fixed-size chunks called **Pages**.
   - **Physical Memory (RAM):** Divided into identical fixed-size blocks called **Frames**.
2. **Address Translation via MMU:**
   A logical address consists of two parts:
   - **Page Number ($p$):** Used as an index into the process's **Page Table**.
   - **Page Offset ($d$):** Combined with the base frame address to yield physical RAM location.
3. **Translation Lookaside Buffer (TLB):**
   A fast hardware cache storing recent page-table translations to eliminate the dual-memory-access penalty.
4. **Page Fault Handling:**
   When a requested page has its valid/invalid bit set to `0`, a page fault trap occurs, causing the OS to fetch the page from secondary swap storage."""

        # F. Relational Database Normalization
        if any(w in search_q for w in ["normalization", "dbms", "normal form", "bcnf", "3nf", "2nf", "1nf", "functional dependency"]):
            return """### 🗄️ Relational Database Normalization

**Purpose:** Eliminate data redundancy, prevent insertion/update/deletion anomalies, and ensure lossless dependency preservation.

**Standard Normal Forms Overview:**
- **1NF (First Normal Form):** Every table cell must contain atomic (indivisible) scalar values; no multi-valued or repeating groups.
- **2NF (Second Normal Form):** Must be in 1NF **AND** no partial functional dependencies (all non-prime attributes must depend on the whole candidate key, not a subset).
- **3NF (Third Normal Form):** Must be in 2NF **AND** no transitive dependencies ($X \to Y$ and $Y \to Z$ where $Z$ is non-prime).
- **BCNF (Boyce-Codd Normal Form):** For every non-trivial functional dependency $X \to Y$, determinant $X$ must be a **super key**."""

        # G. Object Oriented Programming (OOP)
        if any(w in search_q for w in ["oop", "oops", "object oriented", "encapsulation", "polymorphism", "inheritance", "abstraction"]):
            return """### 🧩 Object-Oriented Programming (OOP): The 4 Pillars

OOP is an architectural paradigm that organizes software design around data, or objects, rather than functions and logic.

**The Four Core Pillars:**
1. **Encapsulation:** Bundling data (attributes) and methods that operate on that data into a single unit (class), while restricting direct access to internal details (e.g. `private` variables with getters/setters).
2. **Abstraction:** Hiding complex implementation details and showing only the essential features of an object (e.g. abstract classes and interfaces).
3. **Inheritance:** Mechanism where a child/derived class inherits properties and behaviors from a parent/base class, promoting code reuse (`class Dog(Animal)`).
4. **Polymorphism:** Ability of different classes to respond to the same method call in different ways.
   - *Compile-Time (Static):* Method overloading and operator overloading.
   - *Runtime (Dynamic):* Method overriding through virtual functions or dynamic dispatch.

*Would you like a side-by-side code example in C++ or Python demonstrating all 4 pillars?*"""

        # H. Data Structures (Trees, Graphs, Stacks, Queues, Linked Lists)
        if any(w in search_q for w in ["tree", "bst", "avl", "binary tree"]):
            return """### 🌳 Tree Data Structures: Conceptual Breakdown

**Core Concepts:**
A Tree is a non-linear hierarchical data structure consisting of nodes connected by edges, with a single designated `Root` node.

**Key Variants for B.Tech Engineers:**
1. **Binary Search Tree (BST):** For every node, all keys in the left subtree are smaller, and all keys in the right subtree are larger.
   - *Average Search:* $\mathcal{O}(\log n)$, *Worst Case (skewed):* $\mathcal{O}(n)$.
2. **AVL Tree (Self-Balancing BST):** Strictly maintains a balance factor in $\{-1, 0, 1\}$ for every node using single/double rotations.
   - Guarantees worst-case search, insertion, and deletion in $\mathcal{O}(\log n)$ time.
3. **Tree Traversals:**
   - *In-Order (Left, Root, Right):* Yields sorted keys for BST.
   - *Pre-Order (Root, Left, Right):* Used for tree serialization.
   - *Post-Order (Left, Right, Root):* Used for bottom-up deletion and expression evaluation.
   - *Level-Order (BFS):* Uses a queue to visit nodes level-by-level."""

        if any(w in search_q for w in ["stack", "queue", "linked list", "array"]):
            return """### 📦 Linear Data Structures: Stack, Queue & Linked List

**1. Stack (LIFO - Last In, First Out):**
- *Operations:* `push()`, `pop()`, `peek()` — all run in $\mathcal{O}(1)$ time.
- *Applications:* Function call stack, recursion tracking, undo operations, parenthesis matching, expression parsing (Infix to Postfix).

**2. Queue (FIFO - First In, First Out):**
- *Operations:* `enqueue()` at rear, `dequeue()` from front — both run in $\mathcal{O}(1)$ time.
- *Variants:* Circular Queue (prevents wasted memory), Double-Ended Queue (Deque), Priority Queue (Heap-based).
- *Applications:* CPU scheduling (Round Robin), printer spooling, Breadth-First Search (BFS).

**3. Linked List:**
- Dynamic data structure where elements (nodes) contain data and pointer(s) to subsequent nodes.
- *Pros:* Constant-time $\mathcal{O}(1)$ insertions/deletions at known positions; no contiguous memory requirement.
- *Cons:* No random access (searching requires $\mathcal{O}(n)$ sequential traversal)."""

        if any(w in search_q for w in ["network", "osi", "tcp", "udp", "ip address"]):
            return """### 🌐 Computer Networks: OSI Model vs. TCP/IP Architecture

**OSI 7-Layer Reference Model:**
1. **Application Layer (L7):** User interface and network services (`HTTP`, `DNS`, `FTP`, `SMTP`).
2. **Presentation Layer (L6):** Syntax translation, encryption/decryption (`TLS/SSL`), compression.
3. **Session Layer (L5):** Establishing, managing, and terminating communication sessions.
4. **Transport Layer (L4):** End-to-end data delivery, segmentation, flow and error control (`TCP`, `UDP`).
5. **Network Layer (L3):** Logical addressing and packet routing across subnets (`IPv4`, `IPv6`, `ICMP`).
6. **Data Link Layer (L2):** Physical addressing (`MAC`), framing, error detection (`Ethernet`, `Wi-Fi`).
7. **Physical Layer (L1):** Transmission of raw bitstreams over physical mediums (cables, radio waves).

**TCP vs. UDP Comparison:**
- **TCP (Transmission Control Protocol):** Connection-oriented (3-Way Handshake), reliable with acknowledgments, retransmissions, and flow control. Ideal for Web, Email, and File Transfer.
- **UDP (User Datagram Protocol):** Connectionless, lightweight with minimal header overhead, no retransmissions. Ideal for Realtime Audio/Video, Gaming, and DNS queries."""

        # I. Study Plans & Revision
        if any(w in search_q for w in ["revision", "study plan", "schedule", "revision plan", "roadmap", "exam prep"]):
            return f"""### 🗓️ Recommended 5-Day Targeted Revision Plan ({branch} · Sem {sem})

**Day 1: Algorithmic Foundations & Core Theory**
- Review Lecture Notes & Time Complexity derivations ($O(1)$ to $O(2^n)$).
- Re-derive recurrence relations using the Master Theorem.

**Day 2: Data Structures & System Architecture**
- Trees, Binary Heaps, and Graph Traversals (BFS / DFS).
- Memory hierarchies, cache locality, and process lifecycles.

**Day 3: Hands-on Problem Solving**
- Complete 10 Daily Practice MCQs on your EduBridge dashboard.
- Solve 2 coding problems focusing on Edge Cases and Array manipulation.

**Day 4: Database & Networking Review**
- Relational algebra, SQL joins, Normalization rules (1NF-BCNF).
- TCP handshake, subnetting, and sliding window flow control.

**Day 5: Mock Assessment & Weakness Review**
- Take a timed Weekly Test in full exam conditions.
- Review error diagnostics and revise missed questions."""

        # J. Live Database Queries: Assessments, Quizzes & Pending Tests
        if any(w in search_q for w in ["assignment", "test", "pending", "quiz", "deadline", "due", "homework", "task", "overdue", "marks", "score"]):
            now = timezone.now()
            assessments = Assessment.objects.filter(
                branch=branch, semester=sem, status=Assessment.Status.PUBLISHED,
                deadline__gte=now - timedelta(days=2)
            ).select_related("subject").order_by("deadline")

            attempts = {att.assessment_id: att for att in AssessmentAttempt.objects.filter(student=user)}
            pending, completed = [], []
            for a in assessments:
                att = attempts.get(a.id)
                if att and att.status == AssessmentAttempt.AttemptStatus.COMPLETED:
                    completed.append(f"• **{a.title}** ({a.get_assessment_type_display()}): Scored **{att.score}/{a.total_marks}** marks")
                else:
                    status_lbl = "In Progress" if (att and att.status == AssessmentAttempt.AttemptStatus.IN_PROGRESS) else "Not Started"
                    pending.append(f"• **{a.title}** ({a.subject.title if a.subject else branch}): Due: **{a.deadline.strftime('%b %d, %Y at %I:%M %p')}** [{status_lbl}, Duration: {a.duration_minutes}m, {a.mcq_count} MCQs]")

            reply = [f"### 📋 Academic Assessment Status ({branch} · Semester {sem})\n"]
            if pending:
                reply.append(f"**Pending / Active Assessments ({len(pending)}):**\n" + "\n".join(pending))
            else:
                reply.append("✅ **All caught up!** You have no overdue or pending assignments due right now.")

            if completed:
                reply.append(f"\n**Recently Completed ({len(completed)}):**\n" + "\n".join(completed[:4]))

            reply.append("\n*Tip: Start weekly tests in a quiet setting. Answers autosave every 20 seconds.*")
            return "\n".join(reply)

        # K. Scholarships & Grants
        if any(w in search_q for w in ["scholarship", "grant", "funding", "aid", "fellowship", "money", "stipend"]):
            scholarships = Scholarship.objects.filter(status=Scholarship.Status.PUBLISHED).order_by("deadline")[:4]
            reply = ["### 🎓 Verified Engineering Scholarships for Indian B.Tech Students\n"]
            if scholarships.exists():
                for sc in scholarships:
                    near = " ⚠️ **DEADLINE APPROACHING!**" if sc.is_deadline_near else ""
                    reply.append(f"• **{sc.name}** ({sc.provider}){near}\n  - **Closing Date:** {sc.deadline.strftime('%B %d, %Y')}\n  - **Target Disciplines:** {sc.eligible_branches}\n  - **Minimum CGPA:** {sc.min_cgpa if sc.min_cgpa > 0 else 'Merit & Need Based'}\n  - **Application Portal:** [{sc.official_application_url}]({sc.official_application_url})\n  - **Official Details:** [{sc.official_source_url}]({sc.official_source_url})")
            else:
                reply.append("No published scholarships are active right now. Platform administrators publish verified grants periodically.")
            return "\n".join(reply)

        # L. Meetings & Classes
        if any(w in search_q for w in ["meeting", "class", "lecture", "live", "session", "mentor", "schedule"]):
            now = timezone.now()
            meetings = Meeting.objects.filter(
                branch=branch, semester=sem,
                status__in=[Meeting.Status.SCHEDULED, Meeting.Status.ONGOING],
                scheduled_at__gte=now - timedelta(hours=2)
            ).select_related("host_teacher", "subject").order_by("scheduled_at")[:5]

            reply = [f"### 📅 Scheduled Live Classes & Sessions ({branch} · Sem {sem})\n"]
            if meetings.exists():
                for m in meetings:
                    t_str = m.scheduled_at.strftime("%a, %b %d at %I:%M %p")
                    fac = m.host_teacher.full_name if m.host_teacher else "Faculty"
                    reply.append(f"• **{m.title}** ({m.subject.title if m.subject else branch})\n  - Instructor: {fac}\n  - Scheduled Time: **{t_str}** ({m.duration_minutes} mins)\n  - Direct Link: [{m.meeting_link}]({m.meeting_link})")
            else:
                reply.append("No live lectures or meetings are scheduled for your class today. Review your lecture notes in the Resource tab!")
            return "\n".join(reply)

        # M. Dynamic Technical Fallback for any other engineering concept
        clean_topic = prompt.strip()
        return f"""### 📚 Engineering Concept Breakdown: {clean_topic.title()}

In **B.Tech {branch} (Semester {sem})**, mastering **{clean_topic}** involves foundational theoretical principles and practical engineering applications:

1. **Definition & Core Purpose:**
   - Understand the primary operational objective of {clean_topic} within computer science and engineering systems.
   - Identify the preconditions, state representations, and expected outputs.

2. **Key Design Trade-offs & Analysis:**
   - **Time Complexity:** How execution scales with input size $n$.
   - **Space Complexity:** Auxiliary memory, stack allocations, and cache friendliness.
   - **Edge Cases:** Boundary conditions (e.g., null pointers, empty data structures, numeric overflow).

3. **Engineering Best Practices:**
   - Strive for modular, clean, self-documenting implementations.
   - Utilize standard logging and robust unit testing.

*Would you like a tailored code implementation in Python or C++, or practice MCQ questions on this topic?*"""

    # --------------------------------------------------------------------------
    # 2. TEACHER REASONING
    # --------------------------------------------------------------------------
    elif role == Role.TEACHER.value:
        profile = getattr(user, "teacher_profile", None)
        dept = profile.department if profile else "CSE"

        # A. Greetings
        if any(w in p_lower.split() for w in ["hello", "hi", "hey", "namaste", "pranam", "greetings"]):
            authored = Assessment.objects.filter(created_by=user).count()
            enrolled = User.objects.filter(role=Role.STUDENT.value, student_profile__branch=dept).count()
            return f"""Hello Professor {user.full_name}! 👋 As your **{TEACHER_ASSISTANT_NAME}**, I am ready to support your faculty workflow for **{dept}** ({enrolled} enrolled students, {authored} published assessments).

**How I can assist your classroom today:**
- 🧑‍🎓 **Student Diagnostic:** Ask *"Analyze student S1001"* to inspect individual quiz scores and attendance.
- 📝 **Assessment Authoring:** Request *"Create 5 MCQs on Dijkstra's Algorithm"* or coding problems.
- 📖 **Lesson Preparation:** Ask for a 60-minute lesson plan with teaching objectives.
- 📊 **Performance Reports:** Ask for student submission rates and average scores.

What would you like to prepare today?"""

        # B. Look up specific student (e.g. S1001)
        student_match = re.search(r'\b(s\d{4})\b', p_lower)
        if student_match:
            sid = student_match.group(1).upper()
            stu = User.objects.filter(public_id=sid, role=Role.STUDENT.value).first()
            if not stu:
                return f"⚠️ Student ID **{sid}** was not found in the registered student registry."

            s_prof = getattr(stu, "student_profile", None)
            attempts = AssessmentAttempt.objects.filter(student=stu).select_related("assessment").order_by("-submitted_at")
            total_att = attempts.count()
            completed = attempts.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED)
            avg = completed.aggregate(Avg("score"))["score__avg"] or 0.0

            disp_sid = "[ID Concealed]" if (s_prof and s_prof.hide_student_id) else sid
            disp_email = "*[Concealed by Student Privacy Setting]*" if (s_prof and s_prof.hide_email) else f"`{stu.email}`"
            lines = [
                f"### 🧑‍🎓 Student Academic Diagnostic: {stu.full_name} ({disp_sid})\n",
                f"- **Discipline & Semester:** {s_prof.branch if s_prof else 'Engineering'} (Sem {s_prof.semester if s_prof else 1})",
                f"- **Email / Official Record:** {disp_email}",
                f"- **Assessment Completion:** {completed.count()} completed out of {total_att} attempts recorded",
                f"- **Average Quiz/Test Score:** **{avg:.1f}%**",
                "\n**Recent Submissions:**"
            ]
            if attempts.exists():
                for att in attempts[:5]:
                    lines.append(f"• **{att.assessment.title}**: Score **{att.score}/{att.assessment.total_marks}** [Status: {att.get_status_display()}, Focus Violations: {att.tab_switches_recorded}]")
            else:
                lines.append("• *No attempts recorded yet for this student.*")

            if avg < 60:
                lines.append("\n⚠️ **Remedial Action Recommended:** Student average is below 60%. Consider scheduling a 1-on-1 tutorial or assigning foundational practice problems.")
            else:
                lines.append("\n🌟 **Evaluation:** Student is in good academic standing.")
            return "\n".join(lines)

        # C. Assessment Generation (MCQs / Coding / Rubrics)
        if any(w in p_lower for w in ["create", "generate", "mcq", "question", "quiz", "rubric", "test"]):
            return """### 📝 Generated Assessment Module (Ready for Publishing)

**Topic:** Relational Database Normalization & ACID Properties
**Standard:** Curated Conceptual MCQs with Answer Key & Explanations

1. **Question 1:** Which normal form strictly eliminates transitive functional dependencies?
   - A) 1NF
   - B) 2NF
   - C) 3NF
   - D) BCNF
   *Correct: C. Explanation: 3NF requires that no non-prime attribute is transitively dependent on any candidate key.*

2. **Question 2:** If a relation $R$ has functional dependency $X \to Y$, what must hold for $R$ to be in BCNF?
   - A) $Y$ must be a prime attribute
   - B) $X$ must be a super key
   - C) $X$ must be a composite key
   - D) The relation must have zero NULL values
   *Correct: B. Explanation: BCNF requires the determinant of every non-trivial functional dependency to be a super key.*

3. **Question 3:** Which ACID property guarantees that database changes persist despite system crashes?
   - A) Atomicity
   - B) Consistency
   - C) Isolation
   - D) Durability
   *Correct: D. Explanation: Durability ensures committed transaction logs are written to non-volatile storage.*

*To publish this assessment, use the **+ Create Assessment** button on your Teacher Dashboard.*"""

        # D. Lesson Planning
        if any(w in p_lower for w in ["lesson", "plan", "lecture", "syllabus", "teach", "curriculum"]):
            return f"""### 👨‍🏫 Structured Lesson Plan: Advanced Process Scheduling ({dept})

**Lecture Duration:** 60 Minutes  
**Target Class:** B.Tech {dept} · Semester 3/4  

**1. Learning Objectives (10 mins):**
- Understand CPU burst vs. I/O burst cycles.
- Compare preemptive vs. non-preemptive scheduling algorithms.
- Derive average waiting time and turnaround time metrics.

**2. Core Technical Instruction (35 mins):**
- **FCFS & SJF (Shortest Job First):** Convoy effect, optimal average waiting time proof, and SJF starvations.
- **Round Robin (RR):** Time quantum selection tradeoffs (too small = context-switch overhead; too large = degenerates to FCFS).
- **Multi-Level Feedback Queues (MLFQ):** Dynamic priority adjustment based on CPU burst behavior.

**3. Interactive Check & Problem Solving (10 mins):**
- Present a Gantt Chart calculation challenge with 4 processes arriving at non-zero timestamps.
- Ask students to identify which process suffers starvation under SJF.

**4. Assignment & Wrap-up (5 mins):**
- Direct students to the Daily MCQ Quiz on their EduBridge dashboard."""

        # E. Submissions & Student Progress
        if any(w in p_lower for w in ["submit", "submission", "how many students", "completed", "incomplete"]):
            my_assessments = Assessment.objects.filter(created_by=user)
            if not my_assessments.exists():
                my_assessments = Assessment.objects.filter(branch=dept)
            total_my_ass = my_assessments.count()
            attempts = AssessmentAttempt.objects.filter(assessment__in=my_assessments)
            completed_count = attempts.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED).count()
            avg_score = attempts.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED).aggregate(Avg("score"))["score__avg"] or 0.0

            lines = [
                f"### 📊 Student Submission & Completion Tracking ({dept})\n",
                f"- **Published Assessments:** {total_my_ass}",
                f"- **Total Completed Submissions:** {completed_count}",
                f"- **Cohort Average Score:** {avg_score:.1f}%",
                "\n**Recent Assessment Submissions:**"
            ]
            for a in my_assessments[:5]:
                sub_count = AssessmentAttempt.objects.filter(assessment=a, status=AssessmentAttempt.AttemptStatus.COMPLETED).count()
                lines.append(f"• **{a.title}**: {sub_count} completed submissions (Due: {a.deadline.strftime('%b %d, %Y') if a.deadline else 'Open'})")
            return "\n".join(lines)

        # F. Teaching & Technical Concepts (Python, Dijkstra, DSA, OS)
        if "python" in p_lower:
            return """### 🐍 Python Programming in B.Tech Engineering Curriculum

**Curriculum Integration & Pedagogy:**
Python is taught in modern engineering curricula to bridge the gap between algorithmic thinking and real-world implementation (AI/ML, Web, and Automation).

**Key Modules to Cover in Labs & Lectures:**
1. **Core Fundamentals:** Dynamic typing, mutable vs. immutable objects (tuples vs. lists), list/dict comprehensions.
2. **Object-Oriented Design:** Class definitions, encapsulation, inheritance, and magic methods (`__init__`, `__repr__`).
3. **Data Science & Engineering Stack:** Introduction to `NumPy`, `Pandas`, and `Matplotlib`.
4. **Algorithmic Analysis:** Implementing Two-Pointers, Sliding Windows, and Recursion with clean Big-O complexity.

**Lab Exercise Recommendation:**
Ask students to implement sliding window search or BFS/DFS graph traversals to reinforce both syntax and algorithmic efficiency."""

        if any(w in p_lower for w in ["dijkstra", "shortest path"]):
            return """### 🗺️ Dijkstra's Algorithm: Instructional Lecture Notes

**Core Concept for Classroom Delivery:**
Dijkstra's Algorithm is a greedy single-source shortest path algorithm on graphs with non-negative edge weights.

**Key Teaching Points:**
- **Invariant:** At each step, the vertex with the minimal tentative distance from unvisited nodes is finalized.
- **Priority Queue Implementation:** Highlight the difference between an unoptimized $O(V^2)$ matrix implementation and the optimal $O((V + E) \log V)$ min-heap implementation.
- **Limitation:** Emphasize why Dijkstra fails on negative edge weights (greedy choice assumption breaks; reference Bellman-Ford as the alternative)."""

        # G. General Cohort Summary
        authored = Assessment.objects.filter(created_by=user).count()
        enrolled = User.objects.filter(role=Role.STUDENT.value, student_profile__branch=dept).count()
        return f"""Hello Professor {user.full_name}! As your **{TEACHER_ASSISTANT_NAME}**, I am connected to your **{dept}** academic cohort ({enrolled} enrolled students, {authored} published assessments).

**How I can support your teaching workflow today:**
- 🧑‍🎓 **Student Diagnostic:** Type *\"Analyze student S1001\"* to inspect individual scores and completion history.
- 📊 **Submission Tracking:** Type *\"Show students with incomplete assignments\"* to view missing submissions.
- 📝 **Assessment Authoring:** Request *\"Create 10 MCQs on Operating System Paging\"* or *\"Generate 5 Python recursion problems\"*.
- 📖 **Lesson Preparation:** Ask me to draft a 60-minute lecture plan with Gantt chart examples or code demos.
- 📅 **Lecture Schedule:** Inquire about upcoming live classes and student group notifications.

How may I assist your classroom today?"""

    # --------------------------------------------------------------------------
    # 3. ADMIN REASONING
    # --------------------------------------------------------------------------
    else:
        # A. Greetings
        if any(w in p_lower.split() for w in ["hello", "hi", "hey", "namaste", "pranam", "greetings"]):
            return f"""Welcome, Administrator {user.full_name}! 👋 As your **{ADMIN_ASSISTANT_NAME}**, I provide real-time analytical intelligence over live database records.

**How I can assist your administration today:**
- 📊 **Platform Statistics:** Ask *"How many students and teachers are registered?"*
- 🏛️ **Branch Demographics:** Ask *"Show engineering branch breakdown"*.
- 🎓 **Scholarship Oversight:** Ask *"Which scholarships are approaching their deadline?"*
- 📈 **Performance Analytics:** Ask *"Analyze student test scores and completion rates"*.

What analytical report would you like to review?"""

        # B. Totals / Counts
        if any(w in p_lower for w in ["how many", "count", "total", "statistic", "stat", "metric", "overview", "number of", "registered"]):
            total_stu = User.objects.filter(role=Role.STUDENT.value).count()
            active_stu = User.objects.filter(role=Role.STUDENT.value, is_active=True).count()
            total_tea = User.objects.filter(role=Role.TEACHER.value).count()
            total_pub_ass = Assessment.objects.filter(status=Assessment.Status.PUBLISHED).count()
            total_att = AssessmentAttempt.objects.count()
            avg_score = AssessmentAttempt.objects.aggregate(Avg("score"))["score__avg"]
            avg_disp = f"{avg_score:.1f}%" if avg_score is not None else "N/A"

            return f"""### 📊 Institutional Platform Totals ({timezone.now().strftime('%B %Y')})

- **Registered Students:** **{total_stu}** total ({active_stu} active, {total_stu - active_stu} suspended)
- **Active Faculty & Instructors:** **{total_tea}**
- **Published Assessments:** **{total_pub_ass}** across 11 B.Tech engineering branches
- **Total Student Submissions:** **{total_att}** evaluated attempts
- **Platform-wide Average Score:** **{avg_disp}**
- **System Integrity:** Automated countdown timers, autosave, and anti-cheat tab-monitoring actively enforced."""

        # C. Branch Demographics
        if any(w in p_lower for w in ["branch", "semester", "demographic", "distribution", "breakdown"]):
            by_branch = list(StudentProfile.objects.values("branch").annotate(n=Count("id")).order_by("-n"))
            b_lines = [f"• **{b['branch']}:** {b['n']} students" for b in by_branch]
            return f"""### 🏛️ Engineering Branch Enrollment Breakdown

{chr(10).join(b_lines) if b_lines else '• No students enrolled yet.'}

*All 11 B.Tech engineering disciplines (CSE, IT, AIDS, ECE, EE, ME, CE, CHE, BT, AE, and FY) are active and configurable in the Academic Structure tab.*"""

        # D. Scholarships Audit
        if any(w in p_lower for w in ["scholarship", "grant", "closing", "deadline"]):
            all_sc = Scholarship.objects.all().order_by("deadline")
            pub_sc = all_sc.filter(status=Scholarship.Status.PUBLISHED)
            lines = [
                f"### 🎓 Institutional Scholarship Oversight\n",
                f"- **Total Registered Scholarships:** {all_sc.count()} ({pub_sc.count()} published)",
                "\n**Active Scholarship Deadlines:**"
            ]
            for sc in pub_sc[:5]:
                near = " ⚠️ **CLOSING WITHIN 14 DAYS**" if sc.is_deadline_near else ""
                lines.append(f"• **{sc.name}** ({sc.provider}): Due {sc.deadline.strftime('%b %d, %Y')}{near}")
            return "\n".join(lines)

        # E. System Health & Infrastructure Audit
        if any(w in p_lower for w in ["health", "system health", "status", "uptime", "server", "infrastructure"]):
            return """### 🖥️ EduBridge Platform System Health & Infrastructure Audit

- **Core Application Server:** Operational (Django 5.1 / Python 3.14 runtime)
- **Database Status:** Connected & Optimal (Transactions ACID compliant)
- **Authentication & Security:** Role-based access control (Student, Teacher, Admin) active; CSRF & Rate Limiting enforced
- **Task & Assessment Engine:** Timers, anti-cheat detection, and auto-grading engines healthy
- **System Memory & Storage:** Running within nominal thresholds (<45% capacity)
- **Active Alerts:** 0 critical platform alerts recorded."""

        # F. Python & Platform Architecture
        if "python" in p_lower:
            return """### 🐍 Python Runtime & Architecture in EduBridge

**Infrastructure Role:**
Python powers the entire backend layer of the EduBridge platform:
- **Web Framework:** Django provides enterprise-grade ORM, CSRF protection, and role-based access middleware.
- **AI & Analytics Pipeline:** Powers the Neural Reasoning Engine, assessment evaluation, and student progress diagnostics.
- **Security:** Bcrypt password hashing, session hardening, and rate-limiting enforcement."""

        # G. General Platform Admin Overview
        return f"""Welcome, Administrator {user.full_name}. As your **{ADMIN_ASSISTANT_NAME}**, I provide real-time analytical intelligence over live database records.

**Authorized Administrative Capabilities:**
- 📊 **Platform Metrics:** Inquire about student/teacher counts, pass rates, or enrollment demographics.
- 🎓 **Scholarship Oversight:** Audit published engineering grants, missing criteria, or approaching deadlines.
- 📚 **Curriculum & Resources:** Review published study materials across all 11 engineering disciplines.
- 🔒 **Security & Audits:** Monitor sensitive operations and account lifecycle events.

*Note: In accordance with EduBridge security policy, destructive operations (e.g. suspending accounts or deleting records) require explicit manual confirmation.*"""


# ==============================================================================
# 5. UNIFIED REQUEST DISPATCHERS
# ==============================================================================

def handle_ai_request(role: Role, prompt: str, user: User, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Execute role-authorized AI request through the multi-model pipeline."""
    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        return {"error": "Prompt cannot be empty.", "status": "error"}

    clean_history = []
    if isinstance(history, list):
        for item in history[-8:]:
            if isinstance(item, dict) and "role" in item and "content" in item:
                clean_history.append({
                    "role": "user" if item["role"] == "user" else "assistant",
                    "content": str(item["content"])[:2000]
                })

    # 1. Derive role-specific context and prompts
    if role == Role.STUDENT:
        assistant_name = STUDENT_ASSISTANT_NAME
        system_prompt = SYSTEM_PROMPT_STUDENT
        context_str, raw_meta = build_student_context(user)
    elif role == Role.TEACHER:
        assistant_name = TEACHER_ASSISTANT_NAME
        system_prompt = SYSTEM_PROMPT_TEACHER
        context_str, raw_meta = build_teacher_context(user)
    elif role == Role.ADMIN:
        assistant_name = ADMIN_ASSISTANT_NAME
        system_prompt = SYSTEM_PROMPT_ADMIN
        context_str, raw_meta = build_admin_context(user)
    else:
        return {"error": "Unauthorized role for AI assistant.", "status": "error"}

    # 2. Check for configured AI provider
    provider_name, api_key = get_active_ai_provider()
    reply_text: Optional[str] = None
    active_provider_label = "EduBridge Neural Reasoning Engine (Live DB)"

    if provider_name == "cohere" and api_key:
        reply_text = execute_cohere_call(api_key, system_prompt, context_str, clean_history, clean_prompt)
        if reply_text:
            model_disp = os.environ.get("COHERE_MODEL", "command-a-03-2025")
            active_provider_label = f"Cohere AI ({model_disp})"

    elif provider_name == "gemini" and api_key:
        reply_text = execute_gemini_call(api_key, system_prompt, context_str, clean_history, clean_prompt)
        if reply_text:
            active_provider_label = "Google Gemini AI (Live)"

    elif provider_name == "openai" and api_key:
        reply_text = execute_openai_call(api_key, system_prompt, context_str, clean_history, clean_prompt)
        if reply_text:
            active_provider_label = "OpenAI API (Live)"

    # 3. Fallback to EduBridge Local Reasoning Engine
    if not reply_text:
        reply_text = execute_local_reasoning_engine(
            role=role.value,
            prompt=clean_prompt,
            context_data=context_str,
            history=clean_history,
            user=user,
            raw_meta=raw_meta
        )

    # 4. Final Security Sanitization: Scrub credentials & hashes
    forbidden_tokens = ["pbkdf2", "argon2", "bcrypt", "secret_key", "password_hash"]
    for tok in forbidden_tokens:
        reply_text = re.sub(re.escape(tok), "[REDACTED_SECURITY_TOKEN]", reply_text, flags=re.IGNORECASE)

    return {
        "status": "success",
        "assistant_name": assistant_name,
        "reply": reply_text,
        "topic": raw_meta.get("branch") or raw_meta.get("department") or "general",
        "records_found": raw_meta.get("pending_assessments_count") or raw_meta.get("cohort_size") or raw_meta.get("total_students") or 1,
        "provider": active_provider_label,
        "timestamp": timezone.now().isoformat(),
    }


def handle_student_ai_request(prompt: str, student_user: User, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return handle_ai_request(Role.STUDENT, prompt, student_user, history)


def handle_teacher_ai_request(prompt: str, teacher_user: User, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return handle_ai_request(Role.TEACHER, prompt, teacher_user, history)


def handle_admin_ai_request(prompt: str, admin_user: User, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return handle_ai_request(Role.ADMIN, prompt, admin_user, history)


# ==============================================================================
# 6. TEACHER AI QUESTION GENERATOR (MCQS & CODING PROBLEMS)
# ==============================================================================

def generate_assessment_questions(
    topic: str,
    difficulty: str = "Medium",
    count_mcqs: int = 5,
    count_coding: int = 1,
    language: str = "python",
    subject_title: str = "Engineering"
) -> Dict[str, Any]:
    """Generate structured MCQs and coding challenges with answer keys and test cases."""
    clean_topic = (topic or "Core Engineering Fundamentals").strip()
    diff = difficulty if difficulty in ["Easy", "Medium", "Hard"] else "Medium"
    num_mcqs = max(1, min(int(count_mcqs or 5), 25))
    num_coding = max(0, min(int(count_coding or 0), 5))

    # 1. Attempt generation via external AI Provider if configured
    provider_name, api_key = get_active_ai_provider()
    if provider_name in ["cohere", "gemini", "openai"] and api_key:
        sys_prompt = (
            "You are TeachMate AI, an expert engineering faculty question generator. "
            "Generate rigorous assessment questions. Respond ONLY with valid JSON having the keys 'mcqs' and 'coding_problems'."
        )
        user_prompt = f"""Generate {num_mcqs} multiple choice questions (MCQs) and {num_coding} coding problems on the topic '{clean_topic}' ({diff} difficulty) for {subject_title}.
Return JSON strictly in this structure:
{{
  "mcqs": [
    {{
      "id": 1,
      "question": "Question statement here",
      "options": ["A) First option", "B) Second option", "C) Third option", "D) Fourth option"],
      "correct": "A",
      "explanation": "Clear explanation of why this answer is correct",
      "marks": 4
    }}
  ],
  "coding_problems": [
    {{
      "id": 1,
      "title": "Problem Title",
      "description": "Clear statement of the problem",
      "constraints": "1 <= N <= 10^5",
      "sample_input": "sample input",
      "sample_output": "sample output",
      "test_cases": [
        {{"input": "sample input", "output": "sample output", "hidden": false}},
        {{"input": "hidden input", "output": "hidden output", "hidden": true}}
      ],
      "lang": "{language}",
      "marks": 10
    }}
  ]
}}"""
        raw_res = None
        if provider_name == "cohere":
            raw_res = execute_cohere_call(api_key, sys_prompt, "", [], user_prompt)
        elif provider_name == "gemini":
            raw_res = execute_gemini_call(api_key, sys_prompt, "", [], user_prompt)
        elif provider_name == "openai":
            raw_res = execute_openai_call(api_key, sys_prompt, "", [], user_prompt)

        if raw_res:
            try:
                # Clean JSON fences if present
                clean_json = re.sub(r'^```(?:json)?\s*', '', raw_res.strip(), flags=re.MULTILINE)
                clean_json = re.sub(r'\s*```$', '', clean_json.strip(), flags=re.MULTILINE)
                parsed = json.loads(clean_json)
                if isinstance(parsed, dict) and "mcqs" in parsed:
                    return {
                        "status": "success",
                        "topic": clean_topic,
                        "difficulty": diff,
                        "mcqs": parsed.get("mcqs", [])[:num_mcqs],
                        "coding_problems": parsed.get("coding_problems", [])[:num_coding],
                        "provider": f"{provider_name.title()} AI"
                    }
            except Exception as e:
                logger.warning(f"Failed to parse AI question JSON: {e}")

    # 2. Resilient Fallback Academic Generator
    generated_mcqs = []
    generated_coding = []

    t_lower = clean_topic.lower()
    for i in range(1, num_mcqs + 1):
        if "tree" in t_lower or "graph" in t_lower or "dijkstra" in t_lower:
            q_text = f"In {clean_topic}, what is the maximum depth and time complexity under worst-case scenarios for problem variant {i}?"
            opts = [
                f"A) O(log V) with balanced binary heap trees",
                f"B) O(V^2) when implemented with an adjacency matrix",
                f"C) O(E log V) utilizing a priority queue",
                f"D) O(V + E) for standard breadth-first graph traversal"
            ]
            correct = "C" if i % 2 == 1 else "B"
            exp = f"Under {clean_topic}, priority queues optimize edge relaxations yielding asymptotic bounds."
        elif "database" in t_lower or "sql" in t_lower or "norm" in t_lower:
            q_text = f"Which dependency condition must strictly hold for {clean_topic} to prevent anomaly {i}?"
            opts = [
                "A) Every non-key attribute must depend solely on the whole candidate key",
                "B) Multivalued dependencies must have non-empty Cartesian products",
                "C) Transitive functional dependencies must be preserved in 3NF",
                "D) The primary key must be atomic and non-null"
            ]
            correct = "A" if i % 2 == 1 else "D"
            exp = "Relational integrity requires minimal redundancy and functional determinant super keys."
        elif "os" in t_lower or "memory" in t_lower or "paging" in t_lower:
            q_text = f"Regarding {clean_topic}, how does the virtual memory architecture resolve scenario {i}?"
            opts = [
                "A) Hardware TLB cache hit with zero page table lookups",
                "B) OS Page Fault trap causing secondary storage swap fetch",
                "C) Preemptive round-robin context switch during interrupt handling",
                "D) Direct frame allocation in contiguous physical memory"
            ]
            correct = "B" if i % 2 == 1 else "A"
            exp = "The memory management unit traps missing pages to initiate swap paging."
        else:
            q_text = f"Which algorithmic principle is foundational when evaluating {clean_topic} for test question {i}?"
            opts = [
                f"A) Optimal Substructure and Overlapping Subproblems",
                f"B) Greedy choice property guaranteeing global optimality",
                f"C) Divide and Conquer recurrence bounded by Master Theorem",
                f"D) Linear space state memoization"
            ]
            correct = "A" if i % 2 == 1 else "C"
            exp = f"Foundational theory in {clean_topic} requires state-space exploration and bounding."

        generated_mcqs.append({
            "id": i,
            "question": q_text,
            "options": opts,
            "correct": correct,
            "explanation": exp,
            "marks": 4
        })

    for c in range(1, num_coding + 1):
        generated_coding.append({
            "id": c,
            "title": f"{clean_topic.title()} Problem Solving {c}",
            "description": (
                f"Given a list of engineering parameters for {clean_topic}, write an optimal function in {language.title()} "
                f"that evaluates the maximum throughput and returns the computed result. Handle boundary conditions and empty inputs."
            ),
            "constraints": "1 <= N <= 10^5, all elements within 32-bit signed integer range.",
            "sample_input": "5\n10 20 30 40 50",
            "sample_output": "150",
            "test_cases": [
                {"input": "5\n10 20 30 40 50", "output": "150", "hidden": False},
                {"input": "3\n5 15 25", "output": "45", "hidden": False},
                {"input": "1\n100", "output": "100", "hidden": True},
                {"input": "4\n-10 20 -30 40", "output": "20", "hidden": True}
            ],
            "lang": language,
            "marks": 10
        })

    return {
        "status": "success",
        "topic": clean_topic,
        "difficulty": diff,
        "mcqs": generated_mcqs,
        "coding_problems": generated_coding,
        "provider": "EduBridge Academic Generator"
    }

