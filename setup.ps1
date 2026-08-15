param(
    [switch]$WithAI
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        & $PythonCommand.Source -m venv .venv
    }
    else {
        $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
        $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
        if ($PyLauncher) {
            & $PyLauncher.Source -3.12 -m venv .venv
        }
        elseif (Test-Path -LiteralPath $CodexPython) {
            & $CodexPython -m venv .venv
        }
        else {
            throw "Python was not found. Install Python 3.11 or 3.12, then run setup.ps1 again."
        }
    }
}

if ($WithAI) {
    & $VenvPython -m pip install -r requirements-ai.txt
}
else {
    & $VenvPython -m pip install -r requirements.txt
}

$DenoCommand = Get-Command deno -ErrorAction SilentlyContinue
$NodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($DenoCommand) {
    Write-Host "YouTube JavaScript support: Deno detected." -ForegroundColor Green
}
elseif ($NodeCommand) {
    Write-Host "YouTube JavaScript support: Node.js detected." -ForegroundColor Green
}
else {
    Write-Warning "YouTube downloads need Deno 2.3+ or Node.js 22+. Install one of them for reliable downloads."
}

Write-Host "Setup complete. Run .\start.ps1 to open Karaoke Factory." -ForegroundColor Green
