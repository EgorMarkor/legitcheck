from django.db import models
from django.utils import timezone


class LoginToken(models.Model):
    """One-time token for Telegram authentication."""

    token = models.CharField(max_length=8, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(
        "webapp.User", on_delete=models.CASCADE, null=True, blank=True
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def is_expired(self) -> bool:
        return self.created_at < timezone.now() - timezone.timedelta(minutes=5)

