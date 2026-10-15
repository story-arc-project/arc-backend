FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV PATH="/root/.local/bin/:$PATH"
ENV UV_PYTHON=3.12.13

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/root/.local/bin:/app/.venv/bin:$PATH"

COPY . .

EXPOSE 8001
