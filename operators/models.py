from django.db import models
from django.contrib.auth.models import User


def _compose_product_display_name(brand, model, color='', memory='', region='', sim_type='', specs=''):
    parts = []
    brand_value = (brand or '').strip()
    model_value = (model or '').strip()

    if brand_value and model_value:
        if model_value.lower().startswith(brand_value.lower()):
            parts.append(model_value)
        else:
            parts.extend([brand_value, model_value])
    elif brand_value:
        parts.append(brand_value)
    elif model_value:
        parts.append(model_value)

    if color:
        parts.append(color)
    if memory:
        parts.append(f"{memory}gb")
    if region:
        parts.append(region)
    if sim_type:
        parts.append(sim_type)
    if specs:
        parts.append(specs)

    return ' '.join(parts)


class Supplier(models.Model):
    """Поставщик"""
    name = models.CharField(max_length=200, verbose_name="Название")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"

    def __str__(self):
        return self.name


class PriceList(models.Model):
    """Загруженный прайс-лист"""
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, verbose_name="Поставщик")
    file = models.FileField(
            upload_to='pricelists/%Y/%m/%d/',
            verbose_name="Файл",
            blank=True,
            null=True
        )

    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Загружен")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, default='new', verbose_name="Статус")

    class Meta:
        verbose_name = "Прайс-лист"
        verbose_name_plural = "Прайс-листы"

    def __str__(self):
        return f"{self.supplier.name} - {self.uploaded_at}"


class Product(models.Model):
    """Товар (уже разобранный на составляющие)"""
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, verbose_name="Поставщик")
    pricelist = models.ForeignKey(PriceList, on_delete=models.CASCADE, null=True)

    # Разобранные данные
    category = models.CharField(max_length=50, blank=True, verbose_name="Категория")
    brand = models.CharField(max_length=100, blank=True, verbose_name="Бренд")
    model = models.CharField(max_length=200, verbose_name="Модель")
    color = models.CharField(max_length=100, blank=True, verbose_name="Цвет")
    memory = models.CharField(max_length=50, blank=True, verbose_name="Память")
    region = models.CharField(max_length=100, blank=True, verbose_name="Регион")
    sim_type = models.CharField(max_length=50, blank=True, verbose_name="SIM")
    specs = models.CharField(max_length=255, blank=True, verbose_name="Характеристики")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")


    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self):
        return _compose_product_display_name(
            self.brand,
            self.model,
            self.color,
            self.memory,
            self.region,
            self.sim_type,
            self.specs,
        )


    @property
    def display_name(self):
        return _compose_product_display_name(
            self.brand,
            self.model,
            self.color,
            self.memory,
            self.region,
            self.sim_type,
            self.specs,
        )



class AggregatedProduct(models.Model):
    """Сводный товар (уникальная комбинация brand+model+color+memory+region+sim_type)"""
    category = models.CharField(max_length=50, blank=True, verbose_name="Категория")
    brand = models.CharField(max_length=100, blank=True, verbose_name="Бренд")
    model = models.CharField(max_length=200, verbose_name="Модель")
    color = models.CharField(max_length=100, blank=True, verbose_name="Цвет")
    memory = models.CharField(max_length=50, blank=True, verbose_name="Память")
    region = models.CharField(max_length=100, blank=True, verbose_name="Регион")
    sim_type = models.CharField(max_length=50, blank=True, verbose_name="SIM")
    specs = models.CharField(max_length=255, blank=True, verbose_name="Характеристики")


    class Meta:
        verbose_name = "Сводный товар"
        verbose_name_plural = "Сводные товары"
        unique_together = ['category', 'brand', 'model', 'color', 'memory', 'region', 'sim_type', 'specs']

    def __str__(self):
        return _compose_product_display_name(
            self.brand,
            self.model,
            self.color,
            self.memory,
            self.region,
            self.sim_type,
            self.specs,
        )



class ProductPrice(models.Model):
    """Цена на сводный товар от конкретного поставщика"""
    aggregated_product = models.ForeignKey(AggregatedProduct, on_delete=models.CASCADE, related_name='prices')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)  # исходный товар
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Цена поставщика"
        verbose_name_plural = "Цены поставщиков"
        unique_together = ['aggregated_product', 'supplier']


class TelegramPublication(models.Model):
    KIND_PRICE = 'price'
    KIND_MANUAL = 'manual'

    KIND_CHOICES = [
        (KIND_PRICE, 'Прайс'),
        (KIND_MANUAL, 'Ручное сообщение'),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name="Тип публикации")
    text = models.TextField(verbose_name="Текст")
    photo = models.FileField(
        upload_to='telegram/%Y/%m/%d/',
        verbose_name="Фото",
        blank=True,
        null=True
    )
    message_ids = models.JSONField(default=list, blank=True, verbose_name="ID сообщений Telegram")
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Отправил")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    class Meta:
        verbose_name = "Публикация Telegram"
        verbose_name_plural = "Публикации Telegram"
        ordering = ['-created_at']

    def __str__(self):
        label = 'Прайс' if self.kind == self.KIND_PRICE else 'Сообщение'
        return f"{label} {self.created_at:%d.%m.%Y %H:%M}"


class OperatorPrice(models.Model):
    aggregated_product = models.OneToOneField(
        AggregatedProduct,
        on_delete=models.CASCADE,
        related_name='operator_price',
        verbose_name="Товар"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена оператора")
    source_supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operator_prices',
        verbose_name="Источник цены"
    )
    source_note = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Обновил"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Витринная цена"
        verbose_name_plural = "Витринные цены"
        ordering = ['aggregated_product__brand', 'aggregated_product__model']

    def __str__(self):
        return f"{self.aggregated_product} — {self.price}"


