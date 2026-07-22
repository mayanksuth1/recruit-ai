@echo off
rem ============================================================
rem  Recruit AI - one-command launcher
rem  Starts the backend (port 8000) and frontend (port 5173)
rem  in their own windows, then opens the app in your browser.
rem ============================================================
set ROOT=%~dp0

rem Free port 8000 if a stale backend is still holding it
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

start "Recruit AI - Backend (close to stop)" cmd /k "cd /d %ROOT%backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000"
start "Recruit AI - Frontend (close to stop)" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo Starting Recruit AI... the app will open in your browser shortly.
powershell -NoProfile -Command "Start-Sleep 6" >nul 2>&1
start http://localhost:5173
