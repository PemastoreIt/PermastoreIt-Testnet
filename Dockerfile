# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.9
# Corrected Casing: FROM ... AS ...
FROM python:${PYTHON_VERSION}-slim AS base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# === Install System Dependencies ===
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# === Application Setup ===
WORKDIR /app

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# === Python Dependency Installation ===
USER root
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install --timeout=600 -r requirements.txt

# === Final Application Stage ===
USER root
COPY . .
RUN chown -R appuser:appuser /app

USER appuser
EXPOSE 5000

# Corrected CMD: Use JSON exec form
CMD ["python", "server.py"]