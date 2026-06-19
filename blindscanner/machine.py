from __future__ import annotations

import hashlib
import platform
import socket
import subprocess
import uuid


def _windows_machine_guid() -> str:
    """Ambil MachineGuid dari registry Windows (stabil per instalasi OS)."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except OSError:
        return ""


def _wmic_uuid() -> str:
    """Fallback: UUID motherboard via WMIC (jika tersedia)."""
    try:
        result = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) >= 2 and lines[1].lower() not in {"uuid", ""}:
            return lines[1]
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def get_machine_id() -> str:
    """ID mesin stabil & unik, di-hash agar tidak membocorkan info sistem mentah."""
    parts = [
        _windows_machine_guid(),
        _wmic_uuid(),
        platform.node(),
        str(uuid.getnode()),  # MAC address based
    ]
    seed = "|".join(p for p in parts if p)
    if not seed:
        seed = socket.gethostname() or "unknown-host"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return digest[:32]


def get_hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"
