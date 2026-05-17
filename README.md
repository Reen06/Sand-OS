# Roku-E8C3 — Secure Travel Router

A self-contained travel router and network management appliance for the
Raspberry Pi Zero 2 W. It hosts its own WiFi access point, routes clients
upstream through WireGuard, filters DNS with Pi-hole, and is managed from a
local dashboard at `http://10.0.0.1`.

## Status

Under active construction. Build phases are tracked in the project task list;
the implementation plan lives in `.claude/plans/`.

## Hardware

- Raspberry Pi Zero 2 W — Raspberry Pi OS (Debian 13), 64-bit
- Onboard WiFi  →  access point   (SSID `Roku-E8C3`, `10.0.0.1/24`)
- TP-Link Archer T2U Plus (USB)  →  upstream WiFi client

## Features

- Self-hosted WiFi AP with a recovery-first design — never locks you out
- Dashboard pages: Overview, Devices, WiFi, VPN, Routing, Guest, Settings, Logs
- Upstream WiFi connection with captive-portal handling
- WireGuard VPN with per-device routing and kill-switch
- Pi-hole DNS filtering with graceful failover
- Isolated guest network
- Persistent device memory (SQLite)

## Repository layout

    backend/     FastAPI dashboard backend
    frontend/    Static dashboard UI (no build step)
    config/      hostapd / dnsmasq / nftables templates, interface roles
    systemd/     Service units
    scripts/     Privileged helpers, cutover + recovery scripts
    docs/        Setup, WireGuard, troubleshooting, recovery, security
    tests/       Verification checklist

## Install

Run on the target Pi:

    sudo ./install.sh

The installer stages everything without disrupting live networking. When you
are ready, run `sand-apply` to cut over into router mode. The cutover is
protected by a timed auto-rollback. See `docs/` for full guides.

## Networking

| Role        | Interface        | Manager        | Address       |
|-------------|------------------|----------------|---------------|
| AP (main)   | onboard radio    | hostapd        | `10.0.0.1/24` |
| AP (guest)  | hostapd multi-BSS| hostapd        | `10.0.1.1/24` |
| Upstream    | USB adapter      | NetworkManager | DHCP client   |
| VPN tunnels | `wg0`, `wg1`, …  | wg-quick       | per-profile   |

Interface roles are resolved by driver/MAC and can be swapped by editing
`config/interfaces.conf`.
