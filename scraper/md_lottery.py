"""
MD Lottery scratch-off scraper.

Fetches all active games and per-tier prize data from the WordPress AJAX
endpoint discovered in Phase 1, then upserts into the SQLite database.

Run with:
    uv run python -m scraper.md_lottery
"""

import re
import time
import logging
from datetime import datetime, date
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)

AJAX_URL = (
    "https://www.mdlottery.com/wp-admin/admin-ajax.php"
    "?action=jquery_shortcode&shortcode=scratch_offs&atts=%7B%22null%22%3A%22null%22%7D"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.mdlottery.com/games/scratch-offs/",
}

CRAWL_DELAY = 10  # seconds — as specified in robots.txt


@dataclass
class PrizeTier:
    prize_value: float
    start_count: int
    remaining_count: int


@dataclass
class Game:
    game_id: str
    name: str
    price: float
    top_prize: float
    top_prizes_remaining: int
    chances_to_win: int       # number of distinct prize tiers
    launch_date: date | None
    probability_denominator: float  # "1 in X" — X value
    prize_tiers: list[PrizeTier] = field(default_factory=list)
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    # Derived fields (populated after parse)
    all_prizes_start: int = 0
    all_prizes_remaining: int = 0
    estimated_total_tickets: int = 0
    estimated_remaining_tickets: int = 0
    ev_per_dollar: float = 0.0

    def compute_derived(self):
        self.all_prizes_start = sum(t.start_count for t in self.prize_tiers)
        self.all_prizes_remaining = sum(t.remaining_count for t in self.prize_tiers)
        # Estimate ticket counts using overall win probability
        # total_tickets ≈ total_prizes × probability_denominator
        if self.probability_denominator > 0:
            self.estimated_total_tickets = round(
                self.all_prizes_start * self.probability_denominator
            )
            self.estimated_remaining_tickets = round(
                self.all_prizes_remaining * self.probability_denominator
            )
        # Expected value per dollar spent
        if self.estimated_remaining_tickets > 0 and self.price > 0:
            total_prize_value = sum(
                t.prize_value * t.remaining_count for t in self.prize_tiers
            )
            self.ev_per_dollar = total_prize_value / self.estimated_remaining_tickets / self.price


def _parse_price(text: str) -> float:
    return float(re.sub(r"[^\d.]", "", text))


def _parse_date(text: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_games(html: str) -> list[Game]:
    soup = BeautifulSoup(html, "lxml")
    games: list[Game] = []

    for li in soup.select("li.ticket"):
        game_id_match = re.match(r"ticket_(\d+)", li.get("id", ""))
        if not game_id_match:
            continue
        game_id = game_id_match.group(1)

        def text(selector: str) -> str:
            el = li.select_one(selector)
            return el.get_text(strip=True) if el else ""

        price_str = text(".price")
        top_prize_str = text(".topprize")
        top_remaining_str = text(".topremaining")
        chances_str = text(".chancestowin")
        launch_str = text(".launchdate")
        prob_str = text(".probability")
        name = text(".name")

        try:
            price = _parse_price(price_str) if price_str else 0.0
            top_prize = _parse_price(top_prize_str) if top_prize_str else 0.0
            top_remaining = int(top_remaining_str) if top_remaining_str.isdigit() else 0
            chances = int(chances_str) if chances_str.isdigit() else 0
            probability = float(prob_str) if prob_str else 0.0
            launch = _parse_date(launch_str) if launch_str else None
        except (ValueError, AttributeError):
            log.warning("Failed to parse header fields for game %s", game_id)
            continue

        # Prize tier table: columns are Prize Amount | Start | Remaining
        prize_tiers: list[PrizeTier] = []
        prize_table = li.select_one(f"#prize_details_{game_id} table tbody tr")
        detail_div = li.select_one(f"#prize_details_{game_id}")
        if detail_div:
            for row in detail_div.select("tbody tr"):
                cells = row.find_all("td")
                if len(cells) != 3:
                    continue
                try:
                    prize_val = _parse_price(cells[0].get_text(strip=True))
                    start = int(cells[1].get_text(strip=True).replace(",", ""))
                    remaining = int(cells[2].get_text(strip=True).replace(",", ""))
                    prize_tiers.append(PrizeTier(prize_val, start, remaining))
                except (ValueError, AttributeError):
                    continue

        game = Game(
            game_id=game_id,
            name=name,
            price=price,
            top_prize=top_prize,
            top_prizes_remaining=top_remaining,
            chances_to_win=chances,
            launch_date=launch,
            probability_denominator=probability,
            prize_tiers=prize_tiers,
        )
        game.compute_derived()
        games.append(game)

    return games


def fetch_games() -> list[Game]:
    log.info("Fetching MD Lottery scratch-offs from AJAX endpoint ...")
    resp = requests.get(AJAX_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    log.info("Received %d bytes", len(html))
    games = parse_games(html)
    log.info("Parsed %d games", len(games))
    return games


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from db.schema import init_db
    from db import get_connection
    from db.queries import save_scrape_run

    init_db()
    games = fetch_games()

    conn = get_connection()
    save_scrape_run(conn, games)
    conn.close()
    log.info("Saved %d games to database.", len(games))

    print(f"\n{'Game':<35} {'$':>4} {'EV/$ ':>7} {'TopRem':>7} {'AllRem':>8} {'TixRem':>10}")
    print("-" * 80)
    for g in sorted(games, key=lambda g: g.ev_per_dollar, reverse=True)[:20]:
        print(
            f"{g.name:<35} "
            f"${g.price:>3.0f} "
            f"{g.ev_per_dollar:>7.3f} "
            f"{g.top_prizes_remaining:>7} "
            f"{g.all_prizes_remaining:>8,} "
            f"{g.estimated_remaining_tickets:>10,}"
        )

    print(f"\nTotal games: {len(games)}")
    print(f"Scraped at: {datetime.utcnow().isoformat()}Z")
