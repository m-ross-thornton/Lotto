"""Game rankings page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_connection
from scoring.ev import get_ev_history


def render(df: pd.DataFrame):
    st.header("🏆 Game Rankings")

    if df.empty:
        st.warning("No data yet — click **Refresh Data** in the sidebar.")
        return

    # ── Filters ────────────────────────────────────────────────────────────
    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)

        prices = sorted(df["price"].unique())
        selected_prices = col1.multiselect(
            "Ticket price ($)",
            options=prices,
            default=prices,
            format_func=lambda p: f"${p:.0f}",
        )

        min_top_prizes = col2.number_input(
            "Min top prizes remaining",
            min_value=0,
            max_value=int(df["top_prizes_remaining"].max()),
            value=0,
        )

        min_ev = col3.slider(
            "Min EV per dollar",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.01,
            format="%.2f",
        )

    filtered = df[
        df["price"].isin(selected_prices)
        & (df["top_prizes_remaining"] >= min_top_prizes)
        & (df["ev_per_dollar"] >= min_ev)
    ].copy()

    st.caption(f"Showing {len(filtered)} of {len(df)} games")

    # ── Summary metrics ────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Games shown", len(filtered))
    m2.metric("Best EV/dollar", f"{filtered['ev_per_dollar'].max():.3f}" if not filtered.empty else "—")
    m3.metric("Total top prizes left", f"{filtered['top_prizes_remaining'].sum():,}")
    m4.metric("Avg completion", f"{filtered['completion_pct'].mean() * 100:.1f}%" if not filtered.empty else "—")

    st.divider()

    # ── Main table ─────────────────────────────────────────────────────────
    display = filtered[[
        "name", "price", "ev_per_dollar", "top_prize",
        "top_prizes_remaining", "all_prizes_remaining",
        "est_remaining_tickets", "completion_pct", "top_prize_density",
    ]].copy()

    display.columns = [
        "Game", "Price ($)", "EV / Dollar", "Top Prize ($)",
        "Top Prizes Left", "All Prizes Left",
        "Est. Tickets Left", "% Complete", "Top Prize / 1M tickets",
    ]

    display["Price ($)"] = display["Price ($)"].apply(lambda x: f"${x:.0f}")
    display["Top Prize ($)"] = display["Top Prize ($)"].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
    )
    display["Est. Tickets Left"] = display["Est. Tickets Left"].apply(
        lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
    )
    display["% Complete"] = display["% Complete"].apply(
        lambda x: f"{x * 100:.1f}%" if pd.notna(x) else "—"
    )
    display["Top Prize / 1M tickets"] = display["Top Prize / 1M tickets"].apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else "—"
    )

    # Colour EV column green→red
    st.dataframe(
        display.style.background_gradient(
            subset=["EV / Dollar"], cmap="RdYlGn", vmin=0.5, vmax=0.9
        ),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    # ── EV over time: top 20 games ────────────────────────────────────────
    st.subheader("EV / Dollar Over Time — Top 20 Games")

    top20_ids = df.head(20)["game_id"].tolist()
    with get_connection() as conn:
        history = get_ev_history(conn, top20_ids)

    if history.empty or history["scraped_at"].nunique() < 2:
        st.info(
            "Only one snapshot so far — run **Refresh Data** again later "
            "to start seeing trends."
        )
    else:
        # Keep only names that appear in the top-20 of the *current* ranking
        # so the legend stays readable even if a game moves in/out over time
        top20_names = df.head(20)["name"].tolist()
        history = history[history["name"].isin(top20_names)]

        fig = px.line(
            history,
            x="scraped_at",
            y="ev_per_dollar",
            color="name",
            markers=True,
            labels={
                "scraped_at": "Date",
                "ev_per_dollar": "EV / Dollar",
                "name": "Game",
            },
            hover_data={"ev_per_dollar": ":.4f"},
        )
        fig.update_layout(
            height=450,
            yaxis_tickformat=".3f",
            legend=dict(
                orientation="v",
                x=1.01,
                y=1,
                font=dict(size=11),
            ),
            margin=dict(r=220),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── EV scatter: completion vs EV, bubble = top prizes left ────────────
    st.subheader("Completion vs. Expected Value")
    st.caption("Bubble size = top prizes remaining. Look for large bubbles in the upper-right.")

    if not filtered.empty:
        fig = px.scatter(
            filtered,
            x="completion_pct",
            y="ev_per_dollar",
            size="top_prizes_remaining",
            color="price",
            hover_name="name",
            hover_data={
                "top_prizes_remaining": True,
                "all_prizes_remaining": True,
                "price": True,
                "completion_pct": ":.1%",
                "ev_per_dollar": ":.3f",
            },
            labels={
                "completion_pct": "Game Completion (% of print run sold)",
                "ev_per_dollar": "Expected Value per Dollar",
                "price": "Price ($)",
            },
            color_continuous_scale="Viridis",
            size_max=40,
        )
        fig.update_layout(height=450, xaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "ℹ️ EV is estimated from remaining prize value ÷ estimated remaining tickets ÷ ticket price. "
        "Ticket counts are estimated using overall win probability × prize counts."
    )
