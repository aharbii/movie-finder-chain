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

# Git is needed for uv sync in case of git dependencies, even in builder/runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy


# ---- Stage 1: dev -----------------------------------------------------------
FROM uv-base AS dev

# Install rich dev tools only in the dev stage
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    make \
    zsh \
    vim \
    jq \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Oh My Zsh for a rich terminal experience
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended && \
    chsh -s $(which zsh)

WORKDIR /workspace

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV="/opt/venv" \
    PYTHONPATH="/workspace/chain/src:/workspace/imdbapi/src" \
    SHELL=/bin/zsh

# In standalone mode, we assume files are in .
# In workspace mode, the Makefile handles context.
COPY pyproject.toml uv.lock* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --all-groups --active --no-install-workspace; \
    else \
        uv sync --all-groups --active --no-install-workspace; \
    fi && \
    /opt/venv/bin/pip install --no-cache-dir pre-commit

# Configure zsh to use oh-my-zsh and have a nice prompt
RUN sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="agnoster"/' ~/.zshrc && \
    echo "alias ls='ls --color=auto'" >> ~/.zshrc && \
    echo "alias ll='ls -alF'" >> ~/.zshrc && \
    echo "alias la='ls -A'" >> ~/.zshrc && \
    echo "alias l='ls -CF'" >> ~/.zshrc

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
