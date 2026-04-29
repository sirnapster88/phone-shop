from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operators', '0004_alter_aggregatedproduct_unique_together_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TelegramPublication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('price', 'Прайс'), ('manual', 'Ручное сообщение')], max_length=20, verbose_name='Тип публикации')),
                ('text', models.TextField(verbose_name='Текст')),
                ('message_ids', models.JSONField(blank=True, default=list, verbose_name='ID сообщений Telegram')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Отправил')),
            ],
            options={
                'verbose_name': 'Публикация Telegram',
                'verbose_name_plural': 'Публикации Telegram',
                'ordering': ['-created_at'],
            },
        ),
    ]
