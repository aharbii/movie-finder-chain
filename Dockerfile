# ============================================================
# Stage 1 — Builder
# Installs the workspace (imdbapi + chain) into a venv and
# builds a wheel for the chain package.
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /build

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace pyproject and both packages
COPY pyproject.toml ./
COPY imdbapi/ ./imdbapi/
COPY chain/ ./chain/

# Create virtual env and install all workspace packages
RUN uv venv /opt/venv && \
    uv sync --all-packages --no-dev

# ============================================================
# Stage 2 — Runtime
# Minimal image — only the venv and source code.
# ============================================================
FROM python:3.13-slim AS runtime

# Non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/sh --create-home appuser

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy chain source (needed for prompts + importlib.resources)
COPY --from=builder /build/chain/src /app/src

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

# The chain is a library — no default CMD.
# Override when running tests or embedding in a FastAPI container:
#   docker run movie-finder-chain pytest tests/
CMD ["python", "-c", "from chain import compile_graph; print('chain OK')"]
