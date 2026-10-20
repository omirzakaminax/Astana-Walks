r"""Optional end-to-end browser check (needs `pip install playwright` + a Chromium).

Runs against an already running server, e.g.:
  $env:WALKS_DATA_PATH="tests\\e2e\\e2e_pois.json"; .venv\\Scripts\\python server.py --port 8765 --no-browser
  .venv\\Scripts\\python tests\\e2e\\browser_check.py http://localhost:8765 shots
The E2E dataset is SYNTHETIC. With a real model, answers are slower but the checks are the same.
For a model-free run use the FAKE model: python tests\e2e\mock_ollama.py 11999 and start the server
with OLLAMA_URL=http://127.0.0.1:11999 OLLAMA_MODEL=qwen3:4b-instruct WEATHER_ENABLED=0.
Leaflet (map library) is replaced by a small STUB when its CDN is unreachable, so map-click logic can be
checked offline; real tile rendering is NOT tested by this script.
"""
import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "shots")
OUT.mkdir(exist_ok=True)
CYR = re.compile(r"[а-яёәіңғүұқөһ]", re.I)
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


async def wait_result(pg):
    await pg.wait_for_function("document.getElementById('results').getAttribute('aria-busy') === 'false'", timeout=30000)
    await pg.wait_for_timeout(250)


LEAFLET_STUB = """
window.__clicks = [];
(function(){ function chain(){ var o={addTo:function(){return o;},on:function(e,f){ if(e==='click') window.__mapClick=f; return o;},
  setView:function(){return o;},fitBounds:function(){return o;},remove:function(){},invalidateSize:function(){},removeLayer:function(){}}; return o; }
 window.L={map:function(){return chain();},tileLayer:chain,circle:chain,rectangle:chain,marker:chain,polyline:chain,divIcon:function(){return {};}}; })();
"""


