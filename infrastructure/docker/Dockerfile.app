FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.6.17 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps ./apps
COPY services ./services
COPY infrastructure/docker/healthcheck.py /app/healthcheck.py

ARG PACKAGE=aigateway-gateway
RUN uv sync --frozen --no-dev --package ${PACKAGE} \
    && chown -R app:app /app

ARG MODULE=aigateway.gateway.main:app
ARG HEALTH_PATH=/health
ARG PORT=8000

ENV APP_MODULE=${MODULE} \
    HEALTH_PATH=${HEALTH_PATH} \
    PORT=${PORT}

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python /app/healthcheck.py

CMD ["sh", "-c", "uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port \"$PORT\""]
