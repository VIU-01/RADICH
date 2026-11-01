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

# The ASGI application factory requires an injected runner and repository.
# M15.2 will supply the production application entrypoint and Compose wiring.
# Do not run uvicorn against radich.api:create_app without those dependencies.
CMD ["python", "-c", "import radich, radich.api; print('RADICH image ready; M15.2 entrypoint pending')"]
