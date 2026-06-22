# codex-cli-provider

Experimental local adapter that exposes a small OpenAI-compatible HTTP surface
and runs each chat completion request through the Codex CLI inside Docker.

The original target client is Obsidian LLM Wiki, but the adapter is intentionally
plain HTTP: it implements `/v1/models` and `/v1/chat/completions` well enough
for text-only, OpenAI-compatible clients that can work with one model alias.

## Important Notice

This project is for local, operator-controlled use. It is not a public service,
not an official OpenAI API implementation, not an API billing substitute, and
not a way to bypass authentication, pool accounts, scrape tokens, or evade
provider limits.

You must bring your own dedicated Codex/ChatGPT login and make sure your use of
that login is allowed by the applicable OpenAI product terms and policies. This
repository does not grant permission to power third-party integrations with a
ChatGPT subscription.

The service deliberately refuses startup when `OPENAI_API_KEY` is present:

```text
OPENAI_API_KEY
```

Codex authentication belongs only in the dedicated bind-mounted
`data/codex-home` directory. Do not copy your normal `~/.codex` into this
project.

## What It Provides

- `GET /healthz` readiness check.
- `GET /v1/models` with the local model alias `codex-cli-default`.
- `POST /v1/chat/completions` for text-only chat messages.
- Non-streaming responses and final-only SSE streaming.
- One active Codex execution by default, with an optional second local execution
  slot and short local wait queue.
- A local operator dashboard at `http://127.0.0.1:8320/dashboard/`.

## What It Does Not Provide

- Embeddings, Responses API, tools, functions, function calls, images, audio, or
  files.
- Token-by-token streaming. Streaming mode sends the final answer as one SSE
  content delta.
- Official OpenAI API billing, quotas, authentication, or service-level
  guarantees.
- Multi-user isolation. Treat it as a single-user local adapter.

## Architecture

```text
Local OpenAI-compatible client
  -> http://127.0.0.1:8320/v1
  -> FastAPI wrapper in Docker
  -> Codex CLI one-shot execution
  -> dedicated CODEX_HOME at ./data/codex-home
  -> dedicated workspace at ./data/codex-work
```

The Docker image installs a pinned official Codex CLI release and the Python
wrapper runtime. The Compose files publish only `127.0.0.1:8320:8320`.

Pinned Codex CLI version:

```text
codex-cli 0.141.0
```

Codex is invoked non-interactively with an ephemeral session. The prompt is
passed on stdin, the final response is read from a private temporary output
file, and Codex progress JSONL is treated as internal metadata.

## Security Model

Protected assets include the wrapper bearer token in
`data/secrets/proxy_api_key`, Codex credentials under `data/codex-home`, the
host filesystem, unrelated host credentials, submitted note content, and
generated responses.

The main security boundaries are:

- Every `/v1/*` route requires the wrapper bearer token.
- Codex/ChatGPT credentials are stored only in the project-local
  `data/codex-home` mount.
- The container root filesystem is read-only.
- The Compose files mount only `data/codex-home`, `data/codex-work`, and the
  read-only wrapper bearer-token file.
- Docker capabilities are dropped, with only `DAC_OVERRIDE` and `FOWNER` added
  back so container root can access the dedicated bind mounts.
- `no-new-privileges` is enabled.
- Logs avoid raw prompts, bearer tokens, and Codex credentials.

Important residual risks:

- Codex runs inside the container with `danger-full-access`; Docker mount
  minimization is the remaining isolation boundary.
- Prompt-injected Codex commands can read and modify mounted project paths,
  including `data/codex-home` and `data/codex-work`.
- Prompt-injected Codex commands can read `/run/secrets/proxy_api_key`.
- Submitted content is sent to the upstream service used by the signed-in Codex
  CLI account.
- Prompt injection cannot be eliminated.
- `data/codex-home/auth.json` is a live credential and must be protected like a
  password.

For the discovery notes and implementation rationale, see
[`docs/discovery.md`](docs/discovery.md).

## Prerequisites

- Linux host with Docker Engine and Docker Compose v2.
- A dedicated Codex/ChatGPT sign-in for this project.
- Optional: access to a private container registry if you choose to publish and
  run your own image instead of building locally.

## Quick Start

Clone the repository:

```bash
git clone https://github.com/subdepthtech/codex-cli-provider.git
cd codex-cli-provider
```

Create local config and a strong wrapper bearer token:

```bash
cp .env.example .env
mkdir -p data/codex-home data/codex-work data/secrets
python3 - <<'PY'
import pathlib, secrets
path = pathlib.Path("data/secrets/proxy_api_key")
path.write_text(secrets.token_urlsafe(48) + "\n")
PY
chmod 600 .env data/secrets/proxy_api_key
chmod 700 data/codex-home data/codex-work data/secrets
```

