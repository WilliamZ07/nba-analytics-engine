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

st.markdown(
    """
    <style>
    .main { background-color: #0e1117; }
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 8px 18px;
        background-color: #1e222d;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_team_logo_url(team_abbrev: str) -> str:
    """Return high-resolution transparent PNG logo URL from CDN."""
    # Special mapping for teams if needed, otherwise ESPN's 500x500 CDN handles standard trico codes
    abbr = team_abbrev.lower()
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{abbr}.png"


def get_player_headshot_url(player_id: int | str) -> str:
    """Return official NBA headshot URL."""
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"


@st.cache_data(ttl=300)
def fetch_api_data(endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch structured JSON payload from FastAPI backend."""
    try:
        url = f"{API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        response = httpx.get(url, params=params, timeout=10.0)
        if response.status_code == 200:
            return response.json()
        st.warning(f"API {endpoint} ({response.status_code}): {response.text[:100]}")
        return []
    except Exception as exc:
        st.error(f"Failed to fetch {endpoint}: {exc}")
        return []


# Sidebar Navigation
with st.sidebar:
    st.markdown("## ⚡ **Baseline NBA**")
    st.caption("Lakehouse Analytics & Intelligence Engine")
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

# Master Data Loads
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

tab_overview, tab_matchup, tab_players, tab_surges = st.tabs(
    [
        "📊 Team Efficiency Matrix",
        "⚔️ Matchup Tale of the Tape",
        "👤 Player Intelligence & Logs",
        "🔥 Surge Tracker",
    ]
)

# ---------------------------------------------------------
# TAB 1: TEAM EFFICIENCY MATRIX
# ---------------------------------------------------------
with tab_overview:
    if not df_ratings.empty:
        top_net = df_ratings.sort_values(by="adjusted_net_rating", ascending=False).iloc[0]
        top_off = df_ratings.sort_values(by="adjusted_offensive_rating", ascending=False).iloc[0]
        top_def = df_ratings.sort_values(by="adjusted_defensive_rating", ascending=True).iloc[0]
        fastest_pace = df_ratings.sort_values(by="pace", ascending=False).iloc[0]

        kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
        kpi_1.metric("👑 Net Efficiency Leader", f"{top_net['team_abbreviation']}", f"+{top_net['adjusted_net_rating']:.2f} Adj Net")
        kpi_2.metric("🎯 Top Offensive Rating", f"{top_off['team_abbreviation']}", f"{top_off['adjusted_offensive_rating']:.1f} Pts/100")
        kpi_3.metric("🔒 Top Defensive Rating", f"{top_def['team_abbreviation']}", f"{top_def['adjusted_defensive_rating']:.1f} Pts Allowed", delta_color="inverse")
        kpi_4.metric("⚡ Fastest Pace", f"{fastest_pace['team_abbreviation']}", f"{fastest_pace['pace']:.1f} Poss/48m")

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
                    hover_data={"wins": True, "losses": True, "pace": True, "strength_of_schedule": True, "adjusted_net_rating": ":.2f"},
                    template="plotly_dark",
                )
                fig.update_yaxes(autorange="reversed", title="Opponent-Adj Defensive Rating (Pts Allowed / 100)")
                fig.update_xaxes(title="Opponent-Adj Offensive Rating (Pts Scored / 100)")
                fig.update_traces(textposition="top center", textfont=dict(size=11, color="white"))
                fig.add_vline(x=avg_off, line_width=1, line_dash="dash", line_color="#555")
                fig.add_hline(y=avg_def, line_width=1, line_dash="dash", line_color="#555")

                fig.add_annotation(x=avg_off + 2.5, y=avg_def - 3.5, text="🏆 TITLE CONTENDERS", showarrow=False, font=dict(color="#00d26a", size=11))
                fig.add_annotation(x=avg_off - 2.5, y=avg_def - 3.5, text="🛡️ DEFENSIVE GRINDERS", showarrow=False, font=dict(color="#3b82f6", size=11))
                fig.add_annotation(x=avg_off + 2.5, y=avg_def + 3.5, text="🔥 OFFENSIVE GUNNERS", showarrow=False, font=dict(color="#f59e0b", size=11))
                fig.add_annotation(x=avg_off - 2.5, y=avg_def + 3.5, text="⚠️ LOTTERY BOUND", showarrow=False, font=dict(color="#ef4444", size=11))

                fig.update_layout(height=520, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig, use_container_width=True)

        with col_standings:
            with st.container(border=True):
                st.markdown("#### League Efficiency Rankings")
                display_cols = ["team_abbreviation", "wins", "losses", "pace", "adjusted_offensive_rating", "adjusted_defensive_rating", "adjusted_net_rating"]
                df_sorted = df_ratings[display_cols].sort_values(by="adjusted_net_rating", ascending=False)
                st.dataframe(
                    df_sorted.rename(columns={
                        "team_abbreviation": "Team", "wins": "W", "losses": "L", "pace": "Pace",
                        "adjusted_offensive_rating": "Off Rtg", "adjusted_defensive_rating": "Def Rtg", "adjusted_net_rating": "Net Rtg"
                    }),
                    height=510,
                    hide_index=True,
                    use_container_width=True,
                )

