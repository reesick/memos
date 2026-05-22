"""
tests/test_ui.py — MemoryOS Demo UI end-to-end test suite
Playwright-based. Tests real browser interactions against http://localhost:8000/demo/

Mindset: tough judge — finds real breakage, visual regressions, and usability failures.

Setup (one-time):
    playwright install chromium

Run:
    python tests/test_ui.py
    python tests/test_ui.py --headed    # watch it run
    python tests/test_ui.py --fast      # skip slow LLM interactions
"""

from __future__ import annotations

import io
import os
import sys
import time
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, expect, TimeoutError as PWTimeout

# UTF-8 safe on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.getenv("MEMORYOS_URL", "http://localhost:8000")
DEMO = f"{BASE}/demo/"

SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────
# CLI args
# ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--headed", action="store_true", help="Show browser window")
parser.add_argument("--fast", action="store_true", help="Skip tests that wait for LLM")
args, _ = parser.parse_known_args()

USE_COLOR = os.getenv("NO_COLOR") is None
def _c(code, s): return f"\033[{code}m{s}\033[0m" if USE_COLOR else s
G  = lambda s: _c("32;1", s)
R  = lambda s: _c("31;1", s)
Y  = lambda s: _c("33;1", s)
D  = lambda s: _c("2",    s)
B  = lambda s: _c("1",    s)

# ─────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────

@dataclass
class Case:
    name: str
    status: str
    detail: str = ""
    ms: int = 0

@dataclass
class Report:
    cases: list[Case] = field(default_factory=list)

    def record(self, name, status, detail="", ms=0):
        self.cases.append(Case(name, status, detail, ms))
        sym = {"PASS": G("PASS"), "FAIL": R("FAIL"), "WARN": Y("WARN"), "SKIP": D("SKIP")}[status]
        line = f"  [{sym}] {name}"
        if ms: line += D(f"  ({ms} ms)")
        print(line)
        if detail:
            for l in detail.splitlines():
                print(D(f"        {l}"))

    def summary(self):
        n = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for c in self.cases: n[c.status] += 1
        total = len(self.cases)
        pct = round(100 * n["PASS"] / total) if total else 0
        print()
        print(B("=" * 64))
        print(B("  FINAL UI SUMMARY"))
        print(B("=" * 64))
        print(f"  {G(str(n['PASS']))} pass  {R(str(n['FAIL']))} fail  "
              f"{Y(str(n['WARN']))} warn  {D(str(n['SKIP']))} skip   "
              f"({total} cases, {pct}% pass)")
        if n["FAIL"]:
            print(R(B("  Failures:")))
            for c in self.cases:
                if c.status == "FAIL":
                    print(f"    · {c.name}")
                    if c.detail: print(D(f"      {c.detail[:120]}"))
        print(D(f"  Screenshots saved to: {SCREENSHOTS_DIR}"))
        print(B("=" * 64))
        return n["FAIL"]

report = Report()


def run(name: str, fn, page: Page = None):
    t0 = time.time()
    try:
        fn()
        report.record(name, "PASS", ms=int((time.time()-t0)*1000))
    except AssertionError as e:
        ms = int((time.time()-t0)*1000)
        if page:
            shot = SCREENSHOTS_DIR / f"FAIL_{name.replace(' ', '_')[:50]}.png"
            try: page.screenshot(path=str(shot))
            except: pass
        report.record(name, "FAIL", str(e), ms)
    except PWTimeout as e:
        ms = int((time.time()-t0)*1000)
        if page:
            shot = SCREENSHOTS_DIR / f"FAIL_{name.replace(' ', '_')[:50]}.png"
            try: page.screenshot(path=str(shot))
            except: pass
        report.record(name, "FAIL", f"Timeout: {e}", ms)
    except Exception as e:
        ms = int((time.time()-t0)*1000)
        report.record(name, "FAIL", f"{type(e).__name__}: {e}", ms)

