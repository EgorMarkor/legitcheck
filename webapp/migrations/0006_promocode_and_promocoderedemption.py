from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("webapp", "0005_homepagepopularitem"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromoCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(help_text="Сохраняется в верхнем регистре.", max_length=64, unique=True, verbose_name="Промокод")),
                ("reward_amount", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Сумма начисления")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлен")),
            ],
            options={
                "verbose_name": "Промокод",
                "verbose_name_plural": "Промокоды",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="PromoCodeRedemption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Начислено")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Активирован")),
                (
                    "promo_code",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="redemptions",
                        to="webapp.promocode",
                        verbose_name="Промокод",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promo_code_redemptions",
                        to="webapp.user",
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Активация промокода",
                "verbose_name_plural": "Активации промокодов",
                "ordering": ("-created_at",),
                "unique_together": {("promo_code", "user")},
            },
        ),
    ]
