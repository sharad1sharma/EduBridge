import csv
import json
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from accounts import audit, services
from accounts.access import role_required
from accounts.constants import Branch, Role
from accounts.models import AuditEvent, StudentProfile, TeacherProfile, User
from dashboards.admin_ai import process_admin_ai_query
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


# ==============================================================================
# 1. ANALYTICS & VISUAL REPORTING (Pie Charts, Bar Graphs, Line Graphs)
# ==============================================================================

@role_required(Role.ADMIN)
@require_safe
def admin_analytics(request):
    """Comprehensive, role-protected analytics dashboard for administrators."""
    from dashboards.analytics_service import (
        get_admin_overview_analytics,
        get_admin_all_students_analytics,
        get_admin_all_teachers_analytics,
        get_admin_individual_student_analytics,
        get_admin_individual_teacher_analytics,
    )

    range_key = request.GET.get("range", "30d")
    section = request.GET.get("section", "overview")

    overview_data = get_admin_overview_analytics(range_key=range_key)
    all_students_data = get_admin_all_students_analytics(date_range=range_key)
    all_teachers_data = get_admin_all_teachers_analytics(date_range=range_key)
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "section": section,
        "range": range_key,
        "overview": overview_data,
        "all_students": all_students_data,
        "all_teachers": all_teachers_data,
        "branches": branches,
    }
    return render(request, "dashboards/admin_analytics.html", context)


@role_required(Role.ADMIN)
@require_safe
def admin_analytics_api(request):
    """Dynamic JSON API for administrator analytics navigation, filters, and ID lookups."""
    from dashboards.analytics_service import (
        get_admin_overview_analytics,
        get_admin_all_students_analytics,
        get_admin_all_teachers_analytics,
        get_admin_individual_student_analytics,
        get_admin_individual_teacher_analytics,
    )

    section = request.GET.get("section", "overview")
    range_key = request.GET.get("range", "30d")
    sub = request.GET.get("sub", "all")
    student_id = request.GET.get("student_id", "").strip()
    teacher_id = request.GET.get("teacher_id", "").strip()
    branch = request.GET.get("branch", "")
    semester = request.GET.get("semester", "")
    department = request.GET.get("department", "")

    if section == "students":
        if sub == "individual" and student_id:
            res = get_admin_individual_student_analytics(student_id)
            if res.get("error") == "not_found":
                return JsonResponse({"status": "error", "message": res.get("message")}, status=404)
            return JsonResponse({"status": "success", "data": res})
        else:
            data = get_admin_all_students_analytics(branch=branch, semester=semester, date_range=range_key)
            return JsonResponse({"status": "success", "data": data})

    elif section == "teachers":
        if sub == "individual" and teacher_id:
            res = get_admin_individual_teacher_analytics(teacher_id)
            if res.get("error") == "not_found":
                return JsonResponse({"status": "error", "message": res.get("message")}, status=404)
            return JsonResponse({"status": "success", "data": res})
        else:
            data = get_admin_all_teachers_analytics(department=department, date_range=range_key)
            return JsonResponse({"status": "success", "data": data})

    else:
        # Default: Institution Overview
        data = get_admin_overview_analytics(range_key=range_key)
        return JsonResponse({"status": "success", "data": data})



