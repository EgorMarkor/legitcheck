import json
import shutil
import tempfile
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from pcwebapp.models import LoginToken, UploadedVerdictPhoto
from webapp.models import User, Verdict


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="pcwebapp_tests_media_")


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
        self.host = "checkerlegit.com"

    def _image_file(self, name="test.gif"):
        content = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
            b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
            b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        )
        return SimpleUploadedFile(name, content, content_type="image/gif")

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

    def test_legacy_create_verdict_sets_required_defaults(self):
        session = self.client.session
        session["tg_id"] = self.user.tgId
        session.save()

        response = self.client.post(
            "/verdict/create/",
            {
                "category": "sneakers",
                "brand": "Nike",
                "comment": "legacy create",
                "photos": self._image_file("legacy.gif"),
            },
            HTTP_HOST=self.host,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        verdict = Verdict.objects.order_by("-id").first()
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.speed, "24h")
        self.assertEqual(verdict.price, Decimal("0.00"))
        self.assertFalse(verdict.with_reason)
