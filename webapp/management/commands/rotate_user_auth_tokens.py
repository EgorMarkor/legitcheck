import uuid

from django.core.management.base import BaseCommand

from webapp.models import User


class Command(BaseCommand):
    help = "Rotate every persistent API bearer token after a credential incident."

    def handle(self, *args, **options):
        rotated = 0
        for user in User.objects.only("pk").iterator(chunk_size=500):
            User.objects.filter(pk=user.pk).update(auth_token=uuid.uuid4())
            rotated += 1
        self.stdout.write(self.style.SUCCESS(f"Rotated {rotated} user auth token(s)."))
