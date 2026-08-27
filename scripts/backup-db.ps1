<#
  Recruit AI — database backup.

      .\scripts\backup-db.ps1                 # take a backup
      .\scripts\backup-db.ps1 -List           # show what exists
      .\scripts\backup-db.ps1 -Verify <file>  # check one archive is restorable

  Self-hosting means there is no managed snapshot behind this database. If the
  disk dies, or a migration goes wrong, this directory is the only way back.

  WHERE IT WRITES, AND WHY IT MATTERS
  C:\Users\jamba is itself a git repository whose remote is a PUBLIC GitHub
  repo. A dump written anywhere under the home directory would sit there as an
  untracked file containing every candidate record and every auth user, one
  `git add -A` away from being published. So backups are written OUTSIDE the
  home directory by default. Do not "tidy" them into the project folder.

  WHAT IT DUMPS
  public (all your application data) and auth (the user accounts). Restoring
  public without auth would give you data nobody can log in to reach. Supabase's
  other internal schemas are recreated by `supabase start`, so they are noise
  here and are skipped.

  Custom format (-Fc): compressed, and pg_restore can then restore selectively
  — one table, or data-only — instead of forcing all-or-nothing.
#>
[CmdletBinding()]
param(
    [string]$OutDir = 'C:\recruit-ai-backups',
    [string]$Container = 'supabase_db_recruit-ai',
    [int]$KeepDays = 14,
    # Where to mirror backups off this disk. Empty means auto-detect (see
    # Resolve-Offsite). Pass -OffsiteDir '' -NoOffsite to skip entirely.
    [string]$OffsiteDir,
    [int]$OffsiteKeepDays = 60,
    [switch]$NoOffsite,
    [switch]$List,
    [string]$Verify
)

# NOT 'Stop': in Windows PowerShell 5.1 a native command writing to stderr
# raises NativeCommandError, so an ordinary pg_dump notice would abort a
# perfectly good backup. Every failure below is checked explicitly instead.
$ErrorActionPreference = 'Continue'
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Info($m) { Write-Host "    $m" }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

# ---- list ---------------------------------------------------------------
if ($List) {
    if (-not (Test-Path $OutDir)) { Fail "No backup directory at $OutDir" }
    $files = Get-ChildItem $OutDir -Filter '*.dump' | Sort-Object LastWriteTime -Descending
    if (-not $files) { Warn "No backups yet in $OutDir"; exit 0 }
    Write-Host "`n  Backups in $OutDir`n"
    $files | ForEach-Object {
        '    {0}  {1,8:N2} MB  {2}' -f $_.Name, ($_.Length / 1MB), $_.LastWriteTime
    }
    $total = ($files | Measure-Object Length -Sum).Sum / 1MB
    Write-Host ("`n    {0} backups, {1:N1} MB total`n" -f $files.Count, $total)
    exit 0
}

# ---- verify -------------------------------------------------------------
if ($Verify) {
    if (-not (Test-Path $Verify)) { Fail "No such file: $Verify" }
    $name = Split-Path $Verify -Leaf
    # Read the archive's table of contents. A truncated or corrupt dump fails
    # here, which is the whole point: an unverified backup is a guess.
    docker cp "$Verify" "${Container}:/tmp/verify.dump" | Out-Null
    $toc = docker exec $Container pg_restore --list /tmp/verify.dump 2>&1
    docker exec $Container rm -f /tmp/verify.dump | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "$name is NOT restorable:`n$toc" }
    $tables = ($toc | Select-String -Pattern 'TABLE DATA').Count
    Ok "$name is readable by pg_restore ($tables tables with data)"
    exit 0
}

# ---- back up ------------------------------------------------------------
Write-Host "`nRecruit AI - database backup`n"

$running = docker ps --filter "name=$Container" --format '{{.Names}}'
if (-not $running) { Fail "Container $Container is not running. Start Supabase first." }

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

# Sortable, filename-safe, unambiguous. Local time is fine — this is one machine.
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$name  = "recruit-ai_$stamp.dump"
$dest  = Join-Path $OutDir $name

Info "dumping public + auth ..."
# Dump to a path inside the container, then copy out: piping binary through
# PowerShell's stdout mangles it (encoding + CRLF translation) and produces an
# archive that looks fine until the day you try to restore it.
docker exec $Container pg_dump -U postgres -d postgres `
    --schema=public --schema=auth `
    --format=custom --compress=6 --file=/tmp/backup.dump 2>&1 | Out-String | Write-Verbose
if ($LASTEXITCODE -ne 0) { Fail "pg_dump failed (exit $LASTEXITCODE)" }

docker cp "${Container}:/tmp/backup.dump" "$dest" | Out-Null
docker exec $Container rm -f /tmp/backup.dump | Out-Null

if (-not (Test-Path $dest)) { Fail "The dump did not reach $dest" }
$sizeMB = (Get-Item $dest).Length / 1MB
if ((Get-Item $dest).Length -lt 1024) { Fail "The dump is only $((Get-Item $dest).Length) bytes - treat it as failed." }
Ok ("wrote $name ({0:N2} MB)" -f $sizeMB)

