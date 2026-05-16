/* Roku-E8C3 — Guest Network page.
 * A separate, isolated WiFi network for visitors. */

import { api } from "../api.js";
import { poll } from "../store.js";
import { el, clear, frag, toast, setLoading, emptyState } from "../ui.js";
import { icon } from "../icons.js";

/* ================================================================ main render */
export async function render(view) {
  const stack = el("div", { class: "stack" });
  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Guest Network" }),
        el("p", { text: "A separate, isolated WiFi network for visitors — blocked from your main LAN." }),
      ]),
    ]),
    stack,
  );

  /* ---------- config card ---------- */
  const enableToggle = el("input", { type: "checkbox" });
  const enableTrack  = el("div", { class: "toggle__track" });

  const ssidField = el("input", { class: "input", type: "text", placeholder: "Guest SSID" });
  const pwField   = el("input", { class: "input", type: "password", placeholder: "Password (min 8 chars)" });
  const showPw    = el("button", { class: "icon-btn", type: "button", title: "Show password" });
  showPw.append(frag(icon("eye", 16)));
  showPw.addEventListener("click", () => {
    const hidden = pwField.type === "password";
    pwField.type = hidden ? "text" : "password";
    clear(showPw).append(frag(icon(hidden ? "eyeOff" : "eye", 16)));
  });

  const errMsg  = el("p", { class: "text-sm", style: "color:var(--danger);display:none" });
  const saveBtn = el("button", { class: "btn btn--primary", text: "Save & Apply" });

  const configCard = el("div", { class: "card" }, [
    el("div", { class: "card__header" }, [
      frag(icon("users", 16)),
      el("span", { class: "card__title", text: "Guest Network" }),
      el("span", { class: "grow" }),
      el("label", { class: "toggle" }, [
        enableToggle, enableTrack,
        el("span", { class: "toggle__label", text: "Enabled" }),
      ]),
    ]),
    el("div", { class: "card__body stack" }, [
      el("div", [
        el("label", { class: "label", text: "SSID (guest network name)" }),
        ssidField,
      ]),
      el("div", [
        el("label", { class: "label", text: "Password" }),
        el("div", { style: "position:relative" }, [
          pwField,
          el("span", {
            style: "position:absolute;right:var(--s3);top:50%;transform:translateY(-50%)",
          }, [showPw]),
        ]),
        el("p", { class: "help", text: "At least 8 characters. Visitors join with this password." }),
      ]),
      errMsg,
      el("div", { class: "row" }, [
        el("span", { class: "grow" }),
        saveBtn,
      ]),
    ]),
  ]);

  /* ---------- isolation callout ---------- */
  const isolationCard = el("div", { class: "callout callout--info" }, [
    frag(icon("shield", 18)),
    el("div", [
      el("div", { class: "fw-600", text: "Automatic isolation" }),
      el("div", { class: "text-sm muted",
        text: "Guest devices cannot reach your main LAN (10.0.0.x). Intra-guest traffic is also blocked. All guests share one upstream internet connection." }),
    ]),
  ]);

  /* ---------- clients card ---------- */
  const clientsList = el("div", { class: "stack" });
  const clientsCard = el("div", { class: "card" }, [
    el("div", { class: "card__header" }, [
      frag(icon("devices", 16)),
      el("span", { class: "card__title", text: "Guest Devices" }),
    ]),
    el("div", { class: "card__body" }, [clientsList]),
  ]);

  stack.append(configCard, isolationCard, clientsCard);

  /* ---------- save ---------- */
  saveBtn.addEventListener("click", async () => {
    errMsg.style.display = "none";
    const ssid = ssidField.value.trim();
    const pw   = pwField.value;
    if (!ssid) { errMsg.textContent = "SSID is required."; errMsg.style.display = ""; return; }
    if (pw && pw.length < 8) {
      errMsg.textContent = "Password must be at least 8 characters."; errMsg.style.display = ""; return;
    }
    setLoading(saveBtn, true);
    try {
      await api.post("/guest/config", {
        enabled: enableToggle.checked,
        ssid,
        passphrase: pw || undefined,
      });
      toast("Guest network config saved and applied", "ok");
      await refresh();
    } catch (err) {
      errMsg.textContent = err.message || "Save failed.";
      errMsg.style.display = "";
    } finally {
      setLoading(saveBtn, false);
    }
  });

  /* ---------- data ---------- */

  async function refresh() {
    try {
      const data = await api.get("/guest/config");
      enableToggle.checked = data.enabled;
      ssidField.value = data.ssid || "";
      pwField.value = data.passphrase || "";

      // Update clients list
      const clients = await api.get("/guest/devices").catch(() => ({ devices: [] }));
      clear(clientsList);
      if (!clients.devices.length) {
        clientsList.append(el("p", { class: "muted text-sm", text: "No guest devices connected." }));
      } else {
        for (const d of clients.devices) {
          clientsList.append(el("div", {
            class: "row",
            style: "padding:var(--s2) 0;border-bottom:1px solid var(--border)",
          }, [
            frag(icon("devices", 14)),
            el("div", { class: "grow" }, [
              el("div", { text: d.hostname || "Unknown" }),
              el("div", { class: "mono muted text-xs", text: d.mac }),
            ]),
            el("span", { class: "mono text-sm", text: d.ip || "—" }),
          ]));
        }
      }
    } catch {}
  }

  await refresh();
  const stopPoll = poll(refresh, 20_000);
  view.addEventListener("destroy", stopPoll);
}
