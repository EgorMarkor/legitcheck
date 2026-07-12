from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("webapp", "0010_alter_verdictphoto_options_and_more")]

    operations = [
        migrations.CreateModel(
            name="TelegramVerdictDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chat_id", models.CharField(max_length=64)),
                ("message_ids", models.JSONField(blank=True, default=list)),
                ("interval_minutes", models.PositiveIntegerField()),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("next_send_at", models.DateTimeField(db_index=True)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("verdict", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_delivery", to="webapp.verdict")),
            ],
            options={
                "verbose_name": "Доставка вердикта в Telegram",
                "verbose_name_plural": "Доставки вердиктов в Telegram",
            },
        ),
        migrations.AddIndex(
            model_name="telegramverdictdelivery",
            index=models.Index(fields=["active", "next_send_at"], name="tgdelivery_due_idx"),
        ),
    ]
