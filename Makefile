PROJECT_NAME ?= arc-backend
COMPOSE := docker compose -f ./docker/docker-compose.yml --project-directory . -p "$(PROJECT_NAME)"
COMPOSE_INIT := docker compose -f ./init/docker-compose.yml --project-directory . -p "$(PROJECT_NAME)"

.PHONY: build stop certificate run deploy-prod revision logs psql local-run

build:
	COMPOSE_BAKE=true $(COMPOSE) build

stop:
	$(COMPOSE) down

certificate:
	@set -a; [ -f ./.env ] && . ./.env; set +a; \
	if docker run --rm -v $(PROJECT_NAME)_certbot-etc:/etc/letsencrypt alpine sh -c "[ -f /etc/letsencrypt/live/$$DOMAIN/fullchain.pem ]"; then \
		echo "SSL certificate already exists. Skipping generation."; \
	else \
		echo "No certificate found. Generating new SSL certificate..."; \
		set -e; \
		trap '$(COMPOSE_INIT) down' EXIT; \
		$(COMPOSE_INIT) up --exit-code-from certbot; \
	fi

run: build
	$(COMPOSE) up -d --remove-orphans

deploy-prod: certificate
	$(COMPOSE) up -d --pull always --remove-orphans
	docker image prune -f

revision:
	@test -n "$(MSG)" || (echo "Usage: make revision MSG='message'" && exit 1)
	./scripts/revision.sh "$(MSG)"

logs:
	$(COMPOSE) logs -f

psql:
	@set -a; . ./.env; set +a; \
	docker exec -it $(PROJECT_NAME)-db-1 psql -U "$$DB_USER" -d "$$DB_NAME"

local-run: build stop
	$(COMPOSE) up -d app