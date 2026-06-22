# Windows Docker Setup

This project runs on Windows through Docker Desktop Linux containers. It does
not use a Windows-native container image.

## Requirements

- Windows 10 or 11 with Docker Desktop.
- Docker Desktop configured for Linux containers with the WSL 2 backend.
- PowerShell 5.1 or newer.
- A dedicated Codex/ChatGPT sign-in for this project.
- Optional: `docker login ghcr.io` if the GitHub Container Registry package is
  private.

Keep the repository in a normal local path such as `C:\Users\<you>\Projects`.
Avoid synced or network-backed folders for the `data/` directory if Docker file
sharing behaves oddly.

## Setup

From the repository root in PowerShell, run:

```powershell
.\scripts\setup_windows.ps1
```

The setup script:

- copies `.env.example` to `.env` if `.env` does not exist;
- creates `data\codex-home`, `data\codex-work`, and `data\secrets`;
- writes a strong wrapper bearer token to `data\secrets\proxy_api_key` as UTF-8;
- leaves existing `.env` and token files in place unless `-ForceSecret` is
  used.

Then build and run locally:

```powershell
docker compose up --build -d
```

For a published image, pass the image tag once during setup:

```powershell
.\scripts\setup_windows.ps1 -Image "ghcr.io/subdepthtech/codex-cli-provider:v0.1.2"
docker compose -f docker-compose.image.yml pull
docker compose -f docker-compose.image.yml up -d
```

Do not use `latest`.

## Codex Login

Complete Codex login inside the running container:

```powershell
docker exec -it codex-cli-provider `
  codex login --device-auth `
  -c 'forced_login_method="chatgpt"' `
  -c 'cli_auth_credentials_store="file"'
```

Credentials are written to `/root/.codex` in the Linux container, backed by the
local `data\codex-home` directory.

Confirm readiness:

```powershell
curl.exe -sS http://127.0.0.1:8320/healthz
```

## Client Settings

Use these settings from Windows apps:

- Base URL: `http://127.0.0.1:8320/v1`
- API key: the contents of `data\secrets\proxy_api_key`
- Model: `codex-cli-default`
- Concurrency: `1`

Load the wrapper token into PowerShell for manual API checks:

```powershell
$ProxyApiKey = (Get-Content -Raw data\secrets\proxy_api_key).Trim()
curl.exe -sS `
  -H "Authorization: Bearer $ProxyApiKey" `
  http://127.0.0.1:8320/v1/models
```

## Notes

- Keep Docker Desktop in Linux-container mode.
- Do not set `OPENAI_API_KEY`.
- Keep Codex/ChatGPT auth in `data\codex-home`.
- Keep the wrapper bearer token in `data\secrets\proxy_api_key`.
- If `docker compose` cannot mount files, check Docker Desktop file-sharing
  settings for the drive that contains the repository.
- If `data\secrets\proxy_api_key` was created manually, make sure it is UTF-8
  text and contains only the token plus an optional trailing newline.
