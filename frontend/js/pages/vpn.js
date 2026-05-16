/* Roku-E8C3 — VPN page.
 * WireGuard profile upload, tunnel control and statistics. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, modal, confirmDialog, toast, setLoading, emptyState, fmtBytes, fmtRelative } from "../ui.js";
import { icon } from "../icons.js";

/* ---------------------------------------------------------------- upload modal */
function showUploadModal(onDone) {
  const nameField = el("input", { class: "input", type: "text", placeholder: "e.g. mullvad-us" });
  const fileInput = el("input", { type: "file", accept: ".conf", style: "display:none" });
  const filePick  = el("button", { class: "btn", type: "button", text: "Choose .conf file" }, [
    frag(icon("upload", 14)),
    document.createTextNode(" Choose .conf file"),
  ]);
  const fileName  = el("span", { class: "muted text-sm", text: "No file selected" });
  const errMsg    = el("p", { class: "text-sm", style: "color:var(--danger);display:none" });
  const uploadBtn = el("button", { class: "btn btn--primary", type: "button", text: "Upload" });
  const cancelBtn = el("button", { class: "btn", type: "button", text: "Cancel" });

  filePick.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    fileName.textContent = fileInput.files[0]?.name || "No file selected";
  });

  const body = el("div", { class: "stack" }, [
    el("div", [
      el("label", { class: "label", text: "Profile name" }),
      nameField,
      el("p", { class: "help", text: "Letters, numbers, dashes, underscores. Used to identify this tunnel." }),
    ]),
    el("div", [
      el("label", { class: "label", text: "WireGuard config (.conf)" }),
      el("div", { class: "row" }, [filePick, fileName]),
    ]),
    fileInput,
    errMsg,
  ]);

  const m = modal({ title: "Upload WireGuard Config", body, footer: [cancelBtn, uploadBtn] });
  cancelBtn.addEventListener("click", () => m.close());
  setTimeout(() => nameField.focus(), 60);

  uploadBtn.addEventListener("click", async () => {
    const name = nameField.value.trim();
    const file = fileInput.files[0];
    errMsg.style.display = "none";

    if (!name) { errMsg.textContent = "Profile name is required."; errMsg.style.display = ""; return; }
    if (!/^[a-zA-Z0-9_-]{1,40}$/.test(name)) {
      errMsg.textContent = "Name: letters, numbers, dashes, underscores only (1-40 chars).";
      errMsg.style.display = ""; return;
    }
    if (!file) { errMsg.textContent = "Please select a .conf file."; errMsg.style.display = ""; return; }

    const form = new FormData();
    form.append("name", name);
    form.append("conf", file);

    setLoading(uploadBtn, true);
    try {
      const opts = { method: "POST", body: form, credentials: "same-origin" };
      const csrfToken = document.cookie.match(/roku_csrf=([^;]+)/)?.[1] || "";
      if (csrfToken) opts.headers = { "X-Roku-CSRF": csrfToken };
      const res = await fetch("/api/vpn/profiles/upload", opts);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      m.close();
      toast(data.message || "Profile uploaded", "ok");
      onDone();
    } catch (err) {
      errMsg.textContent = err.message || "Upload failed.";
      errMsg.style.display = "";
      setLoading(uploadBtn, false);
    }
  });
}

