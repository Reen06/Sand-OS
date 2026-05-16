/* Roku-E8C3 — WiFi page.
 * Upstream network scanning, joining, saved networks and captive portal. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, modal, confirmDialog, toast, setLoading, emptyState } from "../ui.js";
import { icon } from "../icons.js";

/* ---------------------------------------------------------------- signal bars */
function signalBars(bars) {
  const heights = [5, 9, 13, 18];
  const color = bars >= 3 ? "var(--ok)" : bars >= 2 ? "var(--warn)" : "var(--danger)";
  const rects = heights.map((h, i) => {
    const filled = i < bars;
    const y = 20 - h;
    return `<rect x="${i * 6}" y="${y}" width="4" height="${h}" rx="1" ` +
      `fill="${filled ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.2"/>`;
  }).join("");
  return `<svg viewBox="0 0 26 22" width="18" height="16" aria-hidden="true" style="color:${color}">${rects}</svg>`;
}

/* ---------------------------------------------------------------- status card */
function buildStatusCard() {
  const iface      = el("span", { class: "mono muted text-sm" });
  const ssidEl     = el("span", { class: "fw-600" });
  const ipEl       = el("span", { class: "muted text-sm" });
  const macEl      = el("span", { class: "mono muted text-sm" });
  const disconnBtn = el("button", { class: "btn btn--sm btn--danger", text: "Disconnect" });
  const randBtn    = el("button", { class: "btn btn--sm" }, [
    frag(icon("refresh", 14)),
    document.createTextNode(" Randomize MAC"),
  ]);

  const card = el("div", { class: "card" }, [
    el("div", { class: "card__body" }, [
      el("div", { class: "row", style: "margin-bottom:var(--s3)" }, [
        frag(icon("wifi", 16)),
        el("span", { class: "fw-600", text: "Upstream Connection" }),
        el("span", { class: "grow" }),
        iface,
      ]),
      el("div", { class: "row" }, [ssidEl, ipEl]),
      el("div", { class: "row", style: "margin-top:var(--s2)" }, [
        el("span", { class: "muted text-sm", text: "MAC " }), macEl,
      ]),
      el("div", { class: "row", style: "margin-top:var(--s4)" }, [disconnBtn, randBtn]),
    ]),
  ]);

  let _onDisc = null, _onRand = null;
  disconnBtn.addEventListener("click", () => _onDisc && _onDisc());
  randBtn.addEventListener("click", () => _onRand && _onRand());

  return {
    card,
    update(data, onDisc, onRand) {
      _onDisc = onDisc; _onRand = onRand;
      const up = data.upstream || {};
      const connected = up.status === "connected";
      ssidEl.textContent = up.ssid || (connected ? "Connected" : "Not connected");
      ipEl.textContent = up.ip ? ` · ${up.ip}` : "";
      macEl.textContent = data.mac || "—";
      iface.textContent = data.interface || "—";
      disconnBtn.disabled = !connected;
      randBtn.disabled = !data.interface;
    },
  };
}

/* ---------------------------------------------------------------- portal banner */
function buildPortalBanner() {
  let _url = null;
  const openBtn = el("button", { class: "btn btn--sm btn--warn", text: "Open portal page" });
  openBtn.addEventListener("click", () => _url && window.open(_url, "_blank"));

  const banner = el("div", { class: "callout callout--warn", style: "display:none" }, [
    frag(icon("alert", 16)),
    el("div", { class: "grow" }, [
      el("div", { class: "fw-600", text: "Captive portal detected" }),
      el("div", { class: "text-sm",
        text: "This network requires a sign-in before granting internet access." }),
    ]),
    openBtn,
  ]);

  return {
    banner,
    update(portal) {
      const show = portal && portal.status === "portal";
      banner.style.display = show ? "" : "none";
      _url = (portal && portal.url) || null;
      openBtn.style.display = _url ? "" : "none";
    },
  };
}

