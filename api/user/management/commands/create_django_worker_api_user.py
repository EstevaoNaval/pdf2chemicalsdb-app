"""Ensure the django-worker API account exists.

Runs from docker-django-api-entrypoint.sh after migrate. Reads
DJANGO_WORKER_API_EMAIL, DJANGO_WORKER_API_USERNAME,
DJANGO_WORKER_API_FIRST_NAME, DJANGO_WORKER_API_LAST_NAME, and
DJANGO_WORKER_API_PASSWORD. Writes one non-staff User, a verified
allauth email, and the django_worker_chemical_writer group
(add_chemical and change_chemical only). Deletes that user's Knox tokens.
"""

import os
import re

from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from knox.models import AuthToken

from user.models import User

_ENV_KEYS = (
    "DJANGO_WORKER_API_EMAIL",
    "DJANGO_WORKER_API_USERNAME",
    "DJANGO_WORKER_API_FIRST_NAME",
    "DJANGO_WORKER_API_LAST_NAME",
    "DJANGO_WORKER_API_PASSWORD",
)
_GROUP_NAME = "django_worker_chemical_writer"
_PERM_CODENAMES = ("add_chemical", "change_chemical")


class Command(BaseCommand):
    help = "Ensure the django-worker API user, group, and verified email exist."

    def handle(self, *args, **options):
        missing = [key for key in _ENV_KEYS if not os.environ.get(key)]
        if missing:
            raise CommandError(
                "Missing environment variables: " + ", ".join(missing)
            )

        email = os.environ["DJANGO_WORKER_API_EMAIL"]
        username = os.environ["DJANGO_WORKER_API_USERNAME"]
        if re.fullmatch(r"[A-Za-z0-9_-]+", username) is None:
            raise CommandError(
                "DJANGO_WORKER_API_USERNAME must contain only letters, digits, hyphens, or underscores."
            )
        if User.objects.filter(username=username).exclude(email=email).exists():
            raise CommandError(
                f"Username {username} already belongs to a different user."
            )

        # User row. Password is applied on every boot so an env change takes effect.
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = User(email=email, username=username)
        user.username = username
        user.first_name = os.environ["DJANGO_WORKER_API_FIRST_NAME"]
        user.last_name = os.environ["DJANGO_WORKER_API_LAST_NAME"]
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(os.environ["DJANGO_WORKER_API_PASSWORD"])
        user.save()

        # add_chemical and change_chemical only. No view, no delete.
        permissions = Permission.objects.filter(
            content_type__app_label="chemicals",
            content_type__model="chemical",
            codename__in=_PERM_CODENAMES,
        )
        if permissions.count() != len(_PERM_CODENAMES):
            raise CommandError(
                "Chemical add/change permissions are missing. Run migrate first."
            )
        group, _created = Group.objects.get_or_create(name=_GROUP_NAME)
        group.permissions.set(permissions)
        user.groups.set([group])

        # LoginView rejects an unverified address and sends confirmation mail.
        EmailAddress.objects.update_or_create(
            user=user,
            email=email,
            defaults={"verified": True, "primary": True},
        )

        # Old bearers, including the retired static token, die on API start.
        AuthToken.objects.filter(user=user).delete()
        self.stdout.write(self.style.SUCCESS(f"django-worker API user {email} is ready."))
