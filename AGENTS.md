# AGENTS.md

Project notes for future Codex/agent sessions.

## Published Images

Public users should build locally by default:

```bash
docker compose up --build -d
```

Use the image-only Compose file only when pulling a published image. Do not use
`latest`; tags should include the image name and version, for example
`codex-cli-provider-0.1.2`.

```bash
CODEX_CLI_PROVIDER_IMAGE=registry.example.com/your-org/codex-cli-provider:codex-cli-provider-0.1.2 \
  docker compose -f docker-compose.image.yml up -d
```

## Auth Boundaries

Do not bake credentials into the image or Compose files.

- Docker Hub auth belongs in local Docker credential storage via `docker login`.
- The wrapper bearer token belongs in `data/secrets/proxy_api_key`.
- Codex/ChatGPT auth belongs in the dedicated bind-mounted `data/codex-home`.
- Do not use or add `OPENAI_API_KEY` for this project.

Codex login is completed inside the running container so credentials are written
to the mounted `/root/.codex` backed by `data/codex-home`:

```bash
docker exec -it codex-cli-provider \
  codex login --device-auth \
  -c forced_login_method='"chatgpt"' \
  -c cli_auth_credentials_store='"file"'
```

## Local Development

Use the default Compose file when building locally:

```bash
docker compose up --build -d
```

Use `docker-compose.image.yml` only when pulling a published image.

## Verification

Before handing off changes, run:

```bash
python3 scripts/check_repo_hygiene.py
python3 scripts/check_compose_security.py
COMPOSE_FILE=docker-compose.image.yml CODEX_CLI_PROVIDER_IMAGE=registry.example.com/your-org/codex-cli-provider:codex-cli-provider-0.1.2 python3 scripts/check_compose_security.py
PYTHONPATH=. .venv/bin/pytest -q
```

The test suite expects the repo root on `PYTHONPATH`, matching the container's
`PYTHONPATH=/app` setting.

## Security Notes

The Dockerfile currently copies only `requirements.txt` and `src/`. Keep it that
way unless there is a specific reason to widen the build context. `.dockerignore`
excludes `.env`, `data/`, Codex auth files, virtualenvs, logs, and other local
state that must not be published in images.
