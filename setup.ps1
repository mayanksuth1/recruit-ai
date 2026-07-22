# Recruit AI — one-time setup. Reads config.env, generates the app's env
# files, installs dependencies, and prints the one manual database step.
param([string]$Root = $PSScriptRoot)

$ErrorActionPreference = "Stop"
function Fail($msg) { Write-Host "`n  SETUP STOPPED: $msg`n" -ForegroundColor Red; exit 1 }
function Ok($msg) { Write-Host "  [ok] $msg" -ForegroundColor Green }

Write-Host "`n=== Recruit AI setup ===`n"

# ---- 1. read config.env ---------------------------------------------------
$configPath = Join-Path $Root "config.env"
if (-not (Test-Path $configPath)) { Fail "config.env not found next to setup.bat" }
$config = @{}
foreach ($line in Get-Content $configPath) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    $i = $line.IndexOf('=')
    if ($i -lt 1) { continue }
    $config[$line.Substring(0, $i).Trim()] = $line.Substring($i + 1).Trim()
}

$required = @("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_PUBLISHABLE_KEY",
              "GEMINI_API_KEY", "RESEND_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")
$missing = $required | Where-Object { -not $config[$_] }
if ($missing) { Fail ("these keys are still empty in config.env: " + ($missing -join ", ")) }
Ok "config.env read — all required keys present"

# ---- 2. check prerequisites ----------------------------------------------
try { $py = (python --version) 2>&1 } catch { $py = $null }
if (-not $py -or $py -notmatch "Python 3") { Fail "Python 3.10+ is required — install from https://python.org (tick 'Add to PATH')" }
try { $node = (node --version) 2>&1 } catch { $node = $null }
if (-not $node) { Fail "Node.js 18+ is required — install from https://nodejs.org" }
Ok "prerequisites found ($py, node $node)"

# ---- 3. generate the app's env files -------------------------------------
@"
SUPABASE_URL=$($config['SUPABASE_URL'])
SUPABASE_SECRET_KEY=$($config['SUPABASE_SECRET_KEY'])
GEMINI_API_KEY=$($config['GEMINI_API_KEY'])
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite
RESEND_API_KEY=$($config['RESEND_API_KEY'])
EMAIL_FROM=$(if ($config['EMAIL_FROM']) { $config['EMAIL_FROM'] } else { 'Recruit AI <onboarding@resend.dev>' })
GOOGLE_CLIENT_ID=$($config['GOOGLE_CLIENT_ID'])
GOOGLE_CLIENT_SECRET=$($config['GOOGLE_CLIENT_SECRET'])
SCHEDULER_TIMEZONE=$(if ($config['SCHEDULER_TIMEZONE']) { $config['SCHEDULER_TIMEZONE'] } else { 'Asia/Kolkata' })
CORS_ORIGINS=http://localhost:5173
"@ | Out-File (Join-Path $Root "backend\.env") -Encoding utf8

@"
VITE_SUPABASE_URL=$($config['SUPABASE_URL'])
VITE_SUPABASE_ANON_KEY=$($config['SUPABASE_PUBLISHABLE_KEY'])
"@ | Out-File (Join-Path $Root "frontend\.env") -Encoding utf8
Ok "backend\.env and frontend\.env generated from config.env"

# ---- 4. install dependencies ---------------------------------------------
$venvPy = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "  installing backend dependencies (first run only)..."
    python -m venv (Join-Path $Root "backend\.venv")
    & $venvPy -m pip install -q -r (Join-Path $Root "backend\requirements.txt")
}
Ok "backend dependencies ready"
if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-Host "  installing frontend dependencies (first run only)..."
    Push-Location (Join-Path $Root "frontend"); npm install --no-fund --no-audit | Out-Null; Pop-Location
}
Ok "frontend dependencies ready"

# ---- 5. the one manual step ----------------------------------------------
Write-Host @"

=== Almost done — ONE manual step ===

  1. Open your Supabase project -> SQL Editor
  2. Open the file  setup-database.sql  (in this folder),
     copy ALL of it, paste into the SQL Editor, click RUN.
     (This creates the database tables. Run once only.)

  Then start the app any time with:   start.bat

"@ -ForegroundColor Yellow
