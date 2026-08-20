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

$InstallArguments = @(
    "--disable-pip-version-check",
    "--retries", "10",
    "--timeout", "60"
)
& $VenvPython -m pip install @InstallArguments --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to update Python installation tools. Please check the network and try again."
}

if ($WithAI) {
    Write-Host "Installing Demucs separation and Whisper lyric-timing support..." -ForegroundColor Cyan
    & $VenvPython -m pip install @InstallArguments --no-build-isolation -r requirements-ai.txt
}
else {
    & $VenvPython -m pip install @InstallArguments -r requirements.txt
}
if ($LASTEXITCODE -ne 0) {
    throw "Package installation failed. Please check the network and try again."
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

if ($WithAI) {
    Write-Host "AI separation and sentence-level lyric timing are ready." -ForegroundColor Green
}
Write-Host "Setup complete. Run .\start.ps1 to open Karaoke Factory." -ForegroundColor Green
