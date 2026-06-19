from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from blindscanner import __version__

_USER_AGENT = f"RunLabScanner/{__version__}"


class UpdateError(Exception):
    pass


@dataclass(slots=True)
class UpdateManifest:
    version: str
    url: str
    notes: str = ""


def parse_version(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = []
    for part in cleaned.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def is_newer_version(candidate: str, current: str=__version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def _parse_manifest_payload(payload: dict) -> UpdateManifest:
    version = str(payload.get("version", "")).strip()
    download_url = str(payload.get("url", "")).strip()
    notes = str(payload.get("notes", "")).strip()

    if not version or not download_url:
        raise UpdateError("Manifest update harus berisi 'version' dan 'url'.")

    return UpdateManifest(version=version, url=download_url, notes=notes)


def fetch_update_manifest(url: str, timeout: float=10.0) -> UpdateManifest:
    if not url.strip():
        raise UpdateError("URL manifest update belum diisi.")
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f"Gagal membaca manifest update: {exc}") from exc

    return _parse_manifest_payload(payload)


def fetch_licensed_update_manifest(
    api_base_url: str,
    license_key: str,
    machine_id: str,
    channel: str = "",
    timeout: float = 10.0,
) -> UpdateManifest:
    """Ambil manifest update yang ter-gate license dari Cloudflare Worker.

    Worker memvalidasi license + aktivasi mesin sebelum mengembalikan info update.
    """
    if not api_base_url.strip():
        raise UpdateError("URL API license belum dikonfigurasi.")
    if not license_key or not machine_id:
        raise UpdateError("License belum aktif, tidak bisa cek update.")

    from urllib.parse import urlencode

    query = urlencode(
        {
            "license_key": license_key,
            "machine_id": machine_id,
            "channel": channel or "",
        }
    )
    url = f"{api_base_url.rstrip('/')}/api/update?{query}"
    try:
        request = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 403:
            raise UpdateError("License tidak valid untuk mengunduh update.") from exc
        if exc.code == 404:
            raise UpdateError("Belum ada release update yang tersedia.") from exc
        raise UpdateError(f"Gagal membaca manifest update: {exc}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f"Gagal membaca manifest update: {exc}") from exc

    if payload.get("error"):
        raise UpdateError(str(payload["error"]))

    return _parse_manifest_payload(payload)


def download_update(download_url: str, version: str) -> Path:
    target_dir = Path(tempfile.gettempdir()) / "runlab-scanner-updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"RunLabScanner-{version}.exe"
    try:
        request = Request(download_url, headers={"User-Agent": _USER_AGENT})
        with urlopen(request, timeout=120) as response, open(target_path, "wb") as out_file:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out_file.write(chunk)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Gagal mengunduh update: {exc}") from exc
    return target_path


def get_current_executable() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def create_update_script(new_exe_path: Path, current_exe_path: Path) -> Path:
    script_path = Path(tempfile.gettempdir()) / "runlab-scanner-apply-update.ps1"
    script_body = f"""
$ErrorActionPreference = 'Stop'
$newExe = '{new_exe_path}'
$currentExe = '{current_exe_path}'
$backupExe = "$currentExe.bak"
Start-Sleep -Seconds 2
if (Test-Path $backupExe) {{
    Remove-Item $backupExe -Force
}}
Move-Item -Path $currentExe -Destination $backupExe -Force
Move-Item -Path $newExe -Destination $currentExe -Force
Start-Process -FilePath $currentExe
""".strip()
    script_path.write_text(script_body, encoding="utf-8")
    return script_path


def launch_update_installer(script_path: Path) -> None:
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
