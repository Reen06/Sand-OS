/* Roku-E8C3 — Logs page. Journal output + dashboard event log. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, escapeHtml, fmtRelative, setLoading, emptyState, toast } from "../ui.js";
import { icon } from "../icons.js";

const LEVEL_KIND = { error: "danger", warn: "warn", warning: "warn", info: "info", debug: "" };
const SOURCE_LABEL = {
  system: "System journal", dashboard: "Dashboard", hostapd: "Access point (hostapd)",
  dnsmasq: "DHCP (dnsmasq)", wifi: "Upstream WiFi", firewall: "Firewall",
  netapply: "Network apply", recovery: "Recovery", watchdog: "Watchdog",
  pihole: "Pi-hole", wireguard: "WireGuard",
};

function renderJournal(out, data) {
  clear(out);
  if (!data.available && !data.lines.length) {
    out.append(emptyState("logs", "No log output",
      data.error || "This service has not produced any log entries yet."));
    return;
  }
  out.append(el("pre", { class: "logview", text: data.lines.join("\n") }));
}

function renderEvents(out, events) {
  clear(out);
  if (!events.length) {
    out.append(emptyState("logs", "No events yet",
      "Dashboard actions and system events will appear here."));
    return;
  }
  const rows = events.map((e) => {
    const kind = LEVEL_KIND[e.level] || "";
    return el("tr", {}, [
      el("td", { class: "muted nowrap mono text-xs", text: fmtRelative(e.created_at) }),
      el("td", {}, [el("span", {
        class: kind ? `badge badge--${kind}` : "badge", text: e.level })]),
      el("td", { class: "muted text-sm", text: e.category }),
      el("td", { class: "text-sm", text: e.message + (e.detail ? `  (${e.detail})` : "") }),
    ]);
  });
  out.append(el("div", { class: "table-wrap" }, [
    el("table", { class: "table" }, [
      el("thead", {}, [el("tr", {}, [
        el("th", { text: "When" }), el("th", { text: "Level" }),
        el("th", { text: "Category" }), el("th", { text: "Message" }),
      ])]),
      el("tbody", {}, rows),
    ]),
  ]));
}

export async function render(view) {
  let sources = ["system"];
  try {
    const r = await api.get("/logs/sources");
    if (r && Array.isArray(r.sources)) sources = r.sources;
  } catch {}

  const sourceSel = el("select", { class: "select", style: "width:auto;min-height:36px" });
  sourceSel.append(el("option", { value: "events", text: "Dashboard events" }));
  for (const s of sources) {
    sourceSel.append(el("option", { value: "journal:" + s, text: SOURCE_LABEL[s] || s }));
  }

  const linesSel = el("select", { class: "select", style: "width:auto;min-height:36px" });
  for (const n of [200, 500, 1000]) {
    linesSel.append(el("option", { value: String(n), text: `${n} lines` }));
  }

  const refreshBtn = el("button", {
    class: "btn btn--sm", type: "button",
    html: icon("refresh", 16) + "<span>Refresh</span>", onclick: () => load(true),
  });

  const out = el("div");

  async function load(manual) {
    if (manual) setLoading(refreshBtn, true);
    const val = sourceSel.value;
    linesSel.hidden = val === "events";
    try {
      if (val === "events") {
        const d = await api.get("/logs/events?limit=250");
        renderEvents(out, d.events || []);
      } else {
        const src = encodeURIComponent(val.slice("journal:".length));
        const d = await api.get(`/logs?source=${src}&lines=${linesSel.value}`);
        renderJournal(out, d);
      }
    } catch (err) {
      clear(out).append(emptyState("alert", "Could not load logs",
        err.message || "Request failed."));
      if (manual) toast(err.message || "Failed to load logs", "error");
    } finally {
      if (manual) setLoading(refreshBtn, false);
    }
  }

  sourceSel.addEventListener("change", () => load(true));
  linesSel.addEventListener("change", () => load(true));

  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Logs" }),
        el("p", { text: "Service journals and a record of dashboard actions." }),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card__header" }, [
        sourceSel,
        el("div", { class: "row" }, [linesSel, refreshBtn]),
      ]),
      el("div", { class: "card__body card__body--flush", style: "padding:var(--s4)" }, [out]),
    ]),
  );

  poll(load, 9000);
}
