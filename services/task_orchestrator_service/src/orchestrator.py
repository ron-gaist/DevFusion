import asyncio
import json
from datetime import datetime, UTC
from typing import Any, Dict, Optional, List
from uuid import uuid4

from shared.common_utils import RabbitMQClient
from shared.common_utils.logger import logger
from shared.message_schemas.task_schemas import (
    TaskStatusUpdateMessage,
    Task,
    TaskStatus,
    TaskPriority,
    QuestionForUserMessage,
    UserResponseMessage,
    TaskEventMessage,
    TaskMetricsMessage
)
from shared.db_models.db_interface import DatabaseInterface
from shared.common_utils.context_manager import ContextManager
from shared.common_utils.saga_manager import SagaManager
from services.config_manager_service.src.config_loader import get_config
from ..config.env_settings import OrchestratorSettings

from ..config.env_settings import settings


class TaskOrchestratorService:
    """Service for orchestrating task execution and management."""

    def __init__(self):
        """Initialize the service."""
        self.service_name = "task_orchestrator_service"
        self.version = "1.0.0"
        self.config = None
        self.db = None
        self.rabbitmq_client = None
        self.saga_manager = None
        self._running = False
        self._task_queue = asyncio.Queue()
        self._max_concurrent_tasks = 5  # Default value, will be updated in initialize()
        self._task_timeout = 300  # 5 minutes default
        self._active_tasks = set()
        self._task_handlers = {}
        self.context = ContextManager()
        self._task_lock = asyncio.Lock()
        self._task_timeouts: Dict[str, asyncio.Task] = {}
        self._priority_queues: Dict[TaskPriority, List[str]] = {
            TaskPriority.LOW: [],
            TaskPriority.MEDIUM: [],
            TaskPriority.HIGH: [],
            TaskPriority.CRITICAL: [],
        }

        # Metrics
        self._task_metrics: Dict[str, Dict[str, Any]] = {}
        self._metrics_lock = asyncio.Lock()

        logger.info(f"{self.service_name} v{self.version} initialized")

    async def initialize(self):
        """Initialize the service asynchronously."""
        try:
            self.config = await get_config(self.service_name)
            if not self.config:
                raise ValueError("Failed to load configuration")
            
            # Extract task configuration with defaults
            task_config = self.config.get("task", {})
            self._max_concurrent_tasks = task_config.get("max_concurrent_tasks", 5)
            self._task_timeout = task_config.get("timeout", 300)
            
            # Validate required configuration sections
            if "database" not in self.config:
                raise ValueError("Database configuration is required")
            if "rabbitmq" not in self.config:
                raise ValueError("RabbitMQ configuration is required")
                
            logger.info(f"Service initialized with max_concurrent_tasks={self._max_concurrent_tasks}, task_timeout={self._task_timeout}")
        except Exception as e:
            logger.error(f"Failed to initialize service: {str(e)}")
            raise

    async def start(self, config: Dict[str, Any]) -> None:
        """Start the orchestrator service."""
        self.config = config
        self.logger.info("Starting orchestrator service...")
        
        # Initialize database connection
        try:
            self.db = DatabaseInterface(connection_params=self.config["database"])
            await self.db.connect()
            self.logger.info("Database connection established")
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {str(e)}")
            raise
        
        # Initialize RabbitMQ client
        try:
            self.rabbitmq_client = RabbitMQClient(
                host=self.config["rabbitmq"]["host"],
                port=self.config["rabbitmq"]["port"],
                username=self.config["rabbitmq"]["username"],
                password=self.config["rabbitmq"]["password"],
                virtual_host=self.config["rabbitmq"]["virtual_host"]
            )
            await self.rabbitmq_client.connect()
            self.logger.info("RabbitMQ connection established")
        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
            raise
        
        # Start task processing
        self.task_processor = TaskProcessor(self.db, self.rabbitmq_client)
        await self.task_processor.start()
        self.logger.info("Task processor started")
        
        self.logger.info("Orchestrator service started successfully")

    async def stop(self):
        """Stop the service."""
        self._running = False
        
        # Close database connection
        if self.db:
            await self.db.close()
            self.db = None
            
        # Close RabbitMQ connection
        if self.rabbitmq_client:
            await self.rabbitmq_client.close()
            self.rabbitmq_client = None
            
        logger.info("Task orchestrator service stopped")

    async def _handle_new_task(self, message):
        """Handle incoming new task messages."""
        async with message.process():
            try:
                # Parse task data
                task_data = json.loads(message.body.decode())
                task = Task(**task_data)

                # Check if we can accept more tasks
                if len(self._active_tasks) >= self._max_concurrent_tasks:
                    logger.warning(
                        "Maximum concurrent tasks reached, rejecting new task"
                    )
                    await message.nack(requeue=True)
                    return

                async with self._task_lock:
                    # Store task in database
                    task = await self.db.create_task(task)
                    self._active_tasks.add(task.task_id)
                    self._task_timeouts[task.task_id] = asyncio.create_task(
                        self._handle_task_timeout(task.task_id)
                    )

                    # Add to priority queue
                    priority = task.metadata.priority
                    self._priority_queues[priority].append(task.task_id)

                    # Initialize metrics
                    self._task_metrics[task.task_id] = {
                        "start_time": datetime.now(UTC),
                        "processing_time": 0,
                        "steps_completed": 0,
                        "errors": 0,
                    }

                # Establish context
                await self.context.establish_context(
                    task.task_id, {"task": task.model_dump(), "priority": priority}
                )

                # Create and execute saga
                saga_steps = [
                    SagaStep("plan_task", self._plan_task, self._compensate_planning),
                    SagaStep(
                        "execute_task", self._execute_task, self._compensate_execution
                    ),
                ]

                await self.saga_manager.create_saga(
                    task.task_id, saga_steps, {"task": task.model_dump()}
                )

                # Start saga execution
                asyncio.create_task(self.saga_manager.execute_saga(task.task_id))

                # Publish status update
                status_update = TaskStatusUpdateMessage(
                    task_id=task.task_id,
                    status=TaskStatus.PLANNING,
                    details={"message": "Task received and planning initiated"},
                )
                await self.rabbitmq_client.publish_message(
                    message_body=status_update.model_dump(),
                    exchange_name=settings.RABBITMQ_EXCHANGE,
                    routing_key="task.status",
                )

                # Publish event
                event = TaskEventMessage(
                    task_id=task.task_id,
                    event_type="TASK_RECEIVED",
                    details={"priority": priority},
                )
                await self.rabbitmq_client.publish_message(
                    message_body=event.model_dump(),
                    exchange_name=settings.RABBITMQ_EXCHANGE,
                    routing_key="task.events",
                )

                logger.info(f"New task received and processed: {task.task_id}")

            except json.JSONDecodeError:
                logger.error("Failed to decode message body")
                await message.nack(requeue=False)
            except Exception as e:
                logger.error(f"Error processing task: {str(e)}")
                await message.nack(requeue=True)

    async def _handle_user_response(self, message):
        """Handle user responses to questions."""
        async with message.process():
            try:
                response_data = json.loads(message.body.decode())
                response = UserResponseMessage(**response_data)
                task_id = response.task_id

                if task_id not in self._active_tasks:
                    logger.warning(f"Received response for unknown task: {task_id}")
                    await message.nack(requeue=False)
                    return

                task = self._task_handlers[task_id](response)
                if task.status != TaskStatus.AWAITING_USER_INPUT:
                    logger.warning(
                        f"Received response for task not awaiting input: {task_id}"
                    )
                    await message.nack(requeue=False)
                    return

                # Update task status
                await self._update_task_status(
                    task_id,
                    TaskStatus.PLANNING,
                    {"message": "Resuming task after user input"},
                )

                # Forward response to capabilities engine
                await self.rabbitmq_client.publish_message(
                    message_body=response.model_dump(),
                    exchange_name="devfusion.capabilities",
                    routing_key="task.user_response",
                )

                # Publish event
                event = TaskEventMessage(
                    task_id=task_id,
                    event_type="USER_RESPONSE_RECEIVED",
                    details={"response_type": type(response.response).__name__},
                )
                await self.rabbitmq_client.publish_message(
                    message_body=event.model_dump(),
                    exchange_name=settings.RABBITMQ_EXCHANGE,
                    routing_key="task.events",
                )

            except json.JSONDecodeError:
                logger.error("Failed to decode user response message")
                await message.nack(requeue=False)
            except Exception as e:
                logger.error(f"Error processing user response: {str(e)}")
                await message.nack(requeue=True)

    async def _plan_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Plan a task."""
        task = Task.model_validate(data["task"])
        priority = task.metadata.priority

        try:
            # Create planning event
            event = TaskEventMessage(
                task_id=task.task_id,
                event_type="TASK_PLANNING",
                details={"priority": priority},
            )
            await self.rabbitmq_client.publish_message(
                message_body=event.model_dump(),
                exchange_name=settings.RABBITMQ_EXCHANGE,
                routing_key="task.events",
            )

            # Create saga for planning
            saga_steps = [
                SagaStep(
                    name="plan",
                    action=self._plan_task,
                    compensation=self._compensate_planning
                )
            ]
            await self.saga_manager.create_saga(
                task.task_id, saga_steps, {"task": task.model_dump()}
            )

            # Update context with planning status
            await self.context.update_context(
                task.task_id,
                {"status": "planning", "priority": priority}
            )

            return {"status": "success", "task_id": task.task_id}

        except Exception as e:
            # Update context with error
            await self.context.update_context(
                task.task_id,
                {"error": str(e), "status": "failed"}
            )
            raise

    async def _compensate_planning(self, data: Dict[str, Any]):
        """Compensate planning step."""
        task = Task.model_validate(data["task"])
        await self._update_task_status(
            task.task_id, TaskStatus.FAILED, {"error": "Planning failed"}
        )

        # Update context
        await self.context.update_context(
            task.task_id,
            {"error": "Planning failed", "status": "failed"}
        )

        # Publish event
        event = TaskEventMessage(
            task_id=task.task_id,
            event_type="PLANNING_FAILED",
            details={"error": "Planning failed"},
        )
        await self.rabbitmq_client.publish_message(
            message_body=event.model_dump(),
            exchange_name=settings.RABBITMQ_EXCHANGE,
            routing_key="task.events",
        )

    async def _execute_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task."""
        task = Task.model_validate(data["task"])
        priority = task.metadata.priority

        try:
            # Create execution event
            event = TaskEventMessage(
                task_id=task.task_id,
                event_type="TASK_EXECUTING",
                details={"priority": priority},
            )
            await self.rabbitmq_client.publish_message(
                message_body=event.model_dump(),
                exchange_name=settings.RABBITMQ_EXCHANGE,
                routing_key="task.events",
            )

            # Create saga for execution
            saga_steps = [
                SagaStep(
                    name="execute",
                    action=self._execute_task,
                    compensation=self._compensate_execution
                )
            ]
            await self.saga_manager.create_saga(
                task.task_id, saga_steps, {"task": task.model_dump()}
            )

            # Update context with executing status
            await self.context.update_context(
                task.task_id,
                {"status": "executing", "priority": priority}
            )

            return {"status": "success", "task_id": task.task_id}

        except Exception as e:
            # Update context with error
            await self.context.update_context(
                task.task_id,
                {"error": str(e), "status": "failed"}
            )
            raise

    async def _compensate_execution(self, data: Dict[str, Any]):
        """Compensate execution step."""
        task = Task.model_validate(data["task"])
        await self._update_task_status(
            task.task_id, TaskStatus.FAILED, {"error": "Execution failed"}
        )

        # Update context
        await self.context.update_context(
            task.task_id,
            {"error": "Execution failed", "status": "failed"}
        )

        # Publish event
        event = TaskEventMessage(
            task_id=task.task_id,
            event_type="EXECUTION_FAILED",
            details={"error": "Execution failed"},
        )
        await self.rabbitmq_client.publish_message(
            message_body=event.model_dump(),
            exchange_name=settings.RABBITMQ_EXCHANGE,
            routing_key="task.events",
        )

    def _is_task_timed_out(self, task: dict) -> bool:
        """Check if a task has timed out."""
        if not task.get("created_at"):
            return False
        timeout = self.config.get("task", {}).get("timeout", settings.TASK_TIMEOUT)
        return (datetime.now(UTC) - task["created_at"]).total_seconds() > timeout

    async def _handle_task_timeout(self, task_id: str) -> None:
        """Handle task timeout."""
        if task_id not in self._active_tasks:
            return
            
        task = self._task_handlers[task_id](None)
        if not self._is_task_timed_out(task):
            return
            
        # Calculate time elapsed since task creation
        time_elapsed = datetime.now(UTC) - task["created_at"]
        
        # Update task status to failed
        task["status"] = TaskStatus.FAILED
        task["result"] = {
            "error": f"Task timed out after {time_elapsed.total_seconds()} seconds"
        }
        
        # Update task in database
        await self.db.update_task(task)
        
        # Update context
        await self.context.update_context(
            task_id,
            {
                "status": "failed",
                "error": f"Task timed out after {time_elapsed.total_seconds()} seconds"
            }
        )
        
        # Remove from active tasks
        self._active_tasks.remove(task_id)

    async def _update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update task status."""
        if task_id not in self._active_tasks:
            raise ValueError(f"Task {task_id} not found")
            
        task = self._task_handlers[task_id](None)
        task["status"] = status
        if result:
            task["result"] = result
            
        # Update task in database
        await self.db.update_task(task)
        
        # Update task metadata
        task["metadata"]["updated_at"] = datetime.now(UTC)

        # Publish status update
        status_update = TaskStatusUpdateMessage(
            task_id=task_id,
            status=status,
            details=result or {},
        )
        await self.rabbitmq_client.publish_message(
            message_body=status_update.model_dump(),
            exchange_name=settings.RABBITMQ_EXCHANGE,
            routing_key="task.status",
        )

        # Update metrics
        async with self._metrics_lock:
            if task_id in self._task_metrics:
                metrics = self._task_metrics[task_id]
                if status == TaskStatus.COMPLETED:
                    metrics["processing_time"] = (
                        datetime.now(UTC) - metrics["start_time"]
                    ).total_seconds()
                    metrics["end_time"] = datetime.now(UTC)
                elif status == TaskStatus.FAILED:
                    metrics["errors"] += 1

                # Publish metrics
                metrics_msg = TaskMetricsMessage(
                    task_id=task_id,
                    metrics=metrics,
                )
                await self.rabbitmq_client.publish_message(
                    message_body=metrics_msg.model_dump(),
                    exchange_name=settings.RABBITMQ_EXCHANGE,
                    routing_key="task.metrics",
                )

        # Clean up if task is completed or failed
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            if task_id in self._task_timeouts:
                self._task_timeouts[task_id].cancel()
                del self._task_timeouts[task_id]
            del self._task_handlers[task_id]
            if task_id in self._task_metrics:
                del self._task_metrics[task_id]

            # Remove from priority queue
            for queue in self._priority_queues.values():
                if task_id in queue:
                    queue.remove(task_id)

    async def _process_tasks(self):
        """Process tasks in the queue."""
        while self._running:
            try:
                task = await self._task_queue.get()
                await self._handle_new_task(task)
            except Exception as e:
                logger.error(f"Error processing task: {str(e)}")
            finally:
                await asyncio.sleep(0.1)


async def main():
    """Main entry point for the service."""
    service = TaskOrchestratorService()
    try:
        await service.initialize()
        await service.start()
        # Keep the service running
        while service._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down service...")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main()) 