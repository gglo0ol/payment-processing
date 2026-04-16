import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    create_payment_with_outbox,
    get_payment_by_id,
    get_payment_by_idempotency_key,
)
from app.database import get_db_session
from app.dependencies import verify_api_key
from app.outbox_processor import run_outbox_processor
from app.rabbit_queues import PAYMENTS_DLQ, PAYMENTS_NEW_QUEUE
from app.schemas import HealthResponse, PaymentAccepted, PaymentCreate, PaymentOut
from app.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from faststream.rabbit import RabbitBroker

    settings = get_settings()
    rabbit = RabbitBroker(settings.rabbitmq_url)
    stop = asyncio.Event()
    await rabbit.start()
    await rabbit.declare_queue(PAYMENTS_DLQ)
    await rabbit.declare_queue(PAYMENTS_NEW_QUEUE)
    outbox_task = asyncio.create_task(run_outbox_processor(rabbit, stop))
    app.state.rabbit_broker = rabbit
    app.state.outbox_stop = stop
    app.state.outbox_task = outbox_task
    logger.info("API started, outbox processor running")
    try:
        yield
    finally:
        stop.set()
        outbox_task.cancel()
        try:
            await outbox_task
        except asyncio.CancelledError:
            pass
        await rabbit.close()
        logger.info("API stopped")


app = FastAPI(title="Payment processing", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health(_: Annotated[None, Depends(verify_api_key)]) -> HealthResponse:
    return HealthResponse(status="ok")


api_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)],
)


@api_router.post(
    "/payments",
    responses={
        status.HTTP_202_ACCEPTED: {"model": PaymentAccepted},
        status.HTTP_200_OK: {"model": PaymentOut},
    },
)
async def create_payment(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    body: PaymentCreate,
):
    existing = await get_payment_by_idempotency_key(session, idempotency_key)
    if existing is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(PaymentOut.model_validate(existing)),
        )

    payment = await create_payment_with_outbox(session, body, idempotency_key)
    payload = PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=jsonable_encoder(payload),
    )


@api_router.get("/payments/{payment_id}", response_model=PaymentOut)
async def read_payment(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payment_id: UUID,
):
    payment = await get_payment_by_id(session, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentOut.model_validate(payment)


app.include_router(api_router)
