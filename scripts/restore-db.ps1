<#
  Recruit AI — restore a database backup.

      .\scripts\restore-db.ps1 -Drill                  # rehearse into a scratch DB (safe)
      .\scripts\restore-db.ps1 -File <path> -Drill     # rehearse a specific archive
      .\scripts\restore-db.ps1 -File <path> -Confirm   # REAL restore over live data

  Defaults to the newest backup in C:\recruit-ai-backups.

  WHY THIS SCRIPT EXISTS RATHER THAN A ONE-LINE pg_restore
  A dump of `public` + `auth` is not self-sufficient. public.ai_embeddings has
  a vector(1024) column, and `vector` lives in the `extensions` schema, which
  is not part of those two schemas. Restore the dump into a bare database and
  Postgres cannot create that one table — every other table restores fine, the
  row counts on everything you happen to spot-check match, and you conclude the
  restore worked. It did not: you silently lost a table.

  Extensions are installed into a database, not carried inside a dump. So this
  script creates the `extensions` schema and installs `vector` and `pgcrypto`
  BEFORE restoring, then verifies the table count against what was expected.

  Found by running an actual restore drill. A backup nobody has restored is a
  hope, and this is the specific way this one was broken.
#>
[CmdletBinding()]
param(
    [string]$File,
    [string]$OutDir = 'C:\recruit-ai-backups',
    [string]$Container = 'supabase_db_recruit-ai',
    [string]$Target = 'postgres',
    [switch]$Drill,
    [switch]$Confirm
)

# NOT 'Stop': in Windows PowerShell 5.1 any line a native command writes to
# stderr is wrapped in a NativeCommandError, so a harmless psql NOTICE would
# abort the script. Failures are detected explicitly via $LASTEXITCODE and the
# verification checks at the end instead.
$ErrorActionPreference = 'Continue'
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Info($m) { Write-Host "    $m" }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

$running = docker ps --filter "name=$Container" --format '{{.Names}}'
if (-not $running) { Fail "Container $Container is not running. Start Supabase first." }

if (-not $File) {
    $newest = Get-ChildItem $OutDir -Filter '*.dump' -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $newest) { Fail "No backups found in $OutDir" }
    $File = $newest.FullName
}
if (-not (Test-Path $File)) { Fail "No such file: $File" }

if (-not $Drill -and -not $Confirm) {
    Warn "Refusing to restore over live data without -Confirm."
    Info "Rehearse first:  .\scripts\restore-db.ps1 -Drill"
    Info "Then, if you really mean it:  .\scripts\restore-db.ps1 -File '$File' -Confirm"
    exit 1
}

$db = if ($Drill) { 'restore_drill' } else { $Target }

Write-Host "`nRestoring $(Split-Path $File -Leaf) -> database '$db'`n"

if ($Drill) {
    Info "creating a scratch database (live data is not touched)"
    # PGOPTIONS rather than an inline SET: DROP DATABASE cannot run inside a
    # transaction block, and psql wraps a multi-statement -c in one.
    docker exec -e PGOPTIONS="-c client_min_messages=warning" $Container `
        psql -U postgres -d postgres -q -c "drop database if exists $db;" | Out-Null
    docker exec $Container psql -U postgres -d postgres -q `
        -c "create database $db;" | Out-Null
} else {
    Warn "This writes over the LIVE database '$db'. Ctrl+C now if that is not what you want."
    Start-Sleep -Seconds 5
}

# The prerequisites a dump of public+auth cannot carry. Without these,
# ai_embeddings fails to create and the loss is silent.
Info "installing extension prerequisites (extensions schema, vector, pgcrypto)"
docker exec -e PGOPTIONS="-c client_min_messages=warning" $Container psql -U postgres -d $db -q -c @"
create schema if not exists extensions;
create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;
"@ | Out-Null

docker cp "$File" "${Container}:/tmp/restore.dump" | Out-Null
Info "restoring ..."
$out = docker exec $Container pg_restore -U postgres -d $db --no-owner --no-acl /tmp/restore.dump 2>&1
docker exec $Container rm -f /tmp/restore.dump | Out-Null

# "already exists" is expected and harmless: the target has a public schema.
$real = $out | Select-String -Pattern '^pg_restore: error' | Where-Object { $_ -notmatch 'already exists' }
if ($real) {
    Warn "pg_restore reported $($real.Count) error(s):"
    $real | Select-Object -First 10 | ForEach-Object { Info $_.ToString() }
} else {
    Ok "restored with no errors"
}

# ---- prove it ------------------------------------------------------------
$tables = docker exec $Container psql -U postgres -d $db -tAc "select count(*) from pg_tables where schemaname='public';"
$tables = [int]($tables -replace '\s','')
if ($tables -lt 19) {
    Fail "Only $tables tables in public - expected 19. The restore is INCOMPLETE."
}
Ok "$tables tables in public"

$counts = docker exec $Container psql -U postgres -d $db -tAc @"
select 'organizations=' || (select count(*) from public.organizations)
    || '  candidates='  || (select count(*) from public.candidates)
    || '  roles='       || (select count(*) from public.roles)
    || '  auth.users='  || (select count(*) from auth.users)
    || '  ai_embeddings=' || (select count(*) from public.ai_embeddings);
"@
Ok "data: $($counts -replace '\s+',' ')"

if ($Drill) {
    Write-Host "`n  Drill complete. The scratch database '$db' is left in place so you can"
    Write-Host "  inspect it. Remove it with:"
    Write-Host "    docker exec $Container psql -U postgres -d postgres -c 'drop database $db;'`n"
} else {
    Write-Host "`n  Restore complete. Restart the backend so it drops any cached state.`n"
}
