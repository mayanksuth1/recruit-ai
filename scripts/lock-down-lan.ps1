<#
  Recruit AI - block the local Supabase ports from the local network.

  WHY: `supabase start` publishes its ports on 0.0.0.0 (every network
  interface), so anyone on the same Wi-Fi / LAN can reach:
    54421  API gateway  - serves /pg and /mcp with NO key = full DB takeover
    54422  Postgres     - postgres / postgres
    54423  Studio       - the database UI
  The public internet tunnel only exposes the backend on 8000, so this is a
  LAN risk, not an internet one - but a cafe, office or shared home network
  is enough. This rule blocks inbound connections to 54420-54429 from other
  machines while leaving the app (which talks to them over loopback) working.

  Windows Firewall applies BLOCK before ALLOW, so this overrides the
  inbound allow Docker Desktop adds for itself.

  RUN AS ADMINISTRATOR:
    Right-click -> Run with PowerShell (accept the elevation prompt), or
    from an elevated PowerShell:  powershell -File scripts\lock-down-lan.ps1
  Remove it later with:          .\scripts\lock-down-lan.ps1 -Remove
#>
[CmdletBinding()]
param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$name = 'Recruit AI - block Supabase ports from LAN'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "This must run as Administrator. Right-click the file -> Run with PowerShell, or open an elevated PowerShell and run it again." -ForegroundColor Red
    exit 1
}

Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if ($Remove) { Write-Host "  Removed: $name" -ForegroundColor Green; exit 0 }

# Loopback is exempt automatically: Windows never applies firewall rules to
# traffic that stays on 127.0.0.1 / ::1, so the app keeps working.
New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Block `
    -Protocol TCP -LocalPort 54420-54429 -Profile Any -RemoteAddress Any | Out-Null

Write-Host "  + Blocked inbound TCP 54420-54429 from the network." -ForegroundColor Green
Write-Host "    The app still reaches Supabase over loopback. Re-run with -Remove to undo."
