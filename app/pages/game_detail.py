"""Game detail page — prize tier breakdown and snapshot history charts."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import get_connection
from scoring.ev import get_prize_tiers, get_snapshot_history


def render(df: pd.DataFrame):
    st.header("🔍 Game Detail")

    if df.empty:
        st.warning("No data yet — click **Refresh Data** in the sidebar.")
        return

    # ── Game selector ──────────────────────────────────────────────────────
    game_options = df.sort_values("ev_per_dollar", ascending=False)
    selected_name = st.selectbox(
        "Select a game",
        options=game_options["name"].tolist(),
        format_func=lambda n: n,
    )

    row = df[df["name"] == selected_name].iloc[0]
    game_id = row["game_id"]

    # ── Header metrics ─────────────────────────────────────────────────────
    st.subheader(f"{row['name']}  —  ${row['price']:.0f} ticket")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("EV / Dollar", f"{row['ev_per_dollar']:.3f}")
    c2.metric("Top Prize", f"${row['top_prize']:,.0f}")
    c3.metric("Top Prizes Left", f"{row['top_prizes_remaining']:,}")
    c4.metric("Est. Tickets Left", f"{row['est_remaining_tickets']:,.0f}")
    c5.metric("Game Complete", f"{row['completion_pct'] * 100:.1f}%")

    st.divider()

    # ── Prize tier table ───────────────────────────────────────────────────
    with get_connection() as conn:
        tiers = get_prize_tiers(conn, game_id)
        history = get_snapshot_history(conn, game_id)

    st.subheader("Prize Tier Breakdown")
    if tiers.empty:
        st.info("No prize tier data available.")
    else:
        # Apply gradient on numeric values before any string formatting
        numeric = tiers[["pct_remaining"]].copy()

        display = tiers.copy()
        display["prize_value"] = display["prize_value"].apply(lambda x: f"${x:,.0f}")
        display["start_count"] = display["start_count"].apply(lambda x: f"{x:,}")
        display["remaining_count"] = display["remaining_count"].apply(lambda x: f"{x:,}")
        display["claimed_count"] = display["claimed_count"].apply(lambda x: f"{x:,}")
        display["pct_remaining"] = display["pct_remaining"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
        )
        display.columns = ["Prize", "Original", "Remaining", "Claimed", "% Left"]

        def _gradient(col):
            vals = numeric["pct_remaining"].fillna(0)
            lo, hi = vals.min(), vals.max()
            def color(v_str):
                try:
                    v = float(v_str.rstrip("%"))
                except (ValueError, AttributeError):
                    return ""
                ratio = (v - lo) / (hi - lo) if hi > lo else 0.5
                r = int(255 * (1 - ratio))
                g = int(200 * ratio)
                return f"background-color: rgb({r},{g},80)"
            return col.map(color)

        st.dataframe(
            display.style.apply(_gradient, subset=["% Left"]),
            use_container_width=True,
            hide_index=True,
        )

        # Bar chart: original vs remaining per tier
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Claimed",
            x=tiers["prize_value"].apply(lambda x: f"${x:,.0f}"),
            y=tiers["claimed_count"],
            marker_color="#ef553b",
        ))
        fig.add_trace(go.Bar(
            name="Remaining",
            x=tiers["prize_value"].apply(lambda x: f"${x:,.0f}"),
            y=tiers["remaining_count"],
            marker_color="#00cc96",
        ))
        fig.update_layout(
            barmode="stack",
            title="Claimed vs. Remaining by Prize Tier",
            xaxis_title="Prize Amount",
            yaxis_title="Count",
            height=350,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── History charts ─────────────────────────────────────────────────────
    st.subheader("Historical Trend")
    if len(history) < 2:
        st.info("Only one snapshot so far — run the scraper again later to see trends.")
    else:
        history["scraped_at"] = pd.to_datetime(history["scraped_at"])

        tab1, tab2, tab3 = st.tabs(["EV over Time", "Prizes Remaining", "Tickets Remaining"])

        with tab1:
            fig = px.line(
                history, x="scraped_at", y="ev_per_dollar",
                markers=True,
                labels={"scraped_at": "Date", "ev_per_dollar": "EV / Dollar"},
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig = px.line(
                history, x="scraped_at",
                y=["top_prizes_remaining", "all_prizes_remaining"],
                markers=True,
                labels={"scraped_at": "Date", "value": "Count", "variable": ""},
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            fig = px.line(
                history, x="scraped_at", y="est_remaining_tickets",
                markers=True,
                labels={"scraped_at": "Date", "est_remaining_tickets": "Est. Tickets Remaining"},
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

    st.caption(f"Game ID: #{game_id}  ·  Launch date: {row['launch_date'] or 'unknown'}")
