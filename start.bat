@echo off
REM ============================================================================
REM  ESGenuine - local development launcher (Windows)
REM
REM  Starts the FastAPI backend (:8000) and the Vite frontend (:8080), each in
REM  its own console window so their logs stay readable and either can be
REM  stopped with Ctrl+C independently.
REM
REM  Usage:
REM    start.bat              both backend and frontend (default)
REM    start.bat backend      backend only
REM    start.bat frontend     frontend only
REM    start.bat both /nobrowser    skip opening the browser
REM
REM  Safe to run from anywhere - it resolves paths from its own location, so a
REM  desktop shortcut works.
REM
REM  WHY THE BACKEND IS LAUNCHED AS  ..\.venv\Scripts\python.exe -m uvicorn
REM  (verified 2026-08-09, both alternatives were tried and rejected):
REM    * bare `uvicorn` - the venv console-script .exe shim exits rc=1 with no
REM      output here. Those shims hardcode an absolute interpreter path at install
REM      time, so they break if the venv or repo folder is ever moved/renamed.
REM    * bare `python` on PATH - resolved to a DIFFERENT interpreter (uvicorn
REM      0.40.0) than the venv (0.41.0), i.e. the app would run against the wrong
REM      environment. Prepending the venv to PATH did not reliably win.
REM  The RELATIVE path from backend\ contains no spaces even though the absolute
REM  repo path does ("Pharos Integrity"), so it needs no quoting - which also
REM  keeps the `cmd /k` argument free of nested quotes that cmd parses badly.
REM  PATH still gets the venv prepended for interactive convenience in the spawned
REM  window (pip, python), but the launch command does NOT depend on it.
REM ============================================================================

setlocal
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=both"

echo(
echo  ESGenuine - starting [%TARGET%]
echo  %ROOT%
echo(

REM ---- preflight -------------------------------------------------------------
if not exist "%VENV%\Scripts\python.exe" (
    echo  [X] No virtualenv at %VENV%
    echo      Create it, then install deps:
    echo        python -m venv .venv
    echo        .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    goto :fail
)

if not exist "%ROOT%.env" (
    echo  [!] No .env at the repo root.
    echo      Backend Supabase reads and frontend config will fail.
    echo      Copy .env.example to .env and fill it in.
    echo(
)

REM Convenience only (pip/python inside the spawned window). The backend launch
REM below uses an explicit relative interpreter path and does NOT rely on this -
REM see the header note: bare `python` here resolved to the wrong interpreter.
set "PATH=%VENV%\Scripts;%PATH%"

REM ---- backend ---------------------------------------------------------------
if /i "%TARGET%"=="frontend" goto :frontend

call :warn_port 8000 backend
echo  [1] backend  -^> http://localhost:8000        (docs: /docs, health: /health)
start "ESGenuine Backend :8000" /d "%ROOT%backend" cmd /k ..\.venv\Scripts\python.exe -m uvicorn src.api.server:app --reload --port 8000

if /i "%TARGET%"=="backend" goto :done

:frontend
REM ---- frontend --------------------------------------------------------------
if not exist "%ROOT%frontend\node_modules" (
    echo  [i] frontend\node_modules missing - running npm install (one time^)...
    pushd "%ROOT%frontend"
    call npm install
    if errorlevel 1 (
        popd
        echo  [X] npm install failed.
        goto :fail
    )
    popd
)

call :warn_port 8080 frontend
echo  [2] frontend -^> http://localhost:8080
start "ESGenuine Frontend :8080" /d "%ROOT%frontend" cmd /k npm run dev

REM ---- open the app ----------------------------------------------------------
if /i "%~2"=="/nobrowser" goto :done
if /i "%TARGET%"=="backend" goto :done
echo(
echo  Waiting for Vite to come up...
timeout /t 8 /nobreak >nul
start "" http://localhost:8080

:done
echo(
echo  Launched. Close the spawned windows (or Ctrl+C in them^) to stop.
echo(
endlocal
exit /b 0

REM ---- helpers ---------------------------------------------------------------
:warn_port
REM %1 = port, %2 = label. Warns instead of failing: an already-running instance
REM is a normal case, and the new window will report the bind error itself.
netstat -ano -p tcp | findstr /r /c:"LISTENING" | findstr /c:":%~1 " >nul 2>&1
if not errorlevel 1 (
    echo  [!] Port %~1 already in use - the %~2 may already be running.
)
goto :eof

:fail
echo(
pause
endlocal
exit /b 1
