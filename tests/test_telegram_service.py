import os
import tempfile
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from webapp import telegram


class TelegramApiCallTests(SimpleTestCase):
    @patch("webapp.telegram._get_session")
    def test_logs_telegram_error_description(self, get_session):
        response = Mock()
        response.status_code = 400
        response.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: chat not found",
        }
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        get_session.return_value.post.return_value = response

        with self.assertLogs("webapp.telegram", level="WARNING") as logs:
            result = telegram.api_call(
                "secret-token",
                "sendMessage",
                {"chat_id": "invalid", "text": "test"},
            )

        self.assertIsNone(result)
        self.assertIn("status=400", logs.output[0])
        self.assertIn("description=Bad Request: chat not found", logs.output[0])
        self.assertNotIn("secret-token", logs.output[0])

    @patch("webapp.telegram._get_session")
    def test_rejects_unsuccessful_telegram_json_response(self, get_session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "ok": False,
            "description": "Telegram rejected the request",
        }
        get_session.return_value.post.return_value = response

        with self.assertLogs("webapp.telegram", level="WARNING"):
            result = telegram.api_call("secret-token", "sendMessage", {})

        self.assertIsNone(result)


class TelegramAvatarTests(SimpleTestCase):
    @override_settings(MEDIA_URL="/media/")
    @patch("webapp.telegram._get_avatar_cdn_url")
    @patch("webapp.telegram._get_session")
    def test_caches_each_user_avatar_under_a_unique_name(
        self,
        get_session,
        get_avatar_cdn_url,
    ):
        response = Mock()
        response.content = b"avatar-bytes"
        get_session.return_value.get.return_value = response
        get_avatar_cdn_url.side_effect = [
            "https://api.telegram.org/file/bot-token/photos/one.jpg",
            "https://api.telegram.org/file/bot-token/photos/two.jpg",
        ]

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                first_url = telegram.download_and_cache_avatar("token", 111)
                second_url = telegram.download_and_cache_avatar("token", 222)

            self.assertEqual(first_url, "/media/avatars/111.jpg")
            self.assertEqual(second_url, "/media/avatars/222.jpg")
            self.assertTrue(os.path.exists(os.path.join(media_root, "avatars", "111.jpg")))
            self.assertTrue(os.path.exists(os.path.join(media_root, "avatars", "222.jpg")))
