/* Roku-E8C3 — Settings page. Dashboard access, services, identity, power. */

import { api } from "../api.js";
import { el, clear, frag, toast, confirmDialog, setLoading } from "../ui.js";
import { icon } from "../icons.js";

function field(label, input, help) {
  return el("div", { class: "field" }, [
    el("label", { class: "label", text: label }), input,
    help ? el("p", { class: "help", text: help }) : null,
  ]);
}

function card(title, bodyChildren, headerExtra) {
  return el("div", { class: "card" }, [
    el("div", { class: "card__header" }, [
      el("span", { class: "card__title", text: title }),
      headerExtra || null,
    ]),
    el("div", { class: "card__body" }, bodyChildren),
  ]);
}

function accessCard() {
  const cur = el("input", { class: "input", type: "password", autocomplete: "current-password", required: true });
  const nw = el("input", { class: "input", type: "password", autocomplete: "new-password", required: true });
  const cf = el("input", { class: "input", type: "password", autocomplete: "new-password", required: true });
  const btn = el("button", { class: "btn btn--primary", type: "submit", text: "Update password" });
  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      if (nw.value !== cf.value) { toast("New passwords do not match", "error"); cf.focus(); return; }
      setLoading(btn, true);
      try {
        await api.post("/auth/change-password",
                       { current_password: cur.value, new_password: nw.value });
        toast("Dashboard password updated", "ok");
        form.reset();
      } catch (err) {
        toast(err.message || "Could not update password", "error");
      } finally { setLoading(btn, false); }
    },
  }, [
    field("Current password", cur),
    field("New password", nw, "At least 10 characters, mixing character types."),
    field("Confirm new password", cf),
    el("div", { style: "margin-top:var(--s4)" }, [btn]),
  ]);
  return card("Dashboard access", [form]);
}

function identityCard() {
  const body = el("div", { class: "row", style: "justify-content:center;padding:var(--s4)" },
                  [el("div", { class: "spinner" })]);
  const node = card("Identity", [body]);
  api.get("/system/settings").then((s) => {
    clear(body);
    body.className = "";
    body.append(
      el("dl", { class: "kv" }, [
        el("dt", { text: "Hostname" }), el("dd", { text: s.hostname || "—" }),
        el("dt", { text: "Access point" }), el("dd", { text: s.ap_ssid || "—" }),
        el("dt", { text: "Guest SSID" }), el("dd", { text: s.guest_ssid || "—" }),
        el("dt", { text: "Guest network" }),
        el("dd", { text: s.guest_enabled === "1" ? "enabled" : "disabled" }),
      ]),
      el("p", { class: "help mt-4",
        text: "SSID and hostname become editable once networking is configured." }),
    );
  }).catch(() => {
    clear(body);
    body.className = "";
    body.append(el("p", { class: "muted text-sm", text: "Could not load settings." }));
  });
  return node;
}

function serviceRow(svc, reload) {
  const kind = svc.active === "active" ? "ok"
             : svc.active === "failed" ? "danger" : "idle";
  const restartBtn = el("button", { class: "btn btn--sm", type: "button", text: "Restart" });
  restartBtn.addEventListener("click", async () => {
    setLoading(restartBtn, true);
    try {
      const r = await api.post(`/system/services/${encodeURIComponent(svc.name)}/restart`);
      toast(r.ok ? `Restarted ${svc.name}` : (r.message || "Restart failed"),
            r.ok ? "ok" : "error");
      setTimeout(reload, 900);
    } catch (err) {
      toast(err.message || "Restart failed", "error");
    } finally { setLoading(restartBtn, false); }
  });
  return el("div", { class: "spread", style: "padding:6px 0" }, [
    el("div", { class: "row" }, [
      el("span", { class: `dot dot--${kind}` }),
      el("span", { class: "mono text-sm truncate", text: svc.name }),
    ]),
    el("div", { class: "row" }, [
      el("span", { class: "muted text-xs", text: svc.active }), restartBtn,
    ]),
  ]);
}

function servicesCard() {
  const list = el("div", { class: "stack", style: "gap:2px" });
  const refresh = el("button", { class: "icon-btn", type: "button", "aria-label": "Refresh services" });
  refresh.append(frag(icon("refresh", 18)));
  const node = card("Services", [list], refresh);
  async function load() {
    clear(list).append(el("div", { class: "row", style: "justify-content:center;padding:var(--s4)" },
                           [el("div", { class: "spinner" })]));
    try {
      const d = await api.get("/system/services");
      clear(list);
      if (!d.available || !d.services.length) {
        list.append(el("p", { class: "muted text-sm",
          text: d.error || "Service status is available after install." }));
        return;
      }
      for (const svc of d.services) list.append(serviceRow(svc, load));
    } catch (err) {
      clear(list).append(el("p", { class: "muted text-sm", text: err.message }));
    }
  }
  refresh.addEventListener("click", load);
  load();
  return node;
}

function powerCard() {
  const reboot = el("button", { class: "btn", type: "button",
    html: icon("refresh", 16) + "<span>Reboot</span>" });
  const shutdown = el("button", { class: "btn btn--danger", type: "button",
    html: icon("power", 16) + "<span>Shut down</span>" });
  reboot.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Reboot device",
      message: "The network and dashboard will be unavailable for about a minute while the device restarts.",
      confirmLabel: "Reboot" }))) return;
    try { await api.post("/system/reboot"); toast("Reboot scheduled", "ok"); }
    catch (e) { toast(e.message || "Reboot failed", "error"); }
  });
  shutdown.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Shut down device",
      message: "The device will power off. You will need to unplug and replug it to start it again.",
      confirmLabel: "Shut down", danger: true }))) return;
    try { await api.post("/system/shutdown"); toast("Shutdown scheduled", "ok"); }
    catch (e) { toast(e.message || "Shutdown failed", "error"); }
  });
  return card("Power", [
    el("p", { class: "muted text-sm", style: "margin-bottom:var(--s4)",
      text: "Restart or power off the router. The access point drops while it restarts." }),
    el("div", { class: "row row--wrap" }, [reboot, shutdown]),
  ]);
}

export async function render(view) {
  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Settings" }),
        el("p", { text: "Dashboard access, services, identity, and power controls." }),
      ]),
    ]),
    el("div", { class: "grid",
      style: "grid-template-columns:repeat(auto-fill,minmax(320px,1fr));align-items:start" }, [
      accessCard(), servicesCard(), identityCard(), powerCard(),
    ]),
  );
}
