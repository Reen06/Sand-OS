#!/usr/bin/env bash
# uninstall.sh — Roku-E8C3 uninstaller.
#
# Stops and disables all services, restores network configuration from the
# cutover snapshot (if present), and removes installed files. The original
# network configuration is restored so the device returns to its pre-install
# connectivity state.
#
#   sudo ./uninstall.sh [--purge]
#
# --purge   also remove /etc/sandos, /var/lib/sandos and the
#           Python venv (leaves config and data by default for reinstall)
set -euo pipefail

PREFIX="/opt/sandos"
ETC="/etc/sandos"
STATE="/var/lib/sandos"
LOGDIR="/var/log/sandos"
HELPERDIR="/usr/local/lib/sandos"
SVC_USER="sand"
SNAP_DIR="${STATE}/cutover-snapshot"
PURGE=0

c_ok="\033[0;32m"; c_warn="\033[0;33m"; c_err="\033[0;31m"; c_x="\033[0m"
say()  { echo -e "${c_ok}==>${c_x} $*"; }
warn() { echo -e "${c_warn}warning:${c_x} $*" >&2; }

for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        -h|--help)
            echo "usage: sudo ./uninstall.sh [--purge]"
            echo "  --purge  remove config and data directories (default: keep)"
            exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 1 ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }

say "Stopping Roku-E8C3 services"
systemctl stop sand-watchdog.timer sand-watchdog.service 2>/dev/null || true
systemctl stop sand-dashboard sand-netapply sand-netapply sand-recovery \
    sand-firewall 2>/dev/null || true
systemctl disable sand-dashboard sand-netapply sand-recovery sand-firewall \
    sand-watchdog.timer 2>/dev/null || true

say "Removing systemd units"
for unit in sand-dashboard sand-netapply sand-recovery sand-firewall \
            sand-watchdog.service sand-watchdog.timer; do
    rm -f "/etc/systemd/system/${unit}"
done
systemctl daemon-reload

say "Removing privileged helpers and sudoers"
rm -f /etc/sudoers.d/sandos
rm -rf "$HELPERDIR"
rm -f /usr/local/sbin/sand-apply /usr/local/sbin/sand-rollback

say "Restoring network configuration"
if [ -d "$SNAP_DIR" ]; then
    ap_iface=$(cat "${SNAP_DIR}/ap-iface" 2>/dev/null || true)
    # Remove hostapd and dnsmasq configs we installed.
    rm -f /etc/hostapd/hostapd.conf /etc/dnsmasq.d/sand.conf \
          /etc/dnsmasq.d/sand-guest.conf /etc/sysctl.d/99-sandos.conf
    # Remove NM unmanaged override.
    rm -f /etc/NetworkManager/conf.d/00-sand-unmanaged.conf
    # Restore netplan if we have a snapshot.
    if [ -d "${SNAP_DIR}/netplan" ] && ls "${SNAP_DIR}/netplan/"*.yaml >/dev/null 2>&1; then
        cp -a "${SNAP_DIR}/netplan/." /etc/netplan/
        netplan apply 2>/dev/null || true
    fi
    # Restore NM connections.
    if [ -d "${SNAP_DIR}/nm" ]; then
        cp -a "${SNAP_DIR}/nm/." /etc/NetworkManager/system-connections/ 2>/dev/null || true
    fi
    # Re-hand the AP interface back to NM.
    [ -n "$ap_iface" ] && nmcli device set "$ap_iface" managed yes 2>/dev/null || true
    systemctl restart NetworkManager 2>/dev/null || true
    say "Network configuration restored from cutover snapshot"
else
    warn "No cutover snapshot found — restoring base networking state"
    rm -f /etc/hostapd/hostapd.conf /etc/dnsmasq.d/sand.conf \
          /etc/dnsmasq.d/sand-guest.conf
    rm -f /etc/NetworkManager/conf.d/00-sand-unmanaged.conf
    systemctl restart NetworkManager 2>/dev/null || true
fi

say "Flushing nftables sand table"
nft delete table inet sand 2>/dev/null || true

say "Removing WireGuard tunnels"
for i in 0 1 2 3 4 5 6 7 8 9; do
    ip link show "wg${i}" >/dev/null 2>&1 && \
        (wg-quick down "wg${i}" 2>/dev/null || true) || true
done

say "Removing application files"
rm -rf "$PREFIX"

if [ "$PURGE" -eq 1 ]; then
    say "Purging config and state (--purge)"
    rm -rf "$ETC" "$STATE" "$LOGDIR"
    userdel "$SVC_USER" 2>/dev/null || true
else
    say "Keeping ${ETC} and ${STATE} (pass --purge to remove)"
fi

# Restore dnsmasq and hostapd to system defaults.
systemctl disable hostapd dnsmasq 2>/dev/null || true
systemctl stop hostapd dnsmasq 2>/dev/null || true

echo -e "
${c_ok}================================================================${c_x}
  Roku-E8C3 uninstalled.

  Network configuration has been restored.
  Pi-hole and WireGuard packages are still installed (remove manually
  with: sudo apt remove pihole wireguard-tools if no longer needed).
${c_ok}================================================================${c_x}"
