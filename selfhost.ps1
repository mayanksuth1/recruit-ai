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
    [int]$Port = 8000,
    # On a cold boot Docker Desktop takes a minute or two to accept
    # connections. Anything launched at logon must wait rather than fail.
    [int]$WaitForDockerMinutes = 0
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
# Where the current public hostname is recorded, so it survives the console
# window that printed it.
$urlFile = Join-Path $root '.public-url.txt'

function Info($m) { Write-Host "  $m" }
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

Write-Host "`nRecruit AI - self-hosted`n"

# --- 1. Docker + Supabase -------------------------------------------------
Write-Host "Database"
$dockerUp = $false
$deadline = (Get-Date).AddMinutes([Math]::Max($WaitForDockerMinutes, 0))
do {
    try { docker version --format '{{.Server.Version}}' 2>$null | Out-Null; $dockerUp = ($LASTEXITCODE -eq 0) } catch { $dockerUp = $false }
    if (-not $dockerUp -and (Get-Date) -lt $deadline) {
        Info 'waiting for Docker to accept connections...'
        Start-Sleep -Seconds 15
    }
} while (-not $dockerUp -and (Get-Date) -lt $deadline)

if (-not $dockerUp) {
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
    # Not just Get-Command: winget writes cloudflared to the MACHINE PATH, and
    # a shell started before that (or a service session) still has the old one.
    # Fall back to the known install locations rather than claiming it is missing.
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        foreach ($p in @("$env:ProgramFiles\cloudflared\cloudflared.exe",
                         "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
                         "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe")) {
            if (Test-Path $p) { $cf = [pscustomobject]@{ Source = $p }; break }
        }
    }
    if (-not $cf) {
        Warn "cloudflared is not installed. Install it with:"
        Info "    winget install Cloudflare.cloudflared"
        Info "then re-run with -Public."
    } elseif (Get-Process cloudflared -ErrorAction SilentlyContinue) {
        Warn "cloudflared is already running - leaving it alone"
        if (Test-Path $urlFile) { Info "current URL: $(Get-Content $urlFile -Raw)".Trim() }
        Info "Kill it first if you want a fresh tunnel: Stop-Process -Name cloudflared"
    } else {
        # cloudflared prints the assigned hostname to stderr and nowhere else.
        # A quick tunnel gets a NEW name every start, so it has to be captured
        # and written down - otherwise after a reboot the app is up and running
        # at an address nobody knows.
        $log = Join-Path $root '.cloudflared.log'
        Remove-Item $log -ErrorAction SilentlyContinue
        # Two traps avoided here.
        #
        # 1. Start-Process's own -RedirectStandardError keeps the stream handles
        #    open in THIS process, so PowerShell never exits and the launcher
        #    hangs forever - the app is up but your terminal never returns.
        # 2. Passing the redirection inline via `cmd /c "..."` looks like the
        #    fix, but cmd's nested-quote parsing mangles a quoted exe path plus
        #    a quoted redirect target, and the process silently never starts.
        #
        # A generated .cmd file sidesteps both: it owns its quoting, and we hold
        # no handles on it.
        $runner = Join-Path $root '.run-tunnel.cmd'
        Set-Content -Path $runner -Encoding ascii -Value @(
            '@echo off',
            ('"{0}" tunnel --url http://localhost:{1} > "{2}" 2>&1' -f $cf.Source, $Port, $log)
        )
        Start-Process -FilePath $runner -WindowStyle Hidden

        Info "waiting for Cloudflare to assign a hostname..."
        $url = $null
        foreach ($i in 1..40) {
            Start-Sleep -Milliseconds 750
            if (Test-Path $log) {
                $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue
                if ($m) { $url = $m.Matches[0].Value; break }
            }
        }

        if ($url) {
            # WriteAllText, not Set-Content -Encoding utf8: PowerShell 5.1 writes a
            # UTF-8 BOM, and anything reading this file naively (curl $(cat ...),
            # a shell script, another language) gets three invisible bytes glued to
            # the front of the hostname.
            [IO.File]::WriteAllText($urlFile, $url)
            Ok "public URL assigned"
            Write-Host "`n  Public: $url" -ForegroundColor Cyan
            Info "(also saved to $urlFile)"
            Warn "This URL CHANGES every time the tunnel restarts. A stable one needs"
            Info "a domain on Cloudflare and a named tunnel, or Tailscale Funnel."
        } else {
            Warn "cloudflared started but no hostname appeared within 30s."
            Info "Check $log"
        }
    }
}

Write-Host "`n  Leave this machine on and awake - it IS the server now.`n"
