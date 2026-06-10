#!/bin/bash
set -e
cd "$(dirname "$0")/app" || exit 1
source ../.env
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
DATABASE_URL=$DATABASE_URL uv run alembic revision --autogenerate -m "$1"
DATABASE_URL=$DATABASE_URL uv run alembic upgrade head