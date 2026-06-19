from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from blindscanner.wia import ScannerDevice, ScanOptions

NETWORK_DEVICE_PREFIX = "net::"

# eSCL color mode mapping dari opsi internal aplikasi.
COLOR_MODE_MAP = {
    "color": "RGB24",
    "grayscale": "Grayscale8",
    "gray": "Grayscale8",
    "bw": "BlackAndWhite1",
    "blackwhite": "BlackAndWhite1",
}

# Kandidat base URL yang dicoba saat probing host eSCL.
_BASE_CANDIDATES = (
    "http://{host}:80",
    "https://{host}:443",
    "http://{host}:8080",
)

_DEFAULT_TIMEOUT = 8.0
# Ukuran A4 dalam satuan 1/300 inci (fallback bila kapabilitas tak punya MaxWidth/Height).
_A4_WIDTH_300 = 2480
_A4_HEIGHT_300 = 3508


class EsclError(RuntimeError):
    pass


@dataclass(slots=True)
class EsclCapabilities:
    base_url: str
    model: str
    max_width: int = _A4_WIDTH_300
    max_height: int = _A4_HEIGHT_300
    color_modes: List[str] = field(default_factory=list)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_first(root: ET.Element, name: str) -> Optional[ET.Element]:
    for element in root.iter():
        if _local_name(element.tag) == name:
            return element
    return None


def _find_all_text(root: ET.Element, name: str) -> List[str]:
    values: List[str] = []
    for element in root.iter():
        if _local_name(element.tag) == name and element.text:
            text = element.text.strip()
            if text:
                values.append(text)
    return values


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _http_get(url: str, timeout: float = _DEFAULT_TIMEOUT) -> bytes:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return response.read()


def _http_post(url: str, body: bytes, timeout: float = _DEFAULT_TIMEOUT):
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "text/xml; charset=utf-8"},
    )
    return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())


def fetch_capabilities(base_url: str, timeout: float = _DEFAULT_TIMEOUT) -> EsclCapabilities:
    base_url = base_url.rstrip("/")
    url = f"{base_url}/eSCL/ScannerCapabilities"
    try:
        raw = _http_get(url, timeout=timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise EsclError(f"Tidak bisa membaca kapabilitas eSCL di {base_url}: {exc}") from exc

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise EsclError(f"Respons eSCL bukan XML valid dari {base_url}: {exc}") from exc

    model_element = _find_first(root, "MakeAndModel")
    model = model_element.text.strip() if model_element is not None and model_element.text else "Network Scanner"

    def _int_text(name: str, default: int) -> int:
        element = _find_first(root, name)
        if element is not None and element.text and element.text.strip().isdigit():
            return int(element.text.strip())
        return default

    return EsclCapabilities(
        base_url=base_url,
        model=model,
        max_width=_int_text("MaxWidth", _A4_WIDTH_300),
        max_height=_int_text("MaxHeight", _A4_HEIGHT_300),
        color_modes=_find_all_text(root, "ColorMode"),
    )


def probe_host(host: str, timeout: float = _DEFAULT_TIMEOUT) -> EsclCapabilities:
    host = host.strip()
    if not host:
        raise EsclError("Host scanner kosong")

    # Bila user sudah memberi base URL lengkap, pakai itu langsung.
    if host.startswith("http://") or host.startswith("https://"):
        return fetch_capabilities(host, timeout=timeout)

    errors: List[str] = []
    for template in _BASE_CANDIDATES:
        base_url = template.format(host=host)
        try:
            return fetch_capabilities(base_url, timeout=timeout)
        except EsclError as exc:
            errors.append(str(exc))
    raise EsclError(
        f"Scanner eSCL tidak ditemukan di {host}. Pastikan AirPrint/eSCL aktif. Detail: {'; '.join(errors)}"
    )


def _build_scan_settings(options: ScanOptions, caps: EsclCapabilities) -> bytes:
    dpi = max(75, min(int(options.dpi), 600))
    color_mode = COLOR_MODE_MAP.get(options.color_mode.lower(), "RGB24")
    if caps.color_modes and color_mode not in caps.color_modes:
        # Fallback ke mode pertama yang didukung scanner.
        color_mode = caps.color_modes[0]
    width = caps.max_width or _A4_WIDTH_300
    height = caps.max_height or _A4_HEIGHT_300

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<scan:ScanSettings '
        'xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" '
        'xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">\n'
        "  <pwg:Version>2.6</pwg:Version>\n"
        "  <scan:Intent>Document</scan:Intent>\n"
        "  <pwg:ScanRegions>\n"
        "    <pwg:ScanRegion>\n"
        f"      <pwg:Height>{height}</pwg:Height>\n"
        f"      <pwg:Width>{width}</pwg:Width>\n"
        "      <pwg:XOffset>0</pwg:XOffset>\n"
        "      <pwg:YOffset>0</pwg:YOffset>\n"
        "    </pwg:ScanRegion>\n"
        "  </pwg:ScanRegions>\n"
        "  <pwg:InputSource>Platen</pwg:InputSource>\n"
        f"  <scan:ColorMode>{color_mode}</scan:ColorMode>\n"
        f"  <scan:XResolution>{dpi}</scan:XResolution>\n"
        f"  <scan:YResolution>{dpi}</scan:YResolution>\n"
        "  <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>\n"
        "</scan:ScanSettings>\n"
    ).encode("utf-8")


