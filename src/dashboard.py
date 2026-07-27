import asyncio
import streamlit as st
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from src.models.domain import StatType, PlayerGameState, Bookmaker
from src.pricing.poisson_pricer import PoissonPricer
from src.pricing.vig_stripper import VigStripper
from src.execution.ev_evaluator import EVEvaluator
from src.execution.kelly_sizer import KellyRiskManager
from src.ingestion.game_finder import GameDiscoveryService

st.set_page_config(
    page_title="Prop Engine — Live Basketball Signal Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# DESIGN SYSTEM — Deep Navy / Blue Accent / Bloomberg-Terminal Style
# =============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ── Root Theme ────────────────────────────────────────────────── */
    :root {
        --bg-primary:    #0b1120;
        --bg-secondary:  #111827;
        --bg-card:       #151d2e;
        --bg-card-hover: #1a2540;
        --border:        #1e2d4a;
        --border-active: #2563eb;
        --text-primary:  #e2e8f0;
        --text-secondary:#8896ab;
        --text-muted:    #5a6a80;
        --accent:        #3b82f6;
        --accent-glow:   rgba(59, 130, 246, 0.15);
        --green:         #22c55e;
        --green-dim:     rgba(34, 197, 94, 0.12);
        --red:           #ef4444;
        --red-dim:       rgba(239, 68, 68, 0.12);
        --amber:         #f59e0b;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* ── Sidebar Styling ───────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: var(--bg-secondary) !important;
        border-right: 1px solid var(--border) !important;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em;
    }

    /* ── Metric Cards (Glassmorphism Terminal) ──────────────────── */
    div[data-testid="stMetric"] {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 18px 20px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    div[data-testid="stMetric"]:hover {
        border-color: var(--border-active);
        box-shadow: 0 0 20px var(--accent-glow);
    }

    div[data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    div[data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 1.55rem !important;
        font-weight: 700 !important;
    }

    /* ── Buttons ────────────────────────────────────────────────── */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        letter-spacing: 0.01em !important;
        transition: all 0.15s ease !important;
        border: 1px solid var(--border) !important;
    }

    .stButton > button[kind="primary"] {
        background: var(--accent) !important;
        border-color: var(--accent) !important;
        color: white !important;
        box-shadow: 0 0 16px var(--accent-glow) !important;
    }

    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 0 28px rgba(59, 130, 246, 0.35) !important;
        transform: translateY(-1px) !important;
    }

    .stButton > button[kind="secondary"] {
        background: var(--bg-card) !important;
        color: var(--text-secondary) !important;
    }

    .stButton > button[kind="secondary"]:hover {
        background: var(--bg-card-hover) !important;
        border-color: var(--accent) !important;
        color: var(--text-primary) !important;
    }

    /* ── Data Tables ───────────────────────────────────────────── */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        overflow: hidden;
    }

    /* ── Expander ──────────────────────────────────────────────── */
    .stExpander {
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }

    /* ── Game Card ──────────────────────────────────────────────── */
    .game-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 14px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
        cursor: default;
    }

    .game-card:hover {
        border-color: var(--border-active);
        box-shadow: 0 0 24px var(--accent-glow);
    }

    .game-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }

    .game-card-matchup {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.01em;
    }

    .game-card-meta {
        font-size: 0.82rem;
        color: var(--text-muted);
        font-family: 'JetBrains Mono', monospace;
        margin-top: 4px;
    }

    /* ── Status Badges ─────────────────────────────────────────── */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .badge-live {
        background: var(--red-dim);
        color: var(--red);
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .badge-live::before {
        content: '';
        display: inline-block;
        width: 6px;
        height: 6px;
        background: var(--red);
        border-radius: 50%;
        margin-right: 6px;
        animation: pulse-dot 1.5s infinite;
    }

    @keyframes pulse-dot {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }

    .badge-scheduled {
        background: rgba(59, 130, 246, 0.1);
        color: var(--accent);
        border: 1px solid rgba(59, 130, 246, 0.25);
    }

    /* ── Signal Alert Card ─────────────────────────────────────── */
    .signal-alert {
        background: var(--green-dim);
        border: 1px solid rgba(34, 197, 94, 0.3);
        border-left: 4px solid var(--green);
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 10px;
    }

    .signal-player {
        font-size: 1rem;
        font-weight: 700;
        color: var(--green);
    }

    .signal-info {
        font-size: 0.88rem;
        color: var(--text-secondary);
        margin-top: 4px;
        font-family: 'JetBrains Mono', monospace;
    }

    .signal-stake {
        display: inline-block;
        background: rgba(34, 197, 94, 0.15);
        color: var(--green);
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.9rem;
        padding: 4px 12px;
        border-radius: 4px;
        margin-top: 6px;
    }

    /* ── Section Headers ───────────────────────────────────────── */
    .section-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border);
    }

    /* ── Header Bar ────────────────────────────────────────────── */
    .header-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--border);
    }

    .header-title {
        font-size: 1.65rem;
        font-weight: 800;
        color: var(--text-primary);
        letter-spacing: -0.02em;
        margin: 0;
    }

    .header-subtitle {
        font-size: 0.88rem;
        color: var(--text-muted);
        font-weight: 400;
        margin-top: 2px;
    }

    /* ── Scheduled Roster Table ─────────────────────────────────── */
    .sched-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'Inter', sans-serif;
    }

    .sched-table th {
        text-align: left;
        padding: 10px 14px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--text-muted);
        font-family: 'JetBrains Mono', monospace;
        border-bottom: 1px solid var(--border);
    }

    .sched-table td {
        padding: 12px 14px;
        font-size: 0.9rem;
        color: var(--text-secondary);
        border-bottom: 1px solid rgba(30, 45, 74, 0.5);
    }

    .sched-table tr:hover td {
        color: var(--text-primary);
        background: var(--bg-card);
    }

    /* ── No-Signal State ───────────────────────────────────────── */
    .no-signal {
        background: var(--bg-card);
        border: 1px dashed var(--border);
        border-radius: 8px;
        padding: 24px;
        text-align: center;
        color: var(--text-muted);
        font-size: 0.9rem;
    }

    /* ── Clickable Game Card States ─────────────────────────────── */
    .game-card-selected {
        background: var(--bg-card);
        border: 1px solid var(--border-active) !important;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 14px;
        box-shadow: 0 0 20px var(--accent-glow);
        position: relative;
    }

    .game-card-selected .game-card-header::after {
        content: '✓';
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        background: var(--accent);
        color: white;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
        margin-left: 10px;
        flex-shrink: 0;
    }

    .game-card-unselected {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 14px;
        opacity: 0.7;
        transition: opacity 0.15s ease, border-color 0.15s ease;
    }

    .game-card-unselected:hover {
        opacity: 1;
        border-color: rgba(59, 130, 246, 0.4);
    }

    /* ── Player Chip Grid ──────────────────────────────────────── */
    .team-group-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-muted);
        margin-top: 16px;
        margin-bottom: 8px;
    }

    .chip-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# SESSION STATE
