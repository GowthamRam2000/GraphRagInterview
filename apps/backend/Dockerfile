FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml

RUN uv sync --project apps/backend --no-dev --frozen

COPY apps/backend/app apps/backend/app

ENV PATH="/opt/venv/bin:${PATH}"

CMD ["sh", "-c", "uvicorn --app-dir apps/backend app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
