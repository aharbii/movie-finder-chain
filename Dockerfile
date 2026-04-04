# =============================================================================
# movie-finder-chain — local development and runtime images
#
# Build context: backend/ (when part of workspace) or . (standalone)
#
# Targets:
#   dev      Docker-only local workflow used by chain/docker-compose.yml
#   builder  Intermediate stage for dependency resolution
#   runtime  Minimal image for smoke tests and standalone packaging
# =============================================================================

FROM python:3.13-slim AS uv-base

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy


# ---- Stage 1: dev -----------------------------------------------------------
FROM uv-base AS dev

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    && rm -rf /var/lib/apt/lists/*

RUN git config --global --add safe.directory /workspace

WORKDIR /workspace

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV="/opt/venv" \
    PYTHONPATH="/workspace/src:/imdbapi/src"

# Copy manifests for current repo AND its path dependency for resolution.
# Context is assumed to be the parent directory (backend/) if built via Makefile.
COPY chain/pyproject.toml chain/uv.lock* chain/README.md ./
COPY imdbapi/pyproject.toml imdbapi/README.md /imdbapi/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --all-groups --active --no-install-workspace

CMD ["sleep", "infinity"]


# ---- Stage 2: builder -------------------------------------------------------
FROM uv-base AS builder

WORKDIR /build

COPY pyproject.toml uv.lock* ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project


# ---- Stage 3: runtime -------------------------------------------------------
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="movie-finder-chain"
LABEL org.opencontainers.image.description="Movie Finder — LangGraph chain library"

RUN useradd --system --uid 1001 --no-create-home appuser

WORKDIR /app

COPY --link --from=builder /build/.venv /app/.venv
COPY --link --from=builder /build/src ./src

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

USER appuser

CMD ["python", "-c", "from chain.graph import compile_graph; print('chain OK')"]
