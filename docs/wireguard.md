# WireGuard & VPN Guide — Roku-E8C3

## How it works

WireGuard tunnels are managed per-profile. Each profile gets a `wg0`–`wg9` interface slot and a fwmark (`50`–`59`). Per-device routing rules in nftables mark each device's packets; Linux policy routing then steers marked packets into the correct WireGuard tunnel.

The VPN kill-switch is always on: if a device is assigned to a tunnel and the tunnel goes down, forwarded traffic is dropped. The device retains access to `10.0.0.1` (dashboard) and DHCP/DNS so it can never be completely cut off.

---

## Uploading a WireGuard profile

1. Open the dashboard → **VPN** page
2. Click **Upload .conf**
3. Select your `.conf` file and give the profile a name
4. Click **Upload**

The profile is validated and stored at `/etc/wireguard/<iface>.conf` (mode 0600, root only).

---

## Connecting / disconnecting

From the VPN page, click **Connect** or **Disconnect** next to the profile.

From the CLI:

```bash
sudo roku-wg up wg0
sudo roku-wg down wg0
```

---

## Routing a device through VPN

1. Open **Routing** page
2. Find the device by hostname or MAC
3. Select the VPN profile from the dropdown
4. Click **Apply**

The nftables ruleset and policy routing are updated immediately.

---

## Per-device routing options

| Option | Effect |
|--------|--------|
| `direct` | Default route — internet via upstream adapter, no VPN |
| `<wg profile>` | Route all traffic through the named WireGuard tunnel |
| `blocked` | Drop all forwarded traffic for this device |

---

## Kill-switch behaviour

| Tunnel state | Device route | Result |
|---|---|---|
| Up | `wg0` | Traffic exits via `wg0` — VPN active |
| Down | `wg0` | Forwarded traffic dropped — kill-switch active |
| Down | `direct` | Traffic exits via upstream — no kill-switch |
| Any | `blocked` | All traffic dropped |

Dashboard and DHCP/DNS are always accessible regardless of tunnel state.

---

## DNS and VPN

When a tunnel is connected, Pi-hole's upstream DNS is updated to use the tunnel's DNS server (if specified in the `.conf` `DNS=` field). This prevents DNS leaks. When all tunnels are disconnected, Pi-hole reverts to the configured default (Cloudflare / Quad9).

---

## Multiple tunnels

Up to 10 simultaneous WireGuard profiles (`wg0`–`wg9`). Each device can be routed through a different tunnel. The default profile (set per VPN profile) is used when the Routing page has not been configured for a device.

---

## QR code import (mobile)

On the VPN page, click the QR icon to open the QR scanner. The browser camera decodes the config and uploads it to the router. Requires HTTPS or localhost (camera permission is only granted in secure contexts).

---

## Troubleshooting

```bash
# Check tunnel state
sudo wg show wg0

# Check policy routing rules
ip rule show

# Check routing table for wg0 (table 200)
ip route show table 200

# Check nftables marks
sudo nft list table inet roku

# View WireGuard logs
journalctl -k | grep wireguard
```
