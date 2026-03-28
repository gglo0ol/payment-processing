from sqlalchemy.engine import create_engine
from pika import BlockingConnection, ConnectionParameters

# RabbitMq
connection = BlockingConnection(ConnectionParameters('localhost'))
channel = connection.channel()

# Sqlalchemy
