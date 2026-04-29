# Phone Shop Operator Dashboard

Демо-проект панели оператора для магазина техники на Django.

## Что умеет

- загрузка прайс-листов из файла или текста
- ручное обновление каталога и витринных цен
- таблица сравнения поставщиков
- генерация и публикация прайса в Telegram
- Telegram-бот для входящих клиентских обращений
- очередь заявок оператора с живым обновлением

## Стек

- Python
- Django
- PostgreSQL
- Telegram Bot API
- Bootstrap + кастомный CSS

## Локальный запуск

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Deploy

Проект подготовлен под бесплатный деплой на Render.

Смотрите:

- [DEPLOY_RENDER.md](./DEPLOY_RENDER.md)
- [render.yaml](./render.yaml)

## Важно

- На бесплатном Render файловая система эфемерная.
- Загруженные медиафайлы в таком режиме не являются постоянными.
- Telegram cleanup в демо-режиме работает лениво: при webhook-запросах и заходах в интерфейс.
