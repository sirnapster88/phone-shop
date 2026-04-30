import json
import logging
import tempfile
import traceback
from pathlib import Path
from secrets import compare_digest

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from urllib.parse import urlencode
from django.http import JsonResponse
from django.template.loader import render_to_string
from .models import (
    Supplier,
    PriceList,
    Product,
    AggregatedProduct,
    ProductPrice,
    TelegramPublication,
    OperatorPrice,
    TelegramCustomer,
    TelegramCustomerMessage,
    TelegramCustomerRequest,
)
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from .telegram_service import (
    answer_telegram_callback,
    send_telegram_messages,
    send_telegram_photo,
    delete_telegram_messages,
    send_telegram_message_to_chat,
    send_operator_notification,
)
from django.contrib.auth import logout
from .telegram_bot import get_active_customer_request, get_channel_entry_keyboard, handle_telegram_update
from .telegram_bot import close_request_and_notify_customer
from .telegram_bot import send_request_message
from .telegram_cleanup import process_due_cleanup_tasks
# Create your views here.

logger = logging.getLogger(__name__)
TELEGRAM_DEBUG_LOG_PATH = Path(tempfile.gettempdir()) / 'telegram_webhook_debug.log'


def _append_telegram_debug_log(message):
    try:
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        with TELEGRAM_DEBUG_LOG_PATH.open('a', encoding='utf-8') as log_file:
            log_file.write(f'[{timestamp}] {message}\n')
    except Exception:
        pass


def _mask_secret(value, keep_start=6, keep_end=4):
    value = (value or '').strip()
    if not value:
        return ''
    if len(value) <= keep_start + keep_end:
        return value
    return f'{value[:keep_start]}...{value[-keep_end:]}'


def _minimal_bot_welcome_text():
    return (
        '👋 Здравствуйте!\n\n'
        'Бот снова в сети. Сейчас работает безопасный режим без заявок, '
        'но уже можно открыть меню и проверить кнопки.'
    )


def _minimal_bot_menu():
    return {
        'inline_keyboard': [
            [
                {'text': '📋 Смотреть прайс', 'callback_data': 'minimal:price'},
            ],
            [
                {'text': '💵 Уточнить цену', 'callback_data': 'minimal:price_request'},
                {'text': '📦 Уточнить наличие', 'callback_data': 'minimal:availability'},
            ],
            [
                {'text': '🛒 Оформить заказ', 'callback_data': 'minimal:order'},
                {'text': '👨‍💼 Связаться с оператором', 'callback_data': 'minimal:operator'},
            ],
        ]
    }


def _minimal_bot_callback_reply(callback_data):
    replies = {
        'minimal:price': 'Прайс будет возвращен на следующем этапе восстановления.',
        'minimal:price_request': 'Напишите модель или вопрос по цене одним сообщением.',
        'minimal:availability': 'Напишите модель или вопрос по наличию одним сообщением.',
        'minimal:order': 'Напишите, что хотите заказать, одним сообщением.',
        'minimal:operator': 'Напишите сообщение для оператора одним сообщением.',
        'minimal:menu': _minimal_bot_welcome_text(),
    }
    return replies.get(callback_data, 'Кнопка получена. Бот работает в безопасном режиме.')


def _minimal_upsert_telegram_customer(user_data):
    telegram_id = user_data.get('id')
    if not telegram_id:
        return None

    defaults = {
        'username': user_data.get('username', '') or '',
        'first_name': user_data.get('first_name', '') or '',
        'last_name': user_data.get('last_name', '') or '',
        'language_code': user_data.get('language_code', '') or '',
    }
    customer, created = TelegramCustomer.objects.get_or_create(
        telegram_id=telegram_id,
        defaults=defaults,
    )

    if not created:
        changed_fields = []
        for field, value in defaults.items():
            if getattr(customer, field) != value:
                setattr(customer, field, value)
                changed_fields.append(field)
        if changed_fields:
            changed_fields.extend(['updated_at', 'last_seen_at'])
            customer.save(update_fields=changed_fields)
        else:
            customer.save(update_fields=['updated_at', 'last_seen_at'])

    return customer


def _minimal_request_type_label(request_type):
    labels = {
        TelegramCustomerRequest.TYPE_PRICE: 'цене',
        TelegramCustomerRequest.TYPE_AVAILABILITY: 'наличию',
        TelegramCustomerRequest.TYPE_ORDER: 'заказу',
        TelegramCustomerRequest.TYPE_QUESTION: 'сообщению',
    }
    return labels.get(request_type, 'запросу')


def _minimal_operator_reply_markup():
    return {
        'inline_keyboard': [
            [
                {'text': '✍️ Написать еще', 'callback_data': 'minimal:operator'},
            ],
            [
                {'text': '📋 Открыть меню', 'callback_data': 'minimal:menu'},
            ],
        ]
    }


def _minimal_start_request_capture(customer, request_type):
    customer.state = TelegramCustomer.STATE_AWAITING_REQUEST_TEXT
    customer.pending_request_type = request_type
    customer.save(update_fields=['state', 'pending_request_type', 'updated_at', 'last_seen_at'])


def _minimal_get_active_request(customer):
    return customer.requests.exclude(
        status__in=[TelegramCustomerRequest.STATUS_DONE, TelegramCustomerRequest.STATUS_CANCELLED]
    ).order_by('created_at', 'id').first()


