from django.core.management.base import BaseCommand
from django.db import transaction

from portal.access import PERMISSIONS, ROLE_DEFINITIONS
from sgr_core.models import Permission, Role


class Command(BaseCommand):
    help = "Crea/actualiza los permisos y los 4 roles base (idempotente)."

    @transaction.atomic
    def handle(self, *args, **options):
        perms = {}
        for codename, name in PERMISSIONS.items():
            perms[codename], _ = Permission.objects.update_or_create(codename=codename, defaults={"name": name})
        for code, d in ROLE_DEFINITIONS.items():
            role, _ = Role.objects.update_or_create(
                code=code, defaults={"name": d["name"], "description": d["description"], "scope": d["scope"], "is_active": True})
            role.permissions.set([perms[c] for c in d["perms"]])
        self.stdout.write(self.style.SUCCESS(f"{len(PERMISSIONS)} permisos y {len(ROLE_DEFINITIONS)} roles listos."))
