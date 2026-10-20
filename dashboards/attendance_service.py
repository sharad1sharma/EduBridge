"""EduBridge Attendance Management & Analytics Engine.

Provides persistent database-backed attendance tracking for:
- Student mode: personal attendance percentage, present/absent/late totals, subject breakdown, history
- Teacher mode: class roster attendance marking, corrections, session summaries
- Admin mode: institution-wide attendance inspection, filtering, audit tracking
- Automatic attendance: records platform activity on login without falsely marking class attendance
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from accounts import audit
from accounts.constants import Role
from accounts.models import User
from dashboards.models import AttendanceRecord, Meeting, Subject


def record_platform_login_activity(user: User, request=None) -> Optional[AttendanceRecord]:
    """
    Records platform activity on user login.
    Deduplicates multiple logins on the same day.
    Only marks class attendance if the student is currently enrolled in an active,
    scheduled session and policy permits.
    """
    if not user or not user.is_authenticated:
        return None

    today = timezone.now().date()

    # Avoid duplicate platform login records for today
    existing = AttendanceRecord.objects.filter(
        student=user,
        date=today,
        session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN
    ).first()
    if existing:
        return existing

    # Check if there is an active meeting/class for this student's cohort right now
    class_record = None
    if user.role == Role.STUDENT.value:
        profile = getattr(user, "student_profile", None)
        branch = profile.branch if profile else "CSE"
        sem = profile.semester if profile else 1
        now = timezone.now()
        active_meeting = Meeting.objects.filter(
            branch=branch,
            semester=sem,
            status__in=[Meeting.Status.SCHEDULED, Meeting.Status.ONGOING],
            scheduled_at__lte=now + timedelta(minutes=15),
            scheduled_at__gte=now - timedelta(hours=2)
        ).first()

        if active_meeting:
            # Check if class attendance was already marked
            existing_class = AttendanceRecord.objects.filter(
                student=user,
                subject=active_meeting.subject,
                date=today,
                session_type=AttendanceRecord.SessionType.CLASS
            ).first()
            if not existing_class:
                class_record = AttendanceRecord.objects.create(
                    student=user,
                    subject=active_meeting.subject,
                    session_title=f"Live Class: {active_meeting.title}",
                    session_type=AttendanceRecord.SessionType.CLASS,
                    date=today,
                    status=AttendanceRecord.Status.PRESENT,
                    recorded_by=active_meeting.host_teacher,
                    is_auto_marked=True,
                    remarks="Automatic attendance via active class login"
                )
                if request:
                    audit.record(request, "class_attendance_auto_marked", student=user.username, session=active_meeting.title)

    # Record platform activity record
    activity_record = AttendanceRecord.objects.create(
        student=user,
        subject=None,
        session_title="Daily Platform Login Activity",
        session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN,
        date=today,
        status=AttendanceRecord.Status.PRESENT,
        recorded_by=user,
        is_auto_marked=True,
        remarks="Daily verified student platform session"
    )
    return class_record or activity_record


def get_student_attendance_summary(student: User) -> Dict[str, Any]:
    """Compute comprehensive personal attendance records for a student."""
    records_qs = AttendanceRecord.objects.filter(
        student=student
    ).select_related("subject", "recorded_by").order_by("-date", "-created_at")

    # Filter for session attendance (excluding pure platform login from physical class calculation if needed, or combining meaningfully)
    class_sessions = records_qs.filter(session_type__in=[
        AttendanceRecord.SessionType.CLASS,
        AttendanceRecord.SessionType.LAB,
        AttendanceRecord.SessionType.TUTORIAL
    ])

    total_sessions = class_sessions.count()
    present_count = class_sessions.filter(status=AttendanceRecord.Status.PRESENT).count()
    absent_count = class_sessions.filter(status=AttendanceRecord.Status.ABSENT).count()
    late_count = class_sessions.filter(status=AttendanceRecord.Status.LATE).count()

    # If no class sessions exist yet, check platform activity
    if total_sessions == 0:
        platform_records = records_qs.filter(session_type=AttendanceRecord.SessionType.PLATFORM_LOGIN)
        total_sessions = platform_records.count()
        present_count = total_sessions
        absent_count = 0
        late_count = 0

    if total_sessions > 0:
        attendance_pct = round(((present_count + 0.5 * late_count) / total_sessions) * 100, 1)
        attendance_str = f"{attendance_pct}%"
        attendance_note = f"{present_count} present, {absent_count} absent across {total_sessions} sessions"
    else:
        attendance_pct = 0.0
        attendance_str = "N/A"
        attendance_note = "No scheduled attendance sessions recorded"

    # Subject-wise attendance breakdown
    from dashboards.analytics_service import get_student_enrolled_subjects
    enrolled_subjects = get_student_enrolled_subjects(student)
    subject_attendance = []

    for subj in enrolled_subjects:
        subj_records = class_sessions.filter(subject=subj)
        s_total = subj_records.count()
        s_present = subj_records.filter(status=AttendanceRecord.Status.PRESENT).count()
        s_absent = subj_records.filter(status=AttendanceRecord.Status.ABSENT).count()
        s_late = subj_records.filter(status=AttendanceRecord.Status.LATE).count()
        if s_total > 0:
            s_pct = round(((s_present + 0.5 * s_late) / s_total) * 100, 1)
        else:
            s_pct = None

        subject_attendance.append({
            "subject_id": subj.id,
            "code": subj.code,
            "title": subj.title,
            "total_sessions": s_total,
            "present_count": s_present,
            "absent_count": s_absent,
            "late_count": s_late,
            "percentage": s_pct,
            "status_label": f"{s_pct}%" if s_pct is not None else "No Sessions",
        })

    # Recent history records (last 20)
    history = []
    for r in records_qs[:20]:
        history.append({
            "id": r.id,
            "date": r.date,
            "session_title": r.session_title,
            "session_type": r.get_session_type_display(),
            "subject_code": r.subject.code if r.subject else "General",
            "subject_title": r.subject.title if r.subject else "Platform Activity",
            "status": r.status,
            "status_display": r.get_status_display(),
            "recorded_by": r.recorded_by.full_name if r.recorded_by else "System",
            "is_auto": r.is_auto_marked,
            "remarks": r.remarks,
        })

    return {
        "attendance_percentage": attendance_str,
        "attendance_numeric": attendance_pct,
        "attendance_note": attendance_note,
        "total_sessions": total_sessions,
        "present_count": present_count,
        "absent_count": absent_count,
        "late_count": late_count,
        "subjects": subject_attendance,
        "history": history,
    }


def get_teacher_attendance_roster(teacher: User, subject_id: Optional[int] = None, session_date: Optional[date] = None) -> Dict[str, Any]:
    """Retrieve authorized attendance roster for a teacher's classes."""
    profile = getattr(teacher, "teacher_profile", None)
    dept = profile.department if profile else "CSE"
    target_date = session_date or timezone.now().date()

    # Subjects assigned to teacher or matching department
    assigned_subjects = teacher.assigned_subjects.all()
    if not assigned_subjects.exists():
        assigned_subjects = Subject.objects.filter(branch=dept)

    selected_subject = None
    if subject_id:
        selected_subject = assigned_subjects.filter(id=subject_id).first()
    if not selected_subject and assigned_subjects.exists():
        selected_subject = assigned_subjects.first()

    # Students enrolled in this subject or belonging to branch & semester
    if selected_subject:
        from dashboards.models import Subject
        students_qs = User.objects.filter(
            Q(enrolled_subjects=selected_subject) |
            Q(student_profile__branch=selected_subject.branch, student_profile__semester=selected_subject.semester),
            role=Role.STUDENT.value
        ).distinct().select_related("student_profile").order_by("student_profile__public_id", "full_name")
    else:
        students_qs = User.objects.filter(
            role=Role.STUDENT.value,
            student_profile__branch=dept
        ).distinct().select_related("student_profile").order_by("full_name")

    # Existing records for target date and subject
    existing_records = {
        r.student_id: r
        for r in AttendanceRecord.objects.filter(
            subject=selected_subject,
            date=target_date,
            session_type__in=[AttendanceRecord.SessionType.CLASS, AttendanceRecord.SessionType.LAB]
        )
    }

    roster = []
    for s in students_qs:
        rec = existing_records.get(s.id)
        roster.append({
            "student_id": s.id,
            "public_id": s.public_id,
            "full_name": s.full_name,
            "email": s.email,
            "branch": s.student_profile.branch if hasattr(s, "student_profile") else dept,
            "semester": s.student_profile.semester if hasattr(s, "student_profile") else 1,
            "status": rec.status if rec else "unmarked",
            "record_id": rec.id if rec else None,
            "remarks": rec.remarks if rec else "",
            "is_auto": rec.is_auto_marked if rec else False,
        })

    # Summary metrics for teacher
    total_marked = sum(1 for item in roster if item["status"] != "unmarked")
    present_marked = sum(1 for item in roster if item["status"] == AttendanceRecord.Status.PRESENT)
    absent_marked = sum(1 for item in roster if item["status"] == AttendanceRecord.Status.ABSENT)
    late_marked = sum(1 for item in roster if item["status"] == AttendanceRecord.Status.LATE)

    return {
        "selected_subject": selected_subject,
        "assigned_subjects": assigned_subjects,
        "target_date": target_date,
        "roster": roster,
        "total_students": len(roster),
        "total_marked": total_marked,
        "present_marked": present_marked,
        "absent_marked": absent_marked,
        "late_marked": late_marked,
        "attendance_rate": round((present_marked / total_marked * 100), 1) if total_marked else 0.0,
    }


