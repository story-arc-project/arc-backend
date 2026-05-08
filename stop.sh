#!/bin/bash
set -e
cd "$(dirname "$0")" || exit 1
source ./config.sh
docker compose -f ./docker-compose.yml -p "$PROJECT_NAME" down
