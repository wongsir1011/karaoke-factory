param(
    [switch]$WithAI
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

function Get-SupportedJsRuntime {
    $DenoCommand = Get-Command deno -ErrorAction SilentlyContinue
    if ($DenoCommand) {
        $DenoVersionLine = (& $DenoCommand.Source --version 2>$null | Select-Object -First 1)
        if ($DenoVersionLine -match '^deno\s+(\d+)\.(\d+)') {
            $DenoMajor = [int]$Matches[1]
            $DenoMinor = [int]$Matches[2]
            if ($DenoMajor -gt 2 -or ($DenoMajor -eq 2 -and $DenoMinor -ge 3)) {
                return $DenoVersionLine
            }
        }
    }

    $NodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($NodeCommand) {
        $NodeVersion = (& $NodeCommand.Source --version 2>$null | Select-Object -First 1)
        if ($NodeVersion -match '^v?(\d+)\.') {
            $NodeMajor = [int]$Matches[1]
            if ($NodeMajor -ge 22) {
                return "Node.js $NodeVersion"
            }
        }
    }

    return $null
}

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

$JsRuntime = Get-SupportedJsRuntime
if (-not $JsRuntime) {
    $WingetCommand = Get-Command winget -ErrorAction SilentlyContinue
    if ($WingetCommand) {
        Write-Host "Installing Deno 2.3+ for reliable YouTube downloads..." -ForegroundColor Cyan
        & $WingetCommand.Source install --id DenoLand.Deno --exact --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
            $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
            $env:Path = "$MachinePath;$UserPath"
            $JsRuntime = Get-SupportedJsRuntime
        }
    }
}

if ($JsRuntime) {
    Write-Host "YouTube JavaScript support ready: $JsRuntime" -ForegroundColor Green
}
else {
    Write-Warning "YouTube downloads need Deno 2.3+ or Node.js 22+. Run: winget install DenoLand.Deno"
}

if ($WithAI) {
    Write-Host "AI separation and sentence-level lyric timing are ready." -ForegroundColor Green
}
Write-Host "Setup complete. Run .\start.ps1 to open Karaoke Factory." -ForegroundColor Green
