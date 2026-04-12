PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS atomic_book_state_5m (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    snapshot_time TEXT NULL,
    quote_row_count_5m INTEGER NULL,
    end_bid_resting_volume REAL NULL,
    end_ask_resting_volume REAL NULL,
    end_bid_resting_amount REAL NULL,
    end_ask_resting_amount REAL NULL,
    top1_bid_volume REAL NULL,
    top1_ask_volume REAL NULL,
    top5_bid_volume REAL NULL,
    top5_ask_volume REAL NULL,
    top1_bid_amount REAL NULL,
    top1_ask_amount REAL NULL,
    top5_bid_amount REAL NULL,
    top5_ask_amount REAL NULL,
    book_imbalance_ratio REAL NULL,
    book_depth_ratio REAL NULL,
    book_state_label TEXT NULL,
    source_type TEXT NOT NULL DEFAULT 'l2_quote_book_state',
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_atomic_book_state_5m_trade_date_symbol
ON atomic_book_state_5m(trade_date, symbol);

CREATE INDEX IF NOT EXISTS idx_atomic_book_state_5m_time_symbol
ON atomic_book_state_5m(bucket_start, symbol);

CREATE TABLE IF NOT EXISTS atomic_book_state_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    avg_bid_resting_amount REAL NULL,
    avg_ask_resting_amount REAL NULL,
    avg_book_imbalance_ratio REAL NULL,
    avg_book_depth_ratio REAL NULL,
    max_bid_resting_amount REAL NULL,
    max_ask_resting_amount REAL NULL,
    close_bid_resting_amount REAL NULL,
    close_ask_resting_amount REAL NULL,
    close_book_imbalance_ratio REAL NULL,
    close_book_depth_ratio REAL NULL,
    bid_dominant_bar_count INTEGER NULL,
    ask_dominant_bar_count INTEGER NULL,
    thin_book_bar_count INTEGER NULL,
    balanced_bar_count INTEGER NULL,
    valid_bucket_count INTEGER NULL,
    source_type TEXT NOT NULL DEFAULT 'l2_quote_book_state',
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_book_state_daily_trade_date_symbol
ON atomic_book_state_daily(trade_date, symbol);
