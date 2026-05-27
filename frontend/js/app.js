/* Roku-E8C3 — dashboard shell: auth gate, navigation, hash routing. */

import { api, onUnauthorized, setCsrf } from "./api.js";
import { icon, paintIcons } from "./icons.js";
import { el, clear, frag, toast, emptyState } from "./ui.js";
import { clearPolls } from "./store.js";
import { renderAuth } from "./pages/auth.js";

const PAGES = [
  { path: "/",         file: "overview.js", label: "Overview", icon: "gauge",    title: "Overview" },
  { path: "/devices",  file: "devices.js",  label: "Devices",  icon: "devices",  title: "Devices" },
  { path: "/wifi",     file: "wifi.js",     label: "WiFi",     icon: "wifi",     title: "WiFi" },
  { path: "/vpn",      file: "vpn.js",      label: "VPN",      icon: "shield",   title: "VPN" },
  { path: "/routing",  file: "routing.js",  label: "Routing",  icon: "route",    title: "Routing" },
  { path: "/guest",    file: "guest.js",    label: "Guest",    icon: "users",    title: "Guest Network" },
  { path: "/pihole",   file: "pihole.js",   label: "Pi-hole",  icon: "ban",      title: "Pi-hole" },
  { path: "/settings", file: "settings.js", label: "Settings", icon: "settings", title: "Settings" },
  { path: "/logs",     file: "logs.js",     label: "Logs",     icon: "logs",     title: "Logs" },
];

let currentMod = null;
let routeSeq = 0;

/* ------------------------------------------------------------------ boot */
async function init() {
  paintIcons(document);
  onUnauthorized(handleUnauthorized);
  try {
    const status = await api.get("/auth/status");
    if (!status.authenticated) return showAuth(status);
    if (status.csrf) setCsrf(status.csrf);
    enterDashboard();
  } catch {
    showAuth({ needs_setup: false });
  }
}

function handleUnauthorized() {
  if (!document.getElementById("app").hidden) {
    toast("Session expired — please sign in again", "info");
    showAuth({ needs_setup: false });
  }
}

async function showAuth(status) {
  if (!status) {
    try { status = await api.get("/auth/status"); }
    catch { status = { needs_setup: false }; }
  }
  document.getElementById("boot").hidden = true;
  document.getElementById("app").hidden = true;
  renderAuth({
    needsSetup: !!status.needs_setup,
    hostname: status.hostname,
    onAuthed: () => { document.getElementById("auth").hidden = true; enterDashboard(); },
  });
}

/* --------------------------------------------------------------- shell */
function enterDashboard() {
  document.getElementById("boot").hidden = true;
  document.getElementById("auth").hidden = true;
  document.getElementById("app").hidden = false;
  buildNav();
  wireChrome();
  window.addEventListener("hashchange", route);
  route();
}

function buildNav() {
  const nav = clear(document.getElementById("nav"));
  for (const p of PAGES) {
    const item = el("a", {
      class: "nav-item", href: "#" + p.path, dataset: { path: p.path },
    }, [frag(icon(p.icon, 18)), el("span", { text: p.label })]);
    nav.append(item);
  }
}

function wireChrome() {
  const sidebar = document.getElementById("sidebar");
  const scrim = document.getElementById("scrim");
  document.getElementById("btn-menu").addEventListener("click", () => {
    sidebar.classList.add("is-open");
    scrim.hidden = false;
  });
  scrim.addEventListener("click", closeDrawer);
  document.getElementById("nav").addEventListener("click", closeDrawer);
  document.getElementById("btn-logout").addEventListener("click", doLogout);
}

function closeDrawer() {
  document.getElementById("sidebar").classList.remove("is-open");
  document.getElementById("scrim").hidden = true;
}

async function doLogout() {
  try { await api.post("/auth/logout"); } catch {}
  setCsrf("");
  clearPolls();
  location.hash = "";
  showAuth({ needs_setup: false });
}

/* --------------------------------------------------------------- router */
async function route() {
  const seq = ++routeSeq;
  const path = location.hash.replace(/^#/, "") || "/";
  const page = PAGES.find((p) => p.path === path) || PAGES[0];

  clearPolls();
  if (currentMod && typeof currentMod.cleanup === "function") {
    try { currentMod.cleanup(); } catch {}
  }
  currentMod = null;

  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("is-active", n.dataset.path === page.path);
  });
  document.getElementById("page-title").textContent = page.title;
  document.title = `${page.title} · Roku-E8C3`;

  const view = document.getElementById("view");
  clear(view).append(frag(
    '<div class="row" style="justify-content:center;padding:var(--s12)">' +
    '<div class="spinner spinner--lg" role="status" aria-label="Loading"></div></div>'));
  closeDrawer();

  let mod;
  try {
    mod = await import("./pages/" + page.file);
  } catch (err) {
    if (seq !== routeSeq) return;
    clear(view).append(emptyState("alert", "Page failed to load",
      "This dashboard page could not be loaded. Try reloading."));
    paintIcons(view);
    return;
  }
  if (seq !== routeSeq) return;        // a newer navigation superseded this one
  currentMod = mod;
  clear(view);
  try {
    await mod.render(view);
  } catch (err) {
    if (seq !== routeSeq) return;
    clear(view).append(emptyState("alert", "Something went wrong",
      (err && err.message) || "This page could not be rendered."));
  }
  paintIcons(view);
  view.scrollTop = 0;
  window.scrollTo(0, 0);
  view.focus();
}

init();
