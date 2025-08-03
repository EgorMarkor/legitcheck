import csv
from django.core.management.base import BaseCommand
from pcwebapp.models import Brand


class Command(BaseCommand):
    help = 'Import brands from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        path = options['csv_file']
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                obj, created = Brand.objects.update_or_create(
                    brand_id=row['brand_id'],
                    defaults={
                        'brand': row['brand'],
                        'logo_url': row['logo_url'],
                        'category': row['category'],
                    }
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Imported {count} brands."))