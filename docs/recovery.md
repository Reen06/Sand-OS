# Recovery Guide — Roku-E8C3

The device is designed to always be recoverable. There are four escalating recovery paths.

---

## Level 1: Auto-rollback (cutover failed)

When you run `sudo roku-apply`, a 5-minute timer starts. If you don't confirm the cutover, the device automatically restores the previous network and reboots.

You don't need to do anything — just wait.

---

## Level 2: Manual rollback (you're on the Pi)

If you can reach the Pi via serial console or have physical access:

```bash
sudo roku-rollback
```

This stops the access-point services, restores the pre-cutover netplan and NetworkManager state, and reboots. The device comes back on the original network.

---

## Level 3: Recovery mode via SD card (locked out completely)

If you can't connect to the Pi at all, mount the SD card on another machine and create the recovery flag:

```bash
# On the other machine, mount the Pi's boot partition
sudo mount /dev/sdX1 /mnt
touch /mnt/roku-recovery
sudo umount /mnt
```

Insert the card and power on the Pi. The `roku-recovery.service` detects the flag at boot, calls `apply_networking()` with the saved settings, and removes the flag. The AP comes up on `10.0.0.1` regardless of previous state.

---

## Level 4: Reflash

If nothing else works, reflash Raspberry Pi OS and run `install.sh` again. Your config and data in `/etc/roku-gateway/` and `/var/lib/roku-gateway/` survive if you kept the SD card (the uninstaller only removes them with `--purge`).

---

## Watchdog

The `roku-watchdog` service runs every 2 minutes and:
- Restarts hostapd/dnsmasq if the AP goes down
- Restarts the dashboard if it crashes
- Activates DNS failover if Pi-hole is down for 3+ consecutive checks
- Re-applies networking if the USB adapter is unplugged/replugged

Monitor it:

```bash
journalctl -u roku-watchdog -f
```

---

## Useful commands

```bash
# Check all Roku services
systemctl status roku-dashboard roku-netapply roku-recovery roku-watchdog.timer

# View live logs
journalctl -u roku-dashboard -f

# Re-apply networking manually (AP, DHCP, firewall)
sudo roku-net apply

# Rebuild firewall from DB
sudo roku-fw apply

# Check WireGuard tunnels
sudo wg show all

# Check nftables rules
sudo nft list ruleset

# Check policy routing
ip rule show
ip route show table all | grep -v "^default"
```
