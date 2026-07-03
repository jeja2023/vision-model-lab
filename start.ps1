param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$SkipInstall,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

Import-DotEnv (Join-Path $Root ".env")

if (-not $env:VMLAB_WORKSPACE -or $env:VMLAB_WORKSPACE -eq ".") {
    $env:VMLAB_WORKSPACE = $Root
}
if (-not $env:VMLAB_METADATA_DB) {
    $env:VMLAB_METADATA_DB = "artifacts/vision_model_lab.sqlite3"
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "artifacts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "artifacts/object-store") | Out-Null

$venvPython = Join-Path $Root ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[setup] Creating .venv..."
    python -m venv .venv
}

if (-not $SkipInstall) {
    Write-Host "[setup] Installing Python dependencies..."
    & $venvPython -m pip install -e ".[dev]"
}

if (-not $SkipFrontendBuild) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location (Join-Path $Root "frontend")
        try {
            if (-not (Test-Path -LiteralPath "node_modules")) {
                Write-Host "[setup] Installing frontend dependencies..."
                npm ci
            }
            Write-Host "[setup] Building frontend..."
            npm run build
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Host "[warn] npm not found; skipping frontend build. Existing frontend/dist will be used if present."
    }
}

Write-Host "[setup] Initializing metadata storage..."
& $venvPython -m vision_model_lab.cli storage migrate --uri $env:VMLAB_METADATA_DB | Out-Host

Write-Host ""
Write-Host "Vision Model Lab is starting..."
Write-Host "Management UI: http://$HostName`:$Port/"
Write-Host "OpenAPI:       http://$HostName`:$Port/docs"
Write-Host "Health:        http://$HostName`:$Port/health"
Write-Host ""

& $venvPython scripts/serve_api.py --host $HostName --port $Port --metadata-db $env:VMLAB_METADATA_DB
