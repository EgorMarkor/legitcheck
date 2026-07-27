import logging

from .apns import send_apns_to_user
from .webpush import send_web_push_to_user


logger = logging.getLogger(__name__)


def send_user_push(user_id, *, title, body, url, tag="checker-verdict"):
    payload = {
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
    }
    delivered = 0
    for sender in (send_web_push_to_user, send_apns_to_user):
        try:
            delivered += sender(user_id, payload)
        except Exception:
            logger.exception("Push sender %s failed for user %s", sender.__name__, user_id)
    return delivered
