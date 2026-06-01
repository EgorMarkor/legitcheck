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

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Session ──────────────────────────────────────────────────────────────────

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        proxy_url = getattr(settings, "TELEGRAM_API_PROXY", "")
        if proxy_url:
            _session.proxies.update({
                "http": proxy_url,
                "https": proxy_url,
            })
    return _session


# ─── Low-level API call ───────────────────────────────────────────────────────

def api_call(token, method, payload=None, files=None, timeout=15):
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
        return resp.json()
    except Exception:
        logger.exception("Telegram API error [%s]", method)
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
        resp = _get_session().get(cdn_url, timeout=10)
        resp.raise_for_status()
    except Exception:
        logger.exception("Failed to download avatar for tg_id=%s", tg_id)
        return None

    ext = cdn_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
    filename = f"{tg_id}.{ext}"
    avatars_dir = os.path.join(settings.MEDIA_ROOT, "avatars")
    os.makedirs(avatars_dir, exist_ok=True)

    with open(os.path.join(avatars_dir, filename), "wb") as f:
        f.write(resp.content)

    return f"{settings.MEDIA_URL.rstrip('/')}/avatars/{filename}"
