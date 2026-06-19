from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from blindscanner.escl import (
    EsclError,
    NetworkScannerEntry,
    NetworkScannerStore,
    base_url_from_device_id,
    device_id_for,
    fetch_capabilities,
    is_network_device,
    probe_host,
    scan_escl,
)
from blindscanner.wia import ScannerDevice, ScanOptions, WIAError, WIAScannerService


class UnifiedScannerService:
    """Menggabungkan scanner WIA (USB lokal) dan scanner jaringan eSCL/AirScan.

    Kompatibel dengan antarmuka WIAScannerService (list_devices + scan) sehingga
    bisa dipakai langsung oleh web server dan UI tanpa perubahan besar.
    """

    def __init__(
        self,
        wia_service: Optional[WIAScannerService] = None,
        network_store: Optional[NetworkScannerStore] = None,
    ) -> None:
        self.wia_service = wia_service or WIAScannerService()
        self.network_store = network_store or NetworkScannerStore()

    def list_devices(self) -> List[ScannerDevice]:
        devices: List[ScannerDevice] = []

        try:
            devices.extend(self.wia_service.list_devices())
        except WIAError:
            # WIA bisa gagal (mis. tidak ada COM/driver). Tetap lanjut ke jaringan.
            pass

        for entry in self.network_store.entries:
            devices.append(
                ScannerDevice(
                    device_id=device_id_for(entry.base_url),
                    name=f"{entry.name} (Jaringan)",
                    type="Network/eSCL",
                )
            )
        return devices

    def add_network_scanner(self, host: str) -> NetworkScannerEntry:
        caps = probe_host(host)
        entry = NetworkScannerEntry(host=host, base_url=caps.base_url, name=caps.model)
        self.network_store.add(entry)
        return entry

    def remove_network_scanner(self, base_url: str) -> None:
        self.network_store.remove(base_url)

    def scan(
        self,
        device_id: str,
        output_path: Path,
        options: ScanOptions | None = None,
        image_format: str | None = None,
    ) -> Path:
        if is_network_device(device_id):
            return self._scan_network(device_id, output_path, options, image_format)
        return self.wia_service.scan(device_id, output_path, options=options, image_format=image_format)

    def _scan_network(
        self,
        device_id: str,
        output_path: Path,
        options: ScanOptions | None,
        image_format: str | None,
    ) -> Path:
        if options is None:
            options = ScanOptions(image_format=image_format or "jpeg")
        elif image_format:
            options = ScanOptions(
                image_format=image_format,
                dpi=options.dpi,
                color_mode=options.color_mode,
                brightness=options.brightness,
                contrast=options.contrast,
            )

        base_url = base_url_from_device_id(device_id)
        try:
            caps = fetch_capabilities(base_url)
            return scan_escl(base_url, output_path, options, caps=caps)
        except EsclError as exc:
            # Bungkus sebagai WIAError supaya layer atas (web/app) menangani seragam.
            raise WIAError(str(exc)) from exc
