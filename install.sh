#!/usr/bin/env bash
# install.sh — Roku-E8C3 secure travel router installer.
#
# Installs the dashboard, networking foundation and services on Raspberry Pi
# OS. It is STAGED: nothing about the live network changes here. When you are
# ready, run `sudo sand-apply` to cut the device over into router mode.
#
#   sudo ./install.sh [--unattended] [--with-raspap]
#
# --unattended    take the dashboard/WiFi passwords from the environment
#                 (SAND_DASHBOARD_PASSWORD, SAND_AP_PASSWORD) or generate them
# --with-raspap   additionally run the RaspAP installer (optional; its web UI
#                 is disabled — the foundation here already uses RaspAP's
#                 proven hostapd/dnsmasq/nftables components directly)
set -euo pipefail

SRC="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PREFIX="/opt/sandos"
ETC="/etc/sandos"
STATE="/var/lib/sandos"
LOGDIR="/var/log/sandos"
HELPERDIR="/usr/local/lib/sandos"
DB="${STATE}/sand.db"
SVC_USER="sand"
UNATTENDED=0
WITH_RASPAP=0
WITH_PIHOLE=1

PKGS="hostapd dnsmasq nftables wireguard-tools iw rfkill qrencode sqlite3 \
rsync python3-venv python3-pip ca-certificates"

c_ok="\033[0;32m"; c_warn="\033[0;33m"; c_err="\033[0;31m"; c_x="\033[0m"
say()  { echo -e "${c_ok}==>${c_x} $*"; }
warn() { echo -e "${c_warn}warning:${c_x} $*" >&2; }
die()  { echo -e "${c_err}error:${c_x} $*" >&2; exit 1; }

for arg in "$@"; do
    case "$arg" in
        --unattended)   UNATTENDED=1 ;;
        --with-raspap)  WITH_RASPAP=1 ;;
        --no-pihole)    WITH_PIHOLE=0 ;;
        -h|--help)      sed -n '2,16p' "$0"; exit 0 ;;
        *) die "unknown option: $arg" ;;
    esac
done

# --------------------------------------------------------------- validation
validate_env() {
    say "Validating environment"
    [ "$(id -u)" -eq 0 ] || die "must run as root (use sudo)"
    [ -f /etc/debian_version ] || die "this installer targets Raspberry Pi OS / Debian"
    [ -e /proc/device-tree/model ] || warn "not a Raspberry Pi — continuing anyway"
    local free_kb
    free_kb=$(df --output=avail / | tail -1)
    [ "$free_kb" -gt 524288 ] || die "need at least 512 MB free disk space"
    command -v apt-get >/dev/null || die "apt-get not found"
    id -u 1000 >/dev/null 2>&1 || warn "no uid 1000 account found"
    getent passwd pi >/dev/null && warn "default 'pi' account exists — consider removing it" || true
}

# --------------------------------------------------------------- packages
install_packages() {
    say "Installing system packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    # shellcheck disable=SC2086
    apt-get install -y -qq $PKGS
}

# --------------------------------------------------------------- service user
create_user() {
    if id "$SVC_USER" >/dev/null 2>&1; then
        say "Service user '${SVC_USER}' already exists"
    else
        say "Creating service user '${SVC_USER}'"
        useradd --system --home-dir "$PREFIX" --shell /usr/sbin/nologin "$SVC_USER"
    fi
    # Journal access for the Logs page; netdev for nmcli queries.
    usermod -aG systemd-journal,netdev "$SVC_USER" 2>/dev/null || true
}

# --------------------------------------------------------------- files
install_files() {
    say "Installing application files to ${PREFIX}"
    mkdir -p "$PREFIX"
    rsync -a --delete \
        --exclude='.git' --exclude='.venv' --exclude='.devdata' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='backups' \
        "$SRC/" "$PREFIX/"
}

create_venv() {
    say "Creating Python virtual environment"
    if [ ! -x "$PREFIX/venv/bin/python" ]; then
        python3 -m venv "$PREFIX/venv"
    fi
    "$PREFIX/venv/bin/pip" install --quiet --disable-pip-version-check --upgrade pip
    "$PREFIX/venv/bin/pip" install --quiet --disable-pip-version-check \
        -r "$PREFIX/backend/requirements.txt"
}

setup_dirs() {
    say "Creating runtime directories"
    mkdir -p "$ETC" "$STATE" "$STATE/backups" "$LOGDIR" "$HELPERDIR"
    chown -R "$SVC_USER:$SVC_USER" "$STATE" "$LOGDIR"
    chmod 750 "$STATE" "$LOGDIR"
}

