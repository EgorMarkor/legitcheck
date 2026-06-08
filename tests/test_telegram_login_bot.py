from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pcwebapp.models import LoginToken
from telegram_login_bot import (
    LoginTokenExpired,
    LoginTokenUnavailable,
    _claim_login_token,
)
from webapp.models import User


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
        self.assertEqual(user.img, "/static/avatar.png")

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
