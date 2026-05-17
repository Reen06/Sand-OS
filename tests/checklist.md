# Roku-E8C3 — Verification Checklist

Run this checklist after every significant change and before each cutover.
Check each item manually unless marked *automated*.

---

## 0. Pre-requisites

- [ ] Pi has at least 256 MB free RAM (`free -h`)
- [ ] `/opt/sandos/` is present (install complete)
- [ ] USB WiFi adapter is plugged in (two radios: `iw dev` shows two)
- [ ] `sudo sand-apply` has NOT been run yet (or `sand-rollback` was used)

---

## 1. Fresh install

- [ ] `sudo ./install.sh` completes with no red errors
- [ ] Dashboard password was accepted (≥ 10 chars)
- [ ] WiFi password was accepted (≥ 8 chars)
- [ ] `sand-dashboard.service` is active: `systemctl is-active sand-dashboard`
- [ ] `sand-netapply.service` is NOT running yet (deferred to `sand-apply`)
- [ ] `/var/lib/sandos/sand.db` exists and is owned by `sand:sand`
- [ ] `/etc/sudoers.d/sandos` present and `visudo -c` passes
- [ ] `sudo -l -U sand` shows sand-sys, sand-net, sand-fw, sand-wifi, sand-wg, sand-pihole
- [ ] Dashboard reachable at `http://<current-IP>` before cutover
- [ ] Sign in with dashboard password succeeds

---

## 2. Access-point boot

```
sudo sand-apply
```

- [ ] Command prints all four `[1/4]…[4/4]` steps
- [ ] Auto-rollback timer armed: `systemctl list-timers sand-rollback-guard`
- [ ] SSID `Roku-E8C3` appears in WiFi scan on a phone within 30 s
- [ ] Phone connects to `Roku-E8C3` and receives a `10.0.0.x` address
- [ ] Dashboard reachable from phone at `http://10.0.0.1`

### Confirm cutover (prevents rollback)

```
sudo sand-apply --confirm
```

- [ ] "Cutover confirmed" message printed
- [ ] `sand-rollback-guard.timer` is no longer active

---

## 3. Dashboard — all pages

- [ ] **Overview**: shows AP status green, upstream status, system stats (CPU, RAM, temp)
- [ ] **Devices**: lists connected clients with MAC and IP
- [ ] **WiFi**: shows current upstream SSID, signal bars, disconnect + randomize-MAC buttons
- [ ] **VPN**: empty state renders correctly; Upload button opens modal
- [ ] **Routing**: lists devices; "Direct" route badge shown for all
- [ ] **Guest**: toggle is off; SSID/passphrase fields present
- [ ] **Settings**: hostname, SSID, passphrase, DHCP range, DNS fields visible
- [ ] **Logs**: shows recent log entries; "Network apply" entries from cutover present

---

## 4. Upstream WiFi connect

From the WiFi page:

- [ ] Scan returns visible networks (including the test AP)
- [ ] Connecting with correct password succeeds; status updates to connected
- [ ] Internet icon on Overview turns green
- [ ] Devices on `Roku-E8C3` can reach the internet (ping 1.1.1.1)
- [ ] Saved networks list shows the just-connected network
- [ ] Forget network removes it from the list

---

## 5. Captive portal

Connect upstream to a network behind a captive portal:

- [ ] WiFi status shows `"status": "portal"` via `GET /wifi/portal`
- [ ] Yellow banner appears on the WiFi page with "Open portal page" button
- [ ] Button opens the portal URL in a new browser tab
- [ ] After signing in, portal banner disappears within the next poll cycle

---

## 6. WireGuard upload and routing

- [ ] Upload a valid `.conf` file from the VPN page → profile appears
- [ ] Connect button turns the tunnel on; status dot turns green
- [ ] `wg show wg0` on the Pi shows the active tunnel with a handshake timestamp
- [ ] Policy routing added: `ip rule show` has a fwmark rule for wg0
- [ ] Set device route to the VPN profile from the Routing page
- [ ] Device traffic is marked: `nft list ruleset` shows the device's fwmark set
- [ ] Device reaches the internet through the VPN endpoint

### Kill-switch

- [ ] Disconnect the VPN tunnel from the dashboard
- [ ] Device with VPN route assignment **cannot** reach the internet
- [ ] Device **can** still reach `http://10.0.0.1` (dashboard)
- [ ] Device **can** still get DHCP/DNS responses

---

## 7. Pi-hole DNS filtering