install_config() {
    say "Installing configuration"
    [ -f "$ETC/sandos.env" ] || cp "$SRC/config/sandos.env" "$ETC/sandos.env"
    [ -f "$ETC/interfaces.conf" ]  || cp "$SRC/config/interfaces.conf"  "$ETC/interfaces.conf"
    echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-sandos.conf
    sysctl -q -w net.ipv4.ip_forward=1 || true
}

install_helpers() {
    say "Installing privileged helpers"
    install -m 0755 -o root -g root "$SRC"/scripts/helpers/* "$HELPERDIR/"
    ln -sf "$PREFIX/scripts/sand-apply"    /usr/local/sbin/sand-apply
    ln -sf "$PREFIX/scripts/sand-rollback" /usr/local/sbin/sand-rollback
    chmod 0755 "$PREFIX"/scripts/sand-apply "$PREFIX"/scripts/sand-rollback
    local sudoers="/etc/sudoers.d/sandos"
    cat > "${sudoers}.tmp" <<EOF
# Roku-E8C3 — the dashboard service user may run only these helper scripts.
${SVC_USER} ALL=(root) NOPASSWD: ${HELPERDIR}/sand-sys, ${HELPERDIR}/sand-net, \
${HELPERDIR}/sand-fw, ${HELPERDIR}/sand-wifi, ${HELPERDIR}/sand-wg, \
${HELPERDIR}/sand-pihole
EOF
    if visudo -cqf "${sudoers}.tmp"; then
        install -m 0440 -o root -g root "${sudoers}.tmp" "$sudoers"
        rm -f "${sudoers}.tmp"
    else
        rm -f "${sudoers}.tmp"
        die "generated sudoers file failed validation"
    fi
}

install_systemd() {
    say "Installing systemd services"
    install -m 0644 "$SRC"/systemd/*.service /etc/systemd/system/
    [ -n "$(echo "$SRC"/systemd/*.timer)" ] && \
        install -m 0644 "$SRC"/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true
    systemctl daemon-reload
}

prepare_host() {
    say "Preparing host networking (staged — not yet applied)"
    # hostapd: unmask, point at our config, do not start independently.
    systemctl unmask hostapd 2>/dev/null || true
    systemctl disable hostapd 2>/dev/null || true
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd
    # dnsmasq: ensure the drop-in directory is read; netapply starts it.
    grep -q '^conf-dir=/etc/dnsmasq.d' /etc/dnsmasq.conf 2>/dev/null || \
        echo 'conf-dir=/etc/dnsmasq.d/,*.conf' >> /etc/dnsmasq.conf
    systemctl disable dnsmasq 2>/dev/null || true
}

install_raspap() {
    [ "$WITH_RASPAP" -eq 1 ] || return 0
    say "Running the RaspAP installer (optional component)"
    if curl -sSL https://install.raspap.com | bash -s -- --yes --openvpn 0 \
            --adblock 0 --wireguard 0 >/dev/null 2>&1; then
        systemctl disable --now lighttpd 2>/dev/null || true
        say "RaspAP installed; its web UI is disabled (dashboard is the UI)"
    else
        warn "RaspAP installer did not complete — the built-in foundation is used instead"
    fi
}

install_pihole() {
    [ "$WITH_PIHOLE" -eq 1 ] || return 0
    say "Installing Pi-hole (unattended)"

    local ap_ip
    ap_ip=$(echo "${SAND_LAN_CIDR:-10.0.0.1/24}" | cut -d/ -f1)

    # Pre-seed Pi-hole configuration so the installer runs non-interactively.
    mkdir -p /etc/pihole
    cat > /etc/pihole/setupVars.conf <<EOF
PIHOLE_INTERFACE=lo
IPV4_ADDRESS=${ap_ip}/24
QUERY_LOGGING=true
INSTALL_WEB_SERVER=false
INSTALL_WEB_INTERFACE=false
LIGHTTPD_ENABLED=false
CACHE_SIZE=10000
DNS_FQDN_REQUIRED=true
DNS_BOGUS_PRIV=true
DNSSEC=false
TEMPERATUREUNIT=C
WEBUIBOXEDLAYOUT=traditional
API_EXCLUDE_DOMAINS=
API_EXCLUDE_CLIENTS=
API_QUERY_LOG_SHOW=all
API_PRIVACY_MODE=false
PIHOLE_DNS_1=1.1.1.1
PIHOLE_DNS_2=9.9.9.9
BLOCKING_ENABLED=true
EOF

    # Some installers check OS version — bypass for trixie.
    local installer_ok=0
    if PIHOLE_SKIP_OS_CHECK=true \
            bash <(curl -sSL https://install.pi-hole.net) --unattended 2>&1 | \
            grep -v "^  \\[" ; then
        installer_ok=1
    fi

    if [ "$installer_ok" -eq 1 ] && command -v pihole >/dev/null 2>&1; then
        # Pi-hole's FTL must NOT start on port 53 until we cut over (dnsmasq
        # handles DNS for now). We start it but configure via our db.
        systemctl enable pihole-FTL 2>/dev/null || true
        # Pi-hole v6 has its own embedded web server (replaces lighttpd).
        # Move it off port 80 so our dashboard can own that port.
        pihole-FTL --config webserver.port 8080 2>/dev/null || true
        # Disable lighttpd in case it is still present (Pi-hole v5 path).
        systemctl disable --now lighttpd 2>/dev/null || true
        say "Pi-hole installed; pihole-FTL enabled (web UI on :8080, activates at cutover)"
    else
        warn "Pi-hole installer did not complete — DNS filtering will be unavailable"
        warn "Re-run with PIHOLE_SKIP_OS_CHECK=true bash <(curl -sSL https://install.pi-hole.net) --unattended"
    fi
}

# --------------------------------------------------------------- database
prompt_password() {  # $1 label  $2 minlen  -> echoes password
    local label="$1" minlen="$2" p1 p2
    while :; do
        read -rsp "  ${label}: " p1; echo
        [ "${#p1}" -ge "$minlen" ] || { echo "  (need at least ${minlen} characters)"; continue; }
        read -rsp "  confirm ${label}: " p2; echo
        [ "$p1" = "$p2" ] || { echo "  (passwords did not match)"; continue; }
        echo "$p1"; return 0
    done
}

init_database() {
    say "Initialising database and credentials"
    local dash_pw ap_pw
    if [ "$UNATTENDED" -eq 1 ]; then
        dash_pw="${SAND_DASHBOARD_PASSWORD:-$(openssl rand -base64 12)}"
        ap_pw="${SAND_AP_PASSWORD:-$(openssl rand -base64 12)}"
        warn "unattended: dashboard password = ${dash_pw}"
        warn "unattended: WiFi password      = ${ap_pw}"
    else
        echo "  Set the dashboard admin password (used to sign in at http://10.0.0.1)"
        dash_pw="$(prompt_password 'dashboard password' 10)"
        echo "  Set the WiFi password for the 'Roku-E8C3' network"
        ap_pw="$(prompt_password 'WiFi password' 8)"
    fi
    SAND_DB="$DB" SAND_DASH_PW="$dash_pw" SAND_AP_PW="$ap_pw" \
        "$PREFIX/venv/bin/python" - <<'PYEOF'
import os, sys
from pathlib import Path
sys.path.insert(0, "/opt/sandos/backend")
from app.db.repo import Database
from app.db.migrations import init_db
from app.core.security import hash_password
db = Database(os.environ["SAND_DB"])
init_db(db, Path("/opt/sandos/backend/app/db/schema.sql"))
db.set_setting("dashboard_password", hash_password(os.environ["SAND_DASH_PW"]))
db.set_setting("ap_passphrase", os.environ["SAND_AP_PW"])
db.set_setting("ap_ssid", "Roku-E8C3")
db.set_setting("hostname", "Roku-E8C3")
db.set_setting("lan_ip", "10.0.0.1")
# dns_port=0 lets Pi-hole handle DNS; set to 53 if Pi-hole absent (watchdog
# can also flip this via dns-failover-on when pihole-FTL goes down).
import subprocess, shutil
pihole_present = shutil.which("pihole") is not None
db.set_setting("dns_port", "0" if pihole_present else "53")
db.set_setting("setup_complete", "1")
db.log_event("system", "Installed via install.sh")
db.close()
PYEOF
    chown -R "$SVC_USER:$SVC_USER" "$STATE"
    chmod 640 "$DB"
}

# --------------------------------------------------------------- services
enable_services() {
    say "Enabling services"
    systemctl enable sand-dashboard sand-netapply sand-recovery sand-watchdog.timer >/dev/null 2>&1 || true
    # Start the dashboard now so it can be used before cutover; do NOT start
    # sand-netapply — that is the cutover, and is left to `sand-apply`.
    systemctl restart sand-dashboard
}

finish() {
    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo -e "
${c_ok}================================================================${c_x}
  Roku-E8C3 installation complete — staged, networking untouched.

  The dashboard is running now at:
      http://${ip:-<this device IP>}

  Sign in with the dashboard password you just set.

  When you are ready to turn this device into a travel router:
      sudo sand-apply

  That cuts over into access-point mode (SSID \"Roku-E8C3\",
  http://10.0.0.1). It is protected by a timed auto-rollback, so a
  failed cutover cannot lock you out.
${c_ok}================================================================${c_x}"
}

main() {
    validate_env
    install_packages
    create_user
    install_files
    create_venv
    setup_dirs
    install_config
    install_helpers
    install_systemd
    prepare_host
    install_raspap
    install_pihole
    init_database
    enable_services
    finish
}

main "$@"