def _minimal_create_or_append_request(customer, text, telegram_message_id=None):
    cleaned_text = (text or '').strip()
    request_type = customer.pending_request_type or TelegramCustomerRequest.TYPE_QUESTION
    active_request = _minimal_get_active_request(customer)

    if active_request is None:
        publication = TelegramPublication.objects.filter(
            kind=TelegramPublication.KIND_PRICE,
            is_active=True,
        ).first()
        active_request = TelegramCustomerRequest.objects.create(
            customer=customer,
            request_type=request_type,
            status=TelegramCustomerRequest.STATUS_NEW,
            publication=publication,
            product_query=cleaned_text,
            client_message=cleaned_text,
            telegram_message_id=telegram_message_id,
            has_unread_customer_message=True,
            unread_messages_count=1,
        )
    else:
        active_request.request_type = request_type or active_request.request_type
        active_request.client_message = cleaned_text
        active_request.has_unread_customer_message = True
        active_request.unread_messages_count = (active_request.unread_messages_count or 0) + 1
        if not active_request.product_query:
            active_request.product_query = cleaned_text
        active_request.save(
            update_fields=[
                'request_type',
                'client_message',
                'has_unread_customer_message',
                'unread_messages_count',
                'product_query',
                'updated_at',
            ]
        )

    TelegramCustomerMessage.objects.create(
        request=active_request,
        sender_type=TelegramCustomerMessage.SENDER_CUSTOMER,
        text=cleaned_text,
        telegram_message_id=telegram_message_id,
    )

    customer.state = TelegramCustomer.STATE_IDLE
    customer.pending_request_type = ''
    customer.save(update_fields=['state', 'pending_request_type', 'updated_at', 'last_seen_at'])

    return active_request

def index(request):
    """Главная страница - перенаправляем на кабинет оператора"""
    return redirect('operators:dashboard')


def healthz(request):
    process_due_cleanup_tasks(limit=5)
    return JsonResponse({'ok': True})


def _get_sidebar_counts():
    process_due_cleanup_tasks(limit=10)
    active_requests = TelegramCustomerRequest.objects.exclude(
        status__in=[TelegramCustomerRequest.STATUS_DONE, TelegramCustomerRequest.STATUS_CANCELLED]
    )
    latest_unread_message = (
        TelegramCustomerMessage.objects.select_related('request__customer')
        .filter(
            sender_type=TelegramCustomerMessage.SENDER_CUSTOMER,
            request__status__in=[
                TelegramCustomerRequest.STATUS_NEW,
                TelegramCustomerRequest.STATUS_IN_PROGRESS,
            ],
        )
        .filter(
            Q(request__has_unread_customer_message=True) | Q(request__status=TelegramCustomerRequest.STATUS_NEW)
        )
        .order_by('-created_at', '-id')
        .first()
    )

    customer_label = ''
    message_preview = ''
    latest_message_id = None
    latest_request_id = None
    latest_unread_event_type = ''

    if latest_unread_message:
        customer = latest_unread_message.request.customer
        customer_label = customer.username or customer.first_name or str(customer.telegram_id)
        message_preview = (latest_unread_message.text or '').strip()
        latest_message_id = latest_unread_message.id
        latest_request_id = latest_unread_message.request_id
        latest_unread_event_type = (
            'new_request'
            if latest_unread_message.request.status == TelegramCustomerRequest.STATUS_NEW
            else 'new_message'
        )

    latest_closed_by_customer = (
        TelegramCustomerMessage.objects.select_related('request__customer')
        .filter(
            sender_type=TelegramCustomerMessage.SENDER_OPERATOR,
            operator__isnull=True,
            text='[system] customer_closed_request',
            request__status=TelegramCustomerRequest.STATUS_DONE,
        )
        .order_by('-created_at', '-id')
        .first()
    )

    latest_system_event_key = ''
    latest_system_event_type = ''
    latest_system_event_title = ''
    latest_system_event_text = ''
    latest_system_event_request_id = None

    if latest_closed_by_customer:
        customer = latest_closed_by_customer.request.customer
        customer_name = customer.username or customer.first_name or str(customer.telegram_id)
        latest_system_event_key = f'closed:{latest_closed_by_customer.id}'
        latest_system_event_type = 'request_closed'
        latest_system_event_title = f'Заявка #{latest_closed_by_customer.request_id} закрыта клиентом'
        latest_system_event_text = f'{customer_name} завершил диалог в Telegram.'
        latest_system_event_request_id = latest_closed_by_customer.request_id

    return {
        'new_requests_count': sum(
            active_requests.values_list('unread_messages_count', flat=True)
        ),
        'in_progress_requests_count': active_requests.filter(
            status=TelegramCustomerRequest.STATUS_IN_PROGRESS
        ).count(),
        'latest_unread_message_id': latest_message_id,
        'latest_unread_request_id': latest_request_id,
        'latest_unread_event_type': latest_unread_event_type,
        'latest_unread_customer_label': customer_label,
        'latest_unread_message_preview': message_preview[:140],
        'latest_system_event_key': latest_system_event_key,
        'latest_system_event_type': latest_system_event_type,
        'latest_system_event_title': latest_system_event_title,
        'latest_system_event_text': latest_system_event_text,
        'latest_system_event_request_id': latest_system_event_request_id,
    }


