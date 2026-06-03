.PHONY: help dev-up dev-down prod-up prod-down test lint format migrate-generate migrate-run backfill seed

# Default action
help:
	@echo "Available commands:"
	@echo "  make dev-up            Start development containers"
	@echo "  make dev-down          Stop development containers and clean volumes"
	@echo "  make prod-up           Start production containers (with Nginx reverse proxy)"
	@echo "  make prod-down         Stop production containers"
	@echo "  make lint              Lint Python code with Ruff"
	@echo "  make format            Format Python code with Ruff"
	@echo "  make test              Run unit and integration tests across services"
	@echo "  make migrate-generate  Generate DB migration using Alembic"
	@echo "  make migrate-run       Run database migrations"
	@echo "  make backfill          Run historical backfilling script"
	@echo "  make seed              Run database seed with tickers and dummy data"

dev-up:
	docker-compose -f docker-compose.yml up --build

dev-down:
	docker-compose -f docker-compose.yml down -v

prod-up:
	docker-compose -f docker-compose.prod.yml up --build -d

prod-down:
	docker-compose -f docker-compose.prod.yml down -v

lint:
	python -m ruff check .

format:
	python -m ruff format .

test:
	python -m pytest services/shared/tests/ services/ingestion/tests/ services/training/tests/ services/inference/tests/ --disable-warnings

migrate-generate:
	docker-compose exec inference alembic revision --autogenerate -m "Auto migration"

migrate-run:
	docker-compose exec inference alembic upgrade head

backfill:
	docker-compose exec ingestion python scripts/backfill.py --symbol BTC/USDT --days 30

seed:
	docker-compose exec ingestion python scripts/seed_db.py
