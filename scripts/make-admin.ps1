<#
  Recruit AI — make an existing account the platform admin.

      .\scripts\make-admin.ps1 -Email you@example.com

  Sign up in the app FIRST, then run this. It looks the account up by email,
  writes its user id into backend\.env as PLATFORM_ADMIN_USER_IDS, and tells
  you to restart the backend. The admin is pinned by id, not email: while
  email verification is off anyone can register any address, but nobody can
  take over an existing account's id.
#>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Email)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root 'backend\.env'
if (-not (Test-Path $envFile)) { Write-Host "No backend\.env found." -ForegroundColor Red; exit 1 }

$envText = Get-Content $envFile -Raw
$url = ([regex]::Match($envText, '(?m)^SUPABASE_URL=(.+)$')).Groups[1].Value.Trim()
$key = ([regex]::Match($envText, '(?m)^SUPABASE_SECRET_KEY=(.+)$')).Groups[1].Value.Trim()
if (-not $url -or -not $key) { Write-Host "SUPABASE_URL / SUPABASE_SECRET_KEY missing in backend\.env" -ForegroundColor Red; exit 1 }

$headers = @{ apikey = $key; Authorization = "Bearer $key" }
$match = $null
$page = 1
do {
    $resp = Invoke-RestMethod -Uri "$url/auth/v1/admin/users?page=$page&per_page=1000" -Headers $headers
    $match = $resp.users | Where-Object { $_.email -ieq $Email } | Select-Object -First 1
    $page++
} while (-not $match -and $resp.users.Count -eq 1000)

if (-not $match) {
    Write-Host "No account with email $Email. Sign up in the app first, then re-run." -ForegroundColor Yellow
    exit 1
}

$line = "PLATFORM_ADMIN_USER_IDS=$($match.id)"
if ($envText -match '(?m)^PLATFORM_ADMIN_USER_IDS=.*$') {
    $envText = [regex]::Replace($envText, '(?m)^PLATFORM_ADMIN_USER_IDS=.*$', $line)
} else {
    $envText = $envText.TrimEnd() + "`r`n`r`n# Platform admin (by user id - see scripts/make-admin.ps1)`r`n$line`r`n"
}
# WriteAllText: no BOM, which python-dotenv would otherwise glue onto the first key.
[IO.File]::WriteAllText($envFile, $envText)
Write-Host "  + $Email is now the platform admin." -ForegroundColor Green
Write-Host "  Restart the backend, sign in, and an 'Admin' link appears in the header."