def _prepare_telegram_requests_data(mark_read=False):
    active_customers = (
        TelegramCustomerRequest.objects.exclude(
            status__in=[TelegramCustomerRequest.STATUS_DONE, TelegramCustomerRequest.STATUS_CANCELLED]
        )
        .select_related('customer')
        .order_by('customer_id', 'created_at')
    )
    seen_customer_ids = set()
    for request_item in active_customers:
        customer = request_item.customer
        if customer.id in seen_customer_ids:
            continue
        seen_customer_ids.add(customer.id)
        get_active_customer_request(customer)

    requests_qs = TelegramCustomerRequest.objects.select_related(
        'customer', 'product', 'assigned_operator', 'publication'
    ).prefetch_related(
        'messages__operator'
    )

    active_requests = list(requests_qs.exclude(
        status__in=[TelegramCustomerRequest.STATUS_DONE, TelegramCustomerRequest.STATUS_CANCELLED]
    ).order_by('-updated_at', '-created_at'))
    archived_requests = list(requests_qs.filter(
        status__in=[TelegramCustomerRequest.STATUS_DONE, TelegramCustomerRequest.STATUS_CANCELLED]
    ).order_by('-updated_at', '-created_at'))

    for item in active_requests + archived_requests:
        thread_messages = list(item.messages.all())
        customer_closed_event = next(
            (
                message for message in reversed(thread_messages)
                if message.sender_type == TelegramCustomerMessage.SENDER_OPERATOR
                and message.operator_id is None
                and message.text == '[system] customer_closed_request'
            ),
            None,
        )
        visible_thread_messages = [
            message for message in thread_messages
            if not (
                message.sender_type == TelegramCustomerMessage.SENDER_OPERATOR
                and message.operator_id is None
            )
        ]
        item.thread_messages = visible_thread_messages
        item.last_thread_message = visible_thread_messages[-1] if visible_thread_messages else None
        item.closed_by_customer = customer_closed_event is not None
        item.customer_closed_at = customer_closed_event.created_at if customer_closed_event else None
        item.has_unread_customer_message = bool(item.has_unread_customer_message)
        item.should_highlight = (item.unread_messages_count or 0) > 0 or item.status == TelegramCustomerRequest.STATUS_NEW

    unread_ids = [item.id for item in active_requests if item.has_unread_customer_message or (item.unread_messages_count or 0) > 0]
    if mark_read and unread_ids:
        TelegramCustomerRequest.objects.filter(id__in=unread_ids).update(
            has_unread_customer_message=False,
            unread_messages_count=0,
        )

    active_requests.sort(
        key=lambda item: (
            0 if item.should_highlight else 1,
            0 if item.status == TelegramCustomerRequest.STATUS_NEW else 1,
            -item.updated_at.timestamp(),
            -item.created_at.timestamp(),
        )
    )

    sidebar_counts = _get_sidebar_counts()

    return {
        'active_requests': active_requests,
        'archived_requests': archived_requests,
        'new_requests_count': sum(1 for item in active_requests if item.status == TelegramCustomerRequest.STATUS_NEW),
        'in_progress_requests_count': sum(1 for item in active_requests if item.status == TelegramCustomerRequest.STATUS_IN_PROGRESS),
        'archived_requests_count': len(archived_requests),
        'sidebar_new_requests_count': 0 if mark_read else sum((item.unread_messages_count or 0) for item in active_requests),
        'sidebar_in_progress_requests_count': sum(
            1 for item in active_requests if item.status == TelegramCustomerRequest.STATUS_IN_PROGRESS
        ),
        'latest_system_event_key': sidebar_counts.get('latest_system_event_key', ''),
        'latest_system_event_type': sidebar_counts.get('latest_system_event_type', ''),
        'latest_system_event_title': sidebar_counts.get('latest_system_event_title', ''),
        'latest_system_event_text': sidebar_counts.get('latest_system_event_text', ''),
        'latest_system_event_request_id': sidebar_counts.get('latest_system_event_request_id'),
    }


def _parse_price_value(value):
    normalized = (value or '').strip().replace(' ', '').replace(',', '.')
    if not normalized:
        return None

    try:
        price = Decimal(normalized)
    except InvalidOperation:
        return None

    if price <= 0:
        return None

    return price.quantize(Decimal('1.00'))


def _build_manual_price_context(request):
    query = request.GET.get('q', '').strip()
    filter_category = request.GET.get('category', '').strip()
    filter_brand = request.GET.get('brand', '').strip()
    without_price_only = request.GET.get('without_price') == '1'
    suppliers = Supplier.objects.all().order_by('name')

    products_qs = AggregatedProduct.objects.select_related('operator_price').prefetch_related('prices__supplier').order_by(
        'brand', 'model', 'memory', 'specs', 'color', 'region', 'sim_type'
    )

    if filter_category:
        products_qs = products_qs.filter(category=filter_category)
    if filter_brand:
        products_qs = products_qs.filter(brand=filter_brand)

    products = list(products_qs)
    if query:
        query_lower = query.lower()
        products = [
            product for product in products
            if query_lower in ' '.join(filter(None, [
                product.brand,
                product.model,
                product.color,
                product.memory,
                product.region,
                product.sim_type,
                product.specs,
            ])).lower()
        ]

    items = []
    for product in products:
        supplier_prices = list(product.prices.all())
        best_price = min((price.price for price in supplier_prices), default=None)
        operator_price = getattr(product, 'operator_price', None)

        if without_price_only and operator_price:
            continue

        items.append({
            'product': product,
            'display_name': str(product),
            'supplier_prices_count': len(supplier_prices),
            'best_supplier_price': best_price,
            'operator_price': operator_price,
        })

    all_products = AggregatedProduct.objects.all()
    categories = sorted({value for value in all_products.values_list('category', flat=True) if value})
    brands = sorted({value for value in all_products.values_list('brand', flat=True) if value})

    return {
        'items': items,
        'filters': {
            'q': query,
            'category': filter_category,
            'brand': filter_brand,
            'without_price': without_price_only,
        },
        'filter_options': {
            'categories': categories,
            'brands': brands,
            'suppliers': suppliers,
        },
        'stats': {
            'total_models': len(items),
            'with_operator_prices': sum(1 for item in items if item['operator_price']),
        }
    }


def _manual_mode_redirect(request=None):
    query = {'mode': 'manual'}
    if request:
        q = request.POST.get('return_q', '').strip()
        category = request.POST.get('return_category', '').strip()
        brand = request.POST.get('return_brand', '').strip()
        without_price = request.POST.get('return_without_price') == '1'

        if q:
            query['q'] = q
        if category:
            query['category'] = category
        if brand:
            query['brand'] = brand
        if without_price:
            query['without_price'] = '1'

    return redirect(f"{reverse('operators:upload_pricelist')}?{urlencode(query)}")


