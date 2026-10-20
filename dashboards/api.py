"""Small JSON API. Each endpoint declares its role; the middleware enforces it before the
view runs, so a student calling /api/admin/... gets 403 no matter how the request is made."""
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_safe

from accounts.access import authenticated, role_required
from accounts.constants import Role
from accounts.models import User


@authenticated
@require_safe
def me(request):
    u = request.user
    return JsonResponse({"public_id": u.public_id, "role": u.role, "full_name": u.full_name})


@role_required(Role.STUDENT)
@require_safe
def student_profile(request):
    u, p = request.user, request.user.student_profile
    percent, _ = p.completion()
    return JsonResponse({
        "student_id": u.public_id, "full_name": u.full_name, "email": u.email,
        "branch": p.branch, "semester": p.semester, "profile_completion": percent,
    })


@role_required(Role.TEACHER)
@require_safe
def teacher_profile(request):
    u, p = request.user, request.user.teacher_profile
    percent, _ = p.completion()
    return JsonResponse({
        "teacher_id": u.public_id, "full_name": u.full_name, "email": u.email,
        "department": p.department, "designation": p.designation, "profile_completion": percent,
    })


@role_required(Role.ADMIN)
@require_safe
def admin_stats(request):
    by_role = dict(User.objects.values_list("role").annotate(n=Count("id")))
    return JsonResponse({
        "students": by_role.get(Role.STUDENT.value, 0),
        "teachers": by_role.get(Role.TEACHER.value, 0),
        "suspended": User.objects.filter(is_active=False).count(),
    })


@role_required(Role.ADMIN)
@require_safe
def admin_users(request):
    try:
        limit = max(1, min(int(request.GET.get("limit", 100)), 200))
    except ValueError:
        limit = 100
    rows = (User.objects.exclude(role=Role.ADMIN.value).order_by("public_id")
            .values("public_id", "full_name", "role", "is_active")[:limit])
    return JsonResponse({"users": list(rows)})


@authenticated
def notifications_list(request):
    """Retrieve unread count and latest notifications for authenticated user."""
    from dashboards.notifications import get_user_notifications_payload
    data = get_user_notifications_payload(request.user)
    return JsonResponse(data)


@authenticated
def notification_mark_read(request, pk):
    """Mark a specific notification as read."""
    from dashboards.models import PlatformNotification
    notif = PlatformNotification.objects.filter(pk=pk, recipient=request.user).first()
    if not notif:
        return JsonResponse({"error": "Notification not found or unauthorized."}, status=404)
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return JsonResponse({"status": "success", "id": pk})


@authenticated
def notification_mark_all_read(request):
    """Mark all unread notifications as read for current user."""
    from dashboards.models import PlatformNotification
    updated = PlatformNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"status": "success", "marked_count": updated})


@authenticated
def unified_ai_chat_api(request):
    """Secure server-side chat endpoint (POST /api/ai/chat/) enforcing role-based permissions and Cohere AI integration."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed. Use POST.", "status": "error"}, status=405)

    import json
    from accounts import audit
    from dashboards.ai_service import handle_ai_request

    try:
        body = json.loads(request.body.decode("utf-8"))
        prompt = (body.get("prompt") or body.get("message") or "").strip()
        history = body.get("history", [])
    except Exception:
        prompt = (request.POST.get("prompt") or request.POST.get("message") or "").strip()
        history = []

    if not prompt:
        return JsonResponse({"error": "Prompt cannot be empty.", "status": "error"}, status=400)

    # Request size guardrail (max 4000 characters)
    if len(prompt) > 4000:
        return JsonResponse({"error": "Prompt exceeds maximum allowed length of 4000 characters.", "status": "error"}, status=400)

    role_val = request.user.role
    try:
        role_enum = Role(role_val)
    except ValueError:
        return JsonResponse({"error": "Invalid user role.", "status": "error"}, status=403)

    result = handle_ai_request(role=role_enum, prompt=prompt, user=request.user, history=history)
    audit.record(request, f"{role_val}_ai_query_executed", prompt_sample=prompt[:80], topic=result.get("topic"))

    return JsonResponse(result)


