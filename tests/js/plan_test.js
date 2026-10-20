// Tests for web/assets/plan.js (export, escaping, safe links, transliteration, Bingo).
// SYNTHETIC plan data. Run: node tests/js/plan_test.js
"use strict";
const assert = require("assert");
const path = require("path");
const AW = require(path.join(__dirname, "..", "..", "web", "assets", "plan.js"));
global.window = {};
require(path.join(__dirname, "..", "..", "web", "assets", "i18n.js"));
require(path.join(__dirname, "..", "..", "web", "assets", "i18n2.js"));

const evil = '<img src=x onerror=alert(1)>';
const plan = {
  total_min: 52, budget_min: 60, walk_min: 22, end_eta: "15:22", return_to_start: true,
  stops: [
    { n: 1, id: "osm:node/1", visit_minutes: 20, walk_from_prev_min: 6, distance_from_prev_m: 340, arrive_at: "14:36",
      poi: { id: "osm:node/1", name: "Кофе " + evil, names: {}, category: "cafe", source_url: "javascript:alert(1)" },
      why: "Близко " + evil, activity: "Выпейте кофе" },
    { n: 2, id: "osm:way/2", visit_minutes: 10, walk_from_prev_min: 5, distance_from_prev_m: 300, arrive_at: "15:02",
      poi: { id: "osm:way/2", name: "Хан Шатыр", names: { en: "Khan Shatyr" }, category: "mall", source_url: "https://www.openstreetmap.org/way/2",
             display_names: { kk: { text: "Хан Шатыр", kind: "original" }, ru: { text: "Хан Шатыр", kind: "original" }, en: { text: "Khan Shatyr", kind: "osm" } } },
      why: "", activity: "" }
  ],
  legs: [{ walk_min: 6 }, { walk_min: 5 }, { walk_min: 11 }]
};
let passed = 0;
function test(name, fn) { fn(); passed++; }

