/* Roku-E8C3 — Overview page. Live system + connectivity summary. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, fmtDuration, fmtBytes, setLoading } from "../ui.js";
import { icon } from "../icons.js";

const STATUS = {
  online:       { kind: "ok",      label: "Online" },
  connected:    { kind: "ok",      label: "Connected" },
  active:       { kind: "ok",      label: "Active" },
  offline:      { kind: "danger",  label: "Offline" },
  down:         { kind: "danger",  label: "Not running" },
  error:        { kind: "danger",  label: "Error" },
  disconnected: { kind: "neutral", label: "Disconnected" },
  disabled:     { kind: "warn",    label: "Disabled" },
  portal:       { kind: "warn",    label: "Captive portal" },
  connecting:   { kind: "warn",    label: "Connecting" },
  unknown:      { kind: "neutral", label: "Not configured" },
};
const meta = (s) => STATUS[s] || STATUS.unknown;

function statusCard(iconName, title) {
  const badge = el("span", { class: "badge" });
  const detail = el("div", { class: "muted text-sm", style: "margin-top:var(--s2)" });
  const node = el("div", { class: "card" }, [
    el("div", { class: "card__body" }, [
      el("div", { class: "stat__label", html: icon(iconName, 15) + `<span>${title}</span>` }),
      el("div", { style: "margin-top:var(--s3)" }, [badge]),
      detail,
    ]),
  ]);
  return {
    node,
    update(status, detailText) {
      const m = meta(status);
      badge.className = m.kind === "neutral" ? "badge" : `badge badge--${m.kind}`;
      clear(badge).append(
        el("span", { class: `dot dot--${m.kind === "neutral" ? "idle" : m.kind}` }),
        document.createTextNode(" " + m.label));
      detail.textContent = detailText || "—";
    },
  };
}

function statTile(iconName, label) {
  const value = el("div", { class: "stat__value", text: "—" });
  const metaEl = el("div", { class: "stat__meta" });
  const fill = el("div", { class: "meter__fill" });
  const meter = el("div", { class: "meter", hidden: true }, [fill]);
  const node = el("div", { class: "stat" }, [
    el("div", { class: "stat__label", html: icon(iconName, 15) + `<span>${label}</span>` }),
    value, metaEl, meter,
  ]);
  return {
    node,
    set(html, metaText, pct) {
      value.innerHTML = html;
      metaEl.textContent = metaText || "";
      if (pct == null) { meter.hidden = true; return; }
      meter.hidden = false;
      fill.style.width = Math.min(100, Math.max(0, pct)) + "%";
      fill.className = "meter__fill" + (pct > 90 ? " is-danger" : pct > 75 ? " is-warn" : "");
    },
  };
}

export async function render(view) {
  const cards = {
    internet: statusCard("globe", "Internet"),
    upstream: statusCard("wifi", "Upstream WiFi"),
    vpn: statusCard("shield", "VPN"),
    pihole: statusCard("ban", "Pi-hole DNS"),
  };
  const tiles = {
    devices: statTile("devices", "Connected devices"),
    uptime: statTile("clock", "Uptime"),
    temp: statTile("thermometer", "CPU temperature"),
    load: statTile("cpu", "CPU load"),
    memory: statTile("database", "Memory"),
    storage: statTile("database", "Storage"),
    battery: statTile("battery", "Battery (PiSugar3)"),
  };

  const warning = el("div", { hidden: true });
  const refreshBtn = el("button", {
    class: "btn btn--sm", type: "button",
    html: icon("refresh", 16) + "<span>Refresh</span>",
    onclick: () => load(true),
  });

  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Overview" }),
        el("p", { text: "Live status of your travel router and its connections." }),
      ]),
      el("div", { class: "page-head__actions" }, [refreshBtn]),
    ]),
    warning,
    el("div", { class: "section-title", text: "Connectivity" }),
    el("div", { class: "grid grid--cards" },
       Object.values(cards).map((c) => c.node)),
    el("div", { class: "section-title mt-6", text: "System" }),
    el("div", { class: "grid grid--stats" },
       Object.values(tiles).map((t) => t.node)),
    el("div", { class: "section-title mt-6", text: "Hardware tools" }),
    el("div", { class: "grid grid--cards" }, [
      el("div", { class: "card" }, [
        el("div", { class: "card__body" }, [
          el("div", { class: "row", style: "margin-bottom:var(--s3)" }, [
            frag(icon("battery", 16)),
            el("span", { class: "fw-600", text: "PiSugar3 Battery" }),
          ]),
          el("p", { class: "muted text-sm",
            text: "Battery management, RTC clock, scheduled wake/shutdown." }),
          el("div", { style: "margin-top:var(--s4)" }, [
            el("a", {
              class: "btn btn--sm btn--primary",
              href: `http://${location.hostname}:8421`,
              target: "_blank",
              rel: "noopener",
              text: "Open PiSugar dashboard →",
            }),
          ]),
        ]),
      ]),
    ]),
  );

  async function load(manual) {
    if (manual) setLoading(refreshBtn, true);
    try {
      const d = await api.get("/overview");
      cards.internet.update(d.internet.status,
        d.internet.status === "unknown" ? "Connect to an upstream network" : null);
      cards.upstream.update(d.upstream.status,
        d.upstream.ssid || (d.upstream.status === "unknown" ? "No network selected" : null));
      cards.vpn.update(d.vpn.status,
        d.vpn.profile || (d.vpn.status === "unknown" ? "No VPN profile active" : null));
      cards.pihole.update(d.pihole.status,
        d.pihole.blocked_today != null
          ? `${d.pihole.blocked_today} queries blocked today` : "Ad &amp; tracker filtering");

      const s = d.system;
      tiles.devices.set(String(d.devices.count), "currently on the network");
      tiles.uptime.set(fmtDuration(s.uptime_seconds), `since last boot`);
      tiles.temp.set(s.cpu_temp_c != null ? `${s.cpu_temp_c}<small> °C</small>` : "—",
        s.cpu_temp_c != null && s.cpu_temp_c > 75 ? "running warm" : "nominal");
      tiles.load.set(String(s.load["1m"]),
        `${s.load["5m"]} / ${s.load["15m"]} · ${s.cpu_count} cores`,
        (s.load["1m"] / s.cpu_count) * 100);
      tiles.memory.set(`${s.memory.used_mb}<small> / ${s.memory.total_mb} MB</small>`,
        `${s.memory.percent}% used`, s.memory.percent);
      tiles.storage.set(`${s.storage.used_gb}<small> / ${s.storage.total_gb} GB</small>`,
        `${s.storage.percent}% used`, s.storage.percent);
      const b = d.battery;
      if (b && b.percent != null) {
        tiles.battery.set(`${b.percent}<small>%</small>`, `${b.volts} V`, b.percent);
      } else {
        tiles.battery.set("—", "Not detected");
      }

      if (s.throttled) {
        warning.hidden = false;
        clear(warning).append(frag(
          '<div class="callout callout--warn"><span data-icon="alert"></span>' +
          "<div>The Pi has reported power throttling or under-voltage. " +
          "Use a stronger power supply for reliable operation.</div></div>"));
      } else {
        warning.hidden = true;
      }
    } catch (err) {
      if (manual) {
        const { toast } = await import("../ui.js");
        toast(err.message || "Failed to refresh", "error");
      }
    } finally {
      if (manual) setLoading(refreshBtn, false);
    }
  }

  poll(load, 6000);
}