def _handle_manual_price_post(request):
    action = request.POST.get('action')
    if action not in {'save_prices', 'add_product'}:
        return None

    if action == 'save_prices':
        updated_count = 0
        invalid_ids = []

        for product_id in request.POST.getlist('product_ids'):
            raw_price = request.POST.get(f'price_{product_id}', '')
            if not raw_price.strip():
                continue

            price = _parse_price_value(raw_price)
            if price is None:
                invalid_ids.append(product_id)
                continue

            source_supplier_id = request.POST.get(f'source_supplier_{product_id}', '').strip()
            source_note = request.POST.get(f'source_note_{product_id}', '').strip()
            source_supplier = None
            if source_supplier_id:
                try:
                    source_supplier = Supplier.objects.get(id=source_supplier_id)
                except Supplier.DoesNotExist:
                    source_supplier = None

            try:
                aggregated_product = AggregatedProduct.objects.get(id=product_id)
            except AggregatedProduct.DoesNotExist:
                continue

            OperatorPrice.objects.update_or_create(
                aggregated_product=aggregated_product,
                defaults={
                    'price': price,
                    'source_supplier': source_supplier,
                    'source_note': source_note,
                    'updated_by': request.user,
                }
            )
            updated_count += 1

        if updated_count:
            messages.success(request, f'Обновлено витринных цен: {updated_count}')
        if invalid_ids:
            messages.warning(request, f'Некоторые цены пропущены из-за неверного формата: {len(invalid_ids)}')

        return _manual_mode_redirect(request)

    category = request.POST.get('category', '').strip()
    brand = request.POST.get('brand', '').strip()
    model = request.POST.get('model', '').strip()
    color = request.POST.get('color', '').strip()
    memory = request.POST.get('memory', '').strip()
    region = request.POST.get('region', '').strip()
    sim_type = request.POST.get('sim_type', '').strip()
    specs = request.POST.get('specs', '').strip()
    price = _parse_price_value(request.POST.get('price', ''))
    source_supplier_id = request.POST.get('source_supplier', '').strip()
    source_note = request.POST.get('source_note', '').strip()
    source_supplier = None

    if source_supplier_id:
        try:
            source_supplier = Supplier.objects.get(id=source_supplier_id)
        except Supplier.DoesNotExist:
            source_supplier = None

    if not model:
        messages.error(request, 'Укажите модель новой позиции')
        return _manual_mode_redirect(request)

    if price is None:
        messages.error(request, 'Укажите корректную цену для новой позиции')
        return _manual_mode_redirect(request)

    aggregated_product, created = AggregatedProduct.objects.get_or_create(
        category=category,
        brand=brand,
        model=model,
        color=color,
        memory=memory,
        region=region,
        sim_type=sim_type,
        specs=specs,
    )

    OperatorPrice.objects.update_or_create(
        aggregated_product=aggregated_product,
        defaults={
            'price': price,
            'source_supplier': source_supplier,
            'source_note': source_note,
            'updated_by': request.user,
        }
    )

    if created:
        messages.success(request, 'Новая модель добавлена и витринная цена сохранена')
    else:
        messages.success(request, 'Для существующей модели обновлена витринная цена')

    return _manual_mode_redirect(request)

@login_required
def dashboard(request):
    """Главная страница кабинета оператора"""
    recent_pricelists = PriceList.objects.select_related('supplier', 'uploaded_by').order_by('-uploaded_at')[:10]
    suppliers = Supplier.objects.all()
    telegram_requests_qs = TelegramCustomerRequest.objects.all()
    operator_prices_count = OperatorPrice.objects.count()
    aggregated_products_count = AggregatedProduct.objects.count()
    processed_pricelists_count = PriceList.objects.filter(status='processed').count()
    latest_telegram_publication = TelegramPublication.objects.first()
    latest_pricelist = PriceList.objects.select_related('supplier', 'uploaded_by').order_by('-uploaded_at').first()
    latest_operator_update = OperatorPrice.objects.select_related('updated_by', 'source_supplier', 'aggregated_product').order_by('-updated_at').first()
    latest_telegram_request = telegram_requests_qs.select_related('customer', 'assigned_operator').first()
    models_without_operator_price = max(aggregated_products_count - operator_prices_count, 0)
    
    sidebar_counts = _get_sidebar_counts()

    context = {
        'recent_pricelists': recent_pricelists,
        'suppliers': suppliers,
        'stats': {
            'suppliers_count': suppliers.count(),
            'pricelists_count': PriceList.objects.count(),
            'processed_pricelists_count': processed_pricelists_count,
            'aggregated_products_count': aggregated_products_count,
            'operator_prices_count': operator_prices_count,
            'models_without_operator_price': models_without_operator_price,
            'telegram_requests_new_count': telegram_requests_qs.filter(
                status=TelegramCustomerRequest.STATUS_NEW
            ).count(),
            'telegram_requests_in_progress_count': telegram_requests_qs.filter(status=TelegramCustomerRequest.STATUS_IN_PROGRESS).count(),
        },
        'latest_telegram_publication': latest_telegram_publication,
        'latest_telegram_request': latest_telegram_request,
        'latest_pricelist': latest_pricelist,
        'latest_operator_update': latest_operator_update,
        'sidebar_counts': sidebar_counts,
    }
    return render(request, 'operators/dashboard.html', context)


@never_cache
@login_required
def sidebar_counts_api(request):
    return JsonResponse(_get_sidebar_counts())


@login_required
def manual_price_editor(request):
    return _manual_mode_redirect()


@login_required
def upload_pricelist(request):
    """Загрузка прайс-листа (файл или текст)"""
    suppliers = Supplier.objects.all()
    mode = request.GET.get('mode', 'upload')
    manual_context = _build_manual_price_context(request)
    
    if request.method == 'POST':
        manual_response = _handle_manual_price_post(request)
        if manual_response is not None:
            return manual_response

        upload_type = request.POST.get('upload_type')
        supplier_id = request.POST.get('supplier')
        
        if not supplier_id:
            messages.error(request, 'Выберите поставщика')
            return redirect('operators:upload_pricelist')
        
        try:
            supplier = Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            messages.error(request, 'Поставщик не найден')
            return redirect('operators:upload_pricelist')
        
        # Загрузка файла
        if upload_type == 'file':
            file = request.FILES.get('file')
            if not file:
                messages.error(request, 'Выберите файл')
                return redirect('operators:upload_pricelist')
            
            # Сохраняем файл
            pricelist = PriceList.objects.create(
                supplier=supplier,
                file=file,
                uploaded_by=request.user,
                status='new'
            )
            messages.success(request, f'✅ Файл загружен: {file.name}')
            
            # Сразу обрабатываем
            return redirect('operators:process_pricelist', pricelist_id=pricelist.id)
        
        # Загрузка текста
        elif upload_type == 'text':
            text = request.POST.get('text')
            if not text or not text.strip():
                messages.error(request, 'Введите текст прайс-листа')
                return redirect('operators:upload_pricelist')

            # Парсим текст
            from .parser import TextPriceParser
            from .aggregator import Aggregator

            parser = TextPriceParser(text)
            products_data = parser.parse()

            if not products_data:
                messages.warning(request, 'Не найдено товаров в тексте')
                return redirect('operators:dashboard')

            # Создаем запись прайс-листа для текста
            pricelist = PriceList.objects.create(
                supplier=supplier,
                uploaded_by=request.user,
                status='processed'
            )

            # Сохраняем товары
            saved = 0
            for item in products_data:
                Product.objects.create(
                    supplier=supplier,
                    pricelist=pricelist,
                    category=item.get('category', ''),
                    brand=item.get('brand', ''),
                    model=item.get('model', ''),
                    color=item.get('color', ''),
                    memory=item.get('memory', ''),
                    region=item.get('region', ''),
                    sim_type=item.get('sim_type', ''),
                    specs=item.get('specs', ''),
                    price=item['price']
                )
                saved += 1


            messages.success(request, f'✅ Обработано {saved} товаров из текста')

            agg_results = Aggregator.aggregate_all()
            messages.info(request, f'📊 Создано {agg_results["aggregated"]} уникальных товаров')

            return redirect('operators:dashboard')

    
    return render(request, 'operators/upload.html', {
        'suppliers': suppliers,
        'mode': mode,
        **manual_context,
    })


