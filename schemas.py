"""
Pydantic v2 request/response schemas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from models import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    """Payload for creating a payment."""

    amount: Decimal = Field(..., max_digits=10, decimal_places=2)
    currency: Currency
    description: str = Field(..., max_length=500)
    metadata: dict[str, Any] | None = None
    webhook_url: str = Field(..., max_length=2048)


class PaymentAccepted(BaseModel):
    """202 Accepted body for a newly queued payment."""

    payment_id: UUID
    status: PaymentStatus
    created_at: datetime


class PaymentRead(BaseModel):
    """Full payment representation (API / idempotent replay)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="metadata_",
    )
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @field_serializer("amount", when_used="json-unless-none")
    def serialize_amount(self, value: Decimal) -> float:
        return float(value)


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str = "ok"
