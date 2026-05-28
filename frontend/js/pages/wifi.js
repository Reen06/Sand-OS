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
    document.createTextNode(" Randomize MAC"),
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
        el("span", { class: "muted text-sm", text: "MAC " }), macEl,
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
      ipEl.textContent = up.ip ? ` · ${up.ip}` : "";
      macEl.textContent = data.mac || "—";
      iface.textContent = data.interface || "—";
      disconnBtn.disabled = !connected;
      randBtn.disabled = !data.interface;
    },
  };
}

/* ---------------------------------------------------------------- portal banner */
function buildPortalBanner(onRecheck) {
  let _url = null;
  let _autoTried = false;
  let _visible = false;

  const autoBtn  = el("button", { class: "btn btn--sm btn--primary", text: "Auto-connect" });
  const openBtn  = el("button", { class: "btn btn--sm btn--warn", text: "Open sign-in page" });
  const checkBtn = el("button", { class: "btn btn--sm", text: "Re-check connection" });
  const desc     = el("div", { class: "text-sm muted" });

  async function _tryAuto() {
    if (!_url) return;
    autoBtn.disabled = true;
    autoBtn.textContent = "Trying…";
    desc.textContent = "Attempting automatic sign-in…";
    try {
      const res = await api.post("/wifi/portal/touch", { url: _url });
      if (res.online) {
        banner.style.display = "none";
        _visible = false;
        toast("Connected — captive portal accepted", "ok");
        onRecheck();
        return;
      }
      if (res.url) _url = res.url;
      desc.textContent =
        "Auto-connect didn’t work — tap “Open sign-in page” to sign in manually, " +
        "then tap “Re-check connection” when done.";
    } catch {
      desc.textContent = "Auto-connect failed. Try opening the sign-in page manually.";
    }
    autoBtn.textContent = "Retry auto-connect";
    autoBtn.disabled = false;
  }

  autoBtn.addEventListener("click", _tryAuto);

  openBtn.addEventListener("click", () => {
    const target = _url || "http://neverssl.com";
    window.open(target, "_blank");
    desc.textContent =
      "Sign-in page opened — complete sign-in there, then tap “Re-check connection”.";
    autoBtn.textContent = "Retry auto-connect";
    autoBtn.disabled = false;
    setTimeout(onRecheck, 8000);
  });

  checkBtn.addEventListener("click", async () => {
    checkBtn.disabled = true;
    checkBtn.textContent = "Checking…";
    try {
      const portal = await api.get("/wifi/portal");
      if (portal.status === "online") {
        banner.style.display = "none";
        _visible = false;
        toast("Internet connection verified ✓", "ok");
      } else {
        _applyPortal(portal);
        toast("Still behind a portal — sign in to continue", "warn");
      }
    } catch {
      toast("Could not reach connection check", "error");
    }
    checkBtn.disabled = false;
    checkBtn.textContent = "Re-check connection";
  });

  const banner = el("div", { class: "callout callout--warn", style: "display:none" }, [
    frag(icon("globe", 16)),
    el("div", { class: "grow" }, [
      el("div", { class: "fw-600", text: "Sign-in may be required" }),
      desc,
      el("div", { class: "row", style: "flex-wrap:wrap;gap:var(--s2);margin-top:var(--s3)" },
        [autoBtn, openBtn, checkBtn]),
    ]),
  ]);

  function _applyPortal(portal) {
    _url = (portal && portal.url) || _url || "http://neverssl.com";
    autoBtn.textContent = "Auto-connect";
    autoBtn.disabled = false;
    if (portal && portal.status === "portal") {
      desc.textContent =
        "This network requires you to sign in before internet access is granted. " +
        "Tap “Auto-connect” to try automatic sign-in, or “Open sign-in page” to do it manually.";
    } else {
      desc.textContent =
        "This network may have a sign-in page. If browsing isn’t working, " +
        "tap “Open sign-in page” to accept terms, then “Re-check connection”.";
    }
  }

  return {
    banner,
    // Call this right after joining a network to show the verification UI immediately.
    showUnverified() {
      _visible = true;
      _autoTried = false;
      _url = null;
      desc.textContent =
        "Verifying internet connection… If this network requires a sign-in, " +
        "use “Open sign-in page” then “Re-check connection”.";
      autoBtn.textContent = "Auto-connect";
      autoBtn.disabled = false;
      banner.style.display = "";
    },
    // Call this with the result of GET /wifi/portal.
    updateFromCheck(portal) {
      if (!portal) return;
      if (portal.status === "online") {
        banner.style.display = "none";
        _visible = false;
        return;
      }
      _visible = true;
      banner.style.display = "";
      _applyPortal(portal);
      if (!_autoTried && portal.status === "portal") {
        _autoTried = true;
        _tryAuto();
      }
    },
    hide() {
      banner.style.display = "none";
      _visible = false;
      _autoTried = false;
    },
    reset() { _autoTried = false; },
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

  const m = modal({ title: `Join "${ssid}"`, body, footer: [cancelBtn, connectBtn] });
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
    document.createTextNode(" Scan"),
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

  scanBtn.addEventListener("click", () => { if (!_scanning) _scan(true); });

  async function _scan(force = false) {
    if (_scanning) return;
    _scanning = true;
    setLoading(scanBtn, true);
    if (force) {
      // Show spinner only for the slow forced rescan.
      clear(list).append(
        el("div", { class: "row", style: "justify-content:center;padding:var(--s8)" }, [
          el("div", { class: "spinner" }),
        ])
      );
    }
    try {
      const data = await api.get(force ? "/wifi/scan?force=true" : "/wifi/scan");
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
        "Press Scan to search for networks, or move closer to a router."));
      return;
    }
    for (const n of networks) {
      const lockSvg = n.open ? "" : icon("lock", 13);
      const joinBtn = el("button", { class: "btn btn--sm btn--primary", text: "Join" });
      const _handleJoin = () => {
        if (!_onConnect) return;
        if (n.saved && !n.open) {
          _onConnect(n.ssid, null);
        } else {
          showConnectModal(n, _onConnect);
        }
      };
      joinBtn.addEventListener("click", (e) => { e.stopPropagation(); _handleJoin(); });
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
            text: `${n.security}  ·  Ch ${n.channel}  ·  ${n.signal}%` }),
        ]),
        joinBtn,
      ]);
      row.addEventListener("click", _handleJoin);
      list.append(row);
    }
  }

  return {
    card,
    setConnectHandler(fn) { _onConnect = fn; },
    scan: () => _scan(false),       // fast: returns cached results immediately
    forceScan: () => _scan(true),   // slow: triggers a fresh OTA scan
  };
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

  const statusCard   = buildStatusCard();
  const portalBanner = buildPortalBanner(checkPortal);
  const netList      = buildNetworkList();
  const savedCard    = buildSavedCard();

  stack.append(statusCard.card, portalBanner.banner, netList.card, savedCard.card);

  /* ---------- state ---------- */
  let _upstreamStatus = "unknown";

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
      portalBanner.hide();
      _upstreamStatus = "disconnected";
      await refreshStatus();
    } catch (err) {
      toast(err.message || "Disconnect failed", "error");
    }
  }

  async function doConnect(ssid, password) {
    await api.post("/wifi/connect", { ssid, password });
    toast(`Joining “${ssid}”…`, "info");
    portalBanner.reset();
    // Show the verification banner immediately — the connection is unverified.
    setTimeout(async () => {
      await refreshStatus();
      if (_upstreamStatus === "connected") {
        portalBanner.showUnverified();
        setTimeout(checkPortal, 2000);
      }
    }, 3500);
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
      message: "The upstream interface MAC will change. You may need to reconnect.",
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
      _upstreamStatus = data.upstream?.status || "unknown";
      if (_upstreamStatus !== "connected") portalBanner.hide();
    } catch {}
  }

  async function refreshSaved() {
    try {
      const data = await api.get("/wifi/saved");
      savedCard.render(data.connections || []);
    } catch {}
  }

  async function checkPortal() {
    if (_upstreamStatus !== "connected") return;
    try {
      const portal = await api.get("/wifi/portal");
      portalBanner.updateFromCheck(portal);
    } catch {}
  }

  /* ---------- init ---------- */

  await Promise.all([refreshStatus(), refreshSaved()]);
  netList.scan();                                          // fast: cached results
  if (_upstreamStatus === "connected") checkPortal();     // non-blocking portal check

  const stopStatus = poll(refreshStatus, 10_000);
  const stopPortal = poll(() => {
    if (_upstreamStatus === "connected") checkPortal();
  }, 45_000);

  view.addEventListener("destroy", () => { stopStatus(); stopPortal(); });
}
