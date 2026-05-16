/* Roku-E8C3 — central polling scheduler.
 * One place owns all live-data refresh so there are no leaked timers and no
 * aggressive background polling: timers pause when the tab is hidden and are
 * fully cleared whenever the page changes. */

const active = [];          // { fn, ms, handle }
let paused = document.hidden;

function runEntry(entry) {
  Promise.resolve()
    .then(entry.fn)
    .catch(() => {});       // page render handles its own error display
}

/** Register a refresh callback. Runs immediately, then every `ms`. */
export function poll(fn, ms = 6000) {
  const entry = { fn, ms, handle: null };
  active.push(entry);
  runEntry(entry);
  if (!paused) entry.handle = setInterval(() => runEntry(entry), ms);
  return entry;
}

/** Clear every registered poller — called on each page change. */
export function clearPolls() {
  active.forEach((e) => { if (e.handle) clearInterval(e.handle); });
  active.length = 0;
}

function pauseAll() {
  paused = true;
  active.forEach((e) => { if (e.handle) { clearInterval(e.handle); e.handle = null; } });
}

function resumeAll() {
  paused = false;
  active.forEach((e) => {
    if (!e.handle) {
      runEntry(e);
      e.handle = setInterval(() => runEntry(e), e.ms);
    }
  });
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) pauseAll();
  else resumeAll();
});
