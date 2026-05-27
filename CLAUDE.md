# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Roku-E8C3** is a travel router and network management appliance for the Raspberry Pi Zero 2 W. The device name is a cover identity — the project code name is "SandOS" (`sand`/`sandos` prefix throughout). It runs a WiFi access point, routes clients through WireGuard VPN, and is managed via a local dashboard at `http://10.0.0.1`.

Hardware: onboard radio → AP (`10.0.0.1/24`), USB WiFi adapter (TP-Link Archer T2U Plus) → upstream client.

## Running the backend (development)

```bash
cd backend
# Set up venv (done once by install.sh in production)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run the dev server (binds to 127.0.0.1:8088 by default)
python -m app.main
```

Override settings via environment variables (see `core/settings.py`):

```bash
SAND_DB=/tmp/dev.db SAND_FRONTEND_DIR=../frontend python -m app.main
```

The frontend requires no build step — it is served directly by FastAPI as static files.

## Key commands

```bash
# Production install (run on target Pi as root)
sudo ./install.sh

# Cut over into router mode (drops current session, arms 300 s auto-rollback)
sudo sand-apply

# Cancel the auto-rollback after cutover
sudo sand-apply --confirm

# Roll back to pre-cutover networking
sudo sand-rollback

# Apply/re-apply networking (idempotent, run as root)
sudo python -m app.netapply apply       # full AP bring-up
sudo python -m app.netapply firewall    # firewall only
sudo python -m app.netapply status      # print JSON status

# Remove the install
sudo ./uninstall.sh
sudo ./uninstall.sh --purge   # also wipes /etc/sandos, /var/lib/sandos, /var/log/sandos
```

## Architecture

### Backend (`backend/app/`)

FastAPI app with no external database driver. All structured state is in a single SQLite file (`/var/lib/sandos/sand.db`).

| Layer | Path | Role |
|---|---|---|
| API routers | `api/` | One router per dashboard page; thin — delegates to services |
| Services | `services/` | Business logic: config, firewall, logs, network, pihole, system, wifi |
| Providers | `providers/` | VPN abstraction (`base.VPNProvider`): `direct`, `wireguard`, `nordvpn` |
| DB | `db/repo.py` | Thin typed wrapper over `sqlite3`; single connection with a lock |
| Core | `core/` | `settings.py` (env-loaded), `security.py` (scrypt + HMAC CSRF), `privileged.py` (sudo helpers), `validation.py` |
| Tools | `netapply.py`, `watchdog.py`, `recovery.py` | Run as root; imported by systemd units |

**Authentication:** cookie-based (`roku_session`). State-changing API calls require an `X-Roku-CSRF` header; the token is derived from the session token via HMAC (no DB storage needed).

**Privileged access:** The dashboard runs as the unprivileged `sand` user. All root operations go through a fixed set of helper scripts (`sand-sys`, `sand-net`, `sand-fw`, `sand-wifi`, `sand-wg`, `sand-pihole`) invoked via `sudo -n` — never via shell strings. The allowlist is in `core/privileged.HELPERS`; arguments are always passed as a list.

**Config templates:** `config/*.tmpl` files use `{{VARIABLE}}` placeholders, rendered by `netapply.render()`. The rendered files are written to `/etc/hostapd/`, `/etc/dnsmasq.d/`, `/etc/sandos/` at apply time.

### Frontend (`frontend/`)

Vanilla JS — no framework, no build step. Hash-based routing (`#/path`). Pages are dynamically imported modules in `js/pages/`. Shared utilities: `api.js` (fetch wrapper with CSRF injection), `ui.js` (DOM helpers), `store.js` (poll management), `icons.js` (inline SVG).

### Systemd units (`systemd/`)

| Unit | Runs as | Purpose |
|---|---|---|
| `sand-netapply.service` | root | Apply networking at boot |
| `sand-dashboard.service` | sand | FastAPI backend (port 80 via `CAP_NET_BIND_SERVICE`) |
| `sand-watchdog.timer` | root | Every 2 min: AP health, Pi-hole, USB adapter change |
| `sand-recovery.service` | root | Boot-time check for `/boot/firmware/sand-recovery` flag |
| `sand-firewall.service` | root | Apply nftables ruleset |

### Database schema

The `settings` table is the primary key/value store for all app configuration (SSID, passwords, DNS, etc.). JSON blobs are stored via `db.set_json()`/`db.get_json()`. The `events` table feeds the Logs page (capped at 5000 rows). Device routing state lives in `devices.route_profile` and `routing_rules`; the nftables ruleset is rebuilt from these on every `netapply`.

## Security constraints to preserve

- All user-supplied values that reach system commands or config files must pass through `core/validation.py` validators.
- Subprocess calls must use list form — never string form with `shell=True`.
- Helper names must be checked against `HELPERS` in `core/privileged.py` before being passed to `sudo`.
- The database must not be opened as root in write mode (avoids root-owned WAL files blocking the `sand` user). Use `Database(path, read_only=True)` in any tool that runs as root.
- CSRF tokens are required on all state-changing API endpoints (`require_csrf` dependency).

## Verification

There are no automated tests. Manual verification is tracked in `tests/checklist.md`. Run the checklist after significant changes and before any cutover.
