from pydantic import BaseModel

class Payment(BaseModel):
    id: int
    cost: decimal
    value: str # Rub, eur, usd
    description: str
    meta_data: json
    status: str
    idempotency_key: str
    webhook_url: str
    create_at
    processed_at