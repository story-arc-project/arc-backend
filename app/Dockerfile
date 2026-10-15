FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

ENV PATH="/root/.local/bin/:$PATH"
ENV UV_PYTHON=3.13.12

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/root/.local/bin:/app/.venv/bin:$PATH"

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]