class TelegramCustomer(models.Model):
    STATE_IDLE = ''
    STATE_AWAITING_REQUEST_TEXT = 'awaiting_request_text'

    STATE_CHOICES = [
        (STATE_IDLE, 'Нет активного сценария'),
        (STATE_AWAITING_REQUEST_TEXT, 'Ожидает текст обращения'),
    ]

    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=255, blank=True, verbose_name="Username")
    first_name = models.CharField(max_length=255, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=255, blank=True, verbose_name="Фамилия")
    language_code = models.CharField(max_length=20, blank=True, verbose_name="Язык")
    state = models.CharField(max_length=64, choices=STATE_CHOICES, default=STATE_IDLE, blank=True, verbose_name="Состояние")
    pending_request_type = models.CharField(max_length=32, blank=True, verbose_name="Ожидаемый тип обращения")
    pending_chat_message_ids = models.JSONField(default=list, blank=True, verbose_name="Ожидающие ID сообщений Telegram")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    last_seen_at = models.DateTimeField(auto_now=True, verbose_name="Последняя активность")

    class Meta:
        verbose_name = "Telegram клиент"
        verbose_name_plural = "Telegram клиенты"
        ordering = ['-last_seen_at']

    def __str__(self):
        label = self.first_name or self.username or str(self.telegram_id)
        return f"{label} ({self.telegram_id})"


class TelegramCustomerRequest(models.Model):
    TYPE_PRICE = 'price'
    TYPE_AVAILABILITY = 'availability'
    TYPE_ORDER = 'order'
    TYPE_QUESTION = 'question'

    TYPE_CHOICES = [
        (TYPE_PRICE, 'Уточнение цены'),
        (TYPE_AVAILABILITY, 'Уточнение наличия'),
        (TYPE_ORDER, 'Заказ'),
        (TYPE_QUESTION, 'Вопрос'),
    ]

    STATUS_NEW = 'new'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_NEW, 'Новая'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_DONE, 'Закрыта'),
        (STATUS_CANCELLED, 'Отменена'),
    ]

    customer = models.ForeignKey(
        TelegramCustomer,
        on_delete=models.CASCADE,
        related_name='requests',
        verbose_name="Клиент"
    )
    request_type = models.CharField(max_length=32, choices=TYPE_CHOICES, verbose_name="Тип обращения")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_NEW, verbose_name="Статус")
    publication = models.ForeignKey(
        TelegramPublication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_requests',
        verbose_name="Публикация"
    )
    product = models.ForeignKey(
        AggregatedProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_requests',
        verbose_name="Товар"
    )
    product_query = models.CharField(max_length=255, blank=True, verbose_name="Запрос по товару")
    client_message = models.TextField(verbose_name="Сообщение клиента")
    operator_note = models.TextField(blank=True, verbose_name="Заметка оператора")
    operator_reply = models.TextField(blank=True, verbose_name="Ответ клиенту")
    has_unread_customer_message = models.BooleanField(default=True, verbose_name="Есть непрочитанное сообщение клиента")
    unread_messages_count = models.PositiveIntegerField(default=1, verbose_name="Количество непрочитанных сообщений клиента")
    extra_message_ids = models.JSONField(default=list, blank=True, verbose_name="Дополнительные ID сообщений Telegram")
    assigned_operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_customer_requests',
        verbose_name="Оператор"
    )
    telegram_message_id = models.BigIntegerField(null=True, blank=True, verbose_name="ID сообщения Telegram")
    replied_at = models.DateTimeField(null=True, blank=True, verbose_name="Ответ отправлен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Запрос клиента из Telegram"
        verbose_name_plural = "Запросы клиентов из Telegram"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_request_type_display()} — {self.customer}"


class TelegramCustomerMessage(models.Model):
    SENDER_CUSTOMER = 'customer'
    SENDER_OPERATOR = 'operator'

    SENDER_CHOICES = [
        (SENDER_CUSTOMER, 'Клиент'),
        (SENDER_OPERATOR, 'Оператор'),
    ]

    request = models.ForeignKey(
        TelegramCustomerRequest,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name="Заявка"
    )
    sender_type = models.CharField(max_length=20, choices=SENDER_CHOICES, verbose_name="Отправитель")
    text = models.TextField(verbose_name="Текст сообщения")
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_messages',
        verbose_name="Оператор"
    )
    telegram_message_id = models.BigIntegerField(null=True, blank=True, verbose_name="ID сообщения Telegram")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Сообщение в заявке Telegram"
        verbose_name_plural = "Сообщения в заявках Telegram"
        ordering = ['created_at']

    def __str__(self):
        return f"{self.get_sender_type_display()} — {self.request_id}"


class TelegramChatCleanupTask(models.Model):
    request = models.ForeignKey(
        TelegramCustomerRequest,
        on_delete=models.CASCADE,
        related_name='cleanup_tasks',
        verbose_name="Заявка"
    )
    customer = models.ForeignKey(
        TelegramCustomer,
        on_delete=models.CASCADE,
        related_name='cleanup_tasks',
        verbose_name="Клиент"
    )
    chat_id = models.BigIntegerField(verbose_name="Telegram chat ID")
    message_ids = models.JSONField(default=list, blank=True, verbose_name="ID сообщений для удаления")
    due_at = models.DateTimeField(verbose_name="Удалить после")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Обработано")
    failed_attempts = models.PositiveIntegerField(default=0, verbose_name="Ошибок обработки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Очередь очистки Telegram-чата"
        verbose_name_plural = "Очередь очистки Telegram-чатов"
        ordering = ['due_at']

    def __str__(self):
        return f"Cleanup #{self.request_id} at {self.due_at:%d.%m.%Y %H:%M}"
