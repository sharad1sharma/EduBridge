"""EduBridge Student Workspace Views & Controllers.

Fully persistent, database-integrated controllers for B.Tech engineering students.
Implements:
- Personalized dashboard with real database feeds
- Interactive assessment taking with server-authoritative countdown & autosave
- Anti-cheating tab-switch detection & policy-driven auto-submission
- Results review & performance tracking
- Read-only resource library & scholarship discovery
- Student AI assistant API
- Persistent notifications
"""
import json
from datetime import timedelta
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from accounts import audit
from accounts.access import role_required
from accounts.constants import Role
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    CodingSubmission,
    DSAQuestion,
    DSATopic,
    LearningResource,
    Meeting,
    PlatformNotification,
    Scholarship,
    Subject,
)
from dashboards.student_ai import process_student_ai_query


@role_required(Role.STUDENT)
def student_dashboard(request):
    """Personalized student dashboard fed with live database records."""
    student = request.user
    profile = getattr(student, "student_profile", None)
    branch = profile.branch if profile else "CSE"
    semester = profile.semester if profile else 1
    percent, missing = profile.completion() if profile else (0, [])

    now = timezone.now()

    # Enrolled Subjects (authoritatively resolved)
    from dashboards.analytics_service import get_student_enrolled_subjects
    subjects = get_student_enrolled_subjects(student)
    enrolled_subject_ids = list(subjects.values_list("id", flat=True))

    # Assessments (Daily Assignments & Weekly Tests)
    from django.db.models import Q
    assessments_qs = Assessment.objects.filter(
        Q(branch=branch, semester=semester) | Q(target_students=student) | Q(subject_id__in=enrolled_subject_ids),
        status__in=[Assessment.Status.PUBLISHED, Assessment.Status.SCHEDULED]
    ).distinct().select_related("subject", "created_by").order_by("deadline")

    user_attempts = {
        att.assessment_id: att
        for att in AssessmentAttempt.objects.filter(student=student)
    }

    daily_assignments = []
    weekly_tests = []
    for a in assessments_qs:
        attempt = user_attempts.get(a.id)
        is_completed = attempt.status == AssessmentAttempt.AttemptStatus.COMPLETED if attempt else False
        is_in_prog = attempt.status == AssessmentAttempt.AttemptStatus.IN_PROGRESS if attempt else False
        is_scheduled = a.is_scheduled_future
        is_avail = a.is_available

        item = {
            "assessment": a,
            "attempt": attempt,
            "is_completed": is_completed,
            "is_in_progress": is_in_prog,
            "score": attempt.score if attempt else None,
            "is_overdue": a.deadline < now and (not attempt or not is_completed),
            "is_scheduled": is_scheduled,
            "is_available": is_avail,
        }
        if a.assessment_type == Assessment.AssessmentType.DAILY_ASSIGNMENT:
            daily_assignments.append(item)
        else:
            weekly_tests.append(item)

    # Live Meetings
    upcoming_meetings = Meeting.objects.filter(
        Q(branch=branch, semester=semester) | Q(subject_id__in=enrolled_subject_ids),
        status__in=[Meeting.Status.SCHEDULED, Meeting.Status.ONGOING],
        scheduled_at__gte=now - timedelta(hours=2)
    ).distinct().select_related("host_teacher", "subject").order_by("scheduled_at")[:5]

    # Published Resources
    recent_resources = LearningResource.objects.filter(
        Q(branch=branch, semester=semester) | Q(subject_id__in=enrolled_subject_ids),
        status=LearningResource.Status.PUBLISHED
    ).distinct().select_related("subject", "author").order_by("-created_at")[:6]

    # Published Scholarships with Eligibility Check
    from dashboards.scholarship_service import ensure_default_scholarships
    ensure_default_scholarships()

    scholarships_qs = Scholarship.objects.filter(
        status=Scholarship.Status.PUBLISHED
    ).order_by("deadline")[:4]

    scholarships = []
    for s in scholarships_qs:
        branch_match = (s.eligible_branches == "All Branches") or (branch in s.eligible_branches)
        cgpa_match = True  # profile does not strictly enforce CGPA field yet
        scholarships.append({
            "scholarship": s,
            "branch_match": branch_match,
            "is_eligible": branch_match and cgpa_match,
        })

    # Unread Notifications
    notifications_qs = PlatformNotification.objects.filter(
        recipient=student
    ).order_by("-created_at")
    unread_notif_count = notifications_qs.filter(is_read=False).count()
    notifications = list(notifications_qs[:8])

    # Completed Attempts for Performance widget
    completed_attempts = AssessmentAttempt.objects.filter(
        student=student,
        status=AssessmentAttempt.AttemptStatus.COMPLETED
    )
    avg_score = 0.0
    if completed_attempts.exists():
        avg_score = sum(a.score for a in completed_attempts) / completed_attempts.count()

    context = {
        "profile": profile,
        "percent": percent,
        "missing": missing,
        "daily_assignments": daily_assignments,
        "weekly_tests": weekly_tests,
        "upcoming_meetings": upcoming_meetings,
        "recent_resources": recent_resources,
        "scholarships": scholarships,
        "subjects": subjects,
        "notifications": notifications,
        "unread_notif_count": unread_notif_count,
        "avg_score": round(avg_score, 1),
        "completed_count": completed_attempts.count(),
    }
    return render(request, "dashboards/student_dashboard.html", context)


