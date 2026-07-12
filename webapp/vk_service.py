import logging
from datetime import datetime, timezone as datetime_timezone
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from .models import VkConversation, VkMessage
from .webpush import send_web_push_to_all


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_vk_api():
    if not settings.VK_GROUP_TOKEN:
        raise ImproperlyConfigured("VK_GROUP_TOKEN is not configured")

    import vk_api

    return vk_api.VkApi(token=settings.VK_GROUP_TOKEN).get_api()


def get_vk_group_id():
    try:
        return int(settings.VK_GROUP_ID)
    except (TypeError, ValueError):
        raise ImproperlyConfigured("VK_GROUP_ID is not configured")


def get_admin_ids(admin_roles=None):
    roles = admin_roles or {"creator", "administrator"}

    try:
        result = get_vk_api().groups.getMembers(
            group_id=get_vk_group_id(),
            filter="managers",
            fields="role",
        )
    except Exception:
        logger.exception("Failed to load VK group managers")
        return []

    admin_ids = []
    for item in result.get("items", []):
        if isinstance(item, int):
            admin_ids.append(item)
            continue

        user_id = item.get("id")
        role = item.get("role")
        if user_id and role in roles:
            admin_ids.append(user_id)

    return admin_ids


def send_to_admin(admin_id, text):
    get_vk_api().messages.send(
        peer_id=admin_id,
        message=text,
        random_id=_random_id(),
    )


def send_vk_reply(peer_id, text):
    text = (text or "").strip()
    if not text:
        raise ValueError("Message text is empty")

    result = get_vk_api().messages.send(
        peer_id=int(peer_id),
        message=text,
        random_id=_random_id(),
    )
    vk_message_id = _extract_sent_message_id(result)
    return create_outgoing_message(peer_id=int(peer_id), text=text, vk_message_id=vk_message_id)


def _random_id():
    from vk_api.utils import get_random_id

    return get_random_id()


def _extract_sent_message_id(result):
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        if isinstance(result.get("message_id"), int):
            return result["message_id"]
        response = result.get("response")
        if isinstance(response, int):
            return response
        if isinstance(response, dict) and isinstance(response.get("message_id"), int):
            return response["message_id"]
    return None


def create_outgoing_message(peer_id, text, vk_message_id=None):
    conversation = ensure_conversation(
        peer_id=int(peer_id),
        from_id=int(peer_id),
    )
    created_at = timezone.now()

    message = VkMessage.objects.create(
        conversation=conversation,
        vk_message_id=vk_message_id,
        peer_id=int(peer_id),
        from_id=-get_vk_group_id(),
        direction=VkMessage.DIRECTION_OUTGOING,
        text=text,
        attachments=[],
        raw_payload={},
        created_at=created_at,
    )

    conversation.last_message_text = text
    conversation.last_message_at = created_at
    conversation.save(update_fields=["last_message_text", "last_message_at", "updated_at"])
    return message


def ensure_conversation(peer_id, from_id=None, title="", avatar_url=""):
    peer_id = int(peer_id)
    from_id = int(from_id or peer_id)

    defaults = {
        "from_id": from_id,
        "title": title,
        "avatar_url": avatar_url,
    }
    conversation, created = VkConversation.objects.get_or_create(
        peer_id=peer_id,
        defaults=defaults,
    )

    changed_fields = []
    if conversation.from_id != from_id:
        conversation.from_id = from_id
        changed_fields.append("from_id")
    if title and conversation.title != title:
        conversation.title = title
        changed_fields.append("title")
    if avatar_url and conversation.avatar_url != avatar_url:
        conversation.avatar_url = avatar_url
        changed_fields.append("avatar_url")

    if not created and changed_fields:
        conversation.save(update_fields=[*changed_fields, "updated_at"])

    if not title and not avatar_url:
        refresh_conversation_profile(conversation)

    return conversation


def refresh_conversation_profile(conversation):
    profile = get_vk_profile(conversation.from_id)
    update_fields = []
    if profile.get("title") and conversation.title != profile["title"]:
        conversation.title = profile["title"]
        update_fields.append("title")
    if profile.get("avatar_url") and conversation.avatar_url != profile["avatar_url"]:
        conversation.avatar_url = profile["avatar_url"]
        update_fields.append("avatar_url")
    if update_fields:
        conversation.save(update_fields=[*update_fields, "updated_at"])
    return conversation


