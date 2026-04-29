from django.utils import timezone

from .models import TelegramChatCleanupTask
from .telegram_service import delete_telegram_messages_from_chat


def process_due_cleanup_tasks(limit=20):
    tasks = TelegramChatCleanupTask.objects.filter(
        processed_at__isnull=True,
        due_at__lte=timezone.now(),
    ).order_by('due_at')[:limit]

    processed = 0
    failed = 0

    for task in tasks:
        try:
            delete_telegram_messages_from_chat(task.chat_id, task.message_ids)
            task.processed_at = timezone.now()
            task.save(update_fields=['processed_at'])
            processed += 1
        except Exception:
            task.failed_attempts += 1
            task.save(update_fields=['failed_attempts'])
            failed += 1

    return processed, failed
