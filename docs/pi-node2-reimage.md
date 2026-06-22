# pi-node2 Reimage Runbook

This runbook is for rebuilding the homelab `pi-node2` host that runs
`codex-cli-provider` from a published image. Keep host-specific values, tokens,
runner registration details, and recovery notes in the ignored top-level
`handoff.md` file, not in tracked documentation.

## Before Reimage

Record the current deploy state without printing credentials:

```bash
cd /home/pi/projects/codex-cli-provider
git status --short --branch
git remote -v
docker compose -f docker-compose.image.yml ps
docker image ls 'ghcr.io/subdepthtech/codex-cli-provider'
test -f .env && printf '.env exists\n'
test -f data/secrets/proxy_api_key && printf 'proxy_api_key exists\n'
test -f data/codex-home/auth.json && printf 'codex auth exists\n'
```

Decide whether to preserve or recreate local state:

- `.env`: local wrapper limits and deploy settings. Back it up only through the
  host's private backup path.
- `data/secrets/proxy_api_key`: wrapper bearer token. Preserve it only if
  existing clients must keep working without changing their configured API key.
  Otherwise regenerate it after the reimage.
- `data/codex-home/`: dedicated Codex/ChatGPT login state. Treat it as a live
  credential. Prefer a fresh device login unless the operator explicitly chooses
  to restore the dedicated project auth home.
- `data/codex-work/`: disposable provider workspace unless the operator has put
  recovery artifacts there.
- Docker/GHCR auth and GitHub self-hosted runner registration are host-local and
  should be recreated after the reimage.

Do not back up or publish a normal user `~/.codex`, an `OPENAI_API_KEY`, Docker
socket credentials, or any host home directory into this project.

## Restore From Image

Install Docker Engine, Docker Compose v2, Git, and Python 3. Then recreate the
checkout and local state:

```bash
mkdir -p /home/pi/projects
git clone https://github.com/subdepthtech/codex-cli-provider.git /home/pi/projects/codex-cli-provider
cd /home/pi/projects/codex-cli-provider
cp .env.example .env
mkdir -p data/codex-home data/codex-work data/secrets
python3 - <<'PY'
import pathlib, secrets
path = pathlib.Path("data/secrets/proxy_api_key")
path.write_text(secrets.token_urlsafe(48) + "\n")
PY
chmod 600 .env data/secrets/proxy_api_key
chmod 700 data/codex-home data/codex-work data/secrets
docker login ghcr.io
```

If restoring a preserved `.env`, `proxy_api_key`, or `data/codex-home`, copy it
into place before starting the service and keep the same file permissions.

Start from an explicit candidate or release tag. Never use `latest`:

```bash
export CODEX_CLI_PROVIDER_IMAGE=ghcr.io/subdepthtech/codex-cli-provider:codex-cli-provider-0.1.2
COMPOSE_FILE=docker-compose.image.yml python3 scripts/check_compose_security.py
docker compose -f docker-compose.image.yml pull
docker compose -f docker-compose.image.yml up -d
```

If `data/codex-home` was not restored, complete the dedicated ChatGPT device
login inside the container:

```bash
docker exec -it codex-cli-provider \
  codex login --device-auth \
  -c forced_login_method='"chatgpt"' \
  -c cli_auth_credentials_store='"file"'
```

Verify the deployment:

```bash
python3 scripts/smoke_test_provider.py
python3 scripts/smoke_test_provider.py --chat
```

The `--chat` check sends one live upstream request through the signed-in Codex
CLI account. Skip it until the dedicated device login is complete.

## Restore Automated Deploys

Install the GitHub self-hosted runner on `pi-node2` with labels:

```text
self-hosted, linux, arm64, pi-node2
```

In GitHub, keep the `pi-node2` environment protected with manual approval.
Only trusted branches should deploy to the self-hosted runner. Set
`PI_NODE2_DEPLOY_DIR` only if the checkout is not
`/home/pi/projects/codex-cli-provider`.

After the runner is online, use the `deploy-pi-node2` workflow with an exact
candidate or release image tag. The workflow validates the tag, updates the
fixed checkout, runs the image compose security check, restarts the service, and
runs the smoke test.

## Local Handoff Notes

Use the ignored top-level `handoff.md` for details that should survive the
reimage discussion but must not be pushed, such as:

- whether the old `.env` or wrapper bearer token was preserved;
- whether `data/codex-home` was restored or reauthenticated;
- current image tag running on the host;
- self-hosted runner registration state;
- private backup location names.

Do not commit `handoff.md`.
