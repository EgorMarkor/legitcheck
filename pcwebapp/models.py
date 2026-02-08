# pcwebapp/models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta

class LoginToken(models.Model):
    token = models.CharField(max_length=8, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # без default
    used_at = models.DateTimeField(null=True, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True)
    user = models.ForeignKey('webapp.User', null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def is_expired(self):
        return self.expires_at <= timezone.now()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)


class Brand(models.Model):
    brand = models.CharField(max_length=255)
    logo_url = models.URLField(max_length=500)
    brand_id = models.CharField(max_length=255, unique=True)
    category = models.CharField(max_length=100)

    def __str__(self):
        return self.brand


class UploadedVerdictPhoto(models.Model):
    user = models.ForeignKey(
        'webapp.User',
        on_delete=models.CASCADE,
        related_name='uploaded_verdict_photos',
    )
    image = models.ImageField(upload_to='verdicts/uploads')
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    verdict = models.ForeignKey(
        'webapp.Verdict',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_uploaded_photos',
    )

    class Meta:
        verbose_name = "Загруженная фотография вердикта"
        verbose_name_plural = "Загруженные фотографии вердикта"

    def mark_used(self, verdict):
        self.verdict = verdict
        self.used_at = timezone.now()
        self.save(update_fields=["verdict", "used_at"])
