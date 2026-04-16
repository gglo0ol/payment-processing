from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(..., max_digits=10, decimal_places=2)
    currency: Currency
    description: str | None = None
    metadata: dict[str, Any] | None = None
    webhook_url: HttpUrl | None = None


class PaymentAccepted(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentOut(BaseModel):
    id: UUID
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="payment_metadata",
        serialization_alias="metadata",
    )
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str | None
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(BaseModel):
    status: str = "ok"
