from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from blindscanner import __version__
from blindscanner.machine import get_hostname, get_machine_id

# Toleransi offline: berapa lama license cache masih dianggap valid tanpa server.
OFFLINE_GRACE_SECONDS = 14 * 24 * 3600  # 14 hari
_HTTP_TIMEOUT = 12.0


class LicenseError(RuntimeError):
    pass


@dataclass(slots=True)
class LicenseStatus:
    valid: bool
    status: str = ""
    license_key: str = ""
    channel: str = "stable"
    expires_at: str = ""
    customer_name: str = ""
    reason: str = ""
    offline: bool = False
    raw: dict = field(default_factory=dict)


def _signable_payload(p: dict) -> str:
    return "|".join(
        [
            "1" if p.get("valid") else "0",
            str(p.get("license_key", "")),
            str(p.get("machine_id", "")),
            str(p.get("status", "")),
            str(p.get("expires_at", "")),
            str(p.get("channel", "")),
            str(p.get("issued_at", "")),
        ]
    )


def _verify_signature(payload: dict, signing_key: str) -> bool:
    signature = payload.get("signature")
    if not signature or not signing_key:
        return False
    expected = hmac.new(
        signing_key.encode("utf-8"),
        _signable_payload(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, str(signature))


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home()
    return root / "RunLabScanner"


class LicenseClient:
    """Client aktivasi & validasi license terhadap Cloudflare Worker.

    Menyimpan cache respons ber-HMAC sehingga aplikasi tetap bisa jalan offline
    dalam periode grace, namun tetap aman dari pemalsuan file cache.
    """

    def __init__(
        self,
        api_base_url: str,
        signing_key: str,
        config_dir: Optional[Path] = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.signing_key = signing_key
        self.config_dir = config_dir or _config_dir()
        self.license_file = self.config_dir / "license.json"
        self.cache_file = self.config_dir / "license_cache.json"

    # ---------- penyimpanan license key ----------
    def load_saved_key(self) -> str:
        if not self.license_file.exists():
            return ""
        try:
            data = json.loads(self.license_file.read_text(encoding="utf-8"))
            return str(data.get("license_key", "")).strip()
        except (json.JSONDecodeError, OSError):
            return ""

    def save_key(self, license_key: str) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.license_file.write_text(
            json.dumps({"license_key": license_key.strip()}, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        for path in (self.license_file, self.cache_file):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    # ---------- cache (anti-tamper) ----------
    def _save_cache(self, payload: dict) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        record = {"payload": payload, "cached_at": int(time.time())}
        self.cache_file.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def _load_cache(self) -> Optional[dict]:
        if not self.cache_file.exists():
            return None
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _status_from_cache(self) -> Optional[LicenseStatus]:
        record = self._load_cache()
        if not record:
            return None
        payload = record.get("payload") or {}
        cached_at = int(record.get("cached_at") or 0)
        # Cache hanya dipercaya jika tanda tangan valid dan masih dalam grace period.
        if not _verify_signature(payload, self.signing_key):
            return None
        if time.time() - cached_at > OFFLINE_GRACE_SECONDS:
            return LicenseStatus(
                valid=False,
                status="offline_expired",
                reason="Tidak bisa menghubungi server license dan masa offline habis.",
                offline=True,
                raw=payload,
            )
        if not payload.get("valid"):
            return None
        return LicenseStatus(
            valid=True,
            status=str(payload.get("status", "active")),
            license_key=str(payload.get("license_key", "")),
            channel=str(payload.get("channel", "stable")),
            expires_at=str(payload.get("expires_at", "")),
            customer_name=str(payload.get("customer_name", "")),
            offline=True,
            raw=payload,
        )

    # ---------- HTTP ----------
    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.api_base_url}{path}"
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"RunLabScanner/{__version__}",
            },
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))

    def _to_status(self, payload: dict) -> LicenseStatus:
        if not _verify_signature(payload, self.signing_key):
            raise LicenseError("Tanda tangan respons license tidak valid (kemungkinan koneksi tidak aman).")
        return LicenseStatus(
            valid=bool(payload.get("valid")),
            status=str(payload.get("status", "")),
            license_key=str(payload.get("license_key", "")),
            channel=str(payload.get("channel", "stable")),
            expires_at=str(payload.get("expires_at", "")),
            customer_name=str(payload.get("customer_name", "")),
            reason=str(payload.get("reason", "")),
            offline=False,
            raw=payload,
        )

    # ---------- API publik ----------
    def activate(self, license_key: str) -> LicenseStatus:
        license_key = license_key.strip()
        if not license_key:
            raise LicenseError("License key kosong.")
        body = {
            "license_key": license_key,
            "machine_id": get_machine_id(),
            "hostname": get_hostname(),
            "app_version": __version__,
        }
        try:
            payload = self._post("/api/activate", body)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise LicenseError(f"Gagal menghubungi server license: {exc}") from exc

        status = self._to_status(payload)
        if status.valid:
            self.save_key(license_key)
            self._save_cache(payload)
        return status

    def validate(self, license_key: Optional[str] = None) -> LicenseStatus:
        key = (license_key or self.load_saved_key()).strip()
        if not key:
            return LicenseStatus(valid=False, status="no_license", reason="Belum ada license.")

        body = {
            "license_key": key,
            "machine_id": get_machine_id(),
            "app_version": __version__,
        }
        try:
            payload = self._post("/api/validate", body)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            # Offline: jatuh ke cache ber-HMAC.
            cached = self._status_from_cache()
            if cached is not None:
                return cached
            return LicenseStatus(
                valid=False,
                status="offline_no_cache",
                reason="Tidak ada koneksi ke server license dan tidak ada cache valid.",
                offline=True,
            )

        status = self._to_status(payload)
        if status.valid:
            self._save_cache(payload)
        return status
