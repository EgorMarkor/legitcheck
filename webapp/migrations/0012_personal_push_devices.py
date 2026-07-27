from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("webapp", "0011_telegramverdictdelivery"),
    ]

    operations = [
        migrations.AddField(
            model_name="webpushsubscription",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="web_push_subscriptions",
                to="webapp.user",
            ),
        ),
        migrations.CreateModel(
            name="NativePushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform", models.CharField(choices=[("ios", "iOS"), ("android", "Android")], max_length=16)),
                ("token", models.CharField(max_length=512, unique=True)),
                ("bundle_id", models.CharField(blank=True, max_length=255)),
                ("environment", models.CharField(default="production", max_length=16)),
                ("active", models.BooleanField(default=True)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="native_push_devices", to="webapp.user")),
            ],
            options={
                "verbose_name": "Нативное push-устройство",
                "verbose_name_plural": "Нативные push-устройства",
                "ordering": ("-updated_at",),
                "indexes": [models.Index(fields=["user", "active", "platform"], name="nativepush_user_active_idx")],
            },
        ),
    ]
