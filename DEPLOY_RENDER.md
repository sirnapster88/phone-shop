# Deploy on Render

## Services

- `phone-shop-demo` - Django web service
- `phone-shop-db` - Render Postgres

## Before first deploy

1. Push the repository to GitHub.
2. In Render, create a new Blueprint from this repository.
3. During setup, fill in secret env vars:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `TELEGRAM_OPERATOR_CHAT_ID`
   - `TELEGRAM_BOT_USERNAME`
4. After the first deploy, note the real Render URL and update:
   - `DJANGO_ALLOWED_HOSTS`
   - `DJANGO_CSRF_TRUSTED_ORIGINS`

## Telegram webhook

Set the webhook to:

`https://<your-render-domain>/operators/telegram-bot/webhook/<TELEGRAM_WEBHOOK_SECRET>/`

Example:

`https://phone-shop-demo.onrender.com/operators/telegram-bot/webhook/<secret>/`

## Notes

- Free Render web services have an ephemeral filesystem.
- Files in `media/` are not durable on the free plan.
- For a more stable demo with uploaded photos, move media to object storage or use a paid disk-backed service.
- Delayed Telegram cleanup works in lazy mode on the free plan:
  - cleanup is processed on webhook calls
  - cleanup is also processed when operators open the app
  - if the app has no traffic for some time, message cleanup can happen with delay
- On the free plan Render does not support `preDeployCommand`, so database migrations run inside the web service start command.
