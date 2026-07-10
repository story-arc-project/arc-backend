#!/bin/bash
set -e
cd "$(dirname "$0")/../app" || exit 1
source ../.env

OVERRIDE_FILE="../docker-compose.db-expose.yml"

cleanup() {
  docker compose -f "$OVERRIDE_FILE" down
  rm -f "$OVERRIDE_FILE"
}
trap cleanup EXIT

sed 's/image: pgvector\/pgvector:pg16/image: pgvector\/pgvector:pg16\n    ports:\n      - "5432:5432"/' ../docker-compose.yml > $OVERRIDE_FILE

docker compose -f $OVERRIDE_FILE down
docker volume rm arc-backend_db_data || true
docker compose -f $OVERRIDE_FILE up -d --build db

DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME

# Wait for db to be ready
until docker compose -f $OVERRIDE_FILE exec db pg_isready -U $DB_USER -d $DB_NAME; do
  sleep 1
done

DATABASE_URL=$DATABASE_URL uv run alembic upgrade head
DATABASE_URL=$DATABASE_URL uv run alembic revision --autogenerate -m "$1"

echo "Migration file generated. Edit it, then press Enter to run upgrade head..."
read -r
DATABASE_URL=$DATABASE_URL uv run alembic upgrade head