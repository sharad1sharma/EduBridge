"""EduBridge Teacher AI Assistant.

Role-isolated analytical engine for faculty instructors and professors.
Provides student performance diagnostics, submission tracking, topic weakness
identification, test score summarization, and meeting schedule oversight.

Strict Security Boundaries:
- Accesses ONLY academic records and students within the teacher's authorized courses/branches.
- Forbidden from accessing administrator settings, raw credentials, audit logs, or scholarship administration.
"""
from dashboards.ai_service import handle_teacher_ai_request, TEACHER_ASSISTANT_NAME


def process_teacher_ai_query(prompt: str, teacher_user, history=None) -> dict:
    """Process pedagogical and analytical query via the EduBridge Teacher AI Assistant."""
    return handle_teacher_ai_request(prompt=prompt, teacher_user=teacher_user, history=history)