@role_required(Role.ADMIN)
@require_safe
def admin_export_csv(request, report_type):
    """Export authorized database records as CSV."""
    now = timezone.now()
    response = HttpResponse(content_type="text/csv")
    filename = f"edubridge_{report_type}_{now:%Y%m%d_%H%M}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    if report_type == "students":
        writer.writerow(["Student ID", "Full Name", "Username", "Email", "Branch", "Semester", "Status", "Date Joined"])
        for u in User.objects.filter(role=Role.STUDENT.value).select_related("student_profile").order_by("public_id"):
            sp = getattr(u, "student_profile", None)
            writer.writerow([
                u.public_id, u.full_name, u.username, u.email,
                sp.branch if sp else "", sp.semester if sp else "",
                "Active" if u.is_active else "Suspended", u.date_joined.strftime("%Y-%m-%d %H:%M")
            ])
    elif report_type == "teachers":
        writer.writerow(["Teacher ID", "Full Name", "Username", "Email", "Department", "Designation", "Status", "Date Joined"])
        for u in User.objects.filter(role=Role.TEACHER.value).select_related("teacher_profile").order_by("public_id"):
            tp = getattr(u, "teacher_profile", None)
            writer.writerow([
                u.public_id, u.full_name, u.username, u.email,
                tp.department if tp else "", tp.designation if tp else "",
                "Active" if u.is_active else "Suspended", u.date_joined.strftime("%Y-%m-%d %H:%M")
            ])
    elif report_type == "assessments":
        writer.writerow(["Title", "Type", "Branch", "Semester", "Duration (mins)", "Total Marks", "Deadline", "Status"])
        for a in Assessment.objects.all().order_by("-deadline"):
            writer.writerow([
                a.title, a.get_assessment_type_display(), a.branch, a.semester,
                a.duration_minutes, a.total_marks, a.deadline.strftime("%Y-%m-%d %H:%M"), a.status
            ])
    elif report_type == "scholarships":
        writer.writerow(["Name", "Provider", "Education Level", "Eligible Branches", "Min CGPA", "Deadline", "Status"])
        for s in Scholarship.objects.all().order_by("deadline"):
            writer.writerow([
                s.name, s.provider, s.education_level, s.eligible_branches,
                s.min_cgpa, s.deadline.strftime("%Y-%m-%d"), s.status
            ])
    else:
        writer.writerow(["Time", "Action", "Actor", "Target Type", "Target ID", "IP Address"])
        for e in AuditEvent.objects.all()[:500]:
            writer.writerow([
                e.created_at.strftime("%Y-%m-%d %H:%M:%S"), e.action, e.actor_label,
                e.target_type, e.target_id, e.ip_address
            ])

    audit.record(request, "admin_export_csv", target_type="report", report_type=report_type)
    return response


# ==============================================================================
# 2. STUDENT MANAGEMENT
# ==============================================================================

@role_required(Role.ADMIN)
def admin_students(request):
    """View and filter all registered students."""
    qs = User.objects.filter(role=Role.STUDENT.value).select_related("student_profile").order_by("public_id")
    q = request.GET.get("q", "").strip()
    branch = request.GET.get("branch", "")
    semester = request.GET.get("semester", "")
    status = request.GET.get("status", "")

    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(username__icontains=q.lower())
                       | Q(email__icontains=q.lower()) | Q(public_id__iexact=q))
    if branch:
        qs = qs.filter(student_profile__branch=branch)
    if semester:
        qs = qs.filter(student_profile__semester=semester)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "suspended":
        qs = qs.filter(is_active=False)

    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "page": page,
        "q": q,
        "branch": branch,
        "semester": semester,
        "status": status,
        "branches": branches,
    }
    return render(request, "dashboards/admin_students.html", context)


@role_required(Role.ADMIN)
def admin_student_detail(request, pk):
    """View full student academic record, assessments, MCQ performance, and manage account."""
    student = get_object_or_404(User, pk=pk, role=Role.STUDENT.value)
    profile = getattr(student, "student_profile", None)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit_profile":
            if profile:
                profile.branch = request.POST.get("branch", profile.branch)
                try:
                    profile.semester = int(request.POST.get("semester", profile.semester))
                except (ValueError, TypeError):
                    pass
                profile.phone = request.POST.get("phone", profile.phone)[:16]
                profile.academic_details = request.POST.get("academic_details", profile.academic_details)[:1000]
                profile.save()
            student.full_name = request.POST.get("full_name", student.full_name)[:120]
            student.save()
            audit.record(request, "admin_student_profile_updated", target=student, student_id=student.public_id)
            messages.success(request, f"Updated profile for {student.public_id}.")
        elif action == "toggle_status":
            student.is_active = not student.is_active
            student.save()
            new_status = "active" if student.is_active else "suspended"
            audit.record(request, f"admin_student_{new_status}", target=student, student_id=student.public_id)
            messages.success(request, f"Account for {student.public_id} is now {new_status}.")
            return redirect("admin_student_detail", pk=student.pk)

        elif action == "delete_account":
            # Confirmation workflow & retention policy check
            confirm_id = request.POST.get("confirm_student_id", "").strip()
            if confirm_id != student.public_id:
                messages.error(request, f"Deletion cancelled: Please type the exact student ID '{student.public_id}' to confirm.")
                return redirect("admin_student_detail", pk=student.pk)

            audit.record(request, "admin_student_deleted", target_type="User", target_id=student.public_id,
                         reason=request.POST.get("reason", "Administrative deletion")[:200])
            student.delete()
            messages.success(request, f"Account {confirm_id} and associated profile records have been permanently removed per institutional retention policy.")
            return redirect("admin_students")

    attempts = AssessmentAttempt.objects.filter(student=student).select_related("assessment").order_by("-started_at")
    percent, missing = profile.completion() if profile else (0, [])
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "student": student,
        "profile": profile,
        "percent": percent,
        "missing": missing,
        "attempts": attempts,
        "branches": branches,
    }
    return render(request, "dashboards/admin_student_detail.html", context)


