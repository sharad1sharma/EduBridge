"""EduBridge Admin AI Assistant.

Provides authorized, real database analysis for administrators only.
Answers student demographics, teacher workloads, combined platform analytics, and scholarship oversight.
Strictly adheres to safety rules: retrieves actual DB counts, never leaks secrets/passwords,
validates server-side permissions, and handles missing/empty data gracefully.
"""
from dashboards.ai_service import handle_admin_ai_request, ADMIN_ASSISTANT_NAME


def process_admin_ai_query(prompt: str, user, history=None) -> dict:
    """Analyze the prompt and query real database models via the EduBridge Admin AI Assistant."""
    return handle_admin_ai_request(prompt=prompt, admin_user=user, history=history)