async def wait_picker(pg):
    await pg.wait_for_function("window.__awReady === true || document.getElementById('datasetLine').textContent.length > 0")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-proxy-server"])
        ctx = await b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        await ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
        await ctx.add_init_script("localStorage.setItem('aw-lang','ru');localStorage.setItem('aw-theme','light');")
        await ctx.route(re.compile(r".*leaflet.*\.js$"), lambda route: route.fulfill(status=200, content_type="application/javascript", body=LEAFLET_STUB))
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        await pg.goto(BASE)
        await wait_picker(pg)

        # --- searchable start picker: suggestions, no duplicates, keyboard, search in any script
        await pg.click("#pickInput")
        opts = await pg.eval_on_selector_all("#pickList .pick-name", "o => o.map(x => x.textContent)")
        check("picker: suggestions shown on focus", len(opts) >= 3, str(opts))
        check("picker: no duplicate places", len(opts) == len(set(opts)), str(opts))
        check("picker: Mega Silk Way listed once", sum(1 for o in opts if "Мега" in o or "Mega" in o) == 1, str(opts))
        check("picker: listbox semantics", await pg.get_attribute("#pickInput", "aria-expanded") == "true"
              and await pg.locator("#pickList [role=option]").count() == len(opts))
        await pg.fill("#pickInput", "Байтерека")          # Russian genitive -> still found? (search uses aliases)
        await pg.wait_for_timeout(500)
        found = await pg.eval_on_selector_all("#pickList .pick-name", "o => o.map(x => x.textContent)")
        check("picker: a case ending is tolerated (Байтерека)", any("Байтерек" in f for f in found), str(found))
        await pg.fill("#pickInput", "baiterek")
        await pg.wait_for_timeout(500)
        found2 = await pg.eval_on_selector_all("#pickList .pick-name", "o => o.map(x => x.textContent)")
        check("picker: Latin spelling finds a Cyrillic-named place", any("Байтерек" in f or "Baiterek" in f for f in found2), str(found2))
        await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("ArrowUp"); await pg.keyboard.press("Enter")
        chosen = await pg.input_value("#pickInput")
        check("picker: keyboard selection", "Байтерек" in chosen, chosen)
        await pg.fill("#pickInput", "zzqx nowhere")
        await pg.wait_for_timeout(500)
        none = await pg.inner_text("#pickList")
        check("picker: honest no-match message", "нет в нашей базе" in none and "не значит" in none, none)
        await pg.keyboard.press("Escape")
        check("picker: Escape restores the chosen start", "Байтерек" in await pg.input_value("#pickInput"))
        await pg.click("[data-lang=en]")
        check("language switch updates the start name from sourced names", await pg.input_value("#pickInput") == "Baiterek",
              await pg.input_value("#pickInput"))
        await pg.click("#pickInput")
        await pg.fill("#pickInput", "atyrau")
        await pg.wait_for_timeout(500)
        txt = await pg.inner_text("#pickList")
        check("en picker: Kazakh-only name kept original with an English type (no fake English)",
              "Атырау көпірі" in txt and "Attraction" in txt and "Atyrau kopiri" not in txt, txt)
        await pg.keyboard.press("Enter")
        chips = await pg.eval_on_selector_all("#chips .chip", "o => o.map(x => x.textContent)")
        check("English: interest chips in English", chips and not any(CYR.search(c) for c in chips), str(chips))
        # map selection (Leaflet stub: checks our click handling, not tiles)
        await pg.check('input[name="mode"][value="map"]')
        await pg.wait_for_timeout(200)
        await pg.evaluate("window.__mapClick && window.__mapClick({latlng: {lat: 51.09012, lng: 71.41777}})")
        coords = await pg.input_value("#coordsInput")
        check("map pick: click fills editable coordinates", coords == "51.09012, 71.41777", coords)
        await pg.check('input[name="mode"][value="landmark"]')
        await pg.click("[data-lang=ru]")
        await pg.click("#pickInput")
        await pg.fill("#pickInput", "Mega")
        await pg.wait_for_timeout(500)
        await pg.keyboard.press("Enter")

        # --- normal request with pace + deadline + outdoor limit
        await pg.click("#more summary")
        await pg.click("[data-pace=leisurely]")
        await pg.check("#dlOn")
        from datetime import datetime, timedelta, timezone
        later = datetime.now(timezone(timedelta(hours=5))) + timedelta(minutes=90)   # works at any hour
        await pg.fill("#dlDate", later.strftime("%Y-%m-%d"))
        await pg.dispatch_event("#dlDate", "change")
        await pg.fill("#dlTime", later.strftime("%H:%M"))
        await pg.dispatch_event("#dlTime", "change")
        await pg.select_option("#odSel", "30")
        await pg.fill("#query", "Хочу погулять и выпить кофе")
        await pg.click("#submit")
        await wait_result(pg)
        recs = await pg.locator(".rec").count()
        segs = await pg.locator(".tl .visit").count()
        check("plan rendered with cards", recs >= 1, f"cards={recs}")
        check("timeline stops == cards (one canonical plan)", recs == segs, f"{recs} vs {segs}")
        nums = await pg.eval_on_selector_all(".rec .num", "o => o.map(x => x.textContent)")
        check("cards numbered in plan order", nums == [str(i + 1) for i in range(len(nums))], str(nums))
        tags = await pg.inner_text(".understood")
        check("pace shown", "Спокойный" in tags, tags)
        live = await pg.locator("#deadlineLive").count()
        check("deadline countdown shown", live == 1)
        await pg.screenshot(path=str(OUT / "01_ru_plan.png"), full_page=True)

        # --- replace keeps the others
        names_before = await pg.eval_on_selector_all(".rec h3", "o => o.map(x => x.textContent)")
        if len(names_before) >= 1:
            await pg.locator(".rec").first.get_by_role("button", name="Заменить").click()
            await wait_result(pg)
            names_after = await pg.eval_on_selector_all(".rec h3", "o => o.map(x => x.textContent)")
            body = await pg.inner_text("#output")
            if "Заменено" in body:
                check("replace: first place changed", names_before[0] not in names_after, f"{names_before} -> {names_after}")
                check("replace: others kept", all(n in names_after for n in names_before[1:]), f"{names_before} -> {names_after}")
            else:
                check("replace: honest 'no replacement' message", "Ни одно другое место" in body, body[:300])

        # --- closed / unavailable
        await pg.locator(".rec").first.get_by_role("button", name="Закрыто или недоступно").click()
        await wait_result(pg)
        body = await pg.inner_text("#output")
        check("closed: replaced or visibly marked", ("Заменено" in body) or ("отметили это место" in body), body[:200])

        # --- remove a stop
        before = await pg.locator(".rec").count()
        await pg.locator(".rec").last.get_by_role("button", name="Убрать из плана").click()
        await wait_result(pg)
        after = await pg.locator(".rec").count()
        check("remove: one card fewer", after == before - 1, f"{before}->{after}")

        # --- fresh plan with normal settings for export / bingo / surprise
        await pg.click("[data-pace=normal]")
        await pg.uncheck("#dlOn")
        await pg.select_option("#odSel", "off")
        await pg.click("#resetEx")
        await pg.fill("#query", "Хочу погулять и выпить кофе, 2 часа")
        await pg.click("#submit")
        await wait_result(pg)
        after = await pg.locator(".rec").count()
        check("fresh plan for export checks", after >= 1, f"cards={after}")

        # --- photos and descriptions (synthetic media; image hosts are offline in the sandbox)
        if after:
            about = await pg.locator(".rec .about").count()
            check("about: description shown with a source badge", about >= 1 and "Из Википедии" in await pg.inner_text(".rec .about >> nth=0"))
            check("about: HTML in descriptions is not rendered", await pg.locator(".rec .about i").count() == 0)
            figs = await pg.locator(".rec figure.photo").count()
            credit = await pg.eval_on_selector_all(".rec figure.photo figcaption", "o => o.map(x => x.textContent)")
            check("photo: figure with licence credit created", figs >= 1 and all("Wikimedia Commons" in c and "CC BY-SA" in c for c in credit), str(credit[:1]))
            await pg.wait_for_timeout(1500)
            broken = await pg.evaluate("[...document.querySelectorAll('.rec figure.photo')].filter(f => !f.hidden && f.querySelector('img').complete && f.querySelector('img').naturalWidth === 0).length")
            check("photo: an image that fails to load is hidden, not shown broken", broken == 0, str(broken))

        # --- export: copy + save
        if after:
            await pg.get_by_role("button", name="Скопировать план").click()
            await pg.wait_for_timeout(300)
            clip = await pg.evaluate("navigator.clipboard.readText()")
            check("copy: plan text in clipboard", "Astana Walks" in clip and "Старт" in clip, clip[:200])
            check("copy: no coordinates by default", not re.search(r"51\.\d{4}", clip), clip)
            async with pg.expect_download() as dl:
                await pg.get_by_role("button", name="Сохранить план (HTML)").click()
            path = await (await dl.value).path()
            html = Path(path).read_text(encoding="utf-8")
            check("save: offline HTML without scripts or external resources",
                  "<script" not in html and "unpkg" not in html and "fonts.g" not in html)
            check("save: user/model text escaped", "<b>Sphere" not in html)
            # bingo
            await pg.locator(".bingo-list input").first.check()
            prog = await pg.inner_text(".progress")
            check("bingo: progress counts self-reported completion", "Выполнено 1" in prog, prog)

        # --- surprise twice
        await pg.click("#surpriseBtn")
        await wait_result(pg)
        s1 = await pg.eval_on_selector_all(".rec h3", "o => o.map(x => x.textContent)")
        body = await pg.inner_text("#output")
        check("surprise: works without text (or says honestly that nothing fits)",
              len(s1) >= 1 or "Подходящего плана нет" in body or "нет подходящих мест" in body, body[:200])
        btn = pg.get_by_role("button", name="Ещё сюрприз")
        if await btn.count():
            await btn.click()
            await wait_result(pg)
            s2 = await pg.eval_on_selector_all(".rec h3", "o => o.map(x => x.textContent)")
            body = await pg.inner_text("#output")
            check("another surprise: different plan or honest exhaustion", set(s1) != set(s2) or "видели все сюрпризы" in body, f"{s1} {s2}")

        # --- group mode on, then back to solo
        await pg.check("#grpOn")
        rows = await pg.locator(".grp-row").count()
        check("group: two people by default", rows == 2)
        await pg.click("#grpAdd")
        check("group: add a third person", await pg.locator(".grp-row").count() == 3)
        await pg.locator(".grp-row").nth(1).get_by_role("button", name="Кофе").click()
        await pg.fill("#query", "")
        await pg.click("#submit")
        await wait_result(pg)
        body = await pg.inner_text("#output")
        check("group: coverage explained", "Как план подходит каждому" in body or "нет мест" in body.lower() or "Подходящего плана нет" in body, body[:300])
        await pg.uncheck("#grpOn")
        check("solo: group rows removed", await pg.locator(".grp-row").count() == 0)
        await pg.fill("#query", "кофе")
        await pg.click("#submit")
        await wait_result(pg)
        body = await pg.inner_text("#output")
        check("solo: no stale group coverage", "Как план подходит каждому" not in body)

        # --- past deadline is rejected, localized
        await pg.check("#dlOn")
        today = datetime.now(timezone(timedelta(hours=5)))
        await pg.fill("#dlDate", today.strftime("%Y-%m-%d"))
        await pg.dispatch_event("#dlDate", "change")
        await pg.fill("#dlTime", "00:01")
        await pg.dispatch_event("#dlTime", "change")
        await pg.click("#submit")
        await wait_result(pg)
        body = await pg.inner_text("#output")
        check("past deadline: clear localized error", "уже прошло" in body or "в пределах ближайших" in body, body[:200])
        await pg.uncheck("#dlOn")


        # --- v5: start conflict -> one clarification with selectable answers
        await pg.click("#pickInput"); await pg.fill("#pickInput", "Mega"); await pg.wait_for_timeout(400); await pg.keyboard.press("Enter")
        await pg.fill("#query", "кофе рядом с Байтереком")
        await pg.click("#submit")
        await wait_result(pg)
        body = await pg.inner_text("#output")
        check("clarify: conflicting start is asked about, not silently used", "Откуда вы начинаете" in body and "Байтерек" in body, body[:300])
        await pg.get_by_role("button", name=re.compile("^Оставить")).click()
        await wait_result(pg)
        check("clarify: 'keep' plans from the selected start", await pg.locator(".rec").count() >= 1 or "Подходящего плана нет" in await pg.inner_text("#output"))

        # --- v5: plan styles, directions, active walk, reports (start at a cafe with 90 min)
        await pg.click("#pickInput"); await pg.fill("#pickInput", "Кофе Бум"); await pg.wait_for_timeout(400); await pg.keyboard.press("Enter")
        start_name = await pg.input_value("#pickInput")
        await pg.fill("#query", "погулять и выпить кофе, 90 минут")
        await pg.click("#submit")
        await wait_result(pg)
        gl = await pg.eval_on_selector_all(".rec .dir-row a", "o => o.map(a => a.href)")
        check("directions: per-stop Google Maps walking link", any("travelmode=walking" in h and "api=1" in h for h in gl), str(gl[:2]))
        whole = await pg.eval_on_selector_all(".route a.link", "o => o.map(a => a.href)")
        check("directions: whole route link with waypoints when there are 2+ stops",
              whole and ("waypoints=" in whole[0] or await pg.locator(".rec").count() < 2), str(whole))
        check("directions: opened only by a click (no auto-open)", "google.com" not in pg.url)
        if await pg.locator(".styles").count():
            cards = await pg.locator(".style-card").count()
            check("styles: alternatives shown with comparable numbers", cards >= 2 and "пешком" in await pg.inner_text(".styles"))
            await pg.locator(".style-card button").first.click()
            await wait_result(pg)
            body = await pg.inner_text("#output")
            check("styles: switching keeps one canonical plan", "План изменён" in body and
                  await pg.locator(".rec").count() == await pg.locator(".tl .visit").count(), body[:200])
        else:
            check("styles: none shown when only one plan fits (allowed)", True)
        n_before = await pg.locator(".rec").count()
        await pg.get_by_role("button", name="Начать прогулку", exact=True).click()
        check("walk: panel shown with self-reported note", "в фоне ничего не отслеживается" in await pg.inner_text(".panel.walk"))
        await pg.locator(".rec").first.get_by_role("button", name="Я здесь / готово").click()
        await pg.get_by_role("button", name="Пересчитать оставшуюся прогулку").click()
        await wait_result(pg)
        body = await pg.inner_text("#output")
        if n_before >= 2:
            route = await pg.inner_text(".route ol")
            last = route.strip().splitlines()[-1]
            check("walk: remaining walk recalculated", "пересчитана" in body and await pg.locator(".rec").count() == n_before - 1, body[:300])
            check("walk: the way back still ends at the ORIGINAL start", start_name in last.split("→")[-1], last)
        else:
            check("walk: single-stop plan -> all done message", "Все места отмечены" in body, body[:200])
        await pg.get_by_role("button", name="Завершить прогулку").click()

        # report a problem: local only, downloadable, no coordinates
        await pg.locator(".rec").first.get_by_role("button", name="Сообщить об ошибке").click()
        await pg.select_option("#rpField", "name")
        await pg.fill("#rpValue", "Правильное название")
        await pg.fill("#rpReason", "Вывеска на месте")
        await pg.click(".report button[type=submit]")
        check("report: saved locally and counted", "Мои сообщения: 1" in await pg.inner_text("#output"))
        async with pg.expect_download() as dl:
            await pg.get_by_role("button", name="Скачать сообщения (JSON)").click()
        rep = Path(await (await dl.value).path()).read_text(encoding="utf-8")
        check("report: JSON has the POI ID and no coordinates or query", '"poi_id"' in rep and '"lat"' not in rep and "погулять" not in rep, rep[:200])
        await pg.get_by_role("button", name="Удалить все сообщения").click()
        check("report: deleted", "Мои сообщения" not in await pg.inner_text("#output"))

        # language switch: cards, route and export agree, no new model call
        await pg.click("[data-lang=en]")
        heads = await pg.eval_on_selector_all(".rec h3", "o => o.map(x => x.textContent.replace(/^\\d+\\.\\s*/, ''))")
        route = await pg.inner_text(".route ol")
        await pg.get_by_role("button", name="Copy plan").click()
        await pg.wait_for_timeout(300)
        clip = await pg.evaluate("navigator.clipboard.readText()")
        check("language switch: card, route and export names agree", all(h in route and h in clip for h in heads), f"{heads} | {route[:120]} | {clip[:120]}")
        check("language switch: offers to regenerate the AI text", await pg.get_by_role("button", name=re.compile("Write the AI text in English")).count() == 1)
        await pg.click("[data-lang=ru]")

        # empty result: explicit one-click changes with a preview
        await pg.fill("#query", "музей, 5 минут")
        await pg.click("#submit")
        await wait_result(pg)
        body = await pg.inner_text("#output")
        btn = pg.get_by_role("button", name=re.compile("Добавить 15 мин"))
        check("no plan: reasons and one-click changes shown", "Измените что-то одно" in body and await btn.count() == 1, body[:300])


        # --- model failure: actionable recovery and a LABELLED plan without AI (real server for the fallback)
        async def fail_once(route):
            resp = await route.fetch()
            data = await resp.json()
            data["error"] = {"code": "timeout", "detail": "simulated in the browser check", "params": {"seconds": 120}}
            data["plan"] = None
            data["recommendations"] = []
            await route.fulfill(response=resp, json=data)
        await pg.route("**/api/recommend", fail_once)
        await pg.fill("#query", "погулять и выпить кофе")
        await pg.click("#submit")
        await wait_result(pg)
        await pg.unroute("**/api/recommend")
        body = await pg.inner_text("#output")
        check("model failure: actionable message + retry + labelled no-AI option + search-only list",
              "не ответила" in body and "Спросить модель ещё раз" in body and "План без текста ИИ" in body
              and await pg.locator(".fallback").count() == 1, body[:400])
        await pg.get_by_role("button", name=re.compile("План без текста ИИ")).click()
        await wait_result(pg)
        body = await pg.inner_text("#output")
        check("app choice: plan shown and clearly labelled as chosen without AI",
              await pg.locator(".rec").count() >= 1 and "БЕЗ модели ИИ" in body and await pg.locator(".rec .pill.ai").count() == 0, body[:300])

        # --- cancel a running request: no stale answer appears afterwards
        await pg.fill("#query", "кофе")
        await pg.click("#submit")
        await pg.click("#cancelBtn")
        await pg.wait_for_timeout(900)
        body = await pg.inner_text("#output")
        check("cancel: request cancelled and the late answer ignored", "Запрос отменён" in body, body[:200])


        # --- v6: discover — place of the day, Astana in photos, guess the place
        await pg.goto(BASE)
        await wait_picker(pg)
        await pg.wait_for_selector(".day", timeout=10000)
        day = await pg.inner_text(".day")
        check("discover: place of the day with a licence credit and an honest 'not a ranking' note",
              "место дня" in day.lower() and "Wikimedia Commons" in day and "не рейтинг" in day, day[:200])
        tiles = await pg.locator(".tile").count()
        check("gallery: tiles for places with a photo", tiles >= 3, str(tiles))
        await pg.locator(".tile").first.click()
        check("gallery: dialog opens with name, type and credit", await pg.locator("[role=dialog]").count() == 1
              and "Wikimedia Commons" in await pg.inner_text("[role=dialog]"))
        await pg.keyboard.press("Escape")
        check("gallery: Escape closes the dialog", await pg.locator("[role=dialog]").count() == 0)
        await pg.get_by_role("button", name="Угадай место").click()
        hidden = await pg.eval_on_selector_all(".tile .tile-name", "o => o.map(x => x.textContent)")
        check("guess: names hidden in guess mode", all(h == "Что это за место?" for h in hidden), str(hidden[:3]))
        await pg.locator(".tile").first.click()
        opts = await pg.locator(".guess-opts button").count()
        check("guess: three real options", opts == 3, str(opts))
        await pg.locator(".guess-opts button").first.click()
        verdict = await pg.inner_text(".verdict")
        check("guess: verdict in words (not colour only) and score updated",
              ("Верно" in verdict or "Не совсем" in verdict) and "Счёт:" in await pg.inner_text(".score"), verdict)
        await pg.locator("[role=dialog]").get_by_role("button", name="Начать прогулку отсюда").click()
        start_val = await pg.input_value("#pickInput")
        check("gallery: 'Start my walk here' sets the start", len(start_val) > 0 and await pg.locator("[role=dialog]").count() == 0, start_val)
        await pg.get_by_role("button", name="Смотреть", exact=True).click()

        # --- other languages / themes / modes / phone
        for lang, theme, vision, w, name in (("kk", "dark", "off", 1280, "02_kk_dark"), ("en", "light", "on", 1280, "03_en_vision"),
                                             ("ru", "light", "off", 390, "04_ru_phone")):
            c2 = await b.new_context(viewport={"width": w, "height": 900})
            await c2.add_init_script(f"localStorage.setItem('aw-lang','{lang}');localStorage.setItem('aw-theme','{theme}');localStorage.setItem('aw-vision','{vision}');")
            p2 = await c2.new_page()
            errs2 = []
            p2.on("pageerror", lambda e: errs2.append(str(e)))
            await c2.route(re.compile(r".*leaflet.*\.js$"), lambda route: route.fulfill(status=200, content_type="application/javascript", body=LEAFLET_STUB))
            await p2.goto(BASE)
            await wait_picker(p2)
            await p2.locator("#examples .example").first.click()
            await p2.click("#submit")
            await wait_result(p2)
            text = await p2.inner_text("body")
            raw_keys = re.findall(r"\b(?:bg|ex|plan|act|adj|calc|outdoor|deadline|group|pace|bingo)_[a-z_]+\b", text)
            check(f"{name}: no raw translation keys", not raw_keys, str(raw_keys[:5]))
            if lang == "en":
                notes = await p2.eval_on_selector_all(".rec", "o => o.map(c => [c.querySelector('h3').textContent, (c.querySelector('.name-note')||{}).textContent || ''])")
                ok = all((not CYR.search(h)) or ("Original name" in n and "Type:" in n) for h, n in notes)
                check("en: every Cyrillic card name is labelled as the original name with an English type", ok, str(notes))
            sw = await p2.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            check(f"{name}: no horizontal scroll", sw)
            check(f"{name}: no JS errors", not errs2, str(errs2))
            await p2.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            await c2.close()

        check("no JavaScript errors in main session", not errors, str(errors[:5]))
        await b.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} browser checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