/* ---------------------------------------------------------------- connect modal */
function showConnectModal(network, onConnect) {
  const { ssid, open, security } = network;

  const pwField = el("input", {
    class: "input", type: "password", placeholder: "Password",
    style: open ? "display:none" : "",
  });
  const showToggle = el("button", { class: "icon-btn", type: "button", title: "Show/hide password" });
  showToggle.append(frag(icon("eye", 16)));
  showToggle.addEventListener("click", () => {
    const hidden = pwField.type === "password";
    pwField.type = hidden ? "text" : "password";
    clear(showToggle).append(frag(icon(hidden ? "eyeOff" : "eye", 16)));
  });

  const errMsg = el("p", { class: "text-sm", style: "color:var(--danger);display:none" });
  const connectBtn = el("button", { class: "btn btn--primary", type: "button", text: "Connect" });
  const cancelBtn  = el("button", { class: "btn", type: "button", text: "Cancel" });

  const body = el("div", { class: "stack" }, [
    el("div", [
      el("div", { class: "muted text-sm", text: "Network" }),
      el("div", { class: "fw-600", text: ssid }),
      el("div", { class: "muted text-sm", text: security }),
    ]),
    open ? null : el("div", [
      el("label", { class: "label", text: "Password" }),
      el("div", { style: "position:relative" }, [
        pwField,
        el("span", { style: "position:absolute;right:var(--s3);top:50%;transform:translateY(-50%)" },
          [showToggle]),
      ]),
    ]),
    errMsg,
  ]);

  const m = modal({ title: `Join “${ssid}”`, body, footer: [cancelBtn, connectBtn] });
  cancelBtn.addEventListener("click", () => m.close());

  connectBtn.addEventListener("click", async () => {
    const pw = pwField.value;
    if (!open && pw.length < 8) {
      errMsg.textContent = "Password must be at least 8 characters.";
      errMsg.style.display = "";
      pwField.focus();
      return;
    }
    errMsg.style.display = "none";
    setLoading(connectBtn, true);
    try {
      await onConnect(ssid, open ? null : pw);
      m.close();
    } catch (err) {
      errMsg.textContent = err.message || "Connection failed.";
      errMsg.style.display = "";
      setLoading(connectBtn, false);
    }
  });

  if (!open) setTimeout(() => pwField.focus(), 60);
}

/* ---------------------------------------------------------------- network list */
function buildNetworkList() {
  const scanBtn = el("button", { class: "btn btn--sm" }, [
    frag(icon("refresh", 14)),
    document.createTextNode(" Scan"),
  ]);
  const list = el("div", { class: "stack" });
  const card = el("div", { class: "card" }, [
    el("div", { class: "card__body" }, [
      el("div", { class: "row", style: "margin-bottom:var(--s4)" }, [
        frag(icon("search", 16)),
        el("span", { class: "fw-600", text: "Available Networks" }),
        el("span", { class: "grow" }),
        scanBtn,
      ]),
      list,
    ]),
  ]);

  let _onConnect = null;
  let _scanning = false;

  scanBtn.addEventListener("click", () => { if (!_scanning) _scan(); });

  async function _scan() {
    if (_scanning) return;
    _scanning = true;
    setLoading(scanBtn, true);
    clear(list).append(
      el("div", { class: "row", style: "justify-content:center;padding:var(--s8)" }, [
        el("div", { class: "spinner" }),
      ])
    );
    try {
      const data = await api.get("/wifi/scan");
      _render(data.networks || []);
    } catch (err) {
      clear(list).append(err.notReady
        ? emptyState("wifi", "No upstream interface",
            "Plug in the USB WiFi adapter and run roku-apply to enable upstream scanning.")
        : el("p", { class: "muted text-sm", text: err.message || "Scan failed." }));
    } finally {
      _scanning = false;
      setLoading(scanBtn, false);
    }
  }

  function _render(networks) {
    clear(list);
    if (!networks.length) {
      list.append(emptyState("wifi", "No networks found",
        "Move closer to a router or press Scan again."));
      return;
    }
    for (const n of networks) {
      const lockSvg = n.open ? "" : icon("lock", 13);
      const joinBtn = el("button", { class: "btn btn--sm btn--primary", text: "Join" });
      joinBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (_onConnect) showConnectModal(n, _onConnect);
      });
      const row = el("div", {
        class: "row",
        style: "padding:var(--s3) 0;border-bottom:1px solid var(--border);cursor:pointer",
      }, [
        el("span", { html: signalBars(n.bars) }),
        el("div", { class: "grow" }, [
          el("div", { class: "row" }, [
            el("span", { class: "fw-600", text: n.ssid }),
            lockSvg ? frag(lockSvg) : null,
            n.saved ? el("span", { class: "badge", text: "saved" }) : null,
          ]),
          el("div", { class: "muted text-sm",
            text: `${n.security}  ·  Ch ${n.channel}  ·  ${n.signal}%` }),
        ]),
        joinBtn,
      ]);
      row.addEventListener("click", () => { if (_onConnect) showConnectModal(n, _onConnect); });
      list.append(row);
    }
  }

  return { card, setConnectHandler(fn) { _onConnect = fn; }, scan: _scan };
}

