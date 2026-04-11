PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS atomic_open_auction_l1_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    auction_price REAL NULL,
    auction_match_volume REAL NULL,
    auction_match_amount REAL NULL,
    auction_price_change_pct_vs_prev_close REAL NULL,
    auction_trade_count_total INTEGER NULL,
    auction_trade_volume_total REAL NULL,
    auction_trade_amount_total REAL NULL,
    auction_trade_count_0915_0920 INTEGER NULL,
    auction_trade_count_0920_0925 INTEGER NULL,
    auction_trade_count_0925_match INTEGER NULL,
    auction_trade_amount_0915_0920 REAL NULL,
    auction_trade_amount_0920_0925 REAL NULL,
    auction_trade_amount_0925_match REAL NULL,
    auction_first_trade_time TEXT NULL,
    auction_last_trade_time TEXT NULL,
    auction_exact_0925_trade_count INTEGER NULL,
    quote_preopen_row_count INTEGER NULL,
    quote_has_0925_snapshot INTEGER NULL,
    quality_info TEXT NULL,
    source_type TEXT NOT NULL DEFAULT 'l1_visible',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_open_auction_l1_daily_trade_date_symbol
ON atomic_open_auction_l1_daily(trade_date, symbol);

CREATE TABLE IF NOT EXISTS atomic_open_auction_l2_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    auction_trade_count_total INTEGER NULL,
    auction_trade_volume_total REAL NULL,
    auction_trade_amount_total REAL NULL,
    auction_trade_count_0915_0920 INTEGER NULL,
    auction_trade_count_0920_0925 INTEGER NULL,
    auction_trade_count_0925_match INTEGER NULL,
    auction_trade_amount_0915_0920 REAL NULL,
    auction_trade_amount_0920_0925 REAL NULL,
    auction_trade_amount_0925_match REAL NULL,
    auction_order_add_buy_amount REAL NULL,
    auction_order_add_sell_amount REAL NULL,
    auction_order_cancel_buy_amount REAL NULL,
    auction_order_cancel_sell_amount REAL NULL,
    auction_order_add_buy_count INTEGER NULL,
    auction_order_add_sell_count INTEGER NULL,
    auction_order_cancel_buy_count INTEGER NULL,
    auction_order_cancel_sell_count INTEGER NULL,
    auction_order_add_buy_amount_0915_0920 REAL NULL,
    auction_order_add_buy_amount_0920_0925 REAL NULL,
    auction_order_add_sell_amount_0915_0920 REAL NULL,
    auction_order_add_sell_amount_0920_0925 REAL NULL,
    auction_order_cancel_buy_amount_0915_0920 REAL NULL,
    auction_order_cancel_sell_amount_0915_0920 REAL NULL,
    auction_has_exact_0925_trade INTEGER NULL,
    auction_has_exact_0925_order INTEGER NULL,
    quality_info TEXT NULL,
    source_type TEXT NOT NULL DEFAULT 'l2_postclose',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_open_auction_l2_daily_trade_date_symbol
ON atomic_open_auction_l2_daily(trade_date, symbol);

CREATE TABLE IF NOT EXISTS atomic_open_auction_manifest (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    has_l1_auction INTEGER NOT NULL DEFAULT 0,
    has_l2_auction INTEGER NOT NULL DEFAULT 0,
    l1_quality_info TEXT NULL,
    l2_quality_info TEXT NULL,
    auction_shape TEXT NULL,
    parser_version TEXT NULL,
    generated_at TEXT NULL,
    notes TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_open_auction_manifest_trade_date_symbol
ON atomic_open_auction_manifest(trade_date, symbol);
