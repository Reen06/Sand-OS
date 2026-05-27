/* SandOS — Pi-hole management page. */

import { api } from "../api.js";
import { el, clear, frag, toast, setLoading } from "../ui.js";
import { icon } from "../icons.js";

// ------------------------------------------------------------------ helpers

function statTile(label, value, sub) {
  return el("div", { class: "stat-tile" }, [
    el("div", { class: "stat-tile__value", text: String(value) }),
    el("div", { class: "stat-tile__label", text: label }),
    sub ? el("div", { class: "stat-tile__sub", text: sub }) : null,
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

function spinner() {
  return el("div", { class: "row", style: "justify-content:center;padding:var(--s6)" },
            [el("div", { class: "spinner" })]);
}

function relTime(ts) {
  if (!ts) return "—";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

function fmtTime(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// ------------------------------------------------------------------ stats bar

function buildStatsBar(summary) {
  const tiles = el("div", {
    class: "grid",
    style: "grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:var(--s3)",
  });
  const s = summary || {};
  tiles.append(
    statTile("Queries today", (s.total || 0).toLocaleString()),
    statTile("Blocked", (s.blocked || 0).toLocaleString(),
             `${s.percent_blocked || 0}%`),
    statTile("Cached", (s.cached || 0).toLocaleString()),
    statTile("Unique domains", (s.unique_domains || 0).toLocaleString()),
  );
  return tiles;
}

// ------------------------------------------------------------------ blocking toggle

function buildControlCard(status, onToggle) {
  const isBlocking = status?.blocking ?? true;
  const isDown = status?.status !== "active";
  const isFailover = status?.failover ?? false;

  const toggleBtn = el("button", {
    class: `btn ${isBlocking ? "btn--danger" : "btn--primary"}`,
    type: "button",
    text: isBlocking ? "Disable blocking" : "Enable blocking",
    disabled: isDown,
  });

  const minutesSel = el("select", { class: "input", style: "width:auto" }, [
    el("option", { value: "", text: "Until re-enabled" }),
    el("option", { value: "5", text: "5 minutes" }),
    el("option", { value: "15", text: "15 minutes" }),
    el("option", { value: "60", text: "1 hour" }),
  ]);

  const durationRow = el("div", { class: "row", style: isBlocking ? "" : "display:none" }, [
    el("label", { class: "label", style: "margin:0", text: "Duration:" }),
    minutesSel,
  ]);

  toggleBtn.addEventListener("click", async () => {
    setLoading(toggleBtn, true);
    try {
      const mins = isBlocking && minutesSel.value ? parseInt(minutesSel.value) : null;
      await api.post("/pihole/blocking", { enabled: !isBlocking, duration_mins: mins });
      toast(isBlocking ? "Blocking disabled" : "Blocking enabled", "ok");
      onToggle();
    } catch (e) {
      toast(e.message || "Could not toggle blocking", "error");
    } finally { setLoading(toggleBtn, false); }
  });

  const statusDot = el("span", {
    class: `dot dot--${isDown ? "danger" : isBlocking ? "ok" : "warn"}`,
  });
  const statusLabel = el("span", {
    class: "text-sm",
    text: isDown ? "Pi-hole is down"
        : isFailover ? "DNS failover active — Pi-hole bypassed"
        : isBlocking ? "Blocking active" : "Blocking disabled",
  });

  return card("Blocking", [
    el("div", { class: "row", style: "margin-bottom:var(--s4)" }, [statusDot, statusLabel]),
    durationRow,
    el("div", { style: "margin-top:var(--s4)" }, [toggleBtn]),
  ]);
}

// ------------------------------------------------------------------ query log

function queryStatusBadge(status, blocked) {
  const cls = blocked ? "badge badge--danger"
            : status === "cached" ? "badge badge--info"
            : "badge badge--ok";
  return el("span", { class: cls, text: blocked ? "blocked" : status });
}

function buildQueryLogCard() {
  const tbody = el("tbody");
  const refreshBtn = el("button", { class: "icon-btn", type: "button",
    "aria-label": "Refresh queries" });
  refreshBtn.append(frag(icon("refresh", 16)));

  const filterInput = el("input", {
    class: "input input--sm",
    type: "search",
    placeholder: "Filter by domain or client…",
    style: "max-width:240px",
  });

  let allRows = [];

  function applyFilter() {
    const term = filterInput.value.toLowerCase();
    clear(tbody);
    const filtered = term
      ? allRows.filter(r => r.domain.includes(term) || r.client.includes(term))
      : allRows;
    if (!filtered.length) {
      tbody.append(el("tr", {}, [el("td", { colspan: 4, class: "muted text-sm",
        style: "padding:var(--s4);text-align:center", text: "No queries yet." })]));
      return;
    }
    for (const q of filtered.slice(0, 200)) {
      tbody.append(el("tr", {}, [
        el("td", { class: "mono text-xs muted", text: fmtTime(q.time) }),
        el("td", { class: "mono text-sm truncate", style: "max-width:240px",
          text: q.domain, title: q.domain }),
        el("td", { class: "text-xs muted truncate", style: "max-width:120px",
          text: q.client }),
        el("td", {}, [queryStatusBadge(q.status, q.blocked)]),
      ]));
    }
  }

  filterInput.addEventListener("input", applyFilter);

  async function load() {
    clear(tbody).append(el("tr", {}, [el("td", { colspan: 4 }, [spinner()])]));
    try {
      const d = await api.get("/pihole/queries?limit=200");
      allRows = d.queries || [];
      applyFilter();
    } catch (e) {
      clear(tbody).append(el("tr", {}, [
        el("td", { colspan: 4, class: "muted text-sm",
          style: "padding:var(--s4);text-align:center",
          text: "Could not load query log." })]));
    }
  }

  refreshBtn.addEventListener("click", load);
  load();

  const table = el("table", { class: "table", style: "font-size:0.8rem" }, [
    el("thead", {}, [el("tr", {}, [
      el("th", { text: "Time" }),
      el("th", { text: "Domain" }),
      el("th", { text: "Client" }),
      el("th", { text: "Status" }),
    ])]),
    tbody,
  ]);

  return card("Query log",
    [el("div", { class: "spread", style: "margin-bottom:var(--s3)" },
       [filterInput, refreshBtn]),
     el("div", { style: "overflow-x:auto;max-height:420px;overflow-y:auto" }, [table])],
    null);
}

// ------------------------------------------------------------------ top domains

function buildTopCard() {
  const permitted = el("div", { class: "stack", style: "gap:2px" });
  const blocked = el("div", { class: "stack", style: "gap:2px" });

  function domainRow(d, isBlocked) {
    const addBtn = el("button", { class: "btn btn--sm", type: "button",
      text: isBlocked ? "Allow" : "Block" });
    addBtn.addEventListener("click", async () => {
      setLoading(addBtn, true);
      try {
        const listType = isBlocked ? "allow" : "deny";
        await api.post("/pihole/list", { domain: d.domain, list_type: listType });
        toast(`${d.domain} added to ${listType}list`, "ok");
      } catch (e) {
        toast(e.message || "Failed", "error");
      } finally { setLoading(addBtn, false); }
    });
    return el("div", { class: "spread", style: "padding:4px 0;border-bottom:1px solid var(--border)" }, [
      el("span", { class: "mono text-sm truncate", style: "max-width:200px",
        text: d.domain, title: d.domain }),
      el("div", { class: "row" }, [
        el("span", { class: "muted text-xs", style: "margin-right:var(--s2)",
          text: d.count.toLocaleString() }),
        addBtn,
      ]),
    ]);
  }

  async function load() {
    clear(permitted).append(spinner());
    clear(blocked).append(spinner());
    try {
      const d = await api.get("/pihole/top");
      clear(permitted);
      if (!d.top_permitted?.length) {
        permitted.append(el("p", { class: "muted text-sm", text: "No data yet." }));
      } else {
        for (const r of d.top_permitted) permitted.append(domainRow(r, false));
      }
      clear(blocked);
      if (!d.top_blocked?.length) {
        blocked.append(el("p", { class: "muted text-sm", text: "No data yet." }));
      } else {
        for (const r of d.top_blocked) blocked.append(domainRow(r, true));
      }
    } catch (e) {
      clear(permitted).append(el("p", { class: "muted text-sm", text: "Could not load." }));
      clear(blocked).append(el("p", { class: "muted text-sm", text: "Could not load." }));
    }
  }

  load();

  return el("div", {
    class: "grid",
    style: "grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:var(--s4);align-items:start",
  }, [
    card("Top allowed domains", [permitted]),
    card("Top blocked domains", [blocked]),
  ]);
}

// ------------------------------------------------------------------ domain management

function buildListCard(onRefresh) {
  const domainInput = el("input", { class: "input", type: "text",
    placeholder: "example.com", autocomplete: "off" });
  const listSel = el("select", { class: "input", style: "width:auto" }, [
    el("option", { value: "deny", text: "Block (denylist)" }),
    el("option", { value: "allow", text: "Allow (allowlist)" }),
  ]);
  const addBtn = el("button", { class: "btn btn--primary", type: "submit",
    text: "Add domain" });

  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      const domain = domainInput.value.trim();
      if (!domain) return;
      setLoading(addBtn, true);
      try {
        await api.post("/pihole/list", { domain, list_type: listSel.value });
        toast(`${domain} added to ${listSel.value}list`, "ok");
        domainInput.value = "";
        onRefresh();
      } catch (err) {
        toast(err.message || "Failed to add domain", "error");
      } finally { setLoading(addBtn, false); }
    },
  }, [
    el("div", { class: "row row--wrap", style: "gap:var(--s2);align-items:flex-end" }, [
      el("div", { style: "flex:1;min-width:180px" }, [
        el("label", { class: "label", text: "Domain" }), domainInput,
      ]),
      el("div", {}, [el("label", { class: "label", text: "Action" }), listSel]),
      el("div", { style: "margin-top:auto" }, [addBtn]),
    ]),
    el("p", { class: "help mt-2",
      text: "Add any domain to block or always-allow it. Wildcards: *.example.com" }),
  ]);

  return card("Domain management", [form]);
}

// ------------------------------------------------------------------ page

export async function render(view) {
  let phStatus = null;
  let summary = null;

  const statsWrap = el("div");
  const controlWrap = el("div");

  view.append(
    el("div", { class: "page-head" }, [
      el("div", { class: "page-head__text" }, [
        el("h2", { text: "Pi-hole" }),
        el("p", { text: "DNS ad-blocking — query log, top domains, and list management." }),
      ]),
    ]),
    statsWrap,
    el("div", {
      class: "grid mt-4",
      style: "grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--s4);align-items:start",
    }, [controlWrap]),
  );

  const queryCard = buildQueryLogCard();
  const topWrap = el("div", { class: "mt-4" });
  const listCard = buildListCard(() => {
    topWrap.querySelector && load();
  });

  async function load() {
    try {
      [phStatus, summary] = await Promise.all([
        api.get("/pihole/status"),
        api.get("/pihole/summary"),
      ]);
    } catch (_) { phStatus = null; summary = null; }

    clear(statsWrap).append(buildStatsBar(summary));
    clear(controlWrap).append(
      buildControlCard(phStatus, load),
      el("div", { class: "mt-4" }, [listCard]),
    );
  }

  view.append(
    el("div", { class: "mt-4" }, [queryCard]),
    topWrap,
  );

  topWrap.append(buildTopCard());

  await load();
}
