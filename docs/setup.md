# Setup Guide — Roku-E8C3

## Prerequisites

- Raspberry Pi Zero 2 W (or Pi 3/4/5) running Raspberry Pi OS (Debian Bookworm or Trixie), 64-bit
- Micro-SD card, at least 8 GB
- TP-Link Archer T2U Plus USB WiFi adapter (or another adapter supported by rtw88/rtl8821au drivers)
- A separate device (laptop, phone) for the initial setup

---

## 1. Initial OS setup (if starting fresh)

Flash Raspberry Pi OS Lite (64-bit) with Raspberry Pi Imager. Enable SSH and set a hostname in the Imager's advanced settings. Boot the Pi, connect it to your local network, and SSH in.

The hostname `Roku-E8C3` is used throughout; set it now:

```bash
sudo hostnamectl set-hostname Roku-E8C3
```

---

## 2. Clone the repository

```bash
git clone https://github.com/yourorg/sandos.git ~/sandos
cd ~/sandos
```

---

## 3. Run the installer

```bash
sudo ./install.sh
```

The installer:
- Installs system packages (hostapd, dnsmasq, nftables, wireguard-tools, etc.)
- Creates the `sand` service user
- Installs the FastAPI dashboard + Python venv
- Installs systemd services
- Optionally installs Pi-hole (DNS filtering) — requires internet access
- Prompts for a dashboard admin password and WiFi passphrase
- **Does not touch live networking** — everything is staged

### Flags

| Flag | Effect |
|------|--------|
| `--unattended` | Take passwords from `SAND_DASHBOARD_PASSWORD` / `SAND_AP_PASSWORD` env vars |
| `--no-pihole` | Skip Pi-hole installation |
| `--with-raspap` | Also run the RaspAP installer (optional; its web UI is disabled) |

---

## 4. Verify the staged install

The dashboard is available on your current network IP before cutover:

```
http://<pi-current-ip>
```

Sign in, explore the pages. Network changes are **not yet live**.

---

## 5. Plug in the USB WiFi adapter

The TP-Link Archer T2U Plus (RTL8821AU) is the upstream interface. Plug it in before cutover so the system sees two radios.

Check that two wireless interfaces appear:

```bash
iw dev
```

You should see `wlan0` (onboard) and `wlan1` (USB adapter).

---

## 6. Cut over into router mode

> **Warning:** This step drops your current SSH/WiFi session over the AP radio.
> Have a plan to reconnect via the new `Roku-E8C3` SSID.

```bash
sudo sand-apply
```

The cutover:
1. Snapshots current network config (for rollback)
2. Hands the AP radio to hostapd
3. Arms a **5-minute auto-rollback** timer — if you don't confirm, the device reverts
4. Brings up the `Roku-E8C3` SSID and dashboard at `http://10.0.0.1`

Connect a device to `Roku-E8C3`, open `http://10.0.0.1`, and confirm the cutover from the Settings page — or run on the Pi:

```bash
sudo sand-apply --confirm
```

---

## 7. Connect upstream WiFi

From the dashboard **WiFi** page, scan for networks and connect to your upstream access point. Once connected, devices on `Roku-E8C3` can reach the internet.

---

## 8. Done

Your Pi is now a travel router. See the other docs for:
- `wireguard.md` — VPN tunnels and per-device routing
- `recovery.md` — rollback and recovery procedures
- `troubleshooting.md` — diagnostics and common fixes
