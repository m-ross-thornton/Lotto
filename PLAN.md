# Lotto Scratch-Off Analyzer — Project Plan

## Goal

Identify scratch-off lottery tickets with the best expected value: fewest tickets remaining in the print run, but the most high-tier prizes (grand, 1st, 2nd) still unclaimed. Start with Maryland, expand to VA, PA, DE.

**Why this works:** MD scratch-off tickets are batch-printed with a fixed, known pool of winners at each prize tier. The "odds" printed on a ticket are simply `winners / total_tickets_in_run`. Because MD Lottery publishes how many prizes at each tier have been claimed, we can compute remaining expected value with real math — not just printed odds.

---

## Research Summary (MD Lottery — 2026-05-23)

| Question | Finding |
|---|---|
| Remaining prizes published? | **Yes** — per-tier prize tables with `Start` and `Remaining` counts for every prize level |
| Data fields available | Game name, price, top prize, top prizes remaining, chances to win, launch date, overall win probability, full prize tier breakdown |
| Per-retailer game inventory? | **No** — only a generic zip-code retailer locator. No per-game-per-store data. |
| Tickets batched or rolling? | **Batched** — confirmed: Start counts are fixed print-run totals; Remaining decrements as prizes are claimed |
| Scraping approach | **Plain HTTP GET** — no Playwright needed. Single AJAX endpoint returns all 91 games + prize tables in one request |
| Key endpoint | `GET https://www.mdlottery.com/wp-admin/admin-ajax.php?action=jquery_shortcode&shortcode=scratch_offs&atts=%7B%22null%22%3A%22null%22%7D` |
| Response format | HTML (317 KB) — parsed with BeautifulSoup |
| Crawl delay (robots.txt) | 10 seconds between requests |
| Total tickets per game | Not directly given — estimated as `sum(all_prize_start_counts) × probability_denominator` |

### Phase 1 Output Files
- `data/discovered_endpoints.json` — all captured network requests/responses
- `data/page_snapshot.html` — rendered page HTML (719 KB)
- `scraper/md_lottery.py` — working scraper producing EV rankings (tested live, 91 games)

---

## Tech Stack

| Layer | Tool |
|---|---|
| Scraper | Python + requests + BeautifulSoup (no Playwright needed) |
| Storage | SQLite (via `sqlite3` or `SQLAlchemy`) |
| Scheduling | APScheduler or cron |
| Frontend | Streamlit |
| Mapping | `folium` or `pydeck` (Streamlit-compatible) |
| Dependency mgmt | `uv` + `pyproject.toml` |

---

## Project Structure

```
Lotto/
├── PLAN.md                  # this file
├── pyproject.toml
├── .env.example
├── data/
│   └── lotto.db             # SQLite database
├── scraper/
│   ├── __init__.py
│   ├── md_lottery.py        # MD-specific scraper
│   ├── discover.py          # Playwright network interceptor (Phase 1)
│   └── scheduler.py         # refresh scheduling
├── db/
│   ├── __init__.py
│   ├── schema.py            # table definitions
│   └── queries.py           # named queries / ORM helpers
├── scoring/
│   ├── __init__.py
│   └── ev.py                # expected value algorithm
└── app/
    ├── __init__.py
    ├── main.py              # Streamlit entry point
    ├── pages/
    │   ├── games.py         # game list + EV table
    │   ├── game_detail.py   # single game prize breakdown + history chart
    │   └── map.py           # retailer map
    └── components/
        └── filters.py       # shared sidebar filters
```

---

## Phase 1 — API Discovery (Start Here)

**Goal:** Find the actual AJAX/fetch endpoints that power the MD Lottery scratch-offs page, so we know exactly what data fields exist before building any schema or UI.

### Steps

1. **Write `scraper/discover.py`**
   - Launch Playwright (headless Chromium)
   - Navigate to `https://www.mdlottery.com/games/scratch-offs/`
   - Intercept all `fetch` and `XHR` network requests
   - Wait for page to fully load (wait for game cards to appear)
   - Dump all captured request/response pairs to `data/discovered_endpoints.json`

2. **Trigger the "Compare Tickets" export**
   - In the same Playwright session, click the "Compare Tickets" button
   - Capture the downloaded file (CSV or XLSX)
   - Save to `data/sample_export/` and inspect column names

3. **Browse individual game detail modals**
   - Click each `[Ticket Details]` link and capture the AJAX payload
   - Look for: prize tier name, original count, remaining count, prize value

4. **Document findings**
   - Update the "Data Schema" section below with real field names
   - Note which fields are per-game vs. per-prize-tier

### Deliverable
`data/discovered_endpoints.json` — list of endpoints, methods, and sample responses
`data/sample_export/` — raw export file from Compare Tickets

---

## Phase 2 — Scraper & Data Pipeline

**Goal:** Reliable, repeatable scraper that captures a full snapshot of all active MD games + prize tiers.

### Steps