# ==============================================================================
# 2. ASSESSMENT TAKING, COUNTDOWN & AUTOSAVE
# ==============================================================================

@role_required(Role.STUDENT)
def student_assessment_view(request, pk):
    """Interactive assessment player with server-authoritative countdown."""
    assessment = get_object_or_404(Assessment, pk=pk, status__in=[Assessment.Status.PUBLISHED, Assessment.Status.SCHEDULED])
    student = request.user
    profile = getattr(student, "student_profile", None)

    # Boundary verification: Student's branch and semester or targeted list must match
    is_targeted = assessment.target_students.filter(pk=student.pk).exists()
    if profile and not is_targeted and (assessment.branch != profile.branch or assessment.semester != profile.semester):
        messages.error(request, "This assessment is not configured for your academic branch or semester.")
        return redirect("student_dashboard")

    # Schedule verification: cannot start before start_date
    if assessment.is_scheduled_future:
        messages.info(request, f"'{assessment.title}' is scheduled and will open on {assessment.start_date.strftime('%b %d, %Y at %I:%M %p')}.")
        return redirect("student_dashboard")

    # Retrieve or initialize attempt record inside atomic transaction
    attempt, created = AssessmentAttempt.objects.get_or_create(
        assessment=assessment,
        student=student,
        defaults={"status": AssessmentAttempt.AttemptStatus.IN_PROGRESS, "started_at": timezone.now()}
    )

    if attempt.status == AssessmentAttempt.AttemptStatus.COMPLETED:
        messages.info(request, f"You have already submitted '{assessment.title}'. View your score below.")
        return redirect("student_results")

    # Calculate remaining time (seconds) strictly based on server time
    now = timezone.now()
    max_seconds = assessment.duration_minutes * 60
    elapsed_seconds = (now - attempt.started_at).total_seconds()
    time_limit_left = max(0, int(max_seconds - elapsed_seconds))

    deadline_left = max(0, int((assessment.deadline - now).total_seconds()))
    remaining_seconds = min(time_limit_left, deadline_left)

    # If time has already expired on initial load, auto-finalize immediately
    if remaining_seconds <= 0:
        _finalize_attempt(attempt, assessment, is_auto=True)
        messages.warning(request, f"Assessment time limit has expired. Your attempt has been automatically finalized.")
        return redirect("student_results")

    context = {
        "assessment": assessment,
        "attempt": attempt,
        "remaining_seconds": remaining_seconds,
        "questions": assessment.questions_data or [],
        "coding_problems": assessment.coding_problems_data or [],
        "attempt_answers_json": json.dumps(attempt.answers or {}),
    }
    return render(request, "dashboards/student_assessment.html", context)


