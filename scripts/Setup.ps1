param([switch]$WithCuda, [string]$Python = '3.12')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Please install uv, then run this script again: https://docs.astral.sh/uv/getting-started/installation/' }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Please install Node.js 24 LTS.' }
    $venvPython = '.venv\Scripts\python.exe'
    $pythonReady = $false
    if (Test-Path -LiteralPath $venvPython) {
        try {
            & $venvPython --version 2>$null | Out-Null
            $pythonReady = $LASTEXITCODE -eq 0
        } catch {
            $pythonReady = $false
        }
    }
    if (-not $pythonReady) {
        uv venv --allow-existing .venv --python $Python --cache-dir .cache/uv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
    }
    uv pip install --python .venv/Scripts/python.exe --cache-dir .cache/uv -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }
    if ($WithCuda) {
        $env:UV_HTTP_TIMEOUT = '180'
        uv pip install --python .venv/Scripts/python.exe --cache-dir .cache/uv 'torch==2.7.1' 'torchvision==0.22.1' --index-url https://download.pytorch.org/whl/cu126
        if ($LASTEXITCODE -ne 0) { throw 'CUDA framework installation failed' }
        uv pip install --python .venv/Scripts/python.exe --cache-dir .cache/uv -r requirements-ml.txt
        if ($LASTEXITCODE -ne 0) { throw 'Training dependency installation failed' }
    }
    if (Test-Path -LiteralPath 'package-lock.json') { npm.cmd ci --cache .cache/npm --no-audit --no-fund } else { npm.cmd install --cache .cache/npm --no-audit --no-fund }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Web build failed' }
    npm.cmd run build:mp
    if ($LASTEXITCODE -ne 0) { throw 'Mini-program build failed' }
    Write-Output 'Ready. Run .\scripts\Start.ps1 to open the local application.'
} finally { Pop-Location }
