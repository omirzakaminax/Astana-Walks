/* Astana Walks — front end (no framework).
   Texts: i18n.js + i18n2.js. Pure helpers: plan.js. Data: /api/meta, /api/recommend, /api/replace, /api/replan.
   ONE canonical plan (state.plan, from the server) drives cards, map numbers, timeline, exports and Bingo. */
(function () {
  "use strict";

  var root = document.documentElement;
  var AW = window.AWPlan;
  var store = {
    ok: (function () { try { var k = "__aw"; localStorage.setItem(k, "1"); localStorage.removeItem(k); return true; } catch (e) { return false; } })(),
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: ignore */ } },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
    getJSON: function (k, d) { try { var v = JSON.parse(localStorage.getItem(k)); return v === null ? d : v; } catch (e) { return d; } }
  };

  var state = {
    lang: root.getAttribute("lang") || "ru",
    meta: null,
    mode: "landmark",
    startId: null,
    minutes: 60,
    coordsText: "51.0890, 71.4160",
    geo: null,
    interests: [],
    pace: ["leisurely", "normal", "brisk"].indexOf(store.get("aw-pace")) >= 0 ? store.get("aw-pace") : "normal",
    deadline: { on: false, date: "", time: "", buffer: 10 },
    outdoor: { sel: "off", custom: 10, strict: false },
    group: { on: false, people: [] },
    remember: store.get("aw-remember") === "1",
    visited: store.get("aw-remember") === "1" ? store.getJSON("aw-visited", []) : [],
    unavailable: [],
    other: [],
    seq: 0,
    busy: false,
    result: null,
    resultLang: null,
    lastBody: null,
    plan: null,
    flags: {},          // per-stop: "unavailable"
    cardMsg: {},        // per-stop message key
    actionMsg: null,    // {kind, text}
    surprise: { history: [] },
    bingo: { done: {} },
    passportOn: store.get("aw-passport-on") === "1",
    includeCoords: false,
    exportText: null,
    clockOffset: 0,
    timer: null,
    map: null,
    places: {},          // id -> brief place (names in all languages) from /api/meta and /api/places
    picker: { open: false, items: [], active: -1, q: "", loading: false, seq: 0, timer: null },
    filters: { known_hours: false, wheelchair: false },
    walk: null,          // active walk: {startedMs, done: [], origin: {start, label}, budget}
    dirIncludeStart: false,
    reportFor: null,     // stop id whose report form is open
    reports: store.getJSON("aw-reports", []),
    pickMap: null,
    gallery: null,
    guess: { on: false, right: 0, tried: 0, solved: {} }
  };

  // ------------------------------------------------------------------ helpers
  function T(key) {
    var d = window.I18N[state.lang] || window.I18N.ru;
    return d[key] !== undefined ? d[key] : (window.I18N.en[key] !== undefined ? window.I18N.en[key] : key);
  }
  var fmt = AW.fmt;
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function num(n) { try { return new Intl.NumberFormat(state.lang === "kk" ? "kk-KZ" : state.lang).format(n); } catch (e) { return String(n); } }
  function catLabel(key) { var c = state.meta && state.meta.labels.categories[key]; return c ? (c[state.lang] || c.en) : key; }
  function intentLabel(key) { var c = state.meta && state.meta.labels.intents[key]; return c ? (c[state.lang] || c.en) : key; }
  function placeName(poi) { return AW.displayName(poi, state.lang, T("unnamed_playground")); }
  function rememberPlaces(list) { (list || []).forEach(function (p) { if (p && p.id) state.places[p.id] = p; }); }
  function minLabel() { return state.lang === "en" ? "min" : "мин"; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function svgIcon(path) {
    var s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true");
    s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "2");
    s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
    path.split("|").forEach(function (d) { var p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", d); s.appendChild(p); });
    return s;
  }
  var ICON_SRC = "M20 6 9 17l-5-5";
  var ICON_AI = "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z|M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z";
  var ICON_SPEAK = "M11 5 6 9H3v6h3l5 4z|M15.5 8.5a5 5 0 0 1 0 7|M18.5 5.5a9 9 0 0 1 0 13";
  function astanaMs(s) { // "YYYY-MM-DDTHH:MM" in Astana time (UTC+5) -> epoch ms
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s || ""); if (!m) return NaN;
    return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] - 5, +m[5]);
  }
  function astanaParts(ms) { var d = new Date(ms + 5 * 3600000); return { date: d.toISOString().slice(0, 10), time: d.toISOString().slice(11, 16) }; }

  // ------------------------------------------------------------------ static texts / preferences
  function applyStaticTexts() {
    root.setAttribute("lang", state.lang);
    document.querySelectorAll("[data-i18n]").forEach(function (n) { n.textContent = T(n.getAttribute("data-i18n")); });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (n) { n.setAttribute("aria-label", T(n.getAttribute("data-i18n-aria"))); });
    document.querySelectorAll("[data-lang]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === state.lang)); });
    document.querySelectorAll("[data-pace]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-pace") === state.pace)); });
    document.getElementById("query").setAttribute("placeholder", T("request_placeholder"));
    var f = state.meta ? state.meta.labels.detour_factor : 1.3;
    document.getElementById("paceHelp").textContent = fmt(T("pace_help"), { f: String(f).replace(".", state.lang === "en" ? "." : ",") });
    var dark = root.getAttribute("data-theme") === "dark";
    var tb = document.getElementById("themeBtn");
    tb.setAttribute("aria-pressed", String(dark));
    tb.querySelector("span").textContent = dark ? T("light_theme") : T("dark_theme");
    document.getElementById("visionBtn").setAttribute("aria-pressed", String(root.getAttribute("data-vision") === "on"));
    document.getElementById("submit").textContent = state.busy ? T("searching") : T("submit");
    renderOutdoorSelect(); renderDeadlineReturn(); renderReset();
  }

  function setLang(lang) {
    state.lang = lang; store.set("aw-lang", lang);
    applyStaticTexts(); renderSentence(); renderChips(); renderExamples(); renderFooter(); renderGroup();
    if (state.result) renderResult(); else renderEmpty();
    renderDiscover();
  }

  // ------------------------------------------------------------------ planner
  function renderSentence() {
    var h = document.getElementById("sentence");
    h.textContent = "";
    T("sentence_" + state.mode).split(/(\{start\}|\{time\})/).forEach(function (part) {
      if (part === "{start}") h.appendChild(startSlot());
      else if (part === "{time}") h.appendChild(timeSlot());
      else if (part) h.appendChild(document.createTextNode(part));
    });
    document.getElementById("geoBtn").hidden = state.mode !== "geo";
    var pm = document.getElementById("pickMapBox");
    if (pm) { pm.hidden = state.mode !== "map"; if (state.mode === "map") setTimeout(drawPickMap, 0); }
    renderDeadlineReturn();
  }

  function landmarkName(lm) { return lm ? AW.displayName(lm, state.lang) : ""; }
  function currentStartName() { var p = state.places[state.startId]; return p ? landmarkName(p) : ""; }

  function startSlot() {
    var wrap = el("span", { class: "slot" });
    if (state.mode === "coords" || state.mode === "map") {
      var inp = el("input", { class: "coords", id: "coordsInput", type: "text", inputmode: "decimal", value: state.coordsText, "aria-label": T("coords_input"), autocomplete: "off" });
      inp.addEventListener("input", function () { state.coordsText = inp.value; if (state.mode === "map") drawPickMarker(); });
      wrap.appendChild(inp);
      return wrap;
    }
    return startPicker(wrap);
  }

  // ---------- searchable start picker (combobox + listbox, keyboard and touch)
  function startPicker(wrap) {
    wrap.className = "slot picker";
    var input = el("input", { type: "text", id: "pickInput", role: "combobox", "aria-expanded": "false", "aria-controls": "pickList",
      "aria-autocomplete": "list", "aria-label": T("picker_label"), placeholder: T("picker_ph"), value: currentStartName(),
      autocomplete: "off", spellcheck: "false", autocapitalize: "off" });
    var list = el("ul", { id: "pickList", role: "listbox", class: "pick-list", "aria-label": T("picker_label") });
    list.hidden = true;
    var live = el("span", { class: "sr-only", role: "status", id: "pickStatus" });
    input.addEventListener("focus", function () { try { input.select(); } catch (e) { /* ignore */ } openPicker(""); });
    input.addEventListener("input", function () {
      var q = input.value.trim(); state.picker.q = q;
      clearTimeout(state.picker.timer);
      state.picker.timer = setTimeout(function () { openPicker(q); }, 180);
    });
    input.addEventListener("keydown", function (e) {
      var P = state.picker, opts = P.items.filter(function (x) { return !x.header; });
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!P.open) { openPicker(input.value.trim() === currentStartName() ? "" : input.value.trim()); return; }
        if (!opts.length) return;
        P.active = (P.active + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
        renderPickList();
      } else if (e.key === "Enter") {
        if (P.open && P.active >= 0 && opts[P.active]) { e.preventDefault(); choosePlace(opts[P.active].place); }
      } else if (e.key === "Escape") {
        if (P.open) { e.preventDefault(); closePicker(true); }
      } else if (e.key === "Tab") closePicker(true);
    });
    input.addEventListener("blur", function () { setTimeout(function () { if (document.activeElement !== input) closePicker(true); }, 200); });
    wrap.appendChild(input); wrap.appendChild(list); wrap.appendChild(live);
    return wrap;
  }

  function pickerSuggestions() {
    var groups = { demo: [], linked: [], sights: [] }, out = [];
    ((state.meta && state.meta.landmarks) || []).forEach(function (p) { (groups[p.group] || groups.sights).push(p); });
    ["demo", "linked", "sights"].forEach(function (g) {
      if (!groups[g].length) return;
      out.push({ header: T("picker_groups")[g] });
      groups[g].forEach(function (p) { out.push({ place: p }); });
    });
    return out;
  }

  function openPicker(q) {
    var P = state.picker; P.open = true; P.q = q; P.active = -1;
    if (!q) { P.loading = false; P.items = pickerSuggestions(); renderPickList(); return; }
    var my = ++P.seq; P.loading = true; renderPickList();
    fetch("/api/places?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (j) {
      if (my !== P.seq) return;                  // a newer search was started
      P.loading = false;
      rememberPlaces(j.results);
      P.items = (j.results || []).length ? [{ header: T("picker_groups").results }].concat(j.results.map(function (p) { return { place: p }; })) : [];
      P.searched = j.searched;
      P.active = P.items.length > 1 ? 0 : -1;
      renderPickList();
    }).catch(function () { if (my === P.seq) { P.loading = false; P.items = []; renderPickList(); } });
  }

  function renderPickList() {
    var list = document.getElementById("pickList"), input = document.getElementById("pickInput"), live = document.getElementById("pickStatus");
    if (!list || !input) return;
    var P = state.picker;
    list.textContent = "";
    list.hidden = !P.open;
    input.setAttribute("aria-expanded", String(P.open));
    if (!P.open) { input.removeAttribute("aria-activedescendant"); return; }
    if (P.loading) { list.appendChild(el("li", { class: "pick-note", role: "presentation", text: T("picker_loading") })); return; }
    if (!P.items.length) {
      var n = (state.meta && state.meta.dataset && state.meta.dataset.count) || 0;
      list.appendChild(el("li", { class: "pick-note", role: "presentation", text: P.q ? fmt(T("picker_none"), { q: P.q, n: n }) : T("picker_hint") }));
      if (live) live.textContent = P.q ? fmt(T("picker_none"), { q: P.q, n: n }) : "";
      return;
    }
    var idx = 0, count = 0;
    P.items.forEach(function (it) {
      if (it.header) { list.appendChild(el("li", { class: "pick-grp", role: "presentation", text: it.header })); return; }
      var i = idx++, p = it.place, name = landmarkName(p);
      var orig = p.display_names && p.display_names[state.lang] && p.display_names[state.lang].original;
      var sub = [catLabel(p.category)];
      if (p.address) sub.push(p.address);
      if (orig && orig !== name) sub.push(orig);
      var li = el("li", { role: "option", id: "pickOpt-" + i, class: "pick-opt", "aria-selected": String(i === P.active) }, [
        el("span", { class: "pick-name", text: name }), el("span", { class: "pick-sub", text: sub.join(" · ") })]);
      li.addEventListener("mousedown", function (e) { e.preventDefault(); });
      li.addEventListener("click", function () { choosePlace(p); });
      list.appendChild(li); count++;
    });
    if (P.active >= 0) {
      input.setAttribute("aria-activedescendant", "pickOpt-" + P.active);
      var a = document.getElementById("pickOpt-" + P.active); if (a && a.scrollIntoView) a.scrollIntoView({ block: "nearest" });
    } else input.removeAttribute("aria-activedescendant");
    if (live && P.q) live.textContent = fmt(T("picker_count"), { n: count });
  }

  function closePicker(restore) {
    state.picker.open = false; state.picker.loading = false; renderPickList();
    var input = document.getElementById("pickInput");
    if (restore && input) input.value = currentStartName();
  }

  function choosePlace(p) {
    rememberPlaces([p]);
    state.startId = p.id;
    closePicker(false);
    var input = document.getElementById("pickInput"); if (input) input.value = landmarkName(p);
    renderDeadlineReturn();
  }

  // ---------- choose the start on a map (coordinates mode with a map)
  function drawPickMap() {
    var box = document.getElementById("pickMap"); if (!box) return;
    if (!window.L && !state.leafletTried) { loadLeafletFallback(drawPickMap); return; }
    if (!window.L) { box.textContent = T("map_unavailable"); return; }
    if (state.pickMap) { state.pickMap.invalidateSize(); drawPickMarker(); return; }
    var c = (state.meta && state.meta.center) || { lat: 51.128, lon: 71.43 };
    var map = L.map(box, { scrollWheelZoom: false }).setView([c.lat, c.lon], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap", referrerPolicy: "strict-origin-when-cross-origin" }).addTo(map);
    ((state.meta && state.meta.coverage) || []).forEach(function (a) {
      if (a.radius_m) L.circle([a.lat, a.lon], { radius: a.radius_m, color: "#395886", weight: 1, fillOpacity: 0.08 }).addTo(map);
      else if (a.bbox) L.rectangle([[a.bbox[0], a.bbox[1]], [a.bbox[2], a.bbox[3]]], { color: "#8AAEE0", weight: 1, fill: false, dashArray: "4 6" }).addTo(map);
    });
    map.on("click", function (e) {
      state.coordsText = e.latlng.lat.toFixed(5) + ", " + e.latlng.lng.toFixed(5);
      var inp = document.getElementById("coordsInput"); if (inp) inp.value = state.coordsText;
      drawPickMarker();
      document.getElementById("pickMapMsg").textContent = fmt(T("map_pick_set"), { c: state.coordsText });
    });
    state.pickMap = map;
    drawPickMarker();
  }
  function drawPickMarker() {
    var map = state.pickMap; if (!map || !window.L) return;
    var parts = (state.coordsText || "").split(/[\s,;]+/).filter(Boolean).map(Number);
    if (state.pickMarker) { map.removeLayer(state.pickMarker); state.pickMarker = null; }
    if (parts.length === 2 && isFinite(parts[0]) && isFinite(parts[1])) {
      state.pickMarker = L.marker([parts[0], parts[1]], { icon: L.divIcon({ className: "", html: '<div class="marker-start"></div>', iconSize: [22, 22], iconAnchor: [11, 11] }), keyboard: false }).addTo(map);
    }
  }

  function timeSlot() {
    var wrap = el("span", { class: "slot" });
    var inp = el("input", { type: "number", min: "15", max: "240", step: "5", value: String(state.minutes), "aria-label": T("time_input") });
    inp.addEventListener("input", function () { var v = parseInt(inp.value, 10); if (!isNaN(v)) state.minutes = Math.max(5, Math.min(720, v)); syncPersonOne(); });
    var step = el("span", { class: "stepper" }, [
      el("button", { type: "button", "aria-label": T("plus15"), text: "▲", onclick: function () { state.minutes = Math.min(240, state.minutes + 15); inp.value = state.minutes; syncPersonOne(); } }),
      el("button", { type: "button", "aria-label": T("minus15"), text: "▼", onclick: function () { state.minutes = Math.max(15, state.minutes - 15); inp.value = state.minutes; syncPersonOne(); } })
    ]);
    wrap.appendChild(inp); wrap.appendChild(step);
    return wrap;
  }

  function renderChips() {
    var box = document.getElementById("chips"); box.textContent = "";
    var keys = state.meta ? Object.keys(state.meta.labels.intents) : [];
    keys.forEach(function (k) {
      box.appendChild(el("button", {
        type: "button", class: "chip", "aria-pressed": String(state.interests.indexOf(k) >= 0), text: intentLabel(k),
        onclick: function (e) {
          var i = state.interests.indexOf(k);
          if (i >= 0) state.interests.splice(i, 1); else state.interests.push(k);
          e.currentTarget.setAttribute("aria-pressed", String(i < 0));
          syncPersonOne();
        }
      }));
    });
  }

  function renderExamples() {
    var box = document.getElementById("examples"); box.textContent = "";
    box.appendChild(el("span", { text: T("examples_label") }));
    T("examples").forEach(function (ex) {
      box.appendChild(el("button", { type: "button", class: "example", text: ex, onclick: function () { var q = document.getElementById("query"); q.value = ex; q.focus(); } }));
    });
  }

  // ---------- more options: pace, deadline, outdoor, group, exclusions
  function renderOutdoorSelect() {
    var sel = document.getElementById("odSel"); if (!sel) return;
    sel.textContent = "";
    [["off", T("outdoor_off")], ["5", fmt(T("outdoor_min_n"), { n: 5 })], ["10", fmt(T("outdoor_min_n"), { n: 10 })],
     ["15", fmt(T("outdoor_min_n"), { n: 15 })], ["20", fmt(T("outdoor_min_n"), { n: 20 })], ["30", fmt(T("outdoor_min_n"), { n: 30 })],
     ["custom", T("outdoor_custom")]].forEach(function (o) {
      var op = el("option", { value: o[0], text: o[1] }); if (o[0] === state.outdoor.sel) op.selected = true; sel.appendChild(op);
    });
    document.getElementById("odCustomWrap").hidden = state.outdoor.sel !== "custom";
  }
  function outdoorMax() {
    if (state.outdoor.sel === "off") return null;
    if (state.outdoor.sel === "custom") return state.outdoor.custom;
    return parseInt(state.outdoor.sel, 10);
  }
  function startLabel() {
    if (state.mode === "landmark") return currentStartName() || T("ex_start_generic");
    return T("ex_start_generic");
  }
  /** Label of the start the CURRENT plan was computed from (not the form, which may have changed). */
  function planStartLabel() {
    var st = state.result && state.result.start;
    if (st && st.display_names) return AW.displayName({ display_names: st.display_names, name: st.name }, state.lang);
    if (st && st.kind === "walk") return T("walk_current");
    return T("ex_start_generic");
  }
  function returnLabel() { return state.walk ? state.walk.origin.label() : planStartLabel(); }
  function renderDeadlineReturn() {
    var n = document.getElementById("dlReturn"); if (!n) return;
    n.textContent = fmt(T("deadline_return"), { s: startLabel() });
    ["dlDate", "dlTime", "dlBuf"].forEach(function (id) { document.getElementById(id).disabled = !state.deadline.on; });
  }
  function exclusionCount() { return state.visited.length + state.unavailable.length + state.other.length; }
  function renderReset() {
    var b = document.getElementById("resetEx"); if (!b) return;
    b.textContent = fmt(T("reset_exclusions"), { n: exclusionCount() });
    b.disabled = exclusionCount() === 0;
    var rem = document.getElementById("remember");
    rem.checked = state.remember; rem.disabled = !store.ok;
  }
  function persistVisited() { if (state.remember) store.set("aw-visited", JSON.stringify(state.visited.slice(-300))); }

  function newPerson(i) {
    return i === 0 ? { interests: state.interests.slice(), minutes: state.minutes, pace: state.pace } : { interests: [], minutes: 60, pace: "normal" };
  }
  function syncPersonOne() {
    if (!state.group.on || !state.group.people.length) return;
    state.group.people[0] = { interests: state.interests.slice(), minutes: state.minutes, pace: state.pace };
    renderGroup();
  }
  function renderGroup() {
    var list = document.getElementById("grpList"), add = document.getElementById("grpAdd");
    if (!list) return;
    list.textContent = "";
    document.getElementById("grpOn").checked = state.group.on;
    add.hidden = !state.group.on || state.group.people.length >= 5;
    if (!state.group.on) return;
    var keys = state.meta ? Object.keys(state.meta.labels.intents) : [];
    state.group.people.forEach(function (p, i) {
      var chips = el("div", { class: "chips", role: "group", "aria-label": T("group_interests") });
      keys.forEach(function (k) {
        chips.appendChild(el("button", { type: "button", class: "chip", "aria-pressed": String(p.interests.indexOf(k) >= 0), text: intentLabel(k),
          disabled: i === 0 ? true : null,
          onclick: function (e) { var j = p.interests.indexOf(k); if (j >= 0) p.interests.splice(j, 1); else p.interests.push(k); e.currentTarget.setAttribute("aria-pressed", String(j < 0)); } }));
      });
      var mins = el("input", { type: "number", min: "5", max: "720", step: "5", value: String(p.minutes), disabled: i === 0 ? true : null });
      mins.addEventListener("input", function () { var v = parseInt(mins.value, 10); if (!isNaN(v)) p.minutes = v; });
      var pace = el("select", { disabled: i === 0 ? true : null });
      ["leisurely", "normal", "brisk"].forEach(function (k) { var o = el("option", { value: k, text: T("pace_" + k) }); if (k === p.pace) o.selected = true; pace.appendChild(o); });
      pace.addEventListener("change", function () { p.pace = pace.value; });
      list.appendChild(el("div", { class: "grp-row" }, [
        el("b", { text: i === 0 ? T("group_you") : fmt(T("group_person"), { n: i + 1 }) }),
        chips,
        el("label", {}, [el("span", { text: T("group_minutes") }), mins]),
        el("label", {}, [el("span", { text: T("group_pace") }), pace]),
        i >= 2 ? el("button", { type: "button", class: "geo-btn", text: T("group_remove"), onclick: function () { state.group.people.splice(i, 1); renderGroup(); } }) : el("span")
      ]));
    });
  }

  function renderFooter() {
    var m = state.meta, ms = document.getElementById("modelState");
    if (!m) return;
    var p = m.provider;
    ms.className = "model-state" + (p.ok ? "" : " bad");
    ms.querySelector("span").textContent = p.ok ? fmt(T("model_ready"), { model: p.model }) : fmt((T("model_bad")[p.code] || p.detail), { model: p.model });
    var ds = m.dataset;
    document.getElementById("datasetLine").textContent = ds ? fmt(T("dataset_line"), { n: ds.count, d: (ds.collected_at || "").slice(0, 10) }) + " " + fmt(T("coverage_note"), { n: ds.count }) : "";
    document.getElementById("synthetic").hidden = !(ds && ds.is_synthetic);
    var nd = document.getElementById("noData");
    nd.hidden = !!ds; if (!ds) nd.textContent = T("errors").no_dataset;
  }

  function renderEmpty() {
    var out = document.getElementById("output"); out.textContent = "";
    out.appendChild(el("p", { class: "empty", text: T("empty") }));
  }


  // ------------------------------------------------------------------ discover: place of the day + Astana in photos
  var SKY = '<svg viewBox="0 0 640 160" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 152H636"/><path d="M28 152 108 34l50 118"/><path d="M296 152V78M312 152V78"/><circle cx="304" cy="42" r="17"/><path d="M402 152 448 84l46 68"/><circle cx="580" cy="122" r="28"/></svg>';
  function photoBox(cls, media, alt) {
    var box = el("div", { class: cls });
    var ph = media && media.photo, src = ph && AW.safeUrl(ph.thumb);
    function fallback() {
      box.textContent = "";
      var d = el("div", { class: "ph" }); d.innerHTML = SKY;   // static markup, no data inside
      d.appendChild(el("span", { text: T("photo_offline") }));
      box.appendChild(d);
    }
    if (!src) { fallback(); return box; }
    var img = el("img", { src: src, alt: alt || "", loading: "lazy", decoding: "async", referrerpolicy: "strict-origin-when-cross-origin" });
    img.addEventListener("error", fallback);
    box.appendChild(img);
    return box;
  }
  function creditLine(media) {
    var ph = media && media.photo; if (!ph) return null;
    var page = AW.safeUrl(ph.page), lic = AW.safeUrl(ph.license_url);
    return el("p", { class: "credit" }, [fmt(T("photo_credit"), { author: ph.author || T("photo_author_unknown") }) + " ",
      lic ? el("a", { href: lic, target: "_blank", rel: "noopener noreferrer", text: ph.license }) : ph.license, ", ",
      page ? el("a", { href: page, target: "_blank", rel: "noopener noreferrer", text: "Wikimedia Commons" }) : "Wikimedia Commons"]);
  }
  function aboutText(p) {
    var a = aboutFor(p); if (!a) return null;
    var url = AW.safeUrl(a.v.url);
    return el("p", { class: "about-text" }, [el("span", { lang: a.lang, text: a.v.text }), " ",
      el("span", { class: "pill src", text: a.v.source === "Wikidata" ? T("badge_wikidata") : T("badge_wikipedia") }),
      url ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: " " + T("read_more") }) : null]);
  }
  function startHere(p) {
    rememberPlaces([p]);
    state.mode = "landmark";
    var r = document.querySelector('input[name="mode"][value="landmark"]'); if (r) r.checked = true;
    state.startId = p.id; renderSentence(); closeDialog();
    window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    var q = document.getElementById("query"); if (q) q.focus({ preventScroll: true });
  }
  function walkThere(p) {
    closeDialog();
    document.getElementById("query").value = fmt(T("q_visit"), { p: AW.displayName(p, state.lang) });
    window.scrollTo({ top: 0 });
    submit(null, null);
  }
  function placeActions(p) {
    return el("div", { class: "actions" }, [
      el("button", { type: "button", class: "btn-s primary", text: T("start_here"), onclick: function () { startHere(p); } }),
      el("button", { type: "button", class: "btn-s", text: T("walk_there"), onclick: function () { walkThere(p); } })]);
  }

  function renderDiscover() {
    var box = document.getElementById("discover"); if (!box) return;
    box.textContent = "";
    var g = state.gallery; if (!g || !g.count) { box.hidden = true; return; }
    box.hidden = false;
    var d = g.day;
    if (d) {
      var dayDate = new Date(g.date + "T12:00:00+05:00");
      var dateTxt = dayDate.toLocaleDateString(state.lang === "kk" ? "kk-KZ" : state.lang, { weekday: "long", day: "numeric", month: "long" });
      var body = el("div", { class: "day-body" }, [
        el("p", { class: "eyebrow", text: T("day_eyebrow") + " · " + dateTxt }),
        el("h2", { id: "dayTitle", text: AW.displayName(d, state.lang) }), nameNote(d),
        el("div", { class: "meta-line" }, [el("span", { class: "pill", text: catLabel(d.category) }), d.address ? el("span", { class: "pill", text: d.address }) : null]),
        aboutText(d), placeActions(d), creditLine(d.media),
        el("p", { class: "credit", text: T("day_how") })]);
      box.appendChild(el("article", { class: "day", "aria-labelledby": "dayTitle" }, [photoBox("day-photo", d.media, AW.displayName(d, state.lang)), body]));
    }
    var guess = state.guess.on;
    var head = el("div", { class: "gal-head" }, [
      el("div", {}, [el("h2", { text: T("gal_title") }), el("p", { class: "gal-sub", text: guess ? T("guess_help") : fmt(T("gal_help"), { n: g.count }) })]),
      el("div", { class: "seg", role: "group", "aria-label": T("gal_title") }, [
        el("button", { type: "button", "aria-pressed": String(!guess), text: T("gal_explore"), onclick: function () { state.guess.on = false; renderDiscover(); } }),
        el("button", { type: "button", "aria-pressed": String(guess), text: T("gal_guess"), onclick: function () { state.guess.on = true; renderDiscover(); } })]),
      guess ? el("span", { class: "score", role: "status", text: fmt(T("guess_score"), { r: state.guess.right, n: state.guess.tried }) }) : null]);
    box.appendChild(head);
    var grid = el("div", { class: "gal-grid" });
    g.items.forEach(function (p) {
      var solved = state.guess.solved[p.id];
      var nameShown = !guess || solved;
      var label = nameShown ? AW.displayName(p, state.lang) : T("guess_q");
      var t = el("button", { type: "button", class: "tile" + (guess && solved ? " solved" : ""), "aria-label": nameShown ? label + ", " + catLabel(p.category) : T("guess_tile") }, [
        photoBox("tile-photo", p.media, nameShown ? label : T("guess_tile")),
        guess && !solved ? el("span", { class: "q", "aria-hidden": "true", text: "?" }) : null,
        el("span", { class: "tile-label" }, [el("span", { class: "tile-name", text: label }), el("span", { class: "tile-type", text: nameShown ? catLabel(p.category) : T("guess_hint") })])]);
      t.addEventListener("click", function () { openPlaceDialog(p, guess && !solved, t); });
      grid.appendChild(t);
    });
    box.appendChild(grid);
  }

  var lastFocus = null;
  function closeDialog() {
    var root = document.getElementById("dialogRoot"); if (!root || !root.firstChild) return;
    root.textContent = ""; document.removeEventListener("keydown", dlgKeys);
    if (lastFocus && document.body.contains(lastFocus)) lastFocus.focus();
    lastFocus = null;
  }
  function dlgKeys(e) {
    if (e.key === "Escape") { e.preventDefault(); closeDialog(); return; }
    if (e.key === "Tab") {   // keep focus inside the dialog
      var f = Array.prototype.slice.call(document.querySelectorAll("#dialogRoot button, #dialogRoot a[href]"));
      if (!f.length) return;
      var i = f.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
    }
  }
  function shuffle(a, seed) { var x = seed; return a.map(function (v) { x = (x * 9301 + 49297) % 233280; return [x, v]; }).sort(function (p, q) { return p[0] - q[0]; }).map(function (p) { return p[1]; }); }

  function openPlaceDialog(p, quiz, from) {
    lastFocus = from || document.activeElement;
    var root = document.getElementById("dialogRoot"); root.textContent = "";
    var name = AW.displayName(p, state.lang);
    var body = el("div", { class: "dlg-body" });
    var dlg = el("div", { class: "dlg", role: "dialog", "aria-modal": "true", "aria-labelledby": "dlgTitle" }, [
      el("div", { class: "dlg-photo" }, [photoBox("dlg-photo", p.media, quiz ? T("guess_tile") : name),
        el("button", { type: "button", class: "dlg-close", "aria-label": T("close"), text: "×", onclick: closeDialog })]),
      body]);
    function reveal(verdict) {
      body.textContent = "";
      var im = dlg.querySelector(".dlg-photo img"); if (im) im.setAttribute("alt", name);
      if (verdict) body.appendChild(el("p", { class: "verdict", role: "status", text: verdict }));
      body.appendChild(el("h2", { id: "dlgTitle", text: name }));
      var nn = nameNote(p); if (nn) body.appendChild(nn);
      body.appendChild(el("div", { class: "meta-line" }, [el("span", { class: "pill", text: catLabel(p.category) }), p.address ? el("span", { class: "pill", text: p.address }) : null]));
      var ab = aboutText(p); if (ab) body.appendChild(ab);
      body.appendChild(placeActions(p));
      body.appendChild(creditLine(p.media));
    }
    if (quiz) {
      var others = state.gallery.items.filter(function (x) { return x.id !== p.id && AW.displayName(x, state.lang) !== name; });
      var seed = (state.guess.tried + 7) * 131 + p.id.length;
      var opts = shuffle([p].concat(shuffle(others, seed).slice(0, 2)), seed + 3);
      body.appendChild(el("h2", { id: "dlgTitle", text: T("guess_title") }));
      body.appendChild(el("p", { class: "gal-sub", text: T("guess_note") }));
      var list = el("div", { class: "guess-opts" });
      opts.forEach(function (o) {
        list.appendChild(el("button", { type: "button", text: AW.displayName(o, state.lang) + " · " + catLabel(o.category), onclick: function () {
          var ok = o.id === p.id;
          state.guess.tried++; if (ok) state.guess.right++;
          state.guess.solved[p.id] = true;
          reveal(ok ? T("guess_right") : fmt(T("guess_wrong"), { p: name }));
          renderDiscover();
          var first = root.querySelector(".dlg-body button"); if (first) first.focus();
        } }));
      });
      body.appendChild(list);
      body.appendChild(creditLine(p.media));
    } else reveal(null);
    var back = el("div", { class: "dlg-back", onclick: function (e) { if (e.target === back) closeDialog(); } }, [dlg]);
    root.appendChild(back);
    document.addEventListener("keydown", dlgKeys);
    var fb = root.querySelector(quiz ? ".guess-opts button" : ".dlg-body button") || root.querySelector("button");
    if (fb) fb.focus();
  }

  function loadGallery() {
    fetch("/api/gallery").then(function (r) { return r.json(); }).then(function (g) {
      state.gallery = g; rememberPlaces(g.items); renderDiscover();
    }).catch(function () { var b = document.getElementById("discover"); if (b) b.hidden = true; });
  }

  // ------------------------------------------------------------------ geolocation
  function locate() {
    var msg = document.getElementById("geoMsg");
    if (!navigator.geolocation) { msg.textContent = T("geo_unsupported"); return; }
    msg.textContent = T("geo_wait");
    try {
      navigator.geolocation.getCurrentPosition(function (pos) {
        state.geo = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        msg.textContent = T("geo_ok");
      }, function () { state.geo = null; msg.textContent = T("geo_denied"); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
    } catch (e) { msg.textContent = T("geo_unsupported"); }
  }

  // ------------------------------------------------------------------ requests
  function buildStart() {
    if (state.mode === "landmark") return state.startId ? { type: "landmark", id: state.startId } : null;
    if (state.mode === "geo") return state.geo ? { type: "geo", lat: state.geo.lat, lon: state.geo.lon } : null;
    var parts = (state.coordsText || "").split(/[\s,;]+/).filter(Boolean);
    return { type: "coords", lat: parts[0], lon: parts.length === 2 ? parts[1] : "x" };
  }

  function buildBody() {
    var od = outdoorMax();
    return {
      text: document.getElementById("query").value, lang: state.lang, start: buildStart(), budget: state.minutes,
      back: document.getElementById("back").checked, interests: state.interests.slice(),
      weather: document.getElementById("useWeather").checked, pace: state.pace,
      deadline: state.deadline.on ? { enabled: true, at: state.deadline.date + "T" + state.deadline.time, buffer_min: state.deadline.buffer } : null,
      outdoor: (od !== null || state.outdoor.strict) ? { max_min: od, strict: state.outdoor.strict } : null,
      group: state.group.on ? { participants: clone(state.group.people) } : null,
      exclude: { visited: state.visited.slice(), unavailable: state.unavailable.slice(), other: state.other.slice() },
      filters: { known_hours: state.filters.known_hours, wheelchair: state.filters.wheelchair }
    };
  }

  /** POST with a sequence guard: a late answer to an older request never overwrites a newer one. */
  function post(path, body, onDone) {
    var my = ++state.seq;
    setBusy(true);
    var ctrl = window.AbortController ? new AbortController() : null;
    state.abort = function () { if (ctrl) ctrl.abort(); };
    fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, j: j }; }); })
      .then(function (x) { if (my !== state.seq) return; setBusy(false); onDone(x.status, x.j); })
      .catch(function () { if (my !== state.seq) return; setBusy(false); onDone(0, { error: { code: "server" } }); });
  }

  /** Cancel: the newest answer slot moves on, so a late reply is ignored; the last plan stays usable. */
  function cancelRequest() {
    state.seq++;
    try { if (state.abort) state.abort(); } catch (e) { /* ignore */ }
    setBusy(false);
    if (state.result) { state.actionMsg = { kind: "info", text: T("cancelled") }; renderResult(); }
    else { var out = document.getElementById("output"); out.textContent = ""; out.appendChild(el("p", { class: "notice info", role: "status", text: T("cancelled") })); }
  }

  function setBusy(on) {
    state.busy = on;
    var b = document.getElementById("submit");
    b.disabled = on; b.textContent = on ? T("searching") : T("submit");
    document.getElementById("surpriseBtn").disabled = on;
    document.querySelectorAll("#output .btn-s:not(#cancelBtn)").forEach(function (x) { x.disabled = on; });
    document.getElementById("results").setAttribute("aria-busy", String(on));
  }

  function showLoading(textKey) {
    var out = document.getElementById("output"); out.textContent = "";
    out.appendChild(el("div", { class: "loading", role: "status" }, [
      el("span", { class: "dots", "aria-hidden": "true" }, [el("i"), el("i"), el("i")]), el("span", { text: T(textKey || "loading") }),
      el("button", { type: "button", class: "btn-s", id: "cancelBtn", text: T("cancel"), onclick: cancelRequest })]));
  }

  function submit(e, mode, extra) {
    if (e) e.preventDefault();
    if (state.busy) return;
    var body = buildBody();
    if (extra) Object.keys(extra).forEach(function (k) { body[k] = extra[k]; });
    if (!body.start) { showError({ message: T(state.mode === "landmark" ? "start_needed" : "geo_needed") }); return; }
    if (mode === "surprise") {
      body.mode = "surprise";
      body.surprise = { seed: Math.floor(Math.random() * 2147483647), avoid: state.surprise.history.slice(-40) };
    }
    showLoading();
    post("/api/recommend", body, function (status, j) {
      if (j.clarify) { renderClarify(j.clarify, body, mode); return; }
      if (!j.plan && !j.understood && j.error) { showError(j.error); return; }
      if (mode !== "walk") state.walk = null;
      acceptResult(j, body);
      if (mode === "surprise" && j.plan) state.surprise.history.push(j.plan.stops.map(function (s) { return s.id; }));
      renderResult();
      var res = document.getElementById("results");
      try { res.focus({ preventScroll: true }); } catch (err) { res.focus(); }
      res.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    });
  }

  function acceptResult(j, body) {
    var snap = clone(body); delete snap.surprise;
    state.result = j; state.resultLang = state.lang; state.lastBody = snap;
    state.flags = {}; state.cardMsg = {}; state.actionMsg = null; state.exportText = null;
    setPlan(j.plan, null);
    if (j.constraints && j.constraints.now) state.clockOffset = astanaMs(j.constraints.now) - Date.now();
  }

  /** Replace the canonical plan. Texts of stops the server marked "keep" come from the previous plan. */
  function setPlan(plan, previous) {
    if (plan && previous) {
      var old = {}; previous.stops.forEach(function (s) { old[s.id] = s; });
      plan.stops.forEach(function (s) {
        if (s.text_source === "keep" && old[s.id]) {
          s.why = old[s.id].why; s.activity = old[s.id].activity; s.text_source = old[s.id].text_source;
          s.calc_code = old[s.id].calc_code; s.calc_params = old[s.id].calc_params; s.warnings = old[s.id].warnings;
        }
      });
    }
    var oldDone = state.bingo.done;
    state.plan = plan;
    state.bingo.done = plan ? AW.carryBingo(oldDone, AW.bingoTasks(plan.stops)) : {};
  }

  function errorText(err) {
    if (err.message) return err.message;
    var msgs = T("errors");
    return fmt(msgs[err.code] || err.detail || msgs.server, err.params || {});
  }

  function showError(err) {
    var out = document.getElementById("output"); out.textContent = "";
    out.appendChild(el("div", { class: "notice error", role: "alert" }, [el("strong", { text: T("err_title") }), el("span", { text: errorText(err) })]));
    if (state.result && state.plan) {
      // keep the last usable plan visible below the error
      var keep = document.createElement("div"); out.appendChild(keep);
      renderPlanInto(keep);
    }
  }

  // ---------- stop actions: replace / visited / closed / too far / remove / recalc
  function currentStops() { return state.plan.stops.map(function (s) { return { id: s.id, visit_minutes: s.visit_minutes }; }); }
  function actionBody() {
    var b = clone(state.lastBody);
    b.lang = state.lang;
    b.exclude = { visited: state.visited.slice(), unavailable: state.unavailable.slice(), other: state.other.slice() };
    return b;
  }
  function addUnique(list, id) { if (list.indexOf(id) < 0) list.push(id); }

  function stopAction(stopId, reason) {
    if (state.busy || !state.plan) return;
    if (reason === "visited") { addUnique(state.visited, stopId); persistVisited(); }
    else if (reason === "closed") { addUnique(state.unavailable, stopId); state.flags[stopId] = "unavailable"; }
    else addUnique(state.other, stopId);
    var body = actionBody();
    body.plan_stops = currentStops(); body.target = stopId; body.reason = reason;
    state.cardMsg[stopId] = "replacing";
    renderResult();
    post("/api/replace", body, function (status, j) {
      delete state.cardMsg[stopId];
      if (status !== 200 || !j.replace) { state.actionMsg = { kind: "error", text: errorText(j.error || { code: "server" }) }; renderResult(); return; }
      if (!j.replace.ok) { state.cardMsg[stopId] = "no_replacement"; renderResult(); return; }
      var prev = state.plan;
      setPlan(j.plan, prev);
      delete state.flags[stopId];
      state.result.notices = j.notices || [];
      state.result.constraints = j.constraints || state.result.constraints;
      state.actionMsg = { kind: "info", text: T("replaced_ok") };
      renderResult();
    });
    renderReset();
  }

  function replanWith(stops, okKey, extra) {
    if (state.busy) return;
    if (!stops.length) { setPlan(null, null); state.actionMsg = { kind: "info", text: T("plan_empty") }; renderResult(); return; }
    var body = actionBody(); body.plan_stops = stops;
    if (extra) Object.keys(extra).forEach(function (k) { body[k] = extra[k]; });
    if (state.walk && state.result.start && state.result.start.kind === "walk") { body.start = { type: "coords", lat: state.result.start.lat, lon: state.result.start.lon }; }
    post("/api/replan", body, function (status, j) {
      if (status !== 200) { state.actionMsg = { kind: "error", text: errorText(j.error || { code: "server" }) }; renderResult(); return; }
      if (!j.plan) { state.actionMsg = { kind: "error", text: planFailText(j) }; renderResult(); return; }
      var prev = state.plan; setPlan(j.plan, prev);
      Object.keys(state.flags).forEach(function (id) { if (!j.plan.stops.some(function (s) { return s.id === id; })) delete state.flags[id]; });
      state.result.constraints = j.constraints || state.result.constraints;
      if (extra && extra.explain) { state.result.notices = j.notices || []; state.resultLang = state.lang; }
      state.actionMsg = { kind: "info", text: T(okKey) };
      renderResult();
    });
  }
  function removeStop(stopId) {
    addUnique(state.other, stopId);
    replanWith(currentStops().filter(function (s) { return s.id !== stopId; }), "removed_ok");
    renderReset();
  }

  function resetExclusions() {
    state.visited = []; state.unavailable = []; state.other = []; state.surprise.history = [];
    store.del("aw-visited");
    document.getElementById("resetMsg").textContent = T("reset_done");
    renderReset();
  }

  // ---------- one concise clarification (start conflict / ambiguous place)
  function renderClarify(c, body, mode) {
    var out = document.getElementById("output"); out.textContent = "";
    rememberPlaces(c.options);
    var sel = c.selected && c.selected.display_names ? AW.displayName({ display_names: c.selected.display_names }, state.lang) : T("clar_selected_coords");
    var q = c.code === "start_ambiguous" ? fmt(T("clar_ambiguous"), { phrase: c.phrase }) : fmt(T("clar_conflict"), { phrase: c.phrase, sel: sel });
    var row = el("div", { class: "actions" });
    c.options.forEach(function (p) {
      row.appendChild(el("button", { type: "button", class: "btn-s primary", text: fmt(T("clar_use"), { p: landmarkName(p) + " (" + catLabel(p.category) + ")" }), onclick: function () {
        state.mode = "landmark"; document.querySelector('input[name="mode"][value="landmark"]').checked = true;
        choosePlace(p); renderSentence(); submit(null, mode);
      } }));
    });
    row.appendChild(el("button", { type: "button", class: "btn-s", text: fmt(T("clar_keep"), { s: sel }), onclick: function () { submit(null, mode, { start_choice: "keep" }); } }));
    out.appendChild(el("section", { class: "notice info clarify", role: "group", "aria-labelledby": "clarT" }, [
      el("h2", { id: "clarT", text: T("clar_title") }), el("p", { text: q }), row]));
    var b = out.querySelector("button"); if (b) b.focus();
  }

  // ------------------------------------------------------------------ results
  function renderResult() {
    stopSpeaking();
    var r = state.result, out = document.getElementById("output");
    out.textContent = "";
    if (!r) return renderEmpty();
    if (r.understood) out.appendChild(renderUnderstood(r));
    var u = r.understood;
    if (u && u.unsupported && u.unsupported.length) {
      var names = u.unsupported.map(function (k) { var l = state.meta.labels.unsupported[k]; return l ? (l[state.lang] || l.en) : k; });
      out.appendChild(el("p", { class: "notice", text: fmt(T("unsupported"), { list: names.join(", ") }) }));
    }
    if (u && u.late_hour) out.appendChild(el("p", { class: "notice", role: "note", text: T("night_note") }));
    if (u && u.flight) out.appendChild(el("p", { class: "notice", role: "note", text: T("flight_note") }));
    ((u && u.named_excluded) || []).forEach(function (n) {
      var why = (T("named_excl_reason")[n.reason] || T("named_excl_reason").other);
      out.appendChild(el("p", { class: "notice", role: "note", text: fmt(T("named_excl"), { p: AW.displayName(n, state.lang), why: fmt(why, n) }) }));
    });
    (r.notices || []).forEach(function (n) { if (n.code === "app_choice") out.appendChild(el("p", { class: "notice info", role: "note", text: T("app_choice_note") })); });
    (r.notices || []).forEach(function (n) { if (n.code === "ai_text_unavailable") out.appendChild(el("p", { class: "notice", text: T("ai_text_unavailable") })); });
    if (state.resultLang && state.resultLang !== state.lang && state.plan && hasAiText()) {
      out.appendChild(el("div", { class: "notice info" }, [el("span", { text: langSwitchNote() + " " }),
        el("button", { type: "button", class: "btn-s", text: fmt(T("regen"), { l: T("lang_names")[state.lang] }), onclick: function () { regenerate(); } })]));
    }
    if (state.actionMsg) out.appendChild(el("p", { class: "notice " + (state.actionMsg.kind === "error" ? "error" : "info"), role: state.actionMsg.kind === "error" ? "alert" : "status", text: state.actionMsg.text }));

    if (r.error) {
      out.appendChild(el("div", { class: "notice error", role: "alert" }, [el("strong", { text: T("err_title") }), el("span", { text: errorText(r.error) })]));
      if (r.trace && r.trace.candidates.length) { out.appendChild(recoveryRow()); out.appendChild(renderFallback(r.trace.candidates)); }
    } else if (!state.plan) {
      out.appendChild(renderNoPlan(r));
      if (r.note_code === "model_empty" && r.trace && r.trace.candidates.length) { out.appendChild(recoveryRow()); out.appendChild(renderFallback(r.trace.candidates)); }
    } else {
      renderPlanInto(out);
    }
    if (r.trace) out.appendChild(renderTrace(r));
    setBusy(state.busy);
  }

  /** After a model failure: retry, or an explicitly labelled plan chosen by the app (no AI text). */
  function recoveryRow() {
    return el("div", { class: "actions" }, [
      el("button", { type: "button", class: "btn-s primary", text: T("retry_model"), onclick: function () { submit(null, null); } }),
      el("button", { type: "button", class: "btn-s", text: T("app_choice_btn"), onclick: function () { submit(null, null, { no_model: true }); } }),
      el("span", { class: "hint", text: T("app_choice_hint") })]);
  }
  function hasAiText() { return state.plan && state.plan.stops.some(function (s) { return s.text_source === "ai"; }); }
  function regenerate() {
    if (!state.lastBody || state.busy) return;
    var b = clone(state.lastBody); b.lang = state.lang;
    showLoading();
    post("/api/recommend", b, function (status, j) {
      if (!j.plan && !j.understood && j.error) { showError(j.error); return; }
      acceptResult(j, b); renderResult();
    });
  }

  function planFailText(r) {
    var reasons = T("reasons");
    if (r.note_code === "no_plan_outdoor") return fmt(T("no_plan_outdoor"), { n: outdoorMax() === null ? "?" : outdoorMax() });
    if (r.note_code === "no_plan") return fmt(T("no_plan"), { reason: reasons[(r.note_params || {}).reason] || reasons.time });
    if (r.note_code === "surprise_exhausted") return T("surprise_exhausted");
    if (r.note_code === "surprise_none") return T("surprise_none");
    if (r.note_code === "plan_empty") return T("plan_empty");
    return r.note_code ? T(r.note_code) : (r.note || T("model_empty"));
  }

  function rerunMode() { return state.result && state.result.mode === "surprise" ? "surprise" : null; }
  function applySuggestion(sg) {
    var m = rerunMode();
    if (sg.key === "add_time") { state.minutes = sg.to; renderSentence(); syncPersonOne(); submit(null, m); }
    else if (sg.key === "relax_outdoor") { state.outdoor.sel = "custom"; state.outdoor.custom = sg.to; document.getElementById("odCustom").value = sg.to; renderOutdoorSelect(); submit(null, m); }
    else if (sg.key === "include_unknown_hours") { state.filters.known_hours = false; document.getElementById("fHours").checked = false; submit(null, m); }
    else if (sg.key === "drop_wheelchair_filter") { state.filters.wheelchair = false; document.getElementById("fWheel").checked = false; submit(null, m); }
    else if (sg.key === "any_category") { submit(null, m, { broaden: true }); }
    else if (sg.key === "deadline_binding") { var d = document.getElementById("more"); d.open = true; document.getElementById("dlTime").focus(); }
    else if (sg.key === "change_start") { window.scrollTo(0, 0); var pi = document.getElementById("pickInput") || document.getElementById("coordsInput"); if (pi) pi.focus(); }
  }
  function suggestionText(sg) {
    var t = fmt(T("sug")[sg.key] || sg.key, sg);
    if (sg.key === "any_category" && sg.keeps && sg.keeps.length) t += " — " + fmt(T("sug_keeps"), { k: sg.keeps.map(catLabel).join(", ") });
    return t;
  }

  function renderNoPlan(r) {
    var box = el("div", { class: "notice info" }, [el("span", { text: planFailText(r) })]);
    var row = el("div", { class: "actions" });
    var ex = r.trace && r.trace.excluded ? Object.keys(r.trace.excluded).filter(function (k) { return r.trace.excluded[k]; }) : [];
    if (ex.length) {
      var ul = el("ul", { class: "why-list" });
      ex.forEach(function (k) { ul.appendChild(el("li", { text: fmt(T("t_excl")[k] || k, { n: r.trace.excluded[k] }) })); });
      box.appendChild(el("p", { class: "hint", text: T("no_plan_why") })); box.appendChild(ul);
    }
    var sugs = r.suggestions || [];
    if (sugs.length) {
      box.appendChild(el("p", { class: "hint", text: T("sug_title") }));
      var sl = el("div", { class: "actions sugs" });
      sugs.forEach(function (sg) {
        if (sg.key === "hours_info") { sl.appendChild(el("p", { class: "hint", text: suggestionText(sg) })); return; }
        sl.appendChild(el("button", { type: "button", class: "btn-s" + (sg.key === "add_time" || sg.key === "relax_outdoor" ? " primary" : ""), text: suggestionText(sg), onclick: function () { applySuggestion(sg); } }));
      });
      box.appendChild(sl);
    }
    if (r.note_code === "surprise_exhausted") {
      row.appendChild(el("button", { type: "button", class: "btn-s primary", text: T("surprise_reset"), onclick: function () { state.surprise.history = []; submit(null, "surprise"); } }));
    }
    if (row.childNodes.length) box.appendChild(row);
    return box;
  }

  function renderPlanInto(out) {
    var r = state.result, p = state.plan;
    var layout = el("div", { class: "layout" });
    var list = el("div", { class: "recs" });
    list.appendChild(renderPlanHead(r, p));
    list.appendChild(renderWalkPanel(p));
    if (r.understood && r.understood.answer_lang === "kk" && T("kk_note")) list.appendChild(el("p", { class: "kk-note", text: T("kk_note") }));
    if (r.note) list.appendChild(el("p", { class: "notice info" }, [el("strong", { text: T("note_ai") }), el("span", { text: r.note })]));
    p.stops.forEach(function (s) { list.appendChild(renderStop(s, p)); });
    if (r.mode === "surprise") {
      list.appendChild(el("div", { class: "actions" }, [el("button", { type: "button", class: "btn-s primary", text: T("surprise_again"), onclick: function () { submit(null, "surprise"); } })]));
    }
    var styles = renderStyles(r, p);
    if (styles) list.appendChild(styles);
    else if (r.styles_status && r.styles_status !== "ok") list.appendChild(el("p", { class: "hint", text: T("styles_none")[r.styles_status] || "" }));
    list.appendChild(renderRoute(p));
    list.appendChild(renderExport(p));
    list.appendChild(renderReports());
    list.appendChild(renderBingo(p));
    layout.appendChild(list);
    layout.appendChild(el("aside", { class: "side" }, [el("div", { class: "mapbox" }, [el("div", { id: "map", role: "img", "aria-label": T("map_cap") }), el("p", { class: "map-cap", text: T("map_cap") })])]));
    out.appendChild(layout);
    setTimeout(function () { drawMap(p); }, 0);
    startCountdown();
  }

  function langSwitchNote() {
    var names = T("lang_names");
    return {
      kk: "ЖИ мәтіні " + names[state.resultLang] + " жазылған. Қазақша алу үшін «Орындарды табу» батырмасын қайта басыңыз.",
      ru: "Текст ИИ написан на языке: " + names[state.resultLang] + ". Чтобы получить его на русском, нажмите «Подобрать места» ещё раз.",
      en: "The AI text is in " + names[state.resultLang] + ". Press “Find places” again to get it in English."
    }[state.lang];
  }

  function budgetChip(c, u) {
    var src = (c && c.budget_source) || u.budget_source, n = (c && c.budget_min) || u.budget_min;
    var key = { text: "budget_text", deadline: "budget_deadline", group: "budget_group" }[src] || "budget_slider";
    return fmt(T(key), { n: n });
  }

  function renderUnderstood(r) {
    var u = r.understood, c = r.constraints, box = el("div", { class: "understood" });
    box.appendChild(el("h2", { text: T("understood") }));
    if (r.mode !== "surprise" || u.intents.length < 6) {
      var ints = u.intents.map(intentLabel).join(", ");
      box.appendChild(el("span", { class: "tag", text: u.assumed ? ints + " (" + T("assumed") + ")" : ints }));
    } else box.appendChild(el("span", { class: "tag", text: T("surprise_title") }));
    box.appendChild(el("span", { class: "tag", text: budgetChip(c, u) }));
    box.appendChild(el("span", { class: "tag", text: T(r.start && r.start.back ? "round_trip" : "one_way") }));
    if (u.negated && u.negated.length) box.appendChild(el("span", { class: "tag neg", text: fmt(T("neg_tag"), { c: u.negated.map(catLabel).join(", ") }) }));
    (u.named || []).forEach(function (n) { box.appendChild(el("span", { class: "tag", text: fmt(T("named_tag"), { p: AW.displayName(n, state.lang) }) })); });
    var days = { kk: ["дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі", "жексенбі"],
                 ru: ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
                 en: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] };
    box.appendChild(el("span", { class: "tag", text: fmt(T("now"), { t: (days[state.lang] || days.en)[u.weekday] + ", " + u.now.slice(11, 16) }) }));
    if (c) {
      box.appendChild(el("span", { class: "tag", text: fmt(T("pace_tag"), { p: T("pace_" + c.pace) }) }));
      if (c.outdoor && c.outdoor.max_min !== null && c.outdoor.max_min !== undefined) box.appendChild(el("span", { class: "tag", text: fmt(T("outdoor_chip"), { n: c.outdoor.max_min }) }));
      if (c.group && c.group.length) box.appendChild(el("span", { class: "tag", text: fmt(T("group_tag"), { n: c.group.length }) }));
    }
    var w = r.weather;
    if (w) {
      var t = Math.round(w.apparent_c !== null && w.apparent_c !== undefined ? w.apparent_c : w.temperature_c);
      if (w.harsh) {
        var reasons = w.reasons.map(function (k) { return T("weather_reasons")[k] || k; }).join(", ");
        box.appendChild(el("span", { class: "tag weather-harsh", text: fmt(T("weather_now"), { t: t }) + ". " + fmt(T("weather_harsh"), { r: reasons }) }));
      } else box.appendChild(el("span", { class: "tag", text: fmt(T("weather_now"), { t: t }) }));
    }
    return box;
  }

  function hoursText(h) {
    var tpl = (window.HOURS_TEXT[state.lang] || window.HOURS_TEXT.en)[h.key] || "";
    return fmt(tpl, { raw: h.raw || "", m: h.minutes_until_close });
  }

  function stopName(id) {
    var s = state.plan && state.plan.stops.filter(function (x) { return x.id === id; })[0];
    if (s) return placeName(s.poi);
    var c = state.result && state.result.trace && state.result.trace.candidates.filter(function (x) { return x.poi.id === id; })[0];
    return c ? placeName(c.poi) : id;
  }

  function renderPlanHead(r, p) {
    var head = el("section", { class: "plan-head", "aria-labelledby": "planTitle" });
    head.appendChild(el("h2", { id: "planTitle", text: r.mode === "surprise" ? T("surprise_title") : T("plan_title") }));
    var facts = el("div", { class: "plan-facts" }, [
      el("span", {}, [el("b", { text: fmt(T("plan_summary"), { n: p.stops.length, total: p.total_min, budget: p.budget_min, walk: p.walk_min }) })]),
      el("span", { text: fmt(T(p.return_to_start ? "plan_back_eta" : "plan_end_eta"), { eta: p.end_eta }) }),
      el("span", { text: fmt(T("plan_outdoor"), { n: p.outdoor_min }) })
    ]);
    head.appendChild(facts);
    head.appendChild(renderTimeline(p));
    var notes = el("ul", { class: "plan-notes" });
    if (p.outdoor_estimated) notes.appendChild(el("li", { text: T("plan_outdoor_est") }));
    (p.adjustments || []).forEach(function (a) {
      if (a.code === "shortened") notes.appendChild(el("li", { text: fmt(T("adj_shortened"), { name: stopName(a.id), from: a.from, to: a.to, reason: T("reasons")[a.reason] || T("reasons").time }) }));
      if (a.code === "dropped") notes.appendChild(el("li", { text: fmt(T("adj_dropped"), { name: stopName(a.id), reason: T("reasons")[a.reason] || a.reason }) }));
    });
    if (notes.childNodes.length) head.appendChild(notes);
    var dl = r.constraints && r.constraints.deadline;
    if (dl) head.appendChild(el("div", { class: "deadline-live", id: "deadlineLive", role: "status" }));
    if (r.coverage && r.coverage.length) {
      var ul = el("ul");
      r.coverage.forEach(function (c) {
        var who = c.person === 1 ? T("group_you") : fmt(T("group_person"), { n: c.person });
        var ints = c.interests.length ? c.interests.map(intentLabel).join(", ") : T("cov_any");
        var current = c.covered_by.filter(function (id) { return p.stops.some(function (s) { return s.id === id; }); });
        if (current.length) ul.appendChild(el("li", { class: "yes", text: fmt(T("cov_yes"), { p: who + " (" + ints + ")", places: current.map(stopName).join(", ") }) }));
        else ul.appendChild(el("li", { class: "no", text: fmt(T("cov_no"), { p: who, ints: ints }) }));
      });
      head.appendChild(el("div", { class: "coverage" }, [el("strong", { text: T("cov_title") }), ul]));
    }
    return head;
  }

  function renderTimeline(p) {
    var total = Math.max(p.budget_min, p.total_min), bar = el("div", { class: "tl", "aria-hidden": "true" }), parts = [];
    function seg(cls, mins, label) { bar.appendChild(el("span", { class: cls, style: "width:" + (100 * mins / total).toFixed(2) + "%", text: label || null })); }
    p.legs.forEach(function (leg, i) {
      seg("walk", leg.walk_min);
      parts.push(T("tb_walk") + " " + leg.walk_min + " " + minLabel());
      var s = p.stops[i];
      if (s) { seg("visit", s.visit_minutes, String(s.n)); parts.push(s.n + ". " + placeName(s.poi) + " " + s.visit_minutes + " " + minLabel()); }
    });
    var spare = Math.max(0, p.budget_min - p.total_min);
    parts.push(T("tb_spare") + " " + spare + " " + minLabel());
    return el("div", { class: "timebar" }, [
      bar,
      el("p", { class: "sr-only", text: parts.join("; ") }),
      el("ul", { class: "legend", "aria-hidden": "true" }, [
        el("li", {}, [el("i", { class: "walk" }), T("tb_walk") + " " + p.walk_min + " " + minLabel()]),
        el("li", {}, [el("i", { class: "visit" }), T("tb_visit") + " " + p.visit_min + " " + minLabel()]),
        el("li", {}, [el("i", { class: "spare" }), T("tb_spare") + " " + spare + " " + minLabel()])
      ])
    ]);
  }

  function calcText(s) {
    var p = s.calc_params || {}, cat = catLabel(s.poi.category);
    if (s.calc_code === "group_cover") return fmt(T("calc_group"), { p: p.person, cat: cat });
    if (s.calc_code === "replacement") return fmt(T("calc_replacement"), { cat: cat, walk: s.walk_from_prev_min });
    if (s.calc_code === "ranked") return fmt(T("calc_ranked"), { cat: cat, walk: s.walk_from_prev_min });
    if (s.calc_code === "fit") return fmt(T("calc_fit"), { cat: cat, walk: s.walk_from_prev_min });
    if (s.calc_code === "style") return fmt(T("calc_style"), { cat: cat, walk: s.walk_from_prev_min });
    return fmt(T("calc_surprise"), { cat: cat, walk: s.walk_from_prev_min });
  }

  function renderStop(s, plan) {
    var p = s.poi, name = placeName(p), unavailable = state.flags[s.id] === "unavailable";
    var card = el("article", { class: "rec" + (unavailable ? " unavailable" : ""), "aria-labelledby": "rec-" + s.n });
    var photo = renderPhoto(p, name);
    if (photo) card.appendChild(photo);
    var speakBtn = el("button", { type: "button", class: "speak" }, [svgIcon(ICON_SPEAK), el("span", { text: T("speak") })]);
    var meta = el("div", { class: "meta-line" }, [
      el("span", { class: "pill", text: catLabel(p.category) }),
      el("span", { class: "pill", text: T(s.indoor ? (s.indoor_basis === "osm_tag" ? "indoor_tag" : "indoor_est") : (s.indoor_basis === "osm_tag" ? "outdoor_tag" : "outdoor_est")) }),
      p.notable ? el("span", { class: "pill notable", text: T("notable") }) : null,
      el("span", { class: "pill src" }, [svgIcon(ICON_SRC), T("badge_src")])
    ]);
    var walkDone = state.walk && state.walk.done.indexOf(s.id) >= 0;
    card.appendChild(el("div", { class: "rec-head" }, [
      el("div", { class: "num", "aria-hidden": "true", text: String(s.n) }),
      el("div", {}, [el("h3", { id: "rec-" + s.n }, [el("span", { class: "sr-only", text: s.n + ". " }), name]), nameNote(p), meta,
        walkDone ? el("span", { class: "pill done", text: T("walk_done_badge") }) : null]),
      speakBtn
    ]));

    var dl = el("dl", { class: "facts" });
    function fact(label, value, note, cls) { dl.appendChild(el("div", { class: cls || null }, [el("dt", { text: label }), el("dd", {}, [value, note ? el("small", { text: note }) : null])])); }
    fact(T("f_arrive"), "≈" + s.arrive_at,
         fmt(T(s.n === 1 ? "from_start" : "from_prev"), { walk: s.walk_from_prev_min, m: num(Math.round(s.distance_from_prev_m / 10) * 10) }) + " · " + T("f_walk_n"));
    fact(T("f_visit"), fmt(T("f_visit_v"), { n: s.visit_minutes }), fmt(T("f_visit_n"), { a: s.visit_range[0], b: s.visit_range[1] }));
    fact(T("f_distance"), fmt(T("f_distance_v"), { m: num(Math.round(s.distance_m / 10) * 10) }), T("f_distance_n"));
    var hoursLine = s.hours_at_arrival === "ok" ? fmt(T("hours_ok_arrival"), { t: s.arrive_at, raw: s.hours.raw || "" }) : hoursText(s.hours);
    fact(T("f_hours"), hoursLine, null, "hours");
    card.appendChild(dl);
    card.appendChild(renderFit(s));
    var about = renderAbout(p);
    if (about) card.appendChild(about);

    var gen = el("div", { class: "gen" });
    if (s.text_source === "ai" && s.why) {
      gen.appendChild(el("div", {}, [el("h4", {}, [T("why"), el("span", { class: "pill ai" }, [svgIcon(ICON_AI), T("badge_ai")])]), el("p", { text: s.why })]));
      if (s.activity) gen.appendChild(el("div", {}, [el("h4", {}, [T("activity"), el("span", { class: "pill ai" }, [svgIcon(ICON_AI), T("badge_ai")])]), el("p", { text: s.activity })]));
    } else if (s.text_source === "calc") {
      gen.appendChild(el("div", {}, [el("h4", {}, [T("why"), el("span", { class: "pill calc", text: T("calc_badge") })]), el("p", { text: calcText(s) })]));
    }
    card.appendChild(gen);
    (s.warnings || []).forEach(function (w) {
      var txt = w.code === "ungrounded" ? fmt(T("warn_ungrounded"), { claims: w.claims.map(function (c) { return T("claims")[c] || c; }).join(", ") })
        : (w.code === "wrong_language" ? T("warn_wrong_language") : T("warn_no_why"));
      card.appendChild(el("p", { class: "warn", role: "note", text: txt }));
    });
    if (unavailable) card.appendChild(el("p", { class: "unavail", role: "note", text: T("unavailable_mark") }));

    // actions
    var msg = state.cardMsg[s.id];
    var acts = el("div", { class: "actions", role: "group", "aria-label": T("actions_label") }, [el("span", { class: "lbl", text: T("actions_label") + ":" })]);
    [["replace", "act_replace"], ["visited", "act_visited"], ["closed", "act_closed"], ["too_far", "act_too_far"]].forEach(function (a) {
      acts.appendChild(el("button", { type: "button", class: "btn-s", text: T(a[1]), onclick: function () { stopAction(s.id, a[0]); } }));
    });
    acts.appendChild(el("button", { type: "button", class: "btn-s" + (msg === "no_replacement" ? " primary" : ""), text: T("act_remove"), onclick: function () { removeStop(s.id); } }));
    acts.appendChild(el("button", { type: "button", class: "btn-s", "aria-expanded": String(state.reportFor === s.id), text: T("report_btn"), onclick: function () { state.reportFor = state.reportFor === s.id ? null : s.id; renderResult(); } }));
    card.appendChild(acts);
    if (msg) card.appendChild(el("p", { class: "inline-msg", role: "status", text: T(msg) }));
    var dir = directionsRow(s, plan);
    if (dir) card.appendChild(dir);
    if (state.walk) card.appendChild(el("div", { class: "actions" }, [el("button", { type: "button", class: "btn-s" + (walkDone ? "" : " primary"), "aria-pressed": String(!!walkDone),
      text: T(walkDone ? "walk_unmark" : "walk_mark"), onclick: function () { toggleDone(s.id); } })]));
    if (state.reportFor === s.id) card.appendChild(renderReportForm(s));

    var foot = el("div", { class: "rec-foot" });
    var url = AW.safeUrl(p.source_url);
    foot.appendChild(el("div", {}, [T("source") + ": ", url ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: "OpenStreetMap " + p.id.replace("osm:", "") }) : p.id,
      ", " + fmt(T("collected"), { d: (p.collected_at || "").slice(0, 10) })]));
    if (!p.name_is_generated) {
      var gis = AW.safeUrl("https://2gis.kz/astana/search/" + encodeURIComponent(p.name));
      if (gis) foot.appendChild(el("div", {}, [el("a", { href: gis, target: "_blank", rel: "noopener noreferrer", text: T("check_2gis") }), " " + T("check_2gis_note")]));
    }
    if (p.description) foot.appendChild(el("div", { text: p.description + " (" + (p.description_source === "osm_description_tag" ? T("desc_osm") : T("desc_tags")) + ")" }));
    var contacts = Object.keys(p.contacts || {}).map(function (k) { return k + ": " + p.contacts[k]; });
    if (contacts.length) foot.appendChild(el("div", { text: T("contacts") + ": " + contacts.join(", ") }));
    card.appendChild(foot);

    speakBtn.addEventListener("click", function () {
      var parts = [s.n + ". " + name + ".", catLabel(p.category) + ".", fmt(T("arrive"), { t: s.arrive_at }) + ".",
        T("f_visit") + " " + fmt(T("f_visit_v"), { n: s.visit_minutes }) + ".", hoursLine];
      var ab = aboutFor(p); if (ab && ab.lang === state.lang) parts.push(ab.v.text);
      if (s.text_source === "ai" && s.why) { parts.push(T("why") + ": " + s.why); if (s.activity) parts.push(T("activity") + ": " + s.activity); }
      else if (s.text_source === "calc") parts.push(calcText(s));
      speak(parts.join(" "), speakBtn, state.resultLang || state.lang);
    });
    return card;
  }

  function renderPhoto(p, name) {
    var ph = p.media && p.media.photo;
    if (!ph) return null;
    var thumb = AW.safeUrl(ph.thumb), page = AW.safeUrl(ph.page);
    if (!thumb || !page) return null;
    var fig = el("figure", { class: "photo" });
    var img = el("img", { src: thumb, alt: name, loading: "lazy", decoding: "async", referrerpolicy: "strict-origin-when-cross-origin" });
    img.addEventListener("error", function () { fig.hidden = true; });   // offline or removed: no broken image
    var lic = AW.safeUrl(ph.license_url);
    var cap = el("figcaption", {}, [
      fmt(T("photo_credit"), { author: ph.author || T("photo_author_unknown") }) + " ",
      lic ? el("a", { href: lic, target: "_blank", rel: "noopener noreferrer", text: ph.license }) : ph.license,
      ", ", el("a", { href: page, target: "_blank", rel: "noopener noreferrer", text: "Wikimedia Commons" })
    ]);
    fig.appendChild(img); fig.appendChild(cap);
    return fig;
  }

  function aboutFor(p) {
    var summ = p.media && p.media.summary; if (!summ) return null;
    var order = [state.lang, "en", "ru", "kk"];
    for (var i = 0; i < order.length; i++) if (summ[order[i]]) return { lang: order[i], v: summ[order[i]] };
    return null;
  }
  function renderAbout(p) {
    var a = aboutFor(p); if (!a) return null;
    var badge = a.v.source === "Wikidata" ? T("badge_wikidata") : T("badge_wikipedia");
    var other = a.lang !== state.lang ? " " + fmt(T("in_lang"), { l: T("lang_names")[a.lang] }) : "";
    var url = AW.safeUrl(a.v.url);
    return el("div", { class: "about" }, [
      el("h4", {}, [T("about_place"), el("span", { class: "pill src" }, [badge])]),
      el("p", {}, [el("span", { lang: a.lang, text: a.v.text }), other ? el("small", { text: other }) : null]),
      url ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: T("read_more") }) : null
    ]);
  }

  function legLabel(id) { return id === "start" ? planStartLabel() : (id === "return" ? returnLabel() : stopName(id)); }
  function renderRoute(p) {
    var ol = el("ol");
    p.legs.forEach(function (l) {
      var from = legLabel(l.from);
      var to = legLabel(l.to);
      ol.appendChild(el("li", { text: from + " → " + to + ": ≈" + num(l.distance_m) + (state.lang === "en" ? " m, ≈" : " м, ≈") + l.walk_min + " " + minLabel() }));
    });
    var pts = [pointOf("start", p)].concat(p.stops.map(function (s) { return pointOf(s.id, p); }));
    var last = p.legs[p.legs.length - 1];
    if (p.return_to_start && last) pts.push(pointOf(last.to, p));
    var whole = AW.safeUrl(AW.directionsUrl(pts, dirOpts()));
    var st = state.result.start || {};
    var consent = null;
    if (st.kind && st.kind !== "landmark") {
      var cb = el("input", { type: "checkbox" }); cb.checked = state.dirIncludeStart;
      cb.addEventListener("change", function () { state.dirIncludeStart = cb.checked; renderResult(); });
      consent = el("label", { class: "check" }, [cb, el("span", { text: T("dir_include_start") })]);
    }
    return el("section", { class: "route", "aria-label": T("route_title") }, [el("h3", { text: T("route_title") }), ol,
      el("p", { text: T("route_order") + " " + fmt(T(p.fits ? "route_fits" : "route_not_fits"), { b: p.budget_min }) }),
      whole ? el("p", {}, [el("a", { href: whole, target: "_blank", rel: "noopener noreferrer", class: "btn-s link", text: T("dir_whole") + " ↗" })]) : null,
      consent, el("p", { class: "hint", text: T("dir_note") })]);
  }


  // ---------- name provenance (from the server; never guessed in the page)
  function nameNote(p) {
    if (p.name_is_generated) return null;
    var d = AW.nameInfo(p, state.lang), bits = [];
    // An original Latin-script name on the English page (or Cyrillic on kk/ru) needs no note.
    if (d.kind === "original" && !(state.lang === "en" && /[а-яёәіңғүұқөһ]/i.test(d.text))) return null;
    if (d.kind === "original" || d.kind === "osm_latin") {
      bits.push(T("name_kind")[d.kind]);
      if (d.descriptor) bits.push(fmt(T("name_type"), { t: d.descriptor }));
      if (d.translation) bits.push("≈ " + d.translation + " (" + T("name_descr_tr") + ")");
      if (d.latin && d.latin !== d.text) bits.push(fmt(T("name_pron"), { t: d.latin }));
    } else if (d.kind === "wikidata") bits.push(T("name_kind").wikidata);
    else if (d.kind === "override") bits.push(fmt(T("name_kind").override, { src: d.source || "" }));
    if (!bits.length) return null;
    return el("p", { class: "name-note" }, [el("span", { lang: d.lang || null, text: bits.join(" · ") })]);
  }

  // ---------- "why it fits", computed by code
  function renderFit(s) {
    var f = s.fit || {}, ul = el("ul", { class: "fit-list" });
    if (f.named) ul.appendChild(el("li", { text: T("fit_named") }));
    if (f.interests && f.interests.length) ul.appendChild(el("li", { text: fmt(T("fit_interest"), { i: f.interests.map(intentLabel).join(", ") }) }));
    ul.appendChild(el("li", { text: fmt(T("fit_walk"), { n: s.walk_from_prev_min }) }));
    if (typeof f.time_left_after_min === "number") ul.appendChild(el("li", { text: fmt(T("fit_left"), { n: Math.max(0, f.time_left_after_min) }) }));
    ul.appendChild(el("li", { text: f.hours === "ok" && f.hours_raw ? fmt(T("fit_hours_ok"), { raw: f.hours_raw }) : (f.hours_raw ? hoursText(s.hours) : T("fit_hours_unknown")) }));
    var ik = (s.indoor_basis === "osm_tag" ? "tag_" : "est_") + (s.indoor ? "in" : "out");
    ul.appendChild(el("li", { text: T("fit_indoor")[ik] }));
    if (f.wheelchair_tag) ul.appendChild(el("li", { text: fmt(T("fit_wheel"), { v: f.wheelchair_tag }) }));
    if (f.unknown && f.unknown.length) ul.appendChild(el("li", { class: "unknown", text: fmt(T("fit_unknown"), { u: f.unknown.map(function (k) { var l = state.meta.labels.unsupported[k]; return l ? (l[state.lang] || l.en) : k; }).join(", ") }) }));
    return el("div", { class: "fit" }, [el("h4", {}, [T("fit_title"), el("span", { class: "pill calc", text: T("calc_badge") })]), ul]);
  }

  // ---------- external walking directions (explicit click only)
  function pointOf(id, plan) {
    var st = state.result.start || {};
    if (id === "start") return { lat: st.lat, lon: st.lon, private: st.kind !== "landmark" };
    if (id === "return") { var o = state.walk && state.walk.origin.start; return o ? { lat: o.lat, lon: o.lon, private: o.kind !== "landmark" } : null; }
    var s = plan.stops.filter(function (x) { return x.id === id; })[0];
    return s ? { lat: s.poi.lat, lon: s.poi.lon } : null;
  }
  function dirOpts() { return { includeStart: state.dirIncludeStart }; }
  function directionsRow(s, plan) {
    var leg = plan.legs.filter(function (l) { return l.to === s.id; })[0]; if (!leg) return null;
    var a = pointOf(leg.from, plan), b = pointOf(s.id, plan);
    var g = AW.safeUrl(AW.directionsUrl([a, b], dirOpts()));
    var o = (!a.private || state.dirIncludeStart) ? AW.safeUrl(AW.directionsUrl([a, b], { provider: "osm" })) : null;
    if (!g) return null;
    return el("p", { class: "dir-row" }, [el("a", { href: g, target: "_blank", rel: "noopener noreferrer", text: T("dir_stop") + " ↗" }),
      o ? " · " : null, o ? el("a", { href: o, target: "_blank", rel: "noopener noreferrer", text: T("dir_osm") + " ↗" }) : null]);
  }

  // ---------- plan styles (same places, same limits; deterministic)
  function renderStyles(r, p) {
    var st = (r.styles || []).filter(function (x) { return x.stop_ids && x.stop_ids.length; });
    if (st.length < 2) return null;
    var cur = p.stops.map(function (s) { return s.id; }).join("|");
    var panel = el("section", { class: "panel styles", "aria-labelledby": "stTitle" }, [el("h3", { id: "stTitle", text: T("styles_title") }), el("p", { class: "hint", text: T("styles_help") })]);
    var grid = el("div", { class: "style-grid" });
    st.forEach(function (x) {
      var isCur = x.stop_ids.join("|") === cur;
      var names = x.stops.map(function (q) { return AW.displayName(q, state.lang) + " (" + catLabel(q.category) + ")"; });
      var facts = fmt(T("style_facts"), { w: x.walk_min, t: x.total_min, o: x.outdoor_min }) + (x.unknown_hours ? " · " + fmt(T("style_unknown_hours"), { n: x.unknown_hours }) : "");
      grid.appendChild(el("div", { class: "style-card" + (isCur ? " current" : "") }, [
        el("h4", { text: (T("style")[x.key] || x.key) }), el("ol", {}, names.map(function (n) { return el("li", { text: n }); })),
        el("p", { class: "hint", text: facts }),
        isCur ? el("span", { class: "pill", text: T("style").current }) :
          el("button", { type: "button", class: "btn-s", text: T("style_use"), onclick: function () {
            var keep = p.stops.map(function (s) { return s.id; });
            replanWith(x.stop_ids.map(function (id, i) { return { id: id, visit_minutes: x.visit_minutes ? x.visit_minutes[i] : 20 }; }), "style_ok", { explain: true, keep_ids: keep });
          } })
      ]));
    });
    panel.appendChild(grid);
    return panel;
  }

  // ---------- active walk: "I'm here" and replanning the rest (self-reported, no tracking)
  function nowMs() { return Date.now() + state.clockOffset; }
  function hhmm(ms) { return astanaParts(ms).time; }
  function renderWalkPanel(p) {
    if (!state.walk) {
      return el("div", { class: "actions walk-start" }, [el("button", { type: "button", class: "btn-s primary", text: T("walk_start"), onclick: startWalk })]);
    }
    var box = el("section", { class: "panel walk", "aria-labelledby": "wkTitle" });
    var w = state.walk, done = w.done.length;
    box.appendChild(el("h3", { id: "wkTitle", text: T("walk_title") }));
    box.appendChild(el("p", { role: "status", text: fmt(T("walk_progress"), { d: done, t: w.total, s: hhmm(w.startedMs) }) }));
    var from = el("select", { "aria-label": T("walk_replan_from") });
    [["last", T("walk_from_last")], ["geo", T("walk_from_geo")]].forEach(function (o) { var op = el("option", { value: o[0], text: o[1] }); if (w.from === o[0]) op.selected = true; from.appendChild(op); });
    from.addEventListener("change", function () { w.from = from.value; });
    box.appendChild(el("div", { class: "opt-row" }, [el("label", {}, [el("span", { text: T("walk_replan_from") + " " }), from]),
      el("button", { type: "button", class: "btn-s primary", text: T("walk_replan"), onclick: replanRemaining }),
      el("button", { type: "button", class: "btn-s", text: T("walk_end"), onclick: function () { state.walk = null; renderResult(); } })]));
    box.appendChild(el("p", { class: "hint", text: fmt(T("walk_note"), { s: w.origin.label() }) }));
    if (w.msg) box.appendChild(el("p", { class: "inline-msg", role: "status", text: w.msg }));
    return box;
  }
  function startWalk() {
    var st = clone(state.result.start), label = planStartLabel();
    state.walk = { startedMs: nowMs(), done: [], total: state.plan.stops.length, from: "last", budget: state.plan.budget_min,
                   origin: { start: st, label: function () { return st.display_names ? AW.displayName({ display_names: st.display_names }, state.lang) : label; } }, msg: null };
    renderResult();
  }
  function toggleDone(id) {
    var w = state.walk, i = w.done.indexOf(id);
    if (i >= 0) w.done.splice(i, 1); else { w.done.push(id); addUnique(state.visited, id); persistVisited(); }
    w.msg = null; renderReset(); renderResult();
  }
  function replanRemaining() {
    var w = state.walk; if (!w || state.busy) return;
    var left = state.plan.stops.filter(function (s) { return w.done.indexOf(s.id) < 0; });
    if (!left.length) { w.msg = T("walk_none_left"); renderResult(); return; }
    function send(start) {
      var b = actionBody();
      b.text = "";                                   // a duration in the old text must not reset the time
      b.start = start;
      b.plan_stops = left.map(function (s) { return { id: s.id, visit_minutes: s.visit_minutes }; });
      var o = w.origin.start;
      if (o.back) b.return_to = o.kind === "landmark" ? { type: "landmark", id: o.landmark_id } : { type: "coords", lat: o.lat, lon: o.lon };
      if (!b.deadline) b.budget = Math.max(5, w.budget - Math.round((nowMs() - w.startedMs) / 60000));
      post("/api/replan", b, function (status, j) {
        if (status !== 200 || !j.plan) { w.msg = status !== 200 ? errorText(j.error || { code: "server" }) : planFailText(j); state.result.suggestions = j.suggestions || []; renderResult(); return; }
        var prev = state.plan; setPlan(j.plan, prev);
        j.start.kind = start.type === "landmark" ? j.start.kind : "walk";
        state.result.start = j.start;
        state.result.constraints = j.constraints || state.result.constraints;
        w.done = []; w.total = j.plan.stops.length; w.budget = j.plan.budget_min; w.startedMs = nowMs();
        w.msg = fmt(T("walk_replanned"), { s: planStartLabel() });
        renderResult();
      });
    }
    if (w.from === "geo") {
      if (!navigator.geolocation) { w.msg = T("walk_geo_fail"); renderResult(); return; }
      navigator.geolocation.getCurrentPosition(function (pos) { send({ type: "geo", lat: pos.coords.latitude, lon: pos.coords.longitude }); },
        function () { w.msg = T("walk_geo_fail"); renderResult(); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
      return;
    }
    var last = w.done[w.done.length - 1];
    if (!last) { w.msg = T("walk_need_mark"); renderResult(); return; }
    send({ type: "landmark", id: last });
  }

  // ---------- report a name/data problem (local only; nothing is sent)
  function saveReports() { if (store.ok) store.set("aw-reports", JSON.stringify(state.reports.slice(-200))); }
  function renderReportForm(s) {
    var f = el("form", { class: "report", "aria-label": T("report_title") });
    var field = el("select", { id: "rpField" });
    Object.keys(T("report_fields")).forEach(function (k) { field.appendChild(el("option", { value: k, text: T("report_fields")[k] })); });
    var value = el("input", { type: "text", id: "rpValue", maxlength: "200" });
    var reason = el("textarea", { id: "rpReason", maxlength: "500", rows: "2" });
    var src = el("input", { type: "url", id: "rpSource", maxlength: "300", placeholder: "https://" });
    var msg = el("p", { class: "inline-msg", role: "status" });
    f.appendChild(el("h4", { text: T("report_title") + ": " + placeName(s.poi) }));
    f.appendChild(el("label", {}, [el("span", { text: T("report_field") }), field]));
    f.appendChild(el("label", {}, [el("span", { text: T("report_value") }), value]));
    f.appendChild(el("label", {}, [el("span", { text: T("report_reason") }), reason]));
    f.appendChild(el("label", {}, [el("span", { text: T("report_source") }), src]));
    f.appendChild(el("p", { class: "hint", text: T("report_note") }));
    f.appendChild(el("div", { class: "actions" }, [el("button", { type: "submit", class: "btn-s primary", text: T("report_save") }),
      el("button", { type: "button", class: "btn-s", text: T("report_cancel"), onclick: function () { state.reportFor = null; renderResult(); } })]));
    f.appendChild(msg);
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var url = src.value.trim();
      if (url && !/^https:\/\/[^\s"'<>]+$/.test(url)) { msg.textContent = T("report_bad_url"); return; }
      state.reports.push({ poi_id: s.id, osm_url: AW.safeUrl(s.poi.source_url), name_shown: placeName(s.poi), original_name: s.poi.name,
        field: field.value, proposed_value: value.value.trim().slice(0, 200), reason: reason.value.trim().slice(0, 500),
        source_url: url || null, created: astanaParts(nowMs()).date, status: "unverified user report" });
      saveReports(); state.reportFor = null; state.actionMsg = { kind: "info", text: T("report_saved") }; renderResult();
    });
    setTimeout(function () { field.focus(); }, 0);
    return f;
  }
  function renderReports() {
    var panel = el("section", { class: "panel", "aria-labelledby": "rpTitle" }, [el("h3", { id: "rpTitle", text: fmt(T("report_list"), { n: state.reports.length }) })]);
    if (!state.reports.length) { panel.hidden = true; return panel; }
    panel.appendChild(el("div", { class: "actions" }, [
      el("button", { type: "button", class: "btn-s", text: T("report_download"), onclick: function () {
        var blob = new Blob([JSON.stringify({ about: "Astana Walks user reports: unverified, not published", reports: state.reports }, null, 1)], { type: "application/json" });
        var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "astana-walks-reports.json";
        document.body.appendChild(a); a.click(); document.body.removeChild(a); setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
      } }),
      el("button", { type: "button", class: "btn-s", text: T("report_delete"), onclick: function () { state.reports = []; store.del("aw-reports"); state.actionMsg = { kind: "info", text: T("report_deleted") }; renderResult(); } })]));
    panel.appendChild(el("p", { class: "hint", text: T("report_note") }));
    return panel;
  }

  // ---------- export
  function exportOpts(p) {
    var start = state.result.start || {};
    var coords = null;
    if (state.includeCoords && start.kind !== "landmark" && typeof start.lat === "number") coords = start.lat.toFixed(5) + ", " + start.lon.toFixed(5);
    var label = start.kind === "landmark" && start.names ? (start.names[state.lang] || start.names.en) : T("ex_start_generic");
    var ds = state.meta && state.meta.dataset;
    return { T: T, lang: state.lang, plan: p, startLabel: label, startCoords: coords, datasetDate: ds ? (ds.collected_at || "").slice(0, 10) : "",
             deadline: state.result.constraints && state.result.constraints.deadline, catLabel: catLabel, unnamed: T("unnamed_playground") };
  }
  function renderExport(p) {
    var panel = el("section", { class: "panel", "aria-labelledby": "exTitle" }, [el("h3", { id: "exTitle", text: T("export_title") })]);
    var row = el("div", { class: "actions" });
    var status = el("p", { class: "inline-msg", role: "status" });
    row.appendChild(el("button", { type: "button", class: "btn-s primary", text: T("copy_plan"), onclick: function () { copyPlan(p, status, panel); } }));
    row.appendChild(el("button", { type: "button", class: "btn-s", text: T("save_plan"), onclick: function () { savePlan(p, status); } }));
    if (navigator.share) row.appendChild(el("button", { type: "button", class: "btn-s", text: T("share_plan"), onclick: function () {
      try { navigator.share({ title: T("ex_title"), text: AW.planText(exportOpts(p)) }).catch(function () { /* user cancelled */ }); } catch (e) { /* unsupported */ } } }));
    panel.appendChild(row);
    var start = state.result.start || {};
    if (start.kind && start.kind !== "landmark") {
      var cb = el("input", { type: "checkbox" }); cb.checked = state.includeCoords;
      cb.addEventListener("change", function () { state.includeCoords = cb.checked; });
      panel.appendChild(el("label", { class: "check" }, [cb, el("span", { text: T("include_coords") })]));
    }
    panel.appendChild(status);
    panel.appendChild(el("p", { class: "hint", text: T("export_note") }));
    if (state.exportText) {
      var ta = el("textarea", { readonly: true, "aria-label": T("copy_plan") }); ta.value = state.exportText; panel.appendChild(ta);
      setTimeout(function () { try { ta.focus(); ta.select(); } catch (e) { /* ignore */ } }, 0);
    }
    return panel;
  }
  function copyPlan(p, status) {
    var text = AW.planText(exportOpts(p));
    function manual() { state.exportText = text; renderResult(); var s = document.querySelector("#output .panel .inline-msg"); if (s) s.textContent = T("copy_manual"); }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { state.exportText = null; status.textContent = T("copied"); }, manual);
      } else manual();
    } catch (e) { manual(); }
  }
  function savePlan(p, status) {
    try {
      var html = AW.planHtml(exportOpts(p));
      var blob = new Blob([html], { type: "text/html;charset=utf-8" });
      var a = document.createElement("a");
      var stamp = (state.result.constraints && state.result.constraints.now || "").replace(/[-:T]/g, "").slice(0, 12);
      a.href = URL.createObjectURL(blob); a.download = "astana-walks-plan-" + (stamp || "plan") + ".html";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
      status.textContent = T("saved");
    } catch (e) { state.exportText = AW.planText(exportOpts(p)); renderResult(); }
  }

  // ---------- City Bingo
  function passport() { return store.getJSON("aw-passport", []); }
  function renderBingo(p) {
    var tasks = AW.bingoTasks(p.stops);
    var done = tasks.filter(function (t) { return state.bingo.done[t.key]; }).length;
    var panel = el("section", { class: "panel", "aria-labelledby": "bgTitle" }, [el("h3", { id: "bgTitle", text: T("bingo_title") }), el("p", { class: "hint", text: T("bingo_help") })]);
    var ul = el("ul", { class: "bingo-list" });
    tasks.forEach(function (t) {
      var stop = t.poi_id ? p.stops.filter(function (s) { return s.id === t.poi_id; })[0] : null;
      var text = fmt(T(t.tpl), { name: stop ? placeName(stop.poi) : "" });
      var cb = el("input", { type: "checkbox" }); cb.checked = !!state.bingo.done[t.key];
      cb.addEventListener("change", function () { if (cb.checked) state.bingo.done[t.key] = true; else delete state.bingo.done[t.key]; renderResult(); });
      ul.appendChild(el("li", { class: cb.checked ? "done" : null }, [el("label", {}, [cb, el("span", { text: (stop ? stop.n + ". " : "") + text })])]));
    });
    panel.appendChild(ul);
    panel.appendChild(el("div", { class: "progress" }, [
      el("span", { class: "meter", "aria-hidden": "true" }, [el("i", { style: "width:" + Math.round(100 * done / tasks.length) + "%" })]),
      el("span", { text: fmt(T("bingo_progress"), { d: done, t: tasks.length }) })]));
    if (!store.ok) { panel.appendChild(el("p", { class: "hint", text: T("storage_off") })); return panel; }
    var opt = el("input", { type: "checkbox" }); opt.checked = state.passportOn;
    opt.addEventListener("change", function () { state.passportOn = opt.checked; store.set("aw-passport-on", opt.checked ? "1" : "0"); renderResult(); });
    panel.appendChild(el("label", { class: "check" }, [opt, el("span", { text: T("bingo_save_opt") })]));
    var msg = el("p", { class: "inline-msg", role: "status", text: state.passportOn ? fmt(T("bingo_count"), { n: passport().length }) : "" });
    if (state.passportOn) {
      panel.appendChild(el("div", { class: "actions" }, [
        el("button", { type: "button", class: "btn-s", text: T("bingo_save"), onclick: function () {
          var list = passport();
          list.push({ date: (state.result.constraints && state.result.constraints.now || "").slice(0, 10), places: p.stops.map(function (s) { return placeName(s.poi); }), done: done, total: tasks.length });
          store.set("aw-passport", JSON.stringify(list.slice(-100)));
          msg.textContent = fmt(T("bingo_saved"), { n: list.length });
        } }),
        el("button", { type: "button", class: "btn-s", text: T("bingo_delete"), onclick: function () { store.del("aw-passport"); msg.textContent = T("bingo_deleted"); } })
      ]));
    }
    panel.appendChild(msg);
    return panel;
  }

  // ---------- deadline countdown (no model calls; recalculation is explicit)
  function startCountdown() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    var dl = state.result && state.result.constraints && state.result.constraints.deadline;
    if (!dl || !state.plan) return;
    function tick() {
      var n = document.getElementById("deadlineLive"); if (!n) { clearInterval(state.timer); state.timer = null; return; }
      var left = Math.floor((astanaMs(dl.at) - (Date.now() + state.clockOffset)) / 60000);
      var tight = left - dl.buffer_min < state.plan.total_min;
      n.textContent = "";
      n.className = "deadline-live" + (tight ? " tight" : "");
      n.appendChild(document.createTextNode(fmt(T("deadline_left"), { at: dl.at_time, n: Math.max(0, left), b: dl.buffer_min })));
      if (tight) {
        n.appendChild(el("span", { text: " " + fmt(T("deadline_tight"), { at: dl.at_time }) + " " }));
        n.appendChild(el("button", { type: "button", class: "btn-s primary", text: T("recalc"), onclick: function () { replanWith(currentStops(), "removed_ok"); } }));
      }
    }
    tick();
    state.timer = setInterval(tick, 30000);
  }

  function renderFallback(cands) {
    var ul = el("ul");
    cands.forEach(function (c) {
      var url = AW.safeUrl(c.poi.source_url);
      ul.appendChild(el("li", {}, [url ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: placeName(c.poi) }) : placeName(c.poi),
        ": " + catLabel(c.poi.category) + ", ≈" + num(c.distance_m) + (state.lang === "en" ? " m, ≈" : " м, ≈") + c.walk_min + " " + minLabel() + ". " + hoursText(c.hours)]));
    });
    return el("div", { class: "fallback" }, [el("strong", { text: T("fallback_title") }), ul]);
  }

  function renderTrace(r) {
    var t = r.trace, u = r.understood || {};
    var d = el("details", { class: "trace" }, [el("summary", { text: T("trace_title") })]);
    var excl = Object.keys(t.excluded || {}).map(function (k) { return fmt(T("t_excl")[k] || k, { n: t.excluded[k] }); });
    var k = t.candidates.length;
    d.appendChild(el("ol", {}, [
      el("li", { text: fmt(T("t_step1"), { ql: T("lang_names")[u.query_lang] || u.query_lang, cats: (u.categories || []).map(catLabel).join(", "), b: u.budget_min }) }),
      el("li", { text: fmt(T("t_step2"), { n: t.considered, excl: excl.length ? excl.join("; ") : T("t_step2_none") }) }),
      el("li", { text: fmt(T("t_step3"), { k: k }) }),
      el("li", { text: t.model ? fmt(T("t_step4"), { model: t.model, s: t.seconds, k: k }) : T("t_step4_none") }),
      el("li", { text: T("t_step5") })
    ]));
    if (k) {
      var thead = el("thead", {}, [el("tr", {}, T("t_cols").map(function (c) { return el("th", { scope: "col", text: c }); }))]);
      var tbody = el("tbody");
      t.candidates.forEach(function (c) {
        tbody.appendChild(el("tr", {}, [el("td", { text: c.alias || "" }), el("td", { text: placeName(c.poi) }), el("td", { text: catLabel(c.poi.category) }),
          el("td", { text: num(c.distance_m) }), el("td", { text: String(c.walk_min) }), el("td", { text: T("t_hours")[c.hours.key] || c.hours.key }), el("td", { text: String(c.score) })]));
      });
      d.appendChild(el("div", { class: "table-wrap" }, [el("table", {}, [thead, tbody])]));
    }
    if (t.dropped && t.dropped.length) d.appendChild(el("p", { text: T("t_dropped") + " " + t.dropped.map(function (x) { return fmt(T("t_drop")[x.code] || x.code, x); }).join("; ") }));
    if (t.retrieval_mode) d.appendChild(el("p", { text: fmt(T("t_mode"), { m: T("t_modes")[t.retrieval_mode] || t.retrieval_mode }) }));
    if (u.retrieval_mode_note) d.appendChild(el("p", { text: fmt(T("t_mode_note"), { d: u.retrieval_mode_note }) }));
    if (t.repair_attempts) d.appendChild(el("p", { text: T("t_repair") }));
    var tm = t.timings_ms || {};
    if (tm.retrieval !== undefined) d.appendChild(el("p", { class: "hint", text: fmt(T("t_timings"), { r: tm.retrieval, p: tm.planning === undefined ? "–" : tm.planning, g: tm.generation === undefined ? "–" : tm.generation }) }));
    if (t.evidence_json) { d.appendChild(el("h4", { text: T("t_evidence") })); d.appendChild(el("pre", { text: t.evidence_json })); }
    if (t.raw_model_text) { d.appendChild(el("h4", { text: T("t_raw") })); d.appendChild(el("pre", { text: t.raw_model_text })); }
    return d;
  }

  // ------------------------------------------------------------------ map (optional; needs internet)
  function loadLeafletFallback(cb) {
    if (window.L || state.leafletTried) return cb();
    state.leafletTried = true;
    var css = document.createElement("link"); css.rel = "stylesheet"; css.href = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"; document.head.appendChild(css);
    var s = document.createElement("script"); s.src = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";
    s.onload = cb; s.onerror = cb; document.head.appendChild(s);
  }

  function drawMap(p) {
    var box = document.getElementById("map");
    if (!box) return;
    if (!window.L && !state.leafletTried) { loadLeafletFallback(function () { drawMap(p); }); return; }
    if (!window.L) { box.removeAttribute("role"); box.style.height = "auto"; box.appendChild(el("p", { class: "map-cap", text: T("map_unavailable") })); return; }
    try {
      if (state.map) { state.map.remove(); state.map = null; }
      var start = state.result.start;
      var map = L.map(box, { scrollWheelZoom: false });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap", referrerPolicy: "strict-origin-when-cross-origin" }).addTo(map);
      var pts = [[start.lat, start.lon]];
      L.marker([start.lat, start.lon], { icon: L.divIcon({ className: "", html: '<div class="marker-start"></div>', iconSize: [22, 22], iconAnchor: [11, 11] }), title: planStartLabel(), keyboard: false }).addTo(map);
      p.stops.forEach(function (s) {
        pts.push([s.poi.lat, s.poi.lon]);
        L.marker([s.poi.lat, s.poi.lon], { icon: L.divIcon({ className: "", html: '<div class="marker-num">' + Number(s.n) + "</div>", iconSize: [32, 32], iconAnchor: [16, 16] }), title: placeName(s.poi), keyboard: false }).addTo(map);
      });
      var line = pts.slice();
      var lastLeg = p.legs[p.legs.length - 1];
      if (p.return_to_start && lastLeg) { var rp = pointOf(lastLeg.to, p) || start; line.push([rp.lat, rp.lon]); if (lastLeg.to === "return") pts.push([rp.lat, rp.lon]); }
      L.polyline(line, { color: "#395886", weight: 3, dashArray: "6 8", opacity: .8 }).addTo(map);
      map.fitBounds(pts, { padding: [36, 36], maxZoom: 16 });
      state.map = map;
    } catch (e) { box.textContent = ""; box.appendChild(el("p", { class: "map-cap", text: T("map_unavailable") })); }
  }

  // ------------------------------------------------------------------ read aloud (browser speech, no network)
  var speakingBtn = null;
  function stopSpeaking() {
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
    if (speakingBtn) { speakingBtn.querySelector("span").textContent = T("speak"); speakingBtn = null; }
  }
  function speak(text, btn, lang) {
    if (!window.speechSynthesis) return;
    if (speakingBtn === btn) { stopSpeaking(); return; }
    stopSpeaking();
    var u = new SpeechSynthesisUtterance(text), code = { kk: "kk-KZ", ru: "ru-RU", en: "en-US" }[lang] || "ru-RU";
    u.lang = code;
    var voices = window.speechSynthesis.getVoices();
    var v = voices.filter(function (x) { return x.lang && x.lang.slice(0, 2) === code.slice(0, 2); })[0];
    if (!v && lang === "kk") v = voices.filter(function (x) { return x.lang && x.lang.slice(0, 2) === "ru"; })[0];
    if (v) u.voice = v;
    u.rate = root.getAttribute("data-vision") === "on" ? 0.9 : 1;
    u.onend = function () { if (speakingBtn === btn) stopSpeaking(); };
    speakingBtn = btn; btn.querySelector("span").textContent = T("stop");
    window.speechSynthesis.speak(u);
  }

  // ------------------------------------------------------------------ init
  function initDeadlineDefaults(nowStr) {
    var nowMs = isNaN(astanaMs(nowStr)) ? Date.now() : astanaMs(nowStr);
    var today = astanaParts(nowMs).date;
    var target = nowMs + 60 * 60000; target = Math.ceil(target / 300000) * 300000;
    var tp = astanaParts(target);
    state.deadline.date = today;
    state.deadline.time = tp.date === today ? tp.time : "23:55";   // default stays today
    document.getElementById("dlDate").value = state.deadline.date;
    document.getElementById("dlTime").value = state.deadline.time;
  }

  function init() {
    applyStaticTexts();
    document.querySelectorAll("[data-lang]").forEach(function (b) { b.addEventListener("click", function () { setLang(b.getAttribute("data-lang")); }); });
    document.getElementById("themeBtn").addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next); store.set("aw-theme", next); applyStaticTexts();
    });
    document.getElementById("visionBtn").addEventListener("click", function () {
      var next = root.getAttribute("data-vision") === "on" ? "off" : "on";
      root.setAttribute("data-vision", next); store.set("aw-vision", next); applyStaticTexts();
      if (state.map) setTimeout(function () { state.map.invalidateSize(); }, 50);
    });
    document.querySelectorAll('input[name="mode"]').forEach(function (r) {
      r.addEventListener("change", function () { state.mode = r.value; renderSentence(); document.getElementById("geoMsg").textContent = ""; if (r.value === "geo" && !state.geo) locate(); });
    });
    document.getElementById("geoBtn").addEventListener("click", locate);
    document.getElementById("askForm").addEventListener("submit", function (e) { submit(e, null); });
    document.getElementById("surpriseBtn").addEventListener("click", function () { submit(null, "surprise"); });
    // pace
    document.querySelectorAll("[data-pace]").forEach(function (b) { b.addEventListener("click", function () { state.pace = b.getAttribute("data-pace"); store.set("aw-pace", state.pace); applyStaticTexts(); syncPersonOne(); }); });
    // deadline
    document.getElementById("dlOn").addEventListener("change", function (e) { state.deadline.on = e.target.checked; renderDeadlineReturn(); });
    document.getElementById("dlDate").addEventListener("change", function (e) { state.deadline.date = e.target.value; });
    document.getElementById("dlTime").addEventListener("change", function (e) { state.deadline.time = e.target.value; });
    document.getElementById("dlBuf").addEventListener("input", function (e) { var v = parseInt(e.target.value, 10); state.deadline.buffer = isNaN(v) ? 10 : v; });
    // outdoor
    document.getElementById("odSel").addEventListener("change", function (e) { state.outdoor.sel = e.target.value; renderOutdoorSelect(); });
    document.getElementById("odCustom").addEventListener("input", function (e) { var v = parseInt(e.target.value, 10); state.outdoor.custom = isNaN(v) ? 0 : v; });
    document.getElementById("odStrict").addEventListener("change", function (e) { state.outdoor.strict = e.target.checked; });
    // group
    document.getElementById("grpOn").addEventListener("change", function (e) {
      state.group.on = e.target.checked;
      state.group.people = state.group.on ? [newPerson(0), newPerson(1)] : [];   // solo mode keeps no stale group settings
      renderGroup();
    });
    document.getElementById("grpAdd").addEventListener("click", function () { if (state.group.people.length < 5) { state.group.people.push(newPerson(state.group.people.length)); renderGroup(); } });
    // exclusions
    document.getElementById("remember").addEventListener("change", function (e) {
      state.remember = e.target.checked; store.set("aw-remember", state.remember ? "1" : "0");
      if (state.remember) persistVisited(); else store.del("aw-visited");
    });
    document.getElementById("resetEx").addEventListener("click", resetExclusions);
    // source-based filters
    document.getElementById("fHours").addEventListener("change", function (e) { state.filters.known_hours = e.target.checked; });
    document.getElementById("fWheel").addEventListener("change", function (e) { state.filters.wheelchair = e.target.checked; });
    renderSentence(); renderExamples(); renderEmpty(); renderReset(); initDeadlineDefaults("");

    fetch("/api/meta").then(function (r) { return r.json(); }).then(function (m) {
      state.meta = m;
      rememberPlaces(m.landmarks);
      if (m.landmarks && m.landmarks.length) state.startId = m.landmarks[0].id;
      document.getElementById("useWeather").closest("label").hidden = !m.weather_enabled;
      if (m.now) initDeadlineDefaults(m.now);
      applyStaticTexts(); renderSentence(); renderChips(); renderFooter();
      window.__awReady = true;
      loadGallery();
    }).catch(function () { showError({ code: "server" }); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
