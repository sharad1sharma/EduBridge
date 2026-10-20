import secrets
from datetime import timedelta

from django.contrib import messages
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts import audit, services
from accounts.access import public, role_home_url, role_required
from accounts.constants import Branch, Role
from accounts.forms import StudentProfileForm, TeacherCreateForm, TeacherProfileForm
from accounts.models import AuditEvent, StudentProfile, TeacherProfile, User


@public
def home(request):
    if request.user.is_authenticated:
        return redirect(role_home_url(request.user))
    return render(request, "home.html")


# --------------------------------------------------------------------------- student
# Every student view reads request.user's own records. No view accepts a student ID or
# user ID from the URL, so there is no way to ask for someone else's data.

@role_required(Role.STUDENT)
def student_dashboard(request):
    profile = request.user.student_profile
    percent, missing = profile.completion()
    return render(request, "dashboards/student_dashboard.html",
                  {"profile": profile, "percent": percent, "missing": missing})


@role_required(Role.STUDENT)
def student_profile(request):
    profile = request.user.student_profile
    form = StudentProfileForm(request.POST or None, instance=profile, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.record(request, "profile_updated")
        messages.success(request, "Profile saved.")
        return redirect("student_profile")
    percent, missing = profile.completion()
    return render(request, "dashboards/profile.html",
                  {"form": form, "percent": percent, "missing": missing, "heading": "Your profile"})


# --------------------------------------------------------------------------- teacher

@role_required(Role.TEACHER)
def teacher_dashboard(request):
    profile = request.user.teacher_profile
    percent, missing = profile.completion()
    return render(request, "dashboards/teacher_dashboard.html",
                  {"profile": profile, "percent": percent, "missing": missing})


@role_required(Role.TEACHER)
def teacher_profile(request):
    profile = request.user.teacher_profile
    form = TeacherProfileForm(request.POST or None, instance=profile, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.record(request, "profile_updated")
        messages.success(request, "Profile saved.")
        return redirect("teacher_profile")
    percent, missing = profile.completion()
    return render(request, "dashboards/profile.html",
                  {"form": form, "percent": percent, "missing": missing, "heading": "Your profile"})


# --------------------------------------------------------------------------- admin

def branch_counts():
    raw = dict(StudentProfile.objects.values_list("branch").annotate(n=Count("id")))
    return [{"code": code, "label": label, "count": raw.get(code, 0)} for code, label in Branch.choices]


@role_required(Role.ADMIN)
def admin_dashboard(request):
    now = timezone.now()
    students = User.objects.filter(role=Role.STUDENT.value)
    teachers = User.objects.filter(role=Role.TEACHER.value)
    branches = branch_counts()
    context = {
        "stats": {
            "students": students.count(),
            "teachers": teachers.count(),
            "suspended": User.objects.filter(is_active=False).count(),
            "new_students_7d": students.filter(date_joined__gte=now - timedelta(days=7)).count(),
        },
        "branches": branches,
        "max_branch": max((b["count"] for b in branches), default=0) or 1,
        "recent_events": AuditEvent.objects.all()[:8],
    }
    return render(request, "dashboards/admin_dashboard.html", context)


@role_required(Role.ADMIN)
def admin_users(request):
    qs = User.objects.exclude(role=Role.ADMIN.value).order_by("public_id")
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(username__icontains=q.lower())
                       | Q(email__icontains=q.lower()) | Q(public_id__iexact=q))
    if role in (Role.STUDENT.value, Role.TEACHER.value):
        qs = qs.filter(role=role)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "suspended":
        qs = qs.filter(is_active=False)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    params = {k: v for k, v in {"q": q, "role": role, "status": status}.items() if v}
    return render(request, "dashboards/admin_users.html",
                  {"page": page, "q": q, "role": role, "status": status,
                   "query": urlencode(params) + "&" if params else ""})


@role_required(Role.ADMIN)
def admin_teacher_new(request):
    form = TeacherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        temp_password = secrets.token_urlsafe(12)
        teacher = services.create_user(
            role=Role.TEACHER, username=data["username"], email=data["email"],
            full_name=data["full_name"], password=temp_password, must_change_password=True,
            profile={"department": data["department"], "designation": data["designation"]},
        )
        audit.record(request, "teacher_account_created", target=teacher, teacher_id=teacher.public_id)
        # Shown once, never stored in plain text or logged.
        return render(request, "dashboards/admin_teacher_created.html",
                      {"teacher": teacher, "temp_password": temp_password})
    return render(request, "dashboards/admin_teacher_form.html", {"form": form})


@role_required(Role.ADMIN)
@require_POST
def admin_user_status(request, pk):
    # Administrators are excluded from the queryset: this page cannot touch admin accounts.
    target = get_object_or_404(User, pk=pk, role__in=[Role.STUDENT.value, Role.TEACHER.value])
    action = request.POST.get("action")
    if action == "suspend":
        target.is_active = False
        event = "account_suspended"
    elif action == "reactivate":
        target.is_active = True
        event = "account_reactivated"
    else:
        messages.error(request, "Unknown action.")
        return redirect("admin_users")
    target.save(update_fields=["is_active"])
    audit.record(request, event, target=target, account=target.public_id,
                 reason=request.POST.get("reason", "").strip()[:200])
    messages.success(request, f"{target.public_id} {'suspended' if not target.is_active else 'reactivated'}.")
    return redirect("admin_users")


@role_required(Role.ADMIN)
def admin_audit(request):
    qs = AuditEvent.objects.select_related("actor")
    action = request.GET.get("action", "").strip()
    if action:
        qs = qs.filter(action=action)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    actions = AuditEvent.objects.order_by().values_list("action", flat=True).distinct()
    return render(request, "dashboards/admin_audit.html",
                  {"page": page, "action": action, "actions": sorted(actions),
                   "query": urlencode({"action": action}) + "&" if action else ""})