@login_required
@require_POST
def seed_catalog_view(request):
    from .catalog_seed import seed_default_catalog

    result = seed_default_catalog()
    if result['created']:
        messages.success(
            request,
            f"Базовый каталог загружен из price.txt. Добавлено моделей: {result['created']}."
        )
    else:
        messages.info(request, 'Каталог из price.txt уже загружен, новых моделей не добавлено.')
    return _manual_mode_redirect(request)


@login_required
@require_POST
def clear_catalog_view(request):
    OperatorPrice.objects.all().delete()
    ProductPrice.objects.all().delete()
    AggregatedProduct.objects.all().delete()
    messages.success(request, 'Каталог очищен: сводные товары, витринные цены и агрегированные цены удалены')
    return _manual_mode_redirect(request)


@login_required
def process_pricelist(request, pricelist_id):
    """Обработка прайс-листа умным парсером"""
    pricelist = get_object_or_404(PriceList, id=pricelist_id)
    
    try:
        from .parser import SmartParser
        from .aggregator import Aggregator

        pricelist.status = 'processing'
        pricelist.save()
        
        # Создаём парсер
        parser = SmartParser(pricelist.file.path)
        products_data = parser.parse()
        
        if not products_data:
            messages.warning(request, 'Не найдено товаров в файле')
            pricelist.status = 'error'
            pricelist.save()
            return redirect('operators:dashboard')
        
        # Сохраняем товары
        saved = 0
        for item in products_data:
            Product.objects.create(
                supplier=pricelist.supplier,
                pricelist=pricelist,
                category=item.get('category', ''),
                brand=item.get('brand', ''),
                model=item.get('model', ''),
                color=item.get('color', ''),
                memory=item.get('memory', ''),
                region=item.get('region', ''),
                sim_type=item.get('sim_type', ''),
                specs=item.get('specs', ''),
                price=item['price']
            )
            saved += 1


        pricelist.status = 'processed'
        pricelist.save()
        
        messages.success(request, f'✅ Обработано {saved} товаров')
        
        # Запускаем агрегацию
        agg_results = Aggregator.aggregate_all()
        messages.info(request, f'📊 Создано {agg_results["aggregated"]} уникальных товаров')
        
    except Exception as e:
        pricelist.status = 'error'
        pricelist.save()
        messages.error(request, f'❌ Ошибка: {str(e)}')
    
    return redirect('operators:dashboard')


@login_required
def comparison_table(request):
    """Сводная таблица сравнения цен"""
    suppliers = Supplier.objects.all().order_by('name')
    products = AggregatedProduct.objects.all().order_by('model')

    filter_model = request.GET.get('model', '').strip()
    filter_supplier = request.GET.get('supplier', '').strip()
    filter_price_min = request.GET.get('price_min', '').strip()
    filter_price_max = request.GET.get('price_max', '').strip()
    sort_by = request.GET.get('sort', 'model')
    best_only = request.GET.get('best_only') == '1'

    table_data = []
    for product in products:
        prices = ProductPrice.objects.filter(
            aggregated_product=product
        ).select_related('supplier')

        if filter_supplier:
            prices = prices.filter(supplier_id=filter_supplier)

        if not prices.exists():
            continue

        price_list = []
        price_values = []

        for price in prices:
            price_value = float(price.price)
            price_list.append({
                'supplier_id': price.supplier.id,
                'supplier_name': price.supplier.name,
                'price': price_value
            })
            price_values.append(price_value)

        min_price = min(price_values)
        max_price = max(price_values)
        display_name = str(product)

        if filter_model and filter_model.lower() not in display_name.lower():
            continue

        if filter_price_min:
            try:
                if min_price < float(filter_price_min):
                    continue
            except ValueError:
                pass

        if filter_price_max:
            try:
                if min_price > float(filter_price_max):
                    continue
            except ValueError:
                pass

        if best_only and len(price_list) < 2:
            continue

        table_data.append({
            'id': product.id,
            'category': product.category,
            'brand': product.brand,
            'model': product.model,
            'color': product.color,
            'memory': product.memory,
            'region': product.region,
            'sim_type': product.sim_type,
            'specs': product.specs,
            'display_name': display_name,
            'price_list': price_list,
            'min_price': min_price,
            'max_price': max_price,
            'suppliers_count': len(price_list)
        })


    if sort_by == 'min_price':
        table_data.sort(key=lambda x: x['min_price'])
    elif sort_by == 'max_price':
        table_data.sort(key=lambda x: x['max_price'])
    elif sort_by == 'suppliers_count':
        table_data.sort(key=lambda x: x['suppliers_count'], reverse=True)
    else:
        table_data.sort(key=lambda x: x['display_name'])

    context = {
        'suppliers': suppliers,
        'products': table_data,
        'total_products': len(table_data),
        'filters': {
            'model': filter_model,
            'supplier': filter_supplier,
            'price_min': filter_price_min,
            'price_max': filter_price_max,
            'sort': sort_by,
            'best_only': best_only,
        }
    }
    return render(request, 'operators/comparison_table.html', context)

   
