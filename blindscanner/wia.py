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
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=creationflags,
        startupinfo=startupinfo,
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
        # WIA SaveFile gagal bila file tujuan sudah ada. Hapus dulu jika ada.
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        escaped_device_id = device_id.replace("'", "''")
        escaped_output = str(output_path).replace("'", "''")
        escaped_format = fmt.replace("'", "''")
        dpi = max(75, min(int(options.dpi), 600))
        brightness = max(-1000, min(int(options.brightness), 1000))
        contrast = max(-1000, min(int(options.contrast), 1000))
        # WIA intent (current intent / 6146): bitmask.
        #   1 = color, 2 = grayscale, 4 = text/bw
        intent_map = {"color": 1, "grayscale": 2, "bw": 4, "blackwhite": 4}
        intent = intent_map.get(options.color_mode.lower())
        if intent is None:
            raise WIAError(f"Unsupported color mode: {options.color_mode}")

        script = rf"""
$ErrorActionPreference = 'Stop'
$targetDeviceId = '{escaped_device_id}'
$outputFile = '{escaped_output}'
$formatId = '{escaped_format}'
$dpi = {dpi}
$brightness = {brightness}
$contrast = {contrast}
$intent = {intent}
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

function Set-WiaProperty($props, $id, $value) {{
    foreach ($p in $props) {{
        if ($p.PropertyID -eq $id) {{
            try {{ $p.Value = $value }} catch {{}}
            return
        }}
    }}
}}

# 6146 = Current Intent (color/grayscale/text)
Set-WiaProperty $item.Properties 6146 $intent
# 6147/6148 = X/Y Resolution (DPI) - HARUS sama agar tidak melar
Set-WiaProperty $item.Properties 6147 $dpi
Set-WiaProperty $item.Properties 6148 $dpi
# 6149/6150 = X/Y Start position = 0
Set-WiaProperty $item.Properties 6149 0
Set-WiaProperty $item.Properties 6150 0

# Hitung extent maksimum dari kapabilitas horizontal/vertikal bed scanner.
# 6151/6152 = X/Y Extent (lebar/tinggi area scan dalam pixel).
$maxX = $null; $maxY = $null
foreach ($p in $item.Properties) {{
    if ($p.PropertyID -eq 6151) {{ $curX = $p }}
    if ($p.PropertyID -eq 6152) {{ $curY = $p }}
}}
# Horizontal/Vertical bed size (1/1000 inch): 3076 / 3077
$bedW = $null; $bedH = $null
foreach ($p in $device.Properties) {{
    if ($p.PropertyID -eq 3076) {{ $bedW = $p.Value }}
    if ($p.PropertyID -eq 3077) {{ $bedH = $p.Value }}
}}
if ($bedW -and $bedH) {{
    $extX = [int]([math]::Floor($bedW / 1000.0 * $dpi))
    $extY = [int]([math]::Floor($bedH / 1000.0 * $dpi))
}} else {{
    # Fallback A4: 8.27 x 11.69 inch
    $extX = [int]([math]::Floor(8.27 * $dpi))
    $extY = [int]([math]::Floor(11.69 * $dpi))
}}
Set-WiaProperty $item.Properties 6151 $extX
Set-WiaProperty $item.Properties 6152 $extY
# 6154/6155 = Brightness/Contrast
Set-WiaProperty $item.Properties 6154 $brightness
Set-WiaProperty $item.Properties 6155 $contrast

$dialog = New-Object -ComObject WIA.CommonDialog
$image = $dialog.ShowTransfer($item, $formatId, $false)
if ($null -eq $image) {{
    throw 'Scan cancelled or failed'
}}
if (Test-Path $outputFile) {{ Remove-Item $outputFile -Force }}
$image.SaveFile($outputFile)
Write-Output $outputFile
"""
        output = _run_powershell(script)
        if not output:
            raise WIAError("Scanner did not return an output file")
        return Path(output.splitlines()[-1].strip())
