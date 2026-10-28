# Agent instructions — arc-backend

## Repository layout
- `app/`: FastAPI backend, SQLModel/PostgreSQL models, Alembic migrations and API tests. Python >=3.13.12.
- `ai_analyst/`: separate Python service using FastAPI, Celery and Playwright. Python >=3.12.13.
- `docker/docker-compose.yml`: application/service orchestration.
- `init/`: certificate initialization; `nginx/`: reverse-proxy configuration.
- `scripts/` and root `Makefile`: existing build and maintenance entrypoints.

## Protected paths and branching rules
- **Never modify any file under `ai_analyst/`** (including configuration, tests, lockfiles and generated files). Treat this directory as read-only unless the user explicitly revokes this restriction.
- **Create every new working branch from `dev`, not `main` or another feature branch.** Target `dev` for pull requests unless explicitly instructed otherwise. Verify the base branch before creating a branch or PR.

## Workspace initialization (Codex Cloud or fresh Linux checkout)
Run commands from the repository root unless otherwise stated.
1. Install `uv` if missing, following https://docs.astral.sh/uv/getting-started/installation/.
2. Install dependencies for the editable backend service:
   ```sh
   cd app && uv sync --frozen && cd ..
   ```
   If the lockfile is absent or stale, report that instead of silently rewriting it.
3. For tests requiring containers, install Docker with the Compose plugin and ensure the Docker daemon is available. This is optional for code-only tasks; cloud sandboxes may not provide a working daemon.
4. Never assume production credentials or services are available. Use `.env.template` only to identify required variable names; populate test-safe values through the environment or an ignored local `.env`. Never commit credentials.
5. External PostgreSQL, Redis, RabbitMQ, object storage and APIs must not be assumed available. Prefer mocks or isolated test containers. Do not connect to production by default.

## Validation
- Backend: `cd app && uv run pytest`
- Run targeted tests before full suites. Some tests may need Docker or external services; report skipped/blocked tests accurately.
- Validate changes within the affected service and avoid editing unrelated files.
- Preserve lockfiles unless dependency changes require updating them intentionally.

## Database and infrastructure safety
- Review `app/alembic/README` before migration work.
- Treat migrations as versioned, reviewable changes. Do not rewrite previously applied migrations or run migrations against a remote/production database without explicit authorization.
- Do not run `make deploy-prod`, `make certificate`, destructive Docker cleanup, or production-oriented deployment commands during workspace setup.
- Never run `docker image prune -af` as part of validation.
- Do not expose secrets in logs or commits; avoid using real cloud credentials or service accounts in tests.

## Working conventions
- Inspect the nearest source code, existing tests and project patterns before modifying code.
- Keep changes focused and add or update tests for behavior changes.
- Prefer `uv run` and checked-in lockfiles over ad-hoc global installs.
- In your completion report, state changed files, test commands/results, and any environment limitations.

## Codex Cloud note
This document guides the agent; it is not an automatically executed initialization script. Configure Codex Cloud's environment setup commands separately if dependencies must be installed before the agent begins. A reasonable setup script is:
```sh
set -eu
(cd app && uv sync --frozen)
```
Use this only in an environment with `uv` installed and compatible Python interpreters available.