/* ---------------------------------------------------------------- profile card */
function buildProfileCard(profile, onAction) {
  const active = profile.active;
  const statusDot = el("span", {
    class: `dot dot--${active ? "ok" : "idle"}`,
    style: "flex:none",
  });
  const statusText = el("span", {
    class: "text-sm muted",
    text: active ? "Connected" : "Disconnected",
  });
  const defaultBadge = profile.is_default
    ? el("span", { class: "badge badge--info", text: "default" })
    : null;

  const connectBtn = el("button", {
    class: `btn btn--sm ${active ? "btn--danger" : "btn--primary"}`,
    text: active ? "Disconnect" : "Connect",
  });
  const moreBtn = el("button", { class: "btn btn--sm", title: "More actions" }, [
    frag(icon("chevronDown", 14)),
  ]);

  connectBtn.addEventListener("click", () =>
    onAction(profile.name, active ? "disconnect" : "connect"));

  // Dropdown for set-default / delete
  moreBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const menu = el("div", {
      style: "position:absolute;right:0;top:100%;z-index:50;min-width:160px;" +
             "background:var(--surface-2);border:1px solid var(--border-strong);" +
             "border-radius:var(--radius-sm);box-shadow:var(--shadow-2);padding:var(--s2) 0;",
    });
    const items = [
      { label: "Set as default", action: "set-default" },
      { label: "Delete profile", action: "delete", danger: true },
    ];
    for (const item of items) {
      const btn = el("button", {
        class: "btn btn--ghost",
        style: `width:100%;justify-content:flex-start;padding:var(--s2) var(--s4);` +
               (item.danger ? "color:var(--danger);" : ""),
        text: item.label,
      });
      btn.addEventListener("click", () => { menu.remove(); onAction(profile.name, item.action); });
      menu.append(btn);
    }
    const pos = el("div", { style: "position:relative" }, [menu]);
    moreBtn.parentElement.append(pos);
    const close = (ev) => { if (!pos.contains(ev.target)) { pos.remove(); document.removeEventListener("click", close); } };
    setTimeout(() => document.addEventListener("click", close), 0);
  });

  const stats = profile.active ? el("div", { class: "row", style: "margin-top:var(--s3);flex-wrap:wrap;gap:var(--s4)" }, [
    el("div", { class: "text-sm" }, [
      el("span", { class: "muted", text: "↓ " }),
      el("span", { text: fmtBytes(profile.rx_bytes) }),
    ]),
    el("div", { class: "text-sm" }, [
      el("span", { class: "muted", text: "↑ " }),
      el("span", { text: fmtBytes(profile.tx_bytes) }),
    ]),
    profile.last_handshake ? el("div", { class: "text-sm muted" }, [
      el("span", { text: `handshake ${fmtRelative(profile.last_handshake)}` }),
    ]) : null,
  ]) : null;

  const endpointEl = profile.endpoint
    ? el("div", { class: "text-sm mono muted", text: profile.endpoint })
    : null;

  return el("div", { class: "card" }, [
    el("div", { class: "card__body" }, [
      el("div", { class: "row", style: "margin-bottom:var(--s2)" }, [
        statusDot,
        el("span", { class: "fw-600", text: profile.name }),
        defaultBadge,
        el("span", { class: "grow" }),
        statusText,
      ]),
      endpointEl,
      stats,
      el("div", { class: "row", style: "margin-top:var(--s4)" }, [
        connectBtn, moreBtn,
      ]),
    ]),
  ]);
}

/* ================================================================ main render */
export async function render(view) {
  const uploadBtn = el("button", { class: "btn btn--primary" }, [
    frag(icon("upload", 14)),
    document.createTextNode(" Upload .conf"),
  ]);

  const stack = el("div", { class: "stack" });

  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "VPN" }),
        el("p", { text: "WireGuard tunnels — upload a .conf to add a tunnel, then assign devices on the Routing page." }),
      ]),
      el("div", { class: "page-head__actions" }, [uploadBtn]),
    ]),
    stack,
  );

  /* ---------- actions ---------- */

  async function handleAction(name, action) {
    if (action === "delete") {
      if (!await confirmDialog({
        title: `Delete "${name}"?`,
        message: "The tunnel will be brought down and its config removed.",
        confirmLabel: "Delete",
        danger: true,
      })) return;
      try {
        await api.del(`/vpn/profiles/${name}`);
        toast(`Profile "${name}" deleted`, "ok");
        await refresh();
      } catch (err) { toast(err.message || "Delete failed", "error"); }
      return;
    }
    if (action === "connect" || action === "disconnect") {
      try {
        await api.post(`/vpn/profiles/${name}/action`, { action });
        toast(action === "connect" ? `Connecting "${name}"…` : `"${name}" disconnected`, "ok");
        setTimeout(refresh, 2000);
      } catch (err) { toast(err.message || "Action failed", "error"); }
      return;
    }
    if (action === "set-default") {
      try {
        await api.post(`/vpn/profiles/${name}/action`, { action: "set-default" });
        toast(`"${name}" set as default tunnel`, "ok");
        await refresh();
      } catch (err) { toast(err.message || "Failed", "error"); }
    }
  }

  /* ---------- data ---------- */

  async function refresh() {
    try {
      const data = await api.get("/vpn/profiles");
      renderProfiles(data.profiles || []);
    } catch {}
  }

  function renderProfiles(profiles) {
    clear(stack);
    if (!profiles.length) {
      stack.append(
        el("div", { class: "card" }, [
          el("div", { class: "card__body" }, [
            emptyState("shield", "No VPN profiles",
              "Upload a WireGuard .conf file to add your first tunnel. Devices can then be routed through it on the Routing page.",
              el("button", { class: "btn btn--primary", onclick: () => showUploadModal(refresh) }, [
                frag(icon("upload", 14)),
                document.createTextNode(" Upload .conf"),
              ])
            ),
          ]),
        ])
      );
      return;
    }
    for (const p of profiles) {
      stack.append(buildProfileCard(p, handleAction));
    }
  }

  uploadBtn.addEventListener("click", () => showUploadModal(refresh));

  await refresh();
  const stopPoll = poll(refresh, 10_000);
  view.addEventListener("destroy", stopPoll);
}
