-- Initialize TimescaleDB Extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 1. Odds Ticks Hypertable (Store raw bookmaker quote changes)
CREATE TABLE IF NOT EXISTS odds_ticks (
    timestamp TIMESTAMPTZ NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    player_id VARCHAR(64) NOT NULL,
    player_name VARCHAR(128) NOT NULL,
    stat_type VARCHAR(32) NOT NULL, -- e.g., 'points', 'rebounds', 'assists'
    bookmaker VARCHAR(64) NOT NULL, -- e.g., 'draftkings', 'pinnacle', 'fanduel'
    line NUMERIC(5, 2) NOT NULL, -- e.g., 24.5
    over_price NUMERIC(6, 2) NOT NULL, -- American or Decimal odds
    under_price NUMERIC(6, 2) NOT NULL,
    implied_over_prob NUMERIC(6, 4),
    implied_under_prob NUMERIC(6, 4)
);

SELECT create_hypertable('odds_ticks', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_odds_ticks_lookup ON odds_ticks (game_id, player_id, stat_type, bookmaker, timestamp DESC);

-- 2. Play-by-Play Events Table (Store raw gamestate updates)
CREATE TABLE IF NOT EXISTS play_events (
    timestamp TIMESTAMPTZ NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    period INT NOT NULL,
    clock_seconds INT NOT NULL, -- Remaining seconds in quarter
    elapsed_total_seconds INT NOT NULL, -- Total elapsed game seconds
    player_id VARCHAR(64),
    event_type VARCHAR(64) NOT NULL, -- e.g., 'made_shot', 'missed_shot', 'foul', 'sub'
    points_scored INT DEFAULT 0,
    home_score INT NOT NULL,
    away_score INT NOT NULL,
    raw_payload JSONB
);

SELECT create_hypertable('play_events', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_play_events_game ON play_events (game_id, timestamp DESC);

-- 3. Model Pricings Table (Store internal true probability calculations)
CREATE TABLE IF NOT EXISTS model_pricings (
    timestamp TIMESTAMPTZ NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    player_id VARCHAR(64) NOT NULL,
    stat_type VARCHAR(32) NOT NULL,
    target_line NUMERIC(5, 2) NOT NULL,
    current_stat_tally INT NOT NULL,
    remaining_seconds INT NOT NULL,
    lambda_rem NUMERIC(8, 4) NOT NULL,
    true_over_prob NUMERIC(6, 4) NOT NULL,
    true_under_prob NUMERIC(6, 4) NOT NULL,
    fair_over_decimal NUMERIC(8, 3) NOT NULL,
    fair_under_decimal NUMERIC(8, 3) NOT NULL
);

SELECT create_hypertable('model_pricings', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_model_pricings_lookup ON model_pricings (game_id, player_id, stat_type, timestamp DESC);

-- 4. Trade Signals Table (Log detected +EV opportunities and wager sizes)
CREATE TABLE IF NOT EXISTS trade_signals (
    timestamp TIMESTAMPTZ NOT NULL,
    signal_id VARCHAR(64) NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    player_id VARCHAR(64) NOT NULL,
    player_name VARCHAR(128) NOT NULL,
    stat_type VARCHAR(32) NOT NULL, -- 'points', 'rebounds', 'assists'
    side VARCHAR(8) NOT NULL, -- 'OVER' or 'UNDER'
    line NUMERIC(5, 2) NOT NULL,
    bookmaker VARCHAR(64) NOT NULL,
    bookmaker_odds NUMERIC(6, 2) NOT NULL,
    fair_odds NUMERIC(6, 2) NOT NULL,
    ev_percent NUMERIC(6, 4) NOT NULL, -- e.g., 0.0521 for 5.21%
    kelly_fraction NUMERIC(6, 4) NOT NULL,
    recommended_wager NUMERIC(10, 2) NOT NULL,
    consensus_fair_prob NUMERIC(6, 4) NOT NULL,
    status VARCHAR(32) DEFAULT 'LOGGED',
    PRIMARY KEY (signal_id, timestamp)
);

SELECT create_hypertable('trade_signals', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_trade_signals_ev ON trade_signals (timestamp DESC, ev_percent DESC);
