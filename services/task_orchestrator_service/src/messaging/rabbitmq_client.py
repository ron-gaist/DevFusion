import json
import asyncio
from typing import Callable, Dict, Any, Optional
from aio_pika import connect_robust, Message, Queue, Exchange
from aio_pika.abc import AbstractConnection, AbstractChannel

from ...config.env_settings import OrchestratorSettings


class RabbitMQClient:
    def __init__(self, settings: OrchestratorSettings):
        self.settings = settings
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchange: Optional[Exchange] = None
        self.queue: Optional[Queue] = None
        self._handlers: Dict[str, Callable] = {}

    async def connect(self):
        """Establish connection to RabbitMQ."""
        self.connection = await connect_robust(self.settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
            self.settings.RABBITMQ_EXCHANGE,
            durable=True
        )
        self.queue = await self.channel.declare_queue(
            self.settings.RABBITMQ_QUEUE,
            durable=True
        )
        
        # Bind queue to exchange with routing keys
        for binding_key in self.settings.RABBITMQ_BINDING_KEYS:
            await self.queue.bind(self.exchange, binding_key)

    async def close(self):
        """Close RabbitMQ connection."""
        if self.connection:
            await self.connection.close()

    async def publish_message(
        self,
        message: Dict[str, Any],
        routing_key: str,
        headers: Optional[Dict[str, str]] = None
    ):
        """Publish a message to RabbitMQ."""
        if not self.channel or not self.exchange:
            raise RuntimeError("RabbitMQ client not connected")

        message_body = json.dumps(message).encode()
        message = Message(
            body=message_body,
            headers=headers or {},
            delivery_mode=2  # Make message persistent
        )
        await self.exchange.publish(message, routing_key=routing_key)

    async def consume_messages(self):
        """Start consuming messages from RabbitMQ."""
        if not self.queue:
            raise RuntimeError("RabbitMQ client not connected")

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        message_body = json.loads(message.body.decode())
                        routing_key = message.routing_key
                        
                        if routing_key in self._handlers:
                            await self._handlers[routing_key](message_body)
                    except Exception as e:
                        # Log error and continue processing
                        print(f"Error processing message: {e}")

    def register_handler(self, routing_key: str, handler: Callable):
        """Register a message handler for a specific routing key."""
        self._handlers[routing_key] = handler

    async def start_consuming(self):
        """Start consuming messages in the background."""
        asyncio.create_task(self.consume_messages()) 