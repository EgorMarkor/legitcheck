from django.db import models
from django.utils import timezone
from datetime import timedelta

class LoginToken(models.Model):
    token = models.CharField(max_length=64, primary_key=True)        # hex
    session_key = models.CharField(max_length=40, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    telegram_id = models.BigIntegerField(null=True, blank=True)

    @classmethod
    def create_for_session(cls, session_key, ttl_minutes=5):
        import secrets
        raw = secrets.token_hex(32)  # 64 hex chars = 256 bits
        return cls.objects.create(
            token=raw,
            session_key=session_key,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes)
        )
