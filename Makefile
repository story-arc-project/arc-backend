PROJECT_NAME ?= arc-backend
COMPOSE := docker compose -f ./docker-compose.yml --project-directory . -p "$(PROJECT_NAME)"
COMPOSE_INIT := docker compose -f ./init/docker-compose.yml --project-directory . -p "$(PROJECT_NAME)"

.PHONY: build stop certificate run revision

build:
	COMPOSE_BAKE=true $(COMPOSE) build

stop:
	$(COMPOSE) down

certificate:
	set -e; \
	trap '$(COMPOSE_INIT) down' EXIT; \
	$(COMPOSE_INIT) up --exit-code-from certbot

run: build stop certificate
	$(COMPOSE) up -d

revision:
	./scripts/revision.sh "$(MSG)"