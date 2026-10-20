"""EduBridge Analytics & Aggregation Engine.

Provides server-authoritative analytics calculations directly from the database for:
1. Students (Personal academic analytics, subject diagnostics, learning time)
2. Teachers (Teaching workload, authorized student cohort diagnostics, individual student search)
3. Administrators (Institution-wide telemetry, authorized student & teacher search, academic trends)
"""
from datetime import timedelta
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from accounts.constants import Role
from accounts.models import AuditEvent, StudentProfile, TeacherProfile, User
from dashboards.models import (
    AcademicBranch,
    Assessment,
    AssessmentAttempt,
    CodingSubmission,
    DSAQuestion,
    LearningResource,
    Meeting,
    Scholarship,
    Subject,
)


def _parse_date_cutoff(range_key: str):
    """Return a timezone-aware datetime cutoff based on range string."""
    now = timezone.now()
    if range_key == "7d":
        return now - timedelta(days=7)
    elif range_key == "30d":
        return now - timedelta(days=30)
    elif range_key == "90d":
        return now - timedelta(days=90)
    elif range_key == "365d":
        return now - timedelta(days=365)
    return None  # All time


def get_student_enrolled_subjects(student):
    """Authoritative course enrollment resolution for a student.
    
    Returns all subjects the student is legitimately enrolled in:
    1. Explicit M2M enrollments (Subject.enrolled_students)
    2. Branch + semester curriculum cohort match
    3. Subjects where the student has taken/submitted assessments or attended sessions
    4. If still empty, all branch curriculum subjects for student's branch
    """
    profile = getattr(student, "student_profile", None)
    branch = profile.branch if profile else "CSE"
    semester = profile.semester if profile else 1

    # 1. Explicit M2M enrollments
    explicit_ids = set(student.enrolled_subjects.values_list("id", flat=True))

    # 2. Branch + semester curriculum cohort match
    cohort_ids = set(Subject.objects.filter(branch=branch, semester=semester).values_list("id", flat=True))

    # 3. Assessment attempts and attendance activity
    activity_ids = set(
        AssessmentAttempt.objects.filter(student=student, assessment__subject__isnull=False)
        .values_list("assessment__subject_id", flat=True)
    )

    combined_ids = explicit_ids.union(cohort_ids).union(activity_ids)

    # 4. If still empty (e.g. transitional semester), fall back to all branch curriculum subjects
    if not combined_ids:
        combined_ids = set(Subject.objects.filter(branch=branch).values_list("id", flat=True))

    return Subject.objects.filter(id__in=combined_ids).order_by("code")



# ==============================================================================
# 1. STUDENT PERSONAL ANALYTICS
# ==============================================================================

