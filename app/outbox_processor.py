import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_pending_outbox_batch, mark_outbox_failed, mark_outbox_sent
from app.database import get_session_factory
from app.rabbit_queues import PAYMENTS_NEW_QUEUE

if TYPE_CHECKING:
    from faststream.rabbit import RabbitBroker

logger = logging.getLogger(__name__)


async def run_outbox_processor(
    rabbit: "RabbitBroker",
    stop: asyncio.Event,
    poll_interval_sec: float = 1.0,
) -> None:
    factory = get_session_factory()
    while not stop.is_set():
        try:
            async with factory() as session:
                await _process_batch(session, rabbit)
        except Exception:
            logger.exception("outbox processor loop error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_interval_sec)
        except TimeoutError:
            continue


async def _process_batch(session: AsyncSession, rabbit: "RabbitBroker") -> None:
    events = await get_pending_outbox_batch(session)
    for event in events:
        try:
            await rabbit.publish(event.payload, queue=PAYMENTS_NEW_QUEUE, persist=True)
            await mark_outbox_sent(session, event)
            logger.info("outbox event published: %s", event.id)
        except Exception:
            logger.exception("failed to publish outbox event %s", event.id)
            await mark_outbox_failed(session, event)
