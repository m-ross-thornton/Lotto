"""
Streamlit entry point.

Run with:
    uv run streamlit run app/main.py
"""

import subprocess
import sys
from datetime import datetime

import streamlit as st

from db import get_connection
from db.schema import init_db
from scoring.ev import get_latest_scores

st.set_page_config(
    page_title="MD Lottery Scratch-Off Analyzer",
    page_icon="🎟️",
    layout="wide",
)

# ── Ensure DB exists ───────────────────────────────────────────────────────
init_db()


# ── Cached data loader ─────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_scores():
    with get_connection() as conn:
        return get_latest_scores(conn)


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎟️ MD Lotto Analyzer")
    st.caption("Maryland scratch-off expected value tracker")

    st.divider()

    if st.button("🔄 Refresh Data", use_container_width=True):
        with st.spinner("Scraping MD Lottery..."):
            result = subprocess.run(
                [sys.executable, "-m", "scraper.md_lottery"],
                capture_output=True,
                text=True,
            )
        if result.returncode == 0:
            st.cache_data.clear()
            st.success("Data refreshed!")
        else:
            st.error("Scrape failed — check logs.")
            st.code(result.stderr[-500:])

    df = load_scores()
    if not df.empty:
        last_scraped = df["scraped_at"].max()
        st.caption(f"Last updated: {last_scraped[:16].replace('T', ' ')} UTC")
        st.caption(f"{len(df)} active games")

    st.divider()
    page = st.radio(
        "Navigate",
        ["🏆 Game Rankings", "🔍 Game Detail"],
        label_visibility="collapsed",
    )

# ── Page routing ───────────────────────────────────────────────────────────
if page == "🏆 Game Rankings":
    from app.pages.games import render
    render(df)
else:
    from app.pages.game_detail import render
    render(df)
