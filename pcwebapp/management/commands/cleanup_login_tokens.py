from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from pcwebapp.models import LoginToken


class Command(BaseCommand):
    help = "Delete expired one-time login tokens after a short retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days",
            type=int,
            default=7,
            help="Keep expired tokens for this many days (default: 7).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the number of matching rows without deleting them.",
        )

    def handle(self, *args, **options):
        retention_days = options["retention_days"]
        if retention_days < 0:
            self.stderr.write(self.style.ERROR("--retention-days cannot be negative"))
            return

        cutoff = timezone.now() - timedelta(days=retention_days)
        queryset = LoginToken.objects.filter(expires_at__lt=cutoff)
        count = queryset.count()

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} expired login tokens.")
            return

        deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired login tokens."))
