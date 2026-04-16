from faststream.rabbit import RabbitQueue

PAYMENTS_DLQ_NAME = "payments.new.dlq"
PAYMENTS_QUEUE_NAME = "payments.new"

# DLQ должна существовать до основной очереди (dead-letter routing).
PAYMENTS_DLQ = RabbitQueue(PAYMENTS_DLQ_NAME, durable=True)

PAYMENTS_NEW_QUEUE = RabbitQueue(
    PAYMENTS_QUEUE_NAME,
    durable=True,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": PAYMENTS_DLQ_NAME,
    },
)
