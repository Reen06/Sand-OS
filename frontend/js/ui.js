/* Roku-E8C3 — DOM helpers, toasts, modals, formatters. */

import { icon, paintIcons } from "./icons.js";

/** Create an element. props: class/text/html/dataset/on<Event>/attributes. */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") {
      node.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, String(v));
  }
  const kids = Array.isArray(children) ? children : [children];
  for (const c of kids) {
    if (c == null || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

/** Build a DocumentFragment from an HTML string, painting any data-icon spans. */
export function frag(html) {
  const t = document.createElement("template");
  t.innerHTML = String(html).trim();
  paintIcons(t.content);
  return t.content;
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/* ---------------------------------------------------------------- toasts */
export function toast(message, kind = "info", ttl = 4200) {
  const root = document.getElementById("toasts");
  if (!root) return () => {};
  const glyph = kind === "ok" ? "check" : kind === "error" ? "alert" : "info";
  const node = el("div", { class: `toast toast--${kind}`, role: "status" }, [
    frag(icon(glyph, 18)),
    el("span", { class: "grow", text: message }),
  ]);
  root.append(node);
  const remove = () => {
    node.classList.add("is-leaving");
    setTimeout(() => node.remove(), 220);
  };
  if (ttl) setTimeout(remove, ttl);
  return remove;
}

/* ---------------------------------------------------------------- modal */
export function modal({ title, body, footer, onClose }) {
  const root = document.getElementById("modal-root");
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    if (onClose) onClose();
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };

  const closeBtn = el("button", {
    class: "icon-btn", type: "button", "aria-label": "Close dialog", onclick: close,
  });
  closeBtn.append(frag(icon("x", 20)));

  const panel = el("div", {
    class: "modal__panel", role: "dialog", "aria-modal": "true",
    "aria-label": title || "Dialog",
  }, [
    el("div", { class: "modal__header" }, [
      el("span", { class: "modal__title", text: title || "" }), closeBtn,
    ]),
    el("div", { class: "modal__body" }, body ? [body] : []),
    footer ? el("div", { class: "modal__footer" }, footer) : null,
  ]);

  const overlay = el("div", {
    class: "modal",
    onclick: (e) => { if (e.target === overlay) close(); },
  }, [panel]);

  document.addEventListener("keydown", onKey);
  root.append(overlay);
  paintIcons(overlay);
  const focusable = panel.querySelector(
    "input, select, textarea, button:not([aria-label='Close dialog'])");
  (focusable || panel).focus();

  return { close, panel };
}

/** Confirmation dialog. Resolves true on confirm, false on cancel. */
export function confirmDialog({ title, message, confirmLabel = "Confirm",
                                cancelLabel = "Cancel", danger = false }) {
  return new Promise((resolve) => {
    let decided = false;
    const finish = (val) => { if (decided) return; decided = true; m.close(); resolve(val); };
    const confirmBtn = el("button", {
      class: `btn ${danger ? "btn--danger" : "btn--primary"}`, type: "button",
      text: confirmLabel, onclick: () => finish(true),
    });
    const cancelBtn = el("button", {
      class: "btn", type: "button", text: cancelLabel, onclick: () => finish(false),
    });
    const m = modal({
      title,
      body: el("p", { class: "muted", text: message }),
      footer: [cancelBtn, confirmBtn],
      onClose: () => finish(false),
    });
  });
}

/* ------------------------------------------------------------ formatters */
export function fmtDuration(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m`;
  return `${seconds}s`;
}

export function fmtBytes(n) {
  n = Number(n) || 0;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${units[i]}`;
}

export function fmtRelative(value) {
  if (!value) return "never";
  const then = typeof value === "number" ? value * 1000 : Date.parse(value + "Z") || Date.parse(value);
  if (!then) return "—";
  const diff = Math.floor((Date.now() - then) / 1000);
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function fmtNum(n) {
  return (Number(n) || 0).toLocaleString("en-US");
}

/* ------------------------------------------------------------ fragments */
export function emptyState(iconName, title, message, action) {
  return el("div", { class: "empty" }, [
    el("div", { class: "empty__icon", html: icon(iconName, 24) }),
    el("h3", { text: title }),
    message ? el("p", { text: message }) : null,
    action || null,
  ]);
}

export function skeletonRows(count = 3, height = 44) {
  const wrap = el("div", { class: "stack" });
  for (let i = 0; i < count; i++) {
    wrap.append(el("div", { class: "skeleton", style: `height:${height}px` }));
  }
  return wrap;
}

/** Set a button into / out of its loading state. */
export function setLoading(btn, loading) {
  if (!btn) return;
  btn.classList.toggle("is-loading", !!loading);
  btn.disabled = !!loading;
}
