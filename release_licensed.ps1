param(
    [Parameter(Mandatory = $true)]
    [string]$Bucket,

    [Parameter(Mandatory = $true)]
    [string]$PublicBaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$WorkerUrl,        # mis. https://runlab-licenses.akun.workers.dev

    [Parameter(Mandatory = $true)]
    [string]$AdminToken,       # ADMIN_TOKEN yang sama dengan secret Worker

    [string]$Channel = 'stable',
    [string]$Notes = '',
    [switch]$Mandatory,
    [string]$ExePath = '.\dist\RunLabScanner.exe',
    [string]$ReleasePrefix = 'runlab-scanner/releases',
    [string]$Version = '',
    [switch]$BuildExe
)

$ErrorActionPreference = 'Stop'

function Get-AppVersion {
    param([string]$InitFilePath)
    if (-not (Test-Path $InitFilePath)) { throw "Version file tidak ditemukan: $InitFilePath" }
    $content = Get-Content -Path $InitFilePath -Raw
    $match = [regex]::Match($content, '__version__\s*=\s*"([^"]+)"')
    if (-not $match.Success) { throw "Tidak bisa membaca __version__ dari $InitFilePath" }
    return $match.Groups[1].Value
}

if (-not (Get-Command wrangler -ErrorAction SilentlyContinue)) {
    throw 'Wrangler CLI tidak ditemukan. Install dulu dengan: npm i -g wrangler'
}

if ($BuildExe) {
    Write-Host 'Building EXE terlebih dahulu...' -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
}

if (-not (Test-Path $ExePath)) { throw "File EXE tidak ditemukan: $ExePath" }

$resolvedExePath = (Resolve-Path $ExePath).Path
$normalizedBaseUrl = $PublicBaseUrl.TrimEnd('/')
$normalizedWorker = $WorkerUrl.TrimEnd('/')

$appVersion = if ($Version.Trim()) { $Version.Trim() } else { Get-AppVersion '.\blindscanner\__init__.py' }
$releaseFileName = "RunLabScanner-$appVersion.exe"
$releaseObjectKey = "$ReleasePrefix/$releaseFileName"
$releaseUrl = "$normalizedBaseUrl/$releaseObjectKey"

Write-Host "Uploading EXE ke R2 (remote): $releaseObjectKey" -ForegroundColor Cyan
& wrangler r2 object put "$Bucket/$releaseObjectKey" --file "$resolvedExePath" --remote

# Daftarkan release ke Worker (D1) agar dipakai endpoint update ber-license.
$payload = [ordered]@{
    version   = $appVersion
    channel   = $Channel
    url       = $releaseUrl
    notes     = $Notes
    mandatory = [bool]$Mandatory
} | ConvertTo-Json -Depth 3

Write-Host "Mendaftarkan release ke Worker: $normalizedWorker/admin/api/releases" -ForegroundColor Cyan
$headers = @{ Authorization = "Bearer $AdminToken"; 'Content-Type' = 'application/json' }
$response = Invoke-RestMethod -Uri "$normalizedWorker/admin/api/releases" -Method Post -Headers $headers -Body $payload

Write-Host ''
Write-Host 'Release ber-license selesai.' -ForegroundColor Green
Write-Host "Version : $appVersion"
Write-Host "Channel : $Channel"
Write-Host "EXE URL : $releaseUrl"
Write-Host "Worker  : OK ($($response.ok))"
