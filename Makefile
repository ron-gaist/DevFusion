.PHONY: test test-cov test-unit test-integration

test:
	pytest -v

test-cov:
	pytest --cov=services --cov-report=term-missing

test-unit:
	pytest -v -m unit

test-integration:
	pytest -v -m integration

test-orchestrator:
	pytest -v tests/component/task_orchestrator_service/

test-config-manager:
	pytest -v tests/component/config_manager_service/ 