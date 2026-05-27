# Cutover & Editing Guide

## What the cutover does

`sand-apply` is the one command that turns the Pi into a live router.
Until you run it, the device operates normally on your existing network — nothing is disrupted.

When you run it:

1. Snapshots current network config (used for auto-rollback)
2. Detects radio roles: `wlan0` (onboard `brcmfmac`) → AP, `wlan1` (USB RTL8821AU) → upstream
3. Removes `wlan0` from NetworkManager so hostapd can own it
4. Starts **hostapd** (broadcasts "Roku-E8C3" WiFi) and **dnsmasq** (DHCP on `10.0.0.0/24`)
5. Sets `wlan1` as the upstream client via NetworkManager
6. Loads nftables firewall (routing, kill-switch, guest isolation)
7. Arms a **5-minute auto-rollback timer** — if you don't confirm, the Pi reverts and reboots

Your current SSH/WiFi session will drop when hostapd takes over `wlan0`.

---

## Troubleshooting

**Error: `bash: /usr/local/lib/roku-gateway/roku-resolve-ifaces: No such file or directory`**

The deployed script was outdated. Fix:
```bash
sudo rsync -a ~/roku-gateway/scripts/sand-apply /opt/sandos/scripts/sand-apply
sudo rsync -a ~/roku-gateway/scripts/helpers/ /opt/sandos/scripts/helpers/
sudo rsync -a ~/roku-gateway/scripts/helpers/ /usr/local/lib/sandos/
sudo chmod +x /opt/sandos/scripts/helpers/* /usr/local/lib/sandos/*
```
Then re-run `sand-apply`.

**Error: `no access-point-capable interface found`**

The USB adapter isn't plugged in or wasn't recognized. Check:
```bash
bash /opt/sandos/scripts/helpers/sand-resolve-ifaces
# Should print: AP_IFACE=wlan0  UPSTREAM_IFACE=wlan1  RADIO_COUNT=2
```
If `RADIO_COUNT=1`, the USB adapter isn't detected. Replug it and wait 10 seconds.

---

## Running the cutover

```bash
sudo /opt/sandos/scripts/sand-apply
```

After it runs:

1. Connect a phone or laptop to the **Roku-E8C3** WiFi network
2. Open **http://10.0.0.1** in a browser and log in
3. Confirm in Settings → or from SSH on the new AP:

```bash
sudo /opt/sandos/scripts/sand-apply --confirm
```

If you don't confirm within 5 minutes, the device automatically restores the previous network and reboots. You cannot be locked out.

---

## Accessing the device after cutover

| Method | How |
|---|---|
| Browser | Connect to Roku-E8C3 WiFi → http://10.0.0.1 |
| SSH | Connect to Roku-E8C3 WiFi → `ssh gateway@10.0.0.1` |
| Serial (recovery) | `/dev/ttyS0` at 115200 baud — works even if WiFi is down |

---

## Making edits after cutover

The source repo lives at `~/roku-gateway/` on the Pi.
Edit files there, then deploy the changes:

### Frontend (JS / CSS) — no restart needed

```bash
sudo rsync -a ~/roku-gateway/frontend/ /opt/sandos/frontend/
```

Then just **reload the browser**. ES modules are not cached aggressively.

### Backend (Python) — restart required

```bash
sudo rsync -a ~/roku-gateway/backend/ /opt/sandos/backend/
sudo systemctl restart sand-dashboard
```

### Helper scripts (`sand-*`)

```bash
sudo rsync -a ~/roku-gateway/scripts/helpers/ /opt/sandos/scripts/helpers/
sudo rsync -a ~/roku-gateway/scripts/helpers/ /usr/local/lib/sandos/
sudo chmod +x /opt/sandos/scripts/helpers/* /usr/local/lib/sandos/*
```

### nftables firewall template

```bash
sudo rsync ~/roku-gateway/config/nftables-sand.conf.tmpl /etc/sandos/
# Then reapply the firewall:
sudo /usr/local/lib/sandos/sand-fw apply
```

### Quick reference

| Changed | Command |
|---|---|
| Any `.js` or `.css` | `rsync frontend/` → reload browser |
| Any `.py` | `rsync backend/` → `systemctl restart sand-dashboard` |
| Helper script | `rsync scripts/helpers/` to both locations + `chmod +x` |
| nftables template | `rsync config/` → `sand-fw apply` |
| systemd unit | `rsync systemd/` → `systemctl daemon-reload` |

---

## Undo / rollback

**Automatic:** If you don't confirm within 5 minutes, the Pi reverts itself.

**Manual at any time:**

```bash
sudo /opt/sandos/scripts/sand-rollback
```

This restores the pre-cutover netplan and NetworkManager config and reboots.

**Emergency (serial console or SD card on another machine):**

```bash
# On the Pi's serial console (/dev/ttyS0, 115200):
sudo /opt/sandos/scripts/sand-rollback

# Or: mount the SD card on another machine and create this flag file:
touch /boot/firmware/sand-recovery
# On next boot, sand-recovery.service enters safe AP-only mode
```