1. **Database schema (`db/schema.py`)**

   ```sql
   CREATE TABLE games (
     game_id       TEXT PRIMARY KEY,   -- MD Lottery game number
     name          TEXT,
     price_dollars REAL,
     start_date    DATE,
     last_claim_date DATE,
     total_tickets INTEGER,
     is_active     BOOLEAN,
     updated_at    DATETIME
   );

   CREATE TABLE prize_tiers (
     id            INTEGER PRIMARY KEY AUTOINCREMENT,
     game_id       TEXT REFERENCES games(game_id),
     tier_name     TEXT,              -- "Grand Prize", "1st", "2nd", etc.
     prize_value   REAL,
     original_count INTEGER,
     remaining_count INTEGER,
     snapshot_at   DATETIME
   );

   CREATE TABLE snapshots (
     id            INTEGER PRIMARY KEY AUTOINCREMENT,
     game_id       TEXT REFERENCES games(game_id),
     snapshot_at   DATETIME,
     remaining_tickets INTEGER,
     top_prizes_remaining INTEGER,
     all_prizes_remaining INTEGER,
     win_probability REAL
   );
   ```

   > Note: `prize_tiers` stores one row per tier per snapshot — keep history so we can chart prize depletion over time.

2. **Scraper (`scraper/md_lottery.py`)**
   - Use the endpoints discovered in Phase 1
   - Fetch all active games + prize tier details
   - Upsert into `games` and insert new rows into `prize_tiers` and `snapshots`
   - Respect 10-second crawl delay

3. **Scheduler (`scraper/scheduler.py`)**
   - On-demand: `python -m scraper.md_lottery`
   - Scheduled: daily refresh at a configurable time (APScheduler or cron)

---

## Phase 3 — Scoring Algorithm

**Goal:** Rank games by expected value per dollar spent, with secondary signals for anomalous prize distributions.

### Core Metric: Expected Value per Dollar

```
EV = Σ(tier_prize_value × tier_remaining_count) / remaining_tickets / ticket_price
```

Example: A $5 ticket with 2 grand prizes ($100k each) remaining out of 50,000 tickets left:
```
EV = (100000 × 2) / 50000 / 5 = 0.80  →  80 cents expected per dollar spent
```

### Secondary Signals

| Signal | Formula | Meaning |
|---|---|---|
| Top prize density | `top_prizes_remaining / remaining_tickets` | Higher = better shot at top prize |
| Game completion % | `1 - (remaining_tickets / total_tickets)` | Higher = game near end of run |
| Prize anomaly score | `(prizes_remaining_pct - tickets_remaining_pct)` | Positive = prizes depleting slower than tickets (lucky streak in other tiers?) |

### Implementation (`scoring/ev.py`)

- Input: snapshot record + prize tier rows for a game
- Output: dict of scores per game
- Expose as a pure function so Streamlit can call it on cached data

---

## Phase 4 — Streamlit Frontend

### Pages

**1. Game List (`app/pages/games.py`)**
- Table of all active games sorted by EV score (default)
- Columns: name, price, EV/dollar, top prizes left, tickets left, completion %, last updated
- Sidebar filters: price range, min top prizes remaining, min EV threshold
- Click row → game detail page

**2. Game Detail (`app/pages/game_detail.py`)**
- Full prize tier table: tier name, prize value, original count, remaining, % claimed
- Line chart: prizes remaining over time (from `snapshots` history)
- EV score breakdown
- Last claim date / active status

**3. Retailer Map (`app/pages/map.py`)**
- Zip-code search → show nearby MD Lottery retailers (from retailer locator)
- Note: per-game inventory is NOT available from MD Lottery — map shows retailer locations only
- Future: if per-retailer data becomes available, add game filter overlay

**4. Refresh (`app/main.py` sidebar)**
- "Refresh Data" button triggers scraper run
- Show last-updated timestamp

---

## Phase 5 — Expansion to Other States

Research needed per state before implementing:

| State | Lottery Site | Remaining Prizes Published? | Notes |
|---|---|---|---|
| VA | `valottery.com` | Unknown | Research needed |
| PA | `palottery.com` | Unknown | Research needed |
| DE | `delottery.com` | Unknown | Research needed |

Each state will need its own scraper module under `scraper/` (e.g., `scraper/va_lottery.py`).

---

## Implementation Order

1. `[x]` Phase 1 — Run `discover.py`, inspect endpoints and export file
2. `[x]` Phase 2a — Write `db/schema.py`, create SQLite DB
3. `[x]` Phase 2b — Write `scraper/md_lottery.py` using discovered endpoints
4. `[x]` Phase 2c — Run first full scrape, verify data in DB (91 games, 939 prize tier rows)
5. `[ ]` Phase 3 — Write `scoring/ev.py`, test against scraped data
6. `[ ]` Phase 4a — Build Streamlit game list page
7. `[ ]` Phase 4b — Build game detail page
8. `[ ]` Phase 4c — Build retailer map page
9. `[ ]` Phase 5 — Research and add VA, PA, DE scrapers

---

## Open Questions

- **Batch size / total tickets per game:** Is total print-run size published anywhere on the MD Lottery site, or only inferrable from prize odds? (e.g., `1 in 3.5 odds` × `known winner count` = total tickets)
- **Retailer inventory:** Confirmed NOT available publicly. Worth emailing MD Lottery to ask if a data feed exists.
- **Terms of Service:** MD Lottery robots.txt allows crawling with a 10-second delay. Review full ToS before productionizing automated scraping.
- **Historical data:** No archive exists — we'll only have history from when we start running snapshots. Consider starting the scraper ASAP to build a baseline.
