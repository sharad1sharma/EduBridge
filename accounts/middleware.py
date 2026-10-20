from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

from . import audit

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
)
# A user who must change a temporary password may only reach these.
PASSWORD_CHANGE_ALLOWED = {"accounts:password_change", "accounts:logout"}


def _wants_json(request) -> bool:
    # Only affects the response *format*; authorization never depends on the path.
    return "/api/" in request.path or request.headers.get("Accept") == "application/json"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.user.is_authenticated or request.path.startswith("/accounts/"):
            add_never_cache_headers(response)  # no stale private pages via back button
            response.headers["Cache-Control"] = "no-store"
        return response


class AccessPolicyMiddleware:
    """Default-deny authorization, evaluated on the server for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        policy = getattr(view_func, "access_policy", None)
        if policy is None:  # a developer forgot to declare access: refuse
            audit.record(request, "authz_denied", reason="view_without_policy", path=request.path[:200])
            return self._forbidden(request)
        if policy.kind == "public":
            return None

        user = request.user
        if not user.is_authenticated:
            if _wants_json(request):
                return JsonResponse({"error": "authentication_required"}, status=401)
            return redirect_to_login(request.get_full_path(), reverse("accounts:login"))

        if user.must_change_password and request.resolver_match.view_name not in PASSWORD_CHANGE_ALLOWED:
            if _wants_json(request):
                return JsonResponse({"error": "password_change_required"}, status=403)
            return redirect("accounts:password_change")

        if policy.kind == "roles" and user.role not in policy.roles:
            audit.record(request, "authz_denied", reason="role_not_allowed",
                         path=request.path[:200], method=request.method)
            return self._forbidden(request)
        return None

    @staticmethod
    def _forbidden(request):
        if _wants_json(request):
            return JsonResponse({"error": "forbidden"}, status=403)
        return render(request, "403.html", status=403)