def get_student_personal_analytics(student, subject_id=None, range_key="30d", view_mode="daily", assessment_type="all"):
    """Compute strictly isolated personal analytics for the authenticated student."""
    now = timezone.now()
    profile = getattr(student, "student_profile", None)
    branch = profile.branch if profile else "CSE"
    semester = profile.semester if profile else 1

    date_cutoff = _parse_date_cutoff(range_key)

    # 1. Enrolled Subjects (authoritatively resolved: 4 courses for CSE)
    enrolled_subjects = get_student_enrolled_subjects(student)
    selected_subject = None
    if subject_id:
        selected_subject = enrolled_subjects.filter(pk=subject_id).first()

    # 2. Base Assessments Query
    assessments_qs = Assessment.objects.filter(
        Q(subject__in=enrolled_subjects) | Q(branch=branch, semester=semester) | Q(target_students=student),
        status__in=[Assessment.Status.PUBLISHED, Assessment.Status.SCHEDULED]
    ).distinct()

    if selected_subject:
        assessments_qs = assessments_qs.filter(subject=selected_subject)
    if assessment_type in [Assessment.AssessmentType.DAILY_ASSIGNMENT, Assessment.AssessmentType.WEEKLY_TEST]:
        assessments_qs = assessments_qs.filter(assessment_type=assessment_type)

    total_published_assessments = assessments_qs.count()

    # 3. Student's Attempts Query
    attempts_qs = AssessmentAttempt.objects.filter(
        student=student,
        assessment__in=assessments_qs
    ).select_related("assessment__subject")

    if date_cutoff:
        attempts_qs = attempts_qs.filter(started_at__gte=date_cutoff)

    completed_attempts = attempts_qs.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED)
    completed_count = completed_attempts.count()
    pending_count = max(0, total_published_assessments - completed_count)

    # Average score & GPA calculation
    avg_score = 0.0
    avg_score_pct = 0.0
    if completed_attempts.exists():
        total_earned = sum(a.score for a in completed_attempts)
        total_possible = sum(a.assessment.total_marks for a in completed_attempts)
        avg_score = round(total_earned / completed_count, 1)
        if total_possible > 0:
            avg_score_pct = round((total_earned / total_possible) * 100, 1)
        else:
            avg_score_pct = avg_score

    # GPA / Letter Grade estimation based on actual scores
    if avg_score_pct >= 90:
        grade = "A+"
        gpa = 9.8
    elif avg_score_pct >= 80:
        grade = "A"
        gpa = 8.7
    elif avg_score_pct >= 70:
        grade = "B+"
        gpa = 7.6
    elif avg_score_pct >= 60:
        grade = "B"
        gpa = 6.8
    elif avg_score_pct >= 50:
        grade = "C"
        gpa = 5.8
    elif completed_count > 0:
        grade = "D"
        gpa = 4.5
    else:
        grade = "N/A"
        gpa = 0.0

    # 4. Active Learning Time (from verified assessment session duration)
    total_learning_seconds = 0
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    daily_learning_seconds = 0
    weekly_learning_seconds = 0

    attempt_dates = set()
    for att in completed_attempts:
        if att.submitted_at and att.started_at:
            delta = (att.submitted_at - att.started_at).total_seconds()
            # Clip between 30 seconds and maximum assessment duration
            max_secs = (att.assessment.duration_minutes or 45) * 60
            secs = max(30, min(delta, max_secs))
            total_learning_seconds += secs
            if att.started_at >= today_start:
                daily_learning_seconds += secs
            if att.started_at >= week_start:
                weekly_learning_seconds += secs
            attempt_dates.add(att.started_at.date())

    total_learning_hours = round(total_learning_seconds / 3600, 1)
    daily_learning_minutes = round(daily_learning_seconds / 60)
    weekly_learning_hours = round(weekly_learning_seconds / 3600, 1)

    # 5. Learning Streak (consecutive days with activity leading to today or yesterday)
    streak_days = 0
    check_date = now.date()
    if check_date not in attempt_dates:
        check_date = check_date - timedelta(days=1)
    while check_date in attempt_dates:
        streak_days += 1
        check_date -= timedelta(days=1)

    # 6. Upcoming deadlines
    upcoming_deadlines_count = assessments_qs.filter(
        deadline__gte=now
    ).exclude(
        attempts__student=student,
        attempts__status=AssessmentAttempt.AttemptStatus.COMPLETED
    ).count()

    # 7. Subject Completion Percentage
    completion_rate = round((completed_count / total_published_assessments * 100), 1) if total_published_assessments else 0.0

    # 8. Subject-wise breakdown for all enrolled subjects
    subject_analytics = []
    subject_bar_labels = []
    subject_bar_scores = []
    subject_bar_completions = []
    subject_bar_titles = []

    for subj in enrolled_subjects:
        subj_assessments = Assessment.objects.filter(
            subject=subj,
            status__in=[Assessment.Status.PUBLISHED, Assessment.Status.SCHEDULED]
        )
        subj_total = subj_assessments.count()
        subj_attempts = AssessmentAttempt.objects.filter(
            student=student,
            assessment__in=subj_assessments,
            status=AssessmentAttempt.AttemptStatus.COMPLETED
        )
        subj_completed = subj_attempts.count()
        subj_avg = round(subj_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)
        subj_time_mins = 0
        for att in subj_attempts:
            if att.submitted_at and att.started_at:
                delta = max(30, min((att.submitted_at - att.started_at).total_seconds(), (att.assessment.duration_minutes or 45) * 60))
                subj_time_mins += delta / 60
        subj_time_hrs = round(subj_time_mins / 60, 1)
        subj_completion_pct = round((subj_completed / subj_total * 100), 1) if subj_total else 0.0

        # Proficiency rating
        if subj_completed == 0:
            status_text = "Not Started"
            badge = "pending"
        elif subj_avg >= 75:
            status_text = "Mastered"
            badge = "active"
        elif subj_avg >= 50:
            status_text = "In Progress"
            badge = "info"
        else:
            status_text = "Needs Practice"
            badge = "alert"

        subject_analytics.append({
            "id": subj.id,
            "code": subj.code,
            "title": subj.title,
            "credits": float(subj.credits),
            "total_assessments": subj_total,
            "completed_assessments": subj_completed,
            "pending_assessments": max(0, subj_total - subj_completed),
            "completion_rate": subj_completion_pct,
            "average_score": subj_avg,
            "learning_hours": subj_time_hrs,
            "status_text": status_text,
            "badge": badge,
        })

        subject_bar_labels.append(subj.code)
        subject_bar_titles.append(subj.title)
        subject_bar_scores.append(subj_avg)
        subject_bar_completions.append(subj_completion_pct)

    # 9. Performance & Activity Trends Over Time (Daily / Weekly intervals)
    trend_labels = []
    trend_scores = []
    activity_minutes = []
    trend_days = 7 if range_key == "7d" else (30 if range_key == "30d" else 14)

    for i in range(trend_days - 1, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        label = day_date.strftime("%d %b")
        trend_labels.append(label)

        day_attempts = completed_attempts.filter(started_at__date=day_date)
        if day_attempts.exists():
            day_avg = round(day_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)
            day_mins = sum(
                max(30, min((att.submitted_at - att.started_at).total_seconds(), (att.assessment.duration_minutes or 45) * 60))
                for att in day_attempts if att.submitted_at and att.started_at
            ) / 60
        else:
            day_avg = 0.0
            day_mins = 0.0

        trend_scores.append(day_avg)
        activity_minutes.append(round(day_mins))

    # 10. Assessment Score Distribution Bands
    score_distribution = {
        "labels": ["≥85% (Excellent)", "70–84% (Good)", "50–69% (Average)", "<50% (Needs Work)"],
        "counts": [
            completed_attempts.filter(score__gte=85).count(),
            completed_attempts.filter(score__gte=70, score__lt=85).count(),
            completed_attempts.filter(score__gte=50, score__lt=70).count(),
            completed_attempts.filter(score__lt=50).count(),
        ]
    }

    # 11. Coding Submissions & Practice Analytics for this Student
    student_coding_subs = CodingSubmission.objects.filter(student=student)
    coding_attempted_q_ids = set(student_coding_subs.filter(question__isnull=False).values_list("question_id", flat=True))
    coding_solved_q_ids = set(
        student_coding_subs.filter(question__isnull=False, status=CodingSubmission.SubmissionStatus.ACCEPTED)
        .values_list("question_id", flat=True)
    )
    total_assigned_dsa = DSAQuestion.objects.filter(status="published").count()

    coding_stats = {
        "assigned_questions": total_assigned_dsa,
        "attempted_questions": len(coding_attempted_q_ids),
        "solved_questions": len(coding_solved_q_ids),
        "pending_questions": max(0, total_assigned_dsa - len(coding_solved_q_ids)),
        "acceptance_rate": round((len(coding_solved_q_ids) / len(coding_attempted_q_ids) * 100), 1) if coding_attempted_q_ids else 0.0,
        "total_submissions": student_coding_subs.count(),
    }

    # 12. Evidence-Based Academic Improvement Recommendations
    suggestions = []
    # A. Low-scoring subjects
    for s in subject_analytics:
        if s["completed_assessments"] > 0 and s["average_score"] < 60:
            suggestions.append({
                "subject": s["title"],
                "code": s["code"],
                "priority": "High",
                "evidence": f"Average score is {s['average_score']}% across {s['completed_assessments']} evaluated tasks.",
                "action": f"Review fundamental lecture materials for {s['title']} and attempt practice exercises.",
                "metric": f"{s['average_score']}% Avg"
            })

    # B. Unattempted subjects
    for s in subject_analytics:
        if s["completed_assessments"] == 0 and s["total_assessments"] > 0:
            suggestions.append({
                "subject": s["title"],
                "code": s["code"],
                "priority": "Medium",
                "evidence": f"{s['total_assessments']} assigned course tests remain unattempted.",
                "action": f"Start with the introductory assignment in {s['code']} to establish academic benchmark progress.",
                "metric": f"{s['pending_assessments']} Pending"
            })

    # C. Study consistency
    if total_learning_hours < 2.0 and completed_count > 0:
        suggestions.append({
            "subject": "Learning Consistency",
            "code": "TIME",
            "priority": "Medium",
            "evidence": f"Total active learning time recorded is {total_learning_hours}h across the evaluated timeframe.",
            "action": "Maintain regular 30-45 minute daily study sessions to solidify algorithmic and conceptual mastery.",
            "metric": f"{total_learning_hours}h"
        })

    # D. Attendance & Engagement Warning / Advice
    from dashboards.attendance_service import get_student_attendance_summary
    att_summary = get_student_attendance_summary(student)
    if att_summary["total_sessions"] > 0 and att_summary["attendance_numeric"] < 75.0:
        suggestions.append({
            "subject": "Class Attendance & Engagement",
            "code": "ATTEND",
            "priority": "High",
            "evidence": f"Recorded attendance is {att_summary['attendance_numeric']}% with {att_summary['absent_count']} absences across {att_summary['total_sessions']} sessions.",
            "action": "Attend all upcoming scheduled classes and labs to maintain institutional examination eligibility (≥75%).",
            "metric": f"{att_summary['attendance_numeric']}% Attended"
        })

    # E. Positive reinforcement fallback
    if not suggestions:
        suggestions.append({
            "subject": "Academic Standing",
            "code": "STATUS",
            "priority": "Low",
            "evidence": f"Consistent performance with {avg_score_pct}% average across active subjects.",
            "action": "Maintain your steady pace and explore external algorithmic challenges in the Coding Hub.",
            "metric": f"Grade {grade}"
        })

    return {
        "student": {
            "public_id": student.public_id,
            "full_name": student.full_name,
            "username": student.username,
            "branch": branch,
            "semester": semester,
        },
        "overview": {
            "total_enrolled_subjects": enrolled_subjects.count(),
            "overall_performance_pct": avg_score_pct,
            "average_marks": avg_score,
            "grade": grade,
            "gpa": gpa,
            "completion_percentage": completion_rate,
            "total_learning_hours": total_learning_hours,
            "daily_learning_minutes": daily_learning_minutes,
            "weekly_learning_hours": weekly_learning_hours,
            "attendance_percentage": att_summary["attendance_percentage"],
            "attendance_numeric": att_summary["attendance_numeric"],
            "attendance_note": att_summary["attendance_note"],
            "attendance_summary": att_summary,
            "completed_assignments": completed_count,
            "pending_assignments": pending_count,
            "upcoming_deadlines": upcoming_deadlines_count,
            "learning_streak_days": streak_days,
            "learning_goal_progress_pct": min(100.0, round((completed_count / max(5, total_published_assessments)) * 100, 1)),
        },
        "selected_subject_id": selected_subject.id if selected_subject else None,
        "selected_subject_name": selected_subject.title if selected_subject else "All Subjects",
        "subjects": subject_analytics,
        "charts": {
            "subject_bars": {
                "labels": subject_bar_labels,
                "titles": subject_bar_titles,
                "scores": subject_bar_scores,
                "completions": subject_bar_completions,
            },
            "performance_line": {
                "labels": trend_labels,
                "scores": trend_scores,
            },
            "activity_area": {
                "labels": trend_labels,
                "minutes": activity_minutes,
            },
            "progress_donut": {
                "completed": completed_count,
                "pending": pending_count,
                "total": total_published_assessments,
            },
            "attendance_chart": {
                "present": att_summary["present_count"],
                "absent": att_summary["absent_count"],
                "late": att_summary["late_count"],
                "total": att_summary["total_sessions"],
                "rate": att_summary["attendance_numeric"],
            },
            "score_distribution": score_distribution,
        },
        "trends": {
            "labels": trend_labels,
            "scores": trend_scores,
            "activity_minutes": activity_minutes,
        },
        "coding": coding_stats,
        "suggestions": suggestions,
    }



# ==============================================================================
# 2. TEACHER ANALYTICS (MODE A & MODE B)
# ==============================================================================

def get_teacher_teaching_analytics(teacher, range_key="30d"):
    """Mode A: Scoped strictly to the authenticated teacher's own teaching activities."""
    now = timezone.now()
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    date_cutoff = _parse_date_cutoff(range_key)

    # Authorized teaching scope
    assigned_subjects = teacher.assigned_subjects.all().order_by("code")
    assigned_branches = list(set(assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    # Student population in teacher's scope
    students_in_scope = User.objects.filter(
        role=Role.STUDENT.value,
        student_profile__branch__in=assigned_branches
    )
    total_students_taught = students_in_scope.count()

    # Assessments created by this faculty
    created_assessments_qs = Assessment.objects.filter(created_by=teacher)
    if date_cutoff:
        created_assessments_qs = created_assessments_qs.filter(created_at__gte=date_cutoff)

    total_assignments_created = created_assessments_qs.count()

    # Attempts submitted to this teacher's assessments
    attempts_qs = AssessmentAttempt.objects.filter(
        assessment__created_by=teacher
    ).select_related("assessment__subject", "student")

    if date_cutoff:
        attempts_qs = attempts_qs.filter(started_at__gte=date_cutoff)

    evaluated_attempts = attempts_qs.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED)
    evaluated_count = evaluated_attempts.count()
    pending_evaluations = attempts_qs.filter(status=AssessmentAttempt.AttemptStatus.IN_PROGRESS).count()

    # Potential submissions vs actual
    expected_submissions = total_students_taught * total_assignments_created
    completion_rate = round((evaluated_count / expected_submissions * 100), 1) if expected_submissions else 0.0

    # Overall class performance across teacher's tests
    avg_score = round(evaluated_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)

    # Class-wise & Subject-wise breakdown
    subject_breakdown = []
    for s in assigned_subjects:
        s_assessments = Assessment.objects.filter(created_by=teacher, subject=s)
        s_attempts = AssessmentAttempt.objects.filter(
            assessment__in=s_assessments,
            status=AssessmentAttempt.AttemptStatus.COMPLETED
        )
        s_avg = round(s_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)
        subject_breakdown.append({
            "code": s.code,
            "title": s.title,
            "branch": s.branch,
            "semester": s.semester,
            "assessments_count": s_assessments.count(),
            "submissions_count": s_attempts.count(),
            "average_score": s_avg,
        })

    # Teaching activity over time (7-day / 30-day velocity)
    trend_days = 7 if range_key == "7d" else 14
    activity_labels = []
    submissions_trend = []
    meetings_trend = []
    attendance_trend = []

    # Real Attendance telemetry for teacher's scope
    from dashboards.models import AttendanceRecord
    t_att_qs = AttendanceRecord.objects.filter(
        Q(subject__in=assigned_subjects) | Q(recorded_by=teacher) | Q(student__student_profile__branch=dept)
    ).exclude(session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN)
    if date_cutoff:
        t_att_qs = t_att_qs.filter(date__gte=date_cutoff.date())
    t_total_att = t_att_qs.count()
    t_present = t_att_qs.filter(status=AttendanceRecord.Status.PRESENT).count()
    t_late = t_att_qs.filter(status=AttendanceRecord.Status.LATE).count()
    t_absent = t_att_qs.filter(status=AttendanceRecord.Status.ABSENT).count()
    if t_total_att > 0:
        t_att_rate = round(((t_present + 0.5 * t_late) / t_total_att) * 100, 1)
        t_att_pct_str = f"{t_att_rate}%"
        t_att_note = f"{t_present} present, {t_absent} absent across {t_total_att} sessions"
    else:
        t_att_rate = 0.0
        t_att_pct_str = "N/A"
        t_att_note = "No class attendance recorded yet"

    for i in range(trend_days - 1, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        activity_labels.append(day_date.strftime("%d %b"))
        sub_count = attempts_qs.filter(started_at__date=day_date).count()
        meet_count = Meeting.objects.filter(host_teacher=teacher, scheduled_at__date=day_date).count()
        att_day_count = t_att_qs.filter(date=day_date, status=AttendanceRecord.Status.PRESENT).count()
        submissions_trend.append(sub_count)
        meetings_trend.append(meet_count)
        attendance_trend.append(att_day_count)

    # Support areas: subjects with low average score
    support_needed_areas = [s for s in subject_breakdown if s["submissions_count"] > 0 and s["average_score"] < 60]

    return {
        "teacher": {
            "public_id": teacher.public_id,
            "full_name": teacher.full_name,
            "department": dept,
            "designation": profile.designation if profile else "Faculty",
        },
        "overview": {
            "total_assigned_classes": len(assigned_branches),
            "total_assigned_subjects": assigned_subjects.count(),
            "total_students_taught": total_students_taught,
            "assignments_created": total_assignments_created,
            "assignments_evaluated": evaluated_count,
            "pending_evaluations": pending_evaluations,
            "assignment_completion_rate": completion_rate,
            "class_average_score": avg_score,
            "attendance_percentage": t_att_pct_str,
            "attendance_numeric": t_att_rate,
            "attendance_note": t_att_note,
            "meetings_hosted": Meeting.objects.filter(host_teacher=teacher).count(),
            "resources_authored": LearningResource.objects.filter(author=teacher).count(),
        },
        "subject_breakdown": subject_breakdown,
        "support_needed_areas": support_needed_areas,
        "trends": {
            "labels": activity_labels,
            "submissions": submissions_trend,
            "meetings": meetings_trend,
            "attendance": attendance_trend,
        }
    }


def get_teacher_individual_student_analytics(teacher, student_public_id):
    """Mode B, Option 1: Detailed individual student analytics with strict authorization check."""
    # 1. Verify student exists
    student = User.objects.filter(public_id__iexact=student_public_id.strip(), role=Role.STUDENT.value).first()
    if not student:
        return {"error": "not_found", "message": f"Student with ID '{student_public_id}' was not found in the institution."}

    # 2. Check authorization: Student must be in teacher's assigned branches/subjects or attempted teacher's assessment
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    assigned_branches = list(set(teacher.assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    s_profile = getattr(student, "student_profile", None)
    student_branch = s_profile.branch if s_profile else None

    has_attempted_teacher_assessment = AssessmentAttempt.objects.filter(
        student=student, assessment__created_by=teacher
    ).exists()

    is_authorized = (student_branch in assigned_branches) or has_attempted_teacher_assessment
    if not is_authorized:
        return {
            "error": "unauthorized",
            "message": f"Access Denied: Student {student.public_id} is in {student_branch} and is not in your authorized department or course groups."
        }

    # 3. Compile authorized student analytics
    student_analytics = get_student_personal_analytics(student, range_key="all")
    return {
        "success": True,
        "student_id": student.public_id,
        "student_name": student.full_name,
        "student_branch": student_branch,
        "student_semester": s_profile.semester if s_profile else 1,
        "analytics": student_analytics,
    }


def get_teacher_all_students_analytics(teacher, branch=None, semester=None, date_range="30d"):
    """Mode B, Option 2: Aggregate analytics across all students in teacher's authorized scope."""
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    assigned_branches = list(set(teacher.assigned_subjects.values_list("branch", flat=True)))
    if not assigned_branches:
        assigned_branches = [dept] if dept else ["CSE"]

    # Filter students strictly in teacher's authorized branches
    students_qs = User.objects.filter(
        role=Role.STUDENT.value,
        student_profile__branch__in=assigned_branches
    ).select_related("student_profile")

    if branch and branch in assigned_branches:
        students_qs = students_qs.filter(student_profile__branch=branch)
    if semester:
        try:
            students_qs = students_qs.filter(student_profile__semester=int(semester))
        except ValueError:
            pass

    total_students = students_qs.count()

    # Attempts in teacher's scope
    attempts_qs = AssessmentAttempt.objects.filter(
        student__in=students_qs,
        status=AssessmentAttempt.AttemptStatus.COMPLETED
    ).select_related("assessment", "student")

    date_cutoff = _parse_date_cutoff(date_range)
    if date_cutoff:
        attempts_qs = attempts_qs.filter(started_at__gte=date_cutoff)

    avg_score = round(attempts_qs.aggregate(a=Avg("score"))["a"] or 0.0, 1)

    # Performance distribution buckets
    high_performers = 0   # >= 80%
    mid_performers = 0    # 60-79%
    avg_performers = 0    # 40-59%
    low_performers = 0    # < 40%

    student_averages = {}
    for att in attempts_qs:
        s_id = att.student.public_id
        if s_id not in student_averages:
            student_averages[s_id] = {"name": att.student.full_name, "scores": [], "branch": att.student.student_profile.branch}
        student_averages[s_id]["scores"].append(att.score)

    students_needing_support = []
    for s_id, data in student_averages.items():
        s_avg = sum(data["scores"]) / len(data["scores"])
        if s_avg >= 80:
            high_performers += 1
        elif s_avg >= 60:
            mid_performers += 1
        elif s_avg >= 40:
            avg_performers += 1
        else:
            low_performers += 1

        if s_avg < 50:
            students_needing_support.append({
                "public_id": s_id,
                "name": data["name"],
                "branch": data["branch"],
                "avg_score": round(s_avg, 1),
                "attempts_count": len(data["scores"]),
            })

    # Sort students needing support by lowest average score
    students_needing_support.sort(key=lambda x: x["avg_score"])

    # Branch comparisons within teacher's scope
    branch_stats = []
    for b in assigned_branches:
        b_students = students_qs.filter(student_profile__branch=b)
        b_attempts = attempts_qs.filter(student__in=b_students)
        b_avg = round(b_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)
        branch_stats.append({
            "branch": b,
            "student_count": b_students.count(),
            "average_score": b_avg,
            "attempts_count": b_attempts.count(),
        })

    # Real Attendance for cohort
    from dashboards.models import AttendanceRecord
    cohort_att = AttendanceRecord.objects.filter(
        student__in=students_qs
    ).exclude(session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN)
    c_tot = cohort_att.count()
    c_pres = cohort_att.filter(status=AttendanceRecord.Status.PRESENT).count()
    c_late = cohort_att.filter(status=AttendanceRecord.Status.LATE).count()
    c_rate = round(((c_pres + 0.5 * c_late) / c_tot * 100), 1) if c_tot else 0.0
    c_pct_str = f"{c_rate}%" if c_tot else "N/A"
    c_note = f"{c_pres} present across {c_tot} records" if c_tot else "No attendance recorded"

    return {
        "scope_summary": {
            "authorized_branches": assigned_branches,
            "total_students": total_students,
            "average_performance": avg_score,
            "total_attempts_recorded": attempts_qs.count(),
            "attendance_percentage": c_pct_str,
            "attendance_numeric": c_rate,
            "attendance_note": c_note,
            "high_performers_count": high_performers,
            "mid_performers_count": mid_performers,
            "avg_performers_count": avg_performers,
            "low_performers_count": low_performers,
        },
        "branch_comparisons": branch_stats,
        "students_needing_support": students_needing_support[:10],
    }


# ==============================================================================
# 3. ADMIN ANALYTICS ENGINE
# ==============================================================================

def get_admin_overview_analytics(range_key="30d"):
    """Section A: Institution-wide telemetry, demographic distributions, and platform health."""
    now = timezone.now()
    date_cutoff = _parse_date_cutoff(range_key)

    students = User.objects.filter(role=Role.STUDENT.value)
    teachers = User.objects.filter(role=Role.TEACHER.value)

    total_students = students.count()
    active_students = students.filter(is_active=True).count()
    suspended_students = students.filter(is_active=False).count()

    total_teachers = teachers.count()
    active_teachers = teachers.filter(is_active=True).count()
    suspended_teachers = teachers.filter(is_active=False).count()

    branches = AcademicBranch.objects.filter(is_archived=False)
    total_branches = branches.count()
    total_subjects = Subject.objects.count()

    assessments_qs = Assessment.objects.all()
    attempts_qs = AssessmentAttempt.objects.all()

    if date_cutoff:
        attempts_qs = attempts_qs.filter(started_at__gte=date_cutoff)

    total_assessments = assessments_qs.count()
    total_attempts = attempts_qs.count()
    completed_attempts = attempts_qs.filter(status=AssessmentAttempt.AttemptStatus.COMPLETED)
    avg_score = round(completed_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)

    # Assignment completion institution-wide
    potential_total = total_students * total_assessments
    completion_rate = round((completed_attempts.count() / potential_total * 100), 1) if potential_total else 0.0

    # Branch Distribution
    branch_counts_raw = dict(StudentProfile.objects.values_list("branch").annotate(n=Count("id")))
    branch_data = [
        {"code": b.code, "name": b.name, "count": branch_counts_raw.get(b.code, 0)}
        for b in branches
    ]
    tot_b = sum(b["count"] for b in branch_data) or 1
    for b in branch_data:
        b["percentage"] = round((b["count"] / tot_b) * 100, 1)

    # Semester Distribution
    sem_counts_raw = dict(StudentProfile.objects.values_list("semester").annotate(n=Count("id")))
    sem_data = [
        {"semester": s, "count": sem_counts_raw.get(s, 0)}
        for s in range(1, 9)
    ]

    # Daily velocity (Registration & Attempt trends)
    trend_days = 7 if range_key == "7d" else (30 if range_key == "30d" else 14)
    velocity_labels = []
    new_users_trend = []
    attempts_trend = []

    for i in range(trend_days - 1, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        velocity_labels.append(day_date.strftime("%d %b"))
        u_cnt = User.objects.filter(date_joined__date=day_date).count()
        att_cnt = AssessmentAttempt.objects.filter(started_at__date=day_date).count()
        new_users_trend.append(u_cnt)
        attempts_trend.append(att_cnt)

    # Real Institution-wide Attendance
    from dashboards.models import AttendanceRecord
    admin_att_qs = AttendanceRecord.objects.exclude(session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN)
    if date_cutoff:
        admin_att_qs = admin_att_qs.filter(date__gte=date_cutoff.date())
    total_admin_att = admin_att_qs.count()
    admin_att_present = admin_att_qs.filter(status=AttendanceRecord.Status.PRESENT).count()
    admin_att_late = admin_att_qs.filter(status=AttendanceRecord.Status.LATE).count()
    admin_att_rate = round(((admin_att_present + 0.5 * admin_att_late) / total_admin_att * 100), 1) if total_admin_att else 0.0

    return {
        "metrics": {
            "total_students": total_students,
            "active_students": active_students,
            "suspended_students": suspended_students,
            "total_teachers": total_teachers,
            "active_teachers": active_teachers,
            "suspended_teachers": suspended_teachers,
            "total_branches": total_branches,
            "total_subjects": total_subjects,
            "total_assessments": total_assessments,
            "total_attempts": total_attempts,
            "avg_score": avg_score,
            "completion_rate": completion_rate,
            "attendance_percentage": f"{admin_att_rate}%" if total_admin_att else "N/A",
            "attendance_numeric": admin_att_rate,
            "attendance_note": f"{admin_att_present} present across {total_admin_att} sessions" if total_admin_att else "No attendance logged yet",
            "total_resources": LearningResource.objects.count(),
            "total_scholarships": Scholarship.objects.count(),
            "total_meetings": Meeting.objects.count(),
            "total_audit_events": AuditEvent.objects.count(),
        },
        "branch_data": branch_data,
        "sem_data": sem_data,
        "trends": {
            "labels": velocity_labels,
            "new_users": new_users_trend,
            "attempts": attempts_trend,
        }
    }


def get_admin_individual_teacher_analytics(teacher_public_id):
    """Section B, Option 1: Detailed individual teacher diagnostic for admin."""
    teacher = User.objects.filter(public_id__iexact=teacher_public_id.strip(), role=Role.TEACHER.value).first()
    if not teacher:
        return {"error": "not_found", "message": f"Teacher ID '{teacher_public_id}' not found."}

    analytics = get_teacher_teaching_analytics(teacher, range_key="all")
    return {
        "success": True,
        "teacher_id": teacher.public_id,
        "teacher_name": teacher.full_name,
        "teacher_email": teacher.email,
        "status": "Active" if teacher.is_active else "Suspended",
        "date_joined": teacher.date_joined.strftime("%Y-%m-%d"),
        "analytics": analytics,
    }


def get_admin_all_teachers_analytics(department=None, date_range="30d"):
    """Section B, Option 2: Institution-wide faculty workload & performance distribution."""
    teachers_qs = User.objects.filter(role=Role.TEACHER.value).select_related("teacher_profile")
    if department:
        teachers_qs = teachers_qs.filter(teacher_profile__department=department)

    teacher_list = []
    for t in teachers_qs:
        created_count = Assessment.objects.filter(created_by=t).count()
        attempts_count = AssessmentAttempt.objects.filter(assessment__created_by=t).count()
        avg_score = round(AssessmentAttempt.objects.filter(
            assessment__created_by=t, status=AssessmentAttempt.AttemptStatus.COMPLETED
        ).aggregate(a=Avg("score"))["a"] or 0.0, 1)
        meetings_count = Meeting.objects.filter(host_teacher=t).count()
        resources_count = LearningResource.objects.filter(author=t).count()

        teacher_list.append({
            "public_id": t.public_id,
            "full_name": t.full_name,
            "department": getattr(t.teacher_profile, "department", "CSE"),
            "designation": getattr(t.teacher_profile, "designation", "Faculty"),
            "is_active": t.is_active,
            "assessments_created": created_count,
            "submissions_received": attempts_count,
            "student_avg_score": avg_score,
            "meetings_hosted": meetings_count,
            "resources_authored": resources_count,
        })

    return {
        "total_teachers": teachers_qs.count(),
        "active_teachers": teachers_qs.filter(is_active=True).count(),
        "teachers": teacher_list,
    }


def get_admin_individual_student_analytics(student_public_id):
    """Section C, Option 1: Detailed individual student diagnostic for admin."""
    student = User.objects.filter(public_id__iexact=student_public_id.strip(), role=Role.STUDENT.value).first()
    if not student:
        return {"error": "not_found", "message": f"Student ID '{student_public_id}' not found."}

    analytics = get_student_personal_analytics(student, range_key="all")
    return {
        "success": True,
        "student_id": student.public_id,
        "student_name": student.full_name,
        "student_email": student.email,
        "status": "Active" if student.is_active else "Suspended",
        "date_joined": student.date_joined.strftime("%Y-%m-%d"),
        "analytics": analytics,
    }


def get_admin_all_students_analytics(branch=None, semester=None, date_range="30d"):
    """Section C, Option 2: Institution-wide student academic aggregation."""
    students_qs = User.objects.filter(role=Role.STUDENT.value).select_related("student_profile")
    if branch:
        students_qs = students_qs.filter(student_profile__branch=branch)
    if semester:
        try:
            students_qs = students_qs.filter(student_profile__semester=int(semester))
        except ValueError:
            pass

    total_students = students_qs.count()
    completed_attempts = AssessmentAttempt.objects.filter(
        student__in=students_qs,
        status=AssessmentAttempt.AttemptStatus.COMPLETED
    )
    overall_avg_score = round(completed_attempts.aggregate(a=Avg("score"))["a"] or 0.0, 1)

    # Students needing support
    student_score_map = {}
    for att in completed_attempts:
        s_id = att.student.public_id
        if s_id not in student_score_map:
            student_score_map[s_id] = {
                "public_id": s_id,
                "name": att.student.full_name,
                "branch": getattr(att.student.student_profile, "branch", "CSE"),
                "semester": getattr(att.student.student_profile, "semester", 1),
                "scores": []
            }
        student_score_map[s_id]["scores"].append(att.score)

    students_needing_support = []
    high_count, mid_count, avg_count, low_count = 0, 0, 0, 0
    for s_id, item in student_score_map.items():
        s_avg = sum(item["scores"]) / len(item["scores"])
        if s_avg >= 80:
            high_count += 1
        elif s_avg >= 60:
            mid_count += 1
        elif s_avg >= 40:
            avg_count += 1
        else:
            low_count += 1

        if s_avg < 50:
            students_needing_support.append({
                "public_id": s_id,
                "name": item["name"],
                "branch": item["branch"],
                "semester": item["semester"],
                "avg_score": round(s_avg, 1),
                "attempts_count": len(item["scores"]),
            })

    students_needing_support.sort(key=lambda x: x["avg_score"])

    # Branch comparisons
    branches = AcademicBranch.objects.filter(is_archived=False)
    branch_comparison = []
    for b in branches:
        b_st = students_qs.filter(student_profile__branch=b.code)
        b_att = completed_attempts.filter(student__in=b_st)
        b_avg = round(b_att.aggregate(a=Avg("score"))["a"] or 0.0, 1)
        branch_comparison.append({
            "branch": b.code,
            "name": b.name,
            "students_count": b_st.count(),
            "average_score": b_avg,
            "attempts_count": b_att.count(),
        })

    return {
        "total_students": total_students,
        "overall_average_score": overall_avg_score,
        "high_performers_count": high_count,
        "mid_performers_count": mid_count,
        "avg_performers_count": avg_count,
        "low_performers_count": low_count,
        "branch_comparison": branch_comparison,
        "students_needing_support": students_needing_support[:15],
    }
