# syntax=docker/dockerfile:1.7
# TenQ.ai API image. Multi-stage: dependencies are resolved with uv in a builder stage; the
# runtime stage contains only Python, the virtualenv, and the application code.
# Multi-arch: every base image here is published for linux/amd64 and linux/arm64 (Oracle A1).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.12.24 AS uv

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first so code changes do not invalidate this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TENQ_DATABASE_PATH=/data/tenq.sqlite3
# Unprivileged user with a fixed UID so volume ownership is predictable.
RUN groupadd --system --gid 10001 tenq \
    && useradd --system --uid 10001 --gid tenq --home-dir /app --shell /usr/sbin/nologin tenq \
    && mkdir -p /data /app \
    && chown tenq:tenq /data
COPY --from=builder /opt/venv /opt/venv
COPY --chown=root:root app /app/app
WORKDIR /app
USER tenq
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status != 200)"]
# SIGTERM -> uvicorn stops accepting connections and lets in-flight requests finish
# (at most 25 s, below the compose stop_grace_period). No --proxy-headers: the app decides
# itself which forwarded headers to trust (app/core/client_ip.py).
STOPSIGNAL SIGTERM
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--no-server-header", "--timeout-graceful-shutdown", "25", "--timeout-keep-alive", "15"]
