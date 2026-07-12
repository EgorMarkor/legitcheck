from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from webapp.models import VkConversation, VkMessage


@override_settings(SECURE_SSL_REDIRECT=False)
class VkChatApiTests(TestCase):
    def test_conversations_require_admin_login(self):
        response = self.client.get(reverse("vkchat_conversations"))

        self.assertEqual(response.status_code, 401)

    def test_conversations_return_saved_dialogs(self):
        admin = get_user_model().objects.create_user(
            username="admin",
            password="password",
            is_staff=True,
        )
        self.client.force_login(admin)

        conversation = VkConversation.objects.create(
            peer_id=123,
            from_id=123,
            title="Test User",
            last_message_text="Привет",
            last_message_at=timezone.now(),
            unread_count=1,
        )
        VkMessage.objects.create(
            conversation=conversation,
            vk_message_id=456,
            peer_id=123,
            from_id=123,
            direction=VkMessage.DIRECTION_INCOMING,
            text="Привет",
            created_at=timezone.now(),
        )

        response = self.client.get(reverse("vkchat_conversations"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["conversations"][0]["peer_id"], 123)
        self.assertEqual(payload["conversations"][0]["unread_count"], 1)