@login_required
def delete_pricelist(request, pricelist_id):
    """Удаление прайс-листа"""
    if request.method == 'POST':
        pricelist = get_object_or_404(PriceList, id=pricelist_id)
        if pricelist.file:
            pricelist.file.delete()
        pricelist.delete()
        messages.success(request, 'Прайс-лист удалён')
    return redirect('operators:dashboard')


@login_required
def delete_all_pricelists(request):
    """Массовое удаление прайс-листов"""
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier_id')
        
        if supplier_id and supplier_id.isdigit():
            pricelists = PriceList.objects.filter(supplier_id=supplier_id)
            count = pricelists.count()
            for pricelist in pricelists:
                if pricelist.file:
                    pricelist.file.delete()
            pricelists.delete()
            messages.success(request, f'Удалено {count} прайс-листов поставщика')
        else:
            count = PriceList.objects.count()
            for pricelist in PriceList.objects.all():
                if pricelist.file:
                    pricelist.file.delete()
            PriceList.objects.all().delete()
            messages.success(request, f'Удалено {count} прайс-листов')
    
    return redirect('operators:dashboard')


@login_required
def start_new_day(request):
    """Полный сброс рабочих данных за день"""
    if request.method == 'POST':
        # Сначала удаляем связанные данные
        ProductPrice.objects.all().delete()
        AggregatedProduct.objects.all().delete()
        Product.objects.all().delete()

        # Удаляем файлы прайс-листов с диска и записи из БД
        for pricelist in PriceList.objects.all():
            if pricelist.file:
                pricelist.file.delete(save=False)

        PriceList.objects.all().delete()

        messages.success(request, 'Начат новый день: все прайсы, товары и агрегированные данные очищены')

    return redirect('operators:dashboard')



@login_required
def product_detail(request, product_id):
    """Детальный просмотр товара"""
    product = get_object_or_404(AggregatedProduct, id=product_id)
    prices = ProductPrice.objects.filter(
        aggregated_product=product
    ).select_related('supplier').order_by('price')

    min_price = prices.first().price if prices.exists() else None
    max_price = prices.last().price if prices.exists() else None
    spread = (max_price - min_price) if min_price is not None and max_price is not None else None
    
    context = {
        'product': product,
        'prices': prices,
        'min_price': min_price,
        'max_price': max_price,
        'spread': spread,
    }
    return render(request, 'operators/product_detail.html', context)


@login_required
def run_aggregation(request):
    """Запуск агрегации вручную"""
    if request.method == 'POST':
        results = Aggregator.aggregate_all()
        messages.success(request, f'Агрегация завершена. Создано {results["aggregated"]} уникальных товаров')
    return redirect('operators:comparison_table')


@login_required
def telegram_price_builder(request):
    """Конструктор прайса для Telegram"""
    products = AggregatedProduct.objects.select_related('operator_price').prefetch_related('prices__supplier').order_by(
        'category', 'brand', 'model', 'memory', 'specs', 'color', 'region', 'sim_type'
    )

    filter_category = request.GET.get('category', '').strip()
    filter_brand = request.GET.get('brand', '').strip()
    filter_supplier = request.GET.get('supplier', '').strip()
    filter_query = request.GET.get('q', '').strip()

    items = []
    categories = set()
    brands = set()
    suppliers = set()

    for product in products:
        prices = list(product.prices.all())
        operator_price = getattr(product, 'operator_price', None)
        if not prices and not operator_price:
            continue

        best_price_obj = min(prices, key=lambda p: p.price) if prices else None

        categories.add(product.category or '')
        brands.add(product.brand or '')
        if best_price_obj and best_price_obj.supplier:
            suppliers.add((best_price_obj.supplier.id, best_price_obj.supplier.name))

        display_name = ' '.join(filter(None, [
            product.brand or '',
            product.model or '',
            product.color or '',
            product.memory or '',
            product.region or '',
            product.sim_type or '',
            product.specs or '',
        ])).strip()

        if filter_category and (product.category or '') != filter_category:
            continue

        if filter_brand and (product.brand or '') != filter_brand:
            continue

        if filter_supplier:
            try:
                if not best_price_obj or not best_price_obj.supplier or best_price_obj.supplier.id != int(filter_supplier):
                    continue
            except ValueError:
                pass

        if filter_query and filter_query.lower() not in display_name.lower():
            continue

        items.append({
            'id': product.id,
            'category': product.category or '',
            'brand': product.brand or '',
            'model': product.model or '',
            'color': product.color or '',
            'memory': product.memory or '',
            'region': product.region or '',
            'sim_type': product.sim_type or '',
            'specs': product.specs or '',
            'base_price': int(operator_price.price if operator_price else best_price_obj.price),
            'supplier_name': (
                operator_price.source_supplier.name
                if operator_price and operator_price.source_supplier
                else (best_price_obj.supplier.name if best_price_obj and best_price_obj.supplier else 'Ручная цена')
            ),
            'has_manual_price': bool(operator_price),
            'manual_price': int(operator_price.price) if operator_price else '',
            'manual_source_supplier_name': operator_price.source_supplier.name if operator_price and operator_price.source_supplier else '',
            'manual_source_note': operator_price.source_note if operator_price else '',
            'manual_updated_by': operator_price.updated_by.username if operator_price and operator_price.updated_by else '',
        })

    context = {
        'items': items,
        'latest_price_publication': TelegramPublication.objects.filter(
            kind=TelegramPublication.KIND_PRICE,
            is_active=True
        ).first(),
        'latest_manual_publication': TelegramPublication.objects.filter(
            kind=TelegramPublication.KIND_MANUAL
        ).first(),
        'filter_options': {
            'categories': sorted([c for c in categories if c]),
            'brands': sorted([b for b in brands if b]),
            'suppliers': sorted(list(suppliers), key=lambda x: x[1]),
        },
        'filters': {
            'category': filter_category,
            'brand': filter_brand,
            'supplier': filter_supplier,
            'q': filter_query,
        }
    }
    return render(request, 'operators/telegram_price_builder.html', context)