- [ ] `pihole-FTL` service is active: `systemctl is-active pihole-FTL`
- [ ] Dashboard Devices page shows block stats (queries / blocked)
- [ ] Known ad domain is blocked from a connected device
- [ ] Disabling blocking from the dashboard disables immediately
- [ ] Re-enabling restores filtering
- [ ] Pi-hole status widget on Overview shows correct blocked percentage

---

## 8. Guest network

- [ ] Enable guest SSID from the Guest page; set a passphrase
- [ ] After save, `Roku-E8C3-Guest` (or custom name) appears in WiFi scan
- [ ] Guest device connects and receives `10.0.1.x` address
- [ ] Guest device can reach the internet
- [ ] Guest device **cannot** ping LAN devices (`10.0.0.x`)
- [ ] LAN device **cannot** ping guest device (`10.0.1.x`)
- [ ] Guest devices appear on the Guest page device list

---

## 9. Reboot persistence

```
sudo reboot
```

After reboot:

- [ ] `Roku-E8C3` SSID is broadcasting within 60 s
- [ ] Dashboard reachable at `http://10.0.0.1`
- [ ] Upstream WiFi reconnects automatically (NM saved profile)
- [ ] Internet works through the AP
- [ ] Guest network broadcasts if it was enabled
- [ ] WireGuard tunnels marked enabled are reconnected (`wg show`)
- [ ] Device routing assignments are restored (check Routing page)
- [ ] Firewall ruleset is active: `nft list table inet sand`

---

## 10. USB adapter removal and re-insertion

- [ ] Unplug the USB WiFi adapter
- [ ] `Roku-E8C3` SSID continues broadcasting on the onboard radio
- [ ] Dashboard is still reachable at `http://10.0.0.1`
- [ ] Internet is unavailable (expected — upstream adapter gone)
- [ ] Watchdog log shows "Radio count changed" within 2 minutes
- [ ] Re-plug the USB adapter
- [ ] Watchdog re-applies networking within 2 minutes
- [ ] Internet is restored on connected devices

---

## 11. Auto-rollback drill

```
# Cut over without confirming:
sudo sand-apply
# Wait for ROLLBACK_TIMEOUT (default 300 s) without confirming
```

- [ ] Device reboots automatically after the timeout
- [ ] Device comes back on the **original** network (not `10.0.0.1`)
- [ ] Previous WiFi SSID is visible again
- [ ] SSH / original network session is recoverable

---

## 12. Recovery flag

From another machine (or USB-mounted SD card):

```
touch /boot/firmware/sand-recovery
sudo reboot
```

- [ ] After reboot, `sand-recovery.service` detects the flag
- [ ] `apply_networking()` is called at boot regardless of saved state
- [ ] `/boot/firmware/sand-recovery` is removed automatically
- [ ] AP comes up cleanly

---

## 13. DNS failover drill

```
sudo systemctl stop pihole-FTL
```

- [ ] After 3 watchdog ticks (≈ 6 min), DNS failover activates
- [ ] Devices connected to `Roku-E8C3` can still resolve DNS
- [ ] Logs page shows "DNS failover activated" event
- [ ] Start `pihole-FTL` again: `sudo systemctl start pihole-FTL`
- [ ] Within 2 minutes, watchdog restores normal Pi-hole DNS
- [ ] Logs page shows "Pi-hole recovered, DNS failover cleared"

---

## 14. `uninstall.sh`

```
sudo ./uninstall.sh
```

- [ ] All sand-* services stopped and disabled
- [ ] `/opt/sandos/` removed
- [ ] `/etc/sudoers.d/sandos` removed
- [ ] nftables sand table flushed: `nft list tables` shows no `sand` table
- [ ] WireGuard tunnels brought down: `ip link show | grep wg` empty
- [ ] Original netplan / NM networking restored
- [ ] Device connects back to the pre-install network after restart

```
sudo ./uninstall.sh --purge
```

- [ ] `/etc/sandos/`, `/var/lib/sandos/`, `/var/log/sandos/` removed
- [ ] `sand` system user deleted

---

## 15. Security spot-checks

- [ ] Dashboard login rejects wrong passwords
- [ ] Session cookie is `HttpOnly; SameSite=Strict`
- [ ] State-changing API calls without CSRF token return 403
- [ ] Dashboard not reachable from the upstream interface IP (firewall blocks it)
- [ ] `sudo -l -U sand` shows only the whitelisted helpers (no `ALL` or bash)
- [ ] `/etc/sudoers.d/sandos` is mode 0440, owned root:root
- [ ] WireGuard conf files in `/etc/wireguard/` are mode 0600
- [ ] `/var/lib/sandos/sand.db` is mode 0640, not world-readable
