from __future__ import annotations

import queue
import secrets
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw
import pystray

from blindscanner import __version__
from blindscanner.config import get_license_api_url, get_license_signing_key
from blindscanner.license_client import LicenseClient, LicenseError, LicenseStatus
from blindscanner.machine import get_machine_id
from blindscanner.pdf_utils import PDFError, save_pdf_from_jpegs
from blindscanner.updater import (
    UpdateError,
    UpdateManifest,
    create_update_script,
    download_update,
    fetch_licensed_update_manifest,
    fetch_update_manifest,
    get_current_executable,
    is_newer_version,
    launch_update_installer,
)
from blindscanner.escl import EsclError
from blindscanner.service import UnifiedScannerService
from blindscanner.web import BlindScannerServer, get_local_ip
from blindscanner.wia import ScanOptions, ScannerDevice, WIAError


class BlindScannerApp:

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"RunLab Scanner Desktop v{__version__}")
        self.root.geometry("860x760")
        self.root.minsize(860, 760)

        self.scanner_service = UnifiedScannerService()
        self.license_client = LicenseClient(
            api_base_url=get_license_api_url(),
            signing_key=get_license_signing_key(),
        )
        self.license_status: LicenseStatus | None = None
        self.server: BlindScannerServer | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.devices: list[ScannerDevice] = []
        self.tray_icon: pystray.Icon | None = None
        self.tray_thread: threading.Thread | None = None
        self.is_quitting = False
        self.update_check_in_progress = False

        self.host_var = tk.StringVar(value=get_local_ip())
        self.port_var = tk.StringVar(value="8765")
        self.output_dir_var = tk.StringVar(value=str((Path.cwd() / "scans").resolve()))
        self.selected_device_var = tk.StringVar()
        self.network_host_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value=f"Ready | v{__version__}")
        self.url_var = tk.StringVar(value="Server belum berjalan")
        self.default_format_var = tk.StringVar(value="jpeg")
        self.dpi_var = tk.StringVar(value="200")
        self.color_mode_var = tk.StringVar(value="color")
        self.brightness_var = tk.StringVar(value="0")
        self.contrast_var = tk.StringVar(value="0")
        self.api_key_var = tk.StringVar(value=secrets.token_urlsafe(16))
        self.update_manifest_url_var = tk.StringVar(value="")
        self.version_var = tk.StringVar(value=f"Versi saat ini: {__version__}")
        self.license_status_var = tk.StringVar(value="License: belum diperiksa")

        self._build_ui()
        self._apply_window_icon()
        self._poll_logs()
        self.refresh_devices()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(200, self._startup_license_check)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text="RunLab Scanner Desktop", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            frame,
            text="Share scanner USB/WIA dari PC host ke browser perangkat lain di jaringan lokal.",
        )
        subtitle.pack(anchor="w", pady=(4, 16))

        config = ttk.LabelFrame(frame, text="Konfigurasi Server", padding=12)
        config.pack(fill="x")

        ttk.Label(config, text="Host").grid(row=0, column=0, sticky="w")
        ttk.Entry(config, textvariable=self.host_var, width=24).grid(row=0, column=1, sticky="we", padx=(8, 12))
        ttk.Label(config, text="Port").grid(row=0, column=2, sticky="w")
        ttk.Entry(config, textvariable=self.port_var, width=10).grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Label(config, text="Output Folder").grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(config, textvariable=self.output_dir_var).grid(row=1, column=1, columnspan=2, sticky="we", padx=(8, 12), pady=(12, 0))
        ttk.Button(config, text="Browse", command=self.choose_output_dir).grid(row=1, column=3, sticky="w", pady=(12, 0))

        ttk.Label(config, text="API Key").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(config, textvariable=self.api_key_var).grid(row=2, column=1, columnspan=2, sticky="we", padx=(8, 12), pady=(12, 0))
        ttk.Button(config, text="Generate", command=self.generate_api_key).grid(row=2, column=3, sticky="w", pady=(12, 0))

        ttk.Label(config, text="Update Manifest URL").grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(config, textvariable=self.update_manifest_url_var).grid(row=3, column=1, columnspan=2, sticky="we", padx=(8, 12), pady=(12, 0))
        ttk.Button(config, text="Check Update", command=self.check_for_updates).grid(row=3, column=3, sticky="w", pady=(12, 0))

        config.columnconfigure(1, weight=1)
        config.columnconfigure(2, weight=1)

        scanner = ttk.LabelFrame(frame, text="Scanner", padding=12)
        scanner.pack(fill="x", pady=(16, 0))

        ttk.Label(scanner, text="Perangkat").grid(row=0, column=0, sticky="w")
        self.device_combo = ttk.Combobox(scanner, textvariable=self.selected_device_var, state="readonly")
        self.device_combo.grid(row=0, column=1, sticky="we", padx=(8, 12))
        ttk.Button(scanner, text="Refresh Devices", command=self.refresh_devices).grid(row=0, column=2, sticky="w")

        ttk.Label(scanner, text="Scanner Jaringan (IP)").grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(scanner, textvariable=self.network_host_var).grid(row=1, column=1, sticky="we", padx=(8, 12), pady=(12, 0))
        network_buttons = ttk.Frame(scanner)
        network_buttons.grid(row=1, column=2, sticky="w", pady=(12, 0))
        ttk.Button(network_buttons, text="Tambah", command=self.add_network_scanner).pack(side="left")
        ttk.Button(network_buttons, text="Hapus", command=self.remove_network_scanner).pack(side="left", padx=(8, 0))
        scanner.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(frame, text="Default Scan Options", padding=12)
        options.pack(fill="x", pady=(16, 0))

        ttk.Label(options, text="Format").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options, textvariable=self.default_format_var, state="readonly", values=["jpeg", "png", "bmp", "tiff", "pdf"]).grid(row=0, column=1, sticky="we", padx=(8, 12))
        ttk.Label(options, text="DPI").grid(row=0, column=2, sticky="w")
        ttk.Entry(options, textvariable=self.dpi_var, width=10).grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Label(options, text="Color Mode").grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Combobox(options, textvariable=self.color_mode_var, state="readonly", values=["color", "grayscale", "bw"]).grid(row=1, column=1, sticky="we", padx=(8, 12), pady=(12, 0))
        ttk.Label(options, text="Brightness").grid(row=1, column=2, sticky="w", pady=(12, 0))
        ttk.Entry(options, textvariable=self.brightness_var, width=10).grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(12, 0))

        ttk.Label(options, text="Contrast").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(options, textvariable=self.contrast_var, width=10).grid(row=2, column=1, sticky="w", padx=(8, 12), pady=(12, 0))
        options.columnconfigure(1, weight=1)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(16, 0))
        ttk.Button(controls, text="Start Server", command=self.start_server).pack(side="left")
        ttk.Button(controls, text="Stop Server", command=self.stop_server).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Test Scan Lokal", command=self.test_scan).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Minimize to Tray", command=self.minimize_to_tray).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="License", command=self.manage_license).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Install Update", command=self.check_for_updates).pack(side="left", padx=(8, 0))

        info = ttk.LabelFrame(frame, text="Status", padding=12)
        info.pack(fill="x", pady=(16, 0))
        ttk.Label(info, textvariable=self.status_var).pack(anchor="w")
        ttk.Label(info, textvariable=self.license_status_var, foreground="#22c55e").pack(anchor="w", pady=(6, 0))
        ttk.Label(info, textvariable=self.version_var).pack(anchor="w", pady=(6, 0))
        ttk.Label(info, textvariable=self.url_var, foreground="#0a84ff").pack(anchor="w", pady=(6, 0))

        logs = ttk.LabelFrame(frame, text="Log", padding=12)
        logs.pack(fill="both", expand=True, pady=(16, 0))
        self.log_text = tk.Text(logs, height=18, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _create_app_image(self, size: int=64) -> Image.Image:
        image = Image.new("RGBA", (size, size), (15, 23, 42, 255))
        draw = ImageDraw.Draw(image)
        pad = max(4, size // 10)
        draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=size // 6, fill=(17, 24, 39, 255), outline=(56, 189, 248, 255), width=max(2, size // 16))
        draw.rounded_rectangle([size * 0.3, size * 0.18, size * 0.7, size * 0.48], radius=size // 12, fill=(56, 189, 248, 220))
        draw.rectangle([size * 0.22, size * 0.6, size * 0.78, size * 0.72], fill=(148, 163, 184, 255))
        draw.rectangle([size * 0.28, size * 0.76, size * 0.72, size * 0.9], fill=(229, 231, 235, 255))
        draw.rectangle([size * 0.34, size * 0.81, size * 0.66, size * 0.84], fill=(56, 189, 248, 255))
        return image

    def _apply_window_icon(self) -> None:
        icon_path = Path.cwd() / "assets" / "blindscanner.png"
        if icon_path.exists():
            try:
                icon_image = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, icon_image)
                self.root._icon_photo = icon_image
                return
            except tk.TclError:
                pass
        try:
            fallback = self._create_app_image(64)
            temp_path = Path.cwd() / "assets" / "blindscanner_runtime.png"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            fallback.save(temp_path)
            icon_image = tk.PhotoImage(file=str(temp_path))
            self.root.iconphoto(True, icon_image)
            self.root._icon_photo = icon_image
        except Exception:
            return

    def _append_log(self, message: str) -> None:
        self.log_queue.put(message)

    def _poll_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"{message}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(150, self._poll_logs)

    def choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if selected:
            self.output_dir_var.set(selected)

    def generate_api_key(self) -> None:
        self.api_key_var.set(secrets.token_urlsafe(16))
        self._append_log("Generated new API key")

    def refresh_devices(self) -> None:
        try:
            self.devices = self.scanner_service.list_devices()
        except WIAError as exc:
            self.status_var.set(f"Gagal membaca scanner: {exc}")
            self._append_log(f"ERROR: {exc}")
            return

        names = [device.name for device in self.devices]
        self.device_combo["values"] = names
        if names:
            self.device_combo.current(0)
            self.selected_device_var.set(names[0])
            self.status_var.set(f"{len(names)} scanner terdeteksi")
            self._append_log(f"Detected scanners: {', '.join(names)}")
        else:
            self.selected_device_var.set("")
            self.status_var.set("Tidak ada scanner WIA terdeteksi")
            self._append_log("No WIA scanner detected")

    def add_network_scanner(self) -> None:
        host = self.network_host_var.get().strip()
        if not host:
            messagebox.showerror("Error", "Masukkan IP atau hostname scanner jaringan.")
            return
        self.status_var.set(f"Mencari scanner eSCL di {host}...")
        self._append_log(f"Probing network scanner at {host}")
        self.root.update_idletasks()
        try:
            entry = self.scanner_service.add_network_scanner(host)
        except EsclError as exc:
            self.status_var.set(f"Scanner jaringan gagal ditambah: {exc}")
            self._append_log(f"Network scanner probe failed: {exc}")
            messagebox.showerror("Gagal", str(exc))
            return
        self.network_host_var.set("")
        self._append_log(f"Network scanner added: {entry.name} ({entry.base_url})")
        messagebox.showinfo("Berhasil", f"Scanner jaringan ditambahkan:\n{entry.name}\n{entry.base_url}")
        self.refresh_devices()

    def remove_network_scanner(self) -> None:
        from blindscanner.escl import base_url_from_device_id, is_network_device

        device = self.get_selected_device()
        if device is None or not is_network_device(device.device_id):
            messagebox.showerror("Error", "Pilih scanner jaringan yang ingin dihapus dari daftar perangkat.")
            return
        base_url = base_url_from_device_id(device.device_id)
        self.scanner_service.remove_network_scanner(base_url)
        self._append_log(f"Network scanner removed: {base_url}")
        self.refresh_devices()

    def get_selected_device(self) -> ScannerDevice | None:
        selected_name = self.selected_device_var.get()
        for device in self.devices:
            if device.name == selected_name:
                return device
        return self.devices[0] if self.devices else None

    def get_selected_device_id(self) -> str | None:
        device = self.get_selected_device()
        return device.device_id if device else None

    def get_default_scan_options(self) -> ScanOptions:
        try:
            dpi = int(self.dpi_var.get())
            brightness = int(self.brightness_var.get())
            contrast = int(self.contrast_var.get())
        except ValueError as exc:
            raise WIAError("DPI, brightness, dan contrast harus berupa angka") from exc
        return ScanOptions(
            image_format=self.default_format_var.get() or "jpeg",
            dpi=dpi,
            color_mode=self.color_mode_var.get() or "color",
            brightness=brightness,
            contrast=contrast,
        )

    def start_server(self) -> None:
        if not self.has_valid_license():
            messagebox.showerror("Error", "License belum aktif. Aktifkan license dulu untuk menjalankan server.")
            self._prompt_activation()
            if not self.has_valid_license():
                return

        if self.server is not None:
            messagebox.showinfo("Info", "Server sudah berjalan.")
            return

        device = self.get_selected_device()
        if device is None:
            messagebox.showerror("Error", "Tidak ada scanner yang dipilih.")
            return

        try:
            port = int(self.port_var.get())
            default_options = self.get_default_scan_options()
        except ValueError:
            messagebox.showerror("Error", "Port harus berupa angka.")
            return
        except WIAError as exc:
            messagebox.showerror("Error", str(exc))
            return

        output_dir = Path(self.output_dir_var.get()).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.server = BlindScannerServer(
                host=self.host_var.get().strip() or "0.0.0.0",
                port=port,
                scanner_service=self.scanner_service,
                output_dir=output_dir,
                selected_device_id_getter=self.get_selected_device_id,
                default_scan_options_getter=self.get_default_scan_options,
                api_key_getter=lambda: self.api_key_var.get(),
                log_callback=self._append_log,
            )
            self.server.start()
        except OSError as exc:
            self.server = None
            messagebox.showerror("Error", f"Gagal start server: {exc}")
            return

        self.status_var.set(f"Server aktif untuk scanner: {device.name}")
        self.url_var.set(f"Akses dari perangkat lain: {self.server.url} | API Key: {self.api_key_var.get()}")
        self._append_log(
            f"Server started at {self.server.url} format={default_options.image_format} dpi={default_options.dpi} mode={default_options.color_mode}"
        )

    def stop_server(self) -> None:
        if self.server is None:
            return
        self.server.stop()
        self.server = None
        self.status_var.set("Server berhenti")
        self.url_var.set("Server belum berjalan")
        self._append_log("Server stopped")

    def test_scan(self) -> None:
        device = self.get_selected_device()
        if device is None:
            messagebox.showerror("Error", "Tidak ada scanner yang dipilih.")
            return

        output_dir = Path(self.output_dir_var.get()).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        self.status_var.set("Menjalankan test scan lokal...")
        self.root.update_idletasks()

        try:
            options = self.get_default_scan_options()
        except WIAError as exc:
            messagebox.showerror("Error", str(exc))
            return

        extension = "jpg" if options.image_format in {"jpeg", "pdf"} else options.image_format
        output_file = output_dir / f"scan_test.{extension}"

        try:
            saved = self.scanner_service.scan(
                device.device_id,
                output_file,
                options=ScanOptions(
                    image_format="jpeg" if options.image_format == "pdf" else options.image_format,
                    dpi=options.dpi,
                    color_mode=options.color_mode,
                    brightness=options.brightness,
                    contrast=options.contrast,
                ),
            )
            final_saved = saved
            if options.image_format == "pdf":
                pdf_file = output_dir / "scan_test.pdf"
                final_saved = save_pdf_from_jpegs([saved], pdf_file)
                saved.unlink(missing_ok=True)
        except (WIAError, PDFError) as exc:
            self.status_var.set(f"Test scan gagal: {exc}")
            self._append_log(f"Local test scan failed: {exc}")
            messagebox.showerror("Scan gagal", str(exc))
            return

        self.status_var.set(f"Test scan berhasil: {final_saved.name}")
        self._append_log(f"Local test scan saved to {final_saved}")
        messagebox.showinfo("Berhasil", f"Hasil scan tersimpan di:\n{final_saved}")

    def _startup_license_check(self) -> None:
        """Cek license saat startup. Bila belum ada/invalid, minta aktivasi."""
        saved_key = self.license_client.load_saved_key()
        if not saved_key:
            self._append_log("No license found, prompting activation")
            if not self._prompt_activation():
                self._enforce_no_license()
            return

        self.status_var.set("Memeriksa license...")
        self.root.update_idletasks()
        try:
            status = self.license_client.validate(saved_key)
        except LicenseError as exc:
            self._append_log(f"License check error: {exc}")
            status = LicenseStatus(valid=False, status="error", reason=str(exc))

        self.license_status = status
        self._apply_license_status(status)

    def _apply_license_status(self, status: LicenseStatus) -> None:
        if status.valid:
            who = status.customer_name or "Terlisensi"
            suffix = " (offline)" if status.offline else ""
            label = f"License: AKTIF - {who}{suffix}"
            if status.expires_at:
                label += f" | exp {status.expires_at[:10]}"
            self.license_status_var.set(label)
            self._append_log(f"License valid: {status.license_key} status={status.status} offline={status.offline}")
        else:
            reason = status.reason or status.status or "tidak valid"
            self.license_status_var.set(f"License: TIDAK AKTIF ({reason})")
            self._append_log(f"License invalid: {reason}")
            self._enforce_no_license()

    def _enforce_no_license(self) -> None:
        """Tanpa license valid, server tidak boleh jalan."""
        if self.server is not None:
            self.stop_server()
        self.status_var.set("Aplikasi terkunci: license belum aktif.")

    def has_valid_license(self) -> bool:
        return self.license_status is not None and self.license_status.valid

    def _prompt_activation(self) -> bool:
        from tkinter import simpledialog

        key = simpledialog.askstring(
            "Aktivasi License",
            "Masukkan License Key RunLab Scanner:",
            parent=self.root,
        )
        if not key:
            return False
        return self._do_activate(key.strip())

    def _do_activate(self, key: str) -> bool:
        self.status_var.set("Mengaktifkan license...")
        self.root.update_idletasks()
        try:
            status = self.license_client.activate(key)
        except LicenseError as exc:
            messagebox.showerror("Aktivasi gagal", str(exc))
            self._append_log(f"Activation failed: {exc}")
            return False

        self.license_status = status
        if not status.valid:
            messagebox.showerror("Aktivasi gagal", status.reason or status.status or "License tidak valid.")
            self._apply_license_status(status)
            return False

        messagebox.showinfo("Berhasil", f"License aktif untuk {status.customer_name or 'perangkat ini'}.")
        self._apply_license_status(status)
        return True

    def manage_license(self) -> None:
        current = self.license_client.load_saved_key()
        if current and self.has_valid_license():
            change = messagebox.askyesno(
                "License",
                f"License aktif: {current}\n\nGanti dengan license key lain?",
            )
            if not change:
                return
        self._prompt_activation()

    def check_for_updates(self) -> None:
        if not self.has_valid_license():
            messagebox.showerror("Update", "License belum aktif. Aktifkan license dulu untuk cek update.")
            return
        if self.update_check_in_progress:
            messagebox.showinfo("Info", "Pengecekan update sedang berjalan.")
            return
        self.update_check_in_progress = True
        self.status_var.set("Memeriksa update...")
        self._append_log("Checking for updates")
        thread = threading.Thread(target=self._check_for_updates_worker, daemon=True)
        thread.start()

    def _check_for_updates_worker(self) -> None:
        try:
            license_status = self.license_status
            manifest = fetch_licensed_update_manifest(
                api_base_url=get_license_api_url(),
                license_key=license_status.license_key if license_status else "",
                machine_id=get_machine_id(),
                channel=license_status.channel if license_status else "",
            )
            self.root.after(0, lambda: self._handle_update_manifest(manifest))
        except UpdateError as exc:
            self.root.after(0, lambda: self._handle_update_error(str(exc)))

    def _handle_update_manifest(self, manifest: UpdateManifest) -> None:
        self.update_check_in_progress = False
        if not is_newer_version(manifest.version, __version__):
            self.status_var.set(f"RunLab Scanner sudah versi terbaru ({__version__})")
            self._append_log(f"No update available. Current version: {__version__}")
            messagebox.showinfo("Update", f"Tidak ada update baru. Versi saat ini: {__version__}")
            return

        lines = [
            f"Versi baru tersedia: {manifest.version}",
            f"Versi saat ini: {__version__}",
        ]
        if manifest.notes:
            lines.extend(["", "Catatan update:", manifest.notes])
        accepted = messagebox.askyesno("Update tersedia", "\n".join(lines) + "\n\nUnduh dan install sekarang?")
        if not accepted:
            self.status_var.set(f"Update tersedia: {manifest.version}")
            self._append_log(f"Update available but skipped: {manifest.version}")
            return

        self.status_var.set(f"Mengunduh update {manifest.version}...")
        self._append_log(f"Downloading update {manifest.version} from {manifest.url}")
        thread = threading.Thread(target=self._download_and_install_update_worker, args=(manifest,), daemon=True)
        thread.start()

    def _download_and_install_update_worker(self, manifest: UpdateManifest) -> None:
        last_percent = [-1]

        def on_progress(downloaded: int, total: int, percent) -> None:
            mb_done = downloaded / 1048576
            if percent is None:
                msg = f"Mengunduh update {manifest.version}... {mb_done:.1f} MB"
            else:
                # Update status hanya tiap kelipatan 1% agar UI tidak terlalu sering refresh.
                if percent == last_percent[0]:
                    return
                last_percent[0] = percent
                mb_total = total / 1048576
                msg = f"Mengunduh update {manifest.version}... {percent}% ({mb_done:.1f}/{mb_total:.1f} MB)"
            self.root.after(0, lambda: self.status_var.set(msg))

        try:
            downloaded_exe = download_update(manifest.url, manifest.version, progress_callback=on_progress)
            self.root.after(0, lambda: self._apply_downloaded_update(manifest, downloaded_exe))
        except UpdateError as exc:
            self.root.after(0, lambda: self._handle_update_error(str(exc)))

    def _apply_downloaded_update(self, manifest: UpdateManifest, downloaded_exe: Path) -> None:
        try:
            current_exe = get_current_executable()
            if not getattr(sys, "frozen", False):
                raise UpdateError("Auto update penuh hanya didukung dari build EXE. Jalankan dari RunLabScanner.exe.")
            update_script = create_update_script(downloaded_exe, current_exe)
            launch_update_installer(update_script)
        except UpdateError as exc:
            self._handle_update_error(str(exc))
            return

        self.status_var.set(f"Menginstall update {manifest.version}...")
        self._append_log(f"Applying update {manifest.version}")
        messagebox.showinfo("Update", "Update sudah diunduh. Aplikasi akan ditutup untuk menerapkan versi baru.")
        self._quit_app()

    def _handle_update_error(self, message: str) -> None:
        self.update_check_in_progress = False
        self.status_var.set(f"Update gagal: {message}")
        self._append_log(f"Update failed: {message}")
        messagebox.showerror("Update gagal", message)

    def _show_window(self) -> None:
        self.root.after(0, self._show_window_sync)

    def _show_window_sync(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_from_tray(self) -> None:
        self.root.after(0, self._quit_app)

    def _quit_app(self) -> None:
        self.is_quitting = True
        self._stop_tray_icon()
        self.stop_server()
        self.root.destroy()

    def _stop_tray_icon(self) -> None:
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        self.tray_thread = None

    def _ensure_tray_icon(self) -> None:
        if self.tray_icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda icon, item: self._show_window()),
            pystray.MenuItem("Quit", lambda icon, item: self._quit_from_tray()),
        )
        self.tray_icon = pystray.Icon("RunLabScanner", self._create_app_image(64), f"RunLab Scanner Desktop v{__version__}", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()
        self._append_log("Tray icon started")

    def minimize_to_tray(self) -> None:
        self._ensure_tray_icon()
        self.root.withdraw()
        self._append_log("Window minimized to tray")

    def _on_close(self) -> None:
        if self.is_quitting:
            return
        self.minimize_to_tray()

    def run(self) -> None:
        self.root.mainloop()
