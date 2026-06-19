from __future__ import annotations

import os

# Konfigurasi koneksi ke Cloudflare Worker (license + update).
# Nilai default di bawah ini di-bake saat build. Untuk override saat runtime,
# gunakan environment variable berikut.
#
#   RUNLAB_LICENSE_API_URL   -> base URL Worker, mis. https://runlab-licenses.akun.workers.dev
#   RUNLAB_LICENSE_SIGNING_KEY -> HMAC signing key (HARUS sama dengan secret di Worker)
#
# CATATAN KEAMANAN: signing key di sini hanya untuk verifikasi tanda tangan respons
# (integritas), bukan rahasia mutlak. Server tetap otoritas akhir validasi license.

DEFAULT_LICENSE_API_URL = "https://runlab-licenses.khatarmalayki21.workers.dev"
DEFAULT_LICENSE_SIGNING_KEY = "wo7PYgi1H9FfTBVcUQXakNsKehGvSZWMExDjpRyJAblLC568"


def get_license_api_url() -> str:
    return (os.environ.get("RUNLAB_LICENSE_API_URL") or DEFAULT_LICENSE_API_URL).rstrip("/")


def get_license_signing_key() -> str:
    return os.environ.get("RUNLAB_LICENSE_SIGNING_KEY") or DEFAULT_LICENSE_SIGNING_KEY