/* ---------------------------------------------------------------- saved networks */
function buildSavedCard() {
  const list = el("div", { class: "stack" });
  const card = el("div", { class: "card" }, [
    el("div", { class: "card__body" }, [
      el("div", { class: "row", style: "margin-bottom:var(--s4)" }, [
        frag(icon("database", 16)),
        el("span", { class: "fw-600", text: "Saved Networks" }),
      ]),
      list,
    ]),
  ]);

  let _onForget = null;

  return {
    card,
    setForgetHandler(fn) { _onForget = fn; },
    render(connections) {
      clear(list);
      if (!connections.length) {
        list.append(el("p", { class: "muted text-sm", text: "No saved networks." }));
        return;
      }
      for (const c of connections) {
        const btn = el("button", {
          class: "icon-btn",
          title: "Forget",
          style: "color:var(--danger)",
        });
        btn.append(frag(icon("trash", 16)));
        btn.addEventListener("click", () => _onForget && _onForget(c));
        list.append(el("div", {
          class: "row",
          style: "padding:var(--s3) 0;border-bottom:1px solid var(--border)",
        }, [
          frag(icon("lock", 14)),
          el("span", { class: "grow", text: c.name }),
          btn,
        ]));
      }
    },
  };
}

/* ================================================================ main render */
export async function render(view) {
  const stack = el("div", { class: "stack" });
  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "WiFi" }),
        el("p", { text: "Connect the router upstream to a public or home WiFi network." }),
      ]),
    ]),
    stack,
  );

  const statusCard = buildStatusCard();
  const portalBanner = buildPortalBanner();
  const netList = buildNetworkList();
  const savedCard = buildSavedCard();

  stack.append(statusCard.card, portalBanner.banner, netList.card, savedCard.card);

  /* ---------- actions ---------- */

  async function doDisconnect() {
    if (!await confirmDialog({
      title: "Disconnect upstream?",
      message: "The router will lose its internet connection until you join another network.",
      confirmLabel: "Disconnect", danger: true,
    })) return;
    try {
      await api.post("/wifi/disconnect", {});
      toast("Disconnected from upstream network", "ok");
      await refreshStatus();
    } catch (err) {
      toast(err.message || "Disconnect failed", "error");
    }
  }

  async function doConnect(ssid, password) {
    await api.post("/wifi/connect", { ssid, password });
    toast(`Joining “${ssid}”…`, "info");
    setTimeout(refreshStatus, 3500);
  }

  async function doForget(conn) {
    if (!await confirmDialog({
      title: `Forget “${conn.name}”?`,
      message: "The saved password will be removed. You can rejoin later.",
      confirmLabel: "Forget", danger: true,
    })) return;
    try {
      await api.del(`/wifi/saved/${conn.uuid}`);
      toast(`Forgot “${conn.name}”`, "ok");
      await refreshSaved();
    } catch (err) {
      toast(err.message || "Could not forget network", "error");
    }
  }

  async function doRandMac() {
    if (!await confirmDialog({
      title: "Randomize MAC address?",
      message: "The upstream interface MAC will change. You may need to reconnect to your network.",
      confirmLabel: "Randomize",
    })) return;
    try {
      const res = await api.post("/wifi/mac/randomize", {});
      toast(`MAC set to ${res.mac}`, "ok");
      await refreshStatus();
    } catch (err) {
      toast(err.message || "MAC randomization failed", "error");
    }
  }

  netList.setConnectHandler(doConnect);
  savedCard.setForgetHandler(doForget);

  /* ---------- data ---------- */

  async function refreshStatus() {
    try {
      const data = await api.get("/wifi/status");
      statusCard.update(data, doDisconnect, doRandMac);
      portalBanner.update(data.portal);
    } catch {}
  }

  async function refreshSaved() {
    try {
      const data = await api.get("/wifi/saved");
      savedCard.render(data.connections || []);
    } catch {}
  }

  await Promise.all([refreshStatus(), refreshSaved()]);
  netList.scan();

  const stopPoll = poll(refreshStatus, 15_000);
  view.addEventListener("destroy", stopPoll);
}
