from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("webapp", "0006_promocode_and_promocoderedemption"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_free_check_available",
            field=models.BooleanField(default=True, verbose_name="Бесплатная проверка доступна"),
        ),
        migrations.AddField(
            model_name="user",
            name="next_free_check_timestamp",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Следующая бесплатная проверка"),
        ),
    ]
