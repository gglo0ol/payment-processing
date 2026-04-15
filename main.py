from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, dispose_engine, get_db, init_db
from models import Payment, PaymentStatus, utc_now
from schemas import HealthResponse, PaymentAccepted, PaymentCreate, PaymentRead

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def process_payment_task(payment_id: UUID) -> None:
    """
    Emulate gateway latency, finalize status, and POST a fire-and-forget webhook.
    """
    await asyncio.sleep(5)

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Payment).where(Payment.id == payment_id))
            payment = result.scalar_one_or_none()
            if payment is None:
                logger.warning("Payment %s not found; skipping background processing", payment_id)
                return

            new_status = PaymentStatus.succeeded if random.random() < 0.8 else PaymentStatus.failed
            payment.status = new_status
            payment.processed_at = utc_now()
            await session.commit()

            payload = {
                "payment_id": str(payment.id),
                "status": new_status.value,
                "amount": float(payment.amount),
                "currency": payment.currency.value,
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.post(payment.webhook_url, json=payload)
            except Exception:
                logger.exception(
                    "Webhook delivery failed for payment %s (url=%s)",
                    payment_id,
                    payment.webhook_url,
                )
        except Exception:
            logger.exception("Background processing failed for payment %s", payment_id)
            await session.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB schema on startup; release engine on shutdown."""
    await init_db()
    logger.info("Database initialized")
    yield
    await dispose_engine()
    logger.info("Engine disposed")


app = FastAPI(
    title="Payment Processing Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok")


@app.post(
    "/api/v1/payments",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["payments"],
    responses={
        status.HTTP_200_OK: {"description": "Existing payment for idempotency key"},
        status.HTTP_202_ACCEPTED: {"description": "Payment accepted for processing"},
    },
)
async def create_payment(
    body: PaymentCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    """
    Create a payment or return an existing one when the idempotency key repeats.
    """
    result = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=PaymentRead.model_validate(existing).model_dump(mode="json"),
        )

    payment = Payment(
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        metadata_=body.metadata,
        status=PaymentStatus.pending,
        idempotency_key=idempotency_key,
        webhook_url=body.webhook_url,
    )
    db.add(payment)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.info("Idempotency race resolved via IntegrityError for key=%s", idempotency_key)
        result = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        existing = result.scalar_one_or_none()
        if existing is None:
            logger.error("Could not load payment after idempotency conflict")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Idempotency conflict could not be resolved",
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=PaymentRead.model_validate(existing).model_dump(mode="json"),
        )

    await db.refresh(payment)
    background_tasks.add_task(process_payment_task, payment.id)

    accepted = PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=accepted.model_dump(mode="json"),
    )


@app.get(
    "/api/v1/payments/{payment_id}",
    response_model=PaymentRead,
    tags=["payments"],
)
async def get_payment(
    payment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentRead:
    """Return a single payment by id."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentRead.model_validate(payment)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
