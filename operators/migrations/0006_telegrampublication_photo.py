from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operators', '0005_telegrampublication'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegrampublication',
            name='photo',
            field=models.FileField(blank=True, null=True, upload_to='telegram/%Y/%m/%d/', verbose_name='Фото'),
        ),
    ]
