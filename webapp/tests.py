import json
import re
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.utils import timezone

from pcwebapp.models import LoginToken
from webapp.models import (
    EmailOTPToken,
    HomePagePopularItem,
    Payment,
    PromoCode,
    PromoCodeRedemption,
    UploadedVerdictPhoto,
    User,
    Verdict,
    VerdictPhoto,
    TelegramVerdictDelivery,
)


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="webapp_tests_media_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class VerdictApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create(
            tgId=123456,
            img="https://example.com/avatar.png",
            name="Test User",
            balance="1000",
            username="testuser",
        )
        self.login_token = LoginToken.objects.create(
            token="ABC123",
            user=self.user,
            used_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.host = "legitcheck.one"

    def _image_file(self, name="test.gif"):
        content = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
            b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
            b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        )
        return SimpleUploadedFile(name, content, content_type="image/gif")

    def _login_web_session(self):
        session = self.client.session
        session["tg_id"] = self.user.tgId
        session.save()

    def test_free_verdict_create_does_not_change_balance_and_starts_cooldown(self):
        self._login_web_session()
        balance_before = self.user.balance

        response = self.client.post(
            "/verdict/create/free/",
            {
                "category": "sneakers",
                "brand": "Nike",
                "comment": "Free weekly check",
                "photos": self._image_file("free.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertFalse(payload["is_free_check_available"])
        self.assertIsNotNone(payload["next_free_check_timestamp"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, balance_before)
        self.assertFalse(self.user.is_free_check_available)
        self.assertGreater(self.user.next_free_check_timestamp, timezone.now() + timedelta(days=6))

        verdict = Verdict.objects.get(id=payload["verdict"]["id"])
        self.assertEqual(verdict.user, self.user)
        self.assertEqual(verdict.speed, "12h-free")
        self.assertEqual(str(verdict.price), "0.00")
        self.assertFalse(verdict.with_reason)
        self.assertEqual(verdict.photos.count(), 1)

    def test_free_verdict_create_rejects_active_cooldown(self):
        self.user.is_free_check_available = False
        self.user.next_free_check_timestamp = timezone.now() + timedelta(days=3)
        self.user.save(update_fields=["is_free_check_available", "next_free_check_timestamp"])
        self._login_web_session()

        response = self.client.post(
            "/verdict/create/free/",
            {
                "category": "sneakers",
                "brand": "Nike",
                "comment": "Blocked free check",
                "photos": self._image_file("blocked.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertFalse(payload["is_free_check_available"])
        self.assertIsNotNone(payload["next_free_check_timestamp"])
        self.assertEqual(Verdict.objects.count(), 0)

    def test_free_verdict_create_allows_after_cooldown_timestamp_passed(self):
        self.user.is_free_check_available = False
        self.user.next_free_check_timestamp = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=["is_free_check_available", "next_free_check_timestamp"])
        self._login_web_session()

        response = self.client.post(
            "/verdict/create/free/",
            {
                "category": "sneakers",
                "brand": "Nike",
                "comment": "Expired cooldown",
                "photos": self._image_file("expired.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["success"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_free_check_available)
        self.assertGreater(self.user.next_free_check_timestamp, timezone.now() + timedelta(days=6))

    def test_check_page_renders_free_check_tariff_state(self):
        self._login_web_session()

        response = self.client.get("/check/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="free-check-tariff"')
        self.assertContains(response, 'createUrl: "/verdict/create/free/"')
        self.assertContains(response, 'isAvailable: true')
        self.assertContains(response, "data-active-src=")
        self.assertContains(response, "data-inactive-src=")

    def test_check_templates_only_reference_existing_static_files(self):
        template_paths = (
            Path(settings.BASE_DIR) / "webapp/templates/check.html",
            Path(settings.BASE_DIR) / "pcwebapp/templates/pc/check.html",
        )
        missing = []

        for template_path in template_paths:
            source = template_path.read_text(encoding="utf-8")
            static_names = set(
                re.findall(r"""{%\s*static\s+['"]([^'"]+)['"]\s*%}""", source)
            )
            missing.extend(
                f"{template_path.name}: {name}"
                for name in sorted(static_names)
                if finders.find(name) is None
            )

        self.assertEqual(missing, [])

    def test_paid_verdict_uses_basic_tariff_for_regular_brand(self):
        self._login_web_session()

        response = self.client.post(
            "/verdict/create/",
            {
                "category": "sneakers",
                "brand": "Nike",
                "speed": "standard",
                "with_reason": "0",
                "photos": self._image_file("basic.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, "851.00")

        verdict = Verdict.objects.latest("id")
        self.assertEqual(verdict.brand, "Nike")
        self.assertEqual(verdict.speed, "standard")
        self.assertEqual(str(verdict.price), "149.00")

    def test_paid_verdict_is_idempotent_for_repeated_submit(self):
        self._login_web_session()

        payload = {
            "category": "sneakers",
            "brand": "Nike",
            "speed": "standard",
            "with_reason": "0",
            "idempotency_key": "paid-repeat-1",
        }
        first_response = self.client.post(
            "/verdict/create/",
            {**payload, "photos": self._image_file("first.gif")},
            HTTP_HOST=self.host,
        )
        second_response = self.client.post(
            "/verdict/create/",
            {**payload, "photos": self._image_file("second.gif")},
            HTTP_HOST=self.host,
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(first_response.json()["success"])
        self.assertTrue(second_response.json()["success"])
        self.assertTrue(second_response.json()["duplicate"])
        self.assertEqual(Verdict.objects.count(), 1)
        self.assertEqual(VerdictPhoto.objects.count(), 1)

        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, "851.00")

    def test_paid_verdict_uses_luxury_tariff_for_luxury_brand(self):
        self._login_web_session()

        response = self.client.post(
            "/verdict/create/",
            {
                "category": "bags",
                "brand": "Dior",
                "speed": "express",
                "with_reason": "0",
                "photos": self._image_file("luxury.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, "1.00")

        verdict = Verdict.objects.latest("id")
        self.assertEqual(verdict.brand, "Dior")
        self.assertEqual(verdict.speed, "express")
        self.assertEqual(str(verdict.price), "999.00")

    def test_upload_then_create_verdict_with_uploaded_photo_ids(self):
        upload_response = self.client.post(
            "/api/verdict/photos/upload/",
            {"photo": self._image_file()},
            HTTP_HOST=self.host,
            HTTP_X_AUTH_TOKEN=self.login_token.token,
        )
        self.assertEqual(upload_response.status_code, 201)
        upload_json = upload_response.json()
        self.assertTrue(upload_json["success"])
        self.assertEqual(len(upload_json["photo_ids"]), 1)
        photo_id = upload_json["photo_ids"][0]

        create_payload = {
            "category": "sneakers",
            "brand": "Nike",
            "comment": "API created verdict",
            "photo_ids": [photo_id],
        }
        create_response = self.client.post(
            "/api/verdict/create/",
            data=json.dumps(create_payload),
            content_type="application/json",
            HTTP_HOST=self.host,
            HTTP_X_AUTH_TOKEN=self.login_token.token,
        )

        self.assertEqual(create_response.status_code, 201)
        create_json = create_response.json()
        self.assertTrue(create_json["success"])

        verdict = Verdict.objects.get(id=create_json["verdict"]["id"])
        self.assertEqual(verdict.user, self.user)
        self.assertEqual(verdict.photos.count(), 1)

        uploaded = UploadedVerdictPhoto.objects.get(id=photo_id)
        self.assertEqual(uploaded.verdict_id, verdict.id)
        self.assertIsNotNone(uploaded.used_at)

    def test_api_create_verdict_is_idempotent_after_uploaded_photo_used(self):
        upload_response = self.client.post(
            "/api/verdict/photos/upload/",
            {"photo": self._image_file("api-once.gif")},
            HTTP_HOST=self.host,
            HTTP_X_AUTH_TOKEN=self.login_token.token,
        )
        self.assertEqual(upload_response.status_code, 201)
        photo_id = upload_response.json()["photo_ids"][0]

        create_payload = {
            "category": "sneakers",
            "brand": "Nike",
            "comment": "API repeat",
            "photo_ids": [photo_id],
            "idempotency_key": "api-repeat-1",
        }
        first_response = self.client.post(
            "/api/verdict/create/",
            data=json.dumps(create_payload),
            content_type="application/json",
            HTTP_HOST=self.host,
            HTTP_X_AUTH_TOKEN=self.login_token.token,
        )
        second_response = self.client.post(
            "/api/verdict/create/",
            data=json.dumps(create_payload),
            content_type="application/json",
            HTTP_HOST=self.host,
            HTTP_X_AUTH_TOKEN=self.login_token.token,
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(first_response.json()["success"])
        self.assertTrue(second_response.json()["success"])
        self.assertTrue(second_response.json()["duplicate"])
        self.assertEqual(
            first_response.json()["verdict"]["id"],
            second_response.json()["verdict"]["id"],
        )
        self.assertEqual(Verdict.objects.count(), 1)
        self.assertEqual(VerdictPhoto.objects.count(), 1)

    def test_api_create_verdict_requires_photos(self):
        payload = {
            "category": "sneakers",
            "brand": "Nike",
            "comment": "No photos",
        }
        response = self.client.post(
            "/api/verdict/create/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_HOST=self.host,
            HTTP_X_AUTH_TOKEN=self.login_token.token,
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_mobile_upload_then_create_verdict_with_tg_id(self):
        upload_response = self.client.post(
            "/api/mobile/verdict/photos/upload/",
            {
                "tg_id": str(self.user.tgId),
                "photo": self._image_file("mobile.gif"),
            },
            HTTP_HOST=self.host,
        )
        self.assertEqual(upload_response.status_code, 201)
        upload_json = upload_response.json()
        self.assertTrue(upload_json["success"])
        photo_id = upload_json["photo_ids"][0]

        create_response = self.client.post(
            "/api/mobile/verdict/create/",
            data=json.dumps(
                {
                    "tg_id": self.user.tgId,
                    "category": "sneakers",
                    "brand": "Nike",
                    "comment": "Mobile API create",
                    "photo_ids": [photo_id],
                }
            ),
            content_type="application/json",
            HTTP_HOST=self.host,
        )

        self.assertEqual(create_response.status_code, 201)
        create_json = create_response.json()
        self.assertTrue(create_json["success"])

        verdict = Verdict.objects.get(id=create_json["verdict"]["id"])
        self.assertEqual(verdict.user_id, self.user.tgId)
        self.assertEqual(verdict.photos.count(), 1)

    def test_mobile_create_verdict_requires_tg_id(self):
        response = self.client.post(
            "/api/mobile/verdict/create/",
            data=json.dumps(
                {
                    "category": "sneakers",
                    "brand": "Nike",
                    "comment": "Missing tg_id",
                }
            ),
            content_type="application/json",
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_mobile_get_verdict_by_code(self):
        verdict = Verdict.objects.create(
            user=self.user,
            status="legit",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="manager comment",
            comment_from_user="user comment",
            code="55555",
            speed="24h",
            price="450.00",
            with_reason=False,
        )

        response = self.client.get(
            f"/api/mobile/verdict/by-code/{verdict.code}/",
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["verdict"]["id"], verdict.id)
        self.assertEqual(payload["verdict"]["status"], "legit")
        self.assertEqual(payload["verdict"]["status_display"], "Оригинал")
        self.assertEqual(payload["verdict"]["code"], "55555")

    def test_web_verdict_page_allows_owner_and_disables_code_inputs(self):
        self._login_web_session()
        verdict = Verdict.objects.create(
            user=self.user,
            status="legit",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="manager comment",
            comment_from_user="user comment",
            code="13579",
            speed="24h",
            price="450.00",
            with_reason=False,
        )
        VerdictPhoto.objects.create(verdict=verdict, image=self._image_file("owner.gif"))

        response = self.client.get(
            f"/verdict/?code={verdict.code}",
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="1" disabled readonly aria-disabled="true"')
        self.assertContains(response, 'value="9" disabled readonly aria-disabled="true"')
        self.assertContains(response, 'id="extra-photo-input"')

    def test_web_verdict_page_does_not_show_other_users_verdict(self):
        other_user = User.objects.create(
            tgId=654321,
            img="https://example.com/other.png",
            name="Other User",
            balance="0",
            username="other",
        )
        verdict = Verdict.objects.create(
            user=other_user,
            status="legit",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="manager comment",
            comment_from_user="user comment",
            code="24680",
            speed="24h",
            price="450.00",
            with_reason=False,
        )
        self._login_web_session()

        response = self.client.get(
            f"/verdict/?code={verdict.code}",
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/verdicts/?error=not_found&code={verdict.code}")

    def test_web_upload_photo_to_other_users_verdict_is_rejected(self):
        other_user = User.objects.create(
            tgId=654322,
            img="https://example.com/other2.png",
            name="Other User 2",
            balance="0",
            username="other2",
        )
        verdict = Verdict.objects.create(
            user=other_user,
            status="inpending",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="",
            comment_from_user="user comment",
            code="97531",
            speed="24h",
            price="450.00",
            with_reason=False,
        )
        self._login_web_session()

        response = self.client.post(
            f"/verdict/{verdict.id}/upload-photo/",
            {"photo": self._image_file("blocked-extra.gif")},
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 404)

    def test_verdicts_api_supports_code_filter(self):
        Verdict.objects.create(
            user=self.user,
            status="legit",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="first",
            comment_from_user="first",
            code="11111",
            speed="24h",
            price="450.00",
            with_reason=False,
        )
        target_verdict = Verdict.objects.create(
            user=self.user,
            status="fake",
            category="sneakers",
            brand="Adidas",
            item_model="Campus",
            comment="second",
            comment_from_user="second",
            code="22222",
            speed="24h",
            price="450.00",
            with_reason=False,
        )

        response = self.client.get(
            "/api/verdicts/?code=22222",
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], target_verdict.id)
        self.assertEqual(payload[0]["code"], "22222")

    def test_mobile_upload_photo_to_existing_verdict(self):
        verdict = Verdict.objects.create(
            user=self.user,
            status="inpending",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="",
            comment_from_user="user comment",
            code="44444",
            speed="24h",
            price="450.00",
            with_reason=False,
        )

        response = self.client.post(
            f"/api/mobile/verdict/{verdict.id}/upload-photo/",
            {
                "tg_id": str(self.user.tgId),
                "photo": self._image_file("verdict-extra.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["photos"]), 1)
        verdict.refresh_from_db()
        self.assertEqual(verdict.photos.count(), 1)

    def test_web_login_with_token_sets_session(self):
        response = self.client.post(
            f"/api/auth/web-login/{self.login_token.token}/",
            data="{}",
            content_type="application/json",
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["user"]["tgId"], self.user.tgId)

        session = self.client.session
        self.assertEqual(session.get("tg_id"), self.user.tgId)

    @override_settings(
        APP_REVIEW_DEMO_EMAIL="egor20080801@yandex.ru",
        APP_REVIEW_DEMO_PASSWORD="1111",
        APP_REVIEW_DEMO_BALANCE="5000",
        SECURE_SSL_REDIRECT=False,
    )
    def test_email_login_accepts_configured_app_review_demo_password(self):
        response = self.client.post(
            "/email/send-otp/",
            {
                "email": "Egor20080801@yandex.ru",
                "password": "1111",
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/home/")

        user = User.objects.get(email="egor20080801@yandex.ru")
        self.assertEqual(user.name, "App Review Demo")
        self.assertEqual(user.balance, "5000.00")
        self.assertTrue(user.is_free_check_available)
        self.assertIsNone(user.next_free_check_timestamp)
        self.assertEqual(self.client.session.get("tg_id"), user.tgId)
        self.assertEqual(
            EmailOTPToken.objects.filter(email__iexact="egor20080801@yandex.ru").count(),
            0,
        )

    @override_settings(
        APP_REVIEW_DEMO_EMAIL="egor20080801@yandex.ru",
        APP_REVIEW_DEMO_PASSWORD="1111",
        SECURE_SSL_REDIRECT=False,
    )
    def test_email_login_rejects_wrong_demo_password_without_sending_otp(self):
        response = self.client.post(
            "/email/send-otp/",
            {
                "email": "Egor20080801@yandex.ru",
                "password": "wrong",
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/email-login/?error=invalid_credentials")
        self.assertFalse(User.objects.filter(email__iexact="egor20080801@yandex.ru").exists())
        self.assertEqual(
            EmailOTPToken.objects.filter(email__iexact="egor20080801@yandex.ru").count(),
            0,
        )
        self.assertNotIn("tg_id", self.client.session)

    def test_index_renders_by_session_without_init_data(self):
        popular_item = HomePagePopularItem.objects.get(position=1)
        popular_item.title = "Nike Dunk"
        popular_item.subtitle = "Panda"
        popular_item.views_count = 999
        popular_item.save()

        session = self.client.session
        session["tg_id"] = self.user.tgId
        session.save()

        response = self.client.get("/home/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "index.html")
        self.assertEqual(len(response.context["popular_models"]), 5)
        self.assertEqual(response.context["popular_models"][0].title, "Nike Dunk")
        self.assertContains(response, "Nike Dunk")

    def test_account_delete_requires_login(self):
        response = self.client.get("/account/delete/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_account_delete_requires_confirmation(self):
        self._login_web_session()

        response = self.client.post("/account/delete/", {}, HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertContains(response, "Подтвердите удаление аккаунта.", status_code=400)

    def test_account_delete_removes_user_data_and_clears_session(self):
        self.user.email = "delete@example.com"
        self.user.save(update_fields=["email"])
        self._login_web_session()

        verdict = Verdict.objects.create(
            user=self.user,
            status="inpending",
            category="sneakers",
            brand="Nike",
            item_model="Dunk",
            comment="manager comment",
            comment_from_user="user comment",
            code="54321",
            speed="24h",
            price="450.00",
            with_reason=False,
        )
        verdict_photo = VerdictPhoto.objects.create(
            verdict=verdict,
            image=self._image_file("delete-verdict.gif"),
        )
        uploaded_photo = UploadedVerdictPhoto.objects.create(
            user=self.user,
            image=self._image_file("delete-upload.gif"),
        )
        payment = Payment.objects.create(
            user=self.user,
            amount="149.00",
            status="COMPLETED",
        )
        promo_code = PromoCode.objects.create(code="DELETE", reward_amount="10.00")
        PromoCodeRedemption.objects.create(
            promo_code=promo_code,
            user=self.user,
            amount="10.00",
        )
        EmailOTPToken.objects.create(email=self.user.email, code="123456")

        media_paths = [verdict_photo.image.name, uploaded_photo.image.name]
        for path in media_paths:
            self.assertTrue(default_storage.exists(path))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/account/delete/",
                {"confirm_delete": "1"},
                HTTP_HOST=self.host,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account_deleted.html")
        self.assertContains(response, "checker_auth_token")

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(Verdict.objects.filter(pk=verdict.pk).count(), 0)
        self.assertEqual(VerdictPhoto.objects.filter(pk=verdict_photo.pk).count(), 0)
        self.assertEqual(UploadedVerdictPhoto.objects.filter(pk=uploaded_photo.pk).count(), 0)
        self.assertEqual(PromoCodeRedemption.objects.filter(user_id=self.user.pk).count(), 0)
        self.assertEqual(EmailOTPToken.objects.filter(email__iexact=self.user.email).count(), 0)
        self.assertEqual(LoginToken.objects.filter(user_id=self.user.pk).count(), 0)

        payment.refresh_from_db()
        self.assertIsNone(payment.user_id)
        self.assertNotIn("tg_id", self.client.session)

        for path in media_paths:
            self.assertFalse(default_storage.exists(path))

    @override_settings(
        TELEGRAM_VERDICT_CHAT_15_30M_ID="-100",
        TELEGRAM_VERDICT_CHAT_1H_ID="-101",
        TELEGRAM_VERDICT_CHAT_2H_ID="-102",
        TELEGRAM_VERDICT_CHAT_12H_ID="-112",
    )
    def test_telegram_verdict_groups_and_repeat_intervals(self):
        from webapp.views import _telegram_delivery_policy

        expected = {
            "express": ("-100", 30, 15),
            "fast": ("-101", 60, 15),
            "standard": ("-102", 120, 30),
            "12h-free": ("-112", 720, 60),
        }
        for speed, (chat_id, lifetime_minutes, interval_minutes) in expected.items():
            verdict = Verdict(user=self.user, speed=speed)
            actual_chat, lifetime, interval = _telegram_delivery_policy(verdict)
            self.assertEqual(actual_chat, chat_id)
            self.assertEqual(lifetime, timedelta(minutes=lifetime_minutes))
            self.assertEqual(interval, timedelta(minutes=interval_minutes))

    @override_settings(
        YOOKASSA_ACCOUNT_ID="shop-id",
        YOOKASSA_SECRET_KEY="secret",
        SECURE_SSL_REDIRECT=False,
    )
    @patch("webapp.views.YooPayment.find_one")
    def test_yookassa_webhook_verifies_and_credits_only_once(self, find_one):
        payment = Payment.objects.create(
            user=self.user,
            amount="100.00",
            status="PENDING",
            provider_payment_id="provider-1",
        )
        find_one.return_value = SimpleNamespace(
            status="succeeded",
            paid=True,
            amount=SimpleNamespace(value="100.00", currency="RUB"),
        )
        body = json.dumps({
            "event": "payment.succeeded",
            "object": {"id": payment.provider_payment_id, "amount": {"value": "999999.00"}},
        })

        for _ in range(2):
            response = self.client.post(
                "/yookassa/webhook/",
                data=body,
                content_type="application/json",
                HTTP_HOST=self.host,
            )
            self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.user.balance, "1100.00")
        self.assertEqual(payment.status, "COMPLETED")
