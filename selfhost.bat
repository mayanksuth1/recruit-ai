@echo off
rem ============================================================
rem  Recruit AI - self-hosted launcher (double-click me)
rem
rem  Windows blocks .ps1 files by default (execution policy
rem  "Restricted"), so running selfhost.ps1 directly fails with
rem  "running scripts is disabled on this system".
rem
rem  -ExecutionPolicy Bypass applies to THIS ONE invocation only.
rem  It changes no system setting and leaves the machine's policy
rem  exactly as it was - which is why this is preferable to
rem  loosening the policy globally.
rem
rem    selfhost.bat            local only
rem    selfhost.bat -Public    also open a public URL
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0selfhost.ps1" %*