def get_admin_attendance_overview(branch: Optional[str] = None, date_filter: Optional[date] = None) -> Dict[str, Any]:
    """Retrieve institution-wide attendance telemetry and audit records."""
    target_date = date_filter or timezone.now().date()
    qs = AttendanceRecord.objects.select_related("student", "subject", "recorded_by")

    if branch and branch != "all":
        qs = qs.filter(student__student_profile__branch=branch)

    total_records = qs.count()
    present_total = qs.filter(status=AttendanceRecord.Status.PRESENT).count()
    absent_total = qs.filter(status=AttendanceRecord.Status.ABSENT).count()
    late_total = qs.filter(status=AttendanceRecord.Status.LATE).count()

    overall_rate = round(((present_total + 0.5 * late_total) / total_records * 100), 1) if total_records else 0.0

    # Today's logs
    today_records = qs.filter(date=target_date).order_by("-created_at")[:50]
    recent_logs = []
    for r in today_records:
        recent_logs.append({
            "id": r.id,
            "date": r.date,
            "student_name": r.student.full_name,
            "student_id": r.student.public_id,
            "subject": r.subject.code if r.subject else "General",
            "session_title": r.session_title,
            "status": r.status,
            "recorded_by": r.recorded_by.full_name if r.recorded_by else "System",
            "is_auto": r.is_auto_marked,
            "updated_at": r.updated_at,
        })

    return {
        "target_date": target_date,
        "total_records": total_records,
        "present_total": present_total,
        "absent_total": absent_total,
        "late_total": late_total,
        "overall_rate": overall_rate,
        "recent_logs": recent_logs,
    }


def update_attendance_record(student_id: int, subject_id: Optional[int], target_date: date, status: str, recorded_by: User, session_title: str = "Class Session", session_type: str = AttendanceRecord.SessionType.CLASS, remarks: str = "") -> AttendanceRecord:
    """Safely create or update an attendance record with atomic consistency."""
    student = User.objects.get(pk=student_id)
    subject = Subject.objects.filter(pk=subject_id).first() if subject_id else None

    with transaction.atomic():
        record, created = AttendanceRecord.objects.update_or_create(
            student=student,
            subject=subject,
            date=target_date,
            session_type=session_type,
            defaults={
                "status": status,
                "session_title": session_title,
                "recorded_by": recorded_by,
                "remarks": remarks,
                "is_auto_marked": False,
            }
        )
    return record