@role_required(Role.STUDENT)
@require_POST
def student_assessment_autosave(request, pk):
    """Periodic answer autosaving and integrity tab-switch tracking."""
    assessment = get_object_or_404(Assessment, pk=pk)
    student = request.user
    attempt = get_object_or_404(AssessmentAttempt, assessment=assessment, student=student)

    if attempt.status == AssessmentAttempt.AttemptStatus.COMPLETED:
        return JsonResponse({"status": "already_completed"}, status=400)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = {}

    answers = body.get("answers", {})
    tab_switch = bool(body.get("tab_switch", False))

    if isinstance(answers, dict):
        attempt.answers = answers

    if tab_switch:
        attempt.tab_switches_recorded += 1

    # Server-side timer check
    now = timezone.now()
    max_seconds = assessment.duration_minutes * 60
    elapsed_seconds = (now - attempt.started_at).total_seconds()
    if elapsed_seconds > max_seconds + 15 or now > assessment.deadline + timedelta(seconds=15):
        _finalize_attempt(attempt, assessment, is_auto=True)
        return JsonResponse({"status": "time_expired", "redirect": "/student/results/"})

    # Integrity policy: auto-submit on exceeding tab switches
    max_switches = assessment.max_tab_switches_allowed if assessment.max_tab_switches_allowed is not None else 3
    should_auto_submit = assessment.auto_submit_on_tab_switch or (max_switches > 0)
    if should_auto_submit and attempt.tab_switches_recorded >= max_switches:
        _finalize_attempt(attempt, assessment, is_auto=True)
        audit.record(request, "student_assessment_tab_violations",
                     assessment_id=assessment.pk, switches=attempt.tab_switches_recorded)
        return JsonResponse({
            "status": "auto_submitted",
            "reason": f"Assessment auto-submitted: Exceeded maximum allowed tab switches ({max_switches}).",
            "redirect": "/student/results/"
        })

    attempt.save(update_fields=["answers", "tab_switches_recorded"])
    return JsonResponse({
        "status": "saved",
        "tab_switches": attempt.tab_switches_recorded,
        "server_time": now.isoformat()
    })


@role_required(Role.STUDENT)
@require_POST
def student_assessment_submit(request, pk):
    """Final manual submission of an assessment attempt."""
    assessment = get_object_or_404(Assessment, pk=pk)
    student = request.user
    attempt = get_object_or_404(AssessmentAttempt, assessment=assessment, student=student)

    if attempt.status == AssessmentAttempt.AttemptStatus.COMPLETED:
        messages.warning(request, "This assessment attempt was already submitted.")
        return redirect("student_results")

    # If answers were posted via form
    if request.POST:
        form_answers = {}
        for k, v in request.POST.items():
            if k.startswith("q_"):
                form_answers[k.replace("q_", "")] = v
            elif k.startswith("code_"):
                form_answers[f"coding_{k.replace('code_', '')}"] = v
        if form_answers:
            attempt.answers.update(form_answers)

    _finalize_attempt(attempt, assessment, is_auto=False)
    audit.record(request, "student_assessment_submitted", assessment_id=assessment.pk, score=attempt.score)
    messages.success(request, f"Assessment '{assessment.title}' submitted successfully! You scored {attempt.score}/{assessment.total_marks}.")
    return redirect("student_results")


