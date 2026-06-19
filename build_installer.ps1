$ErrorActionPreference = 'Stop'

$isccCommand = Get-Command iscc -ErrorAction SilentlyContinue
$isccPath = if ($isccCommand) {
    $isccCommand.Source
} else {
    $candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    ($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
}

if (-not $isccPath) {
    throw 'Inno Setup Compiler (iscc) tidak ditemukan di PATH atau lokasi default. Install Inno Setup terlebih dahulu.'
}

if (-not (Test-Path .\dist\RunLabScanner.exe)) {
    throw 'dist\RunLabScanner.exe belum ada. Jalankan build_exe.ps1 terlebih dahulu.'
}

if (-not (Test-Path .\assets\blindscanner.ico)) {
    & .\.venv\Scripts\python .\scripts\generate_icon.py
}

& $isccPath .\installer.iss
