#!/bin/bash
cd "$(dirname "$0")" || exit 1
./stop.sh
docker build -t arc-backend-app ./app
docker compose -f ./docker-compose.yml up -d
