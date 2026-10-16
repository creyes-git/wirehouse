"""The warehouse viewer in a real (headless) browser.

Optional: skipped unless Playwright and a Chromium-family browser are available
(`pip install -e ".[browser]"` then `python -m playwright install chromium`, or an
installed Chrome). Covers what the Python tests cannot: traces, routes, links into a
view, tours and quests, the schema diagram and exports, with no console errors.
"""

from __future__ import annotations

import json
import textwrap

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from test_wirehouse import FILES  # noqa: E402

from wirehouse import guide  # noqa: E402
from wirehouse.build import build_archmap  # noqa: E402
from wirehouse.render.html import write_html  # noqa: E402

MIGRATION = """
    CREATE TABLE customers (id SERIAL PRIMARY KEY, email VARCHAR(255) NOT NULL);
    CREATE TABLE invoices (id SERIAL PRIMARY KEY, customer_id INT NOT NULL REFERENCES customers(id));
"""
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    root = tmp_path_factory.mktemp("viewer-shop")
    for rel, body in dict(FILES, **{"api/migrations/001_init.sql": MIGRATION}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    data = guide.apply(build_archmap(root, log=lambda *_: None), {})
    return write_html(data, root / "wirehouse.html")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        b = None
        for kw in ({"channel": "chrome"}, {"channel": "msedge"}, {}):
            try:
                b = pw.chromium.launch(headless=True, args=ARGS, **kw)
                break
            except Exception:  # noqa: BLE001 - try the next browser
                continue
        if b is None:
            pytest.skip("no Chromium-family browser available")
        yield b
        b.close()


def open_view(browser, html, hash_="#nowelcome"):
    page = browser.new_page(viewport={"width": 1280, "height": 800}, accept_downloads=True)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(html.as_uri() + hash_)
    page.wait_for_function("window.__wirehouse && __wirehouse.state().items > 0")
    return page, errors


def js(page, expr):
    return page.evaluate(expr)


def test_loads_cleanly_and_keys_do_not_hijack_controls(browser, html):
    page, errors = open_view(browser, html)
    assert js(page, "__wirehouse.state().room") == ""
    page.focus("#helpBtn")
    page.keyboard.press("Space")          # activates the focused button instead of jumping
    assert js(page, "!document.querySelector('#welcome').hidden")
    page.keyboard.press("Escape")
    page.keyboard.press("p")
    assert js(page, "location.hash") == "#plan=1"
    assert errors == []


def test_trace_follows_recorded_connections_at_file_precision(browser, html):
    page, errors = open_view(browser, html)
    down = json.loads(js(page, "__wirehouse.startTrace('down', 'unit:js:web'); JSON.stringify(__wirehouse.trace().marks)"))
    assert down == {"unit:js:web": 0, "unit:python:api": 1, "res:clerk": 1, "res:stripe": 1, "res:postgres": 2, "res:redis": 2}
    only = json.loads(js(page, "__wirehouse.startTrace('down', 'file:web/lib/payments.ts'); JSON.stringify(__wirehouse.trace().marks)"))
    assert set(only) == {"unit:js:web", "res:stripe"}
    up = json.loads(js(page, "__wirehouse.startTrace('up', 'file:api/db.py'); JSON.stringify(__wirehouse.trace().marks)"))
    assert up["unit:js:web"] == 1 and up["actor:users"] == 2
    assert "trace=up~file%3Aapi%2Fdb.py" in js(page, "location.hash")
    route = js(page, "__wirehouse.startRoute('actor:users', 'res:postgres'); __wirehouse.trace()")
    assert route["stops"] == ["actor:users", "unit:js:web", "unit:python:api", "res:postgres"] and not route["loose"]
    assert "file:web/lib/api.ts" in route["path"] and "file:api/db.py" in route["path"]
    # compose depends_on (start-up order) is not traffic: CI/CD and the db container are not on the way
    deps = js(page, "__wirehouse.startTrace('down', 'infra:ci'); Object.keys(__wirehouse.trace().marks)")
    assert deps == ["infra:ci"]
    page.keyboard.press("Escape")
    assert js(page, "__wirehouse.trace()") is None
    assert errors == []


def test_links_restore_the_view(browser, html):
    page, errors = open_view(browser, html, "#room=unit%3Apython%3Aapi&focus=file%3Aapi%2Fdb.py&trace=up~res%3Apostgres")
    st = js(page, "__wirehouse.state()")
    assert st["room"] == "unit:python:api" and st["selected"]["id"] == "file:api/db.py"
    assert js(page, "__wirehouse.trace().id") == "res:postgres"
    page.evaluate("location.hash = '#route=actor%3Ausers~res%3Apostgres&stop=2'")
    page.wait_for_function("__wirehouse.player() && __wirehouse.player().i === 1")
    assert js(page, "__wirehouse.player().kind") == "route"
    assert errors == []


def test_quests_tick_off_and_tours_play(browser, html):
    page, errors = open_view(browser, html)
    js(page, "localStorage.clear()")
    js(page, "__wirehouse.startTour('main-floor', 0, false)")
    assert js(page, "__wirehouse.player().stops[0]") == "actor:users"
    assert "tour=main-floor&stop=1" in js(page, "location.hash")
    page.keyboard.press("Escape")
    js(page, "__wirehouse.focusNode('file:api/routers/orders.py')")
    page.wait_for_function("__wirehouse.progress().found.includes('find-endpoint')")
    assert "1/" in page.inner_text("#clipBtn")
    assert errors == []


def test_schema_diagram_and_share_card(browser, html):
    page, errors = open_view(browser, html)
    js(page, "__wirehouse.openErd('res:postgres')")
    assert js(page, "document.querySelectorAll('.erd-link').length") == 1
    page.keyboard.press("Escape")
    assert js(page, "document.querySelector('#erd').hidden")
    js(page, "__wirehouse.startRoute('actor:users', 'res:postgres')")
    card = page.evaluate("__wirehouse.shareCard()")
    assert (card["w"], card["h"]) == (1200, 630) and card["name"].endswith("route-users-to-postgresql.png")
    page.click("#exportBtn")
    with page.expect_download() as dl:
        page.click("#exportMenu [data-x=png]")
    assert dl.value.suggested_filename == "shop-warehouse.png" or dl.value.suggested_filename.endswith("-warehouse.png")
    assert errors == []
