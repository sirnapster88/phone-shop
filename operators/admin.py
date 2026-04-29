from django.contrib import admin
from .models import (
    Supplier,
    PriceList,
    Product,
    AggregatedProduct,
    ProductPrice,
    TelegramPublication,
    OperatorPrice,
    TelegramChatCleanupTask,
    TelegramCustomer,
    TelegramCustomerMessage,
    TelegramCustomerRequest,
)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'uploaded_at', 'uploaded_by', 'status')
    list_filter = ('status', 'supplier', 'uploaded_at')
    readonly_fields = ('uploaded_at',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'supplier', 'price', 'created_at')
    list_filter = ('supplier', 'created_at')
    search_fields = ('model', 'color', 'memory')
    
    def display_name(self, obj):
        return str(obj)
    display_name.short_description = 'Товар'

@admin.register(AggregatedProduct)
class AggregatedProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'get_suppliers_count')
    search_fields = ('model', 'color', 'memory')
    
    def get_suppliers_count(self, obj):
        return obj.prices.count()
    get_suppliers_count.short_description = 'Поставщиков'

@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ('aggregated_product', 'supplier', 'price', 'created_at')
    list_filter = ('supplier', 'created_at')


@admin.register(TelegramPublication)
class TelegramPublicationAdmin(admin.ModelAdmin):
    list_display = ('kind', 'created_at', 'sent_by', 'is_active', 'has_photo')
    list_filter = ('kind', 'is_active', 'created_at')
    search_fields = ('text',)

    def has_photo(self, obj):
        return bool(obj.photo)
    has_photo.short_description = 'Фото'
    has_photo.boolean = True


@admin.register(OperatorPrice)
class OperatorPriceAdmin(admin.ModelAdmin):
    list_display = ('aggregated_product', 'price', 'source_supplier', 'updated_by', 'updated_at')
    list_filter = ('updated_at', 'source_supplier')
    search_fields = ('aggregated_product__brand', 'aggregated_product__model', 'aggregated_product__color')


@admin.register(TelegramCustomer)
class TelegramCustomerAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'first_name', 'state', 'last_seen_at')
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    list_filter = ('state', 'last_seen_at')


@admin.register(TelegramCustomerRequest)
class TelegramCustomerRequestAdmin(admin.ModelAdmin):
    list_display = ('customer', 'request_type', 'status', 'product_query', 'assigned_operator', 'created_at')
    list_filter = ('request_type', 'status', 'created_at')
    search_fields = ('customer__username', 'customer__first_name', 'product_query', 'client_message')


@admin.register(TelegramCustomerMessage)
class TelegramCustomerMessageAdmin(admin.ModelAdmin):
    list_display = ('request', 'sender_type', 'operator', 'created_at')
    list_filter = ('sender_type', 'created_at')
    search_fields = ('request__customer__username', 'request__customer__first_name', 'text')


@admin.register(TelegramChatCleanupTask)
class TelegramChatCleanupTaskAdmin(admin.ModelAdmin):
    list_display = ('request', 'customer', 'due_at', 'processed_at', 'failed_attempts')
    list_filter = ('processed_at', 'due_at')
    search_fields = ('request__id', 'customer__username', 'customer__first_name')
