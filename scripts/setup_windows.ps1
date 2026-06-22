param(
    [string]$Image = "",
    [switch]$ForceSecret
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    [IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $escapedName = [regex]::Escape($Name)
    if (Test-Path -LiteralPath $Path) {
        $lines = New-Object "System.Collections.Generic.List[string]"
        foreach ($line in [IO.File]::ReadAllLines($Path)) {
            $lines.Add($line)
        }
    } else {
        $lines = New-Object "System.Collections.Generic.List[string]"
    }

    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*#?\s*$escapedName=") {
            $lines[$i] = "$Name=$Value"
            $updated = $true
        }
    }

    if (-not $updated) {
        $lines.Add("$Name=$Value")
    }

    [IO.File]::WriteAllLines($Path, $lines, $Utf8NoBom)
}

Set-Location $RepoRoot

$envExamplePath = Join-Path $RepoRoot ".env.example"
$envPath = Join-Path $RepoRoot ".env"
$codexHomePath = Join-Path $RepoRoot "data/codex-home"
$codexWorkPath = Join-Path $RepoRoot "data/codex-work"
$secretsPath = Join-Path $RepoRoot "data/secrets"
$proxySecretPath = Join-Path $secretsPath "proxy_api_key"

if (-not (Test-Path -LiteralPath $envExamplePath)) {
    throw "Missing .env.example in $RepoRoot"
}

if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
} else {
    Write-Host "Keeping existing .env"
}

if ($Image.Trim()) {
    Set-DotEnvValue -Path $envPath -Name "CODEX_CLI_PROVIDER_IMAGE" -Value $Image.Trim()
    Write-Host "Set CODEX_CLI_PROVIDER_IMAGE in .env"
}

New-Item -ItemType Directory -Force -Path $codexHomePath, $codexWorkPath, $secretsPath | Out-Null
Write-Host "Ensured data/codex-home, data/codex-work, and data/secrets exist"

if ((Test-Path -LiteralPath $proxySecretPath) -and (-not $ForceSecret)) {
    Write-Host "Keeping existing data/secrets/proxy_api_key"
} else {
    $tokenBytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($tokenBytes)
    } finally {
        $rng.Dispose()
    }
    $token = [Convert]::ToBase64String($tokenBytes)
    Write-Utf8File -Path $proxySecretPath -Content "$token`n"
    Write-Host "Wrote new UTF-8 wrapper bearer token to data/secrets/proxy_api_key"
}

Write-Host ""
Write-Host "Next steps:"
if ($Image.Trim()) {
    Write-Host "  docker compose -f docker-compose.image.yml pull"
    Write-Host "  docker compose -f docker-compose.image.yml up -d"
} else {
    Write-Host "  docker compose up --build -d"
}
Write-Host "  docker exec -it codex-cli-provider codex login --device-auth -c 'forced_login_method=`"chatgpt`"' -c 'cli_auth_credentials_store=`"file`"'"
Write-Host ""
Write-Host "Use http://127.0.0.1:8320/v1 as the client base URL."