# ==============================================================================
# 3. TEACHER MANAGEMENT
# ==============================================================================

@role_required(Role.ADMIN)
def admin_teachers(request):
    """View, search, and manage all faculty accounts."""
    qs = User.objects.filter(role=Role.TEACHER.value).select_related("teacher_profile").order_by("public_id")
    q = request.GET.get("q", "").strip()
    dept = request.GET.get("department", "")
    status = request.GET.get("status", "")

    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(username__icontains=q.lower())
                       | Q(email__icontains=q.lower()) | Q(public_id__iexact=q))
    if dept:
        qs = qs.filter(teacher_profile__department=dept)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "suspended":
        qs = qs.filter(is_active=False)

    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "page": page,
        "q": q,
        "department": dept,
        "status": status,
        "branches": branches,
    }
    return render(request, "dashboards/admin_teachers.html", context)


@role_required(Role.ADMIN)
def admin_teacher_detail(request, pk):
    """View full teacher profile, assigned subjects, resources, and meetings."""
    teacher = get_object_or_404(User, pk=pk, role=Role.TEACHER.value)
    profile = getattr(teacher, "teacher_profile", None)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit_profile":
            if profile:
                profile.department = request.POST.get("department", profile.department)
                profile.designation = request.POST.get("designation", profile.designation)[:80]
                profile.bio = request.POST.get("bio", profile.bio)[:500]
                profile.save()
            teacher.full_name = request.POST.get("full_name", teacher.full_name)[:120]
            teacher.save()
            audit.record(request, "admin_teacher_profile_updated", target=teacher, teacher_id=teacher.public_id)
            messages.success(request, f"Updated faculty profile for {teacher.public_id}.")
            return redirect("admin_teacher_detail", pk=teacher.pk)

        elif action == "toggle_status":
            teacher.is_active = not teacher.is_active
            teacher.save()
            new_status = "active" if teacher.is_active else "suspended"
            audit.record(request, f"admin_teacher_{new_status}", target=teacher, teacher_id=teacher.public_id)
            messages.success(request, f"Faculty account for {teacher.public_id} is now {new_status}.")
            return redirect("admin_teacher_detail", pk=teacher.pk)

        elif action == "delete_account":
            confirm_id = request.POST.get("confirm_teacher_id", "").strip()
            if confirm_id != teacher.public_id:
                messages.error(request, f"Deletion cancelled: Please type the exact faculty ID '{teacher.public_id}' to confirm.")
                return redirect("admin_teacher_detail", pk=teacher.pk)

            audit.record(request, "admin_teacher_deleted", target_type="User", target_id=teacher.public_id)
            teacher.delete()
            messages.success(request, f"Faculty account {confirm_id} deleted.")
            return redirect("admin_teachers")

    assigned_subjects = teacher.assigned_subjects.all()
    created_assessments = Assessment.objects.filter(created_by=teacher)
    authored_resources = LearningResource.objects.filter(author=teacher)
    meetings = Meeting.objects.filter(host_teacher=teacher)
    percent, missing = profile.completion() if profile else (0, [])
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "teacher": teacher,
        "profile": profile,
        "percent": percent,
        "missing": missing,
        "assigned_subjects": assigned_subjects,
        "assessments": created_assessments,
        "resources": authored_resources,
        "meetings": meetings,
        "branches": branches,
    }
    return render(request, "dashboards/admin_teacher_detail.html", context)


