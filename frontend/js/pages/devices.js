/* Roku-E8C3 — Devices page.
 * Lists known clients. Renaming, routing and blocking are wired in with the
 * per-device routing module; until then the table is read-only. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, emptyState, fmtRelative } from "../ui.js";

function routeBadge(profile) {
  if (!profile || profile === "direct")
    return el("span", { class: "badge badge--info", text: "Direct" });
  if (profile === "blocked")
    return el("span", { class: "badge badge--danger", text: "Blocked" });
  return el("span", { class: "badge badge--vpn", text: profile });
}

function renderTable(body, devices) {
  if (!devices.length) {
    clear(body).append(emptyState("devices", "No devices yet",
      "Connect a phone or laptop to the Roku-E8C3 network and it will appear here."));
    return;
  }
  const rows = devices.map((d) => el("tr", {}, [
    el("td", {}, [
      el("div", { text: d.nickname || d.hostname || "Unknown device" }),
      el("div", { class: "muted text-xs", text: d.device_type || "" }),
    ]),
    el("td", { class: "mono text-sm", text: d.ip || "—" }),
    el("td", { class: "mono text-xs muted", text: d.mac }),
    el("td", {}, [routeBadge(d.route_profile)]),
    el("td", { class: "muted text-sm nowrap", text: fmtRelative(d.last_seen) }),
  ]));
  clear(body).append(el("div", { class: "table-wrap" }, [
    el("table", { class: "table" }, [
      el("thead", {}, [el("tr", {}, ["Device", "IP address", "MAC", "Route", "Last seen"]
        .map((h) => el("th", { text: h })))]),
      el("tbody", {}, rows),
    ]),
  ]));
}

export async function render(view) {
  const body = el("div");
  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Devices" }),
        el("p", { text: "Every device that has joined your network." }),
      ]),
    ]),
    el("div", { class: "card" }, [el("div", { class: "card__body card__body--flush" }, [body])]),
  );
  clear(body).append(el("div", { class: "row", style: "justify-content:center;padding:var(--s8)" },
                         [el("div", { class: "spinner" })]));

  async function load() {
    try {
      const d = await api.get("/devices");
      renderTable(body, d.devices || []);
    } catch (err) {
      clear(body).append(emptyState("devices",
        err.notReady ? "Devices appear once networking is live" : "Could not load devices",
        err.notReady
          ? "When the access point is broadcasting and a device connects, it is listed here with its address and routing profile."
          : (err.message || "Request failed.")));
    }
  }
  poll(load, 10000);
}