@login_required
@require_POST
def send_telegram_pricelist(request):
    text = request.POST.get('telegram_text', '').strip()

    if not text:
        messages.error(request, 'Нет текста для отправки в Telegram')
        return redirect('operators:telegram_price_builder')

    try:
        active_publications = list(
            TelegramPublication.objects.filter(
                kind=TelegramPublication.KIND_PRICE,
                is_active=True
            )
        )

        deleted_count = 0
        for publication in active_publications:
            if publication.message_ids:
                deleted_count += delete_telegram_messages(publication.message_ids)
            publication.is_active = False
            publication.save(update_fields=['is_active'])

        sent_messages = send_telegram_messages(text, reply_markup=get_channel_entry_keyboard())
        TelegramPublication.objects.create(
            kind=TelegramPublication.KIND_PRICE,
            text=text,
            message_ids=[item['message_id'] for item in sent_messages],
            sent_by=request.user,
            is_active=True,
        )

        if deleted_count:
            messages.info(request, f'Удалено предыдущих сообщений прайса: {deleted_count}')
        messages.success(request, f'Прайс отправлен в Telegram: {len(sent_messages)} сообщ.')
    except Exception as e:
        messages.error(request, f'Ошибка отправки в Telegram: {e}')

    return redirect('operators:telegram_price_builder')


@login_required
@require_POST
def send_telegram_manual_message(request):
    text = request.POST.get('manual_telegram_text', '').strip()
    photo = request.FILES.get('manual_telegram_photo')

    if not text and not photo:
        messages.error(request, 'Добавьте текст или фото для Telegram')
        return redirect('operators:telegram_price_builder')

    try:
        if photo:
            sent_messages = send_telegram_photo(photo, caption=text)
        else:
            sent_messages = send_telegram_messages(text)

        if photo and hasattr(photo, 'seek'):
            photo.seek(0)

        TelegramPublication.objects.create(
            kind=TelegramPublication.KIND_MANUAL,
            text=text,
            photo=photo,
            message_ids=[item['message_id'] for item in sent_messages],
            sent_by=request.user,
            is_active=False,
        )
        if photo:
            messages.success(request, f'Сообщение с фото отправлено в Telegram: {len(sent_messages)} сообщ.')
        else:
            messages.success(request, f'Сообщение отправлено в Telegram: {len(sent_messages)} сообщ.')
    except Exception as e:
        messages.error(request, f'Ошибка отправки сообщения: {e}')

    return redirect('operators:telegram_price_builder')

@login_required
def app_logout(request):
    logout(request)
    messages.success(request, 'Вы вышли из системы')
    return redirect('/login/')


@login_required
def ui_preview(request):
    return render(request, 'operators/ui_preview.html')


@login_required
def telegram_debug_log(request):
    if TELEGRAM_DEBUG_LOG_PATH.exists():
        content = TELEGRAM_DEBUG_LOG_PATH.read_text(encoding='utf-8')
    else:
        content = 'Debug log is empty.'

    return JsonResponse({
        'path': str(TELEGRAM_DEBUG_LOG_PATH),
        'content': content[-20000:],
    })


@login_required
def env_debug(request):
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '').strip()
    token_prefix = bot_token.split(':', 1)[0] if ':' in bot_token else ''
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '').strip()
    operator_chat_id = getattr(settings, 'TELEGRAM_OPERATOR_CHAT_ID', '').strip()

    return JsonResponse({
        'django_debug': settings.DEBUG,
        'allowed_hosts': list(settings.ALLOWED_HOSTS),
        'csrf_trusted_origins': list(getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])),
        'telegram_bot_token_masked': _mask_secret(bot_token, keep_start=10, keep_end=6),
        'telegram_bot_token_prefix': token_prefix,
        'telegram_webhook_secret_masked': _mask_secret(getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')),
        'telegram_chat_id_masked': _mask_secret(chat_id, keep_start=6, keep_end=4),
        'telegram_operator_chat_id_masked': _mask_secret(operator_chat_id, keep_start=6, keep_end=4),
        'telegram_bot_username': getattr(settings, 'TELEGRAM_BOT_USERNAME', '').strip(),
        'webhook_debug_log_path': str(TELEGRAM_DEBUG_LOG_PATH),
        'webhook_debug_log_exists': TELEGRAM_DEBUG_LOG_PATH.exists(),
    })


