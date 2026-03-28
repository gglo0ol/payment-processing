from fastapi import FastAPI


app = FastAPI()

@app.post("/api/v1/payments")
async def create_payment(data):
    return {}

@app.get("/api/v1/payments/{payment_id}")
async def get_payment(payment_id: str):
    return {}