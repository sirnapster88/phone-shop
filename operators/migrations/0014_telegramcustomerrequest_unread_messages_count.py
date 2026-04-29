from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operators', '0013_telegramcustomer_pending_chat_message_ids_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramcustomerrequest',
            name='unread_messages_count',
            field=models.PositiveIntegerField(default=1, verbose_name='Количество непрочитанных сообщений клиента'),
        ),
    ]
