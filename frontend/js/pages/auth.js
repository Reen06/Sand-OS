/* Roku-E8C3 — login and first-run setup screen. */

import { api, setCsrf, ApiError } from "../api.js";
import { el, clear, frag, setLoading } from "../ui.js";
import { icon } from "../icons.js";

function passwordField(label, name) {
  const input = el("input", {
    class: "input", type: "password", name, autocomplete:
      name === "confirm" ? "new-password" : "current-password",
    required: true, style: "padding-right:42px",
  });
  const toggle = el("button", {
    class: "icon-btn", type: "button", "aria-label": "Show password",
    style: "position:absolute;right:3px;top:3px;width:36px;height:36px",
    onclick: () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
      toggle.innerHTML = icon(show ? "eyeOff" : "eye", 18);
    },
  });
  toggle.append(frag(icon("eye", 18)));
  return {
    input,
    node: el("div", { class: "field" }, [
      el("label", { class: "label", text: label }),
      el("div", { style: "position:relative" }, [input, toggle]),
    ]),
  };
}

export function renderAuth({ needsSetup, hostname, onAuthed }) {
  const root = document.getElementById("auth");
  clear(root);

  const pw = passwordField(needsSetup ? "Create a password" : "Dashboard password",
                           "password");
  const confirm = needsSetup ? passwordField("Confirm password", "confirm") : null;
  const errorBox = el("div", { class: "field-error", role: "alert", hidden: true });
  const submit = el("button", {
    class: "btn btn--primary btn--block", type: "submit",
    text: needsSetup ? "Create password & continue" : "Sign in",
  });

  const showError = (msg) => {
    clear(errorBox);
    errorBox.append(frag(icon("alert", 13)), document.createTextNode(" " + msg));
    errorBox.hidden = false;
  };

  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorBox.hidden = true;
      const password = pw.input.value;
      if (needsSetup && password !== confirm.input.value) {
        showError("Passwords do not match.");
        confirm.input.focus();
        return;
      }
      setLoading(submit, true);
      try {
        if (needsSetup) await api.post("/auth/setup", { password });
        const res = await api.post("/auth/login", { password });
        setCsrf(res.csrf);
        onAuthed();
      } catch (err) {
        setLoading(submit, false);
        showError(err instanceof ApiError ? err.message : "Something went wrong.");
        pw.input.focus();
        pw.input.select();
      }
    },
  }, [
    pw.node,
    confirm ? confirm.node : null,
    needsSetup
      ? el("p", { class: "help", text:
          "Use at least 10 characters with three of: lowercase, uppercase, digits, symbols." })
      : null,
    errorBox,
    el("div", { style: "margin-top:var(--s5)" }, [submit]),
  ]);

  const card = el("div", { class: "auth__card" }, [
    el("div", { class: "auth__brand" }, [
      el("span", { class: "sidebar__logo", html: icon("router", 32) }),
      el("h1", { text: hostname || "Roku-E8C3" }),
      el("p", { text: needsSetup
        ? "First-time setup — secure your dashboard"
        : "Sign in to manage your travel router" }),
    ]),
    form,
  ]);

  root.append(card);
  root.hidden = false;
  pw.input.focus();
}
