#!/bin/bash
set -e
cd "$(dirname "$0")" || exit 1
source ./config.sh
docker compose build
docker compose -f ./docker-compose.yml -p "$PROJECT_NAME" down
docker compose -f ./init/docker-compose.yml -p "$PROJECT_NAME" --project-directory . up --exit-code-from certbot
docker compose -f ./init/docker-compose.yml -p "$PROJECT_NAME" --project-directory . down
docker compose -f ./docker-compose.yml -p "$PROJECT_NAME" up -d