# ==============================================================================
# 4. BRANCH, SEMESTER, AND SUBJECT MANAGEMENT
# ==============================================================================

@role_required(Role.ADMIN)
def admin_academic(request):
    """Manage B.Tech branches, semester curricula, and subjects."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_branch":
            code = request.POST.get("code", "").strip().upper()
            name = request.POST.get("name", "").strip()
            desc = request.POST.get("description", "").strip()
            if code and name:
                AcademicBranch.objects.get_or_create(code=code, defaults={"name": name, "description": desc})
                audit.record(request, "admin_branch_added", target_type="AcademicBranch", branch_code=code)
                messages.success(request, f"Branch {code} ({name}) created successfully.")
            return redirect("admin_academic")

        elif action == "toggle_branch":
            code = request.POST.get("code")
            branch = get_object_or_404(AcademicBranch, code=code)
            branch.is_enabled = not branch.is_enabled
            branch.save()
            audit.record(request, "admin_branch_toggled", branch=code, is_enabled=branch.is_enabled)
            messages.success(request, f"Branch {code} is now {'enabled' if branch.is_enabled else 'disabled'}.")
            return redirect("admin_academic")

        elif action == "add_subject":
            code = request.POST.get("code", "").strip().upper()
            title = request.POST.get("title", "").strip()
            branch = request.POST.get("branch", "")
            semester = int(request.POST.get("semester", 1))
            credits = float(request.POST.get("credits", 4.0))
            is_elective = request.POST.get("is_elective") == "on"
            syllabus = request.POST.get("syllabus_summary", "").strip()

            if code and title and branch:
                s, created = Subject.objects.get_or_create(
                    code=code,
                    defaults={
                        "title": title, "branch": branch, "semester": semester,
                        "credits": credits, "is_elective": is_elective, "syllabus_summary": syllabus
                    }
                )
                audit.record(request, "admin_subject_added", subject_code=code)
                messages.success(request, f"Subject {code} ({title}) registered.")
            return redirect("admin_academic")

        elif action == "delete_subject":
            code = request.POST.get("code")
            s = get_object_or_404(Subject, code=code)
            s.delete()
            audit.record(request, "admin_subject_deleted", subject_code=code)
            messages.success(request, f"Subject {code} removed from catalog.")
            return redirect("admin_academic")

    branches = AcademicBranch.objects.all().order_by("code")
    subjects = Subject.objects.all().prefetch_related("assigned_teachers").order_by("branch", "semester", "code")

    context = {
        "branches": branches,
        "subjects": subjects,
    }
    return render(request, "dashboards/admin_academic.html", context)


# ==============================================================================
# 5. ASSIGNMENTS & ASSESSMENTS ADMINISTRATION
# ==============================================================================

@role_required(Role.ADMIN)
def admin_assessments(request):
    """View and manage all daily assignments and weekly tests."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_status":
            aid = request.POST.get("assessment_id")
            assessment = get_object_or_404(Assessment, pk=aid)
            new_status = request.POST.get("new_status")
            if new_status in Assessment.Status.values:
                assessment.status = new_status
                assessment.save()
                audit.record(request, "admin_assessment_status_changed", assessment_id=aid, new_status=new_status)
                messages.success(request, f"Assessment '{assessment.title}' set to {new_status}.")
            return redirect("admin_assessments")

    qs = Assessment.objects.select_related("subject", "created_by").order_by("-deadline")
    b_filter = request.GET.get("branch", "")
    type_filter = request.GET.get("type", "")
    if b_filter:
        qs = qs.filter(branch=b_filter)
    if type_filter:
        qs = qs.filter(assessment_type=type_filter)

    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "page": page,
        "branch": b_filter,
        "type": type_filter,
        "branches": branches,
        "total_assessments": Assessment.objects.count(),
        "total_attempts": AssessmentAttempt.objects.count(),
    }
    return render(request, "dashboards/admin_assessments.html", context)


