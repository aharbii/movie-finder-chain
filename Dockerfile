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

# Install only what the attached-container workflow actually needs:
#   git   — pre-commit hooks and submodule ops
#   zsh   — make shell target
#   make  — run make targets from inside the container when needed
#   curl  — occasional HTTP debugging / health checks
# keep-sorted start
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    make \
    zsh \
    && rm -rf /var/lib/apt/lists/*
# keep-sorted end

WORKDIR /workspace

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV="/opt/venv" \
    PYTHONPATH="/workspace/chain/src:/workspace/imdbapi/src" \
    SHELL=/bin/zsh

COPY pyproject.toml uv.lock* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --all-groups --active --no-install-workspace; \
    else \
        uv sync --all-groups --active --no-install-workspace; \
    fi && \
    /opt/venv/bin/pip install --no-cache-dir pre-commit

# Minimal zsh config — no internet download, no heavy themes.
RUN printf 'export PS1="[chain] %n@%m:%~%% "\nalias ls="ls --color=auto"\nalias ll="ls -alF"\n' \
    > /root/.zshrc

CMD ["sleep", "infinity"]


# ---- Stage 2: builder -------------------------------------------------------
FROM uv-base AS builder

WORKDIR /build

COPY pyproject.toml uv.lock* ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev --no-editable; \
    else \
        uv sync --no-dev --no-editable; \
    fi


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
