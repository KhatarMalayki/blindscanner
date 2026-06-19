$ErrorActionPreference = 'Stop'

if (-not (Test-Path .venv)) {
    python -m venv .venv
}

& .\.venv\Scripts\python -m pip install --upgrade pip
& .\.venv\Scripts\python -m pip install -r requirements.txt
& .\.venv\Scripts\python .\scripts\generate_icon.py
& .\.venv\Scripts\python -m PyInstaller --noconfirm --onefile --windowed --icon .\assets\blindscanner.ico --name RunLabScanner main.py