for (const lang of ["kk", "ru", "en"]) {
  const L = window.I18N[lang];
  const T = (k) => (L[k] !== undefined ? L[k] : k);
  const opts = { T, lang, plan, startLabel: "EXPO", startCoords: null, datasetDate: "2026-10-19",
                 deadline: { at_time: "15:30", buffer_min: 10 }, catLabel: (c) => c, unnamed: "?" };
  test("text " + lang, () => {
    const txt = AW.planText(opts);
    assert(txt.includes("EXPO"));
    assert(txt.includes("52") && txt.includes("60"));
    assert(txt.includes("15:30"));
    assert(!txt.includes("javascript:"), "unsafe link must be dropped");
    assert(txt.includes("https://www.openstreetmap.org/way/2"));
    assert(!/51\.\d{3}/.test(txt), "no coordinates by default");
    assert(!/\{\w+\}/.test(txt), "no unfilled placeholders: " + txt);
    // order and durations from the canonical plan
    assert(txt.indexOf("1. ") < txt.indexOf("2. "));
    assert(txt.includes("20") && txt.includes("10"));
  });
  test("html " + lang, () => {
    const html = AW.planHtml(opts);
    assert(!html.includes("<img"), "HTML must be escaped");
    assert(html.includes("&lt;img"));
    assert(!html.includes("javascript:"));
    assert(!/<script/i.test(html), "no scripts in the export");
    assert(!/https:\/\/(fonts|unpkg|tile)/.test(html), "no external resources needed offline");
    assert(html.startsWith("<!doctype html>"));
    assert(!/\{\w+\}/.test(html));
  });
}
test("descriptions in exports", () => {
  const T = (k) => window.I18N.ru[k];
  const p2 = JSON.parse(JSON.stringify(plan));
  p2.stops[1].poi.media = { summary: { ru: { text: "Описание <script>x</script>", source: "Wikipedia", url: "https://ru.wikipedia.org/wiki/X" } } };
  const o = { T, lang: "ru", plan: p2, startLabel: "EXPO", startCoords: null, datasetDate: "x", deadline: null, catLabel: (c) => c };
  assert(AW.planText(o).includes("Описание"));
  const html = AW.planHtml(o);
  assert(html.includes("Описание &lt;script&gt;") && !html.includes("<script>x"));
  assert.strictEqual(AW.about(p2.stops[1].poi, "kk").text.startsWith("Описание"), true, "falls back to another language");
});
test("coordinates only with opt-in", () => {
  const T = (k) => window.I18N.en[k];
  const txt = AW.planText({ T, lang: "en", plan, startLabel: "Starting point", startCoords: "51.08900, 71.41600",
                            datasetDate: "x", deadline: null, catLabel: (c) => c });
  assert(txt.includes("51.08900, 71.41600"));
});
test("names come from the server, never transliterated in the page", () => {
  assert.strictEqual(AW.displayName(plan.stops[1].poi, "en"), "Khan Shatyr");
  assert.strictEqual(AW.displayName(plan.stops[1].poi, "ru"), "Хан Шатыр");
  // no display_names: the original name is shown unchanged (no Latin guess)
  assert.strictEqual(AW.displayName({ name: "Мега Силк Вей", names: {} }, "en"), "Мега Силк Вей");
  assert.strictEqual(AW.displayName({ name: "x", name_is_generated: true }, "en", "Playground"), "Playground");
  const bridge = { name: "Атырау көпірі", display_names: { en: { text: "Атырау көпірі", kind: "original", translation: "Atyrau Bridge", latin: "Atyrau kopiri" } } };
  const T = (k) => window.I18N.en[k];
  const line = AW.nameLine(bridge, "en", T);
  assert(line.startsWith("Атырау көпірі") && line.includes("Atyrau Bridge") && line.includes(T("name_descr_tr")), line);
  assert(!line.includes("kopiri"), "pronunciation aid is not part of the name");
});
test("directions links", () => {
  const a = { lat: 51.128, lon: 71.43 }, b = { lat: 51.13, lon: 71.44 }, c = { lat: 51.12, lon: 71.41 };
  const g = AW.directionsUrl([a, b, c]);
  assert(g.startsWith("https://www.google.com/maps/dir/?api=1&origin=51.12800%2C71.43000"));
  assert(g.includes("travelmode=walking") && g.includes("&waypoints=51.13000%2C71.44000"));
  const priv = AW.directionsUrl([{ lat: 51.1, lon: 71.4, private: true }, b]);
  assert(!priv.includes("origin="), "a private start is not sent without consent");
  assert(AW.directionsUrl([{ lat: 51.1, lon: 71.4, private: true }, b], { includeStart: true }).includes("origin=51.10000"));
  assert(AW.directionsUrl([a, b], { provider: "osm" }).includes("fossgis_osrm_foot"));
  assert.strictEqual(AW.directionsUrl([a, b, c], { provider: "osm" }), null, "OSM: single leg only");
  assert.strictEqual(AW.directionsUrl([a]), null);
});
test("safeUrl", () => {
  assert.strictEqual(AW.safeUrl("https://a.b/c"), "https://a.b/c");
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "/relative", "https://a.b/\"onmouseover=x", null]) assert.strictEqual(AW.safeUrl(bad), null, bad);
});
test("bingo tasks and replacement invalidation", () => {
  const tasks = AW.bingoTasks(plan.stops);
  assert.strictEqual(tasks.length, 3);
  assert.strictEqual(tasks[0].key, "osm:node/1:bg_new");
  const done = {}; done[tasks[0].key] = true; done[tasks[1].key] = true;
  // replace stop 1 with a park: its completion must not transfer
  const replaced = [{ n: 1, id: "osm:node/9", poi: { category: "park" } }, plan.stops[1]];
  const kept = AW.carryBingo(done, AW.bingoTasks(replaced));
  assert(!kept["osm:node/9:bg_bench"], "new place starts not done");
  assert(kept[tasks[1].key], "unchanged place keeps its completion");
  assert(!kept[tasks[0].key], "old place's task is gone");
  for (const lang of ["kk", "ru", "en"]) for (const t of tasks) assert(window.I18N[lang][t.tpl], lang + " " + t.tpl);
});
console.log("plan.js tests passed: " + passed);
