"""EduBridge Student AI Assistant.

Role-isolated neural analytical query processor for authenticated B.Tech students.
Provides personal assessment tracking, study roadmaps, live meeting schedules,
subject resources, and published scholarship guidance.

Strict Security Boundaries:
- Accesses ONLY the authenticated student's private records and public/published resources.
- Forbidden from accessing teacher analytics, admin consoles, passwords, tokens, or other students' data.
- Read-only: cannot modify records, forge marks, or bypass submissions.
"""
from dashboards.ai_service import handle_student_ai_request, STUDENT_ASSISTANT_NAME


def process_student_ai_query(prompt: str, student_user, history=None) -> dict:
    """Process natural language query via the EduBridge Student AI Assistant."""
    return handle_student_ai_request(prompt=prompt, student_user=student_user, history=history)
