import os
from getpass import getpass

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from accounts import services
from accounts.constants import Role
from accounts.models import IdSequence, User, username_validator


class Command(BaseCommand):
    help = (
        "Create the initial EduBridge administrator. Refuses to run if an administrator "
        "already exists. The password is prompted for (or read from EDUBRIDGE_ADMIN_PASSWORD "
        "for automation) and is never stored in code or logs."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username")
        parser.add_argument("--email")
        parser.add_argument("--full-name", dest="full_name")

    def handle(self, *args, **options):
        if User.objects.filter(role=Role.ADMIN.value).exists():
            raise CommandError("An administrator already exists. This command only creates the first one.")

        username = (options["username"] or input("Admin username: ")).strip().lower()
        email = (options["email"] or input("Admin email: ")).strip().lower()
        full_name = (options["full_name"] or input("Full name: ")).strip()
        try:
            username_validator(username)
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        if not full_name:
            raise CommandError("Full name is required.")
        if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
            raise CommandError("That username or email is already in use.")

        password = os.environ.get("EDUBRIDGE_ADMIN_PASSWORD")
        if not password:
            password = getpass("Password: ")
            if password != getpass("Password (again): "):
                raise CommandError("Passwords do not match.")
        try:
            validate_password(password, user=User(username=username, email=email, full_name=full_name))
        except ValidationError as exc:
            raise CommandError("Password rejected: " + " ".join(exc.messages))

        with transaction.atomic():
            # Lock row serialises concurrent bootstrap runs so two admins cannot be created.
            IdSequence.objects.select_for_update().get_or_create(prefix="A", defaults={"last_value": 0})
            if User.objects.filter(role=Role.ADMIN.value).exists():
                raise CommandError("An administrator already exists.")
            services.create_user(role=Role.ADMIN, username=username, email=email,
                                 full_name=full_name, password=password)
        self.stdout.write(self.style.SUCCESS(f"Administrator '{username}' created. Sign in at /accounts/login/."))