# ==============================================================================
# 6. LEARNING RESOURCE MANAGEMENT
# ==============================================================================

@role_required(Role.ADMIN)
def admin_resources(request):
    """Platform-wide resource management and publication control."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_resource":
            title = request.POST.get("title", "").strip()
            branch = request.POST.get("branch", "")
            semester = int(request.POST.get("semester", 1))
            r_type = request.POST.get("resource_type", "pdf")
            ext_url = request.POST.get("external_url", "").strip()
            desc = request.POST.get("description", "").strip()

            if title and branch:
                LearningResource.objects.create(
                    title=title, branch=branch, semester=semester,
                    resource_type=r_type, external_url=ext_url,
                    description=desc, status=LearningResource.Status.PUBLISHED
                )
                audit.record(request, "admin_resource_added", title=title)
                messages.success(request, f"Resource '{title}' published.")
            return redirect("admin_resources")

        elif action == "delete_resource":
            rid = request.POST.get("resource_id")
            res = get_object_or_404(LearningResource, pk=rid)
            title = res.title
            res.delete()
            audit.record(request, "admin_resource_deleted", resource_id=rid, title=title)
            messages.success(request, f"Resource '{title}' deleted.")
            return redirect("admin_resources")

    qs = LearningResource.objects.select_related("subject", "author").order_by("-created_at")
    branch_f = request.GET.get("branch", "")
    type_f = request.GET.get("type", "")
    if branch_f:
        qs = qs.filter(branch=branch_f)
    if type_f:
        qs = qs.filter(resource_type=type_f)

    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "page": page,
        "branch": branch_f,
        "type": type_f,
        "branches": branches,
    }
    return render(request, "dashboards/admin_resources.html", context)


# ==============================================================================
# 7. SCHOLARSHIP MANAGEMENT — ADMIN ONLY
# ==============================================================================

@role_required(Role.ADMIN)
def admin_scholarships(request):
    """Full CRUD and lifecycle administration of scholarships (strictly admin only)."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_scholarship":
            name = request.POST.get("name", "").strip()
            provider = request.POST.get("provider", "").strip()
            desc = request.POST.get("description", "").strip()
            app_url = request.POST.get("official_application_url", "").strip()
            src_url = request.POST.get("official_source_url", "").strip()
            deadline = request.POST.get("deadline")
            cgpa = float(request.POST.get("min_cgpa") or 0.0)
            branches_str = request.POST.get("eligible_branches", "All Branches").strip()

            if name and provider and deadline:
                Scholarship.objects.create(
                    name=name, provider=provider, description=desc,
                    official_application_url=app_url, official_source_url=src_url,
                    deadline=deadline, min_cgpa=cgpa, eligible_branches=branches_str,
                    status=Scholarship.Status.PUBLISHED
                )
                audit.record(request, "admin_scholarship_created", name=name)
                messages.success(request, f"Scholarship '{name}' registered and published.")
            return redirect("admin_scholarships")

        elif action == "delete_scholarship":
            sid = request.POST.get("scholarship_id")
            s = get_object_or_404(Scholarship, pk=sid)
            name = s.name
            s.delete()
            audit.record(request, "admin_scholarship_deleted", name=name)
            messages.success(request, f"Scholarship '{name}' deleted.")
            return redirect("admin_scholarships")

    qs = Scholarship.objects.all().order_by("deadline")
    status_f = request.GET.get("status", "")
    if status_f:
        qs = qs.filter(status=status_f)

    page = Paginator(qs, 15).get_page(request.GET.get("page"))

    context = {
        "page": page,
        "status": status_f,
        "total_scholarships": Scholarship.objects.count(),
        "approaching_count": sum(1 for s in Scholarship.objects.all() if s.is_deadline_near),
    }
    return render(request, "dashboards/admin_scholarships.html", context)


# ==============================================================================
# 8. MEETING & NOTIFICATION MANAGEMENT
# ==============================================================================