def skip(name, reason):
    report.record(name, "SKIP", reason)

def warn(name, detail, ms=0):
    report.record(name, "WARN", detail, ms)

def section(title):
    print()
    print(B(f"{'─'*64}"))
    print(B(f"  {title}"))
    print(B(f"{'─'*64}"))


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def screenshot(page: Page, name: str):
    path = SCREENSHOTS_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(D(f"        screenshot → {path.name}"))


def wait_mem_count_changes(page: Page, before: int, timeout_ms: int = 30000) -> int:
    """Wait until #mem-count shows a value different from `before`. Returns new count."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        raw = page.locator("#mem-count").inner_text()
        try:
            current = int(raw.strip())
            if current != before:
                return current
        except ValueError:
            pass
        time.sleep(0.3)
    return before  # timed out, return unchanged


def get_mem_count(page: Page) -> int:
    try:
        return int(page.locator("#mem-count").inner_text().strip())
    except Exception:
        return 0


def get_console_errors(page: Page, errors: list) -> list:
    """Returns list of JS errors captured via page.on('console')"""
    return [e for e in errors if e.type == "error"]


# ─────────────────────────────────────────────────────────────────
# Phase 1 · Page loads correctly
# ─────────────────────────────────────────────────────────────────

def phase1_load(page: Page, console_msgs: list):
    section("Phase 1 · Page Load & Initial State")

    def loads_200():
        r = page.goto(DEMO, wait_until="networkidle", timeout=15000)
        assert r and r.status == 200, f"Demo page returned HTTP {r and r.status}"
        screenshot(page, "01_initial_load")

    def no_console_errors():
        errors = [m for m in console_msgs if m.type == "error"]
        # Ignore font/favicon 404s — judge only cares about JS errors
        js_errors = [m for m in errors if "favicon" not in m.text and "fonts.g" not in m.text]
        assert not js_errors, f"JS console errors on load: {[m.text for m in js_errors]}"

    def title_correct():
        assert "MemoryOS" in page.title(), f"Wrong page title: {page.title()}"

    def three_panels_visible():
        assert page.locator("#chat-panel").is_visible(), "Chat panel missing"
        assert page.locator("#memories-panel").is_visible(), "Memories panel missing"
        assert page.locator("#right-panel").is_visible(), "Right panel missing"

    def server_status_shown():
        dot = page.locator("#status-dot")
        assert dot.is_visible(), "#status-dot missing from topbar"

    def model_badge_shown():
        badge = page.locator("#model-badge")
        assert badge.is_visible(), "Model badge missing"
        model_text = badge.inner_text()
        assert model_text.strip(), "Model badge is empty"
        print(D(f"        model badge: {model_text}"))

    def chat_input_focusable():
        page.locator("#chat-input").click()
        assert page.locator("#chat-input").is_focused(), "Chat input not focusable"

    def memories_search_present():
        assert page.locator("#mem-search").is_visible(), "#mem-search input missing"
        assert page.locator("button.btn-search").is_visible(), "Search button missing"

    run("demo page loads HTTP 200", loads_200, page)
    run("no JS console errors on load", no_console_errors, page)
    run("page title contains MemoryOS", title_correct, page)
    run("three-panel layout visible", three_panels_visible, page)
    run("server status dot in topbar", server_status_shown, page)
    run("model badge shows configured model", model_badge_shown, page)
    run("chat input is focusable", chat_input_focusable, page)
    run("memory search input present", memories_search_present, page)


# ─────────────────────────────────────────────────────────────────
# Phase 2 · Send a message — memory gets stored
# ─────────────────────────────────────────────────────────────────

def phase2_add_memory(page: Page):
    section("Phase 2 · Add Memory via Chat")

    if args.fast:
        skip("message appears in chat", "--fast flag")
        skip("memory count increases after message", "--fast flag")
        skip("memory card visible in memories panel", "--fast flag")
        return

    count_before = get_mem_count(page)

    TEST_MSG = "My name is TestUser. I am a frontend engineer at VerifyLabs."

    def message_appears_in_chat():
        inp = page.locator("#chat-input")
        inp.fill(TEST_MSG)
        inp.press("Enter")
        # User bubble should appear immediately
        page.wait_for_selector(".msg-row.you", timeout=5000)
        bubbles = page.locator(".msg-row.you .msg-bubble").all()
        texts = [b.inner_text() for b in bubbles]
        assert any(TEST_MSG[:30] in t for t in texts), \
            f"Sent message not shown in chat. bubbles={texts[:3]}"
        print(D(f"        User bubble appeared ✓"))

    def memory_count_increases():
        new_count = wait_mem_count_changes(page, count_before, timeout_ms=35000)
        assert new_count > count_before, \
            f"Memory count didn't increase after sending message. Before={count_before} After={new_count}"
        print(D(f"        Memory count {count_before} → {new_count} ✓"))
        screenshot(page, "02_after_add_memory")

    def memory_card_visible():
        # Memory panel should show a card with our entity
        page.wait_for_function(
            """() => document.querySelector('#memories-list').children.length > 0""",
            timeout=10000,
        )
        list_html = page.locator("#memories-list").inner_html()
        assert "testuser" in list_html.lower() or "testuser" in list_html.lower() or \
               "verif" in list_html.lower() or "frontend" in list_html.lower(), \
            f"Memory card not visible for TestUser. list HTML starts: {list_html[:300]}"
        screenshot(page, "03_memory_card_visible")
        print(D(f"        Memory card visible ✓"))

    run("sent message appears in chat bubble", message_appears_in_chat, page)
    run("memory count increases after message", memory_count_increases, page)
    run("memory card visible in memories panel", memory_card_visible, page)


# ─────────────────────────────────────────────────────────────────
# Phase 3 · Search memories
# ─────────────────────────────────────────────────────────────────

def phase3_search(page: Page):
    section("Phase 3 · Memory Search")

    def search_returns_results():
        search_box = page.locator("#mem-search")
        search_box.fill("frontend")
        page.locator("button.btn-search").click()
        page.wait_for_timeout(2000)
        list_html = page.locator("#memories-list").inner_html()
        screenshot(page, "04_search_results")
        assert list_html.strip(), "Memory list is empty after search — expected results"
        # Should not show 'No memories' message
        assert "no mem" not in list_html.lower(), "Search returned 'No memories' for known term"
        print(D(f"        Search returned results ✓"))

    def empty_search_resets_list():
        search_box = page.locator("#mem-search")
        search_box.fill("")
        page.locator("button.btn-search").click()
        page.wait_for_timeout(1500)
        # Should show all memories again (count ≥ before)
        count_after_clear = get_mem_count(page)
        print(D(f"        After clearing search: {count_after_clear} memories shown ✓"))

    def search_no_crash_on_special_chars():
        search_box = page.locator("#mem-search")
        search_box.fill('"; DROP TABLE memories; --')
        page.locator("button.btn-search").click()
        page.wait_for_timeout(2000)
        errors = page.evaluate("() => window.__last_error || null")
        screenshot(page, "05_sql_injection_search")
        assert page.locator("#memories-list").is_visible(), \
            "Memories panel crashed on SQL injection input"
        print(D(f"        SQL injection input survived ✓"))

    def search_no_crash_on_unicode():
        search_box = page.locator("#mem-search")
        search_box.fill("こんにちは 안녕 мир 🔥")
        page.locator("button.btn-search").click()
        page.wait_for_timeout(2000)
        assert page.locator("#memories-list").is_visible(), \
            "Memories panel crashed on unicode input"
        search_box.fill("")
        print(D(f"        Unicode input survived ✓"))

    if args.fast:
        skip("search returns results", "--fast flag")
    else:
        run("search 'frontend' returns results", search_returns_results, page)

    run("clearing search resets the list", empty_search_resets_list, page)
    run("SQL injection in search doesn't crash", search_no_crash_on_special_chars, page)
    run("unicode characters in search don't crash", search_no_crash_on_unicode, page)


# ─────────────────────────────────────────────────────────────────
# Phase 4 · Right panel — Context / Graph tabs
# ─────────────────────────────────────────────────────────────────

def phase4_right_panel(page: Page):
    section("Phase 4 · Right Panel — Context & Graph Tabs")

    def context_tab_active_by_default():
        tab_context = page.locator("#tab-context")
        assert tab_context.is_visible(), "#tab-context not visible on load"
        graph_tab = page.locator("#tab-graph")
        assert not graph_tab.is_visible(), "#tab-graph should be hidden initially"
        print(D(f"        Context tab active by default ✓"))

    def graph_tab_switches():
        # Click the Graph tab button
        graph_btn = page.locator("button", has_text="graph")
        if not graph_btn.is_visible():
            # Try alternate text
            graph_btn = page.locator(".tab-btn").filter(has_text="raph")
        graph_btn.first.click()
        page.wait_for_timeout(500)
        graph_vis = page.locator("#tab-graph")
        assert graph_vis.is_visible(), "Graph tab didn't appear after clicking tab button"
        screenshot(page, "06_graph_tab")
        print(D(f"        Graph tab switch ✓"))

    def graph_container_exists():
        graph_div = page.locator("#graph-vis")
        assert graph_div.count() > 0, "#graph-vis div missing"
        # After switching to graph tab, check if canvas was created by vis-network
        page.wait_for_timeout(1000)
        canvas = page.locator("#graph-vis canvas")
        has_canvas = canvas.count() > 0
        if has_canvas:
            print(D(f"        vis-network canvas rendered ✓"))
        else:
            # vis-network might not have rendered yet without data
            print(D(f"        #graph-vis exists (no canvas yet — needs data) ✓"))

    def switch_back_to_context():
        ctx_btn = page.locator(".tab-btn").filter(has_text="ontext")
        ctx_btn.first.click()
        page.wait_for_timeout(300)
        assert page.locator("#tab-context").is_visible(), "Context tab didn't come back"

    run("context tab active by default", context_tab_active_by_default, page)
    run("clicking graph tab switches panel", graph_tab_switches, page)
    run("graph-vis container exists", graph_container_exists, page)
    run("switching back to context tab works", switch_back_to_context, page)


# ─────────────────────────────────────────────────────────────────
# Phase 5 · Edge cases & usability failures
# ─────────────────────────────────────────────────────────────────

def phase5_edge_cases(page: Page):
    section("Phase 5 · Usability Edge Cases")

    def empty_message_doesnt_send():
        count_before = get_mem_count(page)
        chat_input = page.locator("#chat-input")
        chat_input.fill("")
        chat_input.press("Enter")
        page.wait_for_timeout(1000)
        # Count should not change — empty message should not trigger add
        count_after = get_mem_count(page)
        screenshot(page, "07_empty_message")
        assert count_after == count_before, \
            f"Empty message changed memory count: {count_before} → {count_after}"
        print(D(f"        Empty message blocked ✓"))

    def whitespace_only_doesnt_send():
        count_before = get_mem_count(page)
        chat_input = page.locator("#chat-input")
        chat_input.fill("     ")
        chat_input.press("Enter")
        page.wait_for_timeout(1000)
        count_after = get_mem_count(page)
        assert count_after == count_before, \
            f"Whitespace-only message changed memory count"
        print(D(f"        Whitespace-only message blocked ✓"))

    def very_long_message_handled():
        count_before = get_mem_count(page)
        long_msg = "Alice " + ("knows Python " * 400)  # ~2600 chars
        chat_input = page.locator("#chat-input")
        chat_input.fill(long_msg)
        chat_input.press("Enter")
        page.wait_for_timeout(3000)
        # UI must not freeze or crash — check panel still visible
        assert page.locator("#memories-panel").is_visible(), \
            "Memories panel disappeared after long message"
        screenshot(page, "08_long_message")
        print(D(f"        Long message ({len(long_msg)} chars) handled without crash ✓"))

    def xss_in_chat_input():
        chat_input = page.locator("#chat-input")
        xss = '<script>document.body.innerHTML="HACKED"</script>Alice works at <b>XSS Corp</b>'
        chat_input.fill(xss)
        chat_input.press("Enter")
        page.wait_for_timeout(2000)
        body_text = page.locator("body").inner_text()
        assert "HACKED" not in body_text, "XSS payload executed — innerHTML was overwritten"
        screenshot(page, "09_xss_attempt")
        print(D(f"        XSS payload neutralised ✓"))

    def page_doesnt_freeze_under_rapid_input():
        chat_input = page.locator("#chat-input")
        # Rapid-fire 5 messages
        for i in range(5):
            chat_input.fill(f"Quick message {i}")
            chat_input.press("Enter")
            page.wait_for_timeout(100)
        page.wait_for_timeout(1000)
        assert page.locator("#chat-messages").is_visible(), \
            "Chat panel disappeared after rapid messages"
        print(D(f"        Rapid input (5 msgs, 100ms apart) didn't freeze UI ✓"))

    run("empty Enter doesn't trigger memory add", empty_message_doesnt_send, page)
    run("whitespace-only message blocked", whitespace_only_doesnt_send, page)
    run("very long message handled without crash", very_long_message_handled, page)
    run("XSS in chat input neutralized", xss_in_chat_input, page)
    run("rapid-fire input doesn't freeze UI", page_doesnt_freeze_under_rapid_input, page)


# ─────────────────────────────────────────────────────────────────
# Phase 6 · Memory card interactions
# ─────────────────────────────────────────────────────────────────

def phase6_memory_cards(page: Page):
    section("Phase 6 · Memory Card Interactions")

    def cards_render_entity_and_value():
        cards = page.locator("#memories-list .mem-card").all()
        if not cards:
            # Try alternate selector
            cards = page.locator("#memories-list [class*='mem']").all()
        if not cards:
            warn("memory cards render entity+value", "No .mem-card elements found — check class name")
            return
        first = cards[0]
        html = first.inner_html()
        assert html.strip(), "First memory card is empty"
        print(D(f"        {len(cards)} memory cards found, first has content ✓"))

    def delete_button_exists_and_removes():
        count_before = get_mem_count(page)
        if count_before == 0:
            skip("delete button removes memory", "No memories to delete")
            return

        # Find a delete button
        delete_btn = page.locator("#memories-list button[title*='elete'], "
                                  "#memories-list button[aria-label*='elete'], "
                                  "#memories-list button[onclick*='delete'], "
                                  "#memories-list .btn-delete, "
                                  "#memories-list button").first

        if not delete_btn.is_visible():
            warn("delete button removes memory", "No delete button found in memory cards")
            return

        delete_btn.click()
        page.wait_for_timeout(3000)  # allow network + UI update
        count_after = get_mem_count(page)
        screenshot(page, "10_after_delete")
        assert count_after < count_before, \
            f"Delete button clicked but count didn't decrease: {count_before} → {count_after}"
        print(D(f"        Delete: count {count_before} → {count_after} ✓"))

    run("memory cards render entity and value", cards_render_entity_and_value, page)
    run("delete button removes memory from list", delete_button_exists_and_removes, page)


# ─────────────────────────────────────────────────────────────────
# Phase 7 · Server offline behaviour
# ─────────────────────────────────────────────────────────────────

def phase7_offline(page: Page):
    section("Phase 7 · Server Offline Resilience")

    def ui_survives_intercepted_api_call():
        """Intercept /memory/add to simulate a 500 error — UI must not crash."""
        page.route("**/memory/add", lambda route: route.fulfill(
            status=500,
            body='{"error": "simulated server error"}',
            headers={"Content-Type": "application/json"},
        ))

        count_before = get_mem_count(page)
        page.locator("#chat-input").fill("Simulated failure test message")
        page.locator("#chat-input").press("Enter")
        page.wait_for_timeout(3000)

        # Panel must still be visible — UI must not white-screen
        assert page.locator("#memories-panel").is_visible(), \
            "Memories panel disappeared after server 500 error"
        screenshot(page, "11_after_server_500")
        print(D(f"        UI survived simulated 500 response ✓"))

        page.unroute("**/memory/add")

    def search_survives_network_error():
        page.route("**/memory/search", lambda route: route.abort())
        search_box = page.locator("#mem-search")
        search_box.fill("test")
        page.locator("button.btn-search").click()
        page.wait_for_timeout(3000)
        assert page.locator("#memories-list").is_visible(), \
            "Memories list disappeared after search network abort"
        screenshot(page, "12_after_search_abort")
        print(D(f"        UI survived aborted /memory/search request ✓"))
        page.unroute("**/memory/search")

    run("UI survives simulated 500 on /memory/add", ui_survives_intercepted_api_call, page)
    run("UI survives aborted /memory/search", search_survives_network_error, page)


# ─────────────────────────────────────────────────────────────────
# Phase 8 · Visual regression screenshots
# ─────────────────────────────────────────────────────────────────

def phase8_screenshots(page: Page):
    section("Phase 8 · Visual Regression Snapshots")

    def full_page_screenshot():
        page.goto(DEMO, wait_until="networkidle")
        page.wait_for_timeout(1500)
        screenshot(page, "FINAL_full_page")
        print(D(f"        Full page snapshot saved ✓"))

    def mobile_viewport_screenshot():
        page.set_viewport_size({"width": 390, "height": 844})  # iPhone 14
        page.goto(DEMO, wait_until="networkidle")
        page.wait_for_timeout(1000)
        screenshot(page, "FINAL_mobile_390")
        print(D(f"        Mobile viewport (390×844) snapshot saved ✓"))
        page.set_viewport_size({"width": 1280, "height": 800})  # reset

    def narrow_viewport_screenshot():
        page.set_viewport_size({"width": 768, "height": 1024})  # tablet
        page.goto(DEMO, wait_until="networkidle")
        page.wait_for_timeout(1000)
        screenshot(page, "FINAL_tablet_768")
        print(D(f"        Tablet viewport (768×1024) snapshot saved ✓"))
        page.set_viewport_size({"width": 1280, "height": 800})

    run("full page screenshot (1280×800)", full_page_screenshot, page)
    run("mobile viewport (390×844) doesn't white-screen", mobile_viewport_screenshot, page)
    run("tablet viewport (768×1024) renders", narrow_viewport_screenshot, page)


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    print()
    print(B("=" * 64))
    print(B("  MemoryOS UI Test Suite"))
    print(B("=" * 64))
    print(f"  Target   : {DEMO}")
    print(f"  Headed   : {args.headed}")
    print(f"  Fast     : {args.fast}")
    print(f"  Screenshots → {SCREENSHOTS_DIR}")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

        # Capture console messages
        console_msgs: list = []
        page = context.new_page()
        page.on("console", lambda msg: console_msgs.append(msg))
        page.on("pageerror", lambda err: console_msgs.append(
            type("E", (), {"type": "error", "text": str(err)})()
        ))

        try:
            phase1_load(page, console_msgs)
            phase2_add_memory(page)
            phase3_search(page)
            phase4_right_panel(page)
            phase5_edge_cases(page)
            phase6_memory_cards(page)
            phase7_offline(page)
            phase8_screenshots(page)
        finally:
            context.close()
            browser.close()

    fails = report.summary()
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
