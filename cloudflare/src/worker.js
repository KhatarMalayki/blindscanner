// RunLab Scanner - License & Update Worker
// Endpoints:
//   Public (client app):
//     POST /api/activate         { license_key, machine_id, hostname, app_version }
//     POST /api/validate         { license_key, machine_id, app_version }
//     GET  /api/update?license_key=&machine_id=&channel=
//   Admin (dashboard, butuh Authorization: Bearer <ADMIN_TOKEN>):
//     GET  /admin                (UI HTML)
//     GET  /admin/api/licenses
//     POST /admin/api/licenses
//     POST /admin/api/licenses/:id/revoke
//     POST /admin/api/licenses/:id/activate     (set status active)
//     DELETE /admin/api/licenses/:id
//     GET  /admin/api/releases
//     POST /admin/api/releases

import { ADMIN_HTML } from "./admin_ui.js";

const JSON_HEADERS = { "Content-Type": "application/json; charset=utf-8" };

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...JSON_HEADERS, ...corsHeaders(), ...extraHeaders },
  });
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

function nowIso() {
  return new Date().toISOString();
}

function isExpired(expiresAt) {
  if (!expiresAt) return false;
  const t = Date.parse(expiresAt);
  if (Number.isNaN(t)) return false;
  return t < Date.now();
}

// ---- HMAC signing untuk respons license (anti-tamper di sisi client) ----
async function hmacSign(message, secret) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Bentuk payload tanda tangan yang stabil (urutan field tetap).
function signablePayload(p) {
  return [
    p.valid ? "1" : "0",
    p.license_key || "",
    p.machine_id || "",
    p.status || "",
    p.expires_at || "",
    p.channel || "",
    p.issued_at || "",
  ].join("|");
}

async function signedLicenseResponse(payload, env) {
  const issued_at = nowIso();
  const body = { ...payload, issued_at };
  const signature = await hmacSign(signablePayload(body), env.LICENSE_SIGNING_KEY);
  return { ...body, signature };
}

function genLicenseKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(20));
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
  // Format RLS-XXXXX-XXXXX-XXXXX-XXXXX
  const groups = hex.match(/.{1,5}/g).slice(0, 4);
  return "RLS-" + groups.join("-");
}

