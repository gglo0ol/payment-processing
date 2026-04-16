import asyncio
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

import httpx
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.database import get_session_factory
from app.models import Payment, PaymentStatus
from app.rabbit_queues import PAYMENTS_DLQ, PAYMENTS_NEW_QUEUE
from app.settings import get_settings

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

settings = get_settings()
rabbitmq_broker = RabbitBroker(settings.rabbitmq_url)
broker = FastStream(rabbitmq_broker)


@broker.after_startup
async def _after_startup() -> None:
    get_session_factory()
    await rabbitmq_broker.declare_queue(PAYMENTS_DLQ)
    logger.info("consumer ready: DLQ declared, DB session factory initialized")


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _post_webhook(client: httpx.AsyncClient, url: str, payload: dict) -> None:
    response = await client.post(url, json=payload, timeout=30.0)
    response.raise_for_status()


async def _handle_payload(session: AsyncSession, data: dict) -> None:
    payment_id = UUID(data["payment_id"])
    await asyncio.sleep(random.uniform(2.0, 5.0))

    new_status = PaymentStatus.succeeded if random.random() < 0.9 else PaymentStatus.failed

    result = await session.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        logger.error("payment not found: %s", payment_id)
        raise ValueError(f"payment not found: {payment_id}")

    payment.status = new_status
    payment.processed_at = datetime.now(timezone.utc)
    await session.commit()

    webhook_url = payment.webhook_url or data.get("webhook_url")
    if not webhook_url:
        logger.warning("no webhook_url for payment %s", payment_id)
        return

    body = {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
    }

    try:
        async with httpx.AsyncClient() as client:
            await _post_webhook(client, webhook_url, body)
        logger.info("webhook delivered for payment %s", payment_id)
    except Exception:
        logger.exception("webhook failed after retries for payment %s", payment_id)
        raise


@rabbitmq_broker.subscriber(PAYMENTS_NEW_QUEUE)
async def handle_payment_created(payload: dict) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await _handle_payload(session, payload)
