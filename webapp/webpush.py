import json
import logging

from django.conf import settings

from .models import WebPushSubscription


logger = logging.getLogger(__name__)


def send_web_push_to_all(payload):
    public_key = getattr(settings, "VKCHAT_VAPID_PUBLIC_KEY", "")
    private_key = getattr(settings, "VKCHAT_VAPID_PRIVATE_KEY", "")
    claim_email = getattr(settings, "VKCHAT_VAPID_CLAIM_EMAIL", "admin@legitcheck.one")

    if not public_key or not private_key:
        logger.warning("VK chat push skipped: VAPID keys are not configured")
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.exception("VK chat push skipped: pywebpush is not installed")
        return 0

    sent = 0
    payload_json = json.dumps(payload, ensure_ascii=False)
    vapid_claims = {"sub": f"mailto:{claim_email}"}

    for subscription in WebPushSubscription.objects.filter(active=True).iterator():
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload_json,
                vapid_private_key=private_key,
                vapid_claims=vapid_claims,
            )
            if subscription.last_error:
                subscription.last_error = ""
                subscription.save(update_fields=["last_error", "updated_at"])
            sent += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            subscription.last_error = str(exc)[:1000]
            if status_code in {404, 410}:
                subscription.active = False
                subscription.save(update_fields=["active", "last_error", "updated_at"])
            else:
                subscription.save(update_fields=["last_error", "updated_at"])
            logger.warning("VK chat push failed for subscription %s: %s", subscription.id, exc)
        except Exception as exc:
            subscription.last_error = str(exc)[:1000]
            subscription.save(update_fields=["last_error", "updated_at"])
            logger.exception("Unexpected VK chat push error for subscription %s", subscription.id)

    return sent
