"""
Phase 1 discovery script.

Loads the MD Lottery scratch-offs page with a real browser, intercepts every
network request/response, and saves a structured report to:
    data/discovered_endpoints.json
    data/sample_export/   (Compare Tickets download, if captured)
    data/page_snapshot.html (rendered HTML after JS runs)

Run with:
    uv run python -m scraper.discover
"""

import asyncio
import json
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright, Request, Response

BASE_URL = "https://www.mdlottery.com/games/scratch-offs/"
DATA_DIR = Path("data")
EXPORT_DIR = DATA_DIR / "sample_export"
ENDPOINTS_FILE = DATA_DIR / "discovered_endpoints.json"
SNAPSHOT_FILE = DATA_DIR / "page_snapshot.html"

# Resource types we care about — skip images, fonts, stylesheets
CAPTURE_TYPES = {"xhr", "fetch", "document", "script"}

# Patterns that indicate game/prize data vs. noise (analytics, ads, etc.)
INTERESTING_PATTERNS = re.compile(
    r"(scratch|game|ticket|prize|remaining|lottery|lotto|ajax)",
    re.IGNORECASE,
)


def is_interesting(url: str, resource_type: str) -> bool:
    if resource_type in ("xhr", "fetch"):
        return True  # capture all XHR/fetch unconditionally
    if resource_type == "document" and "scratch" in url:
        return True
    return bool(INTERESTING_PATTERNS.search(url))


async def try_get_body(response: Response) -> str | None:
    """Return response body as text, or None if binary / too large."""
    try:
        content_type = response.headers.get("content-type", "")
        if any(t in content_type for t in ("json", "text", "xml", "html")):
            return await response.text()
    except Exception:
        pass
    return None


