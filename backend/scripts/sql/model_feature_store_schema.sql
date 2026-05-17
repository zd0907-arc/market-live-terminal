PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS model_feature_build_runs (
    run_id TEXT PRIMARY KEY,
    feature_version TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    status TEXT NOT NULL,
    source_atomic_db TEXT NOT NULL,
    source_selection_db TEXT NOT NULL,
    source_heat_db TEXT,
    source_market_db TEXT,
    git_commit TEXT,
    config_json TEXT NOT NULL,
    row_counts_json TEXT,
    validation_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_feature_build_runs_feature_version
ON model_feature_build_runs(feature_version);

CREATE INDEX IF NOT EXISTS idx_model_feature_build_runs_status_started_at
ON model_feature_build_runs(status, started_at);

CREATE INDEX IF NOT EXISTS idx_model_feature_build_runs_date_range
ON model_feature_build_runs(date_from, date_to);

CREATE TABLE IF NOT EXISTS model_feature_manifest (
    table_name TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    trade_day_count INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    symbol_count INTEGER,
    coverage_json TEXT NOT NULL,
    source_tables_json TEXT NOT NULL,
    run_id TEXT,
    generated_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (table_name, feature_version, date_from, date_to),
    FOREIGN KEY (run_id) REFERENCES model_feature_build_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_feature_manifest_table_version
ON model_feature_manifest(table_name, feature_version);

CREATE INDEX IF NOT EXISTS idx_model_feature_manifest_run_id
ON model_feature_manifest(run_id);

CREATE INDEX IF NOT EXISTS idx_model_feature_manifest_generated_at
ON model_feature_manifest(generated_at);

CREATE TABLE IF NOT EXISTS model_market_index_daily (
    index_code TEXT NOT NULL,
    index_name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    volume REAL,
    amount REAL,
    source TEXT NOT NULL,
    build_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (index_code, trade_date),
    FOREIGN KEY (build_run_id) REFERENCES model_feature_build_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_trade_date
ON model_market_index_daily(trade_date);

CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_name_trade_date
ON model_market_index_daily(index_name, trade_date);

CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_build_run_id
ON model_market_index_daily(build_run_id);

CREATE TABLE IF NOT EXISTS model_market_state_daily_v1 (
    trade_date TEXT PRIMARY KEY,
    feature_version TEXT NOT NULL,
    market_total_amount_yi REAL,
    market_total_amount_ma20_yi REAL,
    market_amount_ratio_20d REAL,
    market_mean_return_pct REAL,
    market_median_return_pct REAL,
    market_advancer_ratio REAL,
    market_decliner_ratio REAL,
    market_up_gt3_count INTEGER,
    market_down_lt_minus3_count INTEGER,
    limit_up_count INTEGER,
    limit_down_count INTEGER,
    touch_limit_up_count INTEGER,
    broken_limit_up_count INTEGER,
    sealed_limit_up_count INTEGER,
    broken_limit_up_ratio REAL,
    csi1000_close REAL,
    csi1000_ma20 REAL,
    csi1000_above_ma20 INTEGER CHECK (csi1000_above_ma20 IN (0, 1) OR csi1000_above_ma20 IS NULL),
    csi1000_dist_ma20_pct REAL,
    csi1000_ma20_slope_5d_pct REAL,
    csi1000_return_1d_pct REAL,
    csi1000_return_5d_pct REAL,
    csi1000_return_20d_pct REAL,
    csi500_above_ma20 INTEGER CHECK (csi500_above_ma20 IN (0, 1) OR csi500_above_ma20 IS NULL),
    hs300_above_ma20 INTEGER CHECK (hs300_above_ma20 IN (0, 1) OR hs300_above_ma20 IS NULL),
    sh_index_above_ma20 INTEGER CHECK (sh_index_above_ma20 IN (0, 1) OR sh_index_above_ma20 IS NULL),
    gem_index_above_ma20 INTEGER CHECK (gem_index_above_ma20 IN (0, 1) OR gem_index_above_ma20 IS NULL),
    hot_theme_top1_score REAL,
    hot_theme_top5_avg_score REAL,
    hot_theme_top10_amount_ratio REAL,
    hot_theme_top10_l2_net_yi REAL,
    hot_theme_new_count INTEGER,
    hot_theme_continuing_count INTEGER,
    hot_theme_climax_count INTEGER,
    hot_theme_fading_count INTEGER,
    hot_theme_concentration_top3 REAL,
    has_index_data INTEGER NOT NULL DEFAULT 0 CHECK (has_index_data IN (0, 1)),
    has_heat_data INTEGER NOT NULL DEFAULT 0 CHECK (has_heat_data IN (0, 1)),
    has_order_data INTEGER NOT NULL DEFAULT 0 CHECK (has_order_data IN (0, 1)),
    has_book_data INTEGER NOT NULL DEFAULT 0 CHECK (has_book_data IN (0, 1)),
    build_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (build_run_id) REFERENCES model_feature_build_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_market_state_daily_v1_feature_version_trade_date
ON model_market_state_daily_v1(feature_version, trade_date);

CREATE INDEX IF NOT EXISTS idx_model_market_state_daily_v1_build_run_id
ON model_market_state_daily_v1(build_run_id);

CREATE TABLE IF NOT EXISTS model_feature_daily_v1 (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    name TEXT,
    board_type TEXT,
    risk_flag_type TEXT,
    market_cap REAL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    prev_close REAL,
    return_1d_pct REAL,
    return_3d_pct REAL,
    return_5d_pct REAL,
    return_10d_pct REAL,
    return_20d_pct REAL,
    volatility_10d REAL,
    volatility_20d REAL,
    ma20 REAL,
    ma60 REAL,
    dist_ma20_pct REAL,
    dist_ma60_pct REAL,
    price_position_20d REAL,
    price_position_60d REAL,
    breakout_vs_prev20_high_pct REAL,
    drawdown_from_20d_high_pct REAL,
    amount_yi REAL,
    amount_ratio_20d REAL,
    trade_count INTEGER,
    trade_count_ratio_20d REAL,
    l1_main_net_yi REAL,
    l1_super_net_yi REAL,
    l2_main_net_yi REAL,
    l2_super_net_yi REAL,
    l1_main_net_ratio REAL,
    l1_super_net_ratio REAL,
    l2_main_net_ratio REAL,
    l2_super_net_ratio REAL,
    active_buy_strength REAL,
    open_30m_l2_main_net_ratio REAL,
    last_30m_l2_main_net_ratio REAL,
    am_l2_main_net_ratio REAL,
    pm_l2_main_net_ratio REAL,
    positive_l2_bar_ratio REAL,
    oib_delta_yi REAL,
    cvd_delta_yi REAL,
    oib_ratio REAL,
    cvd_ratio REAL,
    add_buy_ratio REAL,
    add_sell_ratio REAL,
    cancel_buy_ratio REAL,
    cancel_sell_ratio REAL,
    open_60m_oib_ratio REAL,
    last_30m_oib_ratio REAL,
    open_60m_cvd_ratio REAL,
    last_30m_cvd_ratio REAL,
    positive_oib_bar_ratio REAL,
    positive_cvd_bar_ratio REAL,
    positive_oib_streak_max INTEGER,
    oib_top3_concentration_ratio REAL,
    buy_support_ratio REAL,
    sell_pressure_ratio REAL,
    support_pressure_spread REAL,
    avg_book_imbalance_ratio REAL,
    close_book_imbalance_ratio REAL,
    avg_book_depth_ratio REAL,
    close_book_depth_ratio REAL,
    bid_dominant_bar_ratio REAL,
    ask_dominant_bar_ratio REAL,
    thin_book_bar_ratio REAL,
    close_bid_resting_amount_yi REAL,
    close_ask_resting_amount_yi REAL,
    close_bid_ask_amount_ratio REAL,
    touch_limit_up INTEGER CHECK (touch_limit_up IN (0, 1) OR touch_limit_up IS NULL),
    touch_limit_down INTEGER CHECK (touch_limit_down IN (0, 1) OR touch_limit_down IS NULL),
    is_limit_up_close INTEGER CHECK (is_limit_up_close IN (0, 1) OR is_limit_up_close IS NULL),
    is_limit_down_close INTEGER CHECK (is_limit_down_close IN (0, 1) OR is_limit_down_close IS NULL),
    broken_limit_up INTEGER CHECK (broken_limit_up IN (0, 1) OR broken_limit_up IS NULL),
    broken_limit_down INTEGER CHECK (broken_limit_down IN (0, 1) OR broken_limit_down IS NULL),
    limit_state_label TEXT,
    first_touch_limit_up_min INTEGER,
    last_touch_limit_up_min INTEGER,
    hot_theme_best_rank INTEGER,
    hot_theme_score REAL,
    hot_theme_persistence_score REAL,
    hot_theme_member_count INTEGER,
    hot_theme_is_top10 INTEGER CHECK (hot_theme_is_top10 IN (0, 1) OR hot_theme_is_top10 IS NULL),
    hot_theme_is_new_hot INTEGER CHECK (hot_theme_is_new_hot IN (0, 1) OR hot_theme_is_new_hot IS NULL),
    hot_theme_is_continuing_hot INTEGER CHECK (hot_theme_is_continuing_hot IN (0, 1) OR hot_theme_is_continuing_hot IS NULL),
    hot_theme_is_climax_hot INTEGER CHECK (hot_theme_is_climax_hot IN (0, 1) OR hot_theme_is_climax_hot IS NULL),
    hot_theme_is_fading INTEGER CHECK (hot_theme_is_fading IN (0, 1) OR hot_theme_is_fading IS NULL),
    hot_theme_l2_main_net_yi REAL,
    csi1000_above_ma20 INTEGER CHECK (csi1000_above_ma20 IN (0, 1) OR csi1000_above_ma20 IS NULL),
    csi1000_dist_ma20_pct REAL,
    market_advancer_ratio REAL,
    market_median_return_pct REAL,
    market_total_amount_yi REAL,
    market_amount_ratio_20d REAL,
    market_limit_up_count INTEGER,
    market_broken_limit_up_ratio REAL,
    hot_theme_concentration_top3 REAL,
    has_trade_daily INTEGER NOT NULL DEFAULT 0 CHECK (has_trade_daily IN (0, 1)),
    has_trade_5m INTEGER NOT NULL DEFAULT 0 CHECK (has_trade_5m IN (0, 1)),
    has_order_daily INTEGER NOT NULL DEFAULT 0 CHECK (has_order_daily IN (0, 1)),
    has_order_5m INTEGER NOT NULL DEFAULT 0 CHECK (has_order_5m IN (0, 1)),
    has_book_daily INTEGER NOT NULL DEFAULT 0 CHECK (has_book_daily IN (0, 1)),
    has_book_5m INTEGER NOT NULL DEFAULT 0 CHECK (has_book_5m IN (0, 1)),
    has_limit_daily INTEGER NOT NULL DEFAULT 0 CHECK (has_limit_daily IN (0, 1)),
    has_heat INTEGER NOT NULL DEFAULT 0 CHECK (has_heat IN (0, 1)),
    has_market_state INTEGER NOT NULL DEFAULT 0 CHECK (has_market_state IN (0, 1)),
    build_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date, feature_version),
    FOREIGN KEY (build_run_id) REFERENCES model_feature_build_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_feature_daily_v1_trade_date
ON model_feature_daily_v1(trade_date);

CREATE INDEX IF NOT EXISTS idx_model_feature_daily_v1_feature_version_trade_date
ON model_feature_daily_v1(feature_version, trade_date);

CREATE INDEX IF NOT EXISTS idx_model_feature_daily_v1_symbol_trade_date
ON model_feature_daily_v1(symbol, trade_date);

CREATE INDEX IF NOT EXISTS idx_model_feature_daily_v1_build_run_id
ON model_feature_daily_v1(build_run_id);

CREATE TABLE IF NOT EXISTS model_feature_intraday_shape_v1 (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    valid_bar_count INTEGER,
    missing_bar_count INTEGER,
    first_bar_time TEXT,
    last_bar_time TEXT,
    intraday_range_pct REAL,
    intraday_close_position REAL,
    high_time_min INTEGER,
    low_time_min INTEGER,
    high_before_1030 INTEGER CHECK (high_before_1030 IN (0, 1) OR high_before_1030 IS NULL),
    low_after_1430 INTEGER CHECK (low_after_1430 IN (0, 1) OR low_after_1430 IS NULL),
    open_5m_return_pct REAL,
    open_15m_return_pct REAL,
    open_30m_return_pct REAL,
    open_60m_return_pct REAL,
    open_15m_high_from_open_pct REAL,
    open_15m_low_from_open_pct REAL,
    open_30m_amount_ratio REAL,
    open_60m_amount_ratio REAL,
    open_15m_l2_main_net_ratio REAL,
    open_30m_l2_main_net_ratio REAL,
    open_60m_l2_main_net_ratio REAL,
    open_15m_l2_super_net_ratio REAL,
    open_15m_oib_ratio REAL,
    open_15m_cvd_ratio REAL,
    open_15m_book_imbalance_avg REAL,
    last_15m_return_pct REAL,
    last_30m_return_pct REAL,
    last_60m_return_pct REAL,
    last_30m_amount_ratio REAL,
    last_30m_l2_main_net_ratio REAL,
    last_30m_l2_super_net_ratio REAL,
    last_30m_oib_ratio REAL,
    last_30m_cvd_ratio REAL,
    last_30m_book_imbalance_avg REAL,
    l2_main_net_positive_bar_ratio REAL,
    l2_super_net_positive_bar_ratio REAL,
    oib_positive_bar_ratio REAL,
    cvd_positive_bar_ratio REAL,
    longest_l2_main_positive_streak INTEGER,
    longest_oib_positive_streak INTEGER,
    l2_main_net_curve_slope REAL,
    oib_curve_slope REAL,
    cvd_curve_slope REAL,
    front_loaded_l2_flow INTEGER CHECK (front_loaded_l2_flow IN (0, 1) OR front_loaded_l2_flow IS NULL),
    back_loaded_l2_flow INTEGER CHECK (back_loaded_l2_flow IN (0, 1) OR back_loaded_l2_flow IS NULL),
    late_day_reversal_up INTEGER CHECK (late_day_reversal_up IN (0, 1) OR late_day_reversal_up IS NULL),
    late_day_distribution INTEGER CHECK (late_day_distribution IN (0, 1) OR late_day_distribution IS NULL),
    has_order_5m INTEGER NOT NULL DEFAULT 0 CHECK (has_order_5m IN (0, 1)),
    has_book_5m INTEGER NOT NULL DEFAULT 0 CHECK (has_book_5m IN (0, 1)),
    build_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date, feature_version),
    FOREIGN KEY (build_run_id) REFERENCES model_feature_build_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_feature_intraday_shape_v1_trade_date
ON model_feature_intraday_shape_v1(trade_date);

CREATE INDEX IF NOT EXISTS idx_model_feature_intraday_shape_v1_feature_version_trade_date
ON model_feature_intraday_shape_v1(feature_version, trade_date);

CREATE INDEX IF NOT EXISTS idx_model_feature_intraday_shape_v1_build_run_id
ON model_feature_intraday_shape_v1(build_run_id);

CREATE TABLE IF NOT EXISTS model_label_forward_return_v1 (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    entry_date TEXT,
    label_end_date TEXT,
    label_complete_asof_date TEXT,
    horizon_days INTEGER NOT NULL CHECK (horizon_days IN (3, 5, 10, 22)),
    feature_version TEXT NOT NULL,
    signal_close REAL,
    entry_open REAL,
    entry_gap_pct REAL,
    entry_buyable INTEGER CHECK (entry_buyable IN (0, 1) OR entry_buyable IS NULL),
    entry_block_reason TEXT,
    max_high REAL,
    min_low REAL,
    exit_close REAL,
    max_runup_pct REAL,
    max_drawdown_pct REAL,
    close_return_pct REAL,
    hit_5pct INTEGER CHECK (hit_5pct IN (0, 1) OR hit_5pct IS NULL),
    hit_8pct INTEGER CHECK (hit_8pct IN (0, 1) OR hit_8pct IS NULL),
    hit_10pct INTEGER CHECK (hit_10pct IN (0, 1) OR hit_10pct IS NULL),
    hit_15pct INTEGER CHECK (hit_15pct IN (0, 1) OR hit_15pct IS NULL),
    hit_20pct INTEGER CHECK (hit_20pct IN (0, 1) OR hit_20pct IS NULL),
    first_hit_8pct_day INTEGER,
    first_hit_15pct_day INTEGER,
    worst_before_first_hit_15pct REAL,
    build_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, trade_date, horizon_days, feature_version),
    FOREIGN KEY (build_run_id) REFERENCES model_feature_build_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_label_forward_return_v1_trade_date
ON model_label_forward_return_v1(trade_date);

CREATE INDEX IF NOT EXISTS idx_model_label_forward_return_v1_entry_date
ON model_label_forward_return_v1(entry_date);

CREATE INDEX IF NOT EXISTS idx_model_label_forward_return_v1_label_complete_asof
ON model_label_forward_return_v1(horizon_days, label_complete_asof_date);

CREATE INDEX IF NOT EXISTS idx_model_label_forward_return_v1_horizon_trade_date
ON model_label_forward_return_v1(horizon_days, trade_date);

CREATE INDEX IF NOT EXISTS idx_model_label_forward_return_v1_build_run_id
ON model_label_forward_return_v1(build_run_id);
