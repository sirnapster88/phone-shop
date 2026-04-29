from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operators', '0012_telegramchatcleanuptask'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramcustomer',
            name='pending_chat_message_ids',
            field=models.JSONField(blank=True, default=list, verbose_name='Ожидающие ID сообщений Telegram'),
        ),
        migrations.AddField(
            model_name='telegramcustomerrequest',
            name='extra_message_ids',
            field=models.JSONField(blank=True, default=list, verbose_name='Дополнительные ID сообщений Telegram'),
        ),
    ]
