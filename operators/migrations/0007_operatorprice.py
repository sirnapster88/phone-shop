from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operators', '0006_telegrampublication_photo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OperatorPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Цена оператора')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('aggregated_product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='operator_price', to='operators.aggregatedproduct', verbose_name='Товар')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Обновил')),
            ],
            options={
                'verbose_name': 'Цена оператора',
                'verbose_name_plural': 'Цены оператора',
                'ordering': ['aggregated_product__brand', 'aggregated_product__model'],
            },
        ),
    ]