def _finalize_attempt(attempt: AssessmentAttempt, assessment: Assessment, is_auto: bool = False):
    """Grade MCQs and coding problems, mark attempt completed, and notify faculty & student."""
    from dashboards.notifications import notify_assessment_submitted, notify_results_released
    questions = assessment.questions_data or []
    coding_problems = assessment.coding_problems_data or []
    correct_count = 0
    wrong_count = 0
    total_mcqs = len(questions)

    for q in questions:
        qid = str(q.get("id"))
        correct_ans = str(q.get("correct", "")).strip().upper()
        student_ans = str(attempt.answers.get(qid, "")).strip().upper()
        if student_ans:
            if correct_ans and student_ans == correct_ans:
                correct_count += 1
            else:
                wrong_count += 1

    # Total score calculation: MCQs portion + Coding portion
    mcq_weight = 0.7 if coding_problems else 1.0
    coding_weight = 0.3 if coding_problems else 0.0

    mcq_score = 0.0
    if total_mcqs > 0:
        base_mcq = (correct_count / total_mcqs) * (assessment.total_marks * mcq_weight)
        neg_penalty = wrong_count * float(assessment.negative_marking or 0.0)
        mcq_score = max(0.0, base_mcq - neg_penalty)

    coding_score = 0.0
    if coding_problems:
        # Check submitted code for each challenge
        code_points = 0
        for c in coding_problems:
            cid = f"coding_{c.get('id')}"
            code_sub = attempt.answers.get(cid, {})
            # If code was submitted and not blank
            if isinstance(code_sub, dict) and code_sub.get("code", "").strip():
                code_points += 1
            elif isinstance(code_sub, str) and code_sub.strip():
                code_points += 1
        coding_score = (code_points / len(coding_problems)) * (assessment.total_marks * coding_weight)

    attempt.score = round(mcq_score + coding_score, 1)
    attempt.status = AssessmentAttempt.AttemptStatus.COMPLETED
    attempt.is_auto_submitted = is_auto
    attempt.submitted_at = timezone.now()
    attempt.save()

    # Trigger notifications: Teacher gets informed of submission, Student gets evaluated confirmation
    notify_assessment_submitted(attempt)
    notify_results_released(attempt)


# ==============================================================================
# 3. RESULTS & PERFORMANCE REVIEW
# ==============================================================================

@role_required(Role.STUDENT)
def student_results(request):
    """Detailed performance overview and past assessment submissions."""
    student = request.user
    attempts = AssessmentAttempt.objects.filter(
        student=student,
        status=AssessmentAttempt.AttemptStatus.COMPLETED
    ).select_related("assessment__subject").order_by("-submitted_at")

    total_attempts = attempts.count()
    avg_score = (sum(a.score for a in attempts) / total_attempts) if total_attempts > 0 else 0.0

    context = {
        "attempts": attempts,
        "total_attempts": total_attempts,
        "avg_score": round(avg_score, 1),
    }
    return render(request, "dashboards/student_results.html", context)


# ==============================================================================
# 4. LEARNING RESOURCES & SCHOLARSHIP DISCOVERY (READ-ONLY FOR STUDENTS)
# ==============================================================================

@role_required(Role.STUDENT)
def student_resources(request):
    """Searchable learning resources library. Strictly read-only for students."""
    if request.method not in ["GET", "HEAD"]:
        return HttpResponseForbidden("Students cannot create, edit, or delete learning resources.")

    student = request.user
    profile = getattr(student, "student_profile", None)
    branch = profile.branch if profile else "CSE"
    semester = profile.semester if profile else 1

    qs = LearningResource.objects.filter(
        status=LearningResource.Status.PUBLISHED
    ).select_related("subject", "author").order_by("-created_at")

    # Filters
    b_filter = request.GET.get("branch", branch)
    sem_filter = request.GET.get("semester", str(semester))
    type_filter = request.GET.get("type", "")
    q = request.GET.get("q", "").strip()

    if b_filter:
        qs = qs.filter(branch=b_filter)
    if sem_filter:
        try:
            qs = qs.filter(semester=int(sem_filter))
        except ValueError:
            pass
    if type_filter:
        qs = qs.filter(resource_type=type_filter)
    if q:
        qs = qs.filter(title__icontains=q)

    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "page": page,
        "branch": b_filter,
        "semester": sem_filter,
        "type": type_filter,
        "q": q,
        "branches": branches,
    }
    return render(request, "dashboards/student_resources.html", context)