Do not commit `.env` or anything under `data/`.

Build and start the local container:

```bash
docker compose up --build -d
```

Complete device login inside the running container:

```bash
docker exec -it codex-cli-provider \
  codex login --device-auth \
  -c forced_login_method='"chatgpt"' \
  -c cli_auth_credentials_store='"file"'
```

Confirm login without printing credentials:

```bash
docker exec -it codex-cli-provider codex login status
```

Check readiness:

```bash
curl -sS http://127.0.0.1:8320/healthz
```

`/healthz` returns 200 only after the container sees the pinned Codex CLI and a
dedicated ChatGPT login. It is normal for the container to report unhealthy
before device login is complete.

## API Examples

Load the wrapper bearer token into a shell variable:

```bash
PROXY_API_KEY="$(cat data/secrets/proxy_api_key)"
```

List models:

```bash
curl -sS \
  -H "Authorization: Bearer $PROXY_API_KEY" \
  http://127.0.0.1:8320/v1/models
```

Run one completion:

```bash
curl -sS \
  -H "Authorization: Bearer $PROXY_API_KEY" \
  -H "Content-Type: application/json" \
  http://127.0.0.1:8320/v1/chat/completions \
  -d '{"model":"codex-cli-default","messages":[{"role":"user","content":"Write one sentence."}]}'
```

Exercise final-only SSE mode:

```bash
curl -N \
  -H "Authorization: Bearer $PROXY_API_KEY" \
  -H "Content-Type: application/json" \
  http://127.0.0.1:8320/v1/chat/completions \
  -d '{"model":"codex-cli-default","stream":true,"messages":[{"role":"user","content":"Write one sentence."}]}'
```

Confirm the provider route rejects unauthenticated callers:

```bash
curl -i http://127.0.0.1:8320/v1/models
```

## Client Settings

For Obsidian LLM Wiki, use:

- Provider: `Custom / OpenAI-compatible`
- Base URL: `http://127.0.0.1:8320/v1`
- API Key: the value from `data/secrets/proxy_api_key`
- Model: `codex-cli-default`
- Page generation concurrency: `1`
- Suggested initial batch delay: `500-800 ms`

`/v1/models` supports Fetch Models. Embeddings are not implemented and are not
required for the inspected OpenAI-compatible provider path.

If near-simultaneous local requests collide, set `QUEUE_WAIT_SECONDS=2` or `3`
in `.env` and restart the wrapper. If the collisions are confirmed
`wrapper_busy` responses rather than upstream rate limits, you can also set
`MAX_CONCURRENT_CODEX_RUNS=2` to permit a second local Codex CLI execution.
Keep it at `1` if the signed-in Codex account starts returning
`upstream_rate_limit`.

## Configuration

Most configuration lives in `.env`, copied from `.env.example`.

| Variable | Purpose |
| --- | --- |
| `PROXY_API_KEY_FILE` | Path to the local bearer-token file. Compose mounts it read-only at `/run/secrets/proxy_api_key`. |
| `CODEX_UPSTREAM_MODEL` | Optional Codex model override passed to the CLI. Empty uses the Codex CLI default. |
| `CODEX_REQUEST_TIMEOUT_SECONDS` | Per-request Codex execution timeout. |
| `DASHBOARD_ENABLED` | Set to `false` to disable `/dashboard/*`. |
| `MAX_REQUEST_BODY_BYTES` | Maximum JSON request body size. |
| `MAX_MESSAGES` | Maximum number of chat messages. |
| `MAX_TOTAL_TEXT_CHARS` | Maximum total text across messages. |
| `QUEUE_WAIT_SECONDS` | Short local wait queue for bursty clients. Values are clamped to `0-5`. |
| `MAX_CONCURRENT_CODEX_RUNS` | Number of provider-side Codex executions allowed at once. Values are clamped to `1-2`; default `1`. |
| `CORS_ALLOWED_ORIGINS` | Optional comma-separated explicit origins. Requests without `Origin` are allowed. |
| `LOG_LEVEL` | Python wrapper log level. |

Unsupported inputs return OpenAI-shaped 400 errors. Unsupported inputs include
images, audio, files, tools, functions, function calls, tool-choice controls,
multimodal content, unknown fields, and `n != 1`.

