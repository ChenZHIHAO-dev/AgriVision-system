$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'runtime\server-process.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No recorded server process.'; exit 0 }
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$server = Get-Process -Id $record.processId -ErrorAction SilentlyContinue
if ($server -and $server.StartTime.ToUniversalTime().Ticks -eq ([datetime]$record.startedAt).ToUniversalTime().Ticks) {
    Stop-Process -Id $server.Id
    Write-Output 'AgriVision stopped.'
} else { Write-Output 'The recorded server has already exited.' }
Remove-Item -LiteralPath $pidFile
