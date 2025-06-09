import asyncio
import json
from dataclasses import asdict
from datetime import datetime, UTC
from typing import Any, Dict, Optional, List


from shared.common_utils import RabbitMQClient, logger
from shared.message_schemas.task_schemas import (
    TaskStatusUpdateMessage,
    TaskCompletedMessage,
    TaskFailedMessage,
    QuestionForUserMessage,
    UserResponseMessage,
)
from shared.db_models.task_models import TaskRecord
from shared.db_models.db_interface import DatabaseInterface
from shared.common_utils.context_manager import ContextManager
from shared.common_utils.saga_manager import SagaManager, SagaStep
from env_settings import (
    SERVICE_NAME,
    SERVICE_VERSION,
    RABBITMQ_URL,
    RABBITMQ_EXCHANGE,
    RABBITMQ_QUEUE,
    RABBITMQ_BINDING_KEYS,
    TaskStatus,
    TaskPriority,
    MAX_CONCURRENT_TASKS,
    TASK_TIMEOUT,
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
)


class TaskOrchestratorService:
    """Service for orchestrating task execution and management."""

    def __init__(self):
        """Initialize the service."""
        self.service_name = SERVICE_NAME
        self.version = SERVICE_VERSION

        # Initialize components
        self.rabbitmq_client = RabbitMQClient(
            service_name=self.service_name,
            rabbitmq_url=RABBITMQ_URL,
            version=self.version,
        )
        self.db = DatabaseInterface(
            {
                "host": DB_HOST,
                "port": DB_PORT,
                "database": DB_NAME,
                "user": DB_USER,
                "password": DB_PASSWORD,
            }
        )
        self.context_manager = ContextManager()
        self.saga_manager = SagaManager()

        # Task management
        self.active_tasks: Dict[str, TaskRecord] = {}
        self._task_lock = asyncio.Lock()
        self._task_timeouts: Dict[str, asyncio.Task] = {}
        self._priority_queues: Dict[int, List[str]] = {
            TaskPriority.LOW: [],
            TaskPriority.MEDIUM: [],
            TaskPriority.HIGH: [],
            TaskPriority.CRITICAL: [],
        }

        logger.info(f"{self.service_name} v{self.version} initialized")

    async def start(self):
        """Start the service and establish connections."""
        try:
            # Connect to database
            await self.db.connect()

            # Load active tasks from database
            active_tasks = await self.db.get_active_tasks()
            for task in active_tasks:
                self.active_tasks[task.task_id] = task
                # Restore timeouts for active tasks
                if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    self._task_timeouts[task.task_id] = asyncio.create_task(
                        self._handle_task_timeout(task.task_id)
                    )

            # Start consuming messages
            await self.rabbitmq_client.start_consuming(
                queue_name=RABBITMQ_QUEUE,
                on_message_callback=self._handle_new_task,
                exchange_name=RABBITMQ_EXCHANGE,
                binding_keys=RABBITMQ_BINDING_KEYS,
            )

            logger.info(f"{self.service_name} v{self.version} started successfully")

        except Exception as e:
            logger.error(f"Failed to start service: {str(e)}")
            raise

    async def stop(self):
        """Stop the service and close connections."""
        try:
            # Cancel all task timeouts
            for timeout_task in self._task_timeouts.values():
                timeout_task.cancel()

            # Close connections
            await self.rabbitmq_client.close()
            await self.db.close()

            logger.info(f"{self.service_name} stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping service: {str(e)}")
            raise

    async def _handle_new_task(self, message):
        """Handle incoming new task messages."""
        async with message.process():
            try:
                # Parse task data
                task_data = json.loads(message.body.decode())
                task = TaskRecord(**task_data)

                # Check if we can accept more tasks
                if len(self.active_tasks) >= MAX_CONCURRENT_TASKS:
                    logger.warning(
                        "Maximum concurrent tasks reached, rejecting new task"
                    )
                    await message.nack(requeue=True)
                    return

                async with self._task_lock:
                    # Store task in database
                    task = await self.db.create_task(task)
                    self.active_tasks[task.task_id] = task

                    # Set up task timeout
                    self._task_timeouts[task.task_id] = asyncio.create_task(
                        self._handle_task_timeout(task.task_id)
                    )

                    # Add to priority queue
                    priority = task.metadata.get("priority", TaskPriority.MEDIUM)
                    self._priority_queues[priority].append(task.task_id)

                # Establish context
                await self.context_manager.establish_context(
                    task.task_id, {"task": task.dict(), "priority": priority}
                )

                # Create and execute saga
                saga_steps = [
                    SagaStep("plan_task", self._plan_task, self._compensate_planning),
                    SagaStep(
                        "execute_task", self._execute_task, self._compensate_execution
                    ),
                ]

                await self.saga_manager.create_saga(
                    task.task_id, saga_steps, {"task": task.dict()}
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
                    message_body=asdict(status_update),
                    exchange_name=RABBITMQ_EXCHANGE,
                    routing_key="task.status",
                )

                logger.info(f"New task received and processed: {task.task_id}")

            except json.JSONDecodeError:
                logger.error("Failed to decode message body")
                await message.nack(requeue=False)
            except Exception as e:
                logger.error(f"Error processing task: {str(e)}")
                await message.nack(requeue=True)

    async def _handle_user_response(self, message):
        """Handle a user response message from the UI."""
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                response = UserResponseMessage(**data)

                # Forward response to capabilities engine
                await self.rabbitmq_client.publish_message(
                    message_body=asdict(response),
                    exchange_name="devfusion.capabilities",
                    routing_key="task.user_response",
                )

                # Update context and mark task as executing again
                await self.context_manager.update_context(
                    response.task_id,
                    {"user_response": response.response_content},
                )
                await self._update_task_status(
                    response.task_id, TaskStatus.EXECUTING
                )

                logger.info(
                    f"User response processed for task {response.task_id}"
                )
            except json.JSONDecodeError:
                logger.error("Failed to decode user response message")
                await message.nack(requeue=False)
            except Exception as e:
                logger.error(f"Error handling user response: {str(e)}")
                await message.nack(requeue=True)
    async def _plan_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Plan a task."""
        task = TaskRecord(**data["task"])

        # Forward to capabilities engine for planning
        await self.rabbitmq_client.publish_message(
            message_body=task.dict(),
            exchange_name="devfusion.capabilities",
            routing_key="task.plan",
        )

        # Update context
        await self.context_manager.update_context(
            task.task_id, {"planning_started": datetime.now(UTC)}
        )

        return {"status": "planning_started"}

    async def _compensate_planning(self, data: Dict[str, Any]):
        """Compensate planning step."""
        task = TaskRecord(**data["task"])
        await self._update_task_status(
            task.task_id, TaskStatus.FAILED, {"error": "Planning failed"}
        )

    async def _execute_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task."""
        task = TaskRecord(**data["task"])

        # Forward to capabilities engine for execution
        await self.rabbitmq_client.publish_message(
            message_body=task.dict(),
            exchange_name="devfusion.capabilities",
            routing_key="task.execute",
        )

        # Update context
        await self.context_manager.update_context(
            task.task_id, {"execution_started": datetime.now(UTC)}
        )

        return {"status": "execution_started"}

    async def _compensate_execution(self, data: Dict[str, Any]):
        """Compensate execution step."""
        task = TaskRecord(**data["task"])
        await self._update_task_status(
            task.task_id, TaskStatus.FAILED, {"error": "Execution failed"}
        )

    async def _handle_task_timeout(self, task_id: str):
        """Handle task timeout."""
        try:
            await asyncio.sleep(TASK_TIMEOUT)
            async with self._task_lock:
                if task_id in self.active_tasks:
                    task = self.active_tasks[task_id]
                    if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        await self._update_task_status(
                            task_id,
                            TaskStatus.FAILED,
                            {"error": "Task timeout exceeded"},
                        )
                        logger.warning(
                            f"Task {task_id} timed out after {TASK_TIMEOUT} seconds"
                        )
        except asyncio.CancelledError:
            pass
        finally:
            self._task_timeouts.pop(task_id, None)

    async def _update_task_status(
        self, task_id: str, status: str, details: Optional[Dict[str, Any]] = None
    ):
        """Update task status and publish update."""
        async with self._task_lock:
            if task_id not in self.active_tasks:
                logger.warning(f"Task not found: {task_id}")
                return

            task = self.active_tasks[task_id]
            task.status = status
            task.updated_at = datetime.now(UTC)
            if details:
                task.details = details

            # Update in database
            await self.db.update_task(task)

            # Update context
            await self.context_manager.update_context(
                task_id, {"status": status, "details": details}
            )

            # Cancel timeout if task is completed or failed
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                if task_id in self._task_timeouts:
                    self._task_timeouts[task_id].cancel()
                    self._task_timeouts.pop(task_id)

                # Clear context
                await self.context_manager.clear_context(task_id)

            status_update = TaskStatusUpdateMessage(
                task_id=task_id, status=status, details=details
            )

            await self.rabbitmq_client.publish_message(
                message_body=asdict(status_update),
                exchange_name=RABBITMQ_EXCHANGE,
                routing_key="task.status",
            )

            if status == TaskStatus.AWAITING_USER_INPUT:
                if details and "question" in details:
                    question_msg = QuestionForUserMessage(
                        task_id=task_id,
                        question=details["question"],
                        user_id=task.user_id,
                    )
                    await self.rabbitmq_client.publish_message(
                        message_body=asdict(question_msg),
                        exchange_name=RABBITMQ_EXCHANGE,
                        routing_key="task.question_for_user",
                    )
            elif status == TaskStatus.COMPLETED:
                completed_msg = TaskCompletedMessage(
                    task_id=task_id, details=details
                )
                await self.rabbitmq_client.publish_message(
                    message_body=asdict(completed_msg),
                    exchange_name=RABBITMQ_EXCHANGE,
                    routing_key="task.completed",
                )
            elif status == TaskStatus.FAILED:
                failed_msg = TaskFailedMessage(
                    task_id=task_id, details=details
                )
                await self.rabbitmq_client.publish_message(
                    message_body=asdict(failed_msg),
                    exchange_name=RABBITMQ_EXCHANGE,
                    routing_key="task.failed",
                )

            logger.info(f"Task {task_id} status updated to {status}")


async def main():
    """Main entry point for the service."""
    service = TaskOrchestratorService()
    try:
        await service.start()
        # Keep the service running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down service...")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