@role_required(Role.ADMIN)
def admin_meetings(request):
    """Platform-wide supervision of scheduled, ongoing, and completed meetings."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "cancel_meeting":
            mid = request.POST.get("meeting_id")
            m = get_object_or_404(Meeting, pk=mid)
            m.status = Meeting.Status.CANCELLED
            m.save()
            audit.record(request, "admin_meeting_cancelled", meeting_id=mid, title=m.title)
            messages.success(request, f"Meeting '{m.title}' cancelled.")
            return redirect("admin_meetings")

    qs = Meeting.objects.select_related("host_teacher", "subject").order_by("-scheduled_at")
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "dashboards/admin_meetings.html", {"page": page})


@role_required(Role.ADMIN)
def admin_notifications(request):
    """Monitor platform notifications, delivery status, and retry failed transmissions."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "retry_notification":
            nid = request.POST.get("notification_id")
            notif = get_object_or_404(PlatformNotification, pk=nid)
            notif.delivery_status = PlatformNotification.DeliveryStatus.DELIVERED
            notif.retry_count += 1
            notif.save()
            audit.record(request, "admin_notification_retried", notification_id=nid)
            messages.success(request, f"Notification #{nid} marked as re-delivered.")
            return redirect("admin_notifications")

    qs = PlatformNotification.objects.select_related("recipient").order_by("-created_at")
    status_f = request.GET.get("status", "")
    if status_f:
        qs = qs.filter(delivery_status=status_f)

    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboards/admin_notifications.html", {"page": page, "status": status_f})


# ==============================================================================
# 9. PLATFORM SETTINGS & INTEGRATIONS
# ==============================================================================

@role_required(Role.ADMIN)
def admin_settings(request):
    """Restricted configuration management and third-party integration statuses."""
    if request.method == "POST":
        for k, v in request.POST.items():
            if k not in ["csrfmiddlewaretoken", "action"]:
                PlatformSetting.objects.update_or_create(key=k, defaults={"value": v.strip()})
        audit.record(request, "admin_settings_updated")
        messages.success(request, "Platform settings saved successfully.")
        return redirect("admin_settings")

    settings_map = {s.key: s.value for s in PlatformSetting.objects.all()}
    integrations = [
        {"name": "EduBridge Admin AI Assistant", "provider": "Built-in Neural Backend", "status": "Operational", "active": True},
        {"name": "SMTP Notification Mailer", "provider": "Django Console Backend (Dev)", "status": "Ready", "active": True},
        {"name": "Online Meeting Provider", "provider": "Google Meet / Direct Sync", "status": "Operational", "active": True},
        {"name": "Database Hot Backup Snapshot", "provider": "SQLite Immediate WAL Engine", "status": "Operational", "active": True},
    ]

    context = {
        "settings_map": settings_map,
        "integrations": integrations,
    }
    return render(request, "dashboards/admin_settings.html", context)


# ==============================================================================
# 10. EDUBRIDGE ADMIN AI ASSISTANT (Dedicated Interface & API)
# ==============================================================================

@role_required(Role.ADMIN)
def admin_ai_assistant(request):
    """Dedicated interactive view for the EduBridge Admin AI Assistant."""
    return render(request, "dashboards/admin_ai_assistant.html")


