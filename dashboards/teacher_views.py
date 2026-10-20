"""EduBridge Teacher Workspace Views & Controllers.

Fully persistent, database-integrated controllers for faculty instructors and professors.
Implements:
- Teacher dashboard with live academic metrics
- Student directory & individual diagnostic performance review
- Daily assignment (>=10 MCQs) & Weekly test (25 MCQs + 5 coding) creation & management
- Assessment integrity settings (anti-cheat tab-monitoring thresholds)
- Live meeting scheduling with automated student notification dispatch
- Learning resource repository management
- Teacher AI assistant API
- Strict restriction: Teachers cannot manage scholarships or access admin consoles
"""
import json
from datetime import timedelta
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts import audit
from accounts.access import role_required
from accounts.constants import Role
from accounts.models import StudentProfile, User
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    LearningResource,
    Meeting,
    PlatformNotification,
    Subject,
)
from dashboards.teacher_ai import process_teacher_ai_query


@role_required(Role.TEACHER)
def teacher_dashboard(request):
    """Personalized teacher workspace fed with live institutional data."""
    teacher = request.user
    profile = getattr(teacher, "teacher_profile", None)
    percent, missing = profile.completion() if profile else (0, [])
    dept = profile.department if profile else "CSE"

    assigned_subjects = teacher.assigned_subjects.all().order_by("code")
    assigned_branches = list(set(assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    # Student enrollment in teacher's subjects/branches
    enrolled_students = User.objects.filter(
        role=Role.STUDENT.value,
        student_profile__branch__in=assigned_branches
    ).select_related("student_profile")
    total_enrolled = enrolled_students.count()

    # Assessments created by this faculty
    created_assessments = Assessment.objects.filter(
        created_by=teacher
    ).select_related("subject").order_by("-deadline")
    total_assessments = created_assessments.count()

    # Submissions received
    total_submissions = AssessmentAttempt.objects.filter(
        assessment__in=created_assessments
    ).count()

    # Upcoming Meetings hosted by this faculty
    now = timezone.now()
    upcoming_meetings = Meeting.objects.filter(
        host_teacher=teacher,
        scheduled_at__gte=now - timedelta(hours=2)
    ).select_related("subject").order_by("scheduled_at")[:5]

    # Authored Resources
    authored_resources = LearningResource.objects.filter(
        author=teacher
    ).order_by("-created_at")[:5]

    # Notifications
    notifications_qs = PlatformNotification.objects.filter(
        recipient=teacher
    ).order_by("-created_at")
    unread_notifs = notifications_qs.filter(is_read=False).count()
    notifications = list(notifications_qs[:6])

    context = {
        "profile": profile,
        "percent": percent,
        "missing": missing,
        "assigned_subjects": assigned_subjects,
        "assigned_branches": assigned_branches,
        "total_enrolled": total_enrolled,
        "total_assessments": total_assessments,
        "total_submissions": total_submissions,
        "upcoming_meetings": upcoming_meetings,
        "authored_resources": authored_resources,
        "notifications": notifications,
        "unread_notifs": unread_notifs,
        "recent_students": enrolled_students[:6],
    }
    return render(request, "dashboards/teacher_dashboard.html", context)


# ==============================================================================
# 2. TEACHER STUDENT DIRECTORY & PERFORMANCE ANALYSIS
# ==============================================================================

@role_required(Role.TEACHER)
def teacher_students(request):
    """Directory of students enrolled in the teacher's department or courses."""
    teacher = request.user
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"

    assigned_branches = list(set(teacher.assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    qs = User.objects.filter(
        role=Role.STUDENT.value,
        student_profile__branch__in=assigned_branches
    ).select_related("student_profile").order_by("public_id")

    # Filters
    q = request.GET.get("q", "").strip()
    branch_f = request.GET.get("branch", "")
    sem_f = request.GET.get("semester", "")

    if q:
        qs = qs.filter(public_id__icontains=q) | qs.filter(full_name__icontains=q) | qs.filter(username__icontains=q)
    if branch_f:
        qs = qs.filter(student_profile__branch=branch_f)
    if sem_f:
        try:
            qs = qs.filter(student_profile__semester=int(sem_f))
        except ValueError:
            pass

    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    branches = AcademicBranch.objects.filter(is_archived=False)

    context = {
        "page": page,
        "q": q,
        "branch": branch_f,
        "semester": sem_f,
        "branches": branches,
    }
    return render(request, "dashboards/teacher_students.html", context)


@role_required(Role.TEACHER)
def teacher_student_detail(request, pk):
    """Detailed academic performance diagnostics for an individual student."""
    student = get_object_or_404(User, pk=pk, role=Role.STUDENT.value)
    s_profile = getattr(student, "student_profile", None)

    # Attempts by this student
    attempts = AssessmentAttempt.objects.filter(
        student=student
    ).select_related("assessment__subject").order_by("-submitted_at", "-started_at")

    completed_attempts = attempts.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED)
    avg_score = 0.0
    if completed_attempts.exists():
        avg_score = sum(a.score for a in completed_attempts) / completed_attempts.count()

    context = {
        "student": student,
        "profile": s_profile,
        "attempts": attempts,
        "total_attempts": attempts.count(),
        "completed_count": completed_attempts.count(),
        "avg_score": round(avg_score, 1),
    }
    return render(request, "dashboards/teacher_student_detail.html", context)


# ==============================================================================
# 3. ASSIGNMENT & ASSESSMENT CREATION AND MANAGEMENT
# ==============================================================================

@role_required(Role.TEACHER)
def teacher_assessments(request):
    """View and manage assessments authored by this faculty."""
    teacher = request.user
    qs = Assessment.objects.filter(created_by=teacher).select_related("subject").order_by("-created_at")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_status":
            aid = request.POST.get("assessment_id")
            assessment = get_object_or_404(Assessment, pk=aid, created_by=teacher)
            new_status = request.POST.get("new_status")
            if new_status in Assessment.Status.values:
                assessment.status = new_status
                assessment.save()
                messages.success(request, f"Assessment '{assessment.title}' is now {new_status}.")
            return redirect("teacher_assessments")

    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "dashboards/teacher_assessments.html", {"page": page})


def _parse_bulk_mcqs_text(text: str) -> list:
    """Parse bulk pasted MCQ text into structured question objects."""
    import re
    items = []
    blocks = re.split(r'\n\s*\n|(?=Q\d+[\.:\)])', text)
    for b in blocks:
        lines = [ln.strip() for ln in b.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        q_line = lines[0]
        q_text = re.sub(r'^(?:Q\d+[\.:\)]\s*|\d+[\.:\)]\s*)', '', q_line).strip()
        options = []
        correct = 'A'
        marks = 4.0
        for ln in lines[1:]:
            opt_m = re.match(r'^([A-D])[\)\.:\-]\s*(.*)$', ln, re.IGNORECASE)
            if opt_m:
                options.append(f"{opt_m.group(1).upper()}) {opt_m.group(2)}")
            ans_m = re.search(r'^(?:Answer|Ans|Correct)[\s:\-]*([A-D])', ln, re.IGNORECASE)
            if ans_m:
                correct = ans_m.group(1).upper()
            mk_m = re.search(r'^(?:Marks|Mark)[\s:\-]*(\d+)', ln, re.IGNORECASE)
            if mk_m:
                try:
                    marks = float(mk_m.group(1))
                except Exception:
                    pass
        if q_text and len(options) >= 2:
            items.append({
                "id": len(items) + 1,
                "question": q_text,
                "options": options,
                "correct": correct,
                "marks": marks,
                "explanation": ""
            })
    return items


@role_required(Role.TEACHER)
def teacher_assessment_new(request):
    """Create a new Assignment, Quiz, or Test with manual, bulk, or AI-generated questions."""
    from django.utils.dateparse import parse_datetime
    from dashboards.notifications import notify_assignment_published
    teacher = request.user
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        topic = request.POST.get("topic", "").strip()
        difficulty = request.POST.get("difficulty", "Medium")
        a_type = request.POST.get("assessment_type", Assessment.AssessmentType.DAILY_ASSIGNMENT)
        branch = request.POST.get("branch", dept)
        semester = int(request.POST.get("semester", 3))
        subject_id = request.POST.get("subject_id")
        subject = Subject.objects.filter(pk=subject_id).first() if subject_id else None
        duration = max(5, int(request.POST.get("duration_minutes", 45)))
        total_marks = max(1, int(request.POST.get("total_marks", 100)))
        max_att = max(1, int(request.POST.get("max_attempts", 1)))
        try:
            neg_marks = float(request.POST.get("negative_marking", 0.0))
        except (ValueError, TypeError):
            neg_marks = 0.0

        start_str = request.POST.get("start_date")
        deadline_str = request.POST.get("deadline")
        desc = request.POST.get("description", "").strip()
        submit_action = request.POST.get("action", "publish")  # 'draft', 'publish', or 'schedule'

        auto_tab = request.POST.get("auto_submit_on_tab_switch") == "on"
        max_tabs = int(request.POST.get("max_tab_switches_allowed", 3))

        # Parse Questions (Manual, Bulk, or AI JSON)
        questions = []
        q_json_str = request.POST.get("questions_json", "").strip()
        if q_json_str:
            try:
                questions = json.loads(q_json_str)
            except Exception:
                questions = []

        # Parse individual form field MCQs (question_1_text, etc.)
        for key in list(request.POST.keys()):
            if key.startswith("question_") and key.endswith("_text"):
                idx = key.split("_")[1]
                q_text = request.POST.get(f"question_{idx}_text", "").strip()
                if q_text:
                    opt_a = request.POST.get(f"question_{idx}_opt_A", "").strip()
                    opt_b = request.POST.get(f"question_{idx}_opt_B", "").strip()
                    opt_c = request.POST.get(f"question_{idx}_opt_C", "").strip()
                    opt_d = request.POST.get(f"question_{idx}_opt_D", "").strip()
                    correct = request.POST.get(f"question_{idx}_correct", "A").strip().upper()
                    try:
                        q_marks = float(request.POST.get(f"question_{idx}_marks", 4))
                    except Exception:
                        q_marks = 4.0
                    questions.append({
                        "id": len(questions) + 1,
                        "question": q_text,
                        "options": [f"A) {opt_a}", f"B) {opt_b}", f"C) {opt_c}", f"D) {opt_d}"],
                        "correct": correct,
                        "marks": q_marks,
                        "explanation": ""
                    })

        # Parse bulk MCQs text if provided
        bulk_text = request.POST.get("bulk_mcqs", "").strip()
        if bulk_text:
            parsed_bulk = _parse_bulk_mcqs_text(bulk_text)
            for item in parsed_bulk:
                item["id"] = len(questions) + 1
                questions.append(item)

        coding_problems = []
        c_json_str = request.POST.get("coding_problems_json", "").strip()
        if c_json_str:
            try:
                coding_problems = json.loads(c_json_str)
            except Exception:
                coding_problems = []

        # Parse individual form field coding questions
        for key in list(request.POST.keys()):
            if key.startswith("coding_") and key.endswith("_title"):
                idx = key.split("_")[1]
                c_title = request.POST.get(f"coding_{idx}_title", "").strip()
                if c_title:
                    c_desc = request.POST.get(f"coding_{idx}_description", "").strip()
                    c_in = request.POST.get(f"coding_{idx}_sample_in", "").strip()
                    c_out = request.POST.get(f"coding_{idx}_sample_out", "").strip()
                    try:
                        c_marks = float(request.POST.get(f"coding_{idx}_marks", 10))
                    except Exception:
                        c_marks = 10.0
                    coding_problems.append({
                        "id": len(coding_problems) + 1,
                        "title": c_title,
                        "description": c_desc,
                        "constraints": "Standard execution limits",
                        "sample_input": c_in,
                        "sample_output": c_out,
                        "test_cases": [{"input": c_in, "output": c_out, "hidden": False}],
                        "lang": "python",
                        "marks": c_marks
                    })

        # If no questions submitted, generate default questions based on assessment type
        if not questions and not coding_problems:
            num_mcqs = 25 if a_type == Assessment.AssessmentType.WEEKLY_TEST else 10
            for i in range(1, num_mcqs + 1):
                questions.append({
                    "id": i,
                    "question": f"Question #{i}: Foundational Concept in {topic or branch} (Semester {semester})",
                    "options": [
                        "A) Primary theoretical model and asymptotic bound",
                        "B) Alternative optimization technique",
                        "C) Worst-case operational boundary",
                        "D) Implementation-specific constraint"
                    ],
                    "correct": "A",
                    "marks": round(total_marks / num_mcqs, 1),
                    "explanation": f"Standard core concept verification for {topic or branch}."
                })

            if a_type in [Assessment.AssessmentType.WEEKLY_TEST, Assessment.AssessmentType.MIXED]:
                for c in range(1, 4):
                    coding_problems.append({
                        "id": c,
                        "title": f"Coding Challenge #{c}: {topic or branch} Problem Solving",
                        "description": f"Write an optimal solution in Python solving computational challenge #{c} for {topic or branch}.",
                        "constraints": "1 <= N <= 10^5",
                        "sample_input": "5\n1 2 3 4 5",
                        "sample_output": "15",
                        "test_cases": [
                            {"input": "5\n1 2 3 4 5", "output": "15", "hidden": False},
                            {"input": "3\n10 20 30", "output": "60", "hidden": True}
                        ],
                        "lang": "python",
                        "marks": 10
                    })

        if not title:
            messages.error(request, "Assessment Title is mandatory.")
            return redirect("teacher_assessment_new")

        now = timezone.now()
        parsed_start = parse_datetime(start_str) if start_str else now
        if not parsed_start or timezone.is_naive(parsed_start):
            parsed_start = timezone.make_aware(parsed_start) if parsed_start else now

        parsed_deadline = parse_datetime(deadline_str) if deadline_str else (parsed_start + timedelta(days=2))
        if not parsed_deadline or timezone.is_naive(parsed_deadline):
            parsed_deadline = timezone.make_aware(parsed_deadline) if parsed_deadline else (parsed_start + timedelta(days=2))

        # Determine Status
        if submit_action == "draft":
            status = Assessment.Status.DRAFT
        elif submit_action == "schedule" or parsed_start > now:
            status = Assessment.Status.SCHEDULED
        else:
            status = Assessment.Status.PUBLISHED

        assessment = Assessment.objects.create(
            title=title,
            topic=topic,
            difficulty=difficulty,
            assessment_type=a_type,
            branch=branch,
            semester=semester,
            subject=subject,
            created_by=teacher,
            description=desc,
            duration_minutes=duration,
            total_marks=total_marks,
            start_date=parsed_start,
            deadline=parsed_deadline,
            max_attempts=max_att,
            negative_marking=neg_marks,
            questions_data=questions,
            coding_problems_data=coding_problems,
            auto_submit_on_tab_switch=auto_tab,
            max_tab_switches_allowed=max_tabs,
            status=status
        )

        # Dispatch student notifications if published or scheduled
        notified_count = 0
        if status in [Assessment.Status.PUBLISHED, Assessment.Status.SCHEDULED]:
            notified_count = notify_assignment_published(assessment, teacher)

        audit.record(request, "teacher_assessment_created", assessment_id=assessment.pk, title=title, status=status)
        if status == Assessment.Status.DRAFT:
            messages.success(request, f"Saved '{title}' as Draft with {len(questions)} MCQs and {len(coding_problems)} coding challenges.")
        else:
            messages.success(request, f"Published '{title}' with {len(questions)} MCQs, {len(coding_problems)} coding challenges. Dispatched alerts to {notified_count} eligible students.")
        return redirect("teacher_assessments")

    branches = AcademicBranch.objects.filter(is_archived=False)
    subjects = Subject.objects.all().order_by("branch", "semester", "code")

    now = timezone.now()
    default_deadline = now + timedelta(days=2)
    context = {
        "branches": branches,
        "subjects": subjects,
        "is_edit": False,
        "assessment": None,
        "default_start_date": now.strftime("%Y-%m-%dT%H:%M"),
        "default_deadline": default_deadline.strftime("%Y-%m-%dT%H:%M"),
        "questions_json": "[]",
        "coding_problems_json": "[]",
    }
    return render(request, "dashboards/teacher_assessment_form.html", context)


@role_required(Role.TEACHER)
def teacher_assessment_edit(request, pk):
    """Edit an existing assessment authored by the teacher."""
    from django.utils.dateparse import parse_datetime
    from dashboards.notifications import notify_assignment_published
    teacher = request.user
    assessment = get_object_or_404(Assessment, pk=pk, created_by=teacher)

    if request.method == "POST":
        assessment.title = request.POST.get("title", assessment.title).strip()
        assessment.topic = request.POST.get("topic", assessment.topic).strip()
        assessment.difficulty = request.POST.get("difficulty", assessment.difficulty)
        assessment.assessment_type = request.POST.get("assessment_type", assessment.assessment_type)
        assessment.branch = request.POST.get("branch", assessment.branch)
        assessment.semester = int(request.POST.get("semester", assessment.semester))
        
        sub_id = request.POST.get("subject_id")
        assessment.subject = Subject.objects.filter(pk=sub_id).first() if sub_id else None
        assessment.duration_minutes = max(5, int(request.POST.get("duration_minutes", assessment.duration_minutes)))
        assessment.total_marks = max(1, int(request.POST.get("total_marks", assessment.total_marks)))
        assessment.description = request.POST.get("description", assessment.description).strip()
        assessment.auto_submit_on_tab_switch = request.POST.get("auto_submit_on_tab_switch") == "on"
        assessment.max_tab_switches_allowed = int(request.POST.get("max_tab_switches_allowed", assessment.max_tab_switches_allowed))
        assessment.max_attempts = max(1, int(request.POST.get("max_attempts", assessment.max_attempts or 1)))
        try:
            assessment.negative_marking = float(request.POST.get("negative_marking", assessment.negative_marking or 0.0))
        except Exception:
            pass

        start_str = request.POST.get("start_date")
        if start_str:
            p_start = parse_datetime(start_str)
            if p_start:
                assessment.start_date = timezone.make_aware(p_start) if timezone.is_naive(p_start) else p_start

        deadline_str = request.POST.get("deadline")
        if deadline_str:
            p_dead = parse_datetime(deadline_str)
            if p_dead:
                assessment.deadline = timezone.make_aware(p_dead) if timezone.is_naive(p_dead) else p_dead

        # Questions JSON update
        q_json_str = request.POST.get("questions_json", "").strip()
        if q_json_str:
            try:
                assessment.questions_data = json.loads(q_json_str)
            except Exception:
                pass

        c_json_str = request.POST.get("coding_problems_json", "").strip()
        if c_json_str:
            try:
                assessment.coding_problems_data = json.loads(c_json_str)
            except Exception:
                pass

        submit_action = request.POST.get("action", "publish")
        old_status = assessment.status
        now = timezone.now()
        if submit_action == "draft":
            assessment.status = Assessment.Status.DRAFT
        elif submit_action == "schedule" or assessment.start_date > now:
            assessment.status = Assessment.Status.SCHEDULED
        else:
            assessment.status = Assessment.Status.PUBLISHED

        assessment.save()

        # If transitioning from Draft to Published, notify students
        if old_status != Assessment.Status.PUBLISHED and assessment.status == Assessment.Status.PUBLISHED:
            notify_assignment_published(assessment, teacher)

        audit.record(request, "teacher_assessment_updated", assessment_id=assessment.pk, title=assessment.title)
        messages.success(request, f"Updated assessment '{assessment.title}'.")
        return redirect("teacher_assessments")

    branches = AcademicBranch.objects.filter(is_archived=False)
    subjects = Subject.objects.all().order_by("branch", "semester", "code")

    context = {
        "branches": branches,
        "subjects": subjects,
        "is_edit": True,
        "assessment": assessment,
        "questions_json": json.dumps(assessment.questions_data or []),
        "coding_problems_json": json.dumps(assessment.coding_problems_data or []),
    }
    return render(request, "dashboards/teacher_assessment_form.html", context)


@role_required(Role.TEACHER)
def teacher_assessment_preview(request, pk):
    """Preview the exact assessment interface that students will see."""
    teacher = request.user
    assessment = get_object_or_404(Assessment, pk=pk, created_by=teacher)

    context = {
        "assessment": assessment,
        "questions": assessment.questions_data or [],
        "coding_problems": assessment.coding_problems_data or [],
        "is_preview": True,
    }
    return render(request, "dashboards/teacher_assessment_preview.html", context)


@role_required(Role.TEACHER)
@require_POST
def teacher_assessment_delete(request, pk):
    """Safely archive or delete an assessment."""
    teacher = request.user
    assessment = get_object_or_404(Assessment, pk=pk, created_by=teacher)
    title = assessment.title
    assessment.delete()
    audit.record(request, "teacher_assessment_deleted", assessment_id=pk, title=title)
    messages.success(request, f"Assessment '{title}' was deleted.")
    return redirect("teacher_assessments")


@role_required(Role.TEACHER, Role.ADMIN)
@require_POST
def teacher_ai_generate_questions(request):
    """API endpoint to generate structured MCQs and coding challenges via AI for faculty and administrators."""
    from dashboards.ai_service import generate_assessment_questions
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        data = {}

    topic = data.get("topic", "Data Structures and Algorithms")
    difficulty = data.get("difficulty", "Medium")
    count_mcqs = int(data.get("count_mcqs") or data.get("mcq_count") or 5)
    count_coding = int(data.get("count_coding") or data.get("coding_count") or 1)
    language = data.get("language", "python")
    subject_title = data.get("subject_title", "Computer Science")

    result = generate_assessment_questions(
        topic=topic,
        difficulty=difficulty,
        count_mcqs=count_mcqs,
        count_coding=count_coding,
        language=language,
        subject_title=subject_title
    )
    return JsonResponse(result)


# ==============================================================================
# 4. MEETING SCHEDULING & STUDENT NOTIFICATIONS
# ==============================================================================

@role_required(Role.TEACHER)
def teacher_meetings(request):
    """View and manage scheduled live classes."""
    teacher = request.user
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "cancel_meeting":
            mid = request.POST.get("meeting_id")
            m = get_object_or_404(Meeting, pk=mid, host_teacher=teacher)
            m.status = Meeting.Status.CANCELLED
            m.save()

            # Dispatch cancellation alerts to students
            students = User.objects.filter(
                role=Role.STUDENT.value,
                student_profile__branch=m.branch,
                student_profile__semester=m.semester
            )
            cancel_disp = m.scheduled_at.strftime('%b %d at %I:%M %p') if hasattr(m.scheduled_at, 'strftime') else str(m.scheduled_at)
            for s in students:
                PlatformNotification.objects.create(
                    recipient=s,
                    title=f"Meeting Cancelled: {m.title}",
                    message=f"The scheduled lecture on {cancel_disp} has been cancelled by Prof. {teacher.full_name}.",
                    notification_type=PlatformNotification.NotificationType.MEETING_CANCEL,
                    link="/student/"
                )

            audit.record(request, "teacher_meeting_cancelled", meeting_id=mid, title=m.title)
            messages.success(request, f"Meeting '{m.title}' cancelled and participants notified.")
            return redirect("teacher_meetings")

    meetings = Meeting.objects.filter(host_teacher=teacher).order_by("-scheduled_at")
    page = Paginator(meetings, 15).get_page(request.GET.get("page"))
    return render(request, "dashboards/teacher_meetings.html", {"page": page})


@role_required(Role.TEACHER)
def teacher_meeting_new(request):
    """Schedule a live lecture or tutorial session."""
    teacher = request.user
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        branch = request.POST.get("branch", dept)
        semester = int(request.POST.get("semester", 3))
        subject_id = request.POST.get("subject_id")
        subject = Subject.objects.filter(pk=subject_id).first() if subject_id else None
        sched_time = request.POST.get("scheduled_at")
        duration = int(request.POST.get("duration_minutes", 60))
        link = request.POST.get("meeting_link", "").strip()
        desc = request.POST.get("description", "").strip()

        if title and sched_time and link:
            from django.utils.dateparse import parse_datetime
            parsed_time = parse_datetime(sched_time) if isinstance(sched_time, str) else sched_time
            if not parsed_time:
                parsed_time = timezone.now() + timedelta(days=1)
            elif timezone.is_naive(parsed_time):
                parsed_time = timezone.make_aware(parsed_time)

            m = Meeting.objects.create(
                title=title,
                host_teacher=teacher,
                branch=branch,
                semester=semester,
                subject=subject,
                scheduled_at=parsed_time,
                duration_minutes=duration,
                meeting_link=link,
                description=desc,
                status=Meeting.Status.SCHEDULED
            )
            m.refresh_from_db()

            # Automatically dispatch notifications to all eligible students
            students = User.objects.filter(
                role=Role.STUDENT.value,
                student_profile__branch=branch,
                student_profile__semester=semester
            )
            meeting_disp = m.scheduled_at.strftime('%b %d at %I:%M %p') if hasattr(m.scheduled_at, 'strftime') else str(m.scheduled_at)
            for s in students:
                PlatformNotification.objects.create(
                    recipient=s,
                    title=f"Live Class Scheduled: {title}",
                    message=f"Prof. {teacher.full_name} scheduled a lecture on {meeting_disp}.",
                    notification_type=PlatformNotification.NotificationType.MEETING,
                    link=m.meeting_link
                )

            audit.record(request, "teacher_meeting_scheduled", meeting_id=m.pk, title=title)
            messages.success(request, f"Meeting '{title}' scheduled! Notified {students.count()} eligible students.")
            return redirect("teacher_meetings")

    branches = AcademicBranch.objects.filter(is_archived=False)
    subjects = Subject.objects.all().order_by("branch", "semester", "code")

    context = {
        "branches": branches,
        "subjects": subjects,
    }
    return render(request, "dashboards/teacher_meeting_form.html", context)


# ==============================================================================
# 5. TEACHER LEARNING RESOURCE MANAGEMENT
# ==============================================================================

@role_required(Role.TEACHER)
def teacher_resources(request):
    """View and manage authorized educational resources."""
    teacher = request.user
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete_resource":
            rid = request.POST.get("resource_id")
            r = get_object_or_404(LearningResource, pk=rid, author=teacher)
            title = r.title
            r.delete()
            audit.record(request, "teacher_resource_deleted", resource_id=rid, title=title)
            messages.success(request, f"Resource '{title}' deleted.")
            return redirect("teacher_resources")

        elif action == "add_resource":
            title = request.POST.get("title", "").strip()
            branch = request.POST.get("branch", "CSE")
            semester = int(request.POST.get("semester", 3))
            subject_id = request.POST.get("subject_id")
            subject = Subject.objects.filter(pk=subject_id).first() if subject_id else None
            r_type = request.POST.get("resource_type", "pdf")
            ext_url = request.POST.get("external_url", "").strip()
            topic = request.POST.get("topic", "").strip()
            desc = request.POST.get("description", "").strip()
            res_file = request.FILES.get("file")

            if title and branch:
                lr = LearningResource.objects.create(
                    title=title,
                    branch=branch,
                    semester=semester,
                    subject=subject,
                    resource_type=r_type,
                    external_url=ext_url,
                    file=res_file,
                    topic=topic,
                    description=desc,
                    author=teacher,
                    status=LearningResource.Status.PUBLISHED
                )

                # Send notifications to students in that branch & semester
                students = User.objects.filter(
                    role=Role.STUDENT.value,
                    student_profile__branch=branch,
                    student_profile__semester=semester
                )
                for s in students:
                    PlatformNotification.objects.create(
                        recipient=s,
                        title=f"New Study Material: {title}",
                        message=f"Prof. {teacher.full_name} published a new {lr.get_resource_type_display()} for your class.",
                        notification_type=PlatformNotification.NotificationType.RESOURCE,
                        link="/student/resources/"
                    )

                audit.record(request, "teacher_resource_added", resource_id=lr.pk, title=title)
                messages.success(request, f"Resource '{title}' published.")
                return redirect("teacher_resources")

    resources = LearningResource.objects.filter(author=teacher).order_by("-created_at")
    branches = AcademicBranch.objects.filter(is_archived=False)
    subjects = Subject.objects.all().order_by("branch", "semester", "code")

    context = {
        "resources": resources,
        "branches": branches,
        "subjects": subjects,
    }
    return render(request, "dashboards/teacher_resources.html", context)


# ==============================================================================
# 6. EDUBRIDGE TEACHER AI ASSISTANT API
# ==============================================================================

@role_required(Role.TEACHER)
@require_POST
def teacher_ai_api(request):
    """Teacher AI analytical query endpoint."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        prompt = body.get("prompt", "").strip()
        history = body.get("history", [])
    except Exception:
        prompt = request.POST.get("prompt", "").strip()
        history = []

    if not prompt:
        return JsonResponse({"error": "Prompt cannot be empty.", "status": "error"}, status=400)

    result = process_teacher_ai_query(prompt, request.user, history=history)
    audit.record(request, "teacher_ai_query_executed", prompt_sample=prompt[:80], topic=result.get("topic"))

    return JsonResponse({
        "status": "success",
        "assistant_name": result.get("assistant_name", "EduBridge Teacher AI Assistant"),
        "reply": result["reply"],
        "topic": result.get("topic"),
        "records_found": result.get("records_found", 0),
        "provider": result.get("provider", "EduBridge Neural Reasoning Engine"),
        "timestamp": timezone.now().isoformat(),
    })


# ==============================================================================
# 7. TEACHER ANALYTICS DASHBOARD & TELEMETRY API
# ==============================================================================

@role_required(Role.TEACHER)
def teacher_analytics(request):
    """Teacher Analytics with dual modes: My Teaching Analytics & Student Analytics."""
    from dashboards.analytics_service import (
        get_teacher_teaching_analytics,
        get_teacher_all_students_analytics,
        get_teacher_individual_student_analytics,
    )
    teacher = request.user
    mode = request.GET.get("mode", "teaching")
    range_key = request.GET.get("range", "30d")
    student_id = request.GET.get("student_id", "").strip()

    teaching_data = get_teacher_teaching_analytics(teacher, range_key=range_key)
    all_students_data = get_teacher_all_students_analytics(teacher, date_range=range_key)

    individual_data = None
    search_error = None
    if student_id:
        res = get_teacher_individual_student_analytics(teacher, student_id)
        if res.get("success"):
            individual_data = res
        else:
            search_error = res.get("message")

    context = {
        "mode": mode,
        "range": range_key,
        "teaching_analytics": teaching_data,
        "all_students_analytics": all_students_data,
        "individual_analytics": individual_data,
        "search_error": search_error,
        "student_id": student_id,
    }
    return render(request, "dashboards/teacher_analytics.html", context)


@role_required(Role.TEACHER)
def teacher_analytics_api(request):
    """Dynamic JSON endpoint for teacher analytics (My Teaching, All Students, or Individual Student search)."""
    from dashboards.analytics_service import (
        get_teacher_teaching_analytics,
        get_teacher_all_students_analytics,
        get_teacher_individual_student_analytics,
    )
    teacher = request.user
    mode = request.GET.get("mode", "teaching")
    range_key = request.GET.get("range", "30d")
    student_id = request.GET.get("student_id", "").strip()
    branch = request.GET.get("branch", "")
    semester = request.GET.get("semester", "")

    if mode == "student" and student_id:
        res = get_teacher_individual_student_analytics(teacher, student_id)
        if res.get("error") == "unauthorized":
            return JsonResponse({"status": "error", "message": res.get("message")}, status=403)
        elif res.get("error") == "not_found":
            return JsonResponse({"status": "error", "message": res.get("message")}, status=404)
        return JsonResponse({"status": "success", "data": res})

    elif mode == "all_students":
        data = get_teacher_all_students_analytics(
            teacher, branch=branch, semester=semester, date_range=range_key
        )
        return JsonResponse({"status": "success", "data": data})

    else:
        # Default: Mode A (My Teaching)
        data = get_teacher_teaching_analytics(teacher, range_key=range_key)
        return JsonResponse({"status": "success", "data": data})


# ==============================================================================
# TEACHER CODING & DSA QUESTION MANAGEMENT
# ==============================================================================

@role_required(Role.TEACHER)
def teacher_coding(request):
    """Teacher Coding and DSA Question Management workspace."""
    from dashboards.coding_service import (
        get_teacher_coding_overview,
        get_teacher_individual_student_coding,
        get_coding_resources_for_management,
        seed_standard_coding_resources,
    )
    from dashboards.models import CodingResource, DSATopic

    seed_standard_coding_resources()
    teacher = request.user
    student_id = request.GET.get("student_id", "").strip()
    status_filter = request.GET.get("status", "all")
    type_filter = request.GET.get("type", "all")
    search_query = request.GET.get("q", "").strip()

    overview = get_teacher_coding_overview(teacher)
    coding_resources = get_coding_resources_for_management(
        teacher,
        status_filter=status_filter,
        type_filter=type_filter,
        search=search_query
    )

    individual_result = None
    search_error = None
    if student_id:
        res = get_teacher_individual_student_coding(teacher, student_id)
        if res.get("success"):
            individual_result = res
        else:
            search_error = res.get("message")

    # Categories list according to Section 2 Area A
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
    return render(request, "dashboards/teacher_coding.html", context)



@role_required(Role.TEACHER)
@require_POST
def teacher_dsa_create_api(request):
    """Faculty endpoint to create and publish a new DSA curriculum question."""
    from dashboards.models import DSAQuestion

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    title = data.get("title", "").strip()
    topic = data.get("topic", "").strip()
    difficulty = data.get("difficulty", "Medium").strip()
    problem_statement = data.get("problem_statement", "").strip()
    input_format = data.get("input_format", "").strip()
    output_format = data.get("output_format", "").strip()
    constraints = data.get("constraints", "").strip()
    sample_input = data.get("sample_input", "").strip()
    sample_output = data.get("sample_output", "").strip()
    explanation = data.get("explanation", "").strip()
    branch = data.get("branch", "CSE").strip()
    semester = int(data.get("semester", 3))

    # Supported languages
    supported_langs = data.get("supported_languages", ["python", "java", "c"])
    if isinstance(supported_langs, str):
        supported_langs = [s.strip().lower() for s in supported_langs.split(",") if s.strip()]

    # Test cases
    public_cases = data.get("public_test_cases", [])
    if isinstance(public_cases, str):
        try:
            public_cases = json.loads(public_cases)
        except Exception:
            public_cases = []

    hidden_cases = data.get("hidden_test_cases", [])
    if isinstance(hidden_cases, str):
        try:
            hidden_cases = json.loads(hidden_cases)
        except Exception:
            hidden_cases = []

    # If test cases empty, create from sample input/output
    if not public_cases and sample_input:
        public_cases = [{"input": sample_input, "output": sample_output, "explanation": "Sample test case"}]

    starter_code = data.get("starter_code", {})
    if isinstance(starter_code, str):
        try:
            starter_code = json.loads(starter_code)
        except Exception:
            starter_code = {"python": starter_code}

    if not title or not problem_statement or not topic:
        return JsonResponse({"status": "error", "message": "Title, topic, and problem statement are required fields."}, status=400)

    question = DSAQuestion.objects.create(
        title=title,
        topic=topic,
        difficulty=difficulty,
        branch=branch,
        semester=semester,
        created_by=request.user,
        problem_statement=problem_statement,
        input_format=input_format,
        output_format=output_format,
        constraints=constraints,
        sample_input=sample_input,
        sample_output=sample_output,
        explanation=explanation,
        supported_languages=supported_langs,
        starter_code=starter_code,
        public_test_cases=public_cases,
        hidden_test_cases=hidden_cases,
        status="published"
    )

    audit.record(
        request,
        "teacher_dsa_question_published",
        question_id=question.id,
        question_title=question.title,
        topic=question.topic
    )

    return JsonResponse({
        "status": "success",
        "message": f"DSA Question '{question.title}' published successfully to curriculum.",
        "question_id": question.id,
    })


@role_required(Role.TEACHER)
def teacher_coding_analytics_api(request):
    """Dynamic JSON API for Teacher coding analytics (Individual student or Cohort overview)."""
    from dashboards.coding_service import (
        get_teacher_coding_overview,
        get_teacher_individual_student_coding,
    )

    mode = request.GET.get("mode", "cohort")
    student_id = request.GET.get("student_id", "").strip()

    if mode == "student" and student_id:
        res = get_teacher_individual_student_coding(request.user, student_id)
        if res.get("error") == "unauthorized":
            return JsonResponse({"status": "error", "message": res.get("message")}, status=403)
        elif res.get("error") == "not_found":
            return JsonResponse({"status": "error", "message": res.get("message")}, status=404)
        return JsonResponse({"status": "success", "data": res})

    overview = get_teacher_coding_overview(request.user)
    return JsonResponse({"status": "success", "data": overview})


@role_required(Role.TEACHER)
@require_POST
def teacher_coding_resource_save(request):
    """Faculty endpoint to create or edit a CodingResource."""
    from dashboards.coding_service import save_coding_resource
    from django.contrib import messages

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
    return redirect("teacher_coding")


@role_required(Role.TEACHER)
@require_POST
def teacher_coding_resource_toggle_status(request, pk):
    """Faculty endpoint to toggle publication status."""
    from dashboards.coding_service import toggle_coding_resource_status
    result = toggle_coding_resource_status(request.user, pk)
    if result["success"]:
        return JsonResponse({"status": "success", **result})
    return JsonResponse({"status": "error", "message": result["message"]}, status=400)


@role_required(Role.TEACHER)
@require_POST
def teacher_coding_resource_delete(request, pk):
    """Faculty endpoint to archive/delete a coding resource."""
    from dashboards.coding_service import delete_or_archive_coding_resource
    result = delete_or_archive_coding_resource(request.user, pk)
    if result["success"]:
        return JsonResponse({"status": "success", "message": result["message"]})
    return JsonResponse({"status": "error", "message": result["message"]}, status=400)


@role_required(Role.TEACHER)
def teacher_attendance(request):
    """Teacher Attendance roster view & management."""
    from datetime import datetime
    from dashboards.attendance_service import get_teacher_attendance_roster

    subject_id_raw = request.GET.get("subject_id")
    subject_id = int(subject_id_raw) if subject_id_raw and subject_id_raw.isdigit() else None

    date_str = request.GET.get("date", "")
    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = None

    roster_data = get_teacher_attendance_roster(request.user, subject_id=subject_id, session_date=target_date)

    context = {
        **roster_data,
        "date_str": roster_data["target_date"].strftime("%Y-%m-%d"),
    }
    return render(request, "dashboards/teacher_attendance.html", context)


@role_required(Role.TEACHER)
@require_POST
def teacher_attendance_mark_api(request):
    """Teacher endpoint to record or update student attendance for a class session."""
    from datetime import datetime
    from dashboards.attendance_service import update_attendance_record
    from dashboards.models import AttendanceRecord

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    action = data.get("action", "mark_single")
    subject_id = data.get("subject_id")
    subject_id = int(subject_id) if subject_id else None

    date_str = data.get("date", "")
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.now().date()
    except ValueError:
        target_date = timezone.now().date()

    session_title = data.get("session_title", "Lecture Session").strip() or "Lecture Session"
    session_type = data.get("session_type", AttendanceRecord.SessionType.CLASS)

    if action == "mark_all_present":
        student_ids = data.get("student_ids", [])
        updated = 0
        for sid in student_ids:
            try:
                update_attendance_record(
                    student_id=int(sid),
                    subject_id=subject_id,
                    target_date=target_date,
                    status=AttendanceRecord.Status.PRESENT,
                    recorded_by=request.user,
                    session_title=session_title,
                    session_type=session_type,
                    remarks="Bulk marked present by faculty"
                )
                updated += 1
            except Exception:
                continue
        return JsonResponse({"status": "success", "message": f"Successfully marked {updated} students present."})

    # Single student mark
    student_id = data.get("student_id")
    status = data.get("status", AttendanceRecord.Status.PRESENT)
    remarks = data.get("remarks", "").strip()

    if not student_id:
        return JsonResponse({"status": "error", "message": "student_id is required."}, status=400)

    try:
        rec = update_attendance_record(
            student_id=int(student_id),
            subject_id=subject_id,
            target_date=target_date,
            status=status,
            recorded_by=request.user,
            session_title=session_title,
            session_type=session_type,
            remarks=remarks
        )
        return JsonResponse({
            "status": "success",
            "message": f"Attendance updated to {rec.get_status_display()}.",
            "record_id": rec.id,
            "status_val": rec.status
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)