@role_required(Role.STUDENT)
def student_scholarships(request):
    """Verified scholarships with eligibility criteria matching. Strictly read-only for students."""
    if request.method not in ["GET", "HEAD"]:
        return HttpResponseForbidden("Students cannot create, modify, or delete scholarship records.")

    student = request.user
    profile = getattr(student, "student_profile", None)
    branch = profile.branch if profile else "CSE"

    from dashboards.scholarship_service import ensure_default_scholarships
    ensure_default_scholarships()

    qs = Scholarship.objects.filter(status=Scholarship.Status.PUBLISHED).order_by("deadline")
    scholarships = []
    for s in qs:
        is_branch_match = (s.eligible_branches == "All Branches") or (branch in s.eligible_branches)
        scholarships.append({
            "record": s,
            "branch_match": is_branch_match,
            "is_near": s.is_deadline_near,
        })

    context = {
        "scholarships": scholarships,
        "student_branch": branch,
    }
    return render(request, "dashboards/student_scholarships.html", context)


# ==============================================================================
# 5. CODING PRACTICE & NOTIFICATIONS
# ==============================================================================

@role_required(Role.STUDENT)
def student_coding(request):
    """B.Tech Student Coding Resources & DSA Practice Hub featuring:
    - Area A: Visual library of DSA topics and external practice questions (LeetCode, GFG, HackerRank)
    - Area B: Curated online compilers & cloud interpreters (Programiz, OnlineGDB, Replit, JDoodle)
    Strictly read-only for students. Opens practice links in new browser tabs.
    """
    if request.method not in ["GET", "HEAD"]:
        return HttpResponseForbidden("Students cannot create, edit, publish, or delete shared coding resources.")

    from dashboards.coding_service import DSA_CATEGORIES, seed_standard_coding_resources
    from dashboards.models import CodingResource

    seed_standard_coding_resources()

    student = request.user
    profile = getattr(student, "student_profile", None)
    branch = profile.branch if profile else "CSE"

    category_filter = request.GET.get("category", "").strip()
    difficulty_filter = request.GET.get("difficulty", "").strip()
    search_q = request.GET.get("q", "").strip()

    # Area A: DSA Practice Questions and Topics
    dsa_qs = CodingResource.objects.filter(
        status=CodingResource.Status.PUBLISHED,
        resource_type__in=[CodingResource.ResourceType.DSA_QUESTION, CodingResource.ResourceType.DSA_TOPIC]
    )
    if category_filter:
        dsa_qs = dsa_qs.filter(topic_category=category_filter)
    if difficulty_filter:
        dsa_qs = dsa_qs.filter(difficulty=difficulty_filter)
    if search_q:
        dsa_qs = dsa_qs.filter(
            Q(title__icontains=search_q) |
            Q(description__icontains=search_q) |
            Q(topic_category__icontains=search_q) |
            Q(platform_name__icontains=search_q)
        )

    dsa_resources = list(dsa_qs)

    # Area B: Online Compilers and Interpreters
    compilers_qs = CodingResource.objects.filter(
        status=CodingResource.Status.PUBLISHED,
        resource_type=CodingResource.ResourceType.COMPILER
    )
    if search_q:
        compilers_qs = compilers_qs.filter(
            Q(title__icontains=search_q) |
            Q(description__icontains=search_q) |
            Q(supported_languages__icontains=search_q) |
            Q(platform_name__icontains=search_q)
        )
    compilers = list(compilers_qs)

    # Telemetry and category distribution counts
    total_dsa = CodingResource.objects.filter(
        status=CodingResource.Status.PUBLISHED,
        resource_type__in=[CodingResource.ResourceType.DSA_QUESTION, CodingResource.ResourceType.DSA_TOPIC]
    ).count()

    context = {
        "branch": branch,
        "categories": DSA_CATEGORIES,
        "difficulties": ["Beginner", "Easy", "Medium", "Hard"],
        "selected_category": category_filter,
        "selected_difficulty": difficulty_filter,
        "search_q": search_q,
        "dsa_resources": dsa_resources,
        "compilers": compilers,
        "total_dsa": total_dsa,
        "total_compilers": len(compilers),
    }
    return render(request, "dashboards/student_coding.html", context)


