FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tools needed by a couple of transitive C-extension deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the metadata + sources needed by the (hatchling) editable install.
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY config ./config
COPY migrations ./migrations

RUN pip install --upgrade pip && pip install -e .

# Non-root
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
