@echo off
REM ============================================================================
REM  ESGenuine - local development launcher (Windows)
REM
REM  Runs the FastAPI backend (:8000) and the Vite frontend (:8080) in THIS ONE
REM  console. Every log line is tagged [backend ] / [frontend] so a single window
REM  tells the whole story, and Ctrl+C asks "Terminate ESGenuine (Y/N)?" - Y stops
REM  both servers (whole process tree), N leaves them running.
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
REM  WHY THE ACTUAL RUNNING LIVES IN scripts\dev-run.ps1
REM  Batch cannot read a child process's pipe line-by-line without blocking, so
REM  cmd alone cannot interleave two servers into one window - which is exactly
REM  why this used to open a separate console per server. PowerShell can, and it
REM  can also take Ctrl+C as input instead of as a signal, which is what makes the
REM  (Y/N) prompt possible at all.
REM
REM  WHY THE BACKEND RUNS AS  .venv\Scripts\python.exe -m uvicorn
REM  (verified 2026-08-09, both alternatives were tried and rejected):
REM    * bare `uvicorn` - the venv console-script .exe shim exits rc=1 with no
REM      output here. Those shims hardcode an absolute interpreter path at install
REM      time, so they break if the venv or repo folder is ever moved/renamed.
REM    * bare `python` on PATH - resolved to a DIFFERENT interpreter (uvicorn
REM      0.40.0) than the venv (0.41.0), i.e. the app would run against the wrong
REM      environment. Prepending the venv to PATH did not reliably win.
REM ============================================================================

setlocal
set "ROOT=%~dp0"
REM Strip the trailing backslash before this is passed as a quoted argument: a
REM path ending in \" escapes the quote in .NET's command-line parser, which would
REM swallow the next argument.
set "ROOTARG=%ROOT:~0,-1%"
set "VENV=%ROOT%.venv"
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=both"

set "NOBROWSER="
if /i "%~2"=="/nobrowser" set "NOBROWSER=-NoBrowser"

echo(
echo  ESGenuine - starting [%TARGET%]
echo  %ROOT%
echo(

REM ---- preflight -------------------------------------------------------------
if /i not "%TARGET%"=="both" if /i not "%TARGET%"=="backend" if /i not "%TARGET%"=="frontend" (
    echo  [X] Unknown target "%TARGET%" - expected: both ^| backend ^| frontend
    goto :fail
)

if /i not "%TARGET%"=="frontend" (
    if not exist "%VENV%\Scripts\python.exe" (
        echo  [X] No virtualenv at %VENV%
        echo      Create it, then install deps:
        echo        python -m venv .venv
        echo        .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
        goto :fail
    )
)

if not exist "%ROOT%scripts\dev-run.ps1" (
    echo  [X] Missing %ROOT%scripts\dev-run.ps1 - the launcher script is part of the repo.
    goto :fail
)

if not exist "%ROOT%.env" (
    echo  [!] No .env at the repo root.
    echo      Backend Supabase reads and frontend config will fail.
    echo      Copy .env.example to .env and fill it in.
    echo(
)

REM Convenience only, for anything the spawned servers shell out to.
set "PATH=%VENV%\Scripts;%PATH%"

if /i not "%TARGET%"=="backend" (
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
)

if /i not "%TARGET%"=="frontend" call :warn_port 8000 backend
if /i not "%TARGET%"=="backend"  call :warn_port 8080 frontend

REM ---- run both servers in this window ---------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\dev-run.ps1" -Root "%ROOTARG%" -Target %TARGET% %NOBROWSER%
if errorlevel 1 goto :fail

endlocal
exit /b 0

REM ---- helpers ---------------------------------------------------------------
:warn_port
REM %1 = port, %2 = label. Warns instead of failing: an already-running instance
REM is a normal case, and the server will report the bind error itself.
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