def _resolve_job_url(base_url: str, location: str) -> str:
    if location.startswith("http://") or location.startswith("https://"):
        return location.rstrip("/")
    return f"{base_url}/{location.strip('/')}"


def scan_escl(
    base_url: str,
    output_path: Path,
    options: ScanOptions,
    caps: Optional[EsclCapabilities] = None,
    timeout: float = 60.0,
) -> Path:
    base_url = base_url.rstrip("/")
    if caps is None:
        caps = fetch_capabilities(base_url)

    settings = _build_scan_settings(options, caps)
    scan_jobs_url = f"{base_url}/eSCL/ScanJobs"

    try:
        response = _http_post(scan_jobs_url, settings, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise EsclError(f"Scanner menolak job scan (HTTP {exc.code}): {exc.reason}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise EsclError(f"Gagal mengirim job scan ke {base_url}: {exc}") from exc

    with response:
        location = response.headers.get("Location")
        if not location:
            raise EsclError("Scanner tidak mengembalikan lokasi job (header Location kosong)")

    job_url = _resolve_job_url(base_url, location)
    document_url = f"{job_url}/NextDocument"

    try:
        image_bytes = _http_get(document_url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise EsclError(f"Gagal mengambil hasil scan (HTTP {exc.code}): {exc.reason}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise EsclError(f"Gagal mengambil hasil scan dari {document_url}: {exc}") from exc

    if not image_bytes:
        raise EsclError("Scanner mengembalikan dokumen kosong")

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    requested_format = options.image_format.lower()
    if requested_format in {"jpeg", "jpg"}:
        output_path.write_bytes(image_bytes)
        return output_path

    # Format lain (png/bmp/tiff): konversi dari JPEG hasil scanner via PIL.
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            save_format = {"tiff": "TIFF", "bmp": "BMP", "png": "PNG"}.get(requested_format, "JPEG")
            converted = image.convert("RGB") if save_format in {"JPEG", "BMP"} else image
            converted.save(output_path, format=save_format)
    except Exception as exc:  # noqa: BLE001 - PIL bisa lempar banyak tipe error
        raise EsclError(f"Gagal mengonversi hasil scan ke {requested_format}: {exc}") from exc

    return output_path


@dataclass(slots=True)
class NetworkScannerEntry:
    host: str
    base_url: str
    name: str


class NetworkScannerStore:
    """Persistensi daftar scanner jaringan eSCL ke file JSON."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or self._default_config_path()
        self.entries: List[NetworkScannerEntry] = []
        self.load()

    @staticmethod
    def _default_config_path() -> Path:
        base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home()
        return root / "RunLabScanner" / "network_scanners.json"

    def load(self) -> None:
        self.entries = []
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for item in data if isinstance(data, list) else []:
            try:
                self.entries.append(
                    NetworkScannerEntry(
                        host=str(item["host"]),
                        base_url=str(item["base_url"]),
                        name=str(item.get("name") or item["host"]),
                    )
                )
            except (KeyError, TypeError):
                continue

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"host": entry.host, "base_url": entry.base_url, "name": entry.name}
            for entry in self.entries
        ]
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, entry: NetworkScannerEntry) -> None:
        for existing in self.entries:
            if existing.base_url == entry.base_url:
                existing.host = entry.host
                existing.name = entry.name
                self.save()
                return
        self.entries.append(entry)
        self.save()

    def remove(self, base_url: str) -> None:
        self.entries = [entry for entry in self.entries if entry.base_url != base_url]
        self.save()


def device_id_for(base_url: str) -> str:
    return f"{NETWORK_DEVICE_PREFIX}{base_url.rstrip('/')}"


def base_url_from_device_id(device_id: str) -> str:
    return device_id[len(NETWORK_DEVICE_PREFIX):]


def is_network_device(device_id: str) -> bool:
    return device_id.startswith(NETWORK_DEVICE_PREFIX)
