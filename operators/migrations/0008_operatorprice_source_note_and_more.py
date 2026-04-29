from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operators', '0007_operatorprice'),
    ]

    operations = [
        migrations.AddField(
            model_name='operatorprice',
            name='source_note',
            field=models.CharField(blank=True, max_length=255, verbose_name='Комментарий'),
        ),
        migrations.AddField(
            model_name='operatorprice',
            name='source_supplier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operator_prices', to='operators.supplier', verbose_name='Источник цены'),
        ),
        migrations.AlterModelOptions(
            name='operatorprice',
            options={'ordering': ['aggregated_product__brand', 'aggregated_product__model'], 'verbose_name': 'Витринная цена', 'verbose_name_plural': 'Витринные цены'},
        ),
    ]
