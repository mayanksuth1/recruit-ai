@echo off
rem ============================================================
rem  Builds recruit-ai-client-package.zip on your Desktop:
rem  the complete folder to hand to a client, with a BLANK
rem  config.env and none of YOUR secrets or heavy folders.
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src = '%~dp0'; $stage = Join-Path $env:TEMP 'recruit-ai-package'; " ^
  "if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }; " ^
  "robocopy $src $stage /E /XD .git .venv node_modules dist __pycache__ /XF .env *.pyc | Out-Null; " ^
  "$zip = Join-Path ([Environment]::GetFolderPath('Desktop')) 'recruit-ai-client-package.zip'; " ^
  "if (Test-Path $zip) { Remove-Item $zip -Force }; " ^
  "Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip; " ^
  "Remove-Item $stage -Recurse -Force; " ^
  "Write-Host ('Client package created: ' + $zip) -ForegroundColor Green"
pause
