from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, OutboxStatus, Payment, PaymentStatus
from app.schemas import PaymentCreate


async def get_payment_by_id(session: AsyncSession, payment_id: UUID) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.id == payment_id))
    return result.scalar_one_or_none()


async def get_payment_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.idempotency_key == idempotency_key),
    )
    return result.scalar_one_or_none()


async def create_payment_with_outbox(
    session: AsyncSession,
    data: PaymentCreate,
    idempotency_key: str,
) -> Payment:
    webhook = str(data.webhook_url) if data.webhook_url is not None else None

    payment = Payment(
        amount=Decimal(data.amount),
        currency=data.currency,
        description=data.description,
        payment_metadata=data.metadata,
        status=PaymentStatus.pending,
        idempotency_key=idempotency_key,
        webhook_url=webhook,
    )
    session.add(payment)
    await session.flush()

    payload = {
        "payment_id": str(payment.id),
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "webhook_url": payment.webhook_url,
    }
    outbox = OutboxEvent(
        event_type="payment.created",
        payload=payload,
        status=OutboxStatus.pending,
    )
    session.add(outbox)
    await session.commit()
    await session.refresh(payment)
    return payment


async def get_pending_outbox_batch(
    session: AsyncSession,
    limit: int = 50,
) -> list[OutboxEvent]:
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.pending)
        .order_by(OutboxEvent.created_at)
        .limit(limit),
    )
    return list(result.scalars().all())


async def mark_outbox_sent(session: AsyncSession, event: OutboxEvent) -> None:
    event.status = OutboxStatus.sent
    event.processed_at = datetime.now(timezone.utc)
    await session.commit()


async def mark_outbox_failed(session: AsyncSession, event: OutboxEvent) -> None:
    event.status = OutboxStatus.failed
    event.processed_at = datetime.now(timezone.utc)
    await session.commit()


async def update_payment_processing(
    session: AsyncSession,
    payment: Payment,
    status: PaymentStatus,
) -> None:
    payment.status = status
    payment.processed_at = datetime.now(timezone.utc)
    await session.commit()
