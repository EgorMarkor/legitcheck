from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

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
