# =============================================================================
# movie-finder-chain — Docker-only developer contract
#
# Usage:
#   make help
#   make <target>
#
# All developer commands execute through Docker Compose so linting, testing,
# formatting, and pre-commit do not depend on a host-managed Python environment.
#
# Typical first-time flow:
#   make init        # build image + create .env + install git hook
#   make editor-up   # start container for VS Code attach
#   make check       # lint + typecheck + tests with coverage
#
# When the editor container is already running, quality commands use
# 'docker compose exec' instead of a new container — faster for interactive dev.
# =============================================================================

.PHONY: help init up dev down editor-up editor-down logs shell lint format fix typecheck \
	test test-coverage pre-commit ci-down check example-basic example-streaming

.DEFAULT_GOAL := help

COMPOSE ?= docker compose
SERVICE ?= chain
GIT_DIR_HOST := $(shell git rev-parse --git-dir)
GIT_HOOKS_DIR := $(GIT_DIR_HOST)/hooks

CHAIN_PATHS := src tests examples chat.py
COVERAGE_XML ?= chain-coverage.xml
COVERAGE_HTML ?= htmlcov/chain

# ---------------------------------------------------------------------------
# exec when running, run --rm otherwise — avoids container startup overhead
# for interactive development while remaining correct for CI.
# ---------------------------------------------------------------------------
define exec_or_run
	@if $(COMPOSE) ps --services --status running 2>/dev/null | grep -qx "$(SERVICE)"; then \
		$(COMPOSE) exec $(SERVICE) $(1); \
	else \
		$(COMPOSE) run --rm --no-deps $(SERVICE) $(1); \
	fi
endef

help:
	@echo ""
	@echo "Movie Finder Chain — available targets"
	@echo "======================================"
	@echo ""
	@echo "  Setup"
	@echo "    init             Build image, create .env from template, install git hook"
	@echo ""
	@echo "  Lifecycle"
	@echo "    up               Start the persistent dev container (alias for editor-up)"
	@echo "    down             Stop the dev container"
	@echo "    editor-up        Start a headless container for IDE attachment"
	@echo "    editor-down      Stop the IDE-attached container"
	@echo "    logs             Tail logs from the running container"
	@echo "    shell            Open a zsh shell in the running container"
	@echo ""
	@echo "  Quality"
	@echo "    lint             Run ruff check (report only)"
	@echo "    format           Run ruff format (apply)"
	@echo "    fix              Run ruff check --fix + ruff format (apply all auto-fixes)"
	@echo "    typecheck        Run mypy --strict"
	@echo "    test             Run pytest"
	@echo "    test-coverage    Run pytest with coverage XML/HTML output"
	@echo "    pre-commit       Run all pre-commit hooks"
	@echo "    check            lint + typecheck + test-coverage"
	@echo ""
	@echo "  CI"
	@echo "    ci-down          Hard cleanup for CI (down -v --rmi local)"
	@echo ""
	@echo "  Examples"
	@echo "    example-basic    Run examples/basic_usage.py inside Docker"
	@echo "    example-streaming Run examples/streaming_example.py inside Docker"
	@echo ""

init:
	@if [ ! -f .env ]; then cp .env.example .env && echo ">>> .env created from .env.example"; fi
	$(COMPOSE) build $(SERVICE)
	@printf '#!/bin/sh\nexec make pre-commit\n' > $(GIT_HOOKS_DIR)/pre-commit
	@chmod +x $(GIT_HOOKS_DIR)/pre-commit
	@echo ">>> git pre-commit hook installed (calls 'make pre-commit' on every commit)"

up: editor-up

down:
	$(COMPOSE) down

editor-up:
	$(COMPOSE) up -d $(SERVICE)

editor-down: down

logs:
	$(COMPOSE) logs -f $(SERVICE)

shell:
	@if $(COMPOSE) ps --services --status running 2>/dev/null | grep -qx "$(SERVICE)"; then \
		$(COMPOSE) exec $(SERVICE) zsh; \
	else \
		$(COMPOSE) run --rm $(SERVICE) zsh; \
	fi

lint:
	$(call exec_or_run,ruff check $(CHAIN_PATHS))

format:
	$(call exec_or_run,ruff format $(CHAIN_PATHS))

fix:
	$(call exec_or_run,ruff check --fix $(CHAIN_PATHS))
	$(call exec_or_run,ruff format $(CHAIN_PATHS))

typecheck:
	$(call exec_or_run,mypy src)

test:
	$(call exec_or_run,pytest tests/ --asyncio-mode=auto -v --tb=short)

test-coverage:
	$(call exec_or_run,pytest tests/ --asyncio-mode=auto -v --tb=short \
		--cov=chain \
		--cov-report=term-missing \
		--cov-report=xml:$(COVERAGE_XML) \
		--cov-report=html:$(COVERAGE_HTML))

pre-commit:
	$(call exec_or_run,pre-commit run --all-files)

ci-down:
	$(COMPOSE) down -v --rmi local

check: lint typecheck test-coverage

example-basic:
	$(COMPOSE) run --rm --no-deps $(SERVICE) python examples/basic_usage.py

example-streaming:
	$(COMPOSE) run --rm --no-deps $(SERVICE) python examples/streaming_example.py
