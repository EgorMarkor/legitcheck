import json
import logging
import time
from pathlib import Path

from django.conf import settings

from .models import NativePushDevice


logger = logging.getLogger(__name__)


def _apns_configuration():
    key_id = str(getattr(settings, "APNS_KEY_ID", "")).strip()
    team_id = str(getattr(settings, "APNS_TEAM_ID", "")).strip()
    key_path = Path(str(getattr(settings, "APNS_AUTH_KEY_PATH", "")).strip())
    bundle_id = str(getattr(settings, "APNS_BUNDLE_ID", "")).strip()
    if not key_id or not team_id or not bundle_id or not key_path.is_file():
        return None
    return key_id, team_id, key_path, bundle_id


def apns_is_configured():
    return _apns_configuration() is not None


def send_apns_to_user(user_id, payload):
    configuration = _apns_configuration()
    if not configuration:
        logger.warning("APNs push skipped: credentials are not configured")
        return 0

    try:
        import httpx
        import jwt
    except ImportError:
        logger.exception("APNs push skipped: required packages are not installed")
        return 0

    key_id, team_id, key_path, default_bundle_id = configuration
    try:
        signing_key = key_path.read_text(encoding="utf-8")
        provider_token = jwt.encode(
            {"iss": team_id, "iat": int(time.time())},
            signing_key,
            algorithm="ES256",
            headers={"kid": key_id},
        )
    except Exception:
        logger.exception("APNs provider token could not be created")
        return 0

    host = (
        "https://api.sandbox.push.apple.com"
        if getattr(settings, "APNS_USE_SANDBOX", False)
        else "https://api.push.apple.com"
    )
    aps = {
        "alert": {
            "title": payload.get("title", "Checker"),
            "body": payload.get("body", "Статус проверки обновлён"),
        },
        "sound": "default",
    }
    wire_payload = {
        "aps": aps,
        "url": payload.get("url", "/verdicts/"),
        "tag": payload.get("tag", "checker-verdict"),
    }
    sent = 0

    with httpx.Client(http2=True, timeout=10.0) as client:
        devices = NativePushDevice.objects.filter(
            user_id=user_id,
            platform=NativePushDevice.PLATFORM_IOS,
            active=True,
        )
        for device in devices.iterator():
            headers = {
                "authorization": f"bearer {provider_token}",
                "apns-topic": device.bundle_id or default_bundle_id,
                "apns-push-type": "alert",
                "apns-priority": "10",
            }
            try:
                response = client.post(
                    f"{host}/3/device/{device.token}",
                    content=json.dumps(wire_payload, ensure_ascii=False).encode("utf-8"),
                    headers=headers,
                )
                if response.status_code == 200:
                    sent += 1
                    if device.last_error:
                        device.last_error = ""
                        device.save(update_fields=["last_error", "updated_at"])
                    continue

                reason = response.text[:1000]
                device.last_error = f"{response.status_code}: {reason}"
                if response.status_code in {400, 410}:
                    device.active = False
                    device.save(update_fields=["active", "last_error", "updated_at"])
                else:
                    device.save(update_fields=["last_error", "updated_at"])
                logger.warning("APNs rejected device %s: %s", device.id, device.last_error)
            except Exception as exc:
                device.last_error = str(exc)[:1000]
                device.save(update_fields=["last_error", "updated_at"])
                logger.exception("APNs request failed for device %s", device.id)

    return sent