# ---------------------------------------------------------
# TAB 2: HEAD-TO-HEAD TALE OF THE TAPE (WITH TEAM LOGOS)
# ---------------------------------------------------------
with tab_matchup:
    if not df_ratings.empty:
        st.markdown("### Matchup Tale of the Tape")
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

        card_a, card_b = st.columns(2)

        # Team A Card with Logo
        with card_a:
            with st.container(border=True):
                logo_col, text_col = st.columns([1, 3])
                with logo_col:
                    st.image(get_team_logo_url(team_a), width=100)
                with text_col:
                    st.markdown(f"## **{team_a}**")
                    st.markdown(f"**Record:** {int(t_a['wins'])}-{int(t_a['losses'])} &nbsp;|&nbsp; **Win %:** {t_a['win_percentage'] * 100:.1f}%")
                    st.markdown(f"**Adj Net Rating:** `{t_a['adjusted_net_rating']:+.2f}`")

        # Team B Card with Logo
        with card_b:
            with st.container(border=True):
                logo_col, text_col = st.columns([1, 3])
                with logo_col:
                    st.image(get_team_logo_url(team_b), width=100)
                with text_col:
                    st.markdown(f"## **{team_b}**")
                    st.markdown(f"**Record:** {int(t_b['wins'])}-{int(t_b['losses'])} &nbsp;|&nbsp; **Win %:** {t_b['win_percentage'] * 100:.1f}%")
                    st.markdown(f"**Adj Net Rating:** `{t_b['adjusted_net_rating']:+.2f}`")

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
                val_a, val_b = float(t_a[col]), float(t_b[col])
                edge = team_a if (val_a > val_b if higher_is_better else val_a < val_b) else (team_b if (val_b > val_a if higher_is_better else val_b < val_a) else "TIE")
                comp_rows.append({
                    "Metric": label,
                    f"{team_a}": f"{val_a:.2f}",
                    f"{team_b}": f"{val_b:.2f}",
                    "Differential": f"{abs(val_a - val_b):.2f}",
                    "Statistical Advantage": f"⭐ {edge}" if edge != "TIE" else "EVEN",
                })
            st.dataframe(pd.DataFrame(comp_rows), hide_index=True, use_container_width=True)

        with st.container(border=True):
            st.markdown("#### Relative Efficiency Advantage")
            diff_categories = ["Offense", "Defense (Inv)", "Net Rating", "Pace"]
            diff_values = [
                t_a["adjusted_offensive_rating"] - t_b["adjusted_offensive_rating"],
                t_b["adjusted_defensive_rating"] - t_a["adjusted_defensive_rating"],
                t_a["adjusted_net_rating"] - t_b["adjusted_net_rating"],
                t_a["pace"] - t_b["pace"],
            ]
            fig_bar = go.Figure(
                go.Bar(
                    x=diff_values,
                    y=diff_categories,
                    orientation="h",
                    marker_color=["#00d26a" if v >= 0 else "#3b82f6" for v in diff_values],
                    text=[f"{v:+.2f}" for v in diff_values],
                    textposition="auto",
                )
            )
            fig_bar.update_layout(template="plotly_dark", height=280, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_bar, use_container_width=True)

