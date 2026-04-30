from django.urls import path
from . import views

app_name = 'operators'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('ui-preview/', views.ui_preview, name='ui_preview'),
    path('telegram-debug-log/', views.telegram_debug_log, name='telegram_debug_log'),
    path('env-debug/', views.env_debug, name='env_debug'),
    path('upload/', views.upload_pricelist, name='upload_pricelist'),
    path('process/<int:pricelist_id>/', views.process_pricelist, name='process_pricelist'),
    
    # Удаление
    path('delete-pricelist/<int:pricelist_id>/', views.delete_pricelist, name='delete_pricelist'),
    path('delete-all-pricelists/', views.delete_all_pricelists, name='delete_all_pricelists'),
    
    # Сравнение и агрегация
    path('comparison/', views.comparison_table, name='comparison_table'),
    path('manual-prices/', views.manual_price_editor, name='manual_price_editor'),
    path('seed-catalog/', views.seed_catalog_view, name='seed_catalog'),
    path('clear-catalog/', views.clear_catalog_view, name='clear_catalog'),
    path('aggregation/', views.run_aggregation, name='run_aggregation'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('start-new-day/', views.start_new_day, name='start_new_day'),

    # Telegram-конструктор
    path('telegram-price/', views.telegram_price_builder, name='telegram_price_builder'),
    path('telegram-price/send/', views.send_telegram_pricelist, name='send_telegram_pricelist'),
    path('telegram-price/send-manual/', views.send_telegram_manual_message, name='send_telegram_manual_message'),
    path('telegram-requests/', views.telegram_requests, name='telegram_requests'),
    path('telegram-requests/live/', views.telegram_requests_live, name='telegram_requests_live'),
    path('sidebar-counts/', views.sidebar_counts_api, name='sidebar_counts_api'),
    path('telegram-bot/webhook/', views.telegram_bot_webhook, name='telegram_bot_webhook_plain'),
    path('telegram-bot/webhook/<path:webhook_secret>/', views.telegram_bot_webhook, name='telegram_bot_webhook'),

    path('logout/', views.app_logout, name='logout'),


]
