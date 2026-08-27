<#
  Recruit AI — self-hosted launcher.

  Brings the whole product up on this machine and, optionally, puts it on the
  internet through a Cloudflare tunnel.

      .\selfhost.ps1              # local only, http://localhost:8000
      .\selfhost.ps1 -Public      # also opens a public URL

  What it starts, in order:
    1. The local Supabase stack (Docker) — skipped if already running.
    2. The FastAPI backend, which in this mode also serves the built frontend
       and reverse-proxies /supabase. One process, one port, one origin.
    3. cloudflared, when -Public is given.

  Rebuild the frontend after changing anything under frontend/src:
      cd frontend; npm run build
#>
[CmdletBinding()]
param(
    [switch]$Public,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Info($m) { Write-Host "  $m" }
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

Write-Host "`nRecruit AI - self-hosted`n"

# --- 1. Docker + Supabase -------------------------------------------------
Write-Host "Database"
try { docker version --format '{{.Server.Version}}' | Out-Null } catch {
    Fail "Docker is not running. Start Docker Desktop, then re-run this script.
    If it crash-loops on startup, rename these two folders aside and try again:
      `$env:LOCALAPPDATA\Docker\run
      `$env:LOCALAPPDATA\docker-secrets-engine"
}

$dbUp = (docker ps --filter 'name=supabase_db_recruit-ai' --format '{{.Names}}') -ne $null
if ($dbUp) {
    Ok "Supabase already running"
} else {
    Info "starting Supabase (first run pulls images and takes a few minutes)..."
    Push-Location $root
    try { npx supabase start | Out-Null } finally { Pop-Location }
    Ok "Supabase started"
}

# --- 2. The frontend build ------------------------------------------------
Write-Host "`nFrontend"
$dist = Join-Path $root 'frontend\dist\index.html'
if (Test-Path $dist) {
    Ok "build present ($(Split-Path (Split-Path $dist) -Leaf)/)"
} else {
    Warn "no build found - building now"
    Push-Location (Join-Path $root 'frontend')
    try { npm run build | Out-Null } finally { Pop-Location }
    Ok "built"
}

# --- 3. Backend -----------------------------------------------------------
Write-Host "`nBackend"
# A stale process on the port would make the new one fail silently.
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Warn "port $Port is in use - stopping the process holding it"
    $busy | Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { Fail "No virtualenv at $python. Run setup.bat first." }

Start-Process -FilePath $python `
    -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port',$Port `
    -WorkingDirectory (Join-Path $root 'backend') `
    -WindowStyle Minimized

# Poll rather than sleep a fixed guess: startup time varies with disk cache.
$healthy = $false
foreach ($i in 1..30) {
    Start-Sleep -Milliseconds 700
    try {
        if ((Invoke-WebRequest "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) {
            $healthy = $true; break
        }
    } catch { }
}
if (-not $healthy) { Fail "The backend did not become healthy. Check the minimized uvicorn window." }
Ok "backend healthy on port $Port (serving the frontend and proxying /supabase)"

Write-Host "`n  Local:  http://localhost:$Port" -ForegroundColor Cyan

# --- 4. Public tunnel -----------------------------------------------------
if ($Public) {
    Write-Host "`nPublic URL"
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        Warn "cloudflared is not installed. Install it with:"
        Info "    winget install Cloudflare.cloudflared"
        Info "then re-run with -Public."
    } else {
        Info "opening a Cloudflare quick tunnel..."
        Info "The URL is printed in the cloudflared window that opens."
        Warn "A quick tunnel's URL CHANGES every restart. For a URL that stays put"
        Info "you need a domain on Cloudflare and a named tunnel."
        Start-Process -FilePath $cf.Source `
            -ArgumentList 'tunnel','--url',"http://localhost:$Port"
    }
}

Write-Host "`n  Leave this machine on and awake - it IS the server now.`n"
