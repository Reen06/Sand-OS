-- Roku-E8C3 travel router — SQLite schema.
-- Applied idempotently at install time and on every backend start.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Key/value application settings: SSID, hostname, MAC mode, guest config,
-- dashboard admin password hash, theme prefs, last-known-good ref, etc.
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Known client devices — persistent device memory.
CREATE TABLE IF NOT EXISTS devices (
    mac            TEXT PRIMARY KEY,                       -- normalized lower-case
    ip             TEXT,                                   -- current/last lease IP
    hostname       TEXT,                                   -- DHCP-reported hostname
    nickname       TEXT,                                   -- user-assigned label
    vendor         TEXT,                                   -- OUI vendor lookup
    device_type    TEXT,                                   -- phone|laptop|tv|iot|unknown
    route_profile  TEXT NOT NULL DEFAULT 'direct',         -- direct|wg:<name>|blocked
    preferred_vpn  TEXT,                                   -- remembered VPN profile
    is_guest       INTEGER NOT NULL DEFAULT 0,
    blocked        INTEGER NOT NULL DEFAULT 0,
    fwmark         INTEGER,                                -- assigned firewall mark
    first_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_devices_lastseen ON devices(last_seen);

-- Saved upstream WiFi networks.
CREATE TABLE IF NOT EXISTS wifi_networks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ssid           TEXT NOT NULL,
    bssid          TEXT,
    security       TEXT,                                   -- open|wpa2|wpa3|wpa2-wpa3
    psk            TEXT,                                   -- pre-shared key (DB is chmod 600)
    priority       INTEGER NOT NULL DEFAULT 0,
    autoconnect    INTEGER NOT NULL DEFAULT 1,
    hidden         INTEGER NOT NULL DEFAULT 0,
    last_connected TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ssid, bssid)
);

-- WireGuard tunnel profiles.
CREATE TABLE IF NOT EXISTS wireguard_profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,                     -- user label
    iface        TEXT NOT NULL UNIQUE,                     -- wg0, wg1, ...
    conf_path    TEXT NOT NULL,                            -- /etc/wireguard/<iface>.conf
    address      TEXT,                                     -- tunnel address(es)
    dns          TEXT,                                     -- VPN-provided DNS
    endpoint     TEXT,                                     -- host:port
    public_key   TEXT,
    fwmark       INTEGER,                                  -- routing mark for this tunnel
    table_id     INTEGER,                                  -- policy routing table id
    is_default   INTEGER NOT NULL DEFAULT 0,
    killswitch   INTEGER NOT NULL DEFAULT 1,
    enabled      INTEGER NOT NULL DEFAULT 0,                -- desired up/down state
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- VPN provider registry (provider abstraction: direct, wireguard, nordvpn).
CREATE TABLE IF NOT EXISTS vpn_providers (
    name      TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    enabled   INTEGER NOT NULL DEFAULT 1,
    config    TEXT                                         -- JSON provider config
);

-- Per-device routing rules — source of truth; nftables is rebuilt from here.
CREATE TABLE IF NOT EXISTS routing_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_mac  TEXT NOT NULL UNIQUE,
    provider    TEXT NOT NULL DEFAULT 'direct',
    profile     TEXT,                                      -- wg profile name if applicable
    fwmark      INTEGER NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (device_mac) REFERENCES devices(mac) ON DELETE CASCADE
);

-- Config backups taken before any edit — recovery.
CREATE TABLE IF NOT EXISTS config_backups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    category    TEXT NOT NULL,                             -- hostapd|dnsmasq|netplan|nft|...
    path        TEXT NOT NULL,                             -- backup archive path
    note        TEXT
);

-- Last-known-good network snapshots — auto-rollback target.
CREATE TABLE IF NOT EXISTS last_known_good (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    snapshot_path TEXT NOT NULL,
    kind          TEXT NOT NULL,                           -- networking|firewall|full
    confirmed     INTEGER NOT NULL DEFAULT 0,
    note          TEXT
);

-- Event / audit log — feeds the Logs page and recovery diagnostics.
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    level      TEXT NOT NULL DEFAULT 'info',               -- debug|info|warn|error
    category   TEXT NOT NULL,                              -- wifi|vpn|firewall|system|auth|recovery
    message    TEXT NOT NULL,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

-- Dashboard login sessions — server-side session store.
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL,
    user_agent  TEXT,
    ip          TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- Static provider seeds.
INSERT OR IGNORE INTO vpn_providers (name, kind, enabled) VALUES
    ('direct',    'direct',    1),
    ('wireguard', 'wireguard', 1),
    ('nordvpn',   'nordvpn',   0);
