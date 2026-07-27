import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from webapp.models import NativePushDevice, User, WebPushSubscription
from webapp.webpush import send_web_push_to_all, send_web_push_to_user


class PushRegistrationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            tgId=741852,
            img="/static/avatar-placeholder.png",
            name="Push User",
            balance="0",
        )
        session = self.client.session
        session["tg_id"] = self.user.pk
        session.save()

    @override_settings(
        WEB_PUSH_VAPID_PUBLIC_KEY="public-key",
        WEB_PUSH_VAPID_PRIVATE_KEY="private-key",
    )
    def test_config_and_web_subscription_are_bound_to_session_user(self):
        config = self.client.get("/api/push/config/")
        self.assertEqual(config.status_code, 200)
        self.assertTrue(config.json()["web_push_enabled"])

        response = self.client.post(
            "/api/push/web/subscribe/",
            data=json.dumps({
                "endpoint": "https://push.example.test/subscription/123",
                "keys": {"p256dh": "public", "auth": "secret"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        subscription = WebPushSubscription.objects.get()
        self.assertEqual(subscription.user, self.user)
        self.assertTrue(subscription.active)

    def test_native_token_is_bound_to_session_user(self):
        response = self.client.post(
            "/api/push/native/register/",
            data=json.dumps({
                "platform": "ios",
                "token": "a" * 64,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        device = NativePushDevice.objects.get()
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.bundle_id, "com.markor.legitcheck")

    def test_invalid_web_endpoint_is_rejected(self):
        response = self.client.post(
            "/api/push/web/subscribe/",
            data=json.dumps({
                "endpoint": "http://insecure.example.test/subscription",
                "keys": {"p256dh": "public", "auth": "secret"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class PushTargetingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            tgId=963258,
            img="/static/avatar-placeholder.png",
            name="Target User",
            balance="0",
        )
        self.legacy = WebPushSubscription.objects.create(
            endpoint="https://push.example.test/legacy",
            p256dh="legacy-public",
            auth="legacy-auth",
        )
        self.personal = WebPushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.test/personal",
            p256dh="personal-public",
            auth="personal-auth",
        )

    @override_settings(
        WEB_PUSH_VAPID_PUBLIC_KEY="public-key",
        WEB_PUSH_VAPID_PRIVATE_KEY="private-key",
    )
    @patch("pywebpush.webpush")
    def test_personal_and_legacy_pushes_do_not_cross(self, mocked_webpush):
        payload = {"title": "Checker", "body": "Test"}

        self.assertEqual(send_web_push_to_user(self.user.pk, payload), 1)
        personal_endpoint = mocked_webpush.call_args.kwargs["subscription_info"]["endpoint"]
        self.assertEqual(personal_endpoint, self.personal.endpoint)

        mocked_webpush.reset_mock()
        self.assertEqual(send_web_push_to_all(payload), 1)
        legacy_endpoint = mocked_webpush.call_args.kwargs["subscription_info"]["endpoint"]
        self.assertEqual(legacy_endpoint, self.legacy.endpoint)
