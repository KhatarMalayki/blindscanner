from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


class WIAError(RuntimeError):
    pass


@dataclass(slots=True)
class ScannerDevice:
    device_id: str
    name: str
    type: str


@dataclass(slots=True)
class ScanOptions:
    image_format: str = "jpeg"
    dpi: int = 200
    color_mode: str = "color"
    brightness: int = 0
    contrast: int = 0


FORMAT_MAP = {
    "bmp": "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}",
    "jpeg": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
    "jpg": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
    "png": "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}",
    "tiff": "{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}",
}


def _run_powershell(script: str) -> str:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Unknown PowerShell error"
        raise WIAError(message)
    return result.stdout.strip()


class WIAScannerService:

    def list_devices(self) -> List[ScannerDevice]:
        script = r"""
$ErrorActionPreference = 'Stop'
$manager = New-Object -ComObject WIA.DeviceManager
$items = foreach ($info in $manager.DeviceInfos) {
    [PSCustomObject]@{
        device_id = [string]$info.DeviceID
        name = [string]$info.Properties['Name'].Value
        type = [string]$info.Type
    }
}
$items | ConvertTo-Json -Depth 3
"""
        output = _run_powershell(script)
        if not output:
            return []
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
        return [
            ScannerDevice(
                device_id=item["device_id"],
                name=item["name"],
                type=item["type"],
            )
            for item in data
        ]

    def scan(self, device_id: str, output_path: Path, options: ScanOptions | None=None, image_format: str | None=None) -> Path:
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

        fmt = FORMAT_MAP.get(options.image_format.lower())
        if not fmt:
            raise WIAError(f"Unsupported format: {options.image_format}")

        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        escaped_device_id = device_id.replace("'", "''")
        escaped_output = str(output_path).replace("'", "''")
        escaped_format = fmt.replace("'", "''")
        dpi = max(75, min(int(options.dpi), 600))
        brightness = max(-1000, min(int(options.brightness), 1000))
        contrast = max(-1000, min(int(options.contrast), 1000))
        color_mode_map = {"color": 1, "grayscale": 2, "bw": 4, "blackwhite": 4}
        color_mode = color_mode_map.get(options.color_mode.lower())
        if color_mode is None:
            raise WIAError(f"Unsupported color mode: {options.color_mode}")

        script = rf"""
$ErrorActionPreference = 'Stop'
$targetDeviceId = '{escaped_device_id}'
$outputFile = '{escaped_output}'
$formatId = '{escaped_format}'
$dpi = {dpi}
$brightness = {brightness}
$contrast = {contrast}
$colorMode = {color_mode}
$manager = New-Object -ComObject WIA.DeviceManager
$deviceInfo = $null
foreach ($info in $manager.DeviceInfos) {{
    if ([string]$info.DeviceID -eq $targetDeviceId) {{
        $deviceInfo = $info
        break
    }}
}}
if ($null -eq $deviceInfo) {{
    throw "Scanner device not found: $targetDeviceId"
}}
$device = $deviceInfo.Connect()
if ($device.Items.Count -lt 1) {{
    throw "Scanner device has no items to scan"
}}
$item = $device.Items.Item(1)
try {{ $item.Properties['6147'].Value = $colorMode }} catch {{}}
try {{ $item.Properties['6148'].Value = $dpi }} catch {{}}
try {{ $item.Properties['6149'].Value = $dpi }} catch {{}}
try {{ $item.Properties['6151'].Value = $brightness }} catch {{}}
try {{ $item.Properties['6152'].Value = $contrast }} catch {{}}
$dialog = New-Object -ComObject WIA.CommonDialog
$image = $dialog.ShowTransfer($item, $formatId, $false)
if ($null -eq $image) {{
    throw 'Scan cancelled or failed'
}}
$image.SaveFile($outputFile)
Write-Output $outputFile
"""
        output = _run_powershell(script)
        if not output:
            raise WIAError("Scanner did not return an output file")
        return Path(output)