@role_required(Role.STUDENT)
@require_POST
def coding_run_api(request):
    """Deprecated legacy endpoint: in-platform execution replaced by external practice hub."""
    return JsonResponse({
        "status": "error",
        "message": "In-platform code execution has been upgraded to the Coding Resources & DSA Practice Hub. Practice directly on external platforms."
    }, status=403)


@role_required(Role.STUDENT)
@require_POST
def coding_submit_api(request):
    """Deprecated legacy endpoint: in-platform submission replaced by external practice hub."""
    return JsonResponse({
        "status": "error",
        "message": "In-platform code submission has been upgraded to the Coding Resources & DSA Practice Hub. Practice directly on external platforms."
    }, status=403)


@role_required(Role.STUDENT)
@require_POST
def student_notification_read(request, pk):
    """Mark a notification as read."""
    notif = get_object_or_404(PlatformNotification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.read_at = timezone.now()
    notif.save(update_fields=["is_read", "read_at"])
    return JsonResponse({"status": "read", "id": pk})


# ==============================================================================
# 6. EDUBRIDGE STUDENT AI ASSISTANT API
# ==============================================================================

@role_required(Role.STUDENT)
@require_POST
def student_ai_api(request):
    """Student AI query endpoint answering strictly from student's authorized records."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        prompt = body.get("prompt", "").strip()
        history = body.get("history", [])
    except Exception:
        prompt = request.POST.get("prompt", "").strip()
        history = []

    if not prompt:
        return JsonResponse({"error": "Prompt cannot be empty.", "status": "error"}, status=400)

    result = process_student_ai_query(prompt, request.user, history=history)
    audit.record(request, "student_ai_query_executed", prompt_sample=prompt[:80], topic=result.get("topic"))

    return JsonResponse({
        "status": "success",
        "assistant_name": result.get("assistant_name", "EduBridge Student AI Assistant"),
        "reply": result["reply"],
        "topic": result.get("topic"),
        "records_found": result.get("records_found", 0),
        "provider": result.get("provider", "EduBridge Neural Reasoning Engine"),
        "timestamp": timezone.now().isoformat(),
    })


# ==============================================================================
# 7. STUDENT ANALYTICS DASHBOARD & TELEMETRY API
# ==============================================================================

@role_required(Role.STUDENT)
@require_safe
def student_analytics(request):
    """Dedicated personal academic analytics workspace strictly isolated for student."""
    from dashboards.analytics_service import get_student_personal_analytics
    student = request.user
    subject_id = request.GET.get("subject_id")
    range_key = request.GET.get("range", "30d")
    view_mode = request.GET.get("view", "daily")
    assessment_type = request.GET.get("type", "all")

    data = get_student_personal_analytics(
        student=student,
        subject_id=subject_id,
        range_key=range_key,
        view_mode=view_mode,
        assessment_type=assessment_type
    )

    context = {
        "analytics": data,
        "selected_range": range_key,
        "selected_subject_id": subject_id,
        "selected_type": assessment_type,
    }
    return render(request, "dashboards/student_analytics.html", context)


@role_required(Role.STUDENT)
@require_safe
def student_analytics_api(request):
    """Dynamic JSON endpoint for student analytics filtering."""
    from dashboards.analytics_service import get_student_personal_analytics
    student = request.user
    subject_id = request.GET.get("subject_id")
    range_key = request.GET.get("range", "30d")
    view_mode = request.GET.get("view", "daily")
    assessment_type = request.GET.get("type", "all")

    data = get_student_personal_analytics(
        student=student,
        subject_id=subject_id,
        range_key=range_key,
        view_mode=view_mode,
        assessment_type=assessment_type
    )
    return JsonResponse({"status": "success", "data": data})


@role_required(Role.STUDENT)
@require_safe
def student_attendance(request):
    """Personal Attendance Record view for students."""
    from dashboards.attendance_service import get_student_attendance_summary
    student = request.user
    summary = get_student_attendance_summary(student)
    context = {
        "summary": summary,
        "student": student,
    }
    return render(request, "dashboards/student_attendance.html", context)



