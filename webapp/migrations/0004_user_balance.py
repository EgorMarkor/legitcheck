# Generated by Django 5.2 on 2025-05-11 12:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapp', '0003_verdict_comment_alter_verdict_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='balance',
            field=models.CharField(default=1, max_length=255, verbose_name='Баланс'),
            preserve_default=False,
        ),
    ]
