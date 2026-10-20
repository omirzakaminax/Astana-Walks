/* Astana Walks — pure helpers shared by the page and the tests (no DOM, no network).
   Exports: escapeHtml, safeUrl, displayName, nameInfo, nameLine, directionsUrl, planText, planHtml,
   bingoTasks, carryBingo. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AWPlan = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function escapeHtml(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /** Only http(s) links survive; everything else (javascript:, data:, relative) becomes null. */
  function safeUrl(u) {
    if (typeof u !== "string") return null;
    var t = u.trim();
    if (!/^https?:\/\/[^\s"'<>]+$/i.test(t)) return null;
    return t;
  }

  /* Names come from the server (walks/names.py) for all three languages, with provenance:
     poi.display_names[lang] = {text, kind: override|osm|wikidata|osm_latin|original|generated,
     descriptor?, translation?, latin?}. The page never invents or transliterates names itself. */
  function nameInfo(poi, lang) {
    if (!poi) return { text: "", kind: "original" };
    var d = poi.display_names && poi.display_names[lang];
    if (d && d.text) return d;
    return { text: poi.display_name || poi.name || "", kind: "original" };
  }

  /** Name in the interface language (sourced), else the original name unchanged. */
  function displayName(poi, lang, unnamedLabel) {
    if (!poi) return "";
    if (poi.name_is_generated && unnamedLabel) return unnamedLabel;
    return nameInfo(poi, lang).text;
  }

  /** One-line name for exports and plain text: "Атырау көпірі (≈ Atyrau Bridge, descriptive translation)". */
  function nameLine(poi, lang, T) {
    var d = nameInfo(poi, lang), out = d.text;
    if (d.translation) out += " (≈ " + d.translation + ", " + T("name_descr_tr") + ")";
    return out;
  }

  /* External walking directions (opened only on an explicit click). Google Maps URLs (api=1,
     travelmode=walking) and OpenStreetMap's foot routing. Coordinates are rounded to 5 decimals.
     A private start (typed or device location) is only included when includeStart is true. */
  function ll(p) { return Number(p.lat).toFixed(5) + "," + Number(p.lon).toFixed(5); }
  function directionsUrl(points, opts) {
    opts = opts || {};
    var pts = (points || []).filter(function (p) { return p && isFinite(p.lat) && isFinite(p.lon); });
    if (pts.length < 2) return null;
    var origin = pts[0], dest = pts[pts.length - 1], mid = pts.slice(1, -1);
    if (opts.provider === "osm") {
      if (mid.length) return null;   // OSM's directions page handles one leg only
      return "https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route=" +
        encodeURIComponent(ll(origin) + ";" + ll(dest));
    }
    var u = "https://www.google.com/maps/dir/?api=1";
    if (!origin.private || opts.includeStart) u += "&origin=" + encodeURIComponent(ll(origin));
    u += "&destination=" + encodeURIComponent(ll(dest)) + "&travelmode=walking";
    if (mid.length) u += "&waypoints=" + encodeURIComponent(mid.map(ll).join("|"));
    return u;
  }

  /** Short description from Wikipedia/Wikidata in the requested language (or a fallback). */
  function about(poi, lang) {
    var s = poi && poi.media && poi.media.summary; if (!s) return null;
    return s[lang] || s.en || s.ru || s.kk || null;
  }

  function fmt(tpl, p) {
    return String(tpl).replace(/\{(\w+)\}/g, function (_, k) { return p && p[k] !== undefined && p[k] !== null ? p[k] : ""; });
  }

  /** opts: {T(key), lang, plan, startLabel, startCoords|null, datasetDate, deadline|null, catLabel(cat), unnamed} */
  function planLines(opts) {
    var T = opts.T, plan = opts.plan, L = [];
    L.push(T("ex_title"));
    L.push(fmt(T("ex_start"), { s: opts.startLabel }) + (opts.startCoords ? " (" + opts.startCoords + ")" : ""));
    L.push(fmt(T("ex_total"), { total: plan.total_min, budget: plan.budget_min, walk: plan.walk_min, eta: plan.end_eta }));
    if (opts.deadline) L.push(fmt(T("ex_deadline"), { at: opts.deadline.at_time, buffer: opts.deadline.buffer_min }));
    L.push("");
    plan.stops.forEach(function (s) {
      var name = s.poi.name_is_generated ? displayName(s.poi, opts.lang, opts.unnamed) : nameLine(s.poi, opts.lang, T);
      L.push(s.n + ". " + name + " (" + opts.catLabel(s.poi.category) + ")");
      L.push("   " + fmt(T("ex_stop"), { walk: s.walk_from_prev_min, m: s.distance_from_prev_m, arrive: s.arrive_at, visit: s.visit_minutes }));
      var ab = about(s.poi, opts.lang);
      if (ab) L.push("   " + ab.text);
      var url = safeUrl(s.poi.source_url);
      if (url) L.push("   " + T("ex_source") + ": " + url);
    });
    if (plan.return_to_start && plan.legs.length) {
      var back = plan.legs[plan.legs.length - 1];
      L.push(fmt(T("ex_back"), { walk: back.walk_min, eta: plan.end_eta }));
    }
    L.push("");
    L.push(T("ex_estimate"));
    L.push(fmt(T("ex_data"), { d: opts.datasetDate || "?" }));
    return L;
  }

  function planText(opts) { return planLines(opts).join("\n"); }

  function planHtml(opts) {
    var T = opts.T, plan = opts.plan, e = escapeHtml;
    var rows = plan.stops.map(function (s) {
      var url = safeUrl(s.poi.source_url);
      var link = url ? '<a href="' + e(url) + '">' + e(T("ex_source")) + "</a>" : "";
      var ab = about(s.poi, opts.lang);
      var abt = ab ? "<p>" + e(ab.text) + (safeUrl(ab.url) ? ' <a href="' + e(safeUrl(ab.url)) + '">' + e(ab.source) + "</a>" : "") + "</p>" : "";
      var why = abt + (s.why ? "<p>" + e(s.why) + "</p>" : "");
      var act = s.activity ? "<p><b>" + e(T("activity")) + ":</b> " + e(s.activity) + "</p>" : "";
      var nm = s.poi.name_is_generated ? displayName(s.poi, opts.lang, opts.unnamed) : nameLine(s.poi, opts.lang, T);
      return "<li><h2>" + e(s.n + ". " + nm) + "</h2>" +
        "<p class=m>" + e(opts.catLabel(s.poi.category)) + "</p>" +
        "<p>" + e(fmt(T("ex_stop"), { walk: s.walk_from_prev_min, m: s.distance_from_prev_m, arrive: s.arrive_at, visit: s.visit_minutes })) + "</p>" +
        why + act + "<p class=m>" + link + "</p></li>";
    }).join("");
    var back = "";
    if (plan.return_to_start && plan.legs.length) {
      var b = plan.legs[plan.legs.length - 1];
      back = "<p>" + e(fmt(T("ex_back"), { walk: b.walk_min, eta: plan.end_eta })) + "</p>";
    }
    var dl = opts.deadline ? "<p>" + e(fmt(T("ex_deadline"), { at: opts.deadline.at_time, buffer: opts.deadline.buffer_min })) + "</p>" : "";
    return "<!doctype html><html lang=\"" + e(opts.lang) + "\"><head><meta charset=\"utf-8\">" +
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>" + e(T("ex_title")) + "</title>" +
      "<style>body{font:16px/1.55 system-ui,'Segoe UI',sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#16243F;background:#F0F3FA}" +
      "h1{color:#395886;font-size:1.5rem}h2{font-size:1.1rem;margin:0 0 4px}ol{padding:0;list-style:none}" +
      "li{background:#fff;border:1px solid #B1C9EF;border-radius:14px;padding:14px 16px;margin:0 0 12px}" +
      ".m{color:#455A80;font-size:.9rem}a{color:#395886}</style></head><body>" +
      "<h1>" + e(T("ex_title")) + "</h1>" +
      "<p>" + e(fmt(T("ex_start"), { s: opts.startLabel })) + (opts.startCoords ? " (" + e(opts.startCoords) + ")" : "") + "</p>" +
      "<p><b>" + e(fmt(T("ex_total"), { total: plan.total_min, budget: plan.budget_min, walk: plan.walk_min, eta: plan.end_eta })) + "</b></p>" +
      dl + "<ol>" + rows + "</ol>" + back +
      "<p class=m>" + e(T("ex_estimate")) + "</p><p class=m>" + e(fmt(T("ex_data"), { d: opts.datasetDate || "?" })) + "</p>" +
      "<p class=m>" + e(T("ex_offline")) + "</p></body></html>";
  }

  /* City Bingo: about three self-reported micro-missions from the plan's places.
     Suggestions only — no facts, no trivia. Keys include the place ID so that completion
     never carries over to a different place after a replacement. */
  var TEMPLATES = {
    park: "bg_bench", playground: "bg_play", museum: "bg_exhibit", gallery: "bg_exhibit", arts_centre: "bg_exhibit",
    artwork: "bg_sides", fountain: "bg_sides", attraction: "bg_detail", viewpoint: "bg_view", cafe: "bg_new",
    restaurant: "bg_new", fast_food: "bg_new", ice_cream: "bg_new", mall: "bg_detail", worship: "bg_quiet_look",
    theatre: "bg_detail", library: "bg_book", stadium: "bg_detail", campus: "bg_detail", zoo: "bg_animal"
  };

  function bingoTasks(stops) {
    var tasks = [];
    (stops || []).slice(0, 3).forEach(function (s) {
      tasks.push({ key: s.id + ":" + (TEMPLATES[s.poi.category] || "bg_detail"), poi_id: s.id, tpl: TEMPLATES[s.poi.category] || "bg_detail", n: s.n });
    });
    if (tasks.length < 3) tasks.push({ key: "walk:bg_photo", poi_id: null, tpl: "bg_photo", n: null });
    if (tasks.length < 3) tasks.push({ key: "walk:bg_colour", poi_id: null, tpl: "bg_colour", n: null });
    return tasks.slice(0, 3);
  }

  /** Keep "done" only for tasks whose key (place + mission) still exists. */
  function carryBingo(oldDone, tasks) {
    var out = {};
    tasks.forEach(function (t) { if (oldDone && oldDone[t.key]) out[t.key] = true; });
    return out;
  }

  return { escapeHtml: escapeHtml, safeUrl: safeUrl, displayName: displayName, nameInfo: nameInfo, nameLine: nameLine,
           directionsUrl: directionsUrl, fmt: fmt,
           planText: planText, planHtml: planHtml, about: about, bingoTasks: bingoTasks, carryBingo: carryBingo };
});
