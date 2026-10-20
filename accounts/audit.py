from .models import AuditEvent

# Keys that must never appear in audit detail.
_FORBIDDEN_KEYS = {"password", "new_password", "old_password", "token", "secret", "session"}


def client_ip(request):
    """Remote address as seen by the server. X-Forwarded-For is deliberately NOT trusted
    here (it is client-controlled unless a trusted proxy overwrites it)."""
    return request.META.get("REMOTE_ADDR") or None


def record(request, action, *, actor=None, target=None, **detail):
    if _FORBIDDEN_KEYS & {key.lower() for key in detail}:
        raise ValueError("Audit detail must not contain credentials.")
    if actor is None and request is not None and getattr(request, "user", None) is not None:
        if request.user.is_authenticated:
            actor = request.user
    return AuditEvent.objects.create(
        actor=actor,
        actor_label=(str(actor) if actor else "")[:80],
        action=action,
        target_type=type(target).__name__ if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        ip_address=client_ip(request) if request is not None else None,
        detail=detail,
    )
