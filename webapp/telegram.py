"""
Centralized Telegram Bot API service.

All server-side communication with api.telegram.org goes through
this module. The browser never contacts Telegram domains directly.

Usage:
    from . import telegram as tg
    tg.send_message(TOKEN, chat_id, "hello")
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Session ──────────────────────────────────────────────────────────────────

_session = None
API_TIMEOUT = (5, 15)
AVATAR_TIMEOUT = (5, 10)
ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.trust_env = False
        proxy_url = getattr(settings, "TELEGRAM_API_PROXY", "")
        if proxy_url:
            _session.proxies.update({
                "http": proxy_url,
                "https": proxy_url,
            })
    return _session


# ─── Low-level API call ───────────────────────────────────────────────────────

def api_call(token, method, payload=None, files=None, timeout=API_TIMEOUT):
    """
    Make a Telegram Bot API request.
    Returns the parsed JSON dict on success, None on any error.
    """
    url = f"https://api.telegram.org/bot{token}/{method}"
    session = _get_session()
    try:
        if files:
            resp = session.post(url, data=payload or {}, files=files, timeout=timeout)
        else:
            resp = session.post(url, json=payload or {}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok", False):
            logger.warning(
                "Telegram API rejected request method=%s status=%s description=%s",
                method,
                resp.status_code,
                data.get("description", "unknown error"),
            )
            return None
        return data
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        description = None
        if response is not None:
            try:
                description = response.json().get("description")
            except (ValueError, AttributeError):
                description = None
        logger.warning(
            "Telegram API request failed method=%s error=%s status=%s description=%s",
            method,
            type(exc).__name__,
            status,
            description or "unavailable",
        )
        return None
    except ValueError:
        logger.warning("Telegram API returned invalid JSON method=%s", method)
        return None


# ─── High-level helpers ───────────────────────────────────────────────────────

def send_message(token, chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_call(token, "sendMessage", payload)


def send_media_group(token, chat_id, media, files=None):
    payload = {
        "chat_id": chat_id,
        "media": json.dumps(media),
    }
    return api_call(token, "sendMediaGroup", payload, files=files)


def answer_callback_query(token, callback_query_id, text):
    return api_call(token, "answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


def edit_message_reply_markup(token, chat_id, message_id, reply_markup):
    return api_call(token, "editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup,
    })


def delete_message(token, chat_id, message_id):
    return api_call(token, "deleteMessage", {
        "chat_id": chat_id,
        "message_id": message_id,
    })


# ─── Avatar: download & cache locally ────────────────────────────────────────

def _get_avatar_cdn_url(token, tg_id):
    """Return the Telegram CDN URL for a user's profile photo, or None."""
    result = api_call(token, "getUserProfilePhotos", {"user_id": tg_id, "limit": 1})
    if not result or not result.get("ok"):
        return None
    photos = result.get("result", {}).get("photos", [])
    if not photos:
        return None
    file_id = sorted(photos[0], key=lambda s: s.get("file_size", 0))[-1]["file_id"]

    result = api_call(token, "getFile", {"file_id": file_id})
    if not result or not result.get("ok"):
        return None
    file_path = result.get("result", {}).get("file_path")
    if not file_path:
        return None
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


def download_and_cache_avatar(token, tg_id):
    """
    Download the user's Telegram profile photo and save it under MEDIA_ROOT/avatars/.
    Returns the local URL string (e.g. "/media/avatars/12345.jpg") on success,
    or None if unavailable / on any error.

    Browsers never contact api.telegram.org directly — photos are served
    from Django's /media/ endpoint instead.
    """
    cdn_url = _get_avatar_cdn_url(token, tg_id)
    if not cdn_url:
        return None

    try:
        resp = _get_session().get(cdn_url, timeout=AVATAR_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(
            "Failed to download avatar tg_id=%s error=%s",
            tg_id,
            type(exc).__name__,
        )
        return None

    ext = Path(urlparse(cdn_url).path).suffix.lstrip(".").lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        ext = "jpg"
    filename = f"{tg_id}.{ext}"
    avatars_dir = os.path.join(settings.MEDIA_ROOT, "avatars")
    os.makedirs(avatars_dir, exist_ok=True)

    destination = os.path.join(avatars_dir, filename)
    fd, temp_path = tempfile.mkstemp(prefix=f".{tg_id}-", dir=avatars_dir)
    try:
        with os.fdopen(fd, "wb") as temp_file:
            temp_file.write(resp.content)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    return f"{settings.MEDIA_URL.rstrip('/')}/avatars/{filename}"
