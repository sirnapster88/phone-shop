from django.core.management.base import BaseCommand

from operators.catalog_seed import seed_default_catalog


class Command(BaseCommand):
    help = "Заполняет базовый каталог моделей в AggregatedProduct"

    def handle(self, *args, **options):
        result = seed_default_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Каталог заполнен. Добавлено новых моделей: {result['created']}. "
                f"Всего seed-позиций: {result['total_seed_rows']}. "
                f"Всего моделей в базе: {result['total_models']}."
            )
        )
