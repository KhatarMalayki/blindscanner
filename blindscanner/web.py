from __future__ import annotations

import json
import secrets
import socket
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from blindscanner.pdf_utils import PDFError, save_pdf_from_jpegs
from blindscanner.wia import ScanOptions, WIAError, WIAScannerService

INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>RunLab Scanner</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f172a;
      --panel: #111827;
      --panel-2: #1f2937;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --success: #22c55e;
      --danger: #ef4444;
      --border: #334155;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: linear-gradient(180deg, #020617, #0f172a);
      color: var(--text);
    }
    .wrap {
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    .panel {
      background: rgba(17, 24, 39, 0.95);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.35);
      margin-bottom: 20px;
    }
    h1, h2, p { margin-top: 0; }
    .muted { color: var(--muted); }
    .grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }
    .row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    button, select, input {
      width: 100%;
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 14px;
    }
    .row button {
      width: auto;
    }
    button.primary {
      background: var(--accent);
      color: #082f49;
      border-color: transparent;
      font-weight: bold;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .status {
      padding: 10px 14px;
      border-radius: 12px;
      background: #0b1220;
      border: 1px solid var(--border);
      white-space: pre-wrap;
    }
    .success { color: var(--success); }
    .danger { color: var(--danger); }
    ul {
      padding-left: 20px;
      margin-bottom: 0;
    }
    li { margin: 8px 0; }
    a { color: var(--accent); }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <h1>RunLab Scanner</h1>
      <p class=\"muted\">Trigger scan dari browser untuk scanner USB yang tersambung ke PC host.</p>
      <div class=\"grid\">
        <div>
          <label for=\"apiKeyInput\">API Key</label>
          <input id=\"apiKeyInput\" type=\"password\" placeholder=\"Masukkan API key\">
        </div>
        <div>
          <label for=\"deviceSelect\">Scanner</label>
          <select id=\"deviceSelect\"></select>
        </div>
        <div>
          <label for=\"formatSelect\">Format</label>
          <select id=\"formatSelect\">
            <option value=\"jpeg\">JPEG</option>
            <option value=\"png\">PNG</option>
            <option value=\"bmp\">BMP</option>
            <option value=\"tiff\">TIFF</option>
            <option value=\"pdf\">PDF</option>
          </select>
        </div>
        <div>
          <label for=\"dpiInput\">DPI</label>
          <input id=\"dpiInput\" type=\"number\" min=\"75\" max=\"600\" value=\"200\">
        </div>
        <div>
          <label for=\"colorModeSelect\">Color Mode</label>
          <select id=\"colorModeSelect\">
            <option value=\"color\">Color</option>
            <option value=\"grayscale\">Grayscale</option>
            <option value=\"bw\">Black & White</option>
          </select>
        </div>
        <div>
          <label for=\"brightnessInput\">Brightness</label>
          <input id=\"brightnessInput\" type=\"number\" min=\"-1000\" max=\"1000\" value=\"0\">
        </div>
        <div>
          <label for=\"contrastInput\">Contrast</label>
          <input id=\"contrastInput\" type=\"number\" min=\"-1000\" max=\"1000\" value=\"0\">
        </div>
      </div>
      <div class=\"row\" style=\"margin-top: 14px;\">
        <button id=\"refreshBtn\">Refresh Devices</button>
        <button id=\"scanBtn\" class=\"primary\">Start Scan</button>
      </div>
      <div id=\"statusBox\" class=\"status\" style=\"margin-top: 14px;\">Ready.</div>
    </div>
    <div class=\"panel\">
      <h2>Hasil Scan</h2>
      <ul id=\"scanList\"></ul>
    </div>
  </div>
  <script>
    const apiKeyInput = document.getElementById('apiKeyInput');
    const deviceSelect = document.getElementById('deviceSelect');
    const formatSelect = document.getElementById('formatSelect');
    const dpiInput = document.getElementById('dpiInput');
    const colorModeSelect = document.getElementById('colorModeSelect');
    const brightnessInput = document.getElementById('brightnessInput');
    const contrastInput = document.getElementById('contrastInput');
    const scanBtn = document.getElementById('scanBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    const statusBox = document.getElementById('statusBox');
    const scanList = document.getElementById('scanList');

    function setStatus(text, cls='') {
      statusBox.className = 'status ' + cls;
      statusBox.textContent = text;
    }

    function apiHeaders() {
      const headers = {};
      if (apiKeyInput.value.trim()) {
        headers['X-API-Key'] = apiKeyInput.value.trim();
      }
      return headers;
    }

    async function loadDevices() {
      setStatus('Memuat device...');
      const res = await fetch('/api/devices', { headers: apiHeaders() });
      const devices = await res.json();
      if (!res.ok) {
        setStatus(devices.error || 'Gagal memuat device.', 'danger');
        return;
      }
      deviceSelect.innerHTML = '';
      for (const device of devices) {
        const option = document.createElement('option');
        option.value = device.device_id;
        option.textContent = device.name;
        deviceSelect.appendChild(option);
      }
      if (!devices.length) {
        const option = document.createElement('option');
        option.textContent = 'Tidak ada scanner terdeteksi';
        option.value = '';
        deviceSelect.appendChild(option);
      }
      setStatus('Device siap.', devices.length ? 'success' : 'danger');
    }

    async function loadScans() {
      const res = await fetch('/api/scans', { headers: apiHeaders() });
      const scans = await res.json();
      if (!res.ok) {
        setStatus(scans.error || 'Gagal memuat hasil scan.', 'danger');
        return;
      }
      scanList.innerHTML = '';
      if (!scans.length) {
        scanList.innerHTML = '<li class="muted">Belum ada hasil scan.</li>';
        return;
      }
      for (const scan of scans) {
        const li = document.createElement('li');
        const a = document.createElement('a');
        const url = new URL(scan.download_url, window.location.origin);
        if (apiKeyInput.value.trim()) {
          url.searchParams.set('api_key', apiKeyInput.value.trim());
        }
        a.href = url.toString();
        a.textContent = `${scan.filename} (${scan.created_at})`;
        a.target = '_blank';
        li.appendChild(a);
        scanList.appendChild(li);
      }
    }

    async function startScan() {
      const deviceId = deviceSelect.value;
      if (!deviceId) {
        setStatus('Pilih scanner terlebih dahulu.', 'danger');
        return;
      }
      scanBtn.disabled = true;
      setStatus('Scanning... tunggu sampai proses pada host selesai.');
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiHeaders() },
        body: JSON.stringify({
          device_id: deviceId,
          format: formatSelect.value,
          dpi: Number(dpiInput.value || 200),
          color_mode: colorModeSelect.value,
          brightness: Number(brightnessInput.value || 0),
          contrast: Number(contrastInput.value || 0)
        })
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || 'Scan gagal.', 'danger');
        scanBtn.disabled = false;
        return;
      }
      setStatus(`Scan berhasil: ${data.filename}`, 'success');
      scanBtn.disabled = false;
      await loadScans();
    }

    refreshBtn.addEventListener('click', async () => {
      await loadDevices();
      await loadScans();
    });
    scanBtn.addEventListener('click', startScan);
    apiKeyInput.addEventListener('change', async () => {
      await loadDevices();
      await loadScans();
    });

    loadDevices().then(loadScans);
  </script>
