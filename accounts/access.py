"""Declarative, default-deny access policies for views.

Every view must carry exactly one of these decorators. `AccessPolicyMiddleware`
(accounts/middleware.py) reads the policy before the view runs and refuses any view that
has none. Authorization therefore never depends on the UI, on URLs, or on anything the
browser stores — only on the server-side user record.

Usage (the decorator returns the same function, so it composes with others):

    @role_required(Role.TEACHER)
    def teacher_dashboard(request): ...
"""
from dataclasses import dataclass

from django.urls import reverse

from .constants import Role


@dataclass(frozen=True)
class Policy:
    kind: str  # "public" | "authenticated" | "roles"
    roles: frozenset = frozenset()


def _value(role):
    return str(getattr(role, "value", role))


def public(view):
    view.access_policy = Policy("public")
    return view


def authenticated(view):
    """Any signed-in, active user (all roles)."""
    view.access_policy = Policy("authenticated")
    return view


def role_required(*allowed):
    roles = frozenset(_value(r) for r in allowed)

    def decorator(view):
        view.access_policy = Policy("roles", roles)
        return view

    return decorator


def policy_allows(view_func, user) -> bool:
    policy = getattr(view_func, "access_policy", None)
    if policy is None:
        return False
    if policy.kind == "public":
        return True
    if not user.is_authenticated:
        return False
    if policy.kind == "authenticated":
        return True
    return user.role in policy.roles


HOME_URL_NAMES = {
    Role.STUDENT.value: "student_dashboard",
    Role.TEACHER.value: "teacher_dashboard",
    Role.ADMIN.value: "admin_dashboard",
}


def role_home_url(user) -> str:
    return reverse(HOME_URL_NAMES[user.role])
