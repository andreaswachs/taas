.PHONY: help setup dev workers test lint format clean init

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies
	uv sync

init: ## Create data directories and copy .env.example
	mkdir -p /var/lib/taas-db /var/lib/taas-audio /var/lib/taas-models
	@test -f .env || cp .env.example .env
	@echo "Initialized. Edit .env to configure the service."

dev: ## Run service in dev mode (fresh build)
	docker compose up --build

workers: ## Start background workers
	PYTHONPATH=src python -m scripts.workers

test: ## Run tests
	pytest

lint: ## Lint code
	uv run ruff check src/

format: ## Format code
	uv run ruff format src/

clean: ## Remove temp files
	rm -rf __pycache__ .pytest_cache
	rm -rf src/__pycache__ src/**/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
