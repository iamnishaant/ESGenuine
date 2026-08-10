<#
  ESGenuine dev runner - backend (:8000) and frontend (:8080) in ONE console.

  Called by start.bat; not normally run by hand. It exists as a .ps1 because cmd
  cannot interleave two child processes' output into a single window: batch has no
  way to read a pipe line-by-line without blocking, so the old launcher had to
  `start` a separate console per server.

  WHAT THIS DOES DIFFERENTLY
    * Both servers are children of THIS console. Their stdout/stderr are redirected
      and pumped into one stream, each line tagged [backend ] / [frontend].
    * Ctrl+C is captured as INPUT (TreatControlCAsInput), not as a signal. That
      matters twice over: it lets us ask "Terminate (Y/N)?" and act on the answer,
      and it stops the console from broadcasting CTRL_C_EVENT to the servers behind
      our back - so a mis-typed Ctrl+C can be declined instead of half-killing the
      stack. The console mode is restored on the way out.
    * Shutdown walks the process TREE. `npm run dev` is cmd.exe -> node -> vite and
      uvicorn --reload is python -> python; killing only the direct child would
      orphan the servers and leave :8000/:8080 bound.

  KEEP THIS FILE PURE ASCII. Windows PowerShell 5.1 decodes a BOM-less .ps1 as
  CP1252, so a UTF-8 em dash arrives as the bytes 'a-tilde, euro, right-double-
  quote' - and PowerShell accepts a curly right-double-quote as a STRING TERMINATOR.
  One em dash in a comment therefore ended the next string literal early and the
  whole script died with "Unexpected token '}'" 30 lines later. Use '-', not a dash.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [ValidateSet('both', 'backend', 'frontend')][string]$Target = 'both',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- helpers ----

function Write-Tagged {
    param([string]$Label, [ConsoleColor]$Color, [string]$Text)
    Write-Host "[$Label] " -ForegroundColor $Color -NoNewline
    Write-Host $Text
}

function Stop-Tree {
    # Depth-first so children die before their parent reaps/reparents them.
    param([int]$ProcessId)
    try {
        $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue)
    } catch { $kids = @() }
    foreach ($kid in $kids) { Stop-Tree -ProcessId ([int]$kid.ProcessId) }
    try { Stop-Process -Id $ProcessId -Force -ErrorAction Stop } catch { }
}

function Stop-StrandedPort {
    <#
      Backstop for a server that broke its parent chain and survived Stop-Tree.
      Deliberately narrow: it only touches a listener on OUR port whose command
      line points into THIS repo, so someone else's app on 8080 is never killed.
    #>
    param([int]$Port, [string]$RepoRoot)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $conn) { return }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -and $proc.CommandLine.Contains($RepoRoot)) {
            Write-Host "  port $Port was still held by pid $($proc.ProcessId) - killing" -ForegroundColor DarkGray
            Stop-Tree -ProcessId ([int]$proc.ProcessId)
        }
    } catch { }
}

# ------------------------------------------------------------ definitions ----

$services = @()

if ($Target -ne 'frontend') {
    $services += [pscustomobject]@{
        Label     = 'backend '
        Color     = [ConsoleColor]::Cyan
        # Explicit venv interpreter, NOT bare `uvicorn`/`python` - see start.bat's
        # header for why both of those were tried and rejected.
        File      = (Join-Path $Root '.venv\Scripts\python.exe')
        Arguments = '-m uvicorn src.api.server:app --reload --port 8000'
        Dir       = (Join-Path $Root 'backend')
        Ready     = 'http://localhost:8000        (docs: /docs, health: /health)'
        Process   = $null
        Reported  = $false
    }
}

if ($Target -ne 'backend') {
    # Run Vite's entrypoint DIRECTLY rather than via `npm run dev`.
    #
    # `npm run dev` is cmd.exe -> node(npm-cli) -> cmd.exe -> node(vite), and the
    # middle links exit once they have handed off. Observed live: the surviving
    # `cmd /d /s /c vite` reported ParentProcessId 3076, a pid that no longer
    # existed - so walking live children down from our own child never reached the
    # process actually holding :8080, and shutdown left an orphan behind. Spawning
    # vite ourselves collapses that chain to a single, directly-killable child.
    # package.json's "dev" script is literally `vite`, so this runs the same thing.
    $viteEntry = Join-Path $Root 'frontend\node_modules\vite\bin\vite.js'
    if (Test-Path $viteEntry) {
        $frontFile = 'node.exe'                      # resolved from PATH
        $frontArgs = '"' + $viteEntry + '"'
    } else {
        # Unusual node_modules layout (pnpm store, partial install). Fall back to
        # npm and accept the weaker shutdown guarantee; the port sweep below is the
        # backstop for exactly this case.
        $frontFile = (Join-Path $env:SystemRoot 'System32\cmd.exe')
        $frontArgs = '/d /s /c npm run dev'
    }
    $services += [pscustomobject]@{
        Label     = 'frontend'
        Color     = [ConsoleColor]::Green
        File      = $frontFile
        Arguments = $frontArgs
        Dir       = (Join-Path $Root 'frontend')
        Ready     = 'http://localhost:8080'
        Process   = $null
        Reported  = $false
    }
}

# ---------------------------------------------------------------- startup ----

Write-Host ''
Write-Host '  ESGenuine' -ForegroundColor White -NoNewline
Write-Host " - $($services.Label -join ' + ')" -ForegroundColor DarkGray
foreach ($svc in $services) { Write-Host "  $($svc.Label.Trim()) -> $($svc.Ready)" -ForegroundColor DarkGray }
Write-Host '  Ctrl+C to shut everything down.' -ForegroundColor DarkGray
Write-Host ('  ' + ('-' * 68)) -ForegroundColor DarkGray
Write-Host ''

