$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$url = 'https://jrsoftware.org/download.php/is.exe?site=1'
$out = Join-Path $env:TEMP 'innosetup-installer.exe'

Invoke-WebRequest -Uri $url -OutFile $out
Start-Process -FilePath $out -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-' -Wait

$paths = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)

foreach ($path in $paths) {
    if (Test-Path $path) {
        Write-Output $path
        exit 0
    }
}

throw 'ISCC.exe tidak ditemukan setelah instalasi Inno Setup.'
