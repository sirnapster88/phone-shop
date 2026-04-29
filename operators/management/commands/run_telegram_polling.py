import time

from django.core.management.base import BaseCommand

from operators.telegram_bot import handle_telegram_update
from operators.telegram_cleanup import process_due_cleanup_tasks
from operators.telegram_service import (
    delete_telegram_webhook,
    get_telegram_updates,
)


class Command(BaseCommand):
    help = 'Запускает Telegram-бота в polling-режиме для локальной разработки'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-delete-webhook',
            action='store_true',
            help='Не снимать webhook перед запуском polling',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=25,
            help='Таймаут long polling в секундах',
        )
        parser.add_argument(
            '--poll-interval',
            type=float,
            default=1.0,
            help='Пауза между повторами после ошибки',
        )

    def handle(self, *args, **options):
        timeout = options['timeout']
        poll_interval = options['poll_interval']
        skip_delete_webhook = options['skip_delete_webhook']
        offset = None

        if not skip_delete_webhook:
            delete_telegram_webhook(drop_pending_updates=False)
            self.stdout.write(self.style.SUCCESS('Webhook удалён. Бот переведён в polling-режим.'))

        self.stdout.write(self.style.SUCCESS('Запущен Telegram polling. Для остановки нажмите Ctrl+C.'))

        while True:
            try:
                process_due_cleanup_tasks()

                updates = get_telegram_updates(
                    offset=offset,
                    timeout=timeout,
                    allowed_updates=['message', 'callback_query'],
                )

                for update in updates:
                    update_id = update.get('update_id')
                    if update_id is not None:
                        offset = update_id + 1

                    handle_telegram_update(update)

            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nTelegram polling остановлен пользователем.'))
                return
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'Ошибка polling: {exc}'))
                time.sleep(poll_interval)
