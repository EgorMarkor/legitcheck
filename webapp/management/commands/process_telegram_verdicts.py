import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from webapp.models import TelegramVerdictDelivery
from webapp.views import _delete_telegram_messages, _deliver_verdict_to_telegram


class Command(BaseCommand):
    help = "Repeat Telegram verdict notifications and remove expired messages."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=int, default=30)

    def handle(self, *args, **options):
        while True:
            self.process_once()
            if options["once"]:
                return
            time.sleep(max(5, options["poll_seconds"]))
            close_old_connections()

    def process_once(self):
        now = timezone.now()
        due = list(
            TelegramVerdictDelivery.objects.select_related("verdict", "verdict__user")
            .prefetch_related("verdict__photos")
            .filter(active=True, next_send_at__lte=now)
            .order_by("next_send_at")[:50]
        )
        for delivery in due:
            verdict = delivery.verdict
            if verdict.status in {"legit", "fake"} or now >= delivery.expires_at:
                _delete_telegram_messages(delivery.chat_id, delivery.message_ids)
                delivery.message_ids = []
                delivery.active = False
                delivery.save(update_fields=["message_ids", "active", "updated_at"])
                continue
            try:
                _deliver_verdict_to_telegram(verdict, delivery=delivery)
            except Exception as exc:
                delivery.last_error = str(exc)[:2000]
                delivery.next_send_at = now + timedelta(minutes=1)
                delivery.save(update_fields=["last_error", "next_send_at", "updated_at"])
                self.stderr.write(f"Verdict {verdict.id}: {exc}")