@lru_cache(maxsize=512)
def get_vk_profile(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return {"title": "", "avatar_url": ""}

    if user_id <= 0:
        return {"title": f"VK {user_id}", "avatar_url": ""}

    try:
        users = get_vk_api().users.get(
            user_ids=str(user_id),
            fields="photo_100,screen_name",
        )
    except Exception:
        logger.exception("Failed to load VK profile for %s", user_id)
        return {"title": f"id{user_id}", "avatar_url": ""}

    if not users:
        return {"title": f"id{user_id}", "avatar_url": ""}

    user = users[0]
    first_name = user.get("first_name") or ""
    last_name = user.get("last_name") or ""
    title = f"{first_name} {last_name}".strip() or f"id{user_id}"
    return {
        "title": title,
        "avatar_url": user.get("photo_100") or "",
    }


def upsert_incoming_message(message, notify=True):
    peer_id = message.get("peer_id")
    from_id = message.get("from_id")
    if not peer_id or not from_id:
        return None, False

    if int(peer_id) != int(from_id):
        return None, False

    vk_message_id = message.get("id") or message.get("conversation_message_id")
    text = message.get("text") or ""
    created_at = _message_datetime(message)
    attachments = _serialize_attachments(message.get("attachments") or [])

    with transaction.atomic():
        conversation = ensure_conversation(peer_id=peer_id, from_id=from_id)
        defaults = {
            "conversation": conversation,
            "from_id": int(from_id),
            "text": text,
            "attachments": attachments,
            "raw_payload": message,
            "created_at": created_at,
        }

        if vk_message_id is not None:
            vk_message, created = VkMessage.objects.get_or_create(
                peer_id=int(peer_id),
                vk_message_id=int(vk_message_id),
                direction=VkMessage.DIRECTION_INCOMING,
                defaults=defaults,
            )
        else:
            vk_message = VkMessage.objects.create(
                peer_id=int(peer_id),
                vk_message_id=None,
                direction=VkMessage.DIRECTION_INCOMING,
                **defaults,
            )
            created = True

        if created:
            conversation.last_message_text = _message_preview(text, attachments)
            conversation.last_message_at = created_at
            conversation.unread_count = conversation.unread_count + 1
            conversation.save(update_fields=["last_message_text", "last_message_at", "unread_count", "updated_at"])

            if notify:
                transaction.on_commit(lambda: notify_incoming_message(vk_message))

    return vk_message, created


def notify_incoming_message(message):
    conversation = message.conversation
    body = _message_preview(message.text, message.attachments)
    payload = {
        "title": conversation.title or f"VK id{conversation.from_id}",
        "body": body,
        "url": f"/vkchat/?peer_id={conversation.peer_id}",
        "tag": f"vkchat-{conversation.peer_id}",
        "peer_id": conversation.peer_id,
        "message_id": message.id,
    }
    send_web_push_to_all(payload)


def mark_conversation_read(peer_id):
    peer_id = int(peer_id)
    VkConversation.objects.filter(peer_id=peer_id).update(unread_count=0)
    try:
        get_vk_api().messages.markAsRead(peer_id=peer_id)
    except Exception:
        logger.exception("Failed to mark VK conversation %s as read", peer_id)


def sync_recent_conversations(limit=30):
    try:
        response = get_vk_api().messages.getConversations(count=limit)
    except Exception:
        logger.exception("Failed to sync VK conversations")
        raise

    synced = 0
    for item in response.get("items", []):
        conversation_info = item.get("conversation") or {}
        peer = conversation_info.get("peer") or {}
        if peer.get("type") != "user":
            continue

        last_message = item.get("last_message") or {}
        if not last_message:
            continue

        message, created = upsert_incoming_message(last_message, notify=False)
        if message:
            unread_count = conversation_info.get("unread_count")
            if unread_count is not None:
                VkConversation.objects.filter(peer_id=message.peer_id).update(unread_count=int(unread_count or 0))
            synced += 1 if created else 0

    return {"synced": synced, "total": response.get("count", 0)}


def serialize_conversation(conversation):
    return {
        "peer_id": conversation.peer_id,
        "from_id": conversation.from_id,
        "title": conversation.title or f"id{conversation.from_id}",
        "avatar_url": conversation.avatar_url,
        "last_message_text": conversation.last_message_text,
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        "unread_count": conversation.unread_count,
        "vk_url": f"https://vk.com/id{conversation.from_id}" if conversation.from_id > 0 else "",
    }


def serialize_message(message):
    return {
        "id": message.id,
        "vk_message_id": message.vk_message_id,
        "peer_id": message.peer_id,
        "from_id": message.from_id,
        "direction": message.direction,
        "text": message.text,
        "attachments": message.attachments,
        "created_at": message.created_at.isoformat(),
    }


def _message_datetime(message):
    raw_date = message.get("date")
    if raw_date:
        try:
            return datetime.fromtimestamp(int(raw_date), tz=datetime_timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    return timezone.now()


def _serialize_attachments(attachments):
    serialized = []
    for attachment in attachments:
        attachment_type = attachment.get("type") or "attachment"
        data = attachment.get(attachment_type) or {}
        item = {"type": attachment_type}

        if attachment_type == "photo":
            item["url"] = _best_photo_url(data)
        elif attachment_type in {"doc", "audio_message", "video"}:
            item["title"] = data.get("title") or data.get("link_ogg") or data.get("link_mp3") or ""
            item["url"] = data.get("url") or data.get("link_ogg") or data.get("link_mp3") or ""
        elif attachment_type == "link":
            item["title"] = data.get("title") or data.get("url") or ""
            item["url"] = data.get("url") or ""

        serialized.append(item)
    return serialized


def _best_photo_url(photo):
    sizes = photo.get("sizes") or []
    if not sizes:
        return ""
    best = sorted(sizes, key=lambda size: (size.get("width") or 0) * (size.get("height") or 0))[-1]
    return best.get("url") or ""


def _message_preview(text, attachments):
    text = (text or "").strip()
    if text:
        return text
    if attachments:
        labels = ", ".join(item.get("type", "attachment") for item in attachments[:3])
        return f"Вложение: {labels}"
    return "[без текста]"
