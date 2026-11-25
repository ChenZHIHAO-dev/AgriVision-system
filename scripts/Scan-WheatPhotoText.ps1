param(
    [Parameter(Mandatory = $true)][string]$InputCsv,
    [Parameter(Mandatory = $true)][string]$OutputCsv
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop') {
    $desktopPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    & $desktopPowerShell -NoProfile -NonInteractive -File $PSCommandPath -InputCsv $InputCsv -OutputCsv $OutputCsv
    exit $LASTEXITCODE
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapTransform, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]

$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$taskMethods = @{}

function Wait-Operation($Operation, [Type]$ResultType) {
    if (-not $taskMethods.ContainsKey($ResultType)) {
        $taskMethods[$ResultType] = $asTask.MakeGenericMethod($ResultType)
    }
    $task = $taskMethods[$ResultType].Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}

$chinese = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('zh-Hans-CN'))
$english = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
if (-not $chinese -or -not $english) { throw 'Install the Windows Chinese and English OCR language capabilities.' }

function Read-PhotoText([string]$Path) {
    $file = Wait-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
    $stream = Wait-Operation ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Wait-Operation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $long = [Math]::Max($decoder.PixelWidth, $decoder.PixelHeight)
        $scale = [Math]::Min(896, [Math]::Max(576, $long)) / $long
        $transform = [Windows.Graphics.Imaging.BitmapTransform]::new()
        $transform.ScaledWidth = [uint32][Math]::Max(1, [Math]::Round($decoder.PixelWidth * $scale))
        $transform.ScaledHeight = [uint32][Math]::Max(1, [Math]::Round($decoder.PixelHeight * $scale))
        $operation = $decoder.GetSoftwareBitmapAsync(
            [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Ignore,
            $transform,
            [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation,
            [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage
        )
        $bitmap = Wait-Operation $operation ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $zh = Wait-Operation ($chinese.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $en = Wait-Operation ($english.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            [pscustomobject]@{ width = $decoder.PixelWidth; height = $decoder.PixelHeight; zh = $zh.Text; en = $en.Text }
        } finally {
            $bitmap.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

if (Test-Path -LiteralPath $OutputCsv) { throw "Output already exists: $OutputCsv" }
$rows = @(Import-Csv -LiteralPath $InputCsv -Encoding UTF8)
$count = 0
$rows | ForEach-Object {
    $row = $_
    try {
        $read = Read-PhotoText $row.file
        [pscustomobject]@{ path = $row.path; width = $read.width; height = $read.height; zh = $read.zh; en = $read.en; error = '' }
    } catch {
        [pscustomobject]@{ path = $row.path; width = ''; height = ''; zh = ''; en = ''; error = $_.Exception.Message }
    }
    $count++
    if ($count % 500 -eq 0) { Write-Host "Scanned $count / $($rows.Length) photos" }
} | Export-Csv -LiteralPath $OutputCsv -Encoding UTF8 -NoTypeInformation
Write-Host "Scanned $count photos. Output: $OutputCsv"
