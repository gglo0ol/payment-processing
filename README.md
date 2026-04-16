# Микросервис асинхронной обработки платежей

Стек: **FastAPI**, **FastStream (RabbitMQ)**, **SQLAlchemy 2.0 + asyncpg**, **Alembic**, **Pydantic v2**, **httpx**, **tenacity**, **uvicorn**.

## Быстрый старт (Docker)

1. Скопируйте переменные окружения:

   ```bash
   cp .env.example .env
   ```

2. Запустите стек:

   ```bash
   docker compose up --build
   ```

Сервисы: **postgres**, **rabbitmq** (management UI на порту 15672), **api** (порт 8000), **consumer**.

При старте `api` выполняет `alembic upgrade head`, затем поднимает **uvicorn**. Фоновый **outbox** в API раз в секунду читает `outbox_events` со статусом `pending`, публикует в очередь `payments.new` и помечает событие как `sent`.

## Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# поднимите PostgreSQL и RabbitMQ или используйте docker compose только для инфраструктуры
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Отдельно consumer:

```bash
faststream run app.consumer:broker --log-level info
```

## Аутентификация

Для **всех** HTTP-эндпоинтов (включая `/health`) требуется заголовок `X-API-Key`, значение задаётся переменной `API_KEY` (по умолчанию `secret-key-123`).

## API

- `POST /api/v1/payments` — заголовки `X-API-Key`, `Idempotency-Key` (обязательны). Тело: `amount`, `currency` (`RUB` | `USD` | `EUR`), опционально `description`, `metadata`, `webhook_url`. Новый платёж: **202** и `payment_id`, `status`, `created_at`. Повтор с тем же `Idempotency-Key`: **200** и полный объект платежа.
- `GET /api/v1/payments/{payment_id}` — детали или **404**.
- `GET /health` — `{"status":"ok"}`.

## Очереди RabbitMQ

- `payments.new` — durable, с `x-dead-letter-exchange: ""` и `x-dead-letter-routing-key: payments.new.dlq`.
- `payments.new.dlq` — durable dead-letter queue.

Consumer имитирует обработку (пауза 2–5 с, ~90% `succeeded` / ~10% `failed`), обновляет платёж в БД и вызывает webhook JSON `{ "payment_id", "status", "amount", "currency" }`. Ошибки webhook повторяются до 3 раз с экспоненциальной задержкой (**tenacity**); после исчерпания попыток сообщение отклоняется без requeue и попадает в DLQ.


## Миграции

```bash
alembic upgrade head
```

Синхронный URL для Alembic: `postgresql+psycopg2://...` (см. `app/settings.py`).