Accepted but unmapped compatibility fields include `temperature`, `top_p`,
`max_tokens`, `max_completion_tokens`, `presence_penalty`, `frequency_penalty`,
`repetition_penalty`, `stop`, `response_format`, `user`, `seed`, `thinking`,
`reasoning_effort`, and `chat_template_kwargs`. Codex is not guaranteed to obey
those sampling controls.

## Dashboard

Open the local dashboard at:

```text
http://127.0.0.1:8320/dashboard/
```

The dashboard shows provider health, bearer-auth gate status, runner state,
runtime limits, a fixed probe, and sanitized in-process request events. It does
not store bearer tokens in browser storage, read `data/codex-home`, read or
rotate `proxy_api_key`, run device login, mount Docker, or display raw request
payloads.

If you expose the service beyond loopback, protect `/dashboard/` with the same
network controls used for the provider route. The safer default is to keep the
Compose loopback binding unchanged.

## Running A Published Image

The default public path is to build locally with `docker compose up --build -d`.
If you publish your own image, use the image-only Compose file and a specific
versioned tag. Do not use `latest`.

```bash
export CODEX_CLI_PROVIDER_IMAGE=registry.example.com/your-org/codex-cli-provider:codex-cli-provider-0.1.2
docker compose -f docker-compose.image.yml pull
docker compose -f docker-compose.image.yml up -d
```

Docker registry authentication belongs in local Docker credential storage via
`docker login`. Do not put Docker Hub passwords, ChatGPT/Codex credentials, or
OpenAI API keys in Compose files.

Codex authentication still lives only in the mounted `data/codex-home`
directory and must be completed inside the running container.

## Verification

Run repository checks without live credentials:

```bash
python3 scripts/check_repo_hygiene.py
python3 scripts/check_compose_security.py
COMPOSE_FILE=docker-compose.image.yml \
  CODEX_CLI_PROVIDER_IMAGE=registry.example.com/your-org/codex-cli-provider:codex-cli-provider-0.1.2 \
  python3 scripts/check_compose_security.py
PYTHONPATH=. .venv/bin/pytest -q
```

Live checks require a running container and the dedicated Codex login:

```bash
PROXY_API_KEY="$(cat data/secrets/proxy_api_key)"
curl -f http://127.0.0.1:8320/healthz
curl -f -H "Authorization: Bearer $PROXY_API_KEY" http://127.0.0.1:8320/v1/models
```

Do not print or inspect `data/codex-home/auth.json`.

## Operations

Stop the service:

```bash
docker compose down
```

Re-authenticate:

```bash
docker compose up -d
docker exec -it codex-cli-provider \
  codex login --device-auth \
  -c forced_login_method='"chatgpt"' \
  -c cli_auth_credentials_store='"file"'
```

Rotate the wrapper bearer token:

```bash
python3 - <<'PY'
import pathlib, secrets
path = pathlib.Path("data/secrets/proxy_api_key")
path.write_text(secrets.token_urlsafe(48) + "\n")
PY
chmod 600 data/secrets/proxy_api_key
docker compose restart
```

## Troubleshooting

- Device login unavailable: stop and do not use API-key login.
- Missing or stale authentication: run
  `docker exec -it codex-cli-provider codex login status`, then re-login in the
  dedicated container home.
- Wrapper 401: your `Authorization: Bearer` value does not match the file at
  `data/secrets/proxy_api_key`.
- `400` with `Message text is too large`: increase `MAX_TOTAL_TEXT_CHARS`, up to
  `500000`, and restart.
- `413` with `Request body too large`: increase `MAX_REQUEST_BODY_BYTES`, up to
  `2000000`, and restart.
- `429` with `code: "wrapper_busy"`: wait for active requests to finish,
  reduce client concurrency to `1`, increase batch delay, set a small
  `QUEUE_WAIT_SECONDS`, or opt into `MAX_CONCURRENT_CODEX_RUNS=2`.
- `429` with `code: "upstream_rate_limit"`: the signed-in upstream account is
  rate limited; wait and retry later, and keep `MAX_CONCURRENT_CODEX_RUNS=1`.
- `502` or `/healthz` returning `503`: check
  `docker exec -it codex-cli-provider codex login status`, then re-run device
  login if needed.
- Accidental API-key detection: unset `OPENAI_API_KEY` before starting.
- Sandbox failure: this configuration intentionally uses Codex
  `danger-full-access` inside Docker. Do not add `privileged`, `SYS_ADMIN`,
  unconfined seccomp/AppArmor, host networking, or host home mounts.
- Bind-mount permission failure: keep the dedicated `data/codex-home`,
  `data/codex-work`, and `data/secrets` paths writable by the Docker runtime.
- ARM64 versus AMD64: build for the matching image architecture and verify the
  Dockerfile checksum step.
