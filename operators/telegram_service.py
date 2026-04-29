import requests
from django.conf import settings


TELEGRAM_MESSAGE_LIMIT = 4000
TELEGRAM_CAPTION_LIMIT = 1024


def _get_telegram_token():
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise ValueError('Не задан TELEGRAM_BOT_TOKEN')
    return token


def _get_telegram_chat_id():
    chat_id = settings.TELEGRAM_CHAT_ID
    if not chat_id:
        raise ValueError('Не задан TELEGRAM_CHAT_ID')
    return chat_id


def split_telegram_text(text, limit=TELEGRAM_MESSAGE_LIMIT):
    """
    Режем текст на части, максимально сохраняя исходные переносы и пустые строки.
    """
    text = (text or '').strip()
    if not text:
        return []

    parts = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break

        split_at = remaining.rfind('\n\n', 0, limit + 1)
        if split_at == -1:
            split_at = remaining.rfind('\n', 0, limit + 1)
        if split_at == -1:
            split_at = limit

        chunk = remaining[:split_at]
        if not chunk.strip():
            chunk = remaining[:limit]
            split_at = limit

        parts.append(chunk.rstrip())
        remaining = remaining[split_at:].lstrip('\n')

    return parts


def _telegram_request(method, payload):
    token = _get_telegram_token()

    url = f'https://api.telegram.org/bot{token}/{method}'
    response = requests.post(url, json=payload, timeout=20)

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError('Telegram вернул некорректный ответ') from exc

    if not response.ok or not data.get('ok'):
        description = data.get('description', 'Неизвестная ошибка Telegram')
        raise ValueError(f'Ошибка Telegram: {description}')

    return data['result']


def answer_telegram_callback(callback_query_id, text=''):
    payload = {
        'callback_query_id': callback_query_id,
    }
    if text:
        payload['text'] = text
    return _telegram_request('answerCallbackQuery', payload)


def send_telegram_message_to_chat(chat_id, text, reply_markup=None):
    payload = {
        'chat_id': chat_id,
        'text': text,
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return _telegram_request('sendMessage', payload)


def send_telegram_text_to_chat(chat_id, text, reply_markup=None, reply_markup_position='last'):
    messages = split_telegram_text(text)
    if not messages:
        raise ValueError('Нет текста для отправки')

    sent_messages = []
    last_index = len(messages) - 1

    for index, message in enumerate(messages):
        payload = {
            'chat_id': chat_id,
            'text': message,
        }
        if reply_markup:
            should_attach_markup = False

            if reply_markup_position == 'all':
                should_attach_markup = True
            elif reply_markup_position == 'first':
                should_attach_markup = index == 0
            else:
                should_attach_markup = index == last_index

            if should_attach_markup:
                payload['reply_markup'] = reply_markup
        result = _telegram_request('sendMessage', payload)
        sent_messages.append({
            'message_id': result['message_id'],
            'text': message,
        })

    return sent_messages


def send_telegram_messages(text, reply_markup=None):
    chat_id = _get_telegram_chat_id()

    return send_telegram_text_to_chat(chat_id, text, reply_markup=reply_markup)


def send_telegram_photo(photo_file, caption=''):
    token = _get_telegram_token()
    chat_id = _get_telegram_chat_id()

    if not photo_file:
        raise ValueError('Не передано фото для отправки')

    caption_parts = split_telegram_text(caption, limit=TELEGRAM_CAPTION_LIMIT) if caption else []
    first_caption = caption_parts[0] if caption_parts else ''
    extra_messages = caption_parts[1:] if len(caption_parts) > 1 else []

    if hasattr(photo_file, 'seek'):
        photo_file.seek(0)

    url = f'https://api.telegram.org/bot{token}/sendPhoto'
    response = requests.post(
        url,
        data={
            'chat_id': chat_id,
            'caption': first_caption,
        },
        files={
            'photo': (
                getattr(photo_file, 'name', 'telegram-photo'),
                photo_file,
                getattr(photo_file, 'content_type', 'application/octet-stream'),
            )
        },
        timeout=30
    )

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError('Telegram вернул некорректный ответ') from exc

    if not response.ok or not data.get('ok'):
        description = data.get('description', 'Неизвестная ошибка Telegram')
        raise ValueError(f'Ошибка Telegram: {description}')

    sent_messages = [{
        'message_id': data['result']['message_id'],
        'text': first_caption,
    }]

    for message in extra_messages:
        result = _telegram_request(
            'sendMessage',
            {
                'chat_id': chat_id,
                'text': message,
            }
        )
        sent_messages.append({
            'message_id': result['message_id'],
            'text': message,
        })

    return sent_messages


def delete_telegram_messages_from_chat(chat_id, message_ids):
    deleted_count = 0

    for message_id in message_ids:
        try:
            _telegram_request(
                'deleteMessage',
                {
                    'chat_id': chat_id,
                    'message_id': message_id,
                }
            )
            deleted_count += 1
        except ValueError as exc:
            description = str(exc).lower()
            if (
                'message to delete not found' in description
                or "message can't be deleted" in description
                or 'message can\'t be deleted' in description
            ):
                continue
            raise

    return deleted_count


def delete_telegram_messages(message_ids):
    chat_id = _get_telegram_chat_id()
    return delete_telegram_messages_from_chat(chat_id, message_ids)


def send_operator_notification(text):
    operator_chat_id = getattr(settings, 'TELEGRAM_OPERATOR_CHAT_ID', '').strip()
    if not operator_chat_id:
        return None
    return send_telegram_message_to_chat(operator_chat_id, text)


def get_telegram_updates(offset=None, timeout=25, allowed_updates=None):
    payload = {
        'timeout': timeout,
    }
    if offset is not None:
        payload['offset'] = offset
    if allowed_updates is not None:
        payload['allowed_updates'] = allowed_updates
    return _telegram_request('getUpdates', payload)


def delete_telegram_webhook(drop_pending_updates=False):
    payload = {}
    if drop_pending_updates:
        payload['drop_pending_updates'] = True
    return _telegram_request('deleteWebhook', payload)
