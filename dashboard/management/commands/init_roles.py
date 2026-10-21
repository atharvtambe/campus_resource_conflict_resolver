from django.core.management.base import BaseCommand
from campus_resolver.permissions import ensure_default_groups, DEFAULT_ROLES
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = "Initializes default campus roles and groups in the database."

    def handle(self, *args, **options):
        ensure_default_groups()
        for role in DEFAULT_ROLES:
            group = Group.objects.get(name=role)
            self.stdout.write(self.style.SUCCESS(f"Verified role group: '{group.name}'"))
        self.stdout.write(self.style.SUCCESS("All default role groups initialized successfully."))
