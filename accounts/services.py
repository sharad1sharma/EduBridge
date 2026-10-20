from django.db import transaction
from django.db.models import F

from .constants import Role
from .models import IdSequence, StudentProfile, TeacherProfile, User

ID_PREFIX = {Role.STUDENT.value: "S", Role.TEACHER.value: "T"}
FIRST_NUMBER = 1001


def allocate_public_id(role: str) -> str:
    """Return the next S#### / T#### ID. Must run inside the caller's transaction so the
    row lock is held until the user row is committed."""
    prefix = ID_PREFIX.get(str(role))
    if prefix is None:
        raise ValueError("Only students and teachers have public IDs.")
    with transaction.atomic():
        sequence, _ = IdSequence.objects.select_for_update().get_or_create(
            prefix=prefix, defaults={"last_value": FIRST_NUMBER - 1}
        )
        if sequence.last_value >= 9999:
            raise RuntimeError(f"Available 4-digit ID range for {prefix} has been exhausted.")
        sequence.last_value = F("last_value") + 1
        sequence.save(update_fields=["last_value"])
        sequence.refresh_from_db()
        return f"{prefix}{sequence.last_value}"


def create_user(*, role, username, email, full_name, password,
                must_change_password=False, profile=None) -> User:
    """The single place accounts are created. Callers decide the role on the server;
    nothing in a request body can choose it."""
    role = str(getattr(role, "value", role))
    with transaction.atomic():
        public_id = allocate_public_id(role) if role in ID_PREFIX else None
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            public_id=public_id,
            must_change_password=must_change_password,
        )
        user.set_password(password)
        user.save()
        if role == Role.STUDENT.value:
            StudentProfile.objects.create(user=user, **(profile or {}))
        elif role == Role.TEACHER.value:
            TeacherProfile.objects.create(user=user, **(profile or {}))
    return user
