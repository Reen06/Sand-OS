"""Networking apply tool — renders config and brings the access point up.

Runs as root: at boot via roku-netapply.service, and on demand via the
roku-net sudo helper. It is idempotent — safe to run repeatedly. Progress is
written to stdout, which systemd captures into the journal (visible on the
dashboard Logs page under "Network apply").

    python -m app.netapply {apply|firewall|status}

The database is opened read-only so this root process never creates
root-owned WAL files the unprivileged dashboard would be unable to write.

Package prerequisites handled once by install.sh: hostapd unmasked with
DAEMON_CONF set, dnsmasq conf-dir enabled, the AP interface marked unmanaged
in NetworkManager, and a real AP passphrase stored in the database.
"""
from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import sys

from .core.settings import settings
from .db.repo import Database
from .services import network


def log(msg: str) -> None:
    print(f"[netapply] {msg}", flush=True)


def run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"{' '.join(cmd)} -> rc={proc.returncode} {proc.stderr.strip()}")
        if check:
            raise RuntimeError(f"command failed: {' '.join(cmd)}")
    return proc


def render(template: str, values: dict) -> str:
    text = (settings.templates_dir / template).read_text()
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


def _net(cidr: str) -> str:
    return str(ipaddress.ip_network(cidr, strict=False))


def _setting(db: Database, key: str, default: str) -> str:
    val = db.get_setting(key)
    return val if val else default


def apply_firewall(db: Database, ifaces: dict) -> bool:
    from .services.firewall import device_rules_nft
    ap = ifaces["ap"] or "lo"
    up = ifaces["upstream"] or "lo"
    ruleset = render("nftables-roku.conf.tmpl", {
        "AP_IFACE": ap,
        "UPSTREAM_IFACE": up,
        "LAN_NET": _net(settings.lan_cidr),
        "GUEST_NET": _net(settings.guest_cidr),
    })
    # Inject per-device mangle (for policy routing) and forward kill-switch rules.
    mangle_rules, forward_rules = device_rules_nft(db)
    ruleset = ruleset.replace("        # ROKU-MANGLE-RULES", mangle_rules)
    ruleset = ruleset.replace("        # ROKU-DEVICE-RULES", forward_rules)
    out_path = settings.config_dir / "nftables-roku.conf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ruleset)
    ok = run(["nft", "-f", str(out_path)]).returncode == 0
    log("firewall ruleset applied" if ok else "firewall ruleset FAILED to apply")
    return ok