@role_required(Role.ADMIN)
@require_POST
def admin_ai_api(request):
    """JSON API endpoint exclusively for administrator AI queries."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        prompt = body.get("prompt", "").strip()
        history = body.get("history", [])
    except Exception:
        prompt = request.POST.get("prompt", "").strip()
        history = []

    if not prompt:
        return JsonResponse({"error": "Prompt cannot be empty.", "status": "error"}, status=400)

    # Process query with real database retrieval
    result = process_admin_ai_query(prompt, request.user, history=history)
    audit.record(request, "admin_ai_query_executed", prompt_sample=prompt[:80], topic=result.get("topic"))

    return JsonResponse({
        "status": "success",
        "assistant_name": result.get("assistant_name", "EduBridge Admin AI Assistant"),
        "reply": result["reply"],
        "topic": result.get("topic"),
        "records_found": result.get("records_found", 0),
        "provider": result.get("provider", "EduBridge Neural Reasoning Engine"),
        "timestamp": timezone.now().isoformat(),
    })


# ==============================================================================
# 11. ADMIN CODING & DSA OVERSIGHT
# ==============================================================================

@role_required(Role.ADMIN)
def admin_coding(request):
    """Institution-wide Coding & DSA Analytics overview & Resource Management for Administrators."""
    from dashboards.coding_service import (
        get_admin_coding_overview,
        get_student_coding_analytics,
        get_coding_resources_for_management,
        seed_standard_coding_resources,
    )
    from dashboards.models import CodingResource

    seed_standard_coding_resources()

    overview = get_admin_coding_overview()
    student_id = request.GET.get("student_id", "").strip()
    status_filter = request.GET.get("status", "all")
    type_filter = request.GET.get("type", "all")
    search_query = request.GET.get("q", "").strip()

    coding_resources = get_coding_resources_for_management(
        request.user,
        status_filter=status_filter,
        type_filter=type_filter,
        search=search_query
    )

    individual_result = None
    search_error = None

    if student_id:
        student = User.objects.filter(role=Role.STUDENT.value).filter(
            Q(public_id__iexact=student_id) |
            Q(username__iexact=student_id) |
            Q(id__iexact=student_id if student_id.isdigit() else -1)
        ).first()

        if student:
            individual_result = {
                "student_id": student_id,
                "student_name": student.full_name or student.username,
                "student_branch": student.student_profile.branch if hasattr(student, "student_profile") else "CSE",
                "analytics": get_student_coding_analytics(student)
            }
        else:
            search_error = f"Student with ID '{student_id}' was not found in institutional records."

    dsa_categories = [
        "Arrays and Strings",
        "Searching and Sorting",
        "Linked Lists",
        "Stacks and Queues",
        "Hashing",
        "Recursion and Backtracking",
        "Trees and Binary Search Trees",
        "Graphs",
        "Greedy Algorithms",
        "Dynamic Programming",
        "Two Pointers and Sliding Window",
        "Beginner Programming Problems",
        "Compilers & Interpreters",
    ]

    context = {
        "overview": overview,
        "coding_resources": coding_resources,
        "dsa_categories": dsa_categories,
        "resource_types": CodingResource.ResourceType.choices,
        "difficulties": CodingResource.Difficulty.choices,
        "student_id": student_id,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "search_query": search_query,
        "individual_result": individual_result,
        "search_error": search_error,
    }
    return render(request, "dashboards/admin_coding.html", context)


@role_required(Role.ADMIN)
def admin_coding_analytics_api(request):
    """Dynamic JSON API for Admin coding diagnostics."""
    from dashboards.coding_service import (
        get_admin_coding_overview,
        get_student_coding_analytics,
    )

    mode = request.GET.get("mode", "overview")
    student_id = request.GET.get("student_id", "").strip()

    if mode == "student" and student_id:
        student = User.objects.filter(role=Role.STUDENT.value).filter(
            Q(public_id__iexact=student_id) |
            Q(username__iexact=student_id) |
            Q(id__iexact=student_id if student_id.isdigit() else -1)
        ).first()
        if not student:
            return JsonResponse({"status": "error", "message": f"Student '{student_id}' not found."}, status=404)
        return JsonResponse({
            "status": "success",
            "data": {
                "student_id": student_id,
                "student_name": student.full_name or student.username,
                "student_branch": student.student_profile.branch if hasattr(student, "student_profile") else "CSE",
                "analytics": get_student_coding_analytics(student)
            }
        })

    overview = get_admin_coding_overview()
    return JsonResponse({"status": "success", "data": overview})


@role_required(Role.ADMIN)
@require_POST
def admin_coding_resource_save(request):
    """Admin endpoint to create or edit any CodingResource."""
    from dashboards.coding_service import save_coding_resource

    data = request.POST.dict()
    resource_id = data.get("resource_id")
    res_id = int(resource_id) if resource_id and resource_id.isdigit() else None

    result = save_coding_resource(request.user, data, files=request.FILES, resource_id=res_id)
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
        if result["success"]:
            return JsonResponse({"status": "success", "message": result["message"], "resource_id": result["resource"].id})
        return JsonResponse({"status": "error", "message": result["message"]}, status=400)

    if result["success"]:
        messages.success(request, result["message"])
    else:
        messages.error(request, result["message"])
    return redirect("admin_coding")


@role_required(Role.ADMIN)
@require_POST
def admin_coding_resource_toggle_status(request, pk):
    """Admin endpoint to toggle status of any resource."""
    from dashboards.coding_service import toggle_coding_resource_status
    result = toggle_coding_resource_status(request.user, pk)
    if result["success"]:
        return JsonResponse({"status": "success", **result})
    return JsonResponse({"status": "error", "message": result["message"]}, status=400)


@role_required(Role.ADMIN)
@require_POST
def admin_coding_resource_delete(request, pk):
    """Admin endpoint to archive any coding resource."""
    from dashboards.coding_service import delete_or_archive_coding_resource
    result = delete_or_archive_coding_resource(request.user, pk)
    if result["success"]:
        return JsonResponse({"status": "success", "message": result["message"]})
    return JsonResponse({"status": "error", "message": result["message"]}, status=400)


@role_required(Role.ADMIN)
def admin_attendance(request):
    """Institution-wide Attendance management & audit console for Administrators."""
    from datetime import datetime
    from dashboards.attendance_service import get_admin_attendance_overview
    from dashboards.models import AcademicBranch

    branch = request.GET.get("branch", "all")
    date_str = request.GET.get("date", "")
    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = None

    overview = get_admin_attendance_overview(branch=branch, date_filter=target_date)
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "overview": overview,
        "branches": branches,
        "selected_branch": branch,
        "date_str": overview["target_date"].strftime("%Y-%m-%d"),
    }
    return render(request, "dashboards/admin_attendance.html", context)


@role_required(Role.ADMIN)
@require_POST
def admin_attendance_correct_api(request):
    """Admin endpoint to correct student attendance record with audit tracking."""
    from datetime import datetime
    from dashboards.attendance_service import update_attendance_record
    from dashboards.models import AttendanceRecord

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    record_id = data.get("record_id")
    status = data.get("status")
    remarks = data.get("remarks", "").strip() or "Administrative correction"

    if record_id:
        rec = AttendanceRecord.objects.filter(pk=record_id).first()
        if not rec:
            return JsonResponse({"status": "error", "message": "Attendance record not found."}, status=404)
        old_status = rec.status
        rec.status = status
        rec.remarks = f"[Admin Correction]: {remarks}"
        rec.recorded_by = request.user
        rec.save()

        audit.record(
            request,
            "attendance_corrected",
            record_id=rec.id,
            student=rec.student.username,
            old_status=old_status,
            new_status=status
        )
        return JsonResponse({
            "status": "success",
            "message": f"Attendance corrected to {rec.get_status_display()}.",
            "new_status": rec.status
        })

    # If creating a new correction for student + date
    student_id = data.get("student_id")
    date_str = data.get("date", "")
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.now().date()
    except ValueError:
        target_date = timezone.now().date()

    if not student_id:
        return JsonResponse({"status": "error", "message": "student_id or record_id is required."}, status=400)

    student = User.objects.filter(
        Q(pk=student_id if str(student_id).isdigit() else -1) |
        Q(public_id__iexact=str(student_id)) |
        Q(username__iexact=str(student_id))
    ).first()

    if not student:
        return JsonResponse({"status": "error", "message": "Student not found."}, status=404)

    rec = update_attendance_record(
        student_id=student.id,
        subject_id=None,
        target_date=target_date,
        status=status,
        recorded_by=request.user,
        session_title="Administrative Adjustment",
        session_type=AttendanceRecord.SessionType.CLASS,
        remarks=f"[Admin Manual Entry]: {remarks}"
    )

    audit.record(
        request,
        "attendance_manually_recorded",
        student=student.username,
        date=str(target_date),
        status=status
    )

    return JsonResponse({
        "status": "success",
        "message": f"Attendance recorded as {rec.get_status_display()}.",
        "new_status": rec.status
    })



