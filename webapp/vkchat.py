import json

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import VkConversation, WebPushSubscription
from .vk_service import (
    mark_conversation_read,
    send_vk_reply,
    serialize_conversation,
    serialize_message,
    sync_recent_conversations,
)


@staff_member_required(login_url="/admin/login/")
@ensure_csrf_cookie
def vkchat_app(request):
    return render(
        request,
        "vk_chat.html",
        {
            "vapid_public_key": settings.VKCHAT_VAPID_PUBLIC_KEY,
        },
    )


@require_GET
def vkchat_manifest(request):
    manifest = {
        "id": "/vkchat/",
        "name": "VK Чаты LegitCheck",
        "short_name": "VK Чаты",
        "description": "Ответы на сообщения VK сообщества LegitCheck.",
        "lang": "ru",
        "start_url": "/vkchat/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "orientation": "portrait",
        "background_color": "#f3f5f8",
        "theme_color": "#0077ff",
        "icons": [
            {
                "src": "/static/pwa/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/pwa/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/pwa/apple-touch-icon-180.png",
                "sizes": "180x180",
                "type": "image/png",
            },
        ],
        "categories": ["social", "productivity", "utilities"],
    }
    return JsonResponse(manifest, json_dumps_params={"ensure_ascii": False})


@require_GET
def vkchat_config(request):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    return JsonResponse(
        {
            "vapid_public_key": settings.VKCHAT_VAPID_PUBLIC_KEY,
            "push_configured": bool(settings.VKCHAT_VAPID_PUBLIC_KEY and settings.VKCHAT_VAPID_PRIVATE_KEY),
        }
    )


@require_GET
def vkchat_conversations(request):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    conversations = VkConversation.objects.order_by("-last_message_at", "-updated_at")[:100]
    return JsonResponse(
        {
            "conversations": [serialize_conversation(conversation) for conversation in conversations],
        },
        json_dumps_params={"ensure_ascii": False},
    )


@require_http_methods(["GET", "POST"])
def vkchat_messages(request, peer_id):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    if request.method == "POST":
        payload = _json_payload(request)
        text = (payload.get("text") or "").strip()
        if not text:
            return JsonResponse({"success": False, "error": "Введите текст ответа"}, status=400)

        try:
            message = send_vk_reply(peer_id=peer_id, text=text)
        except Exception as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

        return JsonResponse(
            {"success": True, "message": serialize_message(message)},
            json_dumps_params={"ensure_ascii": False},
        )

    conversation = VkConversation.objects.filter(peer_id=peer_id).first()
    if not conversation:
        return JsonResponse({"success": False, "error": "Диалог не найден"}, status=404)

    messages = conversation.messages.order_by("-created_at", "-id")[:100]
    messages = list(reversed(messages))
    return JsonResponse(
        {
            "conversation": serialize_conversation(conversation),
            "messages": [serialize_message(message) for message in messages],
        },
        json_dumps_params={"ensure_ascii": False},
    )


@require_http_methods(["POST"])
def vkchat_mark_read(request, peer_id):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    mark_conversation_read(peer_id)
    return JsonResponse({"success": True})


@require_http_methods(["POST"])
def vkchat_sync(request):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    result = sync_recent_conversations()
    return JsonResponse({"success": True, **result})


@require_http_methods(["POST"])
def vkchat_push_subscribe(request):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    payload = _json_payload(request)
    endpoint = (payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()

    if not endpoint or not p256dh or not auth:
        return JsonResponse({"success": False, "error": "Некорректная push-подписка"}, status=400)

    WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "active": True,
            "last_error": "",
        },
    )
    return JsonResponse({"success": True})


@require_http_methods(["POST"])
def vkchat_push_unsubscribe(request):
    auth_error = _require_vkchat_auth(request)
    if auth_error:
        return auth_error

    payload = _json_payload(request)
    endpoint = (payload.get("endpoint") or "").strip()
    if endpoint:
        WebPushSubscription.objects.filter(endpoint=endpoint).update(active=False)
    return JsonResponse({"success": True})


def _require_vkchat_auth(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Не авторизован"}, status=401)

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Недостаточно прав"}, status=403)

    return None


def _json_payload(request):
    if request.method == "GET" or not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
