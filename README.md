# RunLab Scanner Desktop

Aplikasi desktop Windows untuk membagikan scanner USB/WIA ke jaringan lokal. Cocok untuk skenario scanner pada printer multifungsi seperti Epson L3210 yang terhubung ke satu PC, lalu hasil scan bisa dipicu dari browser perangkat lain di LAN.

## Fitur

- Deteksi perangkat scanner WIA yang terlihat oleh Windows
- Pilih scanner aktif dari aplikasi desktop
- Jalankan server lokal agar perangkat lain di jaringan bisa meminta scan
- Security dengan API key untuk akses dari browser atau API
- Pengaturan scan default: format, DPI, mode warna, brightness, contrast
- Simpan hasil scan ke folder lokal host
- Download hasil scan dari browser
- Output gambar atau PDF
- Halaman web sederhana untuk operator jarak jauh
- Build `.exe` untuk Windows
- System tray mode agar app bisa jalan di background
- Script installer Inno Setup
- Check update dari manifest URL
- Download dan apply update untuk build `.exe`

## Catatan kompatibilitas

- Ditujukan untuk **Windows**
- Scanner harus terdeteksi oleh Windows sebagai perangkat **WIA**
- Untuk Epson L3210, pastikan driver scanner sudah terpasang dan proses scan lokal dari Windows sudah normal
- Jika perangkat hanya menyediakan TWAIN dan tidak muncul di WIA, aplikasi ini tidak akan bisa mengaksesnya tanpa integrasi tambahan
- Output PDF saat ini dibuat dari hasil scan JPEG tunggal per request
- Tray mode membutuhkan environment desktop normal di Windows
- Auto update penuh hanya didukung saat aplikasi dijalankan dari build `RunLabScanner.exe`, bukan dari `python main.py`

## Menjalankan

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python .\scripts\generate_icon.py
python main.py
```

## Cara pakai

1. Hubungkan scanner/printer USB ke PC host.
2. Buka aplikasi desktop.
3. Klik **Refresh Devices** lalu pilih scanner.
4. Atur folder output, API key, dan default scan options bila perlu.
5. Klik **Start Server**.
6. Buka alamat yang tampil, misalnya `http://192.168.1.10:8765`, dari HP atau PC lain di jaringan.
7. Masukkan API key yang tampil di aplikasi desktop.
8. Pilih format dan opsi scan dari halaman web.
9. Klik **Start Scan** untuk memicu scan dari perangkat host.
10. Jika ingin app tetap berjalan tanpa jendela utama, klik **Minimize to Tray**.
11. Untuk update app, isi **Update Manifest URL** lalu klik **Check Update**.

## API ringkas

- `GET /api/status`
- `GET /api/devices`
- `GET /api/scans`
- `POST /api/scan`

Semua endpoint `api` dan `downloads` membutuhkan header `X-API-Key` jika API key diaktifkan di host.

Body `POST /api/scan`:

```json
{
  "device_id": "opsional-device-id",
  "format": "jpeg",
  "dpi": 200,
  "color_mode": "color",
  "brightness": 0,
  "contrast": 0
}
```

Nilai `format` yang didukung:

- `jpeg`
- `png`
- `bmp`
- `tiff`
- `pdf`

Nilai `color_mode` yang didukung:

- `color`
- `grayscale`
- `bw`

## Build EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Hasil build akan muncul di folder `dist` dengan nama aplikasi `RunLabScanner.exe`.

## Build Installer

Installer memakai **Inno Setup**.

1. Install Inno Setup.
2. Build EXE dulu.
3. Jalankan:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_installer.ps1
```

Hasil installer akan muncul di folder `installer-dist`.

## Auto Update

Aplikasi membaca file manifest JSON dari URL yang Anda isi di GUI.

Contoh manifest:

```json
{
  "version": "1.0.1",
  "url": "https://example.com/releases/RunLabScanner.exe",
  "notes": "Fix tray issue dan perbaikan scan WIA"
}
```

Alur rilis update:

1. Build `RunLabScanner.exe` versi baru.
2. Upload file EXE baru ke server Anda.
3. Update file manifest JSON agar `version` dan `url` menunjuk ke rilis terbaru.
4. User mengisi URL manifest itu di aplikasi.
5. User klik **Check Update**.
6. Jika versi lebih baru tersedia, app akan download EXE baru, menutup app lama, mengganti file lama, lalu menjalankan versi baru.

Saran distribusi update:

- gunakan `HTTPS`
- simpan manifest di URL yang stabil
- simpan file EXE rilis di URL yang bisa diunduh langsung
- lakukan testing update dari satu mesin dulu sebelum rollout ke semua user

## Publish update ke Cloudflare R2 (Wrangler)

Anda bisa publish update online ke R2 memakai `wrangler` supaya user cukup klik **Check Update**.

Prasyarat:

- `wrangler` sudah terinstall dan login (`wrangler login`)
- bucket R2 sudah dibuat
- bucket punya URL publik (misalnya `https://pub-xxxx.r2.dev`)

Script yang disediakan:

- `release_to_r2.ps1`

Contoh pakai:

```powershell
powershell -ExecutionPolicy Bypass -File .\release_to_r2.ps1 \
  -Bucket "my-runlab-scanner-bucket" \
  -PublicBaseUrl "https://pub-xxxx.r2.dev" \
  -Notes "Fix bug tray dan perbaikan scan WIA" \
  -BuildExe
```

Yang dilakukan script:

1. (Opsional) build EXE jika pakai `-BuildExe`
2. Baca versi dari `blindscanner/__init__.py` (atau bisa override pakai `-Version`)
3. Upload EXE ke key `runlab-scanner/releases/RunLabScanner-<version>.exe`
4. Generate `manifest.json` sesuai format updater
5. Upload manifest ke key `runlab-scanner/manifest.json`

Output penting dari script:

- URL EXE rilis terbaru
- URL manifest yang dipakai di aplikasi

Contoh URL manifest untuk diisi ke GUI RunLab Scanner:

- `https://pub-xxxx.r2.dev/runlab-scanner/manifest.json`

## Struktur

- `main.py` - entrypoint aplikasi desktop
- `blindscanner/__init__.py` - versi aplikasi
- `blindscanner/app.py` - GUI desktop, tray mode, dan check update
- `blindscanner/updater.py` - manifest fetch, download update, dan handoff updater
- `blindscanner/web.py` - HTTP server dan web client
- `blindscanner/wia.py` - integrasi Windows WIA via PowerShell
- `blindscanner/pdf_utils.py` - utilitas PDF sederhana
- `scripts/generate_icon.py` - generator icon PNG dan ICO
- `build_exe.ps1` - build `.exe` menggunakan PyInstaller
- `build_installer.ps1` - build installer memakai Inno Setup
- `installer.iss` - script installer Inno Setup

## Troubleshooting

- Jika daftar device kosong, cek apakah scanner muncul di aplikasi Windows Scan atau Fax and Scan.
- Jalankan aplikasi dengan hak akses user yang sama dengan sesi desktop aktif.
- Nonaktifkan firewall atau buka port yang dipakai jika perangkat lain tidak bisa mengakses server.
- Jika hasil PDF gagal dibuat, gunakan format `jpeg` untuk memastikan driver scanner menghasilkan JPEG yang valid.
- Jika tray icon tidak muncul, pastikan Windows Explorer berjalan normal dan environment desktop tidak dibatasi policy tertentu.
- Jika update gagal, cek apakah URL manifest dapat diakses dan file EXE baru bisa diunduh langsung.