# =============================================================================
if "page" not in st.session_state:
    st.session_state.page = "selection"
if "selected_league" not in st.session_state:
    st.session_state.selected_league = "nba"
if "tracked_configs" not in st.session_state:
    st.session_state.tracked_configs = []
if "selected_game_id" not in st.session_state:
    st.session_state.selected_game_id = None

# =============================================================================
# SCREEN 1 — GAME & PLAYER DISCOVERY
# =============================================================================
if st.session_state.page == "selection":

    # Header
    st.markdown("""
        <div class="header-bar">
            <div>
                <h1 class="header-title">Prop Engine</h1>
                <div class="header-subtitle">Live game discovery and roster selection</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # League selector in sidebar
    st.sidebar.markdown('<div class="section-label">Configuration</div>', unsafe_allow_html=True)
    league_choice = st.sidebar.selectbox(
        "League",
        ["NBA", "WNBA"],
        index=0 if st.session_state.selected_league == "nba" else 1,
        help="Select the target professional basketball league.",
    )
    league = league_choice.lower()
    st.session_state.selected_league = league

    # Discover games
    st.markdown('<div class="section-label">Available Games (Select One)</div>', unsafe_allow_html=True)

    with st.spinner(f"Scanning {league_choice} live feeds..."):
        discovery_service = GameDiscoveryService()
        try:
            live_games = asyncio.run(discovery_service.discover_live_games(league))
        except Exception:
            live_games = []

    user_selections = []

    if live_games:
        for g in live_games:
            gid = g.game_id
            is_live = g.status == "IN_PROGRESS"
            if is_live:
                status_html = '<span class="badge badge-live">Live</span>'
                meta = f"Period {g.period} &mdash; {g.clock_display}"
            else:
                status_html = '<span class="badge badge-scheduled">Scheduled</span>'
                meta = g.scheduled_chicago_display or "Time TBD"

            is_selected = (st.session_state.selected_game_id == gid)
            card_class = "game-card-selected" if is_selected else "game-card-unselected"

            # Render game card tile
            st.markdown(f"""
                <div class="{card_class}" style="margin-bottom: 8px;">
                    <div class="game-card-header">
                        <span class="game-card-matchup">{g.away_team}  <span style="color: var(--text-muted); font-weight: 400;">@</span>  {g.home_team}</span>
                        {status_html}
                    </div>
                    <div class="game-card-meta">{meta}</div>
                </div>
            """, unsafe_allow_html=True)

            # Full-width select button matching card length
            btn_label = "Selected (Click to Deselect)" if is_selected else f"Select {g.away_team} @ {g.home_team}"
            if st.button(btn_label, key=f"select_btn_{gid}", type="secondary" if is_selected else "primary", width="stretch"):
                if is_selected:
                    st.session_state.selected_game_id = None
                else:
                    st.session_state.selected_game_id = gid
                st.rerun()

            # Put players directly below the selected game card
            if is_selected:
                st.markdown('<div class="section-label" style="margin-top: 12px;">Active Roster Selection</div>', unsafe_allow_html=True)
                matchup_label = f"{g.away_team} vs {g.home_team}"
                espn_id = g.espn_game_id or (gid.split("_")[-1] if "_" in gid else gid)
                try:
                    roster_by_team = asyncio.run(discovery_service.fetch_game_roster_by_team(espn_id, league))
                except Exception:
                    roster_by_team = {}

                sel_roster = []
                if roster_by_team:
                    for team_name, players in roster_by_team.items():
                        if not players:
                            continue
                        st.markdown(f'<div class="team-group-label">{team_name}</div>', unsafe_allow_html=True)
                        cols = st.columns(5)
                        for i, pname in enumerate(sorted(players)):
                            with cols[i % 5]:
                                if st.checkbox(pname, key=f"player_{gid}_{pname}", value=False):
                                    sel_roster.append({"name": pname, "team": team_name})
                else:
                    st.markdown(f"""
                        <div class="no-signal" style="font-size: 0.82rem;">
                            Roster not available yet for {matchup_label}.
                        </div>
                    """, unsafe_allow_html=True)

                user_selections.append({
                    "game_id": gid,
                    "game_title": matchup_label,
                    "odds_api_id": g.odds_api_id,
                    "espn_game_id": espn_id,
                    "status": g.status,
                    "chicago_time": g.scheduled_chicago_display,
                    "players": sel_roster,
                })
                st.markdown("<br>", unsafe_allow_html=True)

        asyncio.run(discovery_service.close())
    else:
        st.markdown(f"""
            <div class="no-signal">
                No active or scheduled {league_choice} games found on live feeds.
            </div>
        """, unsafe_allow_html=True)

    # Launch button
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("Launch Monitor", type="primary", width="stretch", help="Open the live pricing and signal dashboard for your selected game and players."):
            if any(cfg["players"] for cfg in user_selections):
                st.session_state.tracked_configs = user_selections
                st.session_state.page = "dashboard"
                st.rerun()
            else:
                st.error("Select at least one player to continue.")

# =============================================================================
# SCREEN 2 — LIVE MONITOR & SIGNALS
# =============================================================================
elif st.session_state.page == "dashboard":

    # Header
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.markdown("""
            <div>
                <h1 class="header-title">Live Signal Monitor</h1>
                <div class="header-subtitle">Real-time prop pricing and execution signals</div>
            </div>
        """, unsafe_allow_html=True)
    with col_h2:
        st.write("")
        if st.button("Back to Discovery", type="secondary", width="stretch", help="Return to game and player selection."):
            st.session_state.page = "selection"
            st.rerun()

    # Guide
    with st.expander("How to read this dashboard", expanded=False):
        st.markdown("""
        **Model Win %** — Our statistical model's calculated probability that a player hits the Over on their prop line, based on their scoring rate, game clock, and foul situation.

        **Sharp Market %** — The consensus true probability implied by the sharpest sportsbooks (Pinnacle, Circa). These books have the tightest, most accurate lines.

        **+EV Signal** — Triggered when a retail sportsbook (DraftKings, FanDuel, etc.) offers odds significantly higher than the true fair price. This is where the mathematical edge exists.

        **Suggested Bet** — The exact dollar amount calculated by the risk manager based on your account balance and safety setting to maximize long-term growth while protecting your money.
        """)

    # Sidebar controls
    st.sidebar.markdown('<div class="section-label">Risk Controls</div>', unsafe_allow_html=True)
    league = st.session_state.selected_league
    min_ev = st.sidebar.slider(
        "Min Profit Edge (EV %)",
        1.0, 10.0, 3.0, 0.5,
        help="Minimum profit advantage required before you get an alert. Higher = fewer but stronger signals.",
    ) / 100.0
    kelly_frac = st.sidebar.selectbox(
        "Bet Sizing Safety",
        [0.125, 0.25, 0.50, 1.0],
        index=0,
        format_func=lambda x: {0.125: "Very Safe (recommended)", 0.25: "Moderate", 0.50: "Aggressive", 1.0: "High Risk"}[x],
        help="How cautiously the app sizes your bets. 'Very Safe' uses a small fraction of your account per bet to protect against losing streaks.",
    )
    bankroll = st.sidebar.number_input(
        "Account Balance ($)",
        min_value=100, value=10000, step=500,
        help="Total money in your sportsbook account. The app calculates each bet as a safe percentage of this total.",
    )

    reg_mins = 40.0 if league == "wnba" else 48.0
    max_fouls = 5 if league == "wnba" else 6

    # Build player list
    all_player_items = []
    for cfg in st.session_state.tracked_configs:
        for pitem in cfg["players"]:
            if isinstance(pitem, dict):
                pname = pitem.get("name", "")
                pteam = pitem.get("team", "Unassigned")
            else:
                pname = str(pitem)
                pteam = "Unassigned"

            all_player_items.append({
                "game_id": cfg["game_id"],
                "game_title": cfg["game_title"],
                "odds_api_id": cfg["odds_api_id"],
                "status": cfg["status"],
                "chicago_time": cfg["chicago_time"],
                "player_name": pname,
                "team": pteam,
            })

    if not all_player_items:
        st.warning("No players selected.")
        st.session_state.page = "selection"
        st.rerun()

    # KPI strip
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Games", len(st.session_state.tracked_configs), help="Number of games being monitored.")
    with k2:
        st.metric("Players", len(all_player_items), help="Number of player props being priced.")
    with k3:
        st.metric("League", league.upper(), help="Active league.")
    with k4:
        st.metric("Min Edge", f"{min_ev * 100:.1f}%", help="Current minimum EV threshold for signal alerts.")

    st.markdown("<br>", unsafe_allow_html=True)

    # Split by status
    live_items = [item for item in all_player_items if item["status"] == "IN_PROGRESS"]
    scheduled_items = [item for item in all_player_items if item["status"] != "IN_PROGRESS"]

    # ── SCHEDULED SECTION ──
    if scheduled_items:
        st.markdown('<div class="section-label">Scheduled — Awaiting Tip-Off</div>', unsafe_allow_html=True)
        sched_rows = []
        for item in scheduled_items:
            sched_rows.append({
                "Team": item["team"],
                "Player": item["player_name"],
                "Matchup": item["game_title"],
                "Tip-Off (Chicago)": item["chicago_time"] or "TBD",
                "Status": "Pending",
            })
        df_sched = pd.DataFrame(sched_rows).sort_values(by=["Team", "Player"])
        st.dataframe(df_sched, width="stretch", hide_index=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
            <div class="no-signal" style="font-size: 0.82rem;">
                Live pricing and trade signals will activate automatically once these games tip off.
            </div>
        """, unsafe_allow_html=True)

    # ── LIVE SECTION ──
    if live_items:
        st.markdown('<div class="section-label">Live — Active Pricing</div>', unsafe_allow_html=True)

        calculated_results = []
        for item in live_items:
            pname = item["player_name"]
            pteam = item["team"]
            gid = item["game_id"]

            pstate = PlayerGameState(
                game_id=gid,
                player_id=f"player_{pname.lower().replace(' ', '_')}",
                player_name=pname,
                projected_total_minutes=32.0,
                elapsed_minutes_played=0.0,
                accumulated_stats={StatType.POINTS: 0},
                fouls=0,
                base_rate_per_minute={StatType.POINTS: 0.65},
            )

            rem_sec = 2160 if league == "nba" else 1800
            line = 20.5
            pricing = PoissonPricer.price_player_prop(
                player_state=pstate,
                stat_type=StatType.POINTS,
                target_line=line,
                remaining_regulation_seconds=rem_sec,
                period=1,
                regulation_minutes=reg_mins,
                max_fouls=max_fouls,
            )

            sharp_over_price = 1.90
            sharp_under_price = 1.90
            sharp_over_fair, sharp_under_fair = VigStripper.power_dejuice(sharp_over_price, sharp_under_price)

            ev_eval = EVEvaluator(min_ev_threshold=min_ev)
            risk_mgr = KellyRiskManager(bankroll=bankroll, kelly_fraction=kelly_frac)

            dk_tick = type("Tick", (), {
                "game_id": gid,
                "player_id": pstate.player_id,
                "line": line,
                "bookmaker": "DraftKings",
                "over_price": 1.90,
                "under_price": 1.90,
            })()

            signal = ev_eval.evaluate_quote(
                pricing=pricing,
                quote=dk_tick,
                consensus_fair_over_prob=sharp_over_fair,
                consensus_fair_under_prob=sharp_under_fair,
                player_name=pname,
            )

            if signal:
                signal = risk_mgr.calculate_wager_size(signal, win_prob=pricing.true_over_prob)

            calculated_results.append({
                "Team": pteam,
                "Player": pname,
                "Matchup": item["game_title"],
                "Line": line,
                "Model Win %": f"{pricing.true_over_prob * 100:.1f}%",
                "Fair Odds": round(pricing.fair_over_decimal, 3),
                "Sharp Mkt %": f"{sharp_over_fair * 100:.1f}%",
                "Signal": f"{signal.bookmaker} {signal.side.value} @ {signal.bookmaker_odds}" if signal else "—",
                "Edge": f"{signal.ev_percent * 100:.2f}%" if signal else "—",
                "Bet": f"${signal.recommended_wager:.2f}" if signal else "—",
            })

        # Signal alerts
        active_signals = [r for r in calculated_results if r["Signal"] != "—"]
        if active_signals:
            st.markdown('<div class="section-label">Execution Signals</div>', unsafe_allow_html=True)
            for sig in active_signals:
                st.markdown(f"""
                    <div class="signal-alert">
                        <div class="signal-player">{sig['Player']}</div>
                        <div class="signal-info">{sig['Matchup']} &mdash; {sig['Signal']} &mdash; Edge: {sig['Edge']}</div>
                        <span class="signal-stake">Suggested: {sig['Bet']}</span>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="no-signal">
                    No profitable signals detected at current threshold. The monitor will alert you when an edge appears.
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Summary table
        st.markdown('<div class="section-label">Quantitative Summary</div>', unsafe_allow_html=True)
        df_live = pd.DataFrame(calculated_results).sort_values(by=["Team", "Player"])
        st.dataframe(df_live, width="stretch", hide_index=True)

    elif not scheduled_items:
        st.markdown("""
            <div class="no-signal">
                No games are being tracked. Use the back button above to select games and players.
            </div>
        """, unsafe_allow_html=True)
