# Troubleshooting — Roku-E8C3

## No `Roku-E8C3` SSID visible after cutover

1. Check hostapd is running: `systemctl status hostapd`
2. Check there are no errors: `journalctl -u hostapd --no-pager | tail -30`
3. Check the AP interface has its address: `ip addr show wlan0`
4. Re-apply networking: `sudo roku-net apply`
5. Last resort: `sudo roku-rollback` to revert to previous networking

---

## Dashboard not reachable at `http://10.0.0.1`

1. Confirm you're connected to `Roku-E8C3` (not another network)
2. Check dashboard: `systemctl status roku-dashboard`
3. Check it's bound to the right address: `ss -tlnp | grep :80`
4. Restart: `sudo systemctl restart roku-dashboard`
5. View logs: `journalctl -u roku-dashboard -n 50`

---

## No internet on connected devices

1. Check upstream: `nmcli connection show --active`
2. Check IP forwarding: `sysctl net.ipv4.ip_forward` (should be `1`)
3. Check nftables: `sudo nft list table inet roku` — look for `postrouting masquerade`
4. Check the upstream interface has a default route: `ip route show`
5. Try connecting upstream manually from WiFi page

---

## DNS not resolving

1. Check Pi-hole: `systemctl status pihole-FTL`
2. Test DNS directly: `dig @10.0.0.1 example.com`
3. Check dnsmasq is DHCP-only (port=0): `grep port= /etc/dnsmasq.d/roku.conf`
4. If Pi-hole is down, DNS failover should activate within ~6 minutes (watchdog)
5. Force failover: `sudo roku-pihole dns-failover-on`

---

## WireGuard tunnel won't connect

1. Check the tunnel state: `sudo wg show wg0`
2. Check the config exists: `ls -la /etc/wireguard/wg0.conf`
3. Check the endpoint is reachable: `ping -c3 <endpoint-host>`
4. Check nftables allows WireGuard ports: `sudo nft list table inet roku | grep 51820`
5. Check logs: `journalctl -k | grep wireguard`

---

## Kill-switch not working (device reaches internet without VPN)

1. Verify the device has a fwmark: `sudo nft list table inet roku | grep <device-mac>`
2. Verify the ip rule exists: `ip rule show | grep fwmark`
3. Rebuild firewall: `sudo roku-fw apply`
4. Re-apply networking (also rebuilds firewall): `sudo roku-net apply`

---

## USB WiFi adapter not detected

1. Check the adapter is seen by the kernel: `lsusb`
2. Check the driver loaded: `lsmod | grep rtw`
3. Check interfaces: `iw dev`
4. If the adapter was plugged in after boot, the watchdog will re-apply networking within 2 minutes
5. Trigger manually: `sudo roku-net apply`

---

## Pi-hole blocking legitimate traffic

1. Whitelist from the Pi-hole dashboard (Pi-hole has its own web UI if needed)
2. Or from the CLI: `pihole whitelist example.com`
3. Or disable blocking temporarily from the Roku dashboard (Pi-hole page)

---

## Service diagnostics at a glance

```bash
# All Roku services
systemctl status roku-dashboard roku-netapply roku-recovery roku-watchdog.timer roku-firewall

# Recent events from all Roku units
journalctl -u 'roku-*' --since '1 hour ago' --no-pager

# Network state
ip addr show
ip rule show
ip route show
sudo nft list table inet roku
sudo wg show all

# AP status
iw dev wlan0 info
iw dev wlan0 station dump
```
