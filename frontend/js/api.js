/* Roku-E8C3 — API client.
 * Thin fetch wrapper: JSON in/out, CSRF header on mutations, 401 handling. */

let csrfToken = "";
const unauthorizedHandlers = [];

export function setCsrf(token) { csrfToken = token || ""; }
export function onUnauthorized(fn) { unauthorizedHandlers.push(fn); }

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
  /** True when the endpoint exists but its feature is not yet provisioned. */
  get notReady() { return this.status === 404 || this.status === 501 || this.status === 503; }
}

async function request(method, path, body) {
  const opts = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET" && csrfToken) opts.headers["X-Roku-CSRF"] = csrfToken;

  let res;
  try {
    res = await fetch("/api" + path, opts);
  } catch {
    throw new ApiError("Network error — the dashboard backend is unreachable", 0);
  }

  if (res.status === 401) {
    unauthorizedHandlers.forEach((fn) => { try { fn(); } catch {} });
    throw new ApiError("Authentication required", 401);
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); }
    catch { data = { detail: text }; }
  }
  if (!res.ok) {
    let msg = data && (data.detail || data.message);
    if (Array.isArray(msg)) msg = msg.map((e) => e.msg || e).join("; ");
    throw new ApiError(typeof msg === "string" ? msg : `Request failed (${res.status})`,
                       res.status);
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  del: (path, body) => request("DELETE", path, body),
};
