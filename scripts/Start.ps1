param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$webPath = Join-Path $projectRoot 'apps\client\dist\build\h5\index.html'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run .\scripts\Setup.ps1 first.' }
if (-not (Test-Path -LiteralPath $webPath)) { throw 'Build the web application first: npm run build' }
$runtimePath = Join-Path $projectRoot 'runtime'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$pidFile = Join-Path $runtimePath 'server-process.json'
if (Test-Path -LiteralPath $pidFile) {
    $previous = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $existing = Get-Process -Id $previous.processId -ErrorAction SilentlyContinue
    if ($existing -and $existing.StartTime.ToUniversalTime().Ticks -eq ([datetime]$previous.startedAt).ToUniversalTime().Ticks) {
        Write-Output "AgriVision is already running: http://127.0.0.1:$($previous.port)"
        exit 0
    }
}
$probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try { $probe.Start() } catch { throw "Port $Port is already in use. Stop the existing service or choose another port." } finally { $probe.Stop() }
$server = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--app-dir','services/api','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'server.log') -RedirectStandardError (Join-Path $runtimePath 'server-error.log')
$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
        if ($health.status -eq 'ok' -and $health.application -eq 'agrivision') {
            # A Windows venv launcher can spawn the actual interpreter. Record
            # the process owning the newly opened port, rather than its launcher.
            $pattern = '^\s*TCP\s+127\.0\.0\.1:' + $Port + '\s+\S+\s+LISTENING\s+(\d+)'
            $listener = @(netstat -ano -p tcp | Select-String $pattern)
            if ($listener.Count -eq 1) {
                $processId = [int]([regex]::Match($listener[0].ToString(), '(\d+)\s*$').Groups[1].Value)
                $actualServer = Get-Process -Id $processId -ErrorAction Stop
                $processRecord = @{ processId = $actualServer.Id; startedAt = $actualServer.StartTime.ToUniversalTime().ToString('o'); port = $Port }
                $processRecord | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
                $ready = $true
                break
            }
        }
    } catch {}
    Start-Sleep -Milliseconds 400
}
if (-not $ready) { throw 'Server readiness timed out. See runtime/server-error.log.' }
Write-Output "AgriVision: http://127.0.0.1:$Port"
Write-Output "API docs: http://127.0.0.1:$Port/docs"
Write-Output 'Stop with .\scripts\Stop.ps1'
