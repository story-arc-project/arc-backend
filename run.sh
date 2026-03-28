#!/bin/bash
cd "$(dirname "$0")" || exit 1
./stop.sh
source ./config.sh
docker compose -f ./init/docker-compose.yml -p "$PROJECT_NAME" --project-directory . up --exit-code-from certbot
docker compose -f ./init/docker-compose.yml -p "$PROJECT_NAME" --project-directory . down
docker build -t arc-backend-app ./app
docker compose -f ./docker-compose.yml -p "$PROJECT_NAME" up -d
