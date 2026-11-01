# RADICH M15.1 — Linux container image for Hetzner Cloud.
# Deployment configuration and PostgreSQL wiring are separate M15 tasks.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install RADICH with API and PostgreSQL dependencies.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir ".[api,postgres]" \
    && useradd --system --create-home --uid 10001 radich

USER radich
EXPOSE 8000

# Start the injected, PostgreSQL-backed ASGI application factory.
CMD ["uvicorn", "radich.deployment:build_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