# ---- verify what we just wrote -----------------------------------------
# A backup you have never read back is a hope, not a backup. This costs a
# second and catches a silently broken dump on the day it breaks rather than
# on the day you need it.
docker cp "$dest" "${Container}:/tmp/verify.dump" | Out-Null
$toc = docker exec $Container pg_restore --list /tmp/verify.dump 2>&1
docker exec $Container rm -f /tmp/verify.dump | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "The dump is not restorable - investigate now:`n$toc" }

$tableCount = ($toc | Select-String -Pattern 'TABLE DATA').Count
if ($tableCount -lt 1) { Fail "The dump contains no table data at all." }
Ok "verified restorable ($tableCount tables with data)"

# ---- offsite copy -------------------------------------------------------
# Backups on the same disk as the database survive a bad migration but not a
# dead drive, a theft, or ransomware. This mirrors them somewhere else.
function Resolve-Offsite {
    if ($NoOffsite) { return $null }
    # NOT $PSBoundParameters: inside a function that refers to the FUNCTION's
    # bound parameters, which are none, so an explicit -OffsiteDir was silently
    # ignored and auto-detection ran anyway. Test the variable directly.
    if ($OffsiteDir) { return $OffsiteDir }
    # Google Drive for Desktop mounts as a drive letter (G: by default) and
    # streams rather than duplicating everything locally, so it is both the
    # first choice and — being outside the home directory — the safe one.
    foreach ($root in @('G:\My Drive', 'H:\My Drive', "$env:USERPROFILE\Google Drive")) {
        if (Test-Path $root) { return (Join-Path $root 'recruit-ai-backups') }
    }
    # OneDrive is deliberately NOT auto-selected. Its folder lives inside the
    # home directory, which is a git repo with a public remote — that is a
    # decision to make on purpose, with a .gitignore entry in place, not a
    # default that quietly starts mirroring candidate data into a repo.
    # Opt in with: -OffsiteDir (Join-Path $env:OneDrive 'recruit-ai-backups')
    return $null
}

$offsite = Resolve-Offsite
if ($NoOffsite) {
    Info "offsite copy skipped (-NoOffsite)"
} elseif (-not $offsite) {
    Warn "no offsite destination - these backups exist on one disk only"
    Info "Install Google Drive for Desktop and sign in; this picks it up automatically."
    Info "Or pass -OffsiteDir 'D:\wherever'. Use -NoOffsite to silence this."
} else {
    # The same trap as the local directory: anything under the home folder sits
    # inside a git repo whose remote is public.
    $home_ = [IO.Path]::GetFullPath($env:USERPROFILE)
    $full  = [IO.Path]::GetFullPath($offsite)
    if ($full.StartsWith($home_, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path (Join-Path $env:USERPROFILE '.git'))) {
        Warn "$offsite is inside $env:USERPROFILE, which is a git repo with a PUBLIC remote."
        Info "Add this line to $env:USERPROFILE\.gitignore before relying on it:"
        Info "    $((Split-Path $offsite -Leaf))/"
    }

    try {
        if (-not (Test-Path $offsite)) { New-Item -ItemType Directory -Path $offsite -Force | Out-Null }
        $mirror = Join-Path $offsite $name
        Copy-Item -Path $dest -Destination $mirror -Force

        # Compare sizes: a sync client that is mid-upload, out of quota, or
        # simply offline can leave a truncated file that looks present.
        $srcLen = (Get-Item $dest).Length
        $dstLen = (Get-Item $mirror).Length
        if ($srcLen -ne $dstLen) { throw "copied $dstLen bytes but the source is $srcLen" }
        Ok "mirrored to $offsite"

        $ocut = (Get-Date).AddDays(-$OffsiteKeepDays)
        $oold = Get-ChildItem $offsite -Filter '*.dump' | Where-Object { $_.LastWriteTime -lt $ocut }
        if ($oold -and ((Get-ChildItem $offsite -Filter '*.dump').Count - $oold.Count) -ge 1) {
            $oold | Remove-Item -Force
            Ok "rotated $($oold.Count) offsite backup(s) older than $OffsiteKeepDays days"
        }
    } catch {
        # A failed mirror must not fail the backup: the local copy is already
        # written and verified, and that is the more important of the two.
        Warn "offsite copy to $offsite failed: $($_.Exception.Message)"
        Info "The local backup is fine. Fix the destination and re-run."
    }
}

# ---- rotate -------------------------------------------------------------
$cutoff = (Get-Date).AddDays(-$KeepDays)
$old = Get-ChildItem $OutDir -Filter '*.dump' | Where-Object { $_.LastWriteTime -lt $cutoff }
# Never let rotation empty the directory: if every file is old because nothing
# has run in a month, deleting them all would leave zero backups.
$keep = (Get-ChildItem $OutDir -Filter '*.dump').Count - $old.Count
if ($old -and $keep -ge 1) {
    $old | Remove-Item -Force
    Ok "rotated out $($old.Count) backup(s) older than $KeepDays days"
} elseif ($old) {
    Warn "skipped rotation - it would have left no backups at all"
}

$all = Get-ChildItem $OutDir -Filter '*.dump'
Write-Host ("`n  {0} backups in {1} ({2:N1} MB)`n" -f $all.Count, $OutDir, (($all | Measure-Object Length -Sum).Sum / 1MB))