async def discover():
    DATA_DIR.mkdir(exist_ok=True)
    EXPORT_DIR.mkdir(exist_ok=True)

    captured: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = await context.new_page()

        # ── Network interception ───────────────────────────────────────────
        response_bodies: dict[str, str] = {}

        async def on_response(response: Response):
            url = response.url
            rtype = response.request.resource_type
            if not is_interesting(url, rtype):
                return
            body = await try_get_body(response)
            if body is not None:
                response_bodies[url] = body

        page.on("response", on_response)

        async def on_request(request: Request):
            url = request.url
            rtype = request.resource_type
            if not is_interesting(url, rtype):
                return
            captured.append(
                {
                    "url": url,
                    "method": request.method,
                    "resource_type": rtype,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                    "response_body": None,  # filled in after response
                }
            )

        page.on("request", on_request)

        # ── Navigate to the scratch-offs page ─────────────────────────────
        print(f"Loading {BASE_URL} ...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)

        # Give JS-heavy SPA extra time to settle
        await asyncio.sleep(5)

        # ── Scroll to trigger lazy-loaded content ──────────────────────────
        print("Scrolling page to trigger lazy loads ...")
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(2)

        # ── Try clicking "Compare Tickets" / export button ─────────────────
        print("Looking for Compare Tickets / export button ...")
        export_selectors = [
            "text=Compare Tickets",
            "text=Export",
            "text=Download",
            "text=Spreadsheet",
            "[data-action*='export']",
            "[class*='export']",
            "[class*='compare']",
            "button:has-text('Compare')",
            "a:has-text('Compare')",
        ]
        export_clicked = False
        for sel in export_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2_000):
                    print(f"  Found export button: {sel!r}")
                    async with page.expect_download(timeout=10_000) as dl_info:
                        await btn.click()
                    download = await dl_info.value
                    dest = EXPORT_DIR / download.suggested_filename
                    await download.save_as(dest)
                    print(f"  Export saved to: {dest}")
                    export_clicked = True
                    await asyncio.sleep(3)
                    break
            except Exception as e:
                print(f"  Selector {sel!r} failed: {e}")

        if not export_clicked:
            print("  No export button found — will rely on intercepted XHR data.")

        # ── Try opening a Ticket Details modal ────────────────────────────
        print("Looking for Ticket Details links ...")
        detail_selectors = [
            "text=Ticket Details",
            "text=Game Details",
            "[class*='ticket-detail']",
            "a[href*='#ticket']",
            "button:has-text('Details')",
        ]
        for sel in detail_selectors:
            try:
                links = page.locator(sel)
                count = await links.count()
                if count > 0:
                    print(f"  Found {count} detail links via {sel!r} — clicking first 3 ...")
                    for i in range(min(3, count)):
                        await links.nth(i).click()
                        await asyncio.sleep(3)  # wait for modal + XHR
                    break
            except Exception as e:
                print(f"  Selector {sel!r} failed: {e}")

        # ── Save rendered HTML snapshot ────────────────────────────────────
        print("Saving rendered HTML snapshot ...")
        html = await page.content()
        SNAPSHOT_FILE.write_text(html, encoding="utf-8")
        print(f"  Saved {len(html):,} bytes to {SNAPSHOT_FILE}")

        # ── Attach response bodies to captured requests ────────────────────
        for entry in captured:
            entry["response_body"] = response_bodies.get(entry["url"])

        await browser.close()

    # ── Post-process: deduplicate by URL ──────────────────────────────────
    seen: set[str] = set()
    unique: list[dict] = []
    for entry in captured:
        if entry["url"] not in seen:
            seen.add(entry["url"])
            unique.append(entry)

    # ── Parse JSON response bodies where possible ─────────────────────────
    for entry in unique:
        body = entry.get("response_body")
        if body:
            try:
                entry["response_json"] = json.loads(body)
                entry["response_body"] = None  # avoid duplication
            except (json.JSONDecodeError, ValueError):
                entry["response_json"] = None

    # ── Print summary ──────────────────────────────────────────────────────
    xhr_fetch = [e for e in unique if e["resource_type"] in ("xhr", "fetch")]
    print(f"\n{'=' * 60}")
    print(f"Total unique requests captured: {len(unique)}")
    print(f"XHR / fetch requests:           {len(xhr_fetch)}")
    print()
    print("XHR/Fetch endpoints:")
    for e in xhr_fetch:
        body_summary = ""
        if e.get("response_json"):
            body_summary = f"  → JSON ({type(e['response_json']).__name__})"
        elif e.get("response_body"):
            body_summary = f"  → text ({len(e['response_body'])} chars)"
        print(f"  [{e['method']}] {e['url']}{body_summary}")

    # ── Write output ───────────────────────────────────────────────────────
    ENDPOINTS_FILE.write_text(
        json.dumps(unique, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nFull report saved to: {ENDPOINTS_FILE}")

    # ── Quick data quality check ───────────────────────────────────────────
    prize_hits = [
        e for e in xhr_fetch
        if e.get("response_json") and _contains_prize_data(e["response_json"])
    ]
    if prize_hits:
        print(f"\n*** {len(prize_hits)} endpoint(s) look like they contain prize/game data:")
        for e in prize_hits:
            print(f"    {e['url']}")
    else:
        print("\nNo XHR endpoints clearly contain prize/game data — check page_snapshot.html")
        print("for embedded JSON blobs (look for <script> tags with JSON data).")


def _contains_prize_data(obj, depth=0) -> bool:
    """Heuristic: does this JSON object contain lottery-relevant keys?"""
    if depth > 4:
        return False
    prize_keys = {"prize", "prizes", "remaining", "ticket", "tickets", "game", "games", "claimed"}
    if isinstance(obj, dict):
        if prize_keys & {k.lower() for k in obj}:
            return True
        return any(_contains_prize_data(v, depth + 1) for v in obj.values())
    if isinstance(obj, list) and obj:
        return _contains_prize_data(obj[0], depth + 1)
    return False


if __name__ == "__main__":
    start = time.time()
    asyncio.run(discover())
    print(f"\nDone in {time.time() - start:.1f}s")
