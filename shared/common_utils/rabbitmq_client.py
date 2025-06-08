import asyncio
import json
import os
from typing import Any, Callable, Optional, Awaitable, Dict, List, Tuple
from datetime import datetime, timedelta

import aio_pika
from aio_pika.abc import (
    AbstractRobustConnection,
    AbstractRobustChannel,
    AbstractIncomingMessage,
    AbstractQueue,
)

from .logger import logger


class RabbitMQClient:
    """
    An asynchronous RabbitMQ client for DevFusion, with enhanced stability features:
    - Robust connection management with automatic reconnection
    - Health monitoring and status reporting
    - Enhanced error handling and recovery
    - Service-specific configuration
    """

    def __init__(
        self,
        service_name: str,
        rabbitmq_url: Optional[str] = None,
        prefetch_count: int = 1,
        max_retries: int = 5,
        retry_backoff: int = 1,
        health_check_interval: int = 30,
        version: Optional[str] = None,
    ):
        """
        Initializes the RabbitMQ client with service-specific configurations.

        Args:
            service_name: Name of the service using this client (e.g., 'task_orchestrator_service')
            rabbitmq_url: The RabbitMQ connection URL. If None, will use from environment variable
            prefetch_count: Prefetch count for consumers
            max_retries: Max retries for connection, publish, and consumer setup
            retry_backoff: Base delay in seconds for exponential backoff
            health_check_interval: Interval in seconds for health checks
            version: Service version. If None, will use from environment variable
        """
        self.service_name = service_name
        self.rabbitmq_url = rabbitmq_url or os.getenv(
            f"{service_name.upper()}_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.version = version or os.getenv(f"{service_name.upper()}_VERSION", "1.0.0")

        self.connection: Optional[AbstractRobustConnection] = None
        self.is_connecting = False
        self.connection_lock = asyncio.Lock()
        self.last_health_check: Optional[datetime] = None
        self.health_check_interval = health_check_interval
        self.health_status = {
            "is_healthy": False,
            "last_check": None,
            "connection_status": "disconnected",
            "error_count": 0,
            "last_error": None,
            "service_name": service_name,
            "version": self.version,
        }

        self.prefetch_count = prefetch_count
        self.max_retries = max_retries
        self.retry_backoff = float(retry_backoff)

        self.active_consumers: Dict[
            str, Tuple[AbstractRobustChannel, str, asyncio.Task]
        ] = {}
        self._consumer_management_lock = asyncio.Lock()

        logger.info(
            f"DevFusion RabbitMQClient initialized for service '{service_name}' (v{self.version})"
        )
        logger.info(f"URL: '{self.rabbitmq_url}', Prefetch: {self.prefetch_count}")
        logger.info(
            f"Retry config: MaxRetries={self.max_retries}, BackoffBase={self.retry_backoff}s"
        )
        logger.info(f"Health check interval: {self.health_check_interval}s")

    async def _get_connection(self) -> AbstractRobustConnection:
        """Enhanced connection management with health checks and better error handling."""
        if self.connection and not self.connection.is_closed:
            # Perform quick health check if needed
            if self._should_perform_health_check():
                await self._perform_health_check()
            return self.connection

        async with self.connection_lock:
            if self.connection and not self.connection.is_closed:
                return self.connection

            self.is_connecting = True
            logger.info(f"[{self.service_name}] Attempting to connect to RabbitMQ...")
            retries_count = 0
            last_error = None

            while retries_count < self.max_retries:
                try:
                    self.connection = await aio_pika.connect_robust(
                        self.rabbitmq_url,
                        timeout=15,
                        client_properties={
                            "connection_name": f"{self.service_name}_{os.getpid()}",
                            "product": "DevFusion",
                            "version": self.version,
                            "service": self.service_name,
                        },
                    )
                    logger.info(
                        f"[{self.service_name}] Successfully connected to RabbitMQ."
                    )
                    self.connection.add_close_callback(self._on_connection_closed)
                    self.connection.add_reconnect_callback(
                        self._on_connection_reconnected
                    )
                    self.is_connecting = False
                    self.health_status.update(
                        {
                            "is_healthy": True,
                            "connection_status": "connected",
                            "last_check": datetime.now(),
                            "error_count": 0,
                            "last_error": None,
                        }
                    )
                    return self.connection

                except (
                    aio_pika.exceptions.AMQPConnectionError,
                    ConnectionRefusedError,
                    OSError,
                    asyncio.TimeoutError,
                ) as e:
                    last_error = e
                    retries_count += 1
                    delay = self.retry_backoff * (2 ** (retries_count - 1))
                    logger.error(
                        f"[{self.service_name}] RabbitMQ connection failed (attempt {retries_count}/{self.max_retries}): {e}. Retrying in {delay:.2f}s...",
                        exc_info=True,
                    )
                    self.health_status.update(
                        {
                            "is_healthy": False,
                            "connection_status": "connecting",
                            "error_count": self.health_status["error_count"] + 1,
                            "last_error": str(e),
                        }
                    )
                    if retries_count >= self.max_retries:
                        logger.critical(
                            f"[{self.service_name}] Max retries reached. Could not connect to RabbitMQ."
                        )
                        self.is_connecting = False
                        raise
                    await asyncio.sleep(delay)

            self.is_connecting = False
            raise aio_pika.exceptions.AMQPConnectionError(
                f"Failed to connect after multiple retries. Last error: {last_error}"
            )

    def _should_perform_health_check(self) -> bool:
        """Determine if a health check should be performed based on the interval."""
        if not self.last_health_check:
            return True
        return (
            datetime.now() - self.last_health_check
        ).total_seconds() >= self.health_check_interval

    async def _perform_health_check(self) -> bool:
        """Perform a health check on the RabbitMQ connection."""
        try:
            if not self.connection or self.connection.is_closed:
                self.health_status.update(
                    {
                        "is_healthy": False,
                        "connection_status": "disconnected",
                        "last_check": datetime.now(),
                        "last_error": "Connection is closed",
                    }
                )
                return False

            # Try to create a test channel
            async with self.connection.channel() as channel:
                await channel.declare_queue("health_check_queue", auto_delete=True)
                self.health_status.update(
                    {
                        "is_healthy": True,
                        "connection_status": "connected",
                        "last_check": datetime.now(),
                        "last_error": None,
                    }
                )
                return True

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            self.health_status.update(
                {
                    "is_healthy": False,
                    "connection_status": "unhealthy",
                    "last_check": datetime.now(),
                    "last_error": str(e),
                }
            )
            return False

    async def get_health_status(self) -> Dict[str, Any]:
        """Get the current health status of the RabbitMQ client."""
        if self._should_perform_health_check():
            await self._perform_health_check()
        return self.health_status

    def _on_connection_closed(self, sender: Any, exc: Optional[BaseException]):
        """Enhanced connection closed handler with better error tracking."""
        logger.warning(
            f"RabbitMQ connection closed. Sender: {sender}, Exception: {exc if exc else 'N/A'}"
        )
        self.connection = None
        self.health_status.update(
            {
                "is_healthy": False,
                "connection_status": "disconnected",
                "last_check": datetime.now(),
                "last_error": str(exc) if exc else "Connection closed",
            }
        )

        async def clear_consumers_on_close():
            async with self._consumer_management_lock:
                logger.warning(
                    f"Connection closed. Cancelling {len(self.active_consumers)} active consumer tasks."
                )
                for tag, (_, _, task) in list(self.active_consumers.items()):
                    if task and not task.done():
                        task.cancel()

        asyncio.create_task(clear_consumers_on_close())

    def _on_connection_reconnected(self, sender: Any):
        """Enhanced reconnection handler with health status update."""
        logger.info(
            f"RabbitMQ connection re-established by robust connector. Sender: {sender}."
        )
        self.health_status.update(
            {
                "is_healthy": True,
                "connection_status": "connected",
                "last_check": datetime.now(),
                "last_error": None,
            }
        )
        logger.warning(
            "Consumers managed by this client may need to be explicitly restarted by the application if they were not self-recovering from this event."
        )

    async def close(self):
        logger.info("Closing RabbitMQ client...")
        async with self._consumer_management_lock:
            consumer_tags_to_cancel = list(self.active_consumers.keys())
            logger.info(
                f"Found {len(consumer_tags_to_cancel)} active consumers to cancel during client close."
            )
            for consumer_tag in consumer_tags_to_cancel:
                _channel, queue_name, task = self.active_consumers.get(
                    consumer_tag, (None, None, None)
                )
                if task and not task.done():
                    logger.info(
                        f"Cancelling consumer task for queue '{queue_name}' (tag: {consumer_tag}) via client.close()."
                    )
                    task.cancel()
            tasks_to_wait = [
                self.active_consumers[tag][2]
                for tag in consumer_tags_to_cancel
                if tag in self.active_consumers and self.active_consumers[tag][2]
            ]
            if tasks_to_wait:
                logger.info(
                    f"Waiting for {len(tasks_to_wait)} consumer tasks to finish cancellation..."
                )
                results = await asyncio.gather(*tasks_to_wait, return_exceptions=True)
                for i, result in enumerate(results):
                    task_name = (
                        tasks_to_wait[i].get_name()
                        if hasattr(tasks_to_wait[i], "get_name")
                        else f"Task-{i}"
                    )
                    if isinstance(result, Exception) and not isinstance(
                        result, asyncio.CancelledError
                    ):
                        logger.error(
                            f"Consumer task '{task_name}' raised an error during cancellation: {result}",
                            exc_info=result,
                        )
                    elif isinstance(result, asyncio.CancelledError):
                        logger.info(
                            f"Consumer task '{task_name}' was successfully cancelled."
                        )
                logger.info(
                    "All consumer tasks processed for cancellation during client close."
                )
            self.active_consumers.clear()
        if self.connection and not self.connection.is_closed:
            logger.info("Closing main RabbitMQ connection.")
            try:
                await self.connection.close()
            except Exception as e:
                logger.error(f"Error closing RabbitMQ connection: {e}", exc_info=True)
            self.connection = None
            logger.info("RabbitMQ connection closed.")
        else:
            logger.info("RabbitMQ connection already closed or not established.")

    async def publish_message(
        self,
        message_body: Any,
        exchange_name: str,
        routing_key: str,
        content_type: str = "application/json",
        delivery_mode: aio_pika.DeliveryMode = aio_pika.DeliveryMode.PERSISTENT,
        correlation_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        app_id: Optional[str] = None,
        properties: Optional[dict] = None,
        headers: Optional[Dict[str, Any]] = None,
    ):
        """
        Enhanced message publishing with better error handling and service-specific integration.
        """
        retries_count = 0
        actual_headers = dict(headers or {})
        actual_headers.update(
            {
                "x-devfusion-timestamp": datetime.now().isoformat(),
                "x-devfusion-version": self.version,
                "x-devfusion-service": self.service_name,
            }
        )

        while retries_count < self.max_retries:
            try:
                conn = await self._get_connection()
                async with conn.channel() as channel:
                    exchange = await channel.declare_exchange(
                        name=exchange_name,
                        type=aio_pika.ExchangeType.TOPIC,
                        durable=True,
                    )

                    # Enhanced message body handling
                    if isinstance(message_body, (dict, list)):
                        body_bytes = json.dumps(message_body).encode("utf-8")
                    elif isinstance(message_body, str):
                        body_bytes = message_body.encode("utf-8")
                    elif isinstance(message_body, bytes):
                        body_bytes = message_body
                    else:
                        body_bytes = str(message_body).encode("utf-8")

                    # Enhanced message properties
                    message_properties = {
                        "content_type": content_type,
                        "delivery_mode": delivery_mode,
                        "correlation_id": correlation_id,
                        "reply_to": reply_to,
                        "app_id": app_id or "devfusion",
                        "headers": actual_headers,
                        "timestamp": int(datetime.now().timestamp() * 1000),
                    }
                    if properties:
                        message_properties.update(properties)

                    message = aio_pika.Message(body=body_bytes, **message_properties)

                    # Publish with confirmation
                    await exchange.publish(
                        message, routing_key=routing_key, mandatory=True, timeout=5
                    )

                    logger.debug(
                        f"Message published to E:'{exchange_name}' RK:'{routing_key}'. "
                        f"CID:{correlation_id}, Headers:{actual_headers}"
                    )
                    return

            except (
                aio_pika.exceptions.ConnectionClosed,
                aio_pika.exceptions.ChannelClosed,
                aio_pika.exceptions.ChannelInvalidStateError,
                aio_pika.exceptions.PublishError,
                aio_pika.exceptions.MessageNackedError,
                aio_pika.exceptions.IncompatibleProtocolError,
                asyncio.TimeoutError,
                OSError,
            ) as e:
                retries_count += 1
                logger.warning(
                    f"Error publishing to E:'{exchange_name}' (att {retries_count}/{self.max_retries}): "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )
                self.health_status["error_count"] += 1
                self.health_status["last_error"] = str(e)

                if retries_count >= self.max_retries:
                    logger.error(f"Max retries for publishing. Giving up.")
                    raise

                delay = self.retry_backoff * (2 ** (retries_count - 1))
                logger.info(f"Retrying publish in {delay:.2f}s...")
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Unexpected error publishing: {e}", exc_info=True)
                self.health_status["error_count"] += 1
                self.health_status["last_error"] = str(e)
                raise

        logger.error(
            f"Failed to publish to E:'{exchange_name}' after {self.max_retries} retries."
        )
        raise aio_pika.exceptions.AMQPError(
            f"Failed to publish after {self.max_retries} retries."
        )

    async def _setup_consumer_infrastructure(  # Simplified: No DLX/DLQ setup from client
        self,
        channel: AbstractRobustChannel,
        queue_name: str,
        exchange_name: Optional[str],
        binding_keys: Optional[List[str]],
        queue_durable: bool,
        queue_auto_delete: bool,
        queue_arguments: Optional[
            Dict[str, Any]
        ],  # User can pass DLX args here if needed
        exchange_type: aio_pika.ExchangeType,
        exchange_durable: bool,
    ) -> AbstractQueue:
        # Declare the main processing queue
        # If DLX is needed, user should pass 'x-dead-letter-exchange' etc. in queue_arguments
        queue = await channel.declare_queue(
            name=queue_name,
            durable=queue_durable,
            auto_delete=queue_auto_delete,
            arguments=queue_arguments,
        )
        logger.info(
            f"Declared queue '{queue_name}' (durable={queue_durable}, auto_delete={queue_auto_delete}, args={queue_arguments})"
        )

        if exchange_name:
            exchange = await channel.declare_exchange(
                name=exchange_name, type=exchange_type, durable=exchange_durable
            )
            logger.info(
                f"Declared exchange '{exchange_name}' (type={exchange_type}, durable={exchange_durable})"
            )
            effective_binding_keys = (
                binding_keys if binding_keys is not None else [queue_name]
            )
            if not effective_binding_keys and exchange_name:
                logger.warning(
                    f"Exchange '{exchange_name}' for Q:'{queue_name}' has no binding keys."
                )
            for binding_key in effective_binding_keys:
                await queue.bind(exchange, routing_key=binding_key)
                logger.info(
                    f"Bound Q:'{queue_name}' to E:'{exchange_name}' with RK '{binding_key}'"
                )
        return queue

    async def start_consuming(
        self,
        queue_name: str,
        on_message_callback: Callable[[AbstractIncomingMessage], Awaitable[None]],
        exchange_name: Optional[str] = None,
        binding_keys: Optional[List[str]] = None,
        queue_durable: bool = True,
        queue_auto_delete: bool = False,
        queue_arguments: Optional[Dict[str, Any]] = None,
        exchange_type: aio_pika.ExchangeType = aio_pika.ExchangeType.TOPIC,
        exchange_durable: bool = True,
    ):
        """
        Enhanced consumer setup with better error handling and DevFusion integration.
        """
        retries_count = 0
        consumer_task_object = asyncio.current_task()
        if consumer_task_object:
            consumer_task_object.set_name(f"DevFusion-Consumer-{queue_name}")

        while retries_count < self.max_retries:
            channel: Optional[AbstractRobustChannel] = None
            consumer_tag: Optional[str] = None
            try:
                conn = await self._get_connection()
                channel = await conn.channel()
                await channel.set_qos(prefetch_count=self.prefetch_count)

                # Enhanced queue setup with DevFusion-specific arguments
                queue_args = dict(queue_arguments or {})
                queue_args.update(
                    {
                        "x-queue-type": "classic",  # Explicit queue type
                        "x-max-priority": 10,  # Support for message priorities
                    }
                )

                queue_obj = await self._setup_consumer_infrastructure(
                    channel,
                    queue_name,
                    exchange_name,
                    binding_keys,
                    queue_durable,
                    queue_auto_delete,
                    queue_args,
                    exchange_type,
                    exchange_durable,
                )

                async def _internal_callback_wrapper(message: AbstractIncomingMessage):
                    start_time = datetime.now()
                    try:
                        # Add message processing metrics
                        message_headers = dict(message.headers or {})
                        message_headers.update(
                            {
                                "x-devfusion-received-at": start_time.isoformat(),
                                "x-devfusion-processing-start": start_time.isoformat(),
                            }
                        )

                        await on_message_callback(message)

                        # Update processing metrics
                        end_time = datetime.now()
                        processing_time = (end_time - start_time).total_seconds()
                        logger.debug(
                            f"Message processed successfully. Queue: {queue_name}, "
                            f"Processing time: {processing_time:.3f}s"
                        )

                    except Exception as e:
                        logger.error(
                            f"Error in on_message_callback for Q:'{queue_name}': {e}. "
                            f"Body:{message.body[:100]}",
                            exc_info=True,
                        )
                        try:
                            if not message.processed:
                                await message.nack(requeue=False)
                                logger.warning(
                                    f"Msg nacked (requeue=False) from Q:'{queue_name}' "
                                    f"due to processing error. DT:{message.delivery_tag}"
                                )
                        except Exception as nack_exc:
                            logger.error(
                                f"Error nacking message on Q:'{queue_name}': {nack_exc}",
                                exc_info=True,
                            )

                consumer_tag = await queue_obj.consume(
                    _internal_callback_wrapper, no_ack=False
                )
                async with self._consumer_management_lock:
                    if consumer_task_object:
                        self.active_consumers[consumer_tag] = (
                            channel,
                            queue_name,
                            consumer_task_object,
                        )

                logger.info(
                    f"Consuming from Q:'{queue_name}' (Tag:{consumer_tag}). "
                    f"Exchange: {exchange_name}, Bindings: {binding_keys}"
                )
                await asyncio.Event().wait()

            except asyncio.CancelledError:
                logger.info(
                    f"Consumer task for Q:'{queue_name}' (Tag:{consumer_tag}) was cancelled."
                )
                if channel and consumer_tag:
                    try:
                        if not channel.is_closed:
                            await channel.basic_cancel(consumer_tag)
                            logger.info(f"Basic_cancel for tag '{consumer_tag}'.")
                    except Exception as bc_exc:
                        logger.error(
                            f"Error basic_cancel for tag '{consumer_tag}': {bc_exc}",
                            exc_info=True,
                        )
                raise

            except (aio_pika.exceptions.AMQPError, OSError, asyncio.TimeoutError) as e:
                retries_count += 1
                logger.error(
                    f"Error setting up consumer for Q:'{queue_name}' "
                    f"(att {retries_count}/{self.max_retries}): {type(e).__name__}:{e}",
                    exc_info=True,
                )
                self.health_status["error_count"] += 1
                self.health_status["last_error"] = str(e)

                if channel and not channel.is_closed:
                    await channel.close()

                if retries_count >= self.max_retries:
                    logger.critical(
                        f"Max retries for consumer setup Q:'{queue_name}'. Giving up."
                    )
                    raise

                delay = self.retry_backoff * (2 ** (retries_count - 1))
                logger.info(
                    f"Retrying consumer setup for '{queue_name}' in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(
                    f"Unexpected error setting up consumer for Q:'{queue_name}': {e}",
                    exc_info=True,
                )
                self.health_status["error_count"] += 1
                self.health_status["last_error"] = str(e)
                if channel and not channel.is_closed:
                    await channel.close()
                raise

            finally:
                logger.debug(
                    f"Consumer setup loop for Q:'{queue_name}' (Tag:{consumer_tag}) "
                    f"iter finished/exited."
                )
                async with self._consumer_management_lock:
                    if consumer_tag and consumer_tag in self.active_consumers:
                        task_is_really_done = (
                            consumer_task_object and consumer_task_object.done()
                        )
                        exiting_due_to_max_retries = retries_count >= self.max_retries
                        if task_is_really_done or exiting_due_to_max_retries:
                            del self.active_consumers[consumer_tag]
                            logger.info(
                                f"Removed consumer tag '{consumer_tag}' for Q:'{queue_name}' "
                                f"from active list."
                            )

                if (
                    channel
                    and not channel.is_closed
                    and (
                        (consumer_task_object and consumer_task_object.done())
                        or retries_count >= self.max_retries
                    )
                ):
                    try:
                        await channel.close()
                    except Exception as e_close:
                        logger.error(
                            f"Error closing channel in consumer finally for Q:'{queue_name}': {e_close}"
                        )

        logger.critical(
            f"Failed to start consumer for Q:'{queue_name}' after {self.max_retries} retries."
        )
        raise aio_pika.exceptions.AMQPError(
            f"Failed to start consumer for '{queue_name}' after max retries."
        )

    # Removed start_dlq_retry_consumer method and its dependency on delayed message exchange.


# --- Example Usage (Simplified) ---
async def example_on_message(message: AbstractIncomingMessage):
    """Example callback for processing a received message."""
    try:
        msg_body_str = message.body.decode()
        logger.info(
            f"Example Main Consumer: Received body: {msg_body_str}. Headers: {message.headers}. DT: {message.delivery_tag}"
        )
        if "make_it_fail" in msg_body_str:  # Simulate a processing failure
            logger.warning(
                f"Main Consumer: Simulating processing failure for: {msg_body_str}"
            )
            raise ValueError("Simulated processing error")  # This will cause a NACK

        await asyncio.sleep(0.1)  # Simulate work
        await message.ack()  # Acknowledge successful processing
        logger.info(
            f"Example Main Consumer: Message processed and ACKED. DT: {message.delivery_tag}"
        )
    except Exception as e:
        logger.error(
            f"Main Consumer: Error processing message: {e}. DT: {message.delivery_tag}",
            exc_info=True,
        )
        if not message.processed:
            await message.nack(
                requeue=False
            )  # NACK and discard (or to DLX if server-configured)


async def main_example():
    rabbitmq_url_for_example = os.getenv(
        "RABBITMQ_URL_EXAMPLE", "amqp://guest:guest@localhost:5672/"
    )
    example_max_retries = int(os.getenv("RABBITMQ_MAX_RETRIES_EXAMPLE", "2"))
    example_retry_backoff = int(os.getenv("RABBITMQ_RETRY_BACKOFF_EXAMPLE", "1"))
    test_exchange_name = os.getenv(
        "RABBITMQ_TEST_EXCHANGE_EXAMPLE", "devfusion_simple_exchange"
    )
    test_queue_name = os.getenv("RABBITMQ_TEST_QUEUE_EXAMPLE", "devfusion_simple_queue")
    test_routing_key_base = os.getenv(
        "RABBITMQ_TEST_ROUTING_KEY_EXAMPLE", "simple.event"
    )

    client = RabbitMQClient(
        service_name="task_orchestrator_service",
        rabbitmq_url=rabbitmq_url_for_example,
        max_retries=example_max_retries,
        retry_backoff=example_retry_backoff,
        prefetch_count=2,
    )
    stop_event = asyncio.Event()
    consumer_tasks_list: List[asyncio.Task] = []

    async def run_main_consumer():
        try:
            # If you need DLX, configure it via queue_arguments:
            # queue_args_with_dlx = {
            #     "x-dead-letter-exchange": "my_app_dlx",
            #     "x-dead-letter-routing-key": f"dlx.{test_queue_name}.failed"
            # }
            # await client.start_consuming(..., queue_arguments=queue_args_with_dlx)
            # And ensure 'my_app_dlx' and a corresponding DLQ are declared on the server.
            await client.start_consuming(
                queue_name=test_queue_name,
                on_message_callback=example_on_message,
                exchange_name=test_exchange_name,
                binding_keys=[f"{test_routing_key_base}.#"],
            )
        except asyncio.CancelledError:
            logger.info(f"Main consumer task for Q:'{test_queue_name}' cancelled.")
        except Exception as e:
            logger.error(
                f"Main consumer for Q:'{test_queue_name}' failed: {e}", exc_info=True
            )
            stop_event.set()

    main_consumer_task = asyncio.create_task(
        run_main_consumer(), name=f"MainConsumer-{test_queue_name}"
    )
    consumer_tasks_list.append(main_consumer_task)
    await asyncio.sleep(3)  # Allow consumer to start

    try:
        rk_ok = f"{test_routing_key_base}.ok"
        logger.info(f"Publishing a normal message to RK: '{rk_ok}'")
        await client.publish_message(
            message_body={"data": "normal_processing", "id": "normal_msg_1"},
            exchange_name=test_exchange_name,
            routing_key=rk_ok,
        )
        await asyncio.sleep(0.5)
        rk_fail = f"{test_routing_key_base}.fail"
        logger.info(f"Publishing a message to fail processing (RK: '{rk_fail}')")
        await client.publish_message(
            message_body={"data": "make_it_fail", "id": "fail_msg_1"},
            exchange_name=test_exchange_name,
            routing_key=rk_fail,
        )
    except Exception as e:
        logger.error(f"Error during publishing test messages: {e}", exc_info=True)
        stop_event.set()

    logger.info("Example running. Check logs. Ctrl+C or wait for stop_event.")
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=20)
    except asyncio.TimeoutError:
        logger.info("Example timeout.")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt.")
    finally:
        logger.info("Shutting down example...")
        if not stop_event.is_set():
            stop_event.set()
        for task in consumer_tasks_list:
            if task and not task.done():
                task.cancel()
        if consumer_tasks_list:
            await asyncio.gather(*consumer_tasks_list, return_exceptions=True)
        await client.close()
        logger.info("Example finished.")


if __name__ == "__main__":
    import logging

    log_level_name_main = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level_name_main, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)-25s [%(threadName)s] %(filename)-30s:%(lineno)-4d %(message)s",
    )
    if hasattr(logger, "name"):
        logger.name = "RMQClientMainExSimplified"
    else:
        logger = logging.getLogger("RMQClientMainExSimplified")
    logger.info(
        f"Simplified standalone execution log level set to: {log_level_name_main}"
    )
    try:
        asyncio.run(main_example())
    except KeyboardInterrupt:
        logger.info("Main example interrupted by user.")
    except Exception as e:
        logger.critical(f"Main example crashed: {e}", exc_info=True)
