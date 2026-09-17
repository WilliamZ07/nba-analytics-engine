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
    """Return high-resolution transparent PNG logo URL from ESPN CDN with NBA trico overrides."""
    espn_overrides = {
        "UTA": "utah",
        "GSW": "gs",
        "NOP": "no",
        "NYK": "ny",
        "SAS": "sa",
        "WAS": "wsh",
    }
    abbr_clean = team_abbrev.strip().upper() if team_abbrev else "NBA"
    slug = espn_overrides.get(abbr_clean, abbr_clean.lower())
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{slug}.png"


def get_player_headshot_url(player_id: int | str) -> str:
    """Return official NBA headshot URL."""
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"


@st.cache_data(ttl=300)
def fetch_api_data(endpoint: str, params: dict[str, Any] | None = None) -> Any:
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

tab_overview, tab_matchup, tab_players, tab_boxscore, tab_surges = st.tabs(
    [
        "📊 Team Efficiency Matrix",
        "⚔️ Matchup Tale of the Tape",
        "👤 Player Intelligence & Logs",
        "📋 Single-Game Box Score",
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
# TAB 2: HEAD-TO-HEAD TALE OF THE TAPE
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
        with card_a:
            with st.container(border=True):
                logo_col, text_col = st.columns([1, 3])
                with logo_col:
                    st.image(get_team_logo_url(team_a), width=100)
                with text_col:
                    st.markdown(f"## **{team_a}**")
                    st.markdown(f"**Record:** {int(t_a['wins'])}-{int(t_a['losses'])} &nbsp;|&nbsp; **Win %:** {t_a['win_percentage'] * 100:.1f}%")
                    st.markdown(f"**Adj Net Rating:** `{t_a['adjusted_net_rating']:+.2f}`")

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
# TAB 3: PLAYER INTELLIGENCE & LOGS
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

            with st.container(border=True):
                st.markdown("#### 📈 Game Scoring Performance vs. 10-Game Baseline")
                st.caption("Hover over any game for full box stats. Green = Boom (+5 pts), Red = Bust (-5 pts).")

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
                    st.caption("Sort by clicking any column header.")

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
# TAB 4: SINGLE-GAME BOX SCORE VIEWER
# ---------------------------------------------------------
with tab_boxscore:
    st.markdown("### 📋 Single-Game Box Score & Telemetry")
    st.caption("Full game analytics: composite possessions, pace, efficiency ratings, and player lines.")

    col_f_team, col_f_game = st.columns([1, 3])

    with col_f_team:
        team_options = ["ALL"] + sorted(df_ratings["team_abbreviation"].tolist()) if not df_ratings.empty else ["ALL"]
        filter_team = st.selectbox("Filter Games by Team", options=team_options, index=0)

    # Clean parameter construction: omit 'team' when filter is ALL
    game_query_params: dict[str, Any] = {"season": selected_season, "limit": 60}
    if filter_team != "ALL":
        game_query_params["team"] = filter_team

    games_list = fetch_api_data("/games", params=game_query_params)

    if not games_list:
        st.info("No games found for the selected season and filter.")
    else:
        game_options = {
            f"{g['game_date']} | {g['away_team']} ({int(g['away_score'])}) @ {g['home_team']} ({int(g['home_score'])})": g["game_id"]
            for g in games_list
        }

        with col_f_game:
            # Setting index=None leaves the dropdown unselected by default
            selected_game_label = st.selectbox(
                "Select Matchup",
                options=list(game_options.keys()),
                index=None,
                placeholder="Choose a game to inspect box score and player telemetry...",
            )

        # Default Empty State
        if not selected_game_label:
            with st.container(border=True):
                st.markdown(
                    """
                    <div style="text-align: center; padding: 40px 20px;">
                        <h3 style="color: #888;">🏀 No Game Selected</h3>
                        <p style="color: #666;">Choose a team filter and select a matchup from the dropdown above to load the box score, pace, and player performance.</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            selected_game_id = game_options[selected_game_label]
            box_data = fetch_api_data(f"/games/{selected_game_id}/boxscore")

            if box_data and "teams" in box_data and "players" in box_data:
                teams_meta = box_data["teams"]
                players_all = box_data["players"]

                away_t = next((t for t in teams_meta if t["location"] == "AWAY"), teams_meta[0])
                home_t = next((t for t in teams_meta if t["location"] == "HOME"), teams_meta[1] if len(teams_meta) > 1 else teams_meta[0])

                # 1. Mini Scoreboard Banner
                with st.container(border=True):
                    col_away_s, col_mid_s, col_home_s = st.columns([3, 2, 3])

                    with col_away_s:
                        c_logo, c_text = st.columns([1, 2])
                        with c_logo:
                            st.image(get_team_logo_url(away_t["team_abbreviation"]), width=85)
                        with c_text:
                            st.markdown(f"### **{away_t['team_abbreviation']}**")
                            wl_badge = "🏆 WINNER" if away_t["wl"] == "W" else "FINAL"
                            st.caption(f"{wl_badge} &nbsp;|&nbsp; Off Rtg: `{float(away_t.get('offensive_rating') or 0.0):.1f}`")
                            st.markdown(f"## **{int(away_t['points'])}**")

                    with col_mid_s:
                        st.markdown("<h4 style='text-align: center; color: #888; margin-top: 10px;'>FINAL</h4>", unsafe_allow_html=True)
                        st.markdown(f"<p style='text-align: center; margin: 0;'><b>{away_t['game_date']}</b></p>", unsafe_allow_html=True)
                        pace_val = float(home_t.get('pace') or away_t.get('pace') or 0.0)
                        poss_val = float(home_t.get('game_possessions') or away_t.get('game_possessions') or 0.0)
                        st.markdown(
                            f"<p style='text-align: center;'><span style='background: #2e3546; padding: 4px 10px; border-radius: 4px; font-size: 0.85rem;'>"
                            f"Pace: <b>{pace_val:.1f}</b> &nbsp;|&nbsp; Possessions: <b>{poss_val:.1f}</b></span></p>",
                            unsafe_allow_html=True,
                        )

                    with col_home_s:
                        c_text, c_logo = st.columns([2, 1])
                        with c_text:
                            st.markdown(f"<h3 style='text-align: right;'><b>{home_t['team_abbreviation']}</b></h3>", unsafe_allow_html=True)
                            wl_badge = "🏆 WINNER" if home_t["wl"] == "W" else "FINAL"
                            st.markdown(f"<p style='text-align: right; color: #888;'>Off Rtg: <code>{float(home_t.get('offensive_rating') or 0.0):.1f}</code> &nbsp;|&nbsp; {wl_badge}</p>", unsafe_allow_html=True)
                            st.markdown(f"<h2 style='text-align: right;'><b>{int(home_t['points'])}</b></h2>", unsafe_allow_html=True)
                        with c_logo:
                            st.image(get_team_logo_url(home_t["team_abbreviation"]), width=85)

                # 2. Team Comparative Shooting & Turnover Table
                with st.container(border=True):
                    st.markdown("#### Team Shooting & Turnover Totals")
                    team_comparison_rows = [
                        {
                            "Category": "Field Goals (FGM / FGA)",
                            away_t["team_abbreviation"]: f"{int(away_t['fgm'])}/{int(away_t['fga'])} ({float(away_t['fgm'])/max(float(away_t['fga']), 1.0)*100:.1f}%)",
                            home_t["team_abbreviation"]: f"{int(home_t['fgm'])}/{int(home_t['fga'])} ({float(home_t['fgm'])/max(float(home_t['fga']), 1.0)*100:.1f}%)",
                        },
                        {
                            "Category": "3-Pointers (3PM / 3PA)",
                            away_t["team_abbreviation"]: f"{int(away_t['fg3_m'])}/{int(away_t['fg3_a'])} ({float(away_t['fg3_m'])/max(float(away_t['fg3_a']), 1.0)*100:.1f}%)",
                            home_t["team_abbreviation"]: f"{int(home_t['fg3_m'])}/{int(home_t['fg3_a'])} ({float(home_t['fg3_m'])/max(float(home_t['fg3_a']), 1.0)*100:.1f}%)",
                        },
                        {
                            "Category": "Free Throws (FTM / FTA)",
                            away_t["team_abbreviation"]: f"{int(away_t['ftm'])}/{int(away_t['fta'])} ({float(away_t['ftm'])/max(float(away_t['fta']), 1.0)*100:.1f}%)",
                            home_t["team_abbreviation"]: f"{int(home_t['ftm'])}/{int(home_t['fta'])} ({float(home_t['ftm'])/max(float(home_t['fta']), 1.0)*100:.1f}%)",
                        },
                        {
                            "Category": "Rebounds / Assists",
                            away_t["team_abbreviation"]: f"{int(away_t['rebounds'])} REB / {int(away_t['assists'])} AST",
                            home_t["team_abbreviation"]: f"{int(home_t['rebounds'])} REB / {int(home_t['assists'])} AST",
                        },
                        {
                            "Category": "Steals / Blocks / Turnovers",
                            away_t["team_abbreviation"]: f"{int(away_t['steals'])} STL / {int(away_t['blocks'])} BLK / {int(away_t['turnovers'])} TOV",
                            home_t["team_abbreviation"]: f"{int(home_t['steals'])} STL / {int(home_t['blocks'])} BLK / {int(home_t['turnovers'])} TOV",
                        },
                    ]
                    st.dataframe(pd.DataFrame(team_comparison_rows), hide_index=True, use_container_width=True)

                # 3. Individual Player Box Scores
                df_players_all = pd.DataFrame(players_all)
                for c in ["points", "rebounds", "assists", "steals", "blocks", "turnovers", "minutes_played", "fgm", "fga", "fg3_m", "fg3_a", "ftm", "fta", "true_shooting_pct"]:
                    if c in df_players_all.columns:
                        df_players_all[c] = pd.to_numeric(df_players_all[c], errors="coerce").fillna(0.0)

                tab_away_roster, tab_home_roster = st.tabs(
                    [f"🏀 {away_t['team_abbreviation']} Box Score", f"🏀 {home_t['team_abbreviation']} Box Score"]
                )

                box_cols = ["player_name", "minutes_played", "points", "rebounds", "assists", "steals", "blocks", "turnovers", "fgm", "fga", "fg3_m", "fg3_a", "ftm", "fta", "true_shooting_pct"]

                with tab_away_roster:
                    df_away_players = df_players_all[df_players_all["team_abbreviation"] == away_t["team_abbreviation"]][box_cols]
                    st.dataframe(
                        df_away_players.rename(columns={
                            "player_name": "Player", "minutes_played": "MIN", "points": "PTS", "rebounds": "REB",
                            "assists": "AST", "steals": "STL", "blocks": "BLK", "turnovers": "TOV",
                            "fgm": "FGM", "fga": "FGA", "fg3_m": "3PM", "fg3_a": "3PA", "ftm": "FTM", "fta": "FTA",
                            "true_shooting_pct": "TS%"
                        }),
                        hide_index=True,
                        use_container_width=True,
                        height=380,
                    )

                with tab_home_roster:
                    df_home_players = df_players_all[df_players_all["team_abbreviation"] == home_t["team_abbreviation"]][box_cols]
                    st.dataframe(
                        df_home_players.rename(columns={
                            "player_name": "Player", "minutes_played": "MIN", "points": "PTS", "rebounds": "REB",
                            "assists": "AST", "steals": "STL", "blocks": "BLK", "turnovers": "TOV",
                            "fgm": "FGM", "fga": "FGA", "fg3_m": "3PM", "fg3_a": "3PA", "ftm": "FTM", "fta": "FTA",
                            "true_shooting_pct": "TS%"
                        }),
                        hide_index=True,
                        use_container_width=True,
                        height=380,
                    )

# ---------------------------------------------------------
# TAB 5: SURGE TRACKER
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