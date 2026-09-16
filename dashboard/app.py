"""Modern NBA Analytics Lakehouse Dashboard & Matchup Engine."""
from __future__ import annotations

import os
from typing import Any
import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Baseline NBA Analytics Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern card styling, badges, and typography
st.markdown(
    """
    <style>
    .main {
        background-color: #0e1117;
    }
    .metric-card {
        background: #1e222d;
        border: 1px solid #2e3546;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .team-badge {
        font-size: 1.8rem;
        font-weight: 800;
        letter-spacing: 1px;
    }
    .edge-badge-a {
        color: #00d26a;
        font-weight: 700;
    }
    .edge-badge-b {
        color: #3b82f6;
        font-weight: 700;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 8px 18px;
        background-color: #1e222d;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def fetch_api_data(endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch structured JSON payload from FastAPI backend."""
    try:
        url = f"{API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        response = httpx.get(url, params=params, timeout=10.0)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []


# Sidebar Navigation
with st.sidebar:
    st.markdown("## ⚡ **Baseline NBA**")
    st.caption("Lakehouse Analytics & Matchup Engine")
    st.divider()

    selected_season = st.selectbox("Season", options=["2024-25", "2023-24"], index=0)

    st.markdown("### Engine Controls")
    if st.button("🔄 Flush Redis Cache", use_container_width=True):
        try:
            res = httpx.delete(f"{API_BASE_URL}/cache", timeout=5.0)
            if res.status_code == 200:
                st.success("Redis Cache Cleared!")
                st.cache_data.clear()
        except Exception as exc:
            st.error(f"Cache error: {exc}")

    st.divider()
    st.markdown(
        """
        **Architecture Stack:**
        - **Lakehouse:** Postgres + dbt + dlt
        - **Cache:** In-Memory Redis
        - **Backend:** FastAPI REST
        - **UI:** Streamlit & Plotly
        """
    )

# Load Master Ratings
raw_ratings = fetch_api_data("/analytics/team-ratings", params={"season": selected_season})
df_ratings = pd.DataFrame(raw_ratings)

if not df_ratings.empty:
    numeric_cols = [
        "wins", "losses", "win_percentage", "pace",
        "offensive_rating", "defensive_rating", "net_rating",
        "strength_of_schedule", "adjusted_offensive_rating",
        "adjusted_defensive_rating", "adjusted_net_rating",
    ]
    for col in numeric_cols:
        if col in df_ratings.columns:
            df_ratings[col] = pd.to_numeric(df_ratings[col], errors="coerce")

tab_overview, tab_matchup, tab_surges = st.tabs(
    ["📊 Team Efficiency Matrix", "⚔️ Head-to-Head Tale of the Tape", "🔥 Player Surge Tracker"]
)

# ---------------------------------------------------------
# TAB 1: TEAM EFFICIENCY MATRIX
# ---------------------------------------------------------
with tab_overview:
    if not df_ratings.empty:
        # Top KPI Cards
        top_net = df_ratings.sort_values(by="adjusted_net_rating", ascending=False).iloc[0]
        top_off = df_ratings.sort_values(by="adjusted_offensive_rating", ascending=False).iloc[0]
        top_def = df_ratings.sort_values(by="adjusted_defensive_rating", ascending=True).iloc[0]
        fastest_pace = df_ratings.sort_values(by="pace", ascending=False).iloc[0]

        kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
        with kpi_1:
            st.metric(
                label="👑 Net Efficiency Leader",
                value=f"{top_net['team_abbreviation']}",
                delta=f"+{top_net['adjusted_net_rating']:.2f} Adj Net",
            )
        with kpi_2:
            st.metric(
                label="🎯 Top Offensive Rating",
                value=f"{top_off['team_abbreviation']}",
                delta=f"{top_off['adjusted_offensive_rating']:.1f} Pts/100",
            )
        with kpi_3:
            st.metric(
                label="🔒 Top Defensive Rating",
                value=f"{top_def['team_abbreviation']}",
                delta=f"{top_def['adjusted_defensive_rating']:.1f} Pts Allowed",
                delta_color="inverse",
            )
        with kpi_4:
            st.metric(
                label="⚡ Fastest Pace",
                value=f"{fastest_pace['team_abbreviation']}",
                delta=f"{fastest_pace['pace']:.1f} Poss/48m",
            )

        st.markdown("<br>", unsafe_allow_html=True)

        col_scatter, col_standings = st.columns([3, 2])

        with col_scatter:
            with st.container(border=True):
                st.markdown("#### Four-Quadrant Tier Analysis")
                st.caption("Adjusted for opponent strength of schedule. Lower Defensive Rating = stingier defense.")

                avg_off = df_ratings["adjusted_offensive_rating"].mean()
                avg_def = df_ratings["adjusted_defensive_rating"].mean()

                fig = px.scatter(
                    df_ratings,
                    x="adjusted_offensive_rating",
                    y="adjusted_defensive_rating",
                    text="team_abbreviation",
                    color="adjusted_net_rating",
                    color_continuous_scale="Tealrose",
                    size="win_percentage",
                    size_max=16,
                    hover_name="team_abbreviation",
                    hover_data={
                        "wins": True,
                        "losses": True,
                        "pace": True,
                        "strength_of_schedule": True,
                        "adjusted_net_rating": ":.2f",
                    },
                    template="plotly_dark",
                )

                # Invert Y-axis so elite defenses are at top
                fig.update_yaxes(autorange="reversed", title="Opponent-Adj Defensive Rating (Pts Allowed / 100)")
                fig.update_xaxes(title="Opponent-Adj Offensive Rating (Pts Scored / 100)")
                fig.update_traces(textposition="top center", textfont=dict(size=11, color="white"))

                # Quadrant Guide Lines
                fig.add_vline(x=avg_off, line_width=1, line_dash="dash", line_color="#555")
                fig.add_hline(y=avg_def, line_width=1, line_dash="dash", line_color="#555")

                # Quadrant Labels
                fig.add_annotation(x=avg_off + 2.5, y=avg_def - 3.5, text="🏆 TITLE CONTENDERS", showarrow=False, font=dict(color="#00d26a", size=11))
                fig.add_annotation(x=avg_off - 2.5, y=avg_def - 3.5, text="🛡️ DEFENSIVE GRINDERS", showarrow=False, font=dict(color="#3b82f6", size=11))
                fig.add_annotation(x=avg_off + 2.5, y=avg_def + 3.5, text="🔥 OFFENSIVE GUNNERS", showarrow=False, font=dict(color="#f59e0b", size=11))
                fig.add_annotation(x=avg_off - 2.5, y=avg_def + 3.5, text="⚠️ LOTTERY BOUND", showarrow=False, font=dict(color="#ef4444", size=11))

                fig.update_layout(height=520, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig, use_container_width=True)

        with col_standings:
            with st.container(border=True):
                st.markdown("#### League Efficiency Rankings")
                display_cols = [
                    "team_abbreviation", "wins", "losses", "pace",
                    "adjusted_offensive_rating", "adjusted_defensive_rating", "adjusted_net_rating"
                ]
                df_sorted = df_ratings[display_cols].sort_values(by="adjusted_net_rating", ascending=False)
                st.dataframe(
                    df_sorted.rename(columns={
                        "team_abbreviation": "Team",
                        "wins": "W",
                        "losses": "L",
                        "pace": "Pace",
                        "adjusted_offensive_rating": "Off Rtg",
                        "adjusted_defensive_rating": "Def Rtg",
                        "adjusted_net_rating": "Net Rtg"
                    }),
                    height=510,
                    hide_index=True,
                    use_container_width=True,
                )
    else:
        st.warning("No rating data available. Start the backend API to populate.")

# ---------------------------------------------------------
# TAB 2: HEAD-TO-HEAD TALE OF THE TAPE
# ---------------------------------------------------------
with tab_matchup:
    if not df_ratings.empty:
        st.markdown("### Matchup Tale of the Tape")
        st.caption("Direct side-by-side efficiency and stylistic breakdown.")

        team_list = sorted(df_ratings["team_abbreviation"].tolist())
        col_sel1, col_vs, col_sel2 = st.columns([4, 1, 4])
        with col_sel1:
            team_a = st.selectbox("Home Team / Team A", options=team_list, index=0)
        with col_vs:
            st.markdown("<h3 style='text-align: center; margin-top: 25px;'>VS</h3>", unsafe_allow_html=True)
        with col_sel2:
            team_b = st.selectbox("Away Team / Team B", options=team_list, index=min(1, len(team_list) - 1))

        t_a = df_ratings[df_ratings["team_abbreviation"] == team_a].iloc[0]
        t_b = df_ratings[df_ratings["team_abbreviation"] == team_b].iloc[0]

        # Top Summary Card Header
        card_a, card_b = st.columns(2)
        with card_a:
            with st.container(border=True):
                st.markdown(f"## **{team_a}**")
                st.markdown(f"**Record:** {int(t_a['wins'])}-{int(t_a['losses'])} &nbsp; | &nbsp; **Win %:** {t_a['win_percentage'] * 100:.1f}%")
                st.markdown(f"**Adj Net Rating:** `{t_a['adjusted_net_rating']:+.2f}`")

        with card_b:
            with st.container(border=True):
                st.markdown(f"## **{team_b}**")
                st.markdown(f"**Record:** {int(t_b['wins'])}-{int(t_b['losses'])} &nbsp; | &nbsp; **Win %:** {t_b['win_percentage'] * 100:.1f}%")
                st.markdown(f"**Adj Net Rating:** `{t_b['adjusted_net_rating']:+.2f}`")

        st.markdown("<br>", unsafe_allow_html=True)

        # Statistical Battle Matrix
        with st.container(border=True):
            st.markdown("#### Head-to-Head Metric Comparison")

            metrics_to_compare = [
                ("Adj Offensive Rating (Pts/100)", "adjusted_offensive_rating", True),
                ("Adj Defensive Rating (Lower is Better)", "adjusted_defensive_rating", False),
                ("Adj Net Rating", "adjusted_net_rating", True),
                ("Pace (Possessions/48m)", "pace", True),
                ("Strength of Schedule", "strength_of_schedule", True),
                ("Raw Win Percentage", "win_percentage", True),
            ]

            comp_rows = []
            for label, col, higher_is_better in metrics_to_compare:
                val_a = float(t_a[col])
                val_b = float(t_b[col])

                if higher_is_better:
                    edge = team_a if val_a > val_b else (team_b if val_b > val_a else "TIE")
                else:
                    edge = team_a if val_a < val_b else (team_b if val_b < val_a else "TIE")

                diff = abs(val_a - val_b)
                comp_rows.append({
                    "Metric": label,
                    f"{team_a}": f"{val_a:.2f}",
                    f"{team_b}": f"{val_b:.2f}",
                    "Differential": f"{diff:.2f}",
                    "Statistical Advantage": f"⭐ {edge}" if edge != "TIE" else "EVEN",
                })

            st.dataframe(pd.DataFrame(comp_rows), hide_index=True, use_container_width=True)

        # Visual Edge Breakdown Chart
        with st.container(border=True):
            st.markdown("#### Relative Efficiency Advantage")
            diff_categories = ["Offense", "Defense (Inv)", "Net Rating", "Pace"]
            # For defense: positive delta means team A allows fewer points (better defense)
            diff_values = [
                t_a["adjusted_offensive_rating"] - t_b["adjusted_offensive_rating"],
                t_b["adjusted_defensive_rating"] - t_a["adjusted_defensive_rating"],
                t_a["adjusted_net_rating"] - t_b["adjusted_net_rating"],
                t_a["pace"] - t_b["pace"],
            ]

            fig_bar = go.Figure()
            colors = ["#00d26a" if v >= 0 else "#3b82f6" for v in diff_values]
            fig_bar.add_trace(
                go.Bar(
                    x=diff_values,
                    y=diff_categories,
                    orientation="h",
                    marker_color=colors,
                    text=[f"{v:+.2f}" for v in diff_values],
                    textposition="auto",
                )
            )
            fig_bar.update_layout(
                title=f"Metric Differential: Positive favors {team_a} (Green) | Negative favors {team_b} (Blue)",
                template="plotly_dark",
                height=320,
                xaxis=dict(title="Net Delta", zeroline=True, zerolinewidth=2, zerolinecolor="white"),
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

# ---------------------------------------------------------
# TAB 3: PLAYER SURGE TRACKER
# ---------------------------------------------------------
with tab_surges:
    st.markdown("### 🔥 Hot & Cold Scoring Surge Tracker")
    st.caption("Identifies players deviating significantly from their baseline scoring over their last 10 games.")

    col_ctrl, _ = st.columns([2, 3])
    with col_ctrl:
        limit_val = st.slider("Display Count", min_value=5, max_value=25, value=12)

    surge_data = fetch_api_data("/analytics/surging-players", params={"season": selected_season, "limit": limit_val})

    if surge_data:
        df_surge = pd.DataFrame(surge_data)
        surge_cols = ["rolling_10_pts_avg", "scoring_surge_differential"]
        for col in surge_cols:
            if col in df_surge.columns:
                df_surge[col] = pd.to_numeric(df_surge[col], errors="coerce")

        col_surge_chart, col_surge_table = st.columns([3, 2])

        with col_surge_chart:
            with st.container(border=True):
                fig_surge = px.bar(
                    df_surge,
                    x="scoring_surge_differential",
                    y="player_name",
                    orientation="h",
                    color="scoring_surge_differential",
                    color_continuous_scale="Spectral",
                    text="scoring_surge_differential",
                    hover_data=["team_abbreviation", "rolling_10_pts_avg"],
                    template="plotly_dark",
                    title="10-Game Scoring Differential (PPG vs Season Avg)",
                )
                fig_surge.update_layout(yaxis={"categoryorder": "total ascending"}, height=520, margin=dict(l=20, r=20, t=40, b=20))
                fig_surge.update_traces(texttemplate="+%{text:.1f} PPG", textposition="outside")
                st.plotly_chart(fig_surge, use_container_width=True)

        with col_surge_table:
            with st.container(border=True):
                st.markdown("#### Surge Leaderboard")
                st.dataframe(
                    df_surge[["player_name", "team_abbreviation", "rolling_10_pts_avg", "scoring_surge_differential"]].rename(
                        columns={
                            "player_name": "Player",
                            "team_abbreviation": "Team",
                            "rolling_10_pts_avg": "L10 PPG",
                            "scoring_surge_differential": "+/- Diff",
                        }
                    ),
                    height=480,
                    hide_index=True,
                    use_container_width=True,
                )
    else:
        st.warning("No surge data found.")