#!/bin/bash
set -e
cd "$(dirname "$0")/.." || exit 1

docker build -t $IMAGE_NAME/app:$IMAGE_TAG app
docker build -t $IMAGE_NAME/ai_analyst:$IMAGE_TAG ai_analyst