function isAdmin(request, env) {
  const auth = request.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  return env.ADMIN_TOKEN && token && token === env.ADMIN_TOKEN;
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

// ----------------- PUBLIC HANDLERS -----------------

async function handleActivate(request, env) {
  const { license_key, machine_id, hostname, app_version } = await readJson(request);
  if (!license_key || !machine_id) {
    return json({ valid: false, error: "license_key dan machine_id wajib diisi" }, 400);
  }

  const license = await env.DB.prepare(
    "SELECT * FROM licenses WHERE license_key = ?"
  ).bind(license_key).first();

  if (!license) {
    return json(await signedLicenseResponse({ valid: false, status: "not_found", license_key, machine_id, reason: "License tidak ditemukan" }, env), 200);
  }
  if (license.status !== "active") {
    return json(await signedLicenseResponse({ valid: false, status: license.status, license_key, machine_id, reason: "License dinonaktifkan" }, env), 200);
  }
  if (isExpired(license.expires_at)) {
    return json(await signedLicenseResponse({ valid: false, status: "expired", license_key, machine_id, expires_at: license.expires_at, reason: "License kadaluarsa" }, env), 200);
  }

  const existing = await env.DB.prepare(
    "SELECT * FROM activations WHERE license_id = ? AND machine_id = ?"
  ).bind(license.id, machine_id).first();

  if (!existing) {
    const countRow = await env.DB.prepare(
      "SELECT COUNT(*) AS c FROM activations WHERE license_id = ?"
    ).bind(license.id).first();
    if (countRow.c >= license.max_activations) {
      return json(await signedLicenseResponse({ valid: false, status: "limit_reached", license_key, machine_id, reason: `Batas aktivasi tercapai (${license.max_activations})` }, env), 200);
    }
    await env.DB.prepare(
      "INSERT INTO activations (license_id, machine_id, hostname, app_version) VALUES (?, ?, ?, ?)"
    ).bind(license.id, machine_id, hostname || "", app_version || "").run();
  } else {
    await env.DB.prepare(
      "UPDATE activations SET last_seen_at = ?, hostname = ?, app_version = ? WHERE id = ?"
    ).bind(nowIso(), hostname || existing.hostname, app_version || existing.app_version, existing.id).run();
  }

  return json(await signedLicenseResponse({
    valid: true,
    status: "active",
    license_key,
    machine_id,
    channel: license.channel,
    expires_at: license.expires_at || "",
    customer_name: license.customer_name,
  }, env), 200);
}

async function handleValidate(request, env) {
  const { license_key, machine_id, app_version } = await readJson(request);
  if (!license_key || !machine_id) {
    return json({ valid: false, error: "license_key dan machine_id wajib diisi" }, 400);
  }

  const license = await env.DB.prepare(
    "SELECT * FROM licenses WHERE license_key = ?"
  ).bind(license_key).first();

  if (!license || license.status !== "active" || isExpired(license.expires_at)) {
    const status = !license ? "not_found" : (license.status !== "active" ? license.status : "expired");
    return json(await signedLicenseResponse({ valid: false, status, license_key, machine_id }, env), 200);
  }

  const activation = await env.DB.prepare(
    "SELECT * FROM activations WHERE license_id = ? AND machine_id = ?"
  ).bind(license.id, machine_id).first();

  if (!activation) {
    return json(await signedLicenseResponse({ valid: false, status: "not_activated", license_key, machine_id }, env), 200);
  }

  await env.DB.prepare(
    "UPDATE activations SET last_seen_at = ?, app_version = ? WHERE id = ?"
  ).bind(nowIso(), app_version || activation.app_version, activation.id).run();

  return json(await signedLicenseResponse({
    valid: true,
    status: "active",
    license_key,
    machine_id,
    channel: license.channel,
    expires_at: license.expires_at || "",
    customer_name: license.customer_name,
  }, env), 200);
}

async function handleUpdate(request, env) {
  const url = new URL(request.url);
  const license_key = url.searchParams.get("license_key") || "";
  const machine_id = url.searchParams.get("machine_id") || "";
  const channel = url.searchParams.get("channel") || "";

  if (!license_key || !machine_id) {
    return json({ error: "license_key dan machine_id wajib diisi" }, 400);
  }

  const license = await env.DB.prepare(
    "SELECT * FROM licenses WHERE license_key = ?"
  ).bind(license_key).first();

  if (!license || license.status !== "active" || isExpired(license.expires_at)) {
    return json({ error: "License tidak valid untuk update" }, 403);
  }

  const activation = await env.DB.prepare(
    "SELECT id FROM activations WHERE license_id = ? AND machine_id = ?"
  ).bind(license.id, machine_id).first();
  if (!activation) {
    return json({ error: "Mesin belum teraktivasi" }, 403);
  }

  const useChannel = channel || license.channel || "stable";
  const release = await env.DB.prepare(
    "SELECT version, url, notes, mandatory FROM releases WHERE channel = ? ORDER BY id DESC LIMIT 1"
  ).bind(useChannel).first();

  if (!release) {
    return json({ error: "Belum ada release untuk channel ini" }, 404);
  }

  // Bentuk kompatibel dengan updater.py: { version, url, notes }
  return json({
    version: release.version,
    url: release.url,
    notes: release.notes,
    mandatory: !!release.mandatory,
    channel: useChannel,
  });
}

// ----------------- ADMIN HANDLERS -----------------

async function adminListLicenses(env) {
  const rows = await env.DB.prepare(`
    SELECT l.*,
      (SELECT COUNT(*) FROM activations a WHERE a.license_id = l.id) AS activation_count
    FROM licenses l ORDER BY l.id DESC
  `).all();
  return json({ licenses: rows.results || [] });
}

async function adminCreateLicense(request, env) {
  const body = await readJson(request);
  const license_key = (body.license_key && String(body.license_key).trim()) || genLicenseKey();
  const customer_name = body.customer_name || "";
  const customer_email = body.customer_email || "";
  const max_activations = Number(body.max_activations) || 1;
  const channel = body.channel || "stable";
  const notes = body.notes || "";
  const expires_at = body.expires_at || null;

  try {
    await env.DB.prepare(`
      INSERT INTO licenses (license_key, customer_name, customer_email, max_activations, channel, notes, expires_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(license_key, customer_name, customer_email, max_activations, channel, notes, expires_at).run();
  } catch (e) {
    return json({ error: "Gagal membuat license (mungkin key duplikat): " + e.message }, 400);
  }
  return json({ ok: true, license_key });
}

async function adminSetStatus(id, status, env) {
  await env.DB.prepare("UPDATE licenses SET status = ? WHERE id = ?").bind(status, id).run();
  return json({ ok: true });
}

async function adminDeleteLicense(id, env) {
  await env.DB.prepare("DELETE FROM activations WHERE license_id = ?").bind(id).run();
  await env.DB.prepare("DELETE FROM licenses WHERE id = ?").bind(id).run();
  return json({ ok: true });
}

async function adminListReleases(env) {
  const rows = await env.DB.prepare("SELECT * FROM releases ORDER BY id DESC").all();
  return json({ releases: rows.results || [] });
}

async function adminCreateRelease(request, env) {
  const body = await readJson(request);
  const version = String(body.version || "").trim();
  let url = String(body.url || "").trim();
  const channel = body.channel || "stable";
  const notes = body.notes || "";
  const mandatory = body.mandatory ? 1 : 0;

  if (!version) return json({ error: "version wajib diisi" }, 400);

  // Jika url kosong tapi ada object_key, bentuk dari PUBLIC_BASE_URL.
  if (!url && body.object_key) {
    url = `${(env.PUBLIC_BASE_URL || "").replace(/\/$/, "")}/${String(body.object_key).replace(/^\//, "")}`;
  }
  if (!url) return json({ error: "url atau object_key wajib diisi" }, 400);

  await env.DB.prepare(
    "INSERT INTO releases (version, channel, url, notes, mandatory) VALUES (?, ?, ?, ?, ?)"
  ).bind(version, channel, url, notes, mandatory).run();
  return json({ ok: true, version, url });
}

// ----------------- ROUTER -----------------

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }

    try {
      // Public API
      if (path === "/api/activate" && method === "POST") return await handleActivate(request, env);
      if (path === "/api/validate" && method === "POST") return await handleValidate(request, env);
      if (path === "/api/update" && method === "GET") return await handleUpdate(request, env);
      if (path === "/" || path === "/health") return json({ ok: true, service: "runlab-licenses" });

      // Admin UI
      if (path === "/admin" && method === "GET") {
        return new Response(ADMIN_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
      }

      // Admin API (semua butuh token)
      if (path.startsWith("/admin/api/")) {
        if (!isAdmin(request, env)) return json({ error: "Unauthorized" }, 401);

        if (path === "/admin/api/licenses" && method === "GET") return await adminListLicenses(env);
        if (path === "/admin/api/licenses" && method === "POST") return await adminCreateLicense(request, env);
        if (path === "/admin/api/releases" && method === "GET") return await adminListReleases(env);
        if (path === "/admin/api/releases" && method === "POST") return await adminCreateRelease(request, env);

        const revokeMatch = path.match(/^\/admin\/api\/licenses\/(\d+)\/revoke$/);
        if (revokeMatch && method === "POST") return await adminSetStatus(Number(revokeMatch[1]), "revoked", env);

        const activateMatch = path.match(/^\/admin\/api\/licenses\/(\d+)\/activate$/);
        if (activateMatch && method === "POST") return await adminSetStatus(Number(activateMatch[1]), "active", env);

        const deleteMatch = path.match(/^\/admin\/api\/licenses\/(\d+)$/);
        if (deleteMatch && method === "DELETE") return await adminDeleteLicense(Number(deleteMatch[1]), env);

        return json({ error: "Not found" }, 404);
      }

      return json({ error: "Not found" }, 404);
    } catch (e) {
      return json({ error: "Server error: " + e.message }, 500);
    }
  },
};
