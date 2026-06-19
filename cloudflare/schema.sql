-- RunLab Scanner - License & Update D1 schema
-- Jalankan: wrangler d1 execute runlab-licenses --file=./schema.sql

CREATE TABLE IF NOT EXISTS licenses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key     TEXT NOT NULL UNIQUE,
    customer_name   TEXT NOT NULL DEFAULT '',
    customer_email  TEXT NOT NULL DEFAULT '',
    max_activations INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active',   -- active | revoked
    channel         TEXT NOT NULL DEFAULT 'stable',   -- stable | beta
    notes           TEXT NOT NULL DEFAULT '',
    expires_at      TEXT,                              -- ISO8601 atau NULL = selamanya
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id   INTEGER NOT NULL,
    machine_id   TEXT NOT NULL,
    hostname     TEXT NOT NULL DEFAULT '',
    app_version  TEXT NOT NULL DEFAULT '',
    activated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (license_id, machine_id),
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     TEXT NOT NULL,
    channel     TEXT NOT NULL DEFAULT 'stable',
    url         TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    mandatory   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activations_license ON activations(license_id);
CREATE INDEX IF NOT EXISTS idx_releases_channel ON releases(channel, created_at);
