/* Roku-E8C3 — Devices page.
 * Lists known clients with per-device routing badges.
 * Includes a default policy control for new devices. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, emptyState, fmtRelative, toast } from "../ui.js";
import { icon } from "../icons.js";

const POLICIES = [
  { value: "direct",  label: "Direct",  desc: "New devices connect through normally with no VPN.",  cls: "badge--info" },
  { value: "blocked", label: "Blocked", desc: "New devices are blocked until you approve them.", cls: "badge--danger" },
];

function routeBadge(profile) {
  if (!profile || profile === "direct")
    return el("span", { class: "badge badge--info", text: "Direct" });
  if (profile === "blocked")
    return el("span", { class: "badge badge--danger", text: "Blocked" });
  return el("span", { class: "badge badge--vpn", text: profile });
}

function connectedDot(connected) {
  const color = connected ? "var(--ok)" : "var(--text-faint)";
  return el("span", {
    title: connected ? "Connected" : "Offline",
    style: `display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0`,
  });
}

/* ---------------------------------------------------------------- policy card */
function buildPolicyCard() {
  const desc    = el("p", { class: "muted text-sm", style: "margin:var(--s2) 0 var(--s4)" });
  const btnArea = el("div", { class: "row", style: "gap:var(--s2);flex-wrap:wrap" });

  let _current = "direct";
  let _onChange = null;

  function _render(policy) {
    _current = policy;
    const p = POLICIES.find((p) => p.value === policy) || POLICIES[0];
    desc.textContent = p.desc;
    clear(btnArea);
    for (const opt of POLICIES) {
      const active = opt.value === policy;
      const btn = el("button", {
        class: "btn btn--sm" + (active ? " btn--primary" : ""),
        text: opt.label,
        disabled: active,
      });
      if (!active) {
        btn.addEventListener("click", () => _onChange && _onChange(opt.value));
      }
      btnArea.append(btn);
    }
  }

  const card = el("div", { class: "card" }, [
    el("div", { class: "card__body" }, [
      el("div", { class: "row", style: "margin-bottom:var(--s1)" }, [
        frag(icon("shield", 16)),
        el("span", { class: "fw-600", text: "New Device Default" }),
      ]),
      desc,
      btnArea,
    ]),
  ]);

  return {
    card,
    render: _render,
    setChangeHandler(fn) { _onChange = fn; },
  };
}

/* ---------------------------------------------------------------- device table */
function renderTable(body, devices) {
  if (!devices.length) {
    clear(body).append(emptyState("devices", "No devices yet",
      "Connect a phone or laptop to the Roku-E8C3 network and it will appear here."));
    return;
  }
  const rows = devices.map((d) => el("tr", { class: d.connected ? "" : "is-offline" }, [
    el("td", {}, [
      el("div", { class: "row", style: "gap:var(--s2)" }, [
        connectedDot(d.connected),
        el("span", { text: d.nickname || d.hostname || "Unknown device" }),
      ]),
      el("div", { class: "muted text-xs", text: d.device_type || "" }),
    ]),
    el("td", { class: "mono text-sm", text: d.ip || "—" }),
    el("td", { class: "mono text-xs muted", text: d.mac }),
    el("td", {}, [routeBadge(d.route_profile)]),
    el("td", { class: "muted text-sm nowrap", text: d.connected ? "now" : fmtRelative(d.last_seen) }),
  ]));
  clear(body).append(el("div", { class: "table-wrap" }, [
    el("table", { class: "table" }, [
      el("thead", {}, [el("tr", {}, ["Device", "IP", "MAC", "Route", "Last seen"]
        .map((h) => el("th", { text: h })))]),
      el("tbody", {}, rows),
    ]),
  ]));
}

export async function render(view) {
  const policyCard = buildPolicyCard();
  const body = el("div");

  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Devices" }),
        el("p", { text: "Every device that has joined your network." }),
      ]),
    ]),
    policyCard.card,
    el("div", { class: "card", style: "margin-top:var(--s4)" }, [
      el("div", { class: "card__body card__body--flush" }, [body]),
    ]),
  );

  clear(body).append(el("div", { class: "row", style: "justify-content:center;padding:var(--s8)" },
                         [el("div", { class: "spinner" })]));

  /* ---- default policy ---- */

  async function loadPolicy() {
    try {
      const d = await api.get("/devices/policy");
      policyCard.render(d.policy || "direct");
    } catch {}
  }

  policyCard.setChangeHandler(async (newPolicy) => {
    try {
      await api.patch("/devices/policy", { policy: newPolicy });
      policyCard.render(newPolicy);
      const label = POLICIES.find((p) => p.value === newPolicy)?.label ?? newPolicy;
      toast(`New devices will now be: ${label}`, "ok");
    } catch (err) {
      toast(err.message || "Failed to update policy", "error");
    }
  });

  /* ---- device list ---- */

  async function load() {
    try {
      const d = await api.get("/devices");
      renderTable(body, d.devices || []);
    } catch (err) {
      clear(body).append(emptyState("devices",
        err.notReady ? "Devices appear once networking is live" : "Could not load devices",
        err.notReady
          ? "When the access point is broadcasting and a device connects, it is listed here."
          : (err.message || "Request failed.")));
    }
  }

  await Promise.all([loadPolicy(), load()]);
  poll(load, 10_000);
}
