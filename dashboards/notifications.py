"""Persistent notification dispatch and management service for EduBridge.
Supports students, teachers, and administrators.
"""
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from accounts.models import User, Role
from dashboards.models import PlatformNotification, Assessment, AssessmentAttempt


def create_notification(
    recipient: User,
    title: str,
    message: str,
    notification_type: str = PlatformNotification.NotificationType.PLATFORM,
    link: str = ""
) -> Optional[PlatformNotification]:
    """Persist a notification record in the database."""
    if not recipient or not recipient.is_active:
        return None
    try:
        return PlatformNotification.objects.create(
            recipient=recipient,
            title=title.strip()[:200],
            message=message.strip(),
            notification_type=notification_type,
            link=link.strip()[:255],
            delivery_status=PlatformNotification.DeliveryStatus.DELIVERED,
            is_read=False
        )
    except Exception:
        return None


def notify_assignment_published(assessment: Assessment, teacher: User) -> int:
    """Notify all eligible students when an assignment is published or scheduled."""
    if assessment.status not in [Assessment.Status.PUBLISHED, Assessment.Status.SCHEDULED]:
        return 0

    # Determine recipients: specific targeted students or whole branch/semester cohort
    if assessment.target_students.exists():
        students = list(assessment.target_students.filter(is_active=True))
    else:
        students = list(User.objects.filter(
            role=Role.STUDENT.value,
            student_profile__branch=assessment.branch,
            student_profile__semester=assessment.semester,
            is_active=True
        ))

    deadline_str = assessment.deadline.strftime("%b %d, %Y at %I:%M %p")
    notif_type = (
        PlatformNotification.NotificationType.ASSIGNMENT
        if assessment.assessment_type == Assessment.AssessmentType.DAILY_ASSIGNMENT
        else PlatformNotification.NotificationType.TEST
    )

    is_scheduled = assessment.is_scheduled_future
    if is_scheduled:
        start_str = assessment.start_date.strftime("%b %d, %Y at %I:%M %p")
        title = f"Scheduled Assessment: {assessment.title}"
        msg = f"Prof. {teacher.full_name} scheduled a new {assessment.get_assessment_type_display()}. It will be available from {start_str} until {deadline_str}."
    else:
        title = f"New Assessment Published: {assessment.title}"
        msg = f"Prof. {teacher.full_name} published '{assessment.title}' ({assessment.get_assessment_type_display()}, {assessment.total_marks} marks) due on {deadline_str}."

    created_count = 0
    with transaction.atomic():
        for s in students:
            notif = create_notification(
                recipient=s,
                title=title,
                message=msg,
                notification_type=notif_type,
                link=f"/student/assessment/{assessment.pk}/"
            )
            if notif:
                created_count += 1
    return created_count


def notify_assessment_submitted(attempt: AssessmentAttempt) -> Optional[PlatformNotification]:
    """Notify authoring faculty when a student submits an assessment."""
    assessment = attempt.assessment
    teacher = assessment.created_by or User.objects.filter(role=Role.TEACHER, is_active=True).first()
    if not teacher:
        teacher = User.objects.filter(role=Role.ADMIN, is_active=True).first()
    if not teacher:
        return None

    student = attempt.student
    score_disp = f"{attempt.score:.1f}/{assessment.total_marks}"
    title = f"Student Assessment Submission: {student.full_name} ({assessment.title})"
    message = f"Student {student.full_name} ({student.public_id}) submitted '{assessment.title}'. Calculated score: {score_disp}."
    
    return create_notification(
        recipient=teacher,
        title=title,
        message=message,
        notification_type=PlatformNotification.NotificationType.ASSIGNMENT,
        link="/teacher/assessments/"
    )


def notify_results_released(attempt: AssessmentAttempt) -> Optional[PlatformNotification]:
    """Notify student when assessment scores/feedback are released."""
    student = attempt.student
    assessment = attempt.assessment
    title = f"Assessment Evaluated: {assessment.title}"
    msg = f"Your attempt for '{assessment.title}' has been evaluated. Your official score is {attempt.score:.1f}/{assessment.total_marks}."
    
    return create_notification(
        recipient=student,
        title=title,
        message=msg,
        notification_type=PlatformNotification.NotificationType.TEST,
        link="/student/results/"
    )


def notify_admin_event(title: str, message: str, link: str = "/administration/audit/") -> int:
    """Notify all active administrators of an important platform event."""
    admins = User.objects.filter(role=Role.ADMIN.value, is_active=True)
    count = 0
    for a in admins:
        if create_notification(a, title, message, PlatformNotification.NotificationType.PLATFORM, link):
            count += 1
    return count


def get_user_notifications_payload(user: User, limit: int = 25) -> Dict[str, Any]:
    """Fetch unread count and recent notifications for a user formatted for API consumption."""
    if not user or not user.is_authenticated:
        return {"unread_count": 0, "notifications": []}

    qs = PlatformNotification.objects.filter(recipient=user).order_by("-created_at")
    unread_count = qs.filter(is_read=False).count()
    recent = list(qs[:limit])

    now = timezone.now()
    items = []
    for n in recent:
        delta = now - n.created_at
        if delta.days == 0:
            if delta.seconds < 60:
                time_ago = "Just now"
            elif delta.seconds < 3600:
                time_ago = f"{delta.seconds // 60}m ago"
            else:
                time_ago = f"{delta.seconds // 3600}h ago"
        elif delta.days == 1:
            time_ago = "Yesterday"
        else:
            time_ago = f"{delta.days}d ago"

        items.append({
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.notification_type,
            "link": n.link or "#",
            "is_read": n.is_read,
            "time_ago": time_ago,
            "created_at_human": time_ago,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "unread_count": unread_count,
        "notifications": items
    }
