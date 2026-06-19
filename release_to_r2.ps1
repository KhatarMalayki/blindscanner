param(
    [Parameter(Mandatory = $true)]
    [string]$Bucket,

    [Parameter(Mandatory = $true)]
    [string]$PublicBaseUrl,

    [string]$Notes = '',
    [string]$ExePath = '.\dist\RunLabScanner.exe',
    [string]$ManifestKey = 'runlab-scanner/manifest.json',
    [string]$ReleasePrefix = 'runlab-scanner/releases',
    [string]$Version = '',
    [switch]$BuildExe
)

$ErrorActionPreference = 'Stop'

function Get-AppVersion {
    param([string]$InitFilePath)

    if (-not (Test-Path $InitFilePath)) {
        throw "Version file tidak ditemukan: $InitFilePath"
    }

    $content = Get-Content -Path $InitFilePath -Raw
    $match = [regex]::Match($content, '__version__\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "Tidak bisa membaca __version__ dari $InitFilePath"
    }

    return $match.Groups[1].Value
}

if (-not (Get-Command wrangler -ErrorAction SilentlyContinue)) {
    throw 'Wrangler CLI tidak ditemukan. Install dulu dengan: npm i -g wrangler'
}

if ($BuildExe) {
    Write-Host 'Building EXE terlebih dahulu...' -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
}

if (-not (Test-Path $ExePath)) {
    throw "File EXE tidak ditemukan: $ExePath"
}

$resolvedExePath = (Resolve-Path $ExePath).Path
$normalizedBaseUrl = $PublicBaseUrl.TrimEnd('/')

$appVersion = if ($Version.Trim()) { $Version.Trim() } else { Get-AppVersion '.\blindscanner\__init__.py' }
$releaseFileName = "RunLabScanner-$appVersion.exe"
$releaseObjectKey = "$ReleasePrefix/$releaseFileName"
$releaseUrl = "$normalizedBaseUrl/$releaseObjectKey"
$manifestUrl = "$normalizedBaseUrl/$ManifestKey"

Write-Host "Uploading EXE ke R2: $releaseObjectKey" -ForegroundColor Cyan
& wrangler r2 object put "$Bucket/$releaseObjectKey" --file "$resolvedExePath"

$tempManifestPath = Join-Path $env:TEMP 'runlab-scanner-manifest.json'
$manifestObject = [ordered]@{
    version = $appVersion
    url = $releaseUrl
    notes = $Notes
}
$manifestObject | ConvertTo-Json -Depth 3 | Set-Content -Path $tempManifestPath -Encoding UTF8

Write-Host "Uploading manifest ke R2: $ManifestKey" -ForegroundColor Cyan
& wrangler r2 object put "$Bucket/$ManifestKey" --file "$tempManifestPath"

Write-Host ''
Write-Host 'Release update selesai.' -ForegroundColor Green
Write-Host "Version     : $appVersion"
Write-Host "EXE URL     : $releaseUrl"
Write-Host "Manifest URL: $manifestUrl"
