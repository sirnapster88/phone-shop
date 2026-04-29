from django.db.models import Q

from .models import TelegramCustomerRequest


def operator_sidebar_context(request):
    if hasattr(request, 'sidebar_counts_override'):
        return request.sidebar_counts_override

    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {
            'sidebar_new_requests_count': 0,
            'sidebar_in_progress_requests_count': 0,
        }

    active_requests = TelegramCustomerRequest.objects.exclude(
        status__in=[TelegramCustomerRequest.STATUS_DONE, TelegramCustomerRequest.STATUS_CANCELLED]
    )

    return {
        'sidebar_new_requests_count': sum(
            active_requests.values_list('unread_messages_count', flat=True)
        ),
        'sidebar_in_progress_requests_count': active_requests.filter(
            status=TelegramCustomerRequest.STATUS_IN_PROGRESS
        ).count(),
    }
