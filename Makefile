# =============================================================================
# movie-finder-chain — Docker-only developer contract
#
# Canonical targets:
#   make init           Initialize a local .env from template
#   make up             Start the dev container (alias for dev)
#   make down           Stop the dev container
#   make editor-up      Start a headless dev container for IDE attachment
#   make editor-down    Stop the IDE-attached dev container
#   make shell          Open a shell in the running container
#   make lint           Run ruff check
#   make format         Run ruff format
#   make typecheck      Run mypy --strict
#   make test           Run pytest
#   make test-coverage  Run pytest with coverage output
#   make pre-commit     Run pre-commit hooks
#   make ci-down        Hard cleanup for CI agents (volumes + local images)
# =============================================================================

.PHONY: help init up dev down editor-up editor-down shell lint format typecheck \
	test test-coverage pre-commit ci-down check

.DEFAULT_GOAL := help

COMPOSE ?= docker compose
SERVICE ?= chain
CHAIN_PATHS := src tests examples chat.py
COVERAGE_XML ?= chain-coverage.xml
COVERAGE_HTML ?= htmlcov/chain

help:
	@echo ""
	@echo "Movie Finder Chain — available targets"
	@echo "======================================"
	@echo ""
	@echo "  Lifecycle"
	@echo "    init             Initialize a local .env from .env.example"
	@echo "    up               Start the persistent dev container (alias for dev)"
	@echo "    dev              Start the persistent dev container (Ctrl+C to stop)"
	@echo "    down             Stop the dev container"
	@echo "    editor-up        Start a headless container for IDE attachment"
	@echo "    editor-down      Stop the IDE-attached container"
	@echo "    shell            Open a shell in the running container"
	@echo ""
	@echo "  Quality"
	@echo "    lint             Run ruff check inside Docker"
	@echo "    format           Run ruff format inside Docker"
	@echo "    typecheck        Run mypy --strict inside Docker"
	@echo "    test             Run pytest inside Docker"
	@echo "    test-coverage    Run pytest with coverage XML/HTML output"
	@echo "    pre-commit       Run pre-commit hooks inside Docker"
	@echo "    check            Convenience alias: lint + typecheck + test"
	@echo ""
	@echo "  CI"
	@echo "    ci-down          Hard cleanup for CI (down -v --rmi local)"
	@echo ""
	@echo "  Examples"
	@echo "    example-basic    Run examples/basic_usage.py inside Docker"
	@echo "    example-streaming Run examples/streaming_example.py inside Docker"
	@echo ""

init:
	@if [ ! -f .env ]; then cp .env.example .env && echo ".env initialized"; else echo ".env already exists"; fi

up: dev

dev:
	$(COMPOSE) up --build $(SERVICE)

down:
	$(COMPOSE) down

editor-up:
	$(COMPOSE) up -d --build $(SERVICE)

editor-down: down

shell:
	@if $(COMPOSE) ps --services --status running | grep -qx "$(SERVICE)"; then \
		$(COMPOSE) exec $(SERVICE) sh; \
	else \
		$(COMPOSE) run --rm $(SERVICE) sh; \
	fi

lint:
	$(COMPOSE) run --rm --no-deps $(SERVICE) ruff check $(CHAIN_PATHS)

format:
	$(COMPOSE) run --rm --no-deps $(SERVICE) ruff format $(CHAIN_PATHS)

typecheck:
	$(COMPOSE) run --rm --no-deps $(SERVICE) mypy src

test:
	$(COMPOSE) run --rm --no-deps $(SERVICE) pytest tests/ --asyncio-mode=auto -v --tb=short

test-coverage:
	$(COMPOSE) run --rm --no-deps $(SERVICE) pytest tests/ --asyncio-mode=auto -v --tb=short \
		--cov=chain \
		--cov-report=term-missing \
		--cov-report=xml:$(COVERAGE_XML) \
		--cov-report=html:$(COVERAGE_HTML)

pre-commit:
	$(COMPOSE) run --rm --no-deps $(SERVICE) pre-commit run --all-files

ci-down:
	$(COMPOSE) down -v --rmi local

check: lint typecheck test

example-basic:
	$(COMPOSE) run --rm --no-deps $(SERVICE) python examples/basic_usage.py

example-streaming:
	$(COMPOSE) run --rm --no-deps $(SERVICE) python examples/streaming_example.py
