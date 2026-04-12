PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS cfg_limit_rule_map (
    board_type TEXT NOT NULL,
    risk_flag_type TEXT NOT NULL,
    limit_pct REAL NOT NULL,
    tick_size REAL NOT NULL DEFAULT 0.01,
    effective_from TEXT NOT NULL,
    effective_to TEXT NULL,
    note TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (board_type, risk_flag_type, effective_from)
);

CREATE TABLE IF NOT EXISTS atomic_limit_state_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    board_type TEXT NOT NULL,
    risk_flag_type TEXT NOT NULL,
    prev_close REAL NULL,
    up_limit_price REAL NULL,
    down_limit_price REAL NULL,
    limit_pct REAL NULL,
    tick_size REAL NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    touch_limit_up INTEGER NOT NULL DEFAULT 0,
    touch_limit_down INTEGER NOT NULL DEFAULT 0,
    is_limit_up_close INTEGER NOT NULL DEFAULT 0,
    is_limit_down_close INTEGER NOT NULL DEFAULT 0,
    touch_limit_up_count_5m INTEGER NULL,
    touch_limit_down_count_5m INTEGER NULL,
    first_touch_limit_up_time TEXT NULL,
    last_touch_limit_up_time TEXT NULL,
    first_touch_limit_down_time TEXT NULL,
    last_touch_limit_down_time TEXT NULL,
    broken_limit_up INTEGER NOT NULL DEFAULT 0,
    broken_limit_down INTEGER NOT NULL DEFAULT 0,
    limit_state_label TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'trade_limit_state',
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_limit_state_daily_trade_date_symbol
ON atomic_limit_state_daily(trade_date, symbol);

CREATE TABLE IF NOT EXISTS atomic_limit_state_5m (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    board_type TEXT NOT NULL,
    risk_flag_type TEXT NOT NULL,
    prev_close REAL NULL,
    up_limit_price REAL NULL,
    down_limit_price REAL NULL,
    limit_pct REAL NULL,
    tick_size REAL NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    touch_limit_up INTEGER NOT NULL DEFAULT 0,
    touch_limit_down INTEGER NOT NULL DEFAULT 0,
    is_limit_up_close_5m INTEGER NOT NULL DEFAULT 0,
    is_limit_down_close_5m INTEGER NOT NULL DEFAULT 0,
    near_limit_up_ratio REAL NULL,
    near_limit_down_ratio REAL NULL,
    state_label_5m TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'trade_limit_state',
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_atomic_limit_state_5m_trade_date_symbol
ON atomic_limit_state_5m(trade_date, symbol);

CREATE INDEX IF NOT EXISTS idx_atomic_limit_state_5m_time_symbol
ON atomic_limit_state_5m(bucket_start, symbol);
