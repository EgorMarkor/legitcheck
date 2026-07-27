from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pcwebapp.models import LoginToken
from telegram_login_bot import (
    LoginTokenExpired,
    LoginTokenUnavailable,
    _apply_verdict_decision,
    _claim_login_token,
)
from webapp.models import TelegramVerdictDelivery, User, Verdict


class ClaimLoginTokenTests(TestCase):
    def setUp(self):
        self.user_data = {
            "tgId": 123456,
            "username": "testuser",
            "full_name": "Test User",
        }

    def test_claims_token_and_creates_user(self):
        token = LoginToken.objects.create(
            token="ABC123",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        user = _claim_login_token(token.token, self.user_data)

        token.refresh_from_db()
        self.assertEqual(token.user, user)
        self.assertEqual(token.telegram_id, user.tgId)
        self.assertIsNotNone(token.used_at)
        self.assertEqual(user.img, "/static/avatar-placeholder.png")

    def test_used_token_cannot_be_claimed_twice(self):
        token = LoginToken.objects.create(
            token="ABC123",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        _claim_login_token(token.token, self.user_data)

        with self.assertRaises(LoginTokenUnavailable):
            _claim_login_token(token.token, self.user_data)

        self.assertEqual(User.objects.count(), 1)

    def test_expired_token_is_rejected(self):
        token = LoginToken.objects.create(
            token="ABC123",
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        with self.assertRaises(LoginTokenExpired):
            _claim_login_token(token.token, self.user_data)

        token.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertEqual(User.objects.count(), 0)

    def test_verdict_callback_must_come_from_delivery_chat(self):
        user = User.objects.create(
            tgId=654321,
            name="Verifier",
            img="/static/avatar-placeholder.png",
            balance="0",
        )
        verdict = Verdict.objects.create(
            user=user,
            status="inpending",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="",
            comment_from_user="",
            code="12345",
            speed="fast",
            price="299.00",
        )
        TelegramVerdictDelivery.objects.create(
            verdict=verdict,
            chat_id="-100123",
            message_ids=[10],
            interval_minutes=15,
            expires_at=timezone.now() + timedelta(hours=1),
            next_send_at=timezone.now() + timedelta(minutes=15),
        )

        with self.assertRaises(PermissionError):
            _apply_verdict_decision(verdict.id, "legit", -100999)

        verdict.refresh_from_db()
        self.assertEqual(verdict.status, "inpending")

        _apply_verdict_decision(verdict.id, "legit", -100123)
        verdict.refresh_from_db()
        self.assertEqual(verdict.status, "legit")
