from django.core.management.base import BaseCommand

from operators.telegram_cleanup import process_due_cleanup_tasks


class Command(BaseCommand):
    help = 'Обрабатывает отложенную очистку сообщений Telegram.'

    def handle(self, *args, **options):
        processed, failed = process_due_cleanup_tasks(limit=100)

        self.stdout.write(
            self.style.SUCCESS(
                f'Обработка cleanup завершена: processed={processed}, failed={failed}'
            )
        )