# ---------------------------------------------------------
# TAB 3: PLAYER INTELLIGENCE & LOGS (WITH HEADSHOTS & LOGOS)
# ---------------------------------------------------------
with tab_players:
    st.markdown("### 👤 Player Intelligence & Contextual Logs")

    players_pool = fetch_api_data("/players", params={"season": selected_season, "limit": 1000})

    if players_pool:
        player_map = {f"{p['player_name']} ({p.get('team_abbreviation') or 'NBA'})": p for p in players_pool}
        sorted_names = sorted(list(player_map.keys()))

        selected_player_str = st.selectbox(
            "Search & Select Any Player in the NBA",
            options=sorted_names,
            index=0,
            help="Type any player name to search across the entire league."
        )

        selected_player = player_map[selected_player_str]
        selected_player_id = selected_player["player_id"]
        team_abbr = selected_player.get("team_abbreviation") or "NBA"

        p_summary_raw = fetch_api_data(f"/players/{selected_player_id}/summary", params={"season": selected_season})
        p_games_raw = fetch_api_data(f"/players/{selected_player_id}/games", params={"season": selected_season, "limit": 82})
        p_splits_raw = fetch_api_data(f"/players/{selected_player_id}/splits", params={"season": selected_season})

        if not p_summary_raw or not p_games_raw:
            st.info(f"No game log records found for {selected_player_str} in season {selected_season}.")
        else:
            p_summary = p_summary_raw[0]
            df_p_games = pd.DataFrame(p_games_raw)

            stat_columns = [
                "points", "rebounds", "assists", "steals", "blocks", "turnovers",
                "ftm", "fta", "fg3_m", "fg3_a", "fgm", "fga",
                "rolling_10_pts_avg", "scoring_surge_differential",
                "true_shooting_pct", "minutes_played"
            ]
            for c in stat_columns:
                if c in df_p_games.columns:
                    df_p_games[c] = pd.to_numeric(df_p_games[c], errors="coerce").fillna(0.0)

            # Dossier Header with Headshot and Team Logo
            with st.container(border=True):
                col_headshot, col_bio = st.columns([1, 5])
                with col_headshot:
                    st.image(get_player_headshot_url(selected_player_id), width=150)
                with col_bio:
                    logo_subcol, name_subcol = st.columns([0.5, 6])
                    with logo_subcol:
                        if team_abbr != "NBA":
                            st.image(get_team_logo_url(team_abbr), width=50)
                    with name_subcol:
                        st.markdown(f"## **{selected_player['player_name']}**")
                        st.caption(f"**Team:** {team_abbr} &nbsp;|&nbsp; **Season:** {selected_season} &nbsp;|&nbsp; **Player ID:** `{selected_player_id}`")

                    # 7-Column Metric Banner
                    pk1, pk2, pk3, pk4, pk5, pk6, pk7 = st.columns(7)
                    pk1.metric("Season PPG", f"{float(p_summary.get('ppg') or 0.0):.1f}", f"{int(p_summary.get('games_played') or 0)} GP")
                    pk2.metric("Rebounds", f"{float(p_summary.get('rpg') or 0.0):.1f} RPG")
                    pk3.metric("Assists", f"{float(p_summary.get('apg') or 0.0):.1f} APG")
                    pk4.metric("Steals", f"{float(p_summary.get('spg') or 0.0):.1f} SPG")
                    pk5.metric("Blocks", f"{float(p_summary.get('bpg') or 0.0):.1f} BPG")
                    pk6.metric("True Shooting", f"{float(p_summary.get('true_shooting_pct') or 0.0):.1f}%")
                    latest_surge = df_p_games["scoring_surge_differential"].iloc[0] if not df_p_games.empty else 0.0
                    latest_rolling = df_p_games["rolling_10_pts_avg"].iloc[0] if not df_p_games.empty else 0.0
                    pk7.metric("Recent Form (L10)", f"{latest_rolling:.1f} PPG", f"{latest_surge:+.1f} vs Avg")

            st.markdown("<br>", unsafe_allow_html=True)

            # Interactive Timeline Chart
            with st.container(border=True):
                st.markdown("#### 📈 Game Scoring Performance vs. 10-Game Baseline")
                st.caption("Hover over any game for full box stats (PTS, REB, AST, STL, BLK, FT, TS%). Green = Boom (+5 pts), Red = Bust (-5 pts).")

                df_p_games_sorted = df_p_games.sort_values(by="game_date", ascending=True).reset_index(drop=True)
                season_ppg = float(p_summary.get("ppg") or 0.0)

                def categorize_game(pts: float) -> str:
                    if pts >= season_ppg + 5:
                        return "#00d26a"
                    elif pts <= season_ppg - 5:
                        return "#ef4444"
                    return "#9ca3af"

                marker_colors = [categorize_game(p) for p in df_p_games_sorted["points"]]

                fig_timeline = go.Figure()
                fig_timeline.add_hline(y=season_ppg, line_dash="dash", line_color="#f59e0b", annotation_text=f"Season Avg ({season_ppg:.1f})")
                fig_timeline.add_trace(go.Scatter(
                    x=df_p_games_sorted["game_date"],
                    y=df_p_games_sorted["rolling_10_pts_avg"],
                    mode="lines",
                    name="10-Game Trend",
                    line=dict(color="#3b82f6", width=2),
                ))
                fig_timeline.add_trace(go.Scatter(
                    x=df_p_games_sorted["game_date"],
                    y=df_p_games_sorted["points"],
                    mode="markers+lines",
                    name="Actual Points",
                    marker=dict(size=8, color=marker_colors),
                    line=dict(color="rgba(255, 255, 255, 0.2)", width=1),
                    hovertext=[
                        f"<b>{m} ({wl})</b><br>"
                        f"PTS: {int(pts)} | REB: {int(reb)} | AST: {int(ast)}<br>"
                        f"STL: {int(stl)} | BLK: {int(blk)} | TO: {int(tov)}<br>"
                        f"FT: {int(ftm)}/{int(fta)} | 3PT: {int(fg3m)}/{int(fg3a)}<br>"
                        f"TS%: {ts:.1f}%"
                        for m, wl, pts, reb, ast, stl, blk, tov, ftm, fta, fg3m, fg3a, ts in zip(
                            df_p_games_sorted["matchup"],
                            df_p_games_sorted["wl"],
                            df_p_games_sorted["points"],
                            df_p_games_sorted["rebounds"],
                            df_p_games_sorted["assists"],
                            df_p_games_sorted["steals"],
                            df_p_games_sorted["blocks"],
                            df_p_games_sorted["turnovers"],
                            df_p_games_sorted["ftm"],
                            df_p_games_sorted["fta"],
                            df_p_games_sorted["fg3_m"],
                            df_p_games_sorted["fg3_a"],
                            df_p_games_sorted["true_shooting_pct"],
                        )
                    ],
                    hoverinfo="text",
                ))
                fig_timeline.update_layout(template="plotly_dark", height=420, margin=dict(l=20, r=20, t=30, b=20), xaxis_title="Game Date", yaxis_title="Points Scored")
                st.plotly_chart(fig_timeline, use_container_width=True)

            # Contextual Splits & Detailed Game Logs
            col_splits, col_gamelog = st.columns([1, 1])

            with col_splits:
                with st.container(border=True):
                    st.markdown("#### 🎯 Contextual Performance Splits")
                    st.caption("How performance fluctuates based on location, game outcome, and opponent defense caliber.")
                    if p_splits_raw:
                        df_splits = pd.DataFrame(p_splits_raw)
                        st.dataframe(
                            df_splits.rename(columns={
                                "split_category": "Dimension",
                                "split_name": "Split",
                                "games": "GP",
                                "ppg": "PPG",
                                "rpg": "RPG",
                                "apg": "APG",
                                "spg": "SPG",
                                "bpg": "BPG",
                                "true_shooting_pct": "TS%",
                                "win_pct": "Win%",
                            }),
                            hide_index=True,
                            use_container_width=True,
                            height=380,
                        )
                    else:
                        st.info("No split data available.")

            with col_gamelog:
                with st.container(border=True):
                    st.markdown("#### 📋 Complete Box Game Logs")
                    st.caption("Sort by any column header (e.g. click FTM, STL, or BLK to sort highest to lowest).")

                    log_cols = [
                        "game_date", "matchup", "wl", "minutes_played",
                        "points", "rebounds", "assists", "steals", "blocks", "turnovers",
                        "ftm", "fta", "fg3_m", "fg3_a", "fgm", "fga",
                        "true_shooting_pct", "scoring_surge_differential"
                    ]
                    available_log_cols = [c for c in log_cols if c in df_p_games.columns]

                    st.dataframe(
                        df_p_games[available_log_cols].rename(columns={
                            "game_date": "Date",
                            "matchup": "Matchup",
                            "wl": "W/L",
                            "minutes_played": "MIN",
                            "points": "PTS",
                            "rebounds": "REB",
                            "assists": "AST",
                            "steals": "STL",
                            "blocks": "BLK",
                            "turnovers": "TOV",
                            "ftm": "FTM",
                            "fta": "FTA",
                            "fg3_m": "3PM",
                            "fg3_a": "3PA",
                            "fgm": "FGM",
                            "fga": "FGA",
                            "true_shooting_pct": "TS%",
                            "scoring_surge_differential": "+/- Trend",
                        }),
                        hide_index=True,
                        use_container_width=True,
                        height=380,
                    )
    else:
        st.warning("No player records found. Make sure the API service is active.")

# ---------------------------------------------------------
# TAB 4: SURGE TRACKER
# ---------------------------------------------------------
with tab_surges:
    st.markdown("### 🔥 Hot & Cold Scoring Surge Tracker")
    limit_val = st.slider("Display Count", min_value=5, max_value=25, value=12)

    surge_data = fetch_api_data("/analytics/surging-players", params={"season": selected_season, "limit": limit_val})
    if surge_data:
        df_surge = pd.DataFrame(surge_data)
        for col in ["rolling_10_pts_avg", "scoring_surge_differential"]:
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