/* Roku-E8C3 — inline SVG icon set.
 * Lucide-style stroke icons: 24x24 viewBox, 1.75 stroke, round caps.
 * One visual language across the whole dashboard (no emoji). */

const PATHS = {
  router: '<rect x="3" y="13.5" width="18" height="6.6" rx="1.7"/><path d="M7 16.8v.01M10.5 16.8v.01"/><path d="M12 13.5V10"/><path d="M8.8 9.2a4.6 4.6 0 0 1 6.4 0"/><path d="M6.3 6.7a8.2 8.2 0 0 1 11.4 0"/>',
  gauge: '<path d="M12 14l4-4"/><path d="M3.6 14a8.4 8.4 0 1 1 16.8 0"/><circle cx="12" cy="14" r="1.6"/>',
  devices: '<rect x="2.5" y="4.5" width="14" height="10" rx="1.6"/><path d="M6 18.5h7"/><path d="M9.5 14.5v4"/><rect x="17" y="9.5" width="5" height="9" rx="1.4"/>',
  wifi: '<path d="M4.5 11.5a11 11 0 0 1 15 0"/><path d="M8 15a6 6 0 0 1 8 0"/><path d="M12 18.5h.01"/>',
  shield: '<path d="M12 3.2l7 2.6v5.4c0 4.8-3.3 7.8-7 9-3.7-1.2-7-4.2-7-9V5.8z"/><path d="M9 12l2 2 4-4"/>',
  route: '<circle cx="6.5" cy="18" r="2.6"/><circle cx="17.5" cy="6" r="2.6"/><path d="M9 18h5.5a3.5 3.5 0 0 0 0-7H10a3.5 3.5 0 0 1 0-7h5"/>',
  users: '<circle cx="9" cy="8" r="3.3"/><path d="M3.4 19a5.6 5.6 0 0 1 11.2 0"/><path d="M15.5 5.3a3.3 3.3 0 0 1 0 6.4"/><path d="M17.6 19a5.6 5.6 0 0 0-3-5"/>',
  settings: '<path d="M3.5 7.5h8M16 7.5h4.5M3.5 16.5h4M11 16.5h9.5"/><circle cx="13.5" cy="7.5" r="2.4"/><circle cx="8" cy="16.5" r="2.4"/>',
  logs: '<rect x="4.5" y="3" width="13" height="18" rx="1.7"/><path d="M8 8h6M8 12h6M8 16h3.5"/><path d="M17.5 7v11.5a2 2 0 0 0 2 2"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  power: '<path d="M12 4v8"/><path d="M7.6 7.6a7 7 0 1 0 8.8 0"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-13.7-5.4L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 13.7 5.4L20 16"/><path d="M20 20v-4h-4"/>',
  chevronRight: '<path d="M9 6l6 6-6 6"/>',
  chevronDown: '<path d="M6 9l6 6 6-6"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="8.6"/><path d="M12 11v5M12 8h.01"/>',
  search: '<circle cx="11" cy="11" r="6.6"/><path d="M20 20l-4.4-4.4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13"/>',
  pencil: '<path d="M4 20h4L20 8l-4-4L4 16z"/><path d="M14.5 5.5l4 4"/>',
  lock: '<rect x="5" y="11" width="14" height="9.5" rx="1.7"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  signal: '<path d="M4 18.5v-2.5M9 18.5v-6M14 18.5v-9.5M19 18.5V5.5"/>',
  globe: '<circle cx="12" cy="12" r="8.6"/><path d="M3.5 12h17"/><path d="M12 3.4c2.6 2.7 2.6 14.5 0 17.2M12 3.4c-2.6 2.7-2.6 14.5 0 17.2"/>',
  ban: '<circle cx="12" cy="12" r="8.6"/><path d="M6 6l12 12"/>',
  upload: '<path d="M12 16V5M8 9l4-4 4 4"/><path d="M5 15.5V19h14v-3.5"/>',
  download: '<path d="M12 5v11M8 12l4 4 4-4"/><path d="M5 19h14"/>',
  arrowLeft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  link: '<path d="M9.5 14.5l5-5"/><path d="M11 6.5l1.5-1.5a3.5 3.5 0 0 1 5 5L17 11.5"/><path d="M13 17.5L11.5 19a3.5 3.5 0 0 1-5-5L7 12.5"/>',
  cpu: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.6"/><path d="M10 3v3M14 3v3M10 18v3M14 18v3M3 10h3M3 14h3M18 10h3M18 14h3"/>',
  thermometer: '<path d="M12 14.5V5a2.5 2.5 0 0 0-5 0v9.5a4 4 0 1 0 5 0z"/>',
  database: '<ellipse cx="12" cy="6" rx="7.5" ry="3"/><path d="M4.5 6v12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6"/><path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/>',
  clock: '<circle cx="12" cy="12" r="8.6"/><path d="M12 7v5l3.5 2"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M4 4l16 16"/><path d="M9.5 5.7A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-3 3.7M6.4 7.4A16 16 0 0 0 2.5 12S6 18.5 12 18.5a9.4 9.4 0 0 0 3.6-.7"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  wrench: '<path d="M14.5 6.5a4 4 0 0 1-5 5L5 16v3h3l4.5-4.5a4 4 0 0 0 5-5l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.6"/>',
  dot: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  battery: '<rect x="2" y="7.5" width="17" height="9" rx="1.6"/><path d="M19 10.5h1.5a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H19"/><path d="M6 11.5h4M8 9.5v4"/>',
};

export function icon(name, size = 20) {
  const body = PATHS[name] || '';
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" ` +
    `stroke="currentColor" stroke-width="1.75" stroke-linecap="round" ` +
    `stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

/** Replace every <span data-icon="name"> in `root` with its SVG. */
export function paintIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((el) => {
    if (el.dataset.painted) return;
    const size = el.dataset.iconSize ? Number(el.dataset.iconSize) : 20;
    el.innerHTML = icon(el.dataset.icon, size);
    el.dataset.painted = '1';
  });
}
