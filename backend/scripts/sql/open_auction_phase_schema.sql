PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS atomic_open_auction_phase_l1_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    auction_price REAL NULL,
    auction_match_volume REAL NULL,
    auction_match_amount REAL NULL,
    phase_0915_0920_trade_count INTEGER NULL,
    phase_0915_0920_trade_amount REAL NULL,
    phase_0920_0925_trade_count INTEGER NULL,
    phase_0920_0925_trade_amount REAL NULL,
    phase_0925_match_trade_count INTEGER NULL,
    phase_0925_match_trade_amount REAL NULL,
    phase_0915_0920_quote_row_count INTEGER NULL,
    phase_0920_0925_quote_row_count INTEGER NULL,
    phase_0925_has_snapshot INTEGER NULL,
    phase_strength_shift_label TEXT NULL,
    quality_info TEXT NULL,
    source_type TEXT NOT NULL DEFAULT 'l1_visible_phase',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_open_auction_phase_l1_daily_trade_date_symbol
ON atomic_open_auction_phase_l1_daily(trade_date, symbol);

CREATE TABLE IF NOT EXISTS atomic_open_auction_phase_l2_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    auction_trade_count_total INTEGER NULL,
    auction_trade_amount_total REAL NULL,
    phase_0915_0920_trade_count INTEGER NULL,
    phase_0915_0920_trade_amount REAL NULL,
    phase_0920_0925_trade_count INTEGER NULL,
    phase_0920_0925_trade_amount REAL NULL,
    phase_0925_match_trade_count INTEGER NULL,
    phase_0925_match_trade_amount REAL NULL,
    phase_0915_0920_add_buy_amount REAL NULL,
    phase_0915_0920_add_sell_amount REAL NULL,
    phase_0915_0920_cancel_buy_amount REAL NULL,
    phase_0915_0920_cancel_sell_amount REAL NULL,
    phase_0920_0925_add_buy_amount REAL NULL,
    phase_0920_0925_add_sell_amount REAL NULL,
    phase_0920_0925_cancel_buy_amount REAL NULL,
    phase_0920_0925_cancel_sell_amount REAL NULL,
    phase_buy_strength_shift TEXT NULL,
    phase_sell_pressure_shift TEXT NULL,
    has_exact_0925_trade INTEGER NULL,
    has_exact_0925_order INTEGER NULL,
    quality_info TEXT NULL,
    source_type TEXT NOT NULL DEFAULT 'l2_postclose_phase',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_open_auction_phase_l2_daily_trade_date_symbol
ON atomic_open_auction_phase_l2_daily(trade_date, symbol);
