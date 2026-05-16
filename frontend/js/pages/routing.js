/* Roku-E8C3 — Routing page.
 * Per-device routing policy: direct, WireGuard tunnel, or blocked. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, toast, setLoading, emptyState } from "../ui.js";
import { icon } from "../icons.js";

/* ---------------------------------------------------------------- profile badge */
function profileBadge(profile, tunnelActive) {
  if (!profile || profile === "direct")
    return el("span", { class: "badge badge--info", text: "Direct" });
  if (profile === "blocked")
    return el("span", { class: "badge badge--danger", text: "Blocked" });
  const cls = tunnelActive === false ? "badge badge--warn" : "badge badge--vpn";
  return el("span", { class: cls, text: profile + (tunnelActive === false ? " ⚑ down" : "") });
}

/* ---------------------------------------------------------------- device row */
function buildRow(device, profiles) {
  const name = device.nickname || device.hostname || "Unknown device";
  const mac  = device.mac;

  const badgeCell = el("td", {}, [profileBadge(device.route_profile, device.tunnel_active)]);

  const sel = el("select", { class: "select" });
  for (const p of profiles) {
    const opt = el("option", {
      value: p.name,
      text: p.label + (p.kind === "wireguard" && p.active === false ? " (down)" : ""),
    });
    if (p.name === (device.route_profile || "direct")) opt.selected = true;
    sel.append(opt);
  }

  const applyBtn = el("button", { class: "btn btn--sm btn--primary", text: "Apply" });
  applyBtn.addEventListener("click", async () => {
    setLoading(applyBtn, true);
    try {
      await api.post("/routing/rules", { mac, profile: sel.value });
      clear(badgeCell).append(profileBadge(sel.value, null));
      toast(`${name} → ${sel.value}`, "ok");
    } catch (err) {
      toast(err.message || "Failed to update route", "error");
    } finally {
      setLoading(applyBtn, false);
    }
  });

  return el("tr", {}, [
    el("td", {}, [
      el("div", { class: "fw-600 truncate", text: name }),
      el("div", { class: "mono muted text-xs", text: mac }),
    ]),
    el("td", { class: "mono text-sm", text: device.ip || "—" }),
    badgeCell,
    el("td", {}, [
      el("div", { class: "row" }, [sel, applyBtn]),
    ]),
  ]);
}

/* ================================================================ main render */
export async function render(view) {
  const rebuildBtn = el("button", { class: "btn" }, [
    frag(icon("refresh", 14)),
    document.createTextNode(" Rebuild firewall"),
  ]);

  const tableWrap = el("div", { class: "table-wrap" });
  const card = el("div", { class: "card" }, [
    el("div", { class: "card__header" }, [
      frag(icon("route", 16)),
      el("span", { class: "card__title", text: "Device Routing Rules" }),
      el("span", { class: "grow" }),
      rebuildBtn,
    ]),
    el("div", { class: "card__body--flush" }, [tableWrap]),
  ]);

  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Routing" }),
        el("p", { text: "Choose how each device reaches the internet — direct, a WireGuard tunnel, or blocked." }),
      ]),
    ]),
    card,
  );

  rebuildBtn.addEventListener("click", async () => {
    setLoading(rebuildBtn, true);
    try {
      await api.post("/routing/rebuild", {});
      toast("Firewall rules rebuilt", "ok");
    } catch (err) {
      toast(err.message || "Rebuild failed", "error");
    } finally {
      setLoading(rebuildBtn, false);
    }
  });

  /* ---------- data ---------- */

  let _profiles = [];

  async function loadProfiles() {
    try {
      const data = await api.get("/routing/profiles");
      _profiles = data.profiles || [];
    } catch {}
  }

  function renderTable(devices) {
    clear(tableWrap);
    if (!devices.length) {
      tableWrap.append(
        el("div", { class: "card__body" }, [
          emptyState("route", "No devices yet",
            "Devices appear here once they connect to the Roku-E8C3 network via DHCP."),
        ])
      );
      return;
    }
    const tbody = el("tbody");
    for (const d of devices) tbody.append(buildRow(d, _profiles));
    tableWrap.append(
      el("table", { class: "table" }, [
        el("thead", {}, [
          el("tr", {}, [
            el("th", { text: "Device" }),
            el("th", { text: "IP" }),
            el("th", { text: "Current route" }),
            el("th", { text: "Change" }),
          ]),
        ]),
        tbody,
      ])
    );
  }

  async function refresh() {
    try {
      const data = await api.get("/routing/rules");
      renderTable(data.devices || []);
    } catch {}
  }

  await loadProfiles();
  await refresh();

  const stopPoll = poll(refresh, 15_000);
  view.addEventListener("destroy", stopPoll);
}
