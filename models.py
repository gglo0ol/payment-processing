"""
SQLAlchemy ORM models for payments.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, JSON, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Currency(str, enum.Enum):
    """Supported payment currencies."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(str, enum.Enum):
    """Lifecycle status of a payment."""

    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


# SQLite-friendly string-backed enums (no native ENUM type).
_currency_enum = Enum(
    Currency,
    name="currency",
    native_enum=False,
    values_callable=lambda x: [e.value for e in x],
)
_status_enum = Enum(
    PaymentStatus,
    name="payment_status",
    native_enum=False,
    values_callable=lambda x: [e.value for e in x],
)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(_currency_enum, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        _status_enum,
        nullable=False,
        default=PaymentStatus.pending,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    webhook_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