$pumps = @()

foreach ($svc in $services) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $svc.File
    $psi.Arguments              = $svc.Arguments
    $psi.WorkingDirectory       = $svc.Dir
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.CreateNoWindow         = $true
    # Vite and uvicorn both colourise only when they think a TTY is attached;
    # redirected pipes turn that off, which is what we want - raw ANSI escapes
    # would fight with our own line tags.
    $psi.EnvironmentVariables['PYTHONUNBUFFERED'] = '1'
    $psi.EnvironmentVariables['FORCE_COLOR']      = '0'

    $svc.Process = [System.Diagnostics.Process]::Start($psi)

    foreach ($reader in @($svc.Process.StandardOutput, $svc.Process.StandardError)) {
        $pumps += [pscustomobject]@{
            Reader = $reader
            Label  = $svc.Label
            Color  = $svc.Color
            Task   = $null
            Done   = $false
        }
    }
}

# Ctrl+C as input rather than as a signal. If stdin is redirected this throws, in
# which case we fall back to letting the console kill us and just clean up in the
# `finally` below.
$interactive = $true
try { [Console]::TreatControlCAsInput = $true } catch { $interactive = $false }

$browserPending = (-not $NoBrowser) -and ($Target -ne 'backend')
$browserDeadline = (Get-Date).AddSeconds(20)

try {
    while ($true) {

        # ---- drain both servers' output ------------------------------------
        foreach ($pump in $pumps) {
            if ($pump.Done) { continue }
            if ($null -eq $pump.Task) { $pump.Task = $pump.Reader.ReadLineAsync() }

            while ($pump.Task -and $pump.Task.IsCompleted) {
                $line = $null
                try { $line = $pump.Task.Result } catch { $pump.Done = $true; $pump.Task = $null; break }
                if ($null -eq $line) { $pump.Done = $true; $pump.Task = $null; break }

                Write-Tagged -Label $pump.Label -Color $pump.Color -Text $line

                # Vite prints its Local: URL once it is actually serving - a far
                # better "open the browser now" signal than a fixed sleep.
                if ($browserPending -and $line -match 'localhost:8080') {
                    $browserPending = $false
                    Start-Process 'http://localhost:8080' | Out-Null
                }

                $pump.Task = $pump.Reader.ReadLineAsync()
            }
        }

        # Fallback if Vite never prints a recognisable line.
        if ($browserPending -and (Get-Date) -gt $browserDeadline) {
            $browserPending = $false
            Start-Process 'http://localhost:8080' | Out-Null
        }

        # ---- report any server that died on its own -------------------------
        foreach ($svc in $services) {
            if (-not $svc.Reported -and $svc.Process.HasExited) {
                $svc.Reported = $true
                Write-Host ''
                Write-Tagged -Label $svc.Label -Color Yellow -Text "exited on its own (code $($svc.Process.ExitCode)). Scroll up for the error."
                Write-Host ''
            }
        }

        # ---- Ctrl+C -----------------------------------------------------------
        if ($interactive) {
            while ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq [ConsoleKey]::C -and ($key.Modifiers -band [ConsoleModifiers]::Control)) {
                    Write-Host ''
                    Write-Host '^C  Terminate ESGenuine (Y/N)? ' -ForegroundColor Yellow -NoNewline
                    $answer = $null
                    while ($null -eq $answer) {
                        $k = [Console]::ReadKey($true)
                        switch ($k.Key) {
                            ([ConsoleKey]::Y)      { $answer = 'Y' }
                            ([ConsoleKey]::N)      { $answer = 'N' }
                            ([ConsoleKey]::Escape) { $answer = 'N' }
                            ([ConsoleKey]::C)      { if ($k.Modifiers -band [ConsoleModifiers]::Control) { $answer = 'Y' } }
                        }
                    }
                    Write-Host $answer
                    if ($answer -eq 'Y') { return }
                    Write-Host '    resuming - servers untouched.' -ForegroundColor DarkGray
                    Write-Host ''
                }
            }
        }

        # ---- stop when nothing is left running -------------------------------
        $alive = @($services | Where-Object { -not $_.Process.HasExited })
        if ($alive.Count -eq 0) {
            $draining = @($pumps | Where-Object { -not $_.Done })
            if ($draining.Count -eq 0) {
                Write-Host ''
                Write-Host '  All servers have exited.' -ForegroundColor Yellow
                break
            }
        }

        Start-Sleep -Milliseconds 60
    }
}
finally {
    # Runs for every exit path: Y at the prompt, a hard Ctrl+C when stdin was
    # redirected, or the window being closed mid-run.
    try { [Console]::TreatControlCAsInput = $false } catch { }

    Write-Host ''
    foreach ($svc in $services) {
        if ($svc.Process -and -not $svc.Process.HasExited) {
            Write-Host "  stopping $($svc.Label.Trim()) (pid $($svc.Process.Id))... " -ForegroundColor DarkGray -NoNewline
            Stop-Tree -ProcessId $svc.Process.Id
            Write-Host 'ok' -ForegroundColor DarkGray
        }
    }
    if ($Target -ne 'frontend') { Stop-StrandedPort -Port 8000 -RepoRoot $Root }
    if ($Target -ne 'backend')  { Stop-StrandedPort -Port 8080 -RepoRoot $Root }
    Write-Host '  ESGenuine stopped.' -ForegroundColor DarkGray
    Write-Host ''
}
