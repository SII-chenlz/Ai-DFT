# Native Windows x64 build. Run from PowerShell with Python 3.11 and Node 22.
$ErrorActionPreference = 'Stop'
$AifsRoot = Split-Path -Parent $PSScriptRoot
$AifsVenv = Join-Path $AifsRoot '.local\desktop-build-venv'

if ($env:OS -ne 'Windows_NT') { throw 'Run this script on Windows x64.' }
Get-Command node.exe, npm.cmd, tar.exe -ErrorAction Stop | Out-Null
Push-Location $AifsRoot
try {
    if (-not (Test-Path "$AifsVenv\Scripts\python.exe")) {
        if ($env:AIFS_PYTHON) {
            & $env:AIFS_PYTHON -m venv $AifsVenv
        } else {
            & py.exe -3.11 -m venv $AifsVenv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 environment creation failed.' }
    }
    $AifsPython = Join-Path $AifsVenv 'Scripts\python.exe'
    & $AifsPython -c "import sys, platform; assert sys.version_info[:2] == (3, 11) and platform.machine().lower() in {'amd64', 'x86_64'} and sys.maxsize > 2**32, 'Requires Windows x64 Python 3.11'"
    if ($LASTEXITCODE -ne 0) { throw 'Wrong Python version or architecture.' }
    & $AifsPython -m pip install -r packaging/requirements-desktop.lock
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    & npm.cmd --prefix dsh-plugin-aifs ci
    if ($LASTEXITCODE -ne 0) { throw 'Plugin dependency installation failed.' }
    & node.exe scripts/release.mjs --installed
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata check failed.' }
    & $AifsPython scripts/build-desktop-backend.py
    if ($LASTEXITCODE -ne 0) { throw 'Native backend build failed.' }
    & $AifsPython scripts/verify-desktop-backend.py build/desktop-runtimes/win32-x64/aifs-backend/aifs-backend.exe --report .local/windows-backend-verification.json
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Windows backend verification failed.' }
    & node.exe scripts/build-desktop-plugin.mjs --target win32-x64
    if ($LASTEXITCODE -ne 0) { throw 'Plugin packaging failed.' }
} finally {
    Pop-Location
}
