# RunLab Scanner - License & Update Server (Cloudflare)

Sistem ini menjalankan **validasi license** dan **distribusi update** di Cloudflare:

- **Worker** (`src/worker.js`) — API publik untuk aplikasi + dashboard admin berbasis web.
- **D1** — database license, aktivasi mesin, dan riwayat release.
- **R2** — penyimpanan file EXE update (bucket yang sama dengan `release_to_r2.ps1`).

## Arsitektur

```
[Aplikasi PC Host]
   |  POST /api/activate  (pertama kali, simpan key)
   |  POST /api/validate  (tiap start, cache offline 14 hari)
   |  GET  /api/update     (cek update, ter-gate license)
   v
[Cloudflare Worker] --- D1 (licenses, activations, releases)
   |                 \-- R2 (file RunLabScanner-x.y.z.exe)
   |
   |  /admin (dashboard web, butuh ADMIN_TOKEN)
   v
[Kamu / Admin]  kelola license & publish update
```

## 1. Prasyarat

```powershell
npm i -g wrangler
wrangler login
```

## 2. Buat D1 database

```powershell
cd cloudflare
wrangler d1 create runlab-licenses
```

Salin `database_id` hasil perintah di atas ke `wrangler.toml` (field `database_id`).
Lalu buat tabelnya:

```powershell
wrangler d1 execute runlab-licenses --remote --file=./schema.sql
```

## 3. Konfigurasi `wrangler.toml`

Isi placeholder berikut:

- `database_id` — dari langkah 2.
- `bucket_name` (R2) — bucket berisi file update (sama dengan yang dipakai release).
- `PUBLIC_BASE_URL` — domain publik R2 kamu, mis. `https://cdn.domainmu.com`.

## 4. Set secret

```powershell
# Token untuk login dashboard admin (rahasiakan).
wrangler secret put ADMIN_TOKEN

# Kunci HMAC untuk menandatangani respons license.
# HARUS sama persis dengan yang dipakai aplikasi (lihat langkah 7).
wrangler secret put LICENSE_SIGNING_KEY
```

## 5. Deploy Worker

```powershell
wrangler deploy
```

Setelah deploy, kamu dapat URL seperti `https://runlab-licenses.<akun>.workers.dev`.

## 6. Buka dashboard admin

Akses `https://runlab-licenses.<akun>.workers.dev/admin`, login dengan `ADMIN_TOKEN`.
Dari sini kamu bisa:

- **Generate license** (atur nama customer, max aktivasi, channel, masa berlaku).
- **Revoke / aktifkan / hapus** license.
- **Publish release** update (versi + URL EXE + catatan + channel).

## 7. Konfigurasi aplikasi desktop

Edit `blindscanner/config.py`:

- `DEFAULT_LICENSE_API_URL` = URL Worker dari langkah 5.
- `DEFAULT_LICENSE_SIGNING_KEY` = nilai sama dengan `LICENSE_SIGNING_KEY` di langkah 4.

Atau set lewat environment variable saat runtime:

```powershell
$env:RUNLAB_LICENSE_API_URL = "https://runlab-licenses.akun.workers.dev"
$env:RUNLAB_LICENSE_SIGNING_KEY = "kunci-yang-sama-dengan-worker"
```

## 8. Rilis update (build + upload + daftarkan)

```powershell
# Dari root project:
.\release_licensed.ps1 `
  -Bucket "nama-bucket-r2" `
  -PublicBaseUrl "https://cdn.domainmu.com" `
  -WorkerUrl "https://runlab-licenses.akun.workers.dev" `
  -AdminToken "ADMIN_TOKEN_KAMU" `
  -Channel stable `
  -Notes "Perbaikan bug + dukungan scan jaringan" `
  -BuildExe
```

Script ini akan: build EXE → upload ke R2 → daftarkan release ke Worker.
Aplikasi yang ter-lisensi akan melihat update saat klik **Install Update**.

## Endpoint API (ringkas)

| Method | Path | Auth | Fungsi |
|--------|------|------|--------|
| POST | `/api/activate` | - | Aktivasi license di sebuah mesin |
| POST | `/api/validate` | - | Validasi license + mesin |
| GET  | `/api/update` | license | Manifest update ter-gate license |
| GET  | `/admin` | - (UI) | Dashboard admin |
| GET/POST | `/admin/api/licenses` | Bearer | List / buat license |
| POST | `/admin/api/licenses/:id/revoke` | Bearer | Revoke license |
| POST | `/admin/api/licenses/:id/activate` | Bearer | Aktifkan kembali |
| DELETE | `/admin/api/licenses/:id` | Bearer | Hapus license |
| GET/POST | `/admin/api/releases` | Bearer | List / publish release |

## Catatan keamanan

- Respons license ditandatangani **HMAC-SHA256**; aplikasi menolak respons/cache yang dipalsukan.
- Aplikasi menyimpan cache ber-tanda-tangan agar bisa jalan **offline hingga 14 hari**.
- `machine_id` di-hash (SHA-256) dari MachineGuid + UUID board + MAC, tidak membocorkan info mentah.
- Endpoint admin butuh `ADMIN_TOKEN`. Gunakan token panjang & acak.
