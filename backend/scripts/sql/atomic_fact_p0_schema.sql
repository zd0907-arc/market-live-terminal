PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS atomic_trade_5m (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    total_amount REAL NOT NULL,
    total_volume REAL NULL,
    trade_count INTEGER NULL,
    l1_main_buy_amount REAL NOT NULL,
    l1_main_sell_amount REAL NOT NULL,
    l1_main_net_amount REAL NOT NULL,
    l1_super_buy_amount REAL NOT NULL,
    l1_super_sell_amount REAL NOT NULL,
    l1_super_net_amount REAL NOT NULL,
    l2_main_buy_amount REAL NOT NULL,
    l2_main_sell_amount REAL NOT NULL,
    l2_main_net_amount REAL NOT NULL,
    l2_super_buy_amount REAL NOT NULL,
    l2_super_sell_amount REAL NOT NULL,
    l2_super_net_amount REAL NOT NULL,
    source_type TEXT NOT NULL,
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_atomic_trade_5m_trade_date
ON atomic_trade_5m(trade_date);

CREATE INDEX IF NOT EXISTS idx_atomic_trade_5m_symbol_trade_date
ON atomic_trade_5m(symbol, trade_date);

CREATE TABLE IF NOT EXISTS atomic_trade_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    total_amount REAL NOT NULL,
    total_volume REAL NULL,
    trade_count INTEGER NULL,
    l1_main_buy_amount REAL NOT NULL,
    l1_main_sell_amount REAL NOT NULL,
    l1_main_net_amount REAL NOT NULL,
    l1_super_buy_amount REAL NOT NULL,
    l1_super_sell_amount REAL NOT NULL,
    l1_super_net_amount REAL NOT NULL,
    l2_main_buy_amount REAL NOT NULL,
    l2_main_sell_amount REAL NOT NULL,
    l2_main_net_amount REAL NOT NULL,
    l2_super_buy_amount REAL NOT NULL,
    l2_super_sell_amount REAL NOT NULL,
    l2_super_net_amount REAL NOT NULL,
    l1_activity_ratio REAL NULL,
    l2_activity_ratio REAL NULL,
    l1_buy_ratio REAL NULL,
    l1_sell_ratio REAL NULL,
    l2_buy_ratio REAL NULL,
    l2_sell_ratio REAL NULL,
    am_l2_main_net_amount REAL NULL,
    pm_l2_main_net_amount REAL NULL,
    open_30m_l2_main_net_amount REAL NULL,
    last_30m_l2_main_net_amount REAL NULL,
    positive_l2_net_bar_count INTEGER NULL,
    negative_l2_net_bar_count INTEGER NULL,
    source_type TEXT NOT NULL,
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_trade_daily_trade_date
ON atomic_trade_daily(trade_date);

CREATE TABLE IF NOT EXISTS atomic_order_5m (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    add_buy_amount REAL NOT NULL,
    add_sell_amount REAL NOT NULL,
    cancel_buy_amount REAL NOT NULL,
    cancel_sell_amount REAL NOT NULL,
    cvd_delta_amount REAL NOT NULL,
    oib_delta_amount REAL NOT NULL,
    add_buy_count INTEGER NULL,
    add_sell_count INTEGER NULL,
    cancel_buy_count INTEGER NULL,
    cancel_sell_count INTEGER NULL,
    add_buy_volume REAL NULL,
    add_sell_volume REAL NULL,
    cancel_buy_volume REAL NULL,
    cancel_sell_volume REAL NULL,
    buy_add_cancel_net_amount REAL NOT NULL,
    sell_add_cancel_net_amount REAL NOT NULL,
    source_type TEXT NOT NULL,
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_atomic_order_5m_trade_date
ON atomic_order_5m(trade_date);

CREATE INDEX IF NOT EXISTS idx_atomic_order_5m_symbol_trade_date
ON atomic_order_5m(symbol, trade_date);

CREATE TABLE IF NOT EXISTS atomic_order_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    add_buy_amount REAL NOT NULL,
    add_sell_amount REAL NOT NULL,
    cancel_buy_amount REAL NOT NULL,
    cancel_sell_amount REAL NOT NULL,
    cvd_delta_amount REAL NOT NULL,
    oib_delta_amount REAL NOT NULL,
    add_buy_count INTEGER NULL,
    add_sell_count INTEGER NULL,
    cancel_buy_count INTEGER NULL,
    cancel_sell_count INTEGER NULL,
    am_oib_delta_amount REAL NULL,
    pm_oib_delta_amount REAL NULL,
    open_60m_oib_delta_amount REAL NULL,
    last_30m_oib_delta_amount REAL NULL,
    open_60m_cvd_delta_amount REAL NULL,
    last_30m_cvd_delta_amount REAL NULL,
    positive_oib_bar_count INTEGER NULL,
    negative_oib_bar_count INTEGER NULL,
    positive_cvd_bar_count INTEGER NULL,
    negative_cvd_bar_count INTEGER NULL,
    buy_support_ratio REAL NULL,
    sell_pressure_ratio REAL NULL,
    quality_info TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_atomic_order_daily_trade_date
ON atomic_order_daily(trade_date);

CREATE TABLE IF NOT EXISTS atomic_data_manifest (
    dataset_key TEXT NOT NULL,
    period_key TEXT NOT NULL,
    source_type TEXT NOT NULL,
    trade_day_count INTEGER NOT NULL,
    symbol_day_count INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    has_order_atomic INTEGER NOT NULL,
    quality_issue_count INTEGER NOT NULL,
    parser_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    notes TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dataset_key, period_key)
);

CREATE INDEX IF NOT EXISTS idx_atomic_data_manifest_period
ON atomic_data_manifest(period_key);