</body>
</html>
"""


@dataclass(slots=True)
class AppState:
    scanner_service: WIAScannerService
    output_dir: Path
    selected_device_id_getter: Callable[[], Optional[str]]
    default_scan_options_getter: Callable[[], ScanOptions]
    api_key_getter: Callable[[], str]
    log_callback: Callable[[str], None]
    scan_lock: threading.Lock


def get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class BlindScannerHandler(BaseHTTPRequestHandler):
    server_version = "RunLabScanner/1.0"

    def __init__(self, *args, app_state: AppState, **kwargs):
        self.app_state = app_state
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        self.app_state.log_callback(format % args)

    def _send_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _request_api_key(self) -> str:
        parsed = urlparse(self.path)
        query = parsed.query
        params = {}
        for part in query.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key] = value
        return self.headers.get("X-API-Key", "") or params.get("api_key", "")

    def _is_authorized(self) -> bool:
        expected = self.app_state.api_key_getter().strip()
        if not expected:
            return True
        provided = self._request_api_key().strip()
        return secrets.compare_digest(provided, expected)

    def _ensure_authorized(self) -> bool:
        if self._is_authorized():
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized. API key required."})
        return False

    def _build_scan_options(self, payload: dict) -> ScanOptions:
        defaults = self.app_state.default_scan_options_getter()
        requested_format = str(payload.get("format") or defaults.image_format).lower()
        actual_format = "jpeg" if requested_format == "pdf" else requested_format
        return ScanOptions(
            image_format=actual_format,
            dpi=int(payload.get("dpi") or defaults.dpi),
            color_mode=str(payload.get("color_mode") or defaults.color_mode),
            brightness=int(payload.get("brightness") or defaults.brightness),
            contrast=int(payload.get("contrast") or defaults.contrast),
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
            return
        if parsed.path.startswith("/api/") or parsed.path.startswith("/downloads/"):
            if not self._ensure_authorized():
                return
        if parsed.path == "/api/status":
            self._send_json(
                HTTPStatus.OK,
                {
                    "selected_device_id": self.app_state.selected_device_id_getter(),
                    "output_dir": str(self.app_state.output_dir),
                    "requires_api_key": bool(self.app_state.api_key_getter().strip()),
                    "default_scan_options": asdict(self.app_state.default_scan_options_getter()),
                },
            )
            return
        if parsed.path == "/api/devices":
            try:
                devices = self.app_state.scanner_service.list_devices()
                self._send_json(HTTPStatus.OK, [asdict(device) for device in devices])
            except WIAError as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        if parsed.path == "/api/scans":
            scans = []
            for file_path in sorted(self.app_state.output_dir.glob("scan_*"), reverse=True):
                scans.append(
                    {
                        "filename": file_path.name,
                        "created_at": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "download_url": f"/downloads/{file_path.name}",
                    }
                )
            self._send_json(HTTPStatus.OK, scans)
            return
        if parsed.path.startswith("/downloads/"):
            filename = Path(parsed.path.removeprefix("/downloads/")).name
            file_path = self.app_state.output_dir / filename
            if not file_path.exists():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
                return
            self._send_file(file_path)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/scan":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not self._ensure_authorized():
            return

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
            return

        device_id = payload.get("device_id") or self.app_state.selected_device_id_getter()
        requested_format = str(payload.get("format") or self.app_state.default_scan_options_getter().image_format).lower()
        scan_options = self._build_scan_options(payload)
        if not device_id:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No scanner device selected"})
            return

        if not self.app_state.scan_lock.acquire(blocking=False):
            self._send_json(HTTPStatus.CONFLICT, {"error": "Scanner is busy"})
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extension = "jpg" if scan_options.image_format in {"jpeg", "jpg"} else scan_options.image_format
            output_path = self.app_state.output_dir / f"scan_{timestamp}.{extension}"
            self.app_state.log_callback(
                f"Scan requested via web for device {device_id} format={requested_format} dpi={scan_options.dpi} mode={scan_options.color_mode}"
            )
            saved_path = self.app_state.scanner_service.scan(device_id, output_path, options=scan_options)
            final_path = saved_path
            if requested_format == "pdf":
                pdf_path = self.app_state.output_dir / f"scan_{timestamp}.pdf"
                try:
                    final_path = save_pdf_from_jpegs([saved_path], pdf_path)
                    saved_path.unlink(missing_ok=True)
                except PDFError as exc:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                    return
            self._send_json(
                HTTPStatus.OK,
                {
                    "filename": final_path.name,
                    "download_url": f"/downloads/{final_path.name}",
                },
            )
        except WIAError as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        finally:
            self.app_state.scan_lock.release()


class BlindScannerServer:

    def __init__(
        self,
        host: str,
        port: int,
        scanner_service: WIAScannerService,
        output_dir: Path,
        selected_device_id_getter: Callable[[], Optional[str]],
        default_scan_options_getter: Callable[[], ScanOptions],
        api_key_getter: Callable[[], str],
        log_callback: Callable[[str], None],
    ) -> None:
        self.host = host
        self.port = port
        self.output_dir = output_dir
        self.app_state = AppState(
            scanner_service=scanner_service,
            output_dir=output_dir,
            selected_device_id_getter=selected_device_id_getter,
            default_scan_options_getter=default_scan_options_getter,
            api_key_getter=api_key_getter,
            log_callback=log_callback,
            scan_lock=threading.Lock(),
        )
        handler = partial(BlindScannerHandler, app_state=self.app_state)
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
