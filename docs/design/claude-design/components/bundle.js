/* @ds-bundle: {"format":4,"namespace":"MeshLens","components":[]} */
(function () {
"use strict";
var NS = {};

/* ---------- icons (tratto 1.75, griglia 24) ---------- */
var IC = {
  map: '<path d="M9 4 3 6.5v13L9 17l6 3 6-2.5v-13L15 7 9 4z"/><path d="M9 4v13M15 7v13"/>',
  nodes: '<circle cx="5" cy="6" r="1.5"/><circle cx="5" cy="12" r="1.5"/><circle cx="5" cy="18" r="1.5"/><path d="M10 6h10M10 12h10M10 18h10"/>',
  network: '<circle cx="12" cy="5" r="2.2"/><circle cx="5" cy="18" r="2.2"/><circle cx="19" cy="18" r="2.2"/><path d="M11 7l-5 9M13 7l5 9M7.2 18h9.6"/>',
  coverage: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r=".8"/><path d="M12 12l6-6"/>',
  chat: '<path d="M4 5h16v11H9l-5 4V5z"/>',
  radio: '<rect x="3" y="9" width="18" height="11" rx="2"/><path d="M7 9l9-5M8 14.5h4M16 13.5v2"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  star: '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9l-5.2 2.8 1-5.9L3.5 9.7l5.9-.8L12 3.5z"/>',
  battery: '<rect x="2.5" y="8" width="16" height="9" rx="2"/><path d="M21 11v3"/>',
  plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0V8zM12 17v4"/>',
  bars: '<path d="M4 18v-3M9 18v-6M14 18V9M19 18V5"/>',
  alert: '<path d="M12 4l9 16H3L12 4z"/><path d="M12 10v4M12 17v.4"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16zM10 20h4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  check2: '<path d="M2.5 12.5l4.5 4.5L15 8.5M10 16.5l1 1L21 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14-4L4 9M4 5v4h4M4 13a8 8 0 0 0 14 4l2-2M20 19v-4h-4"/>',
  trash: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10 11v6M14 11v6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  chevR: '<path d="M9 5l7 7-7 7"/>', chevL: '<path d="M15 5l-7 7 7 7"/>', chevD: '<path d="M5 9l7 7 7-7"/>', chevU: '<path d="M5 15l7-7 7 7"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  route: '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 6h6a3 3 0 0 1 0 6h-4a3 3 0 0 0 0 6h6"/>',
  send: '<path d="M4 12L20 4l-6 16-3-7-7-1z"/>',
  usb: '<path d="M12 3v14M12 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM12 9l4-3M12 12l-4-3"/>',
  bt: '<path d="M7 7l10 10-5 4V3l5 4L7 17"/>',
  layers: '<path d="M12 4l9 5-9 5-9-5 9-5zM3 14l9 5 9-5"/>',
  filter: '<path d="M4 5h16l-6 8v6l-4-2v-4L4 5z"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/>',
  power: '<path d="M12 3v9M7 6.5a8 8 0 1 0 10 0"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.4"/>',
  cloudoff: '<path d="M3 3l18 18M7.5 7.8A6 6 0 0 0 7 18h10.5M10 5.3A6 6 0 0 1 18 11a4 4 0 0 1 3 6"/>',
  pin: '<path d="M12 21s7-6.3 7-11.5A7 7 0 0 0 5 9.5C5 14.700 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  sort: '<path d="M8 5v14M5 16l3 3 3-3M16 19V5M13 8l3-3 3 3"/>',
  user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  flag: '<path d="M6 21V4M6 5h11l-2 4 2 4H6"/>',
  spinner: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4zM13 7l4 4"/>',
  back: '<path d="M10 6l-6 6 6 6M4 12h16"/>'
};
NS.icon = function (n, s) {
  s = s || 18;
  return '<svg class="ml-ic" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (IC[n] || "") + "</svg>";
};
NS.iconNames = Object.keys(IC);
var I = NS.icon;

/* ---------- utilità ---------- */
function num(n, d) { return Number(n).toLocaleString("it-IT", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
function signed(n, d) { var s = num(Math.abs(n), d); return (n > 0 ? "+" : n < 0 ? "−" : "") + s; }
function ago(min) {
  if (min < 1) return "ora";
  if (min < 60) return Math.round(min) + " min fa";
  if (min < 1440) return Math.round(min / 60) + " h fa";
  return Math.round(min / 1440) + " g fa";
}
function contactCls(min) { return min < 120 ? "fresh" : min < 1440 ? "recent" : "old"; }
function snrCls(v) { return v == null ? "none" : v >= 0 ? "good" : v >= -10 ? "mid" : "bad"; }
NS.num = num; NS.signed = signed; NS.ago = ago;

/* ---------- bandiere (SVG: le emoji-bandiera non si vedono su Windows) ---------- */
var FLAGS = {
  IT: '<rect width="6" height="12" fill="#008c45"/><rect x="6" width="6" height="12" fill="#f4f5f0"/><rect x="12" width="6" height="12" fill="#cd212a"/>',
  FR: '<rect width="6" height="12" fill="#0055a4"/><rect x="6" width="6" height="12" fill="#f4f5f0"/><rect x="12" width="6" height="12" fill="#ef4135"/>',
  DE: '<rect width="18" height="4" fill="#111"/><rect y="4" width="18" height="4" fill="#dd0000"/><rect y="8" width="18" height="4" fill="#ffce00"/>',
  ES: '<rect width="18" height="12" fill="#aa151b"/><rect y="3" width="18" height="6" fill="#f1bf00"/>',
  CH: '<rect width="18" height="12" fill="#da291c"/><rect x="8" y="2.5" width="2" height="7" fill="#fff"/><rect x="5.5" y="5" width="7" height="2" fill="#fff"/>'
};
function flag(cc) { return '<svg class="flag" viewBox="0 0 18 12" role="img" aria-label="' + cc + '">' + (FLAGS[cc] || '<rect width="18" height="12" fill="#6a7d96"/>') + "</svg>"; }

/* ---------- atomi ---------- */
function snrBadge(v) {
  var c = snrCls(v), g = c === "good" ? "▲" : c === "mid" ? "●" : c === "bad" ? "▼" : "–";
  return '<span class="snr ' + c + '" title="SNR"><span aria-hidden="true">' + g + "</span>" + (v == null ? "–" : signed(v, 1) + " dB") + "</span>";
}
function battBadge(v, usb) {
  if (usb) return '<span class="batt usb">' + I("plug", 16) + "USB</span>";
  var c = v < 20 ? "low" : v < 40 ? "mid" : "";
  return '<span class="batt ' + c + '">' + I("battery", 16) + v + "%</span>";
}
function srcMark(s, size) {
  size = size || 20;
  var c = s === "radio" ? "var(--src-radio)" : s === "mqtt" ? "var(--src-mqtt)" : "var(--src-both)";
  var inner = s === "both"
    ? '<circle cx="10" cy="10" r="4" fill="none" stroke="' + c + '" stroke-width="2"/><circle cx="10" cy="10" r="8" fill="none" stroke="' + c + '" stroke-width="1.5"/>'
    : s === "mqtt"
    ? '<circle cx="10" cy="10" r="6" fill="none" stroke="' + c + '" stroke-width="2.5" stroke-dasharray="3 2.2"/>'
    : '<circle cx="10" cy="10" r="6" fill="none" stroke="' + c + '" stroke-width="2.5"/>';
  var nm = s === "radio" ? "Radio" : s === "mqtt" ? "MQTT" : "Radio e MQTT";
  return '<span class="src" title="' + nm + '"><svg width="' + size + '" height="' + size + '" viewBox="0 0 20 20" role="img" aria-label="' + nm + '">' + inner + "</svg></span>";
}
function dot(min) { return '<span class="dot ' + contactCls(min) + '" aria-hidden="true"></span>'; }
function badge(kind, text, icon) { return '<span class="badge ' + (kind || "") + '">' + (icon ? I(icon, 14) : "") + text + "</span>"; }
function btn(label, o) {
  o = o || {};
  return '<button class="btn ' + (o.k || "") + (o.cls ? " " + o.cls : "") + '"' + (o.dis ? " disabled" : "") + ">" + (o.i ? I(o.i, o.k === "icon" ? 18 : 16) : "") + (label ? "<span>" + label + "</span>" : "") + "</button>";
}
function iconBtn(i, label, k) { return '<button class="btn icon ' + (k || "") + '" aria-label="' + label + '">' + I(i, 18) + "</button>"; }
function input(ph, o) {
  o = o || {};
  return '<div class="input' + (o.err ? " err" : "") + (o.foc ? " is-focus" : "") + '"' + (o.mono ? ' style="font-family:var(--font-mono)"' : "") + ">" + (o.i ? '<span class="muted">' + I(o.i, 16) + "</span>" : "") + '<span class="grow ' + (o.val ? "" : "muted") + ' trunc">' + (o.val || ph || "") + "</span>" + (o.end || "") + "</div>";
}
function select(val, o) { o = o || {}; return '<div class="select"><span class="trunc' + (o.mono ? " mono" : "") + '">' + val + "</span>" + I("chevD", 16) + "</div>"; }
function field(label, ctrl, hint, err) { return '<div class="field"><label class="lbl">' + label + "</label>" + ctrl + (hint ? '<div class="hint' + (err ? " err" : "") + '">' + hint + "</div>" : "") + "</div>"; }
function sw(label, on) { return '<span class="switch' + (on ? " on" : "") + '" role="switch" aria-checked="' + !!on + '"><span class="trk"></span><span>' + label + "</span></span>"; }
function check(label, on, risk) { return '<span class="check' + (on ? " on" : "") + (risk ? " risk" : "") + '"><span class="bx">' + (on ? I("check", 14) : "") + "</span><span>" + label + "</span></span>"; }
function seg(items, sel, fill) { return '<div class="seg' + (fill ? " fill" : "") + '" role="tablist">' + items.map(function (t) { return '<button class="' + (t === sel ? "on" : "") + '">' + t + "</button>"; }).join("") + "</div>"; }
function chip(label, on, extra) { return '<button class="chip' + (on ? " on" : "") + '">' + (extra || "") + label + "</button>"; }
function banner(kind, title, text, act) {
  var ic = { warn: "alert", danger: "alert", ok: "check", info: "info" }[kind] || "info";
  return '<div class="banner ' + kind + '" role="' + (kind === "danger" ? "alert" : "status") + '">' + I(ic, 20) + '<div class="grow"><div class="bt">' + title + "</div>" + (text ? "<div>" + text + "</div>" : "") + "</div>" + (act || "") + "</div>";
}
function progress(p, kind) { return '<div class="progress ' + (kind || "") + '" role="progressbar" aria-valuenow="' + p + '" aria-valuemin="0" aria-valuemax="100"><i style="width:' + p + '%"></i></div>'; }
function empty(icon, title, text, act) { return '<div class="empty"><div class="ic">' + I(icon, 26) + "</div><h3>" + title + "</h3><p>" + text + "</p>" + (act || "") + "</div>"; }
function skelRows(n, h) { var o = ""; for (var i = 0; i < n; i++) o += '<div class="lrow" style="min-height:' + (h || 56) + 'px"><span class="skel" style="width:18px;height:12px"></span><div class="grow col" style="gap:6px"><span class="skel" style="width:' + (50 + (i * 17) % 35) + '%"></span><span class="skel" style="width:28%;height:9px"></span></div><span class="skel" style="width:44px"></span></div>'; return o; }
function toast(kind, text, act) { return '<div class="toast" role="status">' + I({ ok: "check", warn: "alert", danger: "alert", info: "info" }[kind], 20).replace('class="ml-ic"', 'class="ml-ic" style="color:var(--' + (kind === "info" ? "accent" : kind) + ')"') + '<span class="grow">' + text + "</span>" + (act || "") + "</div>"; }

NS.atoms = { snrBadge: snrBadge, battBadge: battBadge, srcMark: srcMark, dot: dot, badge: badge, btn: btn, input: input, select: select, field: field, sw: sw, check: check, seg: seg, chip: chip, banner: banner, progress: progress, empty: empty, toast: toast, flag: flag };

/* ---------- dati di esempio (inventati) ---------- */
var NODES = [
  { id: "!3a7f91c2", n: "Casa Ulivi", s: "ULIV", hw: "Heltec V3", role: "REPEATER", fw: "2.7.11", src: "both", min: 2, b: 84, v: 4.05, cc: "IT", x: 330, y: 300, snr: 6.5, rssi: -82, hops: 0, ch: 8.2, air: 1.1, mine: true },
  { id: "!b7c1d4e0", n: "Tetto Rosso", s: "TRSS", hw: "T-Beam", role: "CLIENT_MUTE", fw: "2.7.11", src: "radio", min: 3, b: 80, v: 3.98, cc: "IT", x: 420, y: 232, snr: 3.0, rssi: -91, hops: 1, ch: 5.4, air: 0.6, mine: true },
  { id: "!09ac5be7", n: "Nodo Duomo", s: "DUOM", hw: "RAK4631", role: "CLIENT", fw: "2.7.11", src: "both", min: 47, b: 85, v: 4.02, cc: "IT", x: 520, y: 330, snr: -3.5, rssi: -104, hops: 1, ch: 6.9, air: 0.9, mine: true },
  { id: "!6f20a1b9", n: "Passo Alto", s: "PALT", hw: "Heltec V3", role: "CLIENT", fw: "2.7.10", src: "mqtt", min: 130, b: 52, v: 3.81, cc: "IT", x: 600, y: 200, snr: -8.0, rssi: -112, hops: 2, ch: 3.1, air: 0.3, mine: true },
  { id: "!c4410d6f", n: "Ripetitore Torre", s: "RTOR", hw: "RAK4631", role: "ROUTER", fw: "2.7.11", src: "radio", min: 240, b: 84, v: 4.01, cc: "IT", x: 250, y: 190, snr: -12.5, rssi: -118, hops: 3, ch: 9.7, air: 1.8, mine: true },
  { id: "!e8d7731a", n: "Base Colli", s: "BCOL", hw: "T-Echo", role: "CLIENT", fw: "2.7.9", src: "mqtt", min: 1200, b: 14, v: 3.52, cc: "IT", x: 690, y: 320, snr: -14.0, rssi: -121, hops: 3, ch: 1.2, air: 0.1, mine: true },
  { id: "!2b94f0c8", n: "Fienile Radio", s: "FIEN", hw: "Heltec V3", role: "ROUTER", fw: "2.7.11", src: "both", min: 1, b: 83, v: 4.0, cc: "IT", x: 460, y: 410, snr: 4.5, rssi: -88, hops: 0, ch: 7.7, air: 1.3 },
  { id: "!77aa31d5", n: "Rifugio Pino", s: "RPIN", hw: "T-Beam", role: "CLIENT", fw: "2.7.11", src: "mqtt", min: 1, b: 94, v: 4.12, cc: "IT", x: 560, y: 110, snr: 1.0, rssi: -97, hops: 1, ch: 2.2, air: 0.2 },
  { id: "!1e0c85b3", n: "Campanile Est", s: "CEST", hw: "RAK4631", role: "CLIENT", fw: "2.7.11", src: "mqtt", min: 1, b: 70, v: 3.91, cc: "IT", x: 640, y: 440, snr: -2.0, rssi: -101, hops: 1, ch: 4.0, air: 0.5 },
  { id: "!d3f6620e", n: "Mulino Verde", s: "MVER", hw: "Heltec V3", role: "CLIENT", fw: "2.7.11", src: "radio", min: 1, usb: true, b: 100, v: 5.0, cc: "IT", x: 255, y: 405, snr: 5.0, rssi: -85, hops: 0, ch: 2.9, air: 0.4 },
  { id: "!5a19c7e2", n: "Chalet Lac", s: "CLAC", hw: "T-Beam", role: "CLIENT", fw: "2.7.8", src: "mqtt", min: 300, b: 61, v: 3.86, cc: "CH", x: 120, y: 120, snr: -6.0, rssi: -108, hops: 2, ch: 3.6, air: 0.4 },
  { id: "!8c33e4a1", n: "Tour du Col", s: "TCOL", hw: "Heltec V3", role: "ROUTER", fw: "2.7.11", src: "mqtt", min: 18, b: 77, v: 3.95, cc: "FR", x: 90, y: 250, snr: -9.5, rssi: -114, hops: 2, ch: 5.5, air: 0.8 },
  { id: "!a2b7090f", n: "Torre Civica", s: "TCIV", hw: "RAK4631", role: "CLIENT", fw: "2.7.11", src: "both", min: 5, b: 89, v: 4.06, cc: "IT", x: 380, y: 130, snr: 2.5, rssi: -94, hops: 1, ch: 4.8, air: 0.7 }
];
NS.nodes = NODES;
var ROLE_ICON = { ROUTER: "network", REPEATER: "network" };

/* ---------- mappa fittizia (SVG, token mappa) ---------- */
function mapSvg(o) {
  o = o || {};
  var s = '<svg class="map" viewBox="0 0 800 560" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Mappa di esempio">';
  s += '<rect width="800" height="560" fill="var(--map-water)"/>';
  s += '<path d="M240 0 C300 40 330 90 380 120 C430 150 520 140 580 170 C650 205 700 190 800 230 L800 560 L190 560 C230 500 200 440 240 380 C270 330 210 290 230 240 C250 190 200 150 220 90 C228 60 236 30 240 0 Z" fill="var(--map-land)"/>';
  s += '<path d="M0 0 L240 0 C236 30 228 60 220 90 C200 150 250 190 230 240 C210 290 270 330 240 380 C200 440 230 500 190 560 L0 560 Z" fill="var(--map-land)" opacity=".0"/>';
  s += '<path d="M470 380 q40 -18 70 4 q22 24 -10 40 q-46 14 -62 -10 q-8 -18 2 -34z" fill="var(--map-water)"/>';
  s += '<g fill="none" stroke="var(--map-road)" stroke-width="2.5" stroke-linecap="round"><path d="M240 330 C330 300 400 290 470 250 S620 200 800 230"/><path d="M380 120 C400 200 420 280 440 430 L450 560"/><path d="M300 560 C340 470 420 440 520 420 S700 380 800 340"/><path d="M520 60 C540 130 560 190 610 240"/></g>';
  s += '<g fill="none" stroke="var(--map-road)" stroke-width="1.2" opacity=".9"><path d="M250 200 L400 180 L560 120"/><path d="M280 420 L440 390 L700 470"/><path d="M600 200 L680 330 L760 300"/></g>';
  s += '<g font-family="var(--font-sans)" font-size="13" fill="var(--map-label)"><text x="395" y="318">Caserta</text><text x="30" y="500" font-style="italic" font-size="14">Golfo di Gaeta</text><text x="545" y="148">Benevento</text><text x="290" y="466">Napoli</text><text x="630" y="372">Avellino</text></g>';
  return s;
}
function nodeMarker(n, sel) {
  var c = "var(--contact-" + contactCls(n.min) + ")", sc = n.src === "radio" ? "var(--src-radio)" : n.src === "mqtt" ? "var(--src-mqtt)" : "var(--src-both)";
  var g = '<g transform="translate(' + n.x + " " + n.y + ')">';
  if (sel) g += '<circle r="19" fill="none" stroke="var(--ink)" stroke-width="2"/>';
  if (n.src === "both") g += '<circle r="14" fill="none" stroke="' + sc + '" stroke-width="1.8"/>';
  g += '<circle r="9" fill="' + c + '" stroke="' + sc + '" stroke-width="3"' + (n.src === "mqtt" ? ' stroke-dasharray="4 2.6"' : "") + "/>";
  g += '<circle r="10.7" fill="none" stroke="var(--marker-outline)" stroke-width="1" opacity=".8"/>';
  if (n.mine) g += '<path transform="translate(9 -17) scale(.55)" d="M12 2l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 16.800 6.100 20l1.200-6.500L2.500 8.900 9.100 8 12 2z" fill="var(--brand-amber)" stroke="var(--marker-outline)" stroke-width="1.5"/>';
  return g + "</g>";
}
function clusterMarker(x, y, n) {
  return '<g transform="translate(' + x + " " + y + ')"><circle r="17" fill="var(--surface-raised)" stroke="var(--accent)" stroke-width="3"/><text text-anchor="middle" y="5" font-family="var(--font-mono)" font-weight="600" font-size="13" fill="var(--ink)">' + n + "</text></g>";
}
NS.map = { svg: mapSvg, marker: nodeMarker, cluster: clusterMarker };
NS._h = { I: I, num: num, signed: signed, ago: ago, contactCls: contactCls, snrCls: snrCls, flag: flag, snrBadge: snrBadge, battBadge: battBadge, srcMark: srcMark, dot: dot, badge: badge, btn: btn, iconBtn: iconBtn, input: input, select: select, field: field, sw: sw, check: check, seg: seg, chip: chip, banner: banner, progress: progress, empty: empty, skelRows: skelRows, toast: toast, mapSvg: mapSvg, nodeMarker: nodeMarker, clusterMarker: clusterMarker, NODES: NODES };
window.MeshLens = NS;
})();
(function () {
"use strict";
var NS = window.MeshLens, H = NS._h, I = H.I;
var N = H.NODES, byId = {}; N.forEach(function (n) { byId[n.id] = n; });
var S = NS.screens = {};
var TABS = [["mappa", "Mappa", "map"], ["nodi", "Nodi", "nodes"], ["rete", "Rete", "network"], ["copertura", "Copertura", "coverage"], ["chat", "Chat", "chat"], ["radio", "Radio", "radio"], ["impostazioni", "Impostazioni", "settings"]];
var BNAV = [["mappa", "Mappa", "map"], ["nodi", "Nodi", "nodes"], ["chat", "Chat", "chat"], ["copertura", "Copertura", "coverage"], ["altro", "Altro", "more"]];

function logoMark(sz) {
  return '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 256 256" aria-hidden="true"><g stroke="var(--brand-teal)" stroke-opacity=".6" stroke-width="6" stroke-linecap="round" fill="none"><path d="M40 60 L104 36 L184 56 L220 120 M40 60 L52 150 L104 36 M52 150 L40 212"/></g><g fill="var(--brand-sky)"><circle cx="40" cy="60" r="9"/><circle cx="104" cy="36" r="9"/><circle cx="184" cy="56" r="9"/><circle cx="220" cy="120" r="9"/><circle cx="52" cy="150" r="9"/><circle cx="40" cy="212" r="9"/></g><circle cx="124" cy="128" r="58" fill="var(--brand-teal)" fill-opacity=".16" stroke="var(--brand-teal)" stroke-width="14"/><path d="M167 171 L226 230" stroke="var(--brand-teal)" stroke-width="20" stroke-linecap="round"/><path d="M98 108 L152 102 L128 156 Z" stroke="var(--brand-sky)" stroke-width="5" stroke-linejoin="round" fill="none"/><g fill="var(--brand-sky)"><circle cx="98" cy="108" r="8"/><circle cx="152" cy="102" r="8"/><circle cx="128" cy="156" r="8"/></g><circle cx="126" cy="122" r="11" fill="var(--brand-amber)"/></svg>';
}
NS.logoMark = logoMark;

/* ---------- barra superiore, navigazione ---------- */
function topbar(ctx, tab, mq) {
  var ph = ctx.vp === "phone", down = mq === "down";
  var mqtt = '<span class="dot ' + (down ? "danger" : "ok") + '" aria-hidden="true"></span>' + (down ? "MQTT non connesso" : "MQTT");
  var rate = down ? "0,0/s" : "42/s";
  if (!ph) {
    var t = '<nav class="tabs" aria-label="Sezioni">' + TABS.map(function (x) { return '<button class="tab' + (x[0] === tab ? " on" : "") + '">' + x[1] + "</button>"; }).join("") + "</nav>";
    return '<header class="top"><div class="brand">' + logoMark(28) + "<span>MeshLens</span></div>" + t +
      '<div class="status"><span class="stat" title="Stato MQTT">' + mqtt + " <b>" + rate + '</b></span><span class="stat">' + I("nodes", 16) + " Nodi <b>128</b></span><span class=\"stat\">" + I("radio", 16) + " Radio <b>2</b></span><span class=\"stat warn\">" + I("bell", 16) + " Avvisi <b>" + (ctx.alerts == null ? 2 : ctx.alerts) + '</b></span><button class="pillbtn">' + I("download", 14) + " Aggiornamento 1.1.0</button></div></header>";
  }
  return '<header class="top"><div class="brand">' + logoMark(26) + '</div><div class="status" style="margin-left:0;flex:1;justify-content:space-between"><span class="stat" aria-label="MQTT"><span class="dot ' + (down ? "danger" : "ok") + '"></span><b>' + rate + '</b></span><span class="stat" aria-label="Nodi visibili">' + I("nodes", 18) + "<b>128</b></span><span class=\"stat\" aria-label=\"Radio collegate\">" + I("radio", 18) + "<b>2</b></span><span class=\"stat warn\" aria-label=\"Avvisi\">" + I("bell", 18) + "<b>2</b></span><span class=\"stat\" aria-label=\"Aggiornamento disponibile\" style=\"color:var(--accent)\">" + I("download", 18) + "</span></div></header>";
}
function bnav(tab) {
  var cur = ["rete", "radio", "impostazioni"].indexOf(tab) >= 0 ? "altro" : tab;
  return '<nav class="bnav" aria-label="Sezioni">' + BNAV.map(function (x) { return '<button class="' + (x[0] === cur ? "on" : "") + '">' + I(x[2], 24) + "<span>" + x[1] + "</span>" + (x[0] === "altro" ? '<span class="nb">2</span>' : "") + "</button>"; }).join("") + "</nav>";
}
NS.topbar = topbar; NS.bnav = bnav;

/* ---------- guscio schermata ---------- */
function phd(title, right, back) { return '<div class="phd">' + (back ? H.iconBtn("back", "Indietro", "ghost") : "") + '<h2 class="t-md grow trunc">' + title + "</h2>" + (right || "") + "</div>"; }
S.shell = function (ctx, o) {
  var ph = ctx.vp === "phone", h = '<div class="ml frame ' + (ph ? "phone vp-phone" : "desktop") + '" data-theme="' + ctx.theme + '">';
  if (!o.bare) h += topbar(ctx, o.tab, o.mq);
  h += '<div class="main"' + (ph ? ' style="flex-direction:column"' : "") + ">";
  if (o.page) h += o.page;
  else {
    h += '<div class="mapbox"' + (ph ? ' style="flex:none;height:' + o.mapH + 'px"' : "") + ">" + o.map + "</div>";
    var hd = o.noHead ? "" : phd(o.title, o.head, o.back);
    if (!ph) h += '<aside class="panel' + (o.wide ? " wide" : "") + '"><div class="grip" title="Trascina per ridimensionare"></div>' + hd + '<div class="pbody' + (o.flush ? " flush" : "") + '">' + o.panel + "</div></aside>";
    else h += '<div class="sheet" style="position:relative;height:auto;flex:1;margin-top:-14px"><div class="gr"></div>' + hd + '<div class="pbody' + (o.flush ? " flush" : "") + '">' + o.panel + "</div></div>";
  }
  h += "</div>";
  if (ph && !o.bare) h += bnav(o.tab);
  if (o.modal) h += '<div class="modalbg">' + o.modal + "</div>";
  return h + "</div>";
};
S.mapDims = function (ctx, o) { return ctx.vp === "phone" ? { W: 378, H: o.mapH } : { W: (o.wide ? 1280 - 560 : 1280 - 380) - 2, H: 800 - 2 - 48 }; };

/* ---------- mappa composta ---------- */
function proj(W, H) { var s = Math.min(W / 800, H / 560), ox = (W - 800 * s) / 2, oy = (H - 560 * s) / 2; return { s: s, ox: ox, oy: oy, P: function (x, y) { return [ox + x * s, oy + y * s]; } }; }
var LINKS = [["!3a7f91c2", "!b7c1d4e0", 5.0], ["!3a7f91c2", "!2b94f0c8", 4.5], ["!b7c1d4e0", "!a2b7090f", 2.5], ["!3a7f91c2", "!09ac5be7", -3.5], ["!09ac5be7", "!6f20a1b9", -8.0], ["!09ac5be7", "!1e0c85b3", -2.0], ["!6f20a1b9", "!e8d7731a", -14.0], ["!3a7f91c2", "!d3f6620e", 5.0], ["!c4410d6f", "!b7c1d4e0", -12.5, 1], ["!a2b7090f", "!77aa31d5", 1.0]];
function snrColor(v) { return "var(--snr-" + (v >= 0 ? "good" : v >= -10 ? "mid" : "bad") + ")"; }
function legendHtml(ctx, pos) {
  var ph = ctx.vp === "phone";
  var r = function (c, t) { return '<div class="li"><span class="dot ' + c + '"></span>' + t + "</div>"; };
  var l = function (c, d, t) { return '<div class="li"><svg width="26" height="8" aria-hidden="true"><line x1="1" y1="4" x2="25" y2="4" stroke="var(--snr-' + c + ')" stroke-width="3" stroke-linecap="round"' + (d ? ' stroke-dasharray="6 4"' : "") + "/></svg>" + t + "</div>"; };
  var s = function (k, t) { return '<div class="li">' + H.srcMark(k, 20) + t + "</div>"; };
  if (ph) return '<div class="legend" style="' + pos + ';min-width:0;flex-direction:row;align-items:center;gap:8px;padding:8px 12px">' + I("layers", 16) + " Legenda " + I("chevU", 16) + "</div>";
  return '<div class="legend" style="' + pos + '"><h4>Ultimo contatto</h4>' + r("fresh", "Meno di 2 h") + r("recent", "Meno di 24 h") + r("old", "Oltre 24 h") + "<h4>SNR del collegamento</h4>" + l("good", 0, "0 dB o più") + l("mid", 0, "Da −10 a 0 dB") + l("bad", 0, "Sotto −10 dB") + l("none", 1, "Traceroute (tratteggio)") + "<h4>Fonte</h4>" + s("radio", "Radio") + s("mqtt", "MQTT") + s("both", "Radio + MQTT") + "</div>";
}
S.mapView = function (ctx, o) {
  var d = S.mapDims(ctx, o), W = d.W, Hh = d.H, p = proj(W, Hh), ph = ctx.vp === "phone";
  var s = '<svg class="map" viewBox="0 0 ' + W + " " + Hh + '" width="100%" height="100%" preserveAspectRatio="xMinYMin slice" role="img" aria-label="Mappa di esempio con i nodi">';
  s += '<rect width="' + W + '" height="' + Hh + '" fill="var(--map-water)"/><g transform="translate(' + p.ox + " " + p.oy + ") scale(" + p.s + ')">';
  s += '<path d="M240 -1500 L240 0 C300 40 330 90 380 120 C430 150 520 140 580 170 C650 205 700 190 800 230 L2400 230 L2400 2400 L190 2400 L190 560 C230 500 200 440 240 380 C270 330 210 290 230 240 C250 190 200 150 220 90 C228 60 236 30 240 0 Z" fill="var(--map-land)"/>';
  s += '<path d="M470 380 q40 -18 70 4 q22 24 -10 40 q-46 14 -62 -10 q-8 -18 2 -34z" fill="var(--map-water)"/>';
  s += '<g fill="none" stroke="var(--map-road)" stroke-width="3" stroke-linecap="round"><path d="M240 330 C330 300 400 290 470 250 S620 200 800 230 L1200 250"/><path d="M380 120 C400 200 420 280 440 430 L450 700"/><path d="M300 700 C340 470 420 440 520 420 S700 380 800 340 L1200 300"/><path d="M520 -80 C540 130 560 190 610 240"/></g>';
  s += '<g fill="none" stroke="var(--map-road)" stroke-width="1.4"><path d="M250 200 L400 180 L560 120"/><path d="M280 420 L440 390 L700 470"/><path d="M600 200 L680 330 L760 300"/></g>';
  s += '<g font-family="var(--font-sans)" font-size="14" fill="var(--map-label)"><text x="395" y="318">Caserta</text><text x="40" y="500" font-style="italic" font-size="15">Golfo di Gaeta</text><text x="545" y="148">Benevento</text><text x="330" y="500">Napoli</text><text x="630" y="372">Avellino</text></g></g>';
  var nodes = o.empty ? [] : N, P = function (n) { return p.P(n.x, n.y); }, i, a, b, pa, pb;
  if (o.cov) {
    var base = p.P(300, 330), pts = o.cov, path = "M" + base.join(" ");
    pts.forEach(function (q) { var c = p.P(q.x, q.y); path += " L" + c[0] + " " + c[1]; });
    s += '<path d="' + path + '" fill="none" stroke="var(--ink-muted)" stroke-width="2" stroke-dasharray="1 5" stroke-linecap="round"/>';
    pts.forEach(function (q) { var c = p.P(q.x, q.y); if (q.miss) s += '<g transform="translate(' + c[0] + " " + c[1] + ')"><circle r="6" fill="var(--surface)" stroke="var(--snr-none)" stroke-width="2"/><path d="M-3 -3 L3 3 M3 -3 L-3 3" stroke="var(--snr-none)" stroke-width="1.6"/></g>'; else s += '<circle cx="' + c[0] + '" cy="' + c[1] + '" r="6" fill="' + snrColor(q.snr) + '" stroke="var(--marker-outline)" stroke-width="1.5"/>'; });
    if (o.covMax) { var m = p.P(o.covMax.x, o.covMax.y); s += '<line x1="' + base[0] + '" y1="' + base[1] + '" x2="' + m[0] + '" y2="' + m[1] + '" stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="5 4"/>'; }
    s += '<g transform="translate(' + base[0] + " " + base[1] + ')"><circle r="12" fill="var(--ink)" stroke="var(--brand-amber)" stroke-width="3.5"/><circle r="3.5" fill="var(--bg)"/></g>';
  }
  if (o.links && !o.empty) LINKS.forEach(function (l) { pa = P(byId[l[0]]); pb = P(byId[l[1]]); s += '<line x1="' + pa[0] + '" y1="' + pa[1] + '" x2="' + pb[0] + '" y2="' + pb[1] + '" stroke="' + snrColor(l[2]) + '" stroke-width="3" stroke-linecap="round"' + (l[3] ? ' stroke-dasharray="8 6"' : "") + ' opacity=".95"/>'; });
  if (o.tracks && !o.empty) { var tr = [[520, 330], [505, 342], [498, 360], [512, 372], [535, 366], [548, 348]].map(function (q) { return p.P(q[0], q[1]); }); s += '<polyline points="' + tr.map(function (q) { return q.join(","); }).join(" ") + '" fill="none" stroke="var(--ink-muted)" stroke-width="2" stroke-dasharray="2 4" stroke-linecap="round"/>'; tr.slice(1).forEach(function (q, k) { s += '<circle cx="' + q[0] + '" cy="' + q[1] + '" r="3.5" fill="var(--ink-muted)" opacity="' + (0.35 + k * 0.1) + '"/>'; }); }
  if (!o.empty && !o.noMarkers) {
    nodes.forEach(function (n) {
      if (n.id === "!5a19c7e2" || n.id === "!8c33e4a1") return;
      var c = P(n), approx = n.id === "!6f20a1b9" || n.id === "!e8d7731a";
      if (approx) s += '<circle cx="' + c[0] + '" cy="' + c[1] + '" r="' + (34 * Math.max(p.s, .6)) + '" fill="var(--src-mqtt)" fill-opacity=".13" stroke="var(--src-mqtt)" stroke-width="1.5" stroke-dasharray="4 4"/>';
      var nn = o.stale ? Object.assign({}, n, { min: 3000 }) : n;
      s += '<g transform="translate(' + c[0] + " " + c[1] + ')">' + H.nodeMarker(Object.assign({}, nn, { x: 0, y: 0 }), o.sel === n.id).replace(/^<g transform="translate\(0 0\)">/, "<g>") + "</g>";
    });
    var cc = p.P(105, 185); s += '<g transform="translate(' + cc[0] + " " + cc[1] + ')"><circle r="17" fill="var(--surface-raised)" stroke="var(--accent)" stroke-width="3"/><text text-anchor="middle" y="5" font-family="var(--font-mono)" font-weight="600" font-size="14" fill="var(--ink)">2</text></g>';
  }
  s += "</svg>";
  var h = s;
  var zoom = '<div class="mapctl" style="right:12px;top:12px"><button aria-label="Ingrandisci">' + I("plus", 18) + '</button><button aria-label="Riduci">' + I("minus", 18) + "</button></div>";
  h += zoom;
  if (ph && Hh >= 270) h += '<div class="mapctl" style="right:12px;top:' + (12 + 2 * (44) + 14) + 'px"><button aria-label="Collegamenti" style="color:var(--accent)">' + I("route", 18) + '</button><button aria-label="Tracce">' + I("clock", 18) + '</button><button aria-label="Copertura">' + I("coverage", 18) + "</button></div>";
  if (o.legend) h += legendHtml(ctx, ph ? "left:10px;bottom:24px" : "left:12px;bottom:26px");
  if (o.offline) h += '<div class="maptag" style="left:12px;top:12px">' + I("cloudoff", 16) + " Mappa offline" + (ph ? "" : ' <span class="muted">· copia del 12 nov</span>') + "</div>";
  if (o.tag) h += '<div class="maptag" style="left:12px;top:12px">' + o.tag + "</div>";
  h += '<div class="attr">© OpenStreetMap contributors · Protomaps</div>';
  if (o.popup) { var q = P(byId[o.popup]); h += o.popupHtml.replace("%L", Math.max(8, Math.min(W - 268, q[0] - 130))).replace("%T", q[1] - (ph ? 190 : 176) - 14); }
  if (o.overlay) h += '<div class="mapov">' + o.overlay + "</div>";
  return h;
};
S.popup = function (n, ph) {
  return '<div class="popup" style="left:%Lpx;top:%Tpx"><div class="row"><span class="grow nm trunc">' + n.n + "</span>" + H.srcMark(n.src) + '</div><div class="sub mono">' + n.id + " · " + n.role + '</div><div class="row wrap" style="gap:12px">' + H.dot(n.min) + "<span>" + H.ago(n.min) + "</span>" + H.battBadge(n.b, n.usb) + H.snrBadge(n.snr) + '</div><div class="row"><button class="btn primary grow" style="height:' + (ph ? 44 : 30) + 'px">Dettaglio</button><button class="btn" style="height:' + (ph ? 44 : 30) + 'px">' + I("route", 14) + " Percorso</button></div></div>";
};

/* ---------- 1. accesso ---------- */
var COMPAT = '<div class="compat"><span class="slot" aria-hidden="true">LOGO</span><span>Compatibile con Meshtastic®</span></div>';
NS.compatBadge = COMPAT;
S.accesso = {
  label: "Accesso con PIN", states: [["accesso", "Accesso"], ["primo", "Primo avvio"], ["errore", "PIN errato"], ["blocco", "Bloccato"], ["verifica", "Verifica"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", b = "";
    var head = '<div class="col" style="align-items:center;gap:12px;text-align:center">' + logoMark(ph ? 72 : 88) + '<div><h1 class="t-lg">MeshLens</h1><p class="muted">Osserva e gestisci le tue reti Meshtastic</p></div></div>';
    var body = "";
    if (st === "primo") body = '<div class="col" style="gap:16px"><h2 class="t-md">Scegli un PIN</h2><p class="muted">Serve per aprire MeshLens dai dispositivi sulla tua Wi-Fi. Da 4 a 8 cifre.</p>' + H.field("Nuovo PIN", H.input("", { val: "••••••", foc: 1, mono: 1, end: I("eye", 18) })) + H.field("Ripeti il PIN", H.input("", { val: "••••", mono: 1 }), "I due PIN non coincidono ancora.", false) + H.btn("Salva il PIN e continua", { k: "primary lg block" }) + "</div>";
    else if (st === "blocco") body = '<div class="col" style="gap:16px"><h2 class="t-md">Accesso bloccato</h2>' + H.banner("warn", "Troppi tentativi errati", "Riprova tra <b class=\"mono\">04:32</b>. Il blocco serve a proteggere la tua rete.") + H.progress(46, "warn") + H.field("PIN", '<div class="input is-disabled">' + '<span class="grow muted">Disabilitato fino alla fine del blocco</span>' + I("lock", 16) + "</div>") + H.btn("Accedi", { k: "primary lg block", dis: 1 }) + "</div>";
    else if (st === "verifica") body = '<div class="col" style="gap:16px"><h2 class="t-md">Accedi</h2>' + H.field("PIN", H.input("", { val: "••••••", mono: 1 })) + '<button class="btn primary lg block" disabled>' + I("spinner", 16) + " Verifico…</button></div>";
    else body = '<div class="col" style="gap:16px"><h2 class="t-md">Accedi</h2>' + H.field("PIN", H.input("", { val: st === "errore" ? "••••••" : "•••", foc: st !== "errore", err: st === "errore", mono: 1, end: I("eye", 18) }), st === "errore" ? "PIN errato. Hai ancora 2 tentativi." : "Inserisci il PIN scelto al primo avvio.", st === "errore") + H.btn("Accedi", { k: "primary lg block" }) + "</div>";
    var foot = '<div class="col" style="align-items:center;gap:10px;text-align:center">' + COMPAT + '<p class="caption" style="max-width:340px">MeshLens non è affiliato al progetto Meshtastic. Meshtastic® è un marchio registrato di Meshtastic LLC.</p></div>';
    return '<div class="ml frame ' + (ph ? "phone vp-phone" : "desktop") + '" data-theme="' + ctx.theme + '"><div class="login"><div class="box">' + head + '<div class="card">' + body + "</div>" + foot + "</div></div></div>";
  }
};

/* ---------- 2. mappa ---------- */
function layerRow(i, t, on, sub) { return '<div class="row" style="min-height:44px">' + I(i, 18) + '<div class="grow"><div class="nm">' + t + "</div>" + (sub ? '<div class="sub">' + sub + "</div>" : "") + "</div>" + H.sw("", on) + "</div>"; }
S.mappa = {
  label: "Mappa", states: [["normale", "Normale"], ["offline", "Mappa offline"], ["vuoto", "Vuoto"], ["caricamento", "Caricamento"], ["errore", "Errore MQTT"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", sel = byId["!09ac5be7"];
    var o = { links: true, tracks: true, legend: true, sel: sel.id, mapH: ph ? 300 : 0, popup: sel.id, popupHtml: S.popup(sel, ph) };
    var panel, mq;
    var lay = '<div class="sect"><div class="shd"><h3 class="t-sm">Livelli</h3></div><div class="col" style="gap:0">' + layerRow("route", "Collegamenti", 1, "Linee colorate per SNR") + layerRow("clock", "Tracce storiche", 1, "Ultimi spostamenti dei nodi mobili") + layerRow("coverage", "Copertura", 0, "Prove Range Test salvate") + "</div></div>";
    var fonte = '<div class="sect"><h3 class="t-sm">Fonte</h3><div class="chips">' + H.chip("Radio", 1, H.srcMark("radio", 16)) + H.chip("MQTT", 1, H.srcMark("mqtt", 16)) + H.chip("Entrambe", 1, H.srcMark("both", 16)) + "</div></div>";
    var cnt = '<div class="sect"><h3 class="t-sm">Nodi sulla mappa</h3><div class="stats"><div class="s"><div class="caption">Visibili</div><div class="n">128</div></div><div class="s"><div class="caption">Con radio</div><div class="n">41</div></div><div class="s"><div class="caption">Senza posizione</div><div class="n">9</div></div></div></div>';
    panel = lay + fonte + cnt;
    if (ph) { o.popup = null; panel = '<div class="card flat" style="padding:12px"><div class="row"><span class="grow nm">Nodo Duomo</span>' + H.srcMark("both") + '</div><div class="sub mono">!09ac5be7 · CLIENT</div><div class="row wrap" style="gap:12px;margin:8px 0">' + H.dot(47) + "<span>47 min fa</span>" + H.battBadge(85) + H.snrBadge(-3.5) + '</div><div class="row">' + H.btn("Dettaglio", { k: "primary" }) + H.btn("Percorso", { i: "route" }) + "</div></div>" + panel; }
    if (st === "offline") { o.offline = true; }
    if (st === "vuoto") { o.empty = true; o.popup = null; o.legend = false; o.overlay = '<div class="card">' + H.empty("map", "Ancora nessun nodo", "Collega una radio dalla scheda Radio, oppure attendi il traffico pubblico MQTT: i nodi compariranno qui.", H.btn("Collega una radio", { k: "primary", i: "radio" })) + "</div>"; panel = lay.replace(/class="switch on"/g, 'class="switch"') + fonte + '<div class="sect">' + H.empty("nodes", "Nessun dato da mostrare", "I contatori appariranno con i primi nodi.") + "</div>"; }
    if (st === "caricamento") { o.empty = true; o.popup = null; o.legend = false; o.overlay = '<div class="card row" style="gap:12px">' + I("spinner", 22) + '<div><div class="nm">Carico i nodi…</div><div class="sub">Lettura dello storico locale</div></div></div>'; panel = '<div class="col"><span class="skel" style="width:40%"></span><span class="skel tall"></span><span class="skel tall"></span><span class="skel tall"></span><span class="skel" style="width:30%"></span><span class="skel tall"></span></div>'; }
    if (st === "errore") { mq = "down"; o.stale = true; o.popup = null; o.tag = I("alert", 16) + " Dati fermi a 4 min fa"; panel = H.banner("danger", "MQTT non raggiungibile", "Il broker non risponde. Mostro gli ultimi dati ricevuti e riprovo tra 10 s.", "") + '<div class="row">' + H.btn("Riprova ora", { i: "refresh" }) + H.btn("Apri impostazioni MQTT", { k: "ghost" }) + "</div>" + lay + fonte; }
    return S.shell(ctx, { tab: "mappa", mq: mq, map: S.mapView(ctx, o), mapH: o.mapH, title: "Mappa", panel: panel, noHead: ph });
  }
};

/* ---------- 3. nodi ---------- */
function nodeRow(n, sel, ph) {
  return '<div class="lrow' + (sel ? " sel" : "") + '">' + H.flag(n.cc) + '<div class="grow"><div class="nm trunc">' + n.n + '</div><div class="sub mono trunc">' + n.id + " · " + n.role + "</div></div>" +
    '<div class="row" style="gap:6px;width:' + (ph ? 88 : 78) + 'px;justify-content:flex-end;flex:none">' + H.dot(n.min) + '<span class="' + (ph ? "" : "caption") + '" style="white-space:nowrap">' + H.ago(n.min) + "</span></div>" +
    '<div style="width:' + (ph ? 62 : 54) + 'px;flex:none;text-align:right">' + H.battBadge(n.b, n.usb) + "</div>" + H.srcMark(n.src) + "</div>";
}
S.nodi = {
  label: "Nodi", states: [["normale", "Normale"], ["vuoto", "Nessun risultato"], ["caricamento", "Caricamento"], ["errore", "Errore"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", rows = N.slice().sort(function (a, b) { return a.min - b.min; });
    var filt = '<div class="col" style="padding:' + (ph ? "0 16px" : "16px 16px 0") + ';gap:10px">' + H.input("Cerca nome o id…", { i: "search", val: st === "vuoto" ? "zzz" : "" }) +
      '<div class="row wrap">' + H.seg(["Tutte", "Radio", "MQTT"], "Tutte") + H.seg(["2 h", "24 h", "7 g"], st === "vuoto" ? "2 h" : "24 h") + "</div>" +
      '<div class="row wrap">' + '<div style="width:' + (ph ? 150 : 150) + 'px">' + '<div class="select"><span class="row" style="gap:4px">' + H.flag("IT") + H.flag("FR") + '<span class="trunc">Nazioni</span></span>' + I("chevD", 16) + "</div></div>" + '<div style="width:150px">' + H.select("Tutte le radio") + "</div>" + '<div style="width:' + (ph ? 120 : 120) + 'px">' + H.select("Ruolo") + "</div></div></div>";
    var cnt = '<div class="row" style="padding:12px 16px 8px"><span class="lbl grow">' + (st === "vuoto" ? "0 di 128 nodi" : st === "caricamento" ? "Carico…" : "41 di 128 nodi") + "</span>" + H.btn("Azzera", { k: "ghost", i: "x" }) + "</div>";
    var list;
    if (st === "vuoto") list = H.empty("search", "Nessun nodo corrisponde", "Prova ad allargare l’ultimo contatto o a togliere un filtro.", H.btn("Azzera i filtri", { i: "refresh" }));
    else if (st === "caricamento") list = H.skelRows(9, ph ? 60 : 52);
    else if (st === "errore") list = '<div style="padding:16px">' + H.banner("danger", "Impossibile leggere i nodi", "Il servizio locale di MeshLens non risponde.", "") + '<div style="margin-top:12px">' + H.btn("Riprova", { i: "refresh" }) + "</div></div>";
    else list = rows.map(function (n, i) { return nodeRow(n, n.id === "!09ac5be7", ph); }).join("");
    var o = { links: false, tracks: false, legend: false, mapH: ph ? 190 : 0, sel: "!09ac5be7" };
    if (st === "caricamento") o.noMarkers = true;
    return S.shell(ctx, { tab: "nodi", map: S.mapView(ctx, o), mapH: o.mapH, title: "Nodi", head: H.btn("Collega", { k: "ghost", i: "plus" }), noHead: ph, panel: filt + cnt + '<div class="sep"></div>' + '<div style="margin:0 0 0">' + list + "</div>", flush: true });
  }
};

/* ---------- grafico a linee ---------- */
function series(n, a, b, seed) { var o = []; for (var i = 0; i < n; i++) { var t = i / (n - 1); o.push(a + (b - a) * t + Math.sin(i * 1.7 + seed) * (Math.abs(b - a) * 0.12) + Math.sin(i * 0.5 + seed) * (Math.abs(b - a) * 0.08)); } return o; }
S.chart = function (ctx, o) {
  o = o || {};
  var w = ctx.vp === "phone" ? 346 : o.w || 528, h = ctx.vp === "phone" ? 200 : 180, L = 34, R = 34, T = 10, B = 22, iw = w - L - R, ih = h - T - B;
  var bat = o.empty ? [] : series(48, 91, 52, 1), vol = o.empty ? [] : series(48, 4.12, 3.78, 2.3);
  var X = function (i, n) { return L + (iw * i) / (n - 1); }, YB = function (v) { return T + ih * (1 - v / 100); }, YV = function (v) { return T + ih * (1 - (v - 3.7) / 0.5); };
  var pb = bat.map(function (v, i) { return (i ? "L" : "M") + X(i, 48).toFixed(1) + " " + YB(v).toFixed(1); }).join(" "), pv = vol.map(function (v, i) { return (i ? "L" : "M") + X(i, 48).toFixed(1) + " " + YV(v).toFixed(1); }).join(" ");
  var s = '<svg class="chart" viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="Batteria e tensione">';
  [0, 25, 50, 75, 100].forEach(function (v) { s += '<line x1="' + L + '" x2="' + (w - R) + '" y1="' + YB(v) + '" y2="' + YB(v) + '" stroke="var(--line)"/><text x="' + (L - 6) + '" y="' + (YB(v) + 4) + '" text-anchor="end">' + v + "%</text>"; });
  [3.7, 3.95, 4.2].forEach(function (v) { s += '<text x="' + (w - R + 6) + '" y="' + (YV(v) + 4) + '">' + String(v).replace(".", ",") + "V</text>"; });
  var lab = ctx.vp === "phone" ? ["7 g fa", "3 g fa", "ora"] : ["7 giorni fa", "3 giorni fa", "ora"];
  s += '<text x="' + L + '" y="' + (h - 4) + '">' + lab[0] + '</text><text x="' + (L + iw / 2) + '" y="' + (h - 4) + '" text-anchor="middle">' + lab[1] + '</text><text x="' + (w - R) + '" y="' + (h - 4) + '" text-anchor="end">' + lab[2] + "</text>";
  s += '<line x1="' + L + '" x2="' + (w - R) + '" y1="' + YB(20) + '" y2="' + YB(20) + '" stroke="var(--danger)" stroke-width="1.5" stroke-dasharray="5 4"/>';
  if (!o.empty) s += '<path d="' + pb + '" fill="none" stroke="var(--ok)" stroke-width="2.2" stroke-linejoin="round"/><path d="' + pv + '" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-dasharray="1 0" stroke-linejoin="round" opacity=".95"/>';
  else s += '<text x="' + (w / 2) + '" y="' + (h / 2) + '" text-anchor="middle" style="font-family:var(--font-sans);font-size:13px">Nessun dato di batteria in questo periodo</text>';
  return s + "</svg>" + '<div class="legrow"><span><i class="sw" style="border-color:var(--ok)"></i>Batteria %</span><span><i class="sw" style="border-color:var(--accent)"></i>Tensione V</span><span><i class="sw" style="border-color:var(--danger);border-top-style:dashed"></i>Soglia avviso 20%</span></div>';
};

/* ---------- 4. dettaglio nodo ---------- */
function hop(n, snr, last) { return '<span class="chip" style="cursor:default;height:30px">' + n + "</span>" + (last ? "" : '<span class="row" style="gap:4px;color:var(--ink-muted)">' + I("chevR", 14) + H.snrBadge(snr) + I("chevR", 14) + "</span>"); }
S.nodo = {
  label: "Dettaglio nodo", states: [["normale", "Normale"], ["traceroute", "Traceroute in corso"], ["errore", "Traceroute fallito"], ["vuoto", "Senza telemetria"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", n = byId["!09ac5be7"];
    var head = '<div class="col" style="gap:10px"><div class="row" style="align-items:flex-start"><div class="grow"><h2 class="t-lg">' + n.n + '</h2><div class="row wrap" style="gap:8px;margin-top:2px"><span class="mono muted">' + n.id + "</span>" + H.flag("IT") + '<span class="muted">Italia</span></div></div><button class="btn icon" aria-label="Nodo preferito: Mio nodo" style="color:var(--brand-amber)">' + I("star", 18).replace('fill="none"', 'fill="currentColor"') + "</button></div>" +
      '<div class="row wrap">' + H.badge("info", n.role) + H.badge("", n.hw) + H.badge("", "fw " + n.fw) + H.badge("", "Mio nodo", "star") + '<span class="row" style="gap:4px">' + H.srcMark("both") + '<span class="caption">Radio + MQTT</span></span></div>' +
      '<div class="row wrap">' + H.btn("Messaggio diretto", { k: "primary", i: "chat" }) + H.btn("Configura", { i: "settings" }) + H.btn("Mostra percorso", { i: "route" }) + "</div></div>";
    var info = '<div class="sect"><h3 class="t-sm">Stato</h3><div class="kv"><div><div class="k">Ultimo contatto</div><div class="v row" style="gap:6px">' + H.dot(n.min) + H.ago(n.min) + '</div></div><div><div class="k">Batteria</div><div class="v">' + H.battBadge(n.b) + ' <span class="mono muted">· ' + H.num(n.v, 2) + ' V</span></div></div><div><div class="k">Posizione</div><div class="v mono">41,0732° N, 14,3340° E</div></div><div><div class="k">Precisione</div><div class="v row" style="gap:6px">' + H.badge("warn", "Approssimata ±730 m", "alert") + '</div></div><div><div class="k">Utilizzo del canale</div><div class="v mono">' + H.num(n.ch, 1) + ' %</div></div><div><div class="k">Airtime TX</div><div class="v mono">' + H.num(n.air, 1) + " %</div></div></div></div>";
    var heard = '<div class="sect"><h3 class="t-sm">Sentito da</h3><div class="card flat" style="padding:0">' +
      [["Radio-Casa", "usb", -3.5, -104, 1], ["Radio-Portatile", "bt", -9.0, -113, 2]].map(function (r) { return '<div class="lrow">' + I(r[1], 18) + '<div class="grow"><div class="nm">' + r[0] + '</div><div class="sub">' + r[4] + (r[4] === 1 ? " salto" : " salti") + "</div></div>" + H.snrBadge(r[2]) + '<span class="mono muted" style="width:76px;text-align:right">' + H.signed(r[3]) + " dBm</span></div>"; }).join("") +
      '<div class="lrow" style="border-bottom:0">' + I("globe", 18) + '<div class="grow"><div class="nm">Gateway MQTT</div><div class="sub mono">!b7c1d4e0 · !e2a09c11 · !77aa31d5</div></div>' + H.badge("", "3") + "</div></div></div>";
    var chart = '<div class="sect"><div class="row"><h3 class="t-sm grow">Telemetria</h3>' + H.seg(["24 h", "7 g", "30 g"], "7 g") + "</div>" + S.chart(ctx, { empty: st === "vuoto", w: 528 }) + "</div>";
    var tr;
    if (st === "traceroute") tr = '<div class="sect"><h3 class="t-sm">Traceroute</h3><div class="card"><div class="row">' + I("spinner", 18) + '<div class="grow"><div class="nm">In attesa di risposta…</div><div class="sub">Può richiedere fino a 60 secondi</div></div><span class="mono">23 s</span></div><div style="margin:12px 0 4px">' + H.progress(38) + '</div><div class="row" style="justify-content:flex-end;margin-top:8px">' + H.btn("Annulla", { i: "x" }) + "</div></div></div>";
    else if (st === "errore") tr = '<div class="sect"><h3 class="t-sm">Traceroute</h3>' + H.banner("danger", "Nessuna risposta entro 60 s", "Il nodo potrebbe essere fuori portata o spento. Riprova più tardi.", H.btn("Riprova", { i: "refresh" })) + "</div>";
    else tr = '<div class="sect"><div class="row"><h3 class="t-sm grow">Traceroute</h3>' + H.btn("Avvia traceroute", { i: "route" }) + '</div><div class="card flat col" style="gap:12px"><div class="lbl">Andata · 3 salti</div><div class="row wrap" style="gap:6px">' + hop("Radio-Casa", 5.5) + hop("Tetto Rosso", -3.0) + hop("Nodo Duomo", 0, 1) + '</div><div class="lbl">Ritorno · 3 salti</div><div class="row wrap" style="gap:6px">' + hop("Nodo Duomo", -4.0) + hop("Tetto Rosso", 4.5) + hop("Radio-Casa", 0, 1) + '</div><div class="caption">Eseguito 12 min fa · 4 traceroute nello storico</div></div></div>';
    var o = { links: true, tracks: true, legend: false, mapH: ph ? 170 : 0, sel: n.id };
    return S.shell(ctx, { tab: "nodi", map: S.mapView(ctx, o), mapH: o.mapH, title: "Dettaglio nodo", back: true, wide: true, noHead: false, panel: head + '<div class="sep"></div>' + info + heard + chart + tr });
  }
};
})();
(function () {
"use strict";
var NS = window.MeshLens, H = NS._h, I = H.I, S = NS.screens, N = H.NODES;
function pageHd(title, right, sub) { return '<div class="row wrap" style="gap:12px"><div class="grow"><h1 class="t-lg">' + title + "</h1>" + (sub ? '<p class="muted">' + sub + "</p>" : "") + "</div>" + (right || "") + "</div>"; }
function shellPage(ctx, tab, inner, narrow, modal, mq) { return S.shell(ctx, { tab: tab, page: '<div class="page' + (narrow ? " narrow" : "") + '">' + inner + "</div>", modal: modal, mq: mq }); }

/* ---------- 5. rete ---------- */
function reteTable(rows, ph) {
  var th = function (t, c, s) { return '<th class="' + (c || "") + (s ? " sorted" : "") + '">' + t + (s ? I("chevD", 14) : I("sort", 14)) + "</th>"; };
  var h = '<div class="tblwrap"><table class="tbl"><thead><tr><th class="fix" style="min-width:' + (ph ? 150 : 190) + 'px">Nodo' + I("sort", 14) + "</th>" + th("Ultimo contatto", "", 1) + th("Ruolo") + th("Firmware") + th("Batteria") + th("Tensione", "num") + th("SNR") + th("Salti", "num") + th("Uso canale", "num") + th("Airtime", "num") + "</tr></thead><tbody>";
  rows.forEach(function (n, i) {
    h += '<tr class="' + (i === 2 ? "sel" : "") + '"><td class="fix"><span class="row" style="gap:8px">' + H.flag(n.cc) + '<span class="nm">' + n.n + "</span></span></td><td>" + '<span class="row" style="gap:6px">' + H.dot(n.min) + H.ago(n.min) + "</span></td><td><span class=\"role\">" + n.role + '</span></td><td class="mono">' + n.fw + "</td><td>" + H.battBadge(n.b, n.usb) + '</td><td class="num">' + H.num(n.v, 2) + " V</td><td>" + H.snrBadge(n.snr) + '</td><td class="num">' + n.hops + '</td><td class="num">' + H.num(n.ch, 1) + ' %</td><td class="num">' + H.num(n.air, 1) + " %</td></tr>";
  });
  return h + "</tbody></table></div>";
}
S.rete = {
  label: "Rete", states: [["normale", "Normale"], ["vuoto", "Nessun nodo seguito"], ["caricamento", "Caricamento"], ["errore", "Errore"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", mine = N.filter(function (n) { return n.mine; }).sort(function (a, b) { return a.min - b.min; });
    var hd = pageHd("Rete", H.seg(["Miei nodi", "Tutti i nodi"], "Miei nodi"));
    var alerts = '<div class="banner warn" role="status">' + I("alert", 20) + '<div class="grow"><div class="bt">2 avvisi attivi</div><div>Batteria bassa su Base Colli e nodo silenzioso da 20 h.</div></div>' + H.btn("Vedi", { k: "ghost" }) + "</div>" +
      '<div class="card flat" style="padding:0"><div class="lrow">' + I("battery", 20).replace("ml-ic", "ml-ic\" style=\"color:var(--danger)") + '<div class="grow"><div class="nm">Batteria bassa · Base Colli</div><div class="sub">14% (soglia 20%) · da 35 min</div></div>' + H.btn("Apri nodo", { k: "ghost" }) + '</div><div class="lrow" style="border-bottom:0">' + I("clock", 20).replace("ml-ic", "ml-ic\" style=\"color:var(--warn)") + '<div class="grow"><div class="nm">Nodo silenzioso · Base Colli</div><div class="sub">Nessun contatto da 20 h (soglia 6 h)</div></div>' + H.btn("Apri nodo", { k: "ghost" }) + "</div></div>";
    var body;
    if (st === "vuoto") body = '<div class="card flat">' + H.empty("star", "Nessun nodo seguito", "Apri un nodo e premi la stella per segnarlo come “Mio nodo”: lo ritroverai qui con batteria, SNR e avvisi.", H.btn("Vedi tutti i nodi", { i: "nodes" })) + "</div>";
    else if (st === "caricamento") body = '<div class="card flat" style="padding:0">' + H.skelRows(7, 52) + "</div>";
    else if (st === "errore") body = H.banner("danger", "Impossibile leggere la rete", "Il servizio locale non risponde. I valori mostrati potrebbero essere vecchi.", H.btn("Riprova", { i: "refresh" })) + reteTable(mine.slice(0, 3), ph);
    else body = alerts + reteTable(mine, ph);
    return shellPage(ctx, "rete", hd + body);
  }
};

/* ---------- 6. chat ---------- */
function msg(who, text, st, me, ch) {
  var stI = { invio: ["clock", "In invio"], inviato: ["check", "Inviato"], consegnato: ["check2", "Consegnato"], fallito: ["alert", "Non consegnato"] }[st];
  var meta = '<span class="meta">' + (me ? "" : '<b style="color:var(--ink);font-weight:600">' + who + "</b>") + (ch ? '<span class="tag">' + ch + "</span>" : "") + "<span>" + (me ? "" : "") + "14:2" + (text.length % 9) + "</span>" + (stI ? '<span class="row" style="gap:3px;color:' + (st === "fallito" ? "var(--danger)" : "inherit") + '">' + I(stI[0], 14) + stI[1] + "</span>" : "") + "</span>";
  return '<div class="msg' + (me ? " me" : "") + (st === "fallito" ? " fail" : "") + '"><div class="bub">' + text + "</div>" + meta + (st === "fallito" ? '<span class="row" style="gap:6px">' + H.btn("Riprova", { k: "ghost", i: "refresh" }) + "</span>" : "") + "</div>";
}
function clist() {
  var it = function (i, t, sub, on, n) { return '<div class="lrow' + (on ? " sel" : "") + '">' + I(i, 18) + '<div class="grow"><div class="nm trunc">' + t + '</div><div class="sub trunc">' + sub + "</div></div>" + (n ? '<span class="nbadge" style="background:var(--accent);color:var(--on-accent)">' + n + "</span>" : "") + "</div>"; };
  return '<aside class="clist"><div class="phd"><h2 class="t-md grow">Chat</h2>' + H.iconBtn("plus", "Nuovo messaggio", "ghost") + '</div><div style="overflow:hidden"><div class="lbl" style="padding:12px 16px 4px">Canali · Radio-Casa</div>' + it("chat", "Primario", "LongFast · Tetto Rosso: ricevuto", 1, 2) + it("chat", "Emergenza", "Nessun messaggio", 0) + '<div class="lbl" style="padding:12px 16px 4px">Messaggi diretti</div>' + it("user", "Tetto Rosso", "Ok, ci sentiamo alle 18", 0) + it("user", "Nodo Duomo", "Test portata fatto", 0) + '<div class="lbl" style="padding:12px 16px 4px">Pubblico</div>' + it("globe", "Pubblico (MQTT)", "Sola lettura · 214 messaggi/h", 0) + "</div></aside>";
}
S.chat = {
  label: "Chat", states: [["normale", "Canale"], ["pubblico", "Pubblico (MQTT)"], ["vuoto", "Vuoto"], ["caricamento", "Caricamento"], ["errore", "Radio non collegata"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", pub = st === "pubblico", err = st === "errore";
    var title = pub ? "Pubblico (MQTT)" : "Primario", sub = pub ? "Traffico pubblico · sola lettura" : "LongFast · 3 nodi sentiti";
    var from = '<div class="row wrap" style="gap:8px">' + (pub ? '<span class="chip on">' + H.flag("IT") + H.flag("FR") + " Nazioni</span>" + H.sw("Nodi senza posizione", 0) : '<span class="muted">Trasmetti da</span><div style="width:190px">' + H.select(err ? "Nessuna radio" : "Radio-Casa · USB") + "</div>") + "</div>";
    var thHd = '<div class="phd" style="flex-wrap:wrap;gap:8px 12px"><div class="grow" style="min-width:140px"><h2 class="t-md">' + title + '</h2><div class="sub">' + sub + "</div></div>" + from + "</div>";
    var msgs;
    if (st === "caricamento") msgs = '<div class="msgs" style="justify-content:flex-start"><span class="skel tall" style="width:60%"></span><span class="skel tall" style="width:45%;align-self:flex-end"></span><span class="skel tall" style="width:55%"></span><span class="skel tall" style="width:35%;align-self:flex-end"></span></div>';
    else if (st === "vuoto") msgs = '<div class="msgs" style="justify-content:center">' + H.empty("chat", "Ancora nessun messaggio", "Scrivi qui sotto: il messaggio parte dalla radio scelta e arriva ai nodi nel raggio.") + "</div>";
    else if (pub) msgs = '<div class="msgs">' + msg("Rifugio Pino", "Buongiorno dal Passo, neve leggera", "", 0, "LongFast") + msg("Tour du Col", "Test mesh Alpi occidentali", "", 0, "MediumFast") + msg("Chalet Lac", "Qualcuno in ascolto sul lago?", "", 0, "LongFast") + msg("Torre Civica", "Ripetitore ok, batteria 89%", "", 0, "MediumFast") + "</div>";
    else msgs = '<div class="msgs">' + (ph ? "" : msg("Tetto Rosso", "Ricevuto, sono in cima al colle", "", 0) + msg("Io", "Perfetto, ti sento forte", "consegnato", 1)) + msg("Nodo Duomo", "Anche io ti ricevo, SNR buono", "", 0) + msg("Io", "Provo a spostarmi sul lato est", "inviato", 1) + msg("Io", "Se non rispondo richiamo alle 18", "fallito", 1) + msg("Io", "Controllo la batteria del ripetitore", "invio", 1) + "</div>";
    var comp;
    if (pub) comp = '<div class="composer"><div class="row" style="color:var(--ink-muted)">' + I("lock", 16) + "<span>Sola lettura: i messaggi pubblici MQTT non si possono inviare da qui.</span></div></div>";
    else {
      var len = err ? 0 : st === "vuoto" ? 0 : 47;
      comp = '<div class="composer">' + (err ? H.banner("danger", "Nessuna radio collegata", "Collega una radio dalla scheda Radio per trasmettere. Puoi comunque leggere i messaggi.", H.btn("Vai a Radio", { i: "radio" })) : "") + '<div class="row" style="align-items:flex-end"><div class="textarea grow' + (err ? " is-disabled" : "") + '" style="min-height:' + (ph ? 52 : 44) + 'px"><span class="muted">' + (err ? "Scrittura disabilitata" : "Scrivi un messaggio…") + '</span></div><button class="btn primary" ' + (err ? "disabled" : "") + ">" + I("send", 16) + "<span>Invia</span></button></div>" + '<div class="row"><span class="caption grow">Massimo 200 byte per messaggio</span><span class="mono caption" style="color:var(--ink)">' + len + "/200 byte</span></div></div>";
    }
    var thread = '<section class="cthread">' + thHd + msgs + comp + "</section>";
    var inner;
    if (ph) {
      var tabs = '<div style="padding:10px 12px;border-bottom:1px solid var(--line);background:var(--surface)">' + H.seg(["Canali", "Diretti", "Pubblico"], pub ? "Pubblico" : "Canali", 1) + "</div>";
      inner = '<div class="chat" style="flex-direction:column">' + tabs + thread + "</div>";
    } else inner = '<div class="chat">' + clist() + thread + "</div>";
    return S.shell(ctx, { tab: "chat", page: inner, mq: err ? "" : "" });
  }
};

/* ---------- 7. copertura ---------- */
function covPoints(n, upto) {
  var out = [], i; for (i = 0; i < n; i++) { var t = (i + 1) / n; out.push({ x: 300 + 440 * t + Math.sin(i * 1.3) * 6, y: 330 - 200 * t + Math.cos(i * 0.9) * 6, snr: Math.round((8 - 24 * t + Math.sin(i * 2.1) * 3) * 2) / 2, miss: i === 6 || i === 13 || i === 22 || i === 26 || i === 33 || (i > 40 && i % 3 === 0) }); }
  return out.slice(0, upto || n);
}
function checkRow(kind, t, sub) {
  var ic = kind === "ok" ? '<span style="color:var(--ok)">' + I("check", 18) + "</span>" : kind === "warn" ? '<span style="color:var(--warn)">' + I("alert", 18) + "</span>" : kind === "bad" ? '<span style="color:var(--danger)">' + I("x", 18) + "</span>" : '<span class="muted">' + I("minus", 18) + "</span>";
  var w = { ok: "Ok", warn: "Attenzione", bad: "Non ok", none: "In attesa" }[kind];
  return '<div class="row" style="align-items:flex-start;min-height:36px">' + ic + '<div class="grow"><div>' + t + (sub ? '<div class="sub">' + sub + "</div>" : "") + '</div></div><span class="caption">' + w + "</span></div>";
}
S.copertura = {
  label: "Copertura (Range Test)", states: [["preparazione", "Preparazione"], ["incorso", "Prova in corso"], ["risultati", "Risultati"], ["vuoto", "Storico vuoto"], ["errore", "Nessun pacchetto"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", o = { legend: false, noMarkers: true, mapH: ph ? 250 : 0, links: false };
    var panel = "", title = "Copertura";
    var guide = function (a, b, c, d, e) { return '<div class="sect"><h3 class="t-sm">Controlli prima di partire</h3><div class="card flat col" style="gap:2px;padding:8px 12px">' + checkRow(a[0], "Radio di base collegata", a[1]) + checkRow(b[0], "Nodo mobile sentito", b[1]) + checkRow(c[0], "Posizione GPS recente (≤ 10 min)", c[1]) + checkRow(d[0], "Precisione della posizione", d[1]) + checkRow(e[0], "Pacchetti Range Test ricevuti", e[1]) + "</div></div>"; };
    if (st === "preparazione") {
      var form = '<div class="sect"><h3 class="t-sm">Nuova prova</h3><div class="col">' + H.field("Radio di base", H.select("Radio-Portatile · USB COM4")) + H.field("Nodo mobile", H.select("Tetto Rosso (!b7c1d4e0)")) + H.field("Modalità (Range Test è la consigliata)", H.seg(["Range Test", "Solo posizione"], "Range Test", 1)) + H.field("Intervallo (secondi)", H.input("", { val: "30", mono: 1 })) + H.check("Usa un canale privato temporaneo a precisione piena (le due radio saranno isolate dalla rete pubblica durante la prova)", 0) + "</div></div>";
      var warn = H.banner("warn", "Posizioni approssimate", "Il nodo mobile invia la posizione con ±730 m di errore: i punti sulla mappa sarebbero imprecisi.") + '<div style="margin-top:-4px">' + H.check("Ho capito, continuo comunque con posizioni approssimate", 1) + "</div>";
      var diff = '<div class="sect"><h3 class="t-sm">Anteprima delle modifiche alle radio</h3><div class="tblwrap"><table class="tbl diff"><thead><tr><th>Impostazione</th><th>Ora</th><th>Dopo</th></tr></thead><tbody><tr><td>Range Test · modulo</td><td class="old">Disattivo</td><td class="new">Attivo</td></tr><tr><td>Range Test · intervallo</td><td class="old">—</td><td class="new mono">30 s</td></tr><tr class="risky"><td>Canale 1</td><td class="old">Primario · LongFast</td><td class="new">Privato temporaneo</td></tr></tbody></table></div><div class="hint">Con “Ripristina” le radio tornano ai valori di prima.</div></div>';
      var acts = '<div class="row wrap">' + H.btn("Prepara le radio", { i: "settings" }) + H.btn("Ripristina", { k: "ghost", i: "refresh" }) + '<span class="spacer"></span>' + H.btn("Avvia prova", { k: "primary", i: "target" }) + "</div>";
      panel = form + guide(["ok", "Radio-Portatile · USB COM4"], ["ok", "Tetto Rosso · sentito 12 s fa"], ["warn", "Ultimo fix 6 min fa"], ["warn", "Approssimata (±730 m)"], ["none", "Parte dopo l’avvio"]) + warn + diff + acts;
      o.tag = '<span class="muted">' + I("target", 16) + "</span> Pronto per una nuova prova";
    } else if (st === "incorso") {
      o.cov = covPoints(48, 30); o.tag = '<span class="dot danger" aria-hidden="true"></span> Prova in corso · 14:32';
      panel = '<div class="banner info">' + I("info", 20) + '<div class="grow"><div class="bt">Prova in corso</div><div>Cammina o guida con il nodo mobile: i punti compaiono sulla mappa.</div></div></div><div class="stats" style="grid-template-columns:repeat(2,1fr)"><div class="s"><div class="caption">Punti ricevuti</div><div class="n">24</div></div><div class="s"><div class="caption">Mancanti</div><div class="n">6</div></div><div class="s"><div class="caption">Perdita</div><div class="n">20,0 %</div></div><div class="s"><div class="caption">Ultimo SNR</div><div class="n">' + H.snrBadge(-3.5) + '</div></div></div><div class="row"><span class="muted grow">Durata</span><span class="mono">14:32</span></div>' + H.btn("Ferma la prova", { k: "danger lg block", i: "x" });
    } else if (st === "risultati") {
      var pts = covPoints(48); o.cov = pts; o.covMax = pts[38]; o.tag = "Risultati · Colle est";
      if (!ph) { o.popup = "x"; }
      panel = '<div class="sect"><div class="row"><h3 class="t-sm grow">Colle est</h3>' + H.badge("ok", "Conclusa", "check") + '</div><div class="stats"><div class="s"><div class="caption">Distanza max</div><div class="n">3,4 km</div></div><div class="s"><div class="caption">Punti</div><div class="n">41</div></div><div class="s"><div class="caption">Mancanti</div><div class="n">7</div></div></div></div><div class="sect"><h3 class="t-sm">Legenda dei punti</h3><div class="legrow"><span><i class="dot" style="background:var(--snr-good)"></i>≥ 0 dB</span><span><i class="dot" style="background:var(--snr-mid)"></i>−10…0 dB</span><span><i class="dot" style="background:var(--snr-bad)"></i>&lt; −10 dB</span><span>' + I("x", 14) + " Mancante</span></div></div>" +
        '<div class="sect"><h3 class="t-sm">Storico delle prove</h3><div class="card flat" style="padding:0">' + [["Colle est", "21 nov · 48 punti · 3,4 km", 1], ["Lungomare", "14 nov · 52 punti · 1,9 km", 0], ["Test iniziale", "2 nov · 18 punti · 0,8 km", 0]].map(function (r) { return '<div class="lrow' + (r[2] ? " sel" : "") + '"><div class="grow"><div class="nm">' + r[0] + '</div><div class="sub">' + r[1] + "</div></div>" + H.iconBtn("edit", "Rinomina", "ghost") + H.iconBtn("trash", "Elimina", "ghost") + "</div>"; }).join("") + '</div></div><div class="field"><label class="lbl">Note</label><div class="textarea"><span>Salita dal parcheggio, ricezione persa dopo il tornante.</span></div></div>';
    } else if (st === "vuoto") {
      panel = '<div class="card flat">' + H.empty("coverage", "Nessuna prova salvata", "Una prova di copertura mostra fin dove arriva il segnale. Servono due radio: una di base e un nodo mobile.", H.btn("Nuova prova", { k: "primary", i: "plus" })) + "</div>";
      o.tag = "Nessuna prova";
    } else {
      o.tag = '<span style="color:var(--danger)">' + I("alert", 16) + "</span> Nessun pacchetto ricevuto";
      panel = H.banner("danger", "Nessun pacchetto Range Test ricevuto", "Sono passati 2 minuti e il nodo mobile non risponde.") + guide(["ok", "Radio-Portatile · USB COM4"], ["bad", "Tetto Rosso non sentito da 4 min"], ["ok", "Ultimo fix 40 s fa"], ["ok", "Esatta (±8 m)"], ["bad", "0 pacchetti ricevuti"]) + '<div class="sect"><h3 class="t-sm">Cosa controllare</h3><ul class="muted" style="margin:0;padding-left:18px"><li>Il modulo Range Test è attivo sul nodo mobile.</li><li>Le due radio usano lo stesso canale.</li><li>Il nodo mobile è acceso e con la batteria carica.</li></ul></div><div class="row">' + H.btn("Riprova", { k: "primary", i: "refresh" }) + H.btn("Ripristina le radio", { k: "ghost" }) + "</div>";
    }
    var popupHtml = '<div class="popup" style="left:%Lpx;top:%Tpx"><div class="row"><span class="grow nm">Punto 31</span><span class="mono caption">14:21</span></div><div class="row" style="gap:12px">' + H.snrBadge(-7.5) + '<span class="mono">2,1 km dalla base</span></div><div class="sub">RSSI −109 dBm · salti 0</div></div>';
    if (o.popup) { o.popup = "!6f20a1b9"; o.popupHtml = popupHtml; }
    return S.shell(ctx, { tab: "copertura", map: S.mapView(ctx, o), mapH: o.mapH, title: title, noHead: ph, panel: panel });
  }
};

/* ---------- 8. radio ---------- */
function radioCard(r) {
  var badge = r.st === "ok" ? H.badge("ok", "Collegata", "check") : r.st === "re" ? H.badge("warn", "Riconnessione… tentativo 3", "refresh") : H.badge("danger", "Errore", "alert");
  var h = '<div class="card col" style="gap:12px"><div class="row wrap">' + I(r.tr === "usb" ? "usb" : "bt", 20) + '<div class="grow" style="min-width:150px"><div class="nm t-sm">' + r.n + '</div><div class="sub mono">' + r.port + "</div></div>" + badge + "</div>";
  if (r.st === "err") h += H.banner("danger", "Impossibile aprire la porta", "COM6 è usata da un’altra applicazione (per esempio l’app Meshtastic). Chiudila e riprova.", H.btn("Riprova", { i: "refresh" }));
  else if (r.st === "re") h += H.banner("warn", "Connessione persa", "Provo a ricollegarmi da solo. Controlla che il cavo sia inserito.", "");
  else {
    h += '<div class="kv one"><div><div class="k">Nodo locale</div><div class="v">Casa Ulivi</div><div class="sub mono">!3a7f91c2 · Heltec V3 · fw 2.7.11</div></div><div><div class="k">Canali</div><div class="chips" style="margin-top:4px">' + ['0 · Primario', '1 · Emergenza', '2 · Test'].map(function (c) { return '<span class="tag">' + c + "</span>"; }).join("") + "</div></div></div>" +
      '<div class="field"><label class="lbl">Chiave admin (pubblica)</label><div class="row">' + H.input("", { val: "mAdKq3…v9fT2xLw=", mono: 1 }) + H.btn("Copia", { i: "copy" }) + '</div><div class="hint">Serve per amministrare questo nodo da un’altra radio.</div></div>';
  }
  h += '<div class="row wrap">' + (r.st === "ok" ? H.btn("Configura", { i: "settings" }) : "") + H.btn("Disconnetti", { k: r.st === "ok" ? "" : "ghost", i: "power" }) + "</div></div>";
  return h;
}
function addDialog(kind, ph) {
  var usb = kind === "usb", scan = kind === "bt";
  var tabs = H.seg(["USB", "Bluetooth"], usb ? "USB" : "Bluetooth", 1);
  var list = usb ? [["COM4", "Heltec V3 (CP210x USB to UART)", 1], ["COM7", "T-Beam (CH9102)", 0], ["COM9", "Dispositivo seriale USB", 0]].map(function (r) { return '<div class="lrow' + (r[2] ? " sel" : "") + '" style="min-height:56px">' + I("usb", 18) + '<div class="grow"><div class="nm mono">' + r[0] + '</div><div class="sub">' + r[1] + "</div></div>" + (r[2] ? I("check", 18) : "") + "</div>"; }).join("")
    : '<div class="lrow" style="min-height:56px">' + I("bt", 18) + '<div class="grow"><div class="nm">Meshtastic_a91c</div><div class="sub">Segnale buono</div></div></div><div class="lrow" style="min-height:56px">' + I("bt", 18) + '<div class="grow"><div class="nm">Meshtastic_0d4e</div><div class="sub">Segnale debole</div></div></div><div class="row" style="padding:12px 16px;color:var(--ink-muted)">' + I("spinner", 16) + "<span>Scansione in corso…</span></div>";
  return '<div class="modal"><div class="row"><h2 class="t-md grow">Aggiungi una radio</h2>' + H.iconBtn("x", "Chiudi", "ghost") + "</div>" + tabs + '<div class="card flat" style="padding:0">' + list + "</div>" + (usb ? '<div class="hint">Non vedi la tua radio? Controlla il cavo dati (non solo di ricarica) e il driver USB.</div>' : "") + '<div class="acts">' + H.btn("Annulla") + H.btn(usb ? "Collega COM4" : "Collega", { k: "primary" }) + "</div></div>";
}
S.radio = {
  label: "Radio", states: [["normale", "Normale"], ["aggiungi", "Aggiungi · USB"], ["bluetooth", "Aggiungi · Bluetooth"], ["vuoto", "Nessuna radio"], ["errore", "Errore porta"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", body, modal = "";
    var rs = [{ n: "Radio-Casa", tr: "usb", port: "USB · COM4", st: "ok" }, { n: "Radio-Portatile", tr: "bt", port: "Bluetooth · Meshtastic_a91c", st: "re" }, { n: "Radio-Prova", tr: "usb", port: "USB · COM6", st: "err" }];
    if (st === "vuoto") body = '<div class="card flat">' + H.empty("radio", "Nessuna radio collegata", "Collega una radio Meshtastic via USB o Bluetooth per leggere i suoi messaggi, configurarla e fare prove di copertura.", H.btn("Aggiungi una radio", { k: "primary", i: "plus" })) + "</div>";
    else if (st === "errore") body = H.banner("danger", "Una radio ha un problema", "Radio-Prova non si apre. Vedi i dettagli qui sotto.", "") + radioCard(rs[2]) + radioCard(rs[0]);
    else body = radioCard(rs[0]) + radioCard(rs[1]) + radioCard(rs[2]);
    if (st === "aggiungi") modal = addDialog("usb", ph); if (st === "bluetooth") modal = addDialog("bt", ph);
    return shellPage(ctx, "radio", pageHd("Radio", H.btn("Aggiungi radio", { k: "primary", i: "plus" }), "Radio collegate a questo PC") + body, true, modal);
  }
};
})();
(function () {
"use strict";
var NS = window.MeshLens, H = NS._h, I = H.I, S = NS.screens;
function pageHd(title, right, sub, back) { return '<div class="row wrap" style="gap:12px">' + (back ? H.iconBtn("back", "Indietro", "ghost") : "") + '<div class="grow"><h1 class="t-lg">' + title + "</h1>" + (sub ? '<p class="muted">' + sub + "</p>" : "") + "</div>" + (right || "") + "</div>"; }
function shellPage(ctx, tab, inner, narrow, modal) { return S.shell(ctx, { tab: tab, page: '<div class="page' + (narrow ? " narrow" : "") + '">' + inner + "</div>", modal: modal }); }

/* ---------- 9. configura nodo ---------- */
var CT = ["Generale", "Posizione", "Telemetria", "LoRa", "Canali", "Moduli", "Avanzate"];
function chRows(ph) {
  var rows = [["0", "Primario", "PRIMARY", "••••••••••••••••", 0], ["1", "Emergenza", "SECONDARY", "••••••••••••••••", 1], ["2", "Test", "SECONDARY", "••••••••••••••••", 0], ["3", "", "DISABLED", "", 0], ["4", "", "DISABLED", "", 0], ["5", "", "DISABLED", "", 0], ["6", "", "DISABLED", "", 0], ["7", "", "DISABLED", "", 0]];
  return rows.map(function (r) {
    var on = r[2] !== "DISABLED";
    return '<div class="chrow"><span class="mono muted">' + r[0] + "</span><div>" + H.input("Nome canale", { val: r[1] }) + "</div><div>" + H.select(r[2]) + '</div><div class="row">' + (on ? H.input("", { val: r[3], mono: 1 }) + H.btn("", { k: "icon", i: "eye" }).replace("<button", '<button aria-label="Mostra chiave"') + H.btn("Genera", { i: "refresh" }) : '<span class="muted">Canale non usato</span>') + "</div></div>";
  }).join("");
}
function loraForm() {
  return '<div class="form">' + H.field("Regione", H.select("EU_868")) + H.field('<span class="changed">Preset del modem</span>', H.select("ShortFast"), "Era LongFast. A rischio: vedi anteprima.") + H.field("Salti massimi", H.input("", { val: "3", mono: 1 })) + H.field("Potenza di trasmissione (dBm)", H.input("", { val: "20", mono: 1 })) + H.field("Offset di frequenza (MHz)", H.input("", { val: "0,0", mono: 1 })) + H.field("Canale (slot) di frequenza", H.input("", { val: "0 (automatico)", mono: 1 })) + '<div style="grid-column:1/-1" class="col">' + H.sw("Trasmissione attiva", 1) + H.sw("Ignora MQTT", 0) + "</div></div>";
}
function diffModal(stage, ph) {
  var rows = [["Generale · Nome breve", "ULIV", "CASA", 0, ""], ["LoRa · Potenza TX", "17 dBm", "20 dBm", 0, ""], ["LoRa · Preset del modem", "LongFast", "ShortFast", 1, "Il nodo non sentirà più i vicini che usano LongFast e potrebbe restare isolato dalla rete."]];
  var tb = '<div class="tblwrap" style="max-height:260px;overflow:auto"><table class="tbl diff"><thead><tr><th>Impostazione</th><th>Attuale</th><th>Nuovo</th></tr></thead><tbody>' + rows.map(function (r) { return '<tr class="' + (r[3] ? "risky" : "") + '"><td>' + (r[3] ? '<span class="row" style="gap:6px;color:var(--danger);font-weight:600">' + I("alert", 16) + "A rischio</span>" : "") + r[0] + (r[3] ? '<div class="sub" style="color:var(--ink)">' + r[4] + "</div>" : "") + '</td><td class="old mono">' + r[1] + '</td><td class="new mono">' + r[2] + "</td></tr>"; }).join("") + "</tbody></table></div>";
  if (stage === "applicazione") return '<div class="modal"><h2 class="t-md">Applico le modifiche…</h2>' + H.progress(66) + '<div class="col" style="gap:6px"><div class="row">' + I("check", 16) + "<span>Generale · scritto</span></div><div class=\"row\">" + I("spinner", 16) + "<span>LoRa · scrittura 2/3…</span></div><div class=\"row muted\">" + I("minus", 16) + '<span>Verifica finale</span></div></div><div class="hint">Non scollegare la radio e non chiudere la pagina. Il nodo può riavviarsi.</div></div>';
  return '<div class="modal risk"><div class="row"><h2 class="t-md grow">Anteprima delle modifiche</h2>' + H.iconBtn("x", "Chiudi", "ghost") + '</div><p class="muted">3 impostazioni cambiano su Casa Ulivi. Una può rendere il nodo irraggiungibile.</p>' + tb + H.check("Ho capito che questa modifica può isolare il nodo", 0, 1) + '<div class="hint err" style="margin-top:-8px">Per applicare devi confermare la casella.</div><div class="acts">' + H.btn("Annulla") + H.btn("Applica le modifiche", { k: "danger", dis: 1, i: "check" }) + "</div></div>";
}
S.configura = {
  label: "Configura nodo", states: [["normale", "Canali"], ["lettura", "Lettura"], ["anteprima", "Anteprima differenze"], ["applicazione", "Applicazione"], ["esito", "Esito positivo"], ["errore", "Verifica non coincide"], ["avanzate", "Avanzate"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", modal = "", tab = st === "normale" ? "Canali" : st === "avanzate" ? "Avanzate" : "LoRa";
    var tabs = ph ? '<div class="htabs">' + CT.map(function (t) { return H.chip(t, t === tab); }).join("") + "</div>" : '<nav class="vtabs" aria-label="Sezioni di configurazione">' + CT.map(function (t) { return '<button class="vtab' + (t === tab ? " on" : "") + '">' + t + "</button>"; }).join("") + "</nav>";
    var content;
    if (st === "lettura") content = '<div class="card col"><div class="row">' + I("spinner", 18) + '<div class="grow nm">Lettura LoRa 3/25…</div><span class="mono">12 %</span></div>' + H.progress(12) + '<div class="hint">Leggo la configurazione dalla radio. Ci vuole circa un minuto.</div></div><div class="form"><span class="skel tall"></span><span class="skel tall"></span><span class="skel tall"></span><span class="skel tall"></span></div>';
    else if (st === "normale") content = '<div class="sect"><div class="shd"><h2 class="t-md grow">Canali</h2>' + H.badge("", "8 posizioni") + '</div><div class="hint">La chiave (PSK) è nascosta. Premi l’occhio per vederla o “Genera” per crearne una nuova.</div><div class="card flat" style="padding:4px 12px">' + chRows(ph) + "</div></div>";
    else if (st === "avanzate") content = '<div class="sect"><div class="shd"><h2 class="t-md grow">Avanzate</h2>' + H.badge("", "Generate dallo schema") + "</div>" + H.input("Cerca un campo (es. “rebroadcast”)", { i: "search" }) + '<div class="card flat col" style="gap:14px"><div class="t-sm">Dispositivo · device</div><div class="form">' + H.field("rebroadcast_mode", H.select("ALL"), "Enum · come ritrasmettere i pacchetti.") + H.field("node_info_broadcast_secs", H.input("", { val: "10800", mono: 1 }), "Numero · secondi.") + H.field("serial_enabled", H.sw("Attivo", 1)) + H.field("button_gpio", H.input("", { val: "0", mono: 1 }), "Numero · pin del pulsante.") + "</div></div>" + H.banner("warn", "Campi per esperti", "Cambiare questi valori senza sapere cosa fanno può rendere la radio instabile.") + "</div>";
    else content = '<div class="sect"><div class="shd"><h2 class="t-md grow">LoRa</h2>' + H.badge("info", "2 modifiche non applicate") + "</div>" + loraForm() + "</div>";
    if (st === "esito") content = H.banner("ok", "Applicato e verificato", "Ho riletto la radio: i valori coincidono con quelli scelti. Copia di sicurezza creata alle 14:36.", H.btn("Vedi dettagli", { k: "ghost" })) + content;
    if (st === "errore") content = H.banner("danger", "La verifica non coincide", "Dopo la scrittura, “LoRa · Preset del modem” risulta ancora LongFast. Le altre 2 modifiche sono a posto.", '<div class="row">' + H.btn("Riprova") + H.btn("Ripristina la copia", { i: "refresh" }) + "</div>") + content;
    if (st === "anteprima") modal = diffModal("anteprima", ph); if (st === "applicazione") modal = diffModal("applicazione", ph);
    var bk = '<div class="card flat col" style="gap:8px"><div class="shd row"><h3 class="t-sm grow">Copie di sicurezza</h3>' + H.btn("Crea ora", { i: "plus" }) + '</div><div class="row"><span class="grow mono caption" style="color:var(--ink)">21 nov 14:12 · automatica</span>' + H.btn("Ripristina", { k: "ghost" }) + '</div><div class="row"><span class="grow mono caption" style="color:var(--ink)">14 nov 09:40 · manuale</span>' + H.btn("Ripristina", { k: "ghost" }) + "</div></div>";
    var side = ph ? "" : '<div class="col" style="width:240px;flex:none">' + bk + "</div>";
    var hdR = '<div class="row wrap">' + H.btn("Guida chiave admin", { k: "ghost", i: "key" }) + H.btn("Riavvia il nodo", { i: "power" }) + "</div>";
    var foot = '<div class="stickybar"><span class="grow"><b>3</b> modifiche non applicate</span>' + H.btn("Annulla") + H.btn("Anteprima modifiche", { k: "primary", i: "eye" }) + "</div>";
    var body = '<div class="' + (ph ? "col" : "row") + '" style="align-items:flex-start;gap:24px">' + tabs + '<div class="grow col" style="width:100%;gap:16px">' + content + (ph ? bk : "") + "</div>" + side + "</div>";
    return shellPage(ctx, "radio", pageHd("Configura Casa Ulivi", ph ? "" : hdR, "Radio-Casa · Heltec V3 · !3a7f91c2", true) + (ph ? hdR : "") + body + (st === "lettura" ? "" : foot), false, modal);
  }
};

/* ---------- 10. impostazioni ---------- */
var IM = ["Storico dati", "MQTT", "Avvisi", "Rete locale", "Mappe offline", "Aggiornamenti", "Informazioni"];
function card(title, icon, inner, sub) { return '<section class="card flat sect"><div class="shd">' + I(icon, 18) + '<h2 class="t-sm grow">' + title + "</h2></div>" + (sub ? '<p class="muted">' + sub + "</p>" : "") + inner + "</section>"; }
S.impostazioni = {
  label: "Impostazioni", states: [["normale", "Normale"], ["scarica", "Download mappe"], ["conferma", "Conferma area"], ["aggiornamento", "Aggiornamento disponibile"], ["errore", "Token non valido"]],
  render: function (ctx) {
    var st = ctx.st, ph = ctx.vp === "phone", modal = "";
    var nav = ph ? '<div class="htabs">' + IM.map(function (t, i) { return H.chip(t, i === (st === "normale" || st === "scarica" || st === "conferma" ? 4 : 5)); }).join("") + "</div>" : '<nav class="vtabs" style="position:sticky;top:0">' + IM.map(function (t, i) { return '<button class="vtab' + (i === (st === "normale" || st === "scarica" || st === "conferma" ? 4 : 5) ? " on" : "") + '">' + t + "</button>"; }).join("") + "</nav>";
    var paesi = '<div class="chips">' + ["IT", "FR", "CH", "DE"].map(function (c) { return '<span class="chip on">' + H.flag(c) + {IT: "Italia", FR: "Francia", CH: "Svizzera", DE: "Germania"}[c] + " " + I("x", 14) + "</span>"; }).join("") + H.chip("Aggiungi", 0, I("plus", 14) + " ") + "</div>";
    var storico = card("Storico dati", "clock", H.field("Nazioni da salvare", paesi, "I nodi di altre nazioni restano visibili ma non vengono archiviati.") + H.field("Conserva i dati per", H.select("90 giorni")) + '<div class="row">' + H.btn("Pulisci ora", { i: "trash" }) + '<span class="caption">Spazio usato: 214 MB</span></div>');
    var mqtt = card("MQTT", "globe", H.field("Broker", H.input("", { val: "mqtt.meshtastic.org", mono: 1 })) + H.field("Canali da ascoltare", '<div class="chips">' + ["LongFast", "MediumFast", "ShortFast"].map(function (c, i) { return '<span class="chip ' + (i < 2 ? "on" : "") + '">' + c + (i < 2 ? " " + I("x", 14) : "") + "</span>"; }).join("") + H.chip("Aggiungi", 0, I("plus", 14) + " ") + "</div>", "Più canali, più traffico da elaborare."));
    var avv = card("Soglie degli avvisi", "bell", '<div class="form">' + H.field("Batteria bassa sotto", H.input("", { val: "20 %", mono: 1 })) + H.field("Nodo silenzioso dopo", H.input("", { val: "6 ore", mono: 1 })) + "</div>");
    var rete = card("Accesso dalla rete locale", "lock", H.sw("Consenti l’accesso da telefono e altri PC della Wi-Fi", 1) + '<div class="row">' + H.input("", { val: "http://192.168.1.20:8080", mono: 1 }) + H.btn("Copia", { i: "copy" }) + "</div>" + '<div class="hint">Serve il PIN. Non aprire questa porta su internet.</div>');
    var mapMode = H.field("Modalità mappa", H.seg(["Automatica", "Solo online", "Solo offline"], "Automatica", 1));
    var free = '<div class="col" style="gap:6px"><div class="row"><span class="grow muted">Spazio libero</span><b class="mono">667,0 GB</b></div>' + H.progress(14) + "</div>";
    var dl = H.btn("Scarica il mondo (base)", { i: "download" }) + H.btn("Scarica l’Italia", { i: "download" }) + H.btn("Scarica l’area visibile", { i: "download" });
    var prog = st === "scarica" ? '<div class="card col" style="gap:8px"><div class="row"><span class="grow nm">Scarico l’Italia…</span><span class="mono">38 %</span></div>' + H.progress(38) + '<div class="row"><span class="caption grow">0,7 di 1,8 GB · 4 min rimasti</span>' + H.btn("Annulla", { i: "x" }) + "</div></div>" : "";
    var list = '<div class="card flat" style="padding:0">' + [["Mondo (base)", "186 MB · 3 nov"], ["Italia", "1,8 GB · 12 nov"]].map(function (r, i, a) { return '<div class="lrow"' + (i === a.length - 1 ? ' style="border-bottom:0"' : "") + '><div class="grow"><div class="nm">' + r[0] + '</div><div class="sub">' + r[1] + "</div></div>" + H.btn("Elimina", { k: "ghost", i: "trash" }) + "</div>"; }).join("") + "</div>";
    var offline = card("Mappe offline", "map", mapMode + free + '<div class="row wrap">' + dl + "</div>" + prog + '<h3 class="t-sm">Mappe scaricate</h3>' + list + '<div class="caption">© OpenStreetMap contributors · Protomaps</div>');
    var upd = '<div class="row"><span class="grow muted">Versione attuale</span><b class="mono">1.0.0</b></div>';
    if (st === "aggiornamento") upd += H.banner("info", "Disponibile la versione 1.1.0", "Ultimo controllo: oggi alle 13:00", "") + '<div class="card flat col" style="gap:6px"><div class="t-sm">Novità della 1.1.0</div><ul class="muted" style="margin:0;padding-left:18px"><li>Nuova scheda Copertura con guida di preparazione.</li><li>Grafico di batteria su 30 giorni.</li><li>Correzioni all’avvio con Bluetooth.</li></ul></div><div class="row wrap">' + H.btn("Scarica", { i: "download" }) + H.btn("Installa e riavvia", { k: "primary", i: "refresh" }) + "</div>";
    else if (st === "errore") upd += H.banner("danger", "Token GitHub non valido", "Il repository è privato: inserisci un token valido per controllare gli aggiornamenti.", H.btn("Come crearlo", { k: "ghost" })) + '<div class="caption">Ultimo controllo: non riuscito</div>';
    else upd += '<div class="caption">Ultimo controllo: oggi alle 13:00 · sei aggiornato</div>';
    upd += H.field("Token GitHub (repository privato)", '<div class="row wrap">' + H.input("", { val: "github_pat_••••••••••••", mono: 1, err: st === "errore" }) + H.btn("Salva token") + "</div>", st === "errore" ? "Il token è scaduto o non ha accesso al repository." : "", st === "errore") + '<div class="row wrap">' + H.check("Controlla automaticamente ogni giorno", 1) + "</div><div class=\"row wrap\">" + H.btn("Controlla ora", { i: "refresh" }) + H.btn("Come creare il token", { k: "ghost", i: "info" }) + "</div>";
    var aggi = card("Aggiornamenti", "download", upd);
    var info = card("Informazioni e licenze", "info", '<div class="row wrap">' + NS.compatBadge + '</div><p class="caption">MeshLens non è affiliato al progetto Meshtastic. Meshtastic® è un marchio registrato di Meshtastic LLC.</p><div class="row">' + H.btn("Licenze open source", { k: "ghost" }) + "</div>");
    var sections = (st === "normale" || st === "scarica" || st === "conferma") ? [offline, aggi, storico, mqtt, avv, rete, info] : [aggi, offline, storico, mqtt, avv, rete, info];
    var logout = '<div class="row">' + H.btn("Esci", { i: "power" }) + "</div>";
    if (st === "conferma") modal = '<div class="modal"><h2 class="t-md">Scaricare l’area visibile?</h2><div class="kv"><div><div class="k">Dimensione stimata</div><div class="v mono">≈ 412 MB</div></div><div><div class="k">Tile da scaricare</div><div class="v mono">18.400</div></div><div><div class="k">Spazio libero dopo</div><div class="v mono">666,6 GB</div></div><div><div class="k">Tempo stimato</div><div class="v">circa 6 min</div></div></div><div class="acts">' + H.btn("Annulla") + H.btn("Scarica", { k: "primary", i: "download" }) + "</div></div>";
    if (st === "aggiornamento" && false) modal = "";
    var body = '<div class="' + (ph ? "col" : "row") + '" style="align-items:flex-start;gap:24px">' + nav + '<div class="grow col" style="width:100%;gap:16px">' + sections.join("") + logout + "</div></div>";
    return shellPage(ctx, "impostazioni", pageHd("Impostazioni") + body, false, modal);
  }
};
})();
(function () {
"use strict";
var NS = window.MeshLens, H = NS._h, I = H.I, S = NS.screens, N = H.NODES;

/* ---------- logo con colori fissi (i file SVG sono a colori fissi) ---------- */
function markInner(g) {
  var t = g === "dark" ? "#14b8a6" : "#0f766e", n = g === "dark" ? "#38bdf8" : "#0284c7";
  return '<g stroke="' + t + '" stroke-opacity=".6" stroke-width="6" stroke-linecap="round" fill="none"><path d="M40 60 L104 36 L184 56 L220 120 M40 60 L52 150 L104 36 M52 150 L40 212"/></g><g fill="' + n + '"><circle cx="40" cy="60" r="9"/><circle cx="104" cy="36" r="9"/><circle cx="184" cy="56" r="9"/><circle cx="220" cy="120" r="9"/><circle cx="52" cy="150" r="9"/><circle cx="40" cy="212" r="9"/></g><circle cx="124" cy="128" r="58" fill="' + t + '" fill-opacity=".16" stroke="' + t + '" stroke-width="14"/><path d="M167 171 L226 230" stroke="' + t + '" stroke-width="20" stroke-linecap="round"/><path d="M98 108 L152 102 L128 156 Z" stroke="' + n + '" stroke-width="5" stroke-linejoin="round" fill="none"/><g fill="' + n + '"><circle cx="98" cy="108" r="8"/><circle cx="152" cy="102" r="8"/><circle cx="128" cy="156" r="8"/></g><circle cx="126" cy="122" r="11" fill="#f59e0b"/>';
}
function logoSvg(sz, g) { return '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 256 256" role="img" aria-label="MeshLens">' + markInner(g) + "</svg>"; }
function oldLogo(sz) { return '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 256 256" role="img" aria-label="MeshLens attuale"><g stroke="#14b8a6" stroke-width="5" stroke-linecap="round" fill="none"><path d="M48 70 L110 44 L176 70 L208 128 M48 70 L66 138 L110 44 M66 138 L128 168 L176 70 M128 168 L208 128 M66 138 L48 200"/></g><g fill="#0ea5e9"><circle cx="48" cy="70" r="10"/><circle cx="110" cy="44" r="10"/><circle cx="176" cy="70" r="10"/><circle cx="66" cy="138" r="10"/><circle cx="208" cy="128" r="10"/><circle cx="48" cy="200" r="10"/></g><circle cx="128" cy="124" r="52" fill="#14b8a6" fill-opacity="0.18" stroke="#0f766e" stroke-width="12"/><path d="M166 162 L222 218" stroke="#0f766e" stroke-width="18" stroke-linecap="round"/><circle cx="128" cy="168" r="11" fill="#f59e0b"/></svg>'; }
function appIcon(sz, small) {
  if (small) return '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 256 256" role="img" aria-label="MeshLens"><rect width="256" height="256" rx="56" fill="#0b1220"/><circle cx="116" cy="116" r="66" fill="#14b8a6" fill-opacity=".2" stroke="#14b8a6" stroke-width="28"/><path d="M166 166 L218 218" stroke="#14b8a6" stroke-width="36" stroke-linecap="round"/><circle cx="116" cy="116" r="22" fill="#f59e0b"/></svg>';
  return '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 256 256" role="img" aria-label="MeshLens"><rect width="256" height="256" rx="56" fill="#0b1220"/><g transform="translate(25 25) scale(.8)">' + markInner("dark") + "</g></svg>";
}

/* ---------- guscio dei campioni ---------- */
function pane(theme, title, inner, cls) { return '<div class="pane ' + (cls || "") + '" data-theme="' + theme + '"><div class="tt">' + title + "</div>" + inner + "</div>"; }
function mountSpecimen(name, o) {
  o = o || {};
  var root = document.getElementById("root"); root.className = "ml";
  var f = SPEC[name], h = '<div class="' + (o.stack ? "" : "specgrid") + '">';
  h += pane("dark", "Tema scuro", f("dark"), "") + pane("light", "Tema chiaro", f("light"), "");
  root.innerHTML = h + "</div>";
}
NS.mountSpecimen = mountSpecimen;
function ph(inner) { return '<div class="vp-phone" style="display:contents">' + inner + "</div>"; }
function row(inner) { return '<div class="sample">' + inner + "</div>"; }
function lab(t) { return '<div class="lbl">' + t + "</div>"; }
function sub(t, inner) { return lab(t) + inner; }
var SPEC = {};

SPEC.buttons = function () {
  var b = H.btn;
  return sub("Principale · secondario · distruttivo · testo · solo icona", row(b("Avvia prova", { k: "primary", i: "target" }) + b("Annulla") + b("Elimina", { k: "danger", i: "trash" }) + b("Come crearlo", { k: "ghost" }) + H.iconBtn("settings", "Impostazioni"))) +
    sub("Stati: hover · premuto · focus · disabilitato", row(b("Hover", { k: "primary", cls: "is-hover" }) + b("Premuto", { k: "primary", cls: "is-active" }) + b("Focus", { k: "primary", cls: "is-focus" }) + b("Disabilitato", { k: "primary", dis: 1 }) + b("Hover", { cls: "is-hover" }) + b("Focus", { cls: "is-focus" }) + b("Disabilitato", { dis: 1 }))) +
    sub("Su telefono: 44 px di altezza", ph(row(b("Avvia prova", { k: "primary", i: "target" }) + b("Annulla") + H.iconBtn("settings", "Impostazioni")))) +
    sub("Larghezza piena (modali e pannelli)", b("Salva il PIN e continua", { k: "primary lg block" }));
};
SPEC.fields = function () {
  return sub("Campo: normale · focus · errore · disabilitato", '<div class="col" style="gap:12px">' + H.field("Normale", H.input("Cerca nome o id…", { i: "search" })) + H.field("Focus", H.input("", { val: "Casa Ulivi", foc: 1 })) + H.field("Errore", H.input("", { val: "••••", err: 1, mono: 1 }), "PIN errato. Hai ancora 2 tentativi.", 1) + H.field("Disabilitato", '<div class="input is-disabled"><span class="grow muted">Disabilitato fino alla fine del blocco</span></div>') + H.field("Select", H.select("Tutte le radio")) + "</div>") +
    sub("Interruttore · checkbox", row(H.sw("Collegamenti", 1) + H.sw("Copertura", 0)) + row(H.check("Controlla ogni giorno", 1) + H.check("Non selezionato", 0) + H.check("Ho capito il rischio", 0, 1))) +
    sub("Segmented control", row(H.seg(["24 h", "7 g", "30 g"], "7 g") + H.seg(["Tutte", "Radio", "MQTT"], "Tutte"))) +
    sub("Chip dei filtri", '<div class="chips">' + H.chip("2 h", 0) + H.chip("24 h", 1) + H.chip("7 g", 0) + H.chip("Italia", 1, H.flag("IT") + " ") + H.chip("Radio", 1, H.srcMark("radio", 16)) + "</div>") +
    sub("Telefono: aree da 44 px", ph(row(H.seg(["24 h", "7 g", "30 g"], "7 g") + H.chip("24 h", 1)) + '<div>' + H.check("Controlla ogni giorno", 1) + "</div>"));
};
SPEC.badges = function () {
  var d = H.NODES[0];
  return sub("Stato di connessione", row(H.badge("ok", "Collegata", "check") + H.badge("warn", "Riconnessione…", "refresh") + H.badge("danger", "Errore", "alert") + H.badge("info", "Aggiornamento", "download") + H.badge("", "Neutro"))) +
    sub("SNR: sempre con segno e unità", row(H.snrBadge(6.5) + H.snrBadge(-3.5) + H.snrBadge(-12.5) + H.snrBadge(null))) +
    sub("Batteria: normale · 20–40% · sotto soglia · alimentato", row(H.battBadge(84) + H.battBadge(34) + H.battBadge(14) + H.battBadge(100, true))) +
    sub("Ultimo contatto", row('<span class="row" style="gap:6px">' + H.dot(5) + "5 min fa</span>" + '<span class="row" style="gap:6px">' + H.dot(300) + "5 h fa</span>" + '<span class="row" style="gap:6px">' + H.dot(3000) + "2 g fa</span>")) +
    sub("Fonte: Radio · MQTT · Entrambe", row('<span class="row" style="gap:6px">' + H.srcMark("radio") + "Radio</span>" + '<span class="row" style="gap:6px">' + H.srcMark("mqtt") + "MQTT</span>" + '<span class="row" style="gap:6px">' + H.srcMark("both") + "Entrambe</span>")) +
    sub("Ruolo, canale, nazione", row('<span class="role">ROUTER</span><span class="tag">LongFast</span>' + H.flag("IT") + H.flag("FR") + H.flag("DE") + H.flag("CH") + H.flag("ES"))) +
    sub("Telefono: etichette da 14 px", ph(row(H.badge("ok", "Collegata", "check") + H.snrBadge(-3.5) + H.battBadge(34))));
};
SPEC.table = function () {
  var rows = N.filter(function (n) { return n.mine; }).slice(0, 4);
  var tb = '<div class="tblwrap"><table class="tbl"><thead><tr><th class="fix">Nodo' + I("sort", 14) + '</th><th class="sorted">Ultimo contatto' + I("chevD", 14) + "</th><th>Ruolo</th><th>Batteria</th><th>SNR</th><th class=\"num\">Salti</th></tr></thead><tbody>" + rows.map(function (n, i) { return '<tr class="' + (i === 1 ? "sel" : "") + '"><td class="fix"><span class="row" style="gap:8px">' + H.flag(n.cc) + '<span class="nm">' + n.n + "</span></span></td><td><span class=\"row\" style=\"gap:6px\">" + H.dot(n.min) + H.ago(n.min) + '</span></td><td><span class="role">' + n.role + "</span></td><td>" + H.battBadge(n.b, n.usb) + "</td><td>" + H.snrBadge(n.snr) + '</td><td class="num">' + n.hops + "</td></tr>"; }).join("") + "</tbody></table></div>";
  return sub("Tabella densa · colonna fissa · riga selezionata · colonna ordinata", tb) + '<div class="hint">Su telefono la tabella scorre in orizzontale: la colonna “Nodo” resta ferma e le righe salgono a 52 px.</div>' + sub("Telefono", ph('<div style="max-width:340px">' + tb + "</div>"));
};
SPEC.surfaces = function () {
  return sub("Scheda · scheda piatta · scheda a rischio", '<div class="col"><div class="card"><div class="t-sm">Scheda sollevata</div><p class="muted">Per contenuti sopra il fondo del pannello.</p></div><div class="card flat"><div class="t-sm">Scheda piatta</div><p class="muted">Per liste e gruppi dentro un pannello.</p></div><div class="card risk"><div class="row" style="color:var(--danger);font-weight:600">' + I("alert", 16) + "A rischio</div><p>Il nodo potrebbe restare isolato.</p></div></div>") +
    sub("Modale di conferma", '<div class="modal" style="max-width:none"><h2 class="t-md">Installare l’aggiornamento?</h2><p class="muted">MeshLens si riavvia e le radio collegate si ricollegano da sole.</p><div class="acts">' + H.btn("Annulla") + H.btn("Installa e riavvia", { k: "primary" }) + "</div></div>") +
    sub("Modale “a rischio”: bordo e conferma obbligatoria", '<div class="modal risk" style="max-width:none"><h2 class="t-md">Applicare la modifica?</h2><p class="muted">Cambiare il preset può isolare il nodo.</p>' + H.check("Ho capito che questa modifica può isolare il nodo", 0, 1) + '<div class="acts">' + H.btn("Annulla") + H.btn("Applica", { k: "danger", dis: 1 }) + "</div></div>") +
    sub("Bottom sheet (telefono)", ph('<div class="sheet" style="position:relative;height:150px;z-index:0"><div class="gr"></div><div class="phd"><h2 class="t-md grow">Nodi</h2></div><div class="lrow" style="border:0">' + H.flag("IT") + '<span class="grow nm">Fienile Radio</span>' + H.battBadge(83) + "</div></div>"));
};
SPEC.feedback = function () {
  return sub("Banner", '<div class="col" style="gap:8px">' + H.banner("warn", "1 avviso attivo", "Batteria bassa su Base Colli.") + H.banner("danger", "MQTT non raggiungibile", "Riprovo tra 10 s.", H.btn("Riprova")) + H.banner("ok", "Applicato e verificato", "Copia di sicurezza creata.") + H.banner("info", "Disponibile la versione 1.1.0", "", H.btn("Scarica", { k: "primary" })) + "</div>") +
    sub("Toast", '<div class="col" style="gap:8px;align-items:flex-start">' + H.toast("ok", "Messaggio inviato") + H.toast("warn", "Radio-Portatile si sta ricollegando", H.btn("Dettagli", { k: "ghost" })) + H.toast("danger", "Messaggio non consegnato") + "</div>") +
    sub("Barre di avanzamento", '<div class="col" style="gap:10px">' + H.progress(38) + H.progress(72, "ok") + H.progress(46, "warn") + H.progress(20, "danger") + "</div>") +
    sub("Stato vuoto", '<div class="card flat">' + H.empty("search", "Nessun nodo corrisponde", "Prova ad allargare l’ultimo contatto.", H.btn("Azzera i filtri", { i: "refresh" })) + "</div>") +
    sub("Caricamento: segnaposto fissi, senza animazione continua", '<div class="card flat" style="padding:0">' + H.skelRows(3, 56) + "</div>");
};
SPEC.chart = function () {
  return sub("Grafico di batteria e tensione · 7 giorni · soglia", row(H.seg(["24 h", "7 g", "30 g"], "7 g")) + S.chart({ vp: "desktop" }, { w: 500 })) + sub("Senza dati", S.chart({ vp: "desktop" }, { w: 500, empty: 1 })) + sub("Telefono: testo da 14 px", ph('<div style="max-width:346px">' + S.chart({ vp: "phone" }) + "</div>"));
};
SPEC.mapparts = function (th) {
  var mk = function (src, min, mine) { return '<svg width="44" height="44" viewBox="-22 -22 44 44">' + H.nodeMarker({ x: 0, y: 0, min: min, src: src, mine: mine }, 0) + "</svg>"; };
  var cols = '<div class="sample"><span class="caption" style="width:70px">Radio</span>' + mk("radio", 10) + mk("radio", 300) + mk("radio", 3000) + '</div><div class="sample"><span class="caption" style="width:70px">MQTT</span>' + mk("mqtt", 10) + mk("mqtt", 300) + mk("mqtt", 3000) + '</div><div class="sample"><span class="caption" style="width:70px">Entrambe</span>' + mk("both", 10, 1) + mk("both", 300) + mk("both", 3000) + "</div>";
  var bg = 'background:var(--map-land);border-radius:12px;padding:12px;border:1px solid var(--line)';
  var lines = '<svg width="100%" height="120" style="background:var(--map-water);border-radius:12px"><rect x="0" y="40" width="100%" height="80" fill="var(--map-land)"/><line x1="20" y1="22" x2="200" y2="22" stroke="var(--snr-good)" stroke-width="3" stroke-linecap="round"/><text x="210" y="26" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">≥ 0 dB</text><line x1="20" y1="46" x2="200" y2="46" stroke="var(--snr-mid)" stroke-width="3" stroke-linecap="round"/><text x="210" y="50" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">−10…0 dB</text><line x1="20" y1="70" x2="200" y2="70" stroke="var(--snr-bad)" stroke-width="3" stroke-linecap="round"/><text x="210" y="74" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">&lt; −10 dB</text><line x1="20" y1="96" x2="200" y2="96" stroke="var(--snr-mid)" stroke-width="3" stroke-linecap="round" stroke-dasharray="8 6"/><text x="210" y="100" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">da traceroute</text></svg>';
  var extra = '<svg width="100%" height="76" style="background:var(--map-land);border-radius:12px"><circle cx="50" cy="38" r="30" fill="var(--src-mqtt)" fill-opacity=".13" stroke="var(--src-mqtt)" stroke-width="1.5" stroke-dasharray="4 4"/><g transform="translate(50 38)">' + H.nodeMarker({ x: 0, y: 0, min: 130, src: "mqtt" }, 0) + '</g><text x="96" y="42" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">Posizione approssimata</text><g transform="translate(260 38)"><circle r="17" fill="var(--surface-raised)" stroke="var(--accent)" stroke-width="3"/><text text-anchor="middle" y="5" font-family="var(--font-mono)" font-weight="600" font-size="14" fill="var(--ink)">12</text></g><text x="290" y="42" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">Cluster</text></svg>';
  var cov = '<svg width="100%" height="60" style="background:var(--map-land);border-radius:12px"><g transform="translate(24 30)"><circle r="12" fill="var(--ink)" stroke="var(--brand-amber)" stroke-width="3.5"/><circle r="3.5" fill="var(--bg)"/></g><circle cx="70" cy="30" r="6" fill="var(--snr-good)" stroke="var(--marker-outline)" stroke-width="1.5"/><circle cx="92" cy="30" r="6" fill="var(--snr-mid)" stroke="var(--marker-outline)" stroke-width="1.5"/><circle cx="114" cy="30" r="6" fill="var(--snr-bad)" stroke="var(--marker-outline)" stroke-width="1.5"/><g transform="translate(136 30)"><circle r="6" fill="var(--surface)" stroke="var(--snr-none)" stroke-width="2"/><path d="M-3 -3 L3 3 M3 -3 L-3 3" stroke="var(--snr-none)" stroke-width="1.6"/></g><text x="160" y="34" fill="var(--map-label)" font-size="12" font-family="var(--font-sans)">Base · SNR · punto mancante</text></svg>';
  var popup = '<div style="position:relative;height:150px;' + bg + '"><div class="popup" style="left:12px;top:6px;position:absolute"><div class="row"><span class="grow nm">Nodo Duomo</span>' + H.srcMark("both") + '</div><div class="sub mono">!09ac5be7 · CLIENT</div><div class="row" style="gap:12px">' + H.dot(47) + "<span>47 min fa</span>" + H.battBadge(85) + H.snrBadge(-3.5) + "</div></div></div>";
  var legend = '<div style="position:relative;height:300px;' + bg + '">' + (function () { var c = S.shell; return ""; })() + "</div>";
  return sub("Marker: fonte (forma dell’anello) × ultimo contatto (riempimento) · stella = Mio nodo", '<div style="' + bg + '">' + cols + "</div>") + sub("Collegamenti per SNR", lines) + sub("Precisione e cluster", extra) + sub("Range Test", cov) + sub("Popup del nodo", popup) + sub("Controlli e indicatore offline", '<div style="position:relative;height:90px;background:var(--map-water);border-radius:12px"><div class="maptag" style="left:12px;top:12px;position:absolute">' + I("cloudoff", 16) + ' Mappa offline <span class="muted">· copia del 12 nov</span></div><div class="mapctl" style="right:12px;top:12px;position:absolute"><button aria-label="Ingrandisci">' + I("plus", 18) + '</button><button aria-label="Riduci">' + I("minus", 18) + "</button></div></div>");
};
SPEC.legendfull = function () { return ""; };
SPEC.nav = function (th) {
  var ctx = { vp: "desktop", theme: th };
  return sub("Barra superiore con stato (desktop)", '<div class="frame" style="width:100%;height:auto;border-radius:12px">' + NS.topbar(ctx, "mappa") + "</div>") + sub("Barra con MQTT non connesso", '<div class="frame" style="width:100%;height:auto;border-radius:12px">' + NS.topbar(ctx, "rete", "down") + "</div>") +
    sub("Telefono: stato compatto in alto, cinque voci in basso", '<div class="vp-phone" style="display:flex;flex-direction:column;gap:12px;max-width:378px"><div class="frame" style="width:100%;height:auto;border-radius:12px">' + NS.topbar({ vp: "phone" }, "mappa") + '</div><div class="frame" style="width:100%;height:auto;border-radius:12px">' + NS.bnav("mappa") + '</div><div class="frame" style="width:100%;height:auto;border-radius:12px">' + NS.bnav("rete") + "</div></div>") + '<div class="hint">“Altro” raccoglie Rete, Radio e Impostazioni e mostra il numero degli avvisi.</div>';
};
SPEC.datacolors = function () {
  var sw = function (v, t, n) { return '<div class="row" style="gap:10px"><span style="width:34px;height:34px;border-radius:8px;background:var(' + v + ');border:1px solid var(--line-strong)"></span><div><div class="nm">' + t + '</div><div class="caption mono">' + n + "</div></div></div>"; };
  return sub("Ultimo contatto", '<div class="col" style="gap:8px">' + sw("--contact-fresh", "Meno di 2 h", "contact-fresh") + sw("--contact-recent", "Meno di 24 h", "contact-recent") + sw("--contact-old", "Oltre 24 h", "contact-old") + "</div>") +
    sub("SNR (con segno ▲ ● ▼ e valore)", '<div class="col" style="gap:8px">' + sw("--snr-good", "0 dB o più", "snr-good") + sw("--snr-mid", "Da −10 a 0 dB", "snr-mid") + sw("--snr-bad", "Sotto −10 dB", "snr-bad") + sw("--snr-none", "Sconosciuto o mancante", "snr-none") + "</div>") +
    sub("Fonte (forma dell’anello)", '<div class="col" style="gap:8px"><div class="row" style="gap:10px">' + H.srcMark("radio", 34) + '<div><div class="nm">Radio</div><div class="caption mono">src-radio · anello pieno</div></div></div><div class="row" style="gap:10px">' + H.srcMark("mqtt", 34) + '<div><div class="nm">MQTT</div><div class="caption mono">src-mqtt · anello tratteggiato</div></div></div><div class="row" style="gap:10px">' + H.srcMark("both", 34) + '<div><div class="nm">Radio + MQTT</div><div class="caption mono">src-both · doppio anello</div></div></div></div>') +
    '<div class="hint">Verde e rosso si distinguono poco per chi ha un daltonismo: per questo ogni valore porta anche un segno, un numero o una forma.</div>';
};
SPEC.logo = function (th) {
  var g = th;
  var sizes = [16, 24, 32, 48, 64, 128, 256].map(function (s) { return '<div class="col" style="align-items:center;gap:4px">' + appIcon(s, s <= 32) + '<span class="caption mono">' + s + "</span></div>"; }).join("");
  return sub("Marchio proposto, con scritta", '<div class="row" style="gap:14px">' + logoSvg(72, g) + '<div class="t-lg" style="font-size:34px;line-height:40px">MeshLens</div></div>') +
    sub("Marchio in uso oggi (invariato)", '<div class="row" style="gap:14px">' + oldLogo(72) + '<span class="muted">Stessi colori; reticolo esterno più fitto, lente senza nodi dentro.</span></div>') +
    sub("Icona dell’app: 16–32 px versione semplificata, da 48 px quella completa", '<div class="sample" style="align-items:flex-end">' + sizes + "</div>");
};
SPEC.compat = function (th) {
  var slot = function (txt) { return '<span class="compat"><span class="slot" aria-hidden="true">LOGO</span><span>' + txt + "</span></span>"; };
  return sub("Badge di compatibilità (il riquadro tratteggiato è il posto del logo ufficiale)", row(slot("Compatibile con Meshtastic®"))) +
    sub("Versione solo testo", row('<span class="compat"><span>Compatibile con Meshtastic®</span></span>')) +
    sub("Dichiarazione di non affiliazione", '<p class="caption" style="max-width:420px">MeshLens non è affiliato al progetto Meshtastic. Meshtastic® è un marchio registrato di Meshtastic LLC.</p>') +
    sub("Dove compare", '<ul class="muted" style="margin:0;padding-left:18px"><li>Schermata di accesso, sotto il riquadro del PIN.</li><li>Impostazioni → Informazioni e licenze.</li><li>Piè di pagina delle Impostazioni.</li></ul>') +
    sub("Telefono", ph(row(slot("Compatibile con Meshtastic®"))));
};
SPEC.icons = function () {
  return '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:10px">' + NS.iconNames.map(function (n) { return '<div class="col" style="align-items:center;gap:6px;padding:10px 4px;border:1px solid var(--line);border-radius:8px;background:var(--surface)">' + I(n, 24) + '<span class="caption mono">' + n + "</span></div>"; }).join("") + "</div>" + '<div class="hint">Set di segnaposto nello stile di Lucide (tratto 1,75 px, griglia 24). In produzione si usa Lucide (licenza ISC).</div>';
};
SPEC.flags = function () { return ""; };

/* ---------- guscio delle schermate ---------- */
function mountScreen(id) {
  var sc = S[id], root = document.getElementById("root"); root.className = "ml";
  var ctx = { vp: "desktop", theme: "dark", st: sc.states[0][0] };
  function draw() {
    var seg = function (key, items, cur) { return '<div class="seg" role="tablist">' + items.map(function (x) { return '<button data-k="' + key + '" data-v="' + x[0] + '" class="' + (x[0] === cur ? "on" : "") + '">' + x[1] + "</button>"; }).join("") + "</div>"; };
    var h = '<div class="stage"><div class="tools"><span class="lbl">Vista</span>' + seg("vp", [["desktop", "Desktop"], ["phone", "Telefono"]], ctx.vp) + '<span class="lbl">Tema</span>' + seg("theme", [["dark", "Scuro"], ["light", "Chiaro"]], ctx.theme) + '<span class="lbl">Stato</span>' + seg("st", sc.states, ctx.st) + '</div><div style="display:flex;justify-content:center">' + sc.render(ctx) + "</div></div>";
    root.innerHTML = h;
  }
  root.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button[data-k]"); if (!b) return;
    ctx[b.getAttribute("data-k")] = b.getAttribute("data-v"); draw();
  });
  draw();
}
NS.mountScreen = mountScreen;
})();