@csrf_exempt
def telegram_bot_webhook(request, webhook_secret=''):
    if request.method != 'POST':
        _append_telegram_debug_log(f'method_not_allowed method={request.method}')
        return JsonResponse({'ok': False, 'error': 'method_not_allowed'}, status=405)

    expected_secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '').strip()
    header_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '').strip()
    secret_matches = False

    if expected_secret:
        if webhook_secret and compare_digest(webhook_secret, expected_secret):
            secret_matches = True
        elif header_secret and compare_digest(header_secret, expected_secret):
            secret_matches = True

    if not expected_secret or not secret_matches:
        _append_telegram_debug_log(
            'secret_mismatch '
            f'header_present={bool(header_secret)} path_present={bool(webhook_secret)}'
        )
        return JsonResponse({'ok': False, 'error': 'not_found'}, status=404)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        _append_telegram_debug_log('invalid_json')
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    _append_telegram_debug_log(
        'webhook_received '
        f'update_id={payload.get("update_id")} keys={list(payload.keys())}'
    )

    try:
        if payload.get('callback_query'):
            callback_query = payload['callback_query']
            callback_id = callback_query.get('id')
            callback_data = callback_query.get('data', '')
            callback_message = callback_query.get('message') or {}
            callback_chat = callback_message.get('chat') or {}
            callback_chat_id = callback_chat.get('id')
            callback_user = callback_query.get('from') or {}
            _append_telegram_debug_log(
                f'callback_received id={callback_id} data={callback_data!r}'
            )
            if callback_id:
                answer_telegram_callback(callback_id, text='Принято')
                _append_telegram_debug_log(f'callback_answered id={callback_id}')
            if callback_chat_id:
                customer = _minimal_upsert_telegram_customer(callback_user)
                if callback_data == 'minimal:price_request' and customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_PRICE)
                elif callback_data == 'minimal:availability' and customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_AVAILABILITY)
                elif callback_data == 'minimal:order' and customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_ORDER)
                elif callback_data == 'minimal:operator' and customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_QUESTION)

                reply_text = _minimal_bot_callback_reply(callback_data)
                reply_markup = _minimal_bot_menu() if callback_data == 'minimal:menu' else None
                send_telegram_message_to_chat(callback_chat_id, reply_text, reply_markup=reply_markup)
                _append_telegram_debug_log(
                    f'callback_message_sent chat_id={callback_chat_id} reply={reply_text!r}'
                )
            return JsonResponse({'ok': True, 'mode': 'minimal'})

        message = payload.get('message') or {}
        chat = message.get('chat') or {}
        from_user = message.get('from') or {}
        chat_id = chat.get('id') or from_user.get('id')
        text = (message.get('text') or '').strip()
        customer = _minimal_upsert_telegram_customer(from_user)

        _append_telegram_debug_log(
            f'message_received chat_id={chat_id} from_user={from_user.get("id")} text={text!r}'
        )

        if not chat_id:
            _append_telegram_debug_log('message_skipped_no_chat_id')
            return JsonResponse({'ok': True, 'mode': 'minimal'})

        if text.startswith('/start'):
            start_param = text.split(maxsplit=1)[1].strip() if ' ' in text else ''
            reply_text = _minimal_bot_welcome_text()
            if start_param == 'price':
                reply_text += '\n\nОткрыт сценарий: прайс / цена и наличие.'
                if customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_PRICE)
            elif start_param == 'order':
                reply_text += '\n\nОткрыт сценарий: оформление заказа.'
                if customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_ORDER)
            elif start_param == 'question':
                reply_text += '\n\nОткрыт сценарий: связь с оператором.'
                if customer:
                    _minimal_start_request_capture(customer, TelegramCustomerRequest.TYPE_QUESTION)

            send_telegram_message_to_chat(chat_id, reply_text, reply_markup=_minimal_bot_menu())
        elif customer and customer.state == TelegramCustomer.STATE_AWAITING_REQUEST_TEXT:
            request_obj = _minimal_create_or_append_request(
                customer,
                text,
                telegram_message_id=message.get('message_id'),
            )
            reply_text = (
                f'📨 Сообщение сохранено в заявку #{request_obj.id}.\n'
                f'Передали оператору информацию по {_minimal_request_type_label(request_obj.request_type)}.'
            )
            send_telegram_message_to_chat(chat_id, reply_text)
        else:
            reply_text = 'Бот работает в безопасном режиме. Нажмите /start, чтобы открыть меню.'
            send_telegram_message_to_chat(chat_id, reply_text)

        _append_telegram_debug_log(
            f'message_sent chat_id={chat_id} reply={reply_text!r}'
        )
    except Exception as exc:
        logger.exception(
            'Telegram webhook failed. update_id=%s keys=%s',
            payload.get('update_id'),
            list(payload.keys()),
        )
        _append_telegram_debug_log(
            'webhook_error '
            f'update_id={payload.get("update_id")} error={exc!r}\n{traceback.format_exc()}'
        )
        try:
            operator_chat_id = getattr(settings, 'TELEGRAM_OPERATOR_CHAT_ID', '').strip()
            public_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '').strip()
            if operator_chat_id and operator_chat_id != public_chat_id:
                send_operator_notification(
                    'Webhook error on Render\n'
                    f'update_id={payload.get("update_id")}\n'
                    f'error={exc!r}'
                )
        except Exception:
            pass
        return JsonResponse({'ok': False, 'error': 'internal_error'}, status=500)

    return JsonResponse({'ok': True})


@login_required
def telegram_requests(request):
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        customer_request = get_object_or_404(TelegramCustomerRequest, id=request_id)

        if action == 'send_reply':
            reply_text = request.POST.get('reply_text', '').strip()
            operator_note = request.POST.get('operator_note', '').strip()

            if not reply_text:
                messages.error(request, 'Введите текст ответа клиенту')
                return redirect('operators:telegram_requests')

            try:
                send_request_message(
                    customer_request,
                    reply_text,
                    reply_markup=_minimal_operator_reply_markup(),
                    operator=request.user,
                )
            except Exception as exc:
                messages.error(request, f'Не удалось отправить ответ клиенту: {exc}')
                return redirect('operators:telegram_requests')

            customer_request.operator_note = operator_note
            customer_request.assigned_operator = customer_request.assigned_operator or request.user
            customer_request.status = TelegramCustomerRequest.STATUS_IN_PROGRESS
            customer_request.replied_at = timezone.now()
            customer_request.save(
                update_fields=[
                    'operator_note',
                    'assigned_operator',
                    'status',
                    'replied_at',
                    'updated_at',
                ]
            )
            messages.success(request, 'Ответ отправлен клиенту в Telegram')
        elif action == 'mark_done':
            close_request_and_notify_customer(customer_request)
            messages.success(request, 'Обращение закрыто')

        return redirect('operators:telegram_requests')

    context = _prepare_telegram_requests_data(mark_read=True)
    request.sidebar_counts_override = {
        'sidebar_new_requests_count': context['sidebar_new_requests_count'],
        'sidebar_in_progress_requests_count': context['sidebar_in_progress_requests_count'],
    }
    return render(request, 'operators/telegram_requests.html', context)


@login_required
@never_cache
def telegram_requests_live(request):
    context = _prepare_telegram_requests_data(mark_read=True)
    return JsonResponse({
        'active_html': render_to_string(
            'operators/_telegram_requests_active.html',
            context,
            request=request,
        ),
        'archive_html': render_to_string(
            'operators/_telegram_requests_archive.html',
            context,
            request=request,
        ),
        'new_requests_count': context['new_requests_count'],
        'in_progress_requests_count': context['in_progress_requests_count'],
        'archived_requests_count': context['archived_requests_count'],
        'latest_system_event_key': context['latest_system_event_key'],
        'latest_system_event_type': context['latest_system_event_type'],
        'latest_system_event_title': context['latest_system_event_title'],
        'latest_system_event_text': context['latest_system_event_text'],
        'latest_system_event_request_id': context['latest_system_event_request_id'],
    })