def apply_networking(db: Database) -> int:
    ifaces = network.resolve_interfaces()
    ap = ifaces["ap"]
    up = ifaces["upstream"]
    if not ap:
        log("no AP-capable interface present — access point cannot start")
        return 1
    log(f"AP={ap} upstream={up or 'none'} radios={ifaces['radio_count']}")

    ap_ip = settings.lan_cidr.split("/")[0]
    prefix = ".".join(ap_ip.split(".")[:3])

    # hostapd — main BSS
    hostapd = render("hostapd.conf.tmpl", {
        "COUNTRY": _setting(db, "wifi_country", "US"),
        "AP_IFACE": ap,
        "SSID": _setting(db, "ap_ssid", settings.ap_ssid),
        "CHANNEL": _setting(db, "ap_channel", "6"),
        "WPA_PASSPHRASE": _setting(db, "ap_passphrase", "roku-setup-0000"),
    })
    # Append guest BSS block if enabled.
    guest_enabled = _setting(db, "guest_enabled", "0") == "1"
    guest_ssid = _setting(db, "guest_ssid", "Roku-E8C3-Guest")
    guest_pw   = _setting(db, "guest_passphrase", "")
    guest_ip   = settings.guest_cidr.split("/")[0]
    if guest_enabled and len(guest_pw) >= 8:
        hostapd += f"""
# --- Guest BSS ---
bss={ap}
ssid={guest_ssid}
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase={guest_pw}
ignore_broadcast_ssid=0
ap_isolate=1
"""
    os.makedirs("/etc/hostapd", exist_ok=True)
    with open("/etc/hostapd/hostapd.conf", "w") as fh:
        fh.write(hostapd)
    os.chmod("/etc/hostapd/hostapd.conf", 0o600)

    # dnsmasq — main LAN DHCP
    dnsmasq = render("dnsmasq-roku.conf.tmpl", {
        "AP_IFACE": ap,
        "UPSTREAM_IFACE": up or "lo",
        "DNS_PORT": _setting(db, "dns_port", "53"),
        "UPSTREAM_DNS_1": _setting(db, "upstream_dns_1", "1.1.1.1"),
        "UPSTREAM_DNS_2": _setting(db, "upstream_dns_2", "9.9.9.9"),
        "LAN_DHCP_START": _setting(db, "lan_dhcp_start", f"{prefix}.50"),
        "LAN_DHCP_END": _setting(db, "lan_dhcp_end", f"{prefix}.200"),
        "AP_IP": ap_ip,
        "LAN_DNS": _setting(db, "lan_dns", ap_ip),
    })
    os.makedirs("/etc/dnsmasq.d", exist_ok=True)
    with open("/etc/dnsmasq.d/roku.conf", "w") as fh:
        fh.write(dnsmasq)

    # dnsmasq — guest DHCP scope (separate file, removed when guest disabled).
    guest_conf = "/etc/dnsmasq.d/roku-guest.conf"
    if guest_enabled:
        gprefix = ".".join(guest_ip.split(".")[:3])
        guest_dnsmasq = (
            f"# Roku-E8C3 guest DHCP scope — auto-generated\n"
            f"dhcp-range=set:guest,{gprefix}.50,{gprefix}.200,255.255.255.0,4h\n"
            f"dhcp-option=tag:guest,option:router,{guest_ip}\n"
            f"dhcp-option=tag:guest,option:dns-server,{guest_ip}\n"
        )
        with open(guest_conf, "w") as fh:
            fh.write(guest_dnsmasq)
        # Bring up the guest interface address.
        run(["ip", "addr", "add", f"{guest_ip}/24", "dev", ap, "label", f"{ap}:1"],)
    else:
        try:
            os.unlink(guest_conf)
        except FileNotFoundError:
            pass

    # AP interface address
    run(["ip", "addr", "flush", "dev", ap])
    run(["ip", "addr", "add", f"{ap_ip}/24", "dev", ap])
    run(["ip", "link", "set", ap, "up"])

    # IP forwarding
    run(["sysctl", "-q", "-w", "net.ipv4.ip_forward=1"])

    # Firewall before services so NAT/forwarding are ready.
    apply_firewall(db, ifaces)

    # Services
    run(["systemctl", "unmask", "hostapd"])
    hostapd_rc = run(["systemctl", "restart", "hostapd"]).returncode
    dnsmasq_rc = run(["systemctl", "restart", "dnsmasq"]).returncode

    ok = hostapd_rc == 0 and dnsmasq_rc == 0
    log("access point is up" if ok else "access point services reported errors")

    # Re-enable WireGuard tunnels that were active before the last reboot.
    _restore_wireguard_tunnels(db)

    return 0 if ok else 2


def _restore_wireguard_tunnels(db: Database) -> None:
    """Re-connect WireGuard tunnels marked enabled in the DB.

    ip rule / ip route state is not persistent; roku-wg up re-adds it.
    Called at the end of apply_networking so VPN routing survives reboots.
    """
    try:
        from .core.privileged import run_helper
        rows = db.query(
            "SELECT iface, name FROM wireguard_profiles WHERE enabled=1")
        for row in rows:
            iface, name = row["iface"], row["name"]
            res = run_helper("roku-wg", "up", iface, timeout=20)
            if res.ok:
                log(f"WireGuard tunnel '{name}' ({iface}) restored")
            else:
                log(f"WireGuard tunnel '{name}' ({iface}) restore failed: {res.stderr}")
    except Exception as exc:
        log(f"WireGuard restore skipped: {exc}")


def show_status(db: Database) -> int:
    print(json.dumps({
        "ap": network.ap_status(),
        "upstream": network.upstream_status(),
    }, indent=2))
    return 0


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "apply"
    if os.geteuid() != 0 and action != "status":
        log("must run as root")
        return 1
    db = Database(settings.db_path, read_only=True)
    try:
        if action == "apply":
            return apply_networking(db)
        if action == "firewall":
            return 0 if apply_firewall(db, network.resolve_interfaces()) else 2
        if action == "status":
            return show_status(db)
        log(f"unknown action: {action}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
