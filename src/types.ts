export interface StockBase {
  code: string;      // e.g., "600519"
  symbol: string;    // e.g., "sh600519"
  name: string;      // e.g., "贵州茅台"
}

export interface RealTimeQuote extends StockBase {
  price: number;
  lastClose: number;
  open: number;
  high: number;
  low: number;
  volume: number;    // 成交量（股）
  amount: number;    // 成交额（元）
  time: string;
  date: string;
  // 买卖五档
  bids: { price: number; volume: number }[];
  asks: { price: number; volume: number }[];
}

export interface TickData {
  time: string;      // HH:mm:ss
  price: number;     // 成交价
  volume: number;    // 成交量（手）
  amount: number;    // 成交额（元）
  type: 'buy' | 'sell' | 'neutral'; // 主卖/主买/中性
  color: string;     // UI辅助颜色
}

export interface SearchResult {
  name: string;
  code: string;
  symbol: string; // 完整带前缀代码
  market: string; // sh or sz
}

export interface CapitalFlowTrend {
  time: string;           // HH:mm
  mainNetInflow: number;  // 主力净流入 (大单+超大单)
  superNetInflow: number; // 超大单净流入
  mainCumInflow: number;  // 主力累计
  superCumInflow: number; // 超大单累计
}

export interface CapitalRatioData {
  time: string;           // HH:mm
  mainBuyRatio: number;   // 主力买入占比 %
  mainSellRatio: number;  // 主力卖出占比 %
  mainParticipationRatio: number; // 主力参与度 (买+卖)/总 %
  mainBuyAmount?: number; // 主力买入金额 (元)
  mainSellAmount?: number; // 主力卖出金额 (元)
  superBuyAmount?: number; // 超大单买入金额 (元)
  superSellAmount?: number; // 超大单卖出金额 (元)
  superParticipationRatio?: number; // 超大单参与度 %
  closePrice?: number;    // 收盘价
}

export interface CumulativeCapitalData {
  time: string;           // HH:mm
  cumMainBuy: number;     // 累计主力买入 (元)
  cumMainSell: number;    // 累计主力卖出 (元)
  cumNetInflow: number;   // 累计净流入 (元)
  
  // 超大单数据
  cumSuperNetInflow: number; // 累计超大单净流入
  cumSuperBuy: number;
  cumSuperSell: number;
}

export interface DashboardSourceMeta {
  source?: string;
  is_finalized?: boolean;
  bucket_granularity?: string;
  display_date?: string;
  natural_today?: string;
  market_status?: string;
  market_status_label?: string;
  default_display_date?: string;
  default_display_scope?: string;
  default_display_scope_label?: string;
  view_mode?: string;
  view_mode_label?: string;
  is_realtime_session?: boolean;
}

export interface RealtimeDashboardData extends DashboardSourceMeta {
  chart_data: CapitalRatioData[];
  cumulative_data: CumulativeCapitalData[];
  latest_ticks: TickData[];
}

export type IntradayFusionMode =
  | 'intraday_l1_only'
  | 'postclose_dual_track'
  | 'historical_dual_track';

export interface IntradayFusionBar {
  datetime: string;
  trade_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  total_amount: number | null;
  total_volume: number | null;
  l1_main_buy: number | null;
  l1_main_sell: number | null;
  l1_super_buy: number | null;
  l1_super_sell: number | null;
  l1_net_inflow: number | null;
  l2_main_buy: number | null;
  l2_main_sell: number | null;
  l2_super_buy: number | null;
  l2_super_sell: number | null;
  l2_net_inflow: number | null;
  add_buy_amount: number | null;
  add_sell_amount: number | null;
  cancel_buy_amount: number | null;
  cancel_sell_amount: number | null;
  l2_cvd_delta: number | null;
  l2_oib_delta: number | null;
  source?: string;
  is_finalized?: boolean;
  preview_level?: string | null;
  fallback_used?: boolean;
}

export interface IntradayFusionData {
  symbol: string;
  trade_date: string;
  mode: IntradayFusionMode;
  mode_label: string;
  bucket_granularity: string;
  is_l2_finalized: boolean;
  source: string;
  fallback_used: boolean;
  bars: IntradayFusionBar[];
}

export interface FundsBattleSignalTuning {
  diffThreshold: number;
  cancelThreshold: number;
  vwapDistanceThreshold: number;
  volatilityChannelRatio: number;
  volumeResonanceRatio: number;
}

// 新增：历史分析数据结构
export interface HistoryAnalysisData {
  date: string;
  close: number;
  pct_change: number;
  total_amount: number;
  main_buy_amount: number;
  main_sell_amount: number;
  net_inflow: number;
  // 以下为前端计算字段
  buyRatio?: number;
  sellRatio?: number;
  activityRatio?: number;
  super_large_ratio?: number;
  source?: string;
  is_finalized?: boolean;
  fallback_used?: boolean;
  l1_main_buy_amount?: number;
  l1_main_sell_amount?: number;
  l1_net_inflow?: number;
  l1_super_large_in?: number;
  l1_super_large_out?: number;
  l1_activityRatio?: number;
  l1_buyRatio?: number;
  l1_sellRatio?: number;
  l1_super_large_ratio?: number;
  l2_main_buy_amount?: number;
  l2_main_sell_amount?: number;
  l2_net_inflow?: number;
  l2_super_large_in?: number;
  l2_super_large_out?: number;
  l2_activityRatio?: number;
  l2_buyRatio?: number;
  l2_sellRatio?: number;
  l2_super_large_ratio?: number;
}

export interface HistoryTrendData {
  time: string; // "YYYY-MM-DD HH:MM:SS"
  net_inflow: number;
  main_buy: number;
  main_sell: number;
  super_net: number;
  super_buy: number;
  super_sell: number;
  close?: number; // Added for V3.3 price line
  open?: number;
  high?: number;
  low?: number;
  source?: string;
  is_finalized?: boolean;
  fallback_used?: boolean;
}

export type HistoryMultiframeGranularity = '5m' | '15m' | '30m' | '1h' | '1d';

export interface HistoryMultiframeItem {
  datetime: string;
  trade_date: string;
  granularity: HistoryMultiframeGranularity;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  prev_close?: number | null;
  change_pct?: number | null;
  total_amount: number | null;
  l1_main_buy: number | null;
  l1_main_sell: number | null;
  l1_super_buy: number | null;
  l1_super_sell: number | null;
  l2_main_buy: number | null;
  l2_main_sell: number | null;
  l2_super_buy: number | null;
  l2_super_sell: number | null;
  source?: string;
  is_finalized?: boolean;
  preview_level?: string | null;
  fallback_used?: boolean;
  quality_info?: string | null;
  is_placeholder?: boolean;
}

export interface SandboxReviewBar {
  symbol: string;
  datetime: string;
  bucket_granularity?: '5m' | '15m' | '30m' | '60m' | '1d';
  open: number;
  high: number;
  low: number;
  close: number;
  total_amount: number;
  l1_main_buy: number;
  l1_main_sell: number;
  l1_main_net: number;
  l1_super_buy: number;
  l1_super_sell: number;
  l1_super_net: number;
  l2_main_buy: number;
  l2_main_sell: number;
  l2_main_net: number;
  l2_super_buy: number;
  l2_super_sell: number;
  l2_super_net: number;
  source_date: string;
}

export interface SandboxPoolItem {
  symbol: string;
  name: string;
  market_cap: number;
  as_of_date: string;
  source: string;
  updated_at: string;
}

export interface ReviewBar extends SandboxReviewBar {
  quality_info?: string | null;
}

export interface ReviewPoolItem extends SandboxPoolItem {
  min_date: string;
  max_date: string;
  latest_date: string;
}

export interface SentimentData {
  symbol: string;
  name: string;
  price: number;
  last_close: number;
  volume: number;
  outer_disk: number; // Active Buy
  inner_disk: number; // Active Sell
  buy_queue_vol: number; // Total Buy 1-5
  sell_queue_vol: number; // Total Sell 1-5
  turnover_rate: number;
  timestamp: string;
}


export type SelectionStrategy = 'stable_capital_callback' | 'trend_continuation_callback' | 'stealth' | 'breakout' | 'distribution' | 'v2';

export interface SelectionHealthData {
  status: string;
  feature_version: string;
  strategy_version: string;
  backtest_version: string;
  latest_signal_date?: string | null;
  feature_rows: number;
  signal_rows: number;
  backtest_runs: number;
  source_snapshot?: Record<string, any>;
}

export interface SelectionTradeDateItem {
  date: string;
  is_trade_day: boolean;
  signal_count: number;
  candidate_count?: number;
  feature_count?: number;
  has_feature?: boolean;
  has_candidates?: boolean;
  has_market_environment?: boolean;
  market_environment_only?: boolean;
  can_generate?: boolean;
  has_run?: boolean;
  run_count?: number;
  successful_run_count?: number;
  failed_run_count?: number;
  run_candidate_count?: number;
  last_run_finished_at?: string | null;
  selectable: boolean;
  disabled_reason?: string | null;
}

export interface SelectionTradeDatesData {
  start_date?: string | null;
  end_date?: string | null;
  strategy?: string;
  truncated?: boolean;
  window_days?: number;
  items: SelectionTradeDateItem[];
}

export type SelectionMarketGateStatus = 'allowed' | 'watch_only' | 'blocked' | 'exception_failed' | (string & {});

export interface SelectionMarketEnvironment {
  trade_date?: string | null;
  water_score?: number | null;
  market_regime?: string | null;
  market_detail?: string | null;
  market_detail_label?: string | null;
  default_action?: string | null;
  reason_top3?: string[];
  metrics?: Record<string, number | null | undefined>;
  recent?: Array<{
    trade_date?: string | null;
    water_score?: number | null;
    market_regime?: string | null;
    market_detail_label?: string | null;
    default_action?: string | null;
    action_code?: string | null;
    all_up_ratio_5d?: number | null;
    small_up_ratio_5d?: number | null;
    all_med_ret_5d?: number | null;
    csi1000_return_5d_pct?: number | null;
  }>;
  [key: string]: any;
}

export interface SelectionEntryDecisionBreakdown {
  market_gate?: {
    status?: SelectionMarketGateStatus | null;
    label?: string | null;
    reasons?: string[];
  };
  stock_rule?: {
    status?: string | null;
    label?: string | null;
    buy_rule?: string | null;
  };
  final_action?: {
    status?: string | null;
    label?: string | null;
  };
  [key: string]: any;
}

export interface SelectionMarketGateEvidence {
  primary_window?: string | null;
  warning_window?: string | null;
  confirm_window?: string | null;
  [key: string]: any;
}

export interface SelectionCandidateItem {
  rank?: number;
  symbol: string;
  name: string;
  trade_date: string;
  score: number;
  signal: number;
  signal_label?: string;
  current_judgement?: string;
  reason_summary?: string;
  risk_level?: string;
  stealth_score: number;
  breakout_score: number;
  distribution_score: number;
  close?: number | null;
  return_5d_pct?: number | null;
  return_10d_pct?: number | null;
  return_20d_pct?: number | null;
  net_inflow_5d?: number | null;
  net_inflow_20d?: number | null;
  positive_inflow_ratio_10d?: number | null;
  dist_ma20_pct?: number | null;
  price_position_60d?: number | null;
  l2_vs_l1_strength?: number | null;
  l2_order_event_available?: number;
  sentiment_heat_ratio?: number | null;
  market_cap?: number | null;
  feature_version?: string;
  strategy_version?: string;
  intent_profile?: Record<string, any>;
  entry_allowed?: boolean;
  entry_block_reasons?: string[];
  market_environment?: SelectionMarketEnvironment | null;
  market_environment_snapshot?: SelectionMarketEnvironment | null;
  source_action_label?: string | null;
  market_gate_status?: SelectionMarketGateStatus | null;
  market_gate_reasons?: string[];
  market_default_action?: string | null;
  final_entry_allowed?: boolean | null;
  final_action_label?: string | null;
  entry_decision_source?: string | null;
  gate_policy_id?: string | null;
  gate_policy_version?: string | null;
  entry_decision_summary?: string | null;
  entry_decision_breakdown?: SelectionEntryDecisionBreakdown | null;
  market_gate_evidence?: SelectionMarketGateEvidence | null;
  candidate_types?: string[];
  selection_rank_score?: number | null;
  selection_rank_mode?: string;
  source_score?: number | null;
  lifecycle_phase?: string;
  lifecycle_phase_label?: string;
  action_label?: string;
  replay_return_pct?: number | null;
  replay_entry_date?: string | null;
  replay_exit_signal_date?: string | null;
  replay_exit_reason?: string | null;
  strategy_display_name?: string;
  strategy_internal_id?: string;
  policy_id?: string;
  policy_name?: string;
  entry_signal_date?: string | null;
  entry_date?: string | null;
  observe_date?: string | null;
  discovery_date?: string | null;
  launch_start_date?: string | null;
  launch_end_date?: string | null;
  pullback_confirm_date?: string | null;
  exit_signal_date?: string | null;
  exit_date?: string | null;
  risk_count?: number;
  risk_labels?: string[];
  setup_reason?: string;
  launch_reason?: string;
  pullback_reason?: string;
  exit_plan_summary?: string;
  trend_score?: number | null;
  fund_score?: number | null;
  repair_score?: number | null;
  confirm_active_buy_strength?: number | null;
  confirm_main_net_ratio?: number | null;
  source_count?: number;
  source_ids?: string[];
  source_types?: string[];
  primary_source_id?: string;
  primary_source_name?: string;
  primary_source_type?: string;
  source_details?: Array<Record<string, any> & {
    source_score_percentile?: number;
    source_strength_label?: string;
    source_score_distribution?: Record<string, number>;
  }>;
  dual_exit_tracks?: SelectionDualExitTrack[];
  spark_exit_meta?: Record<string, any>;
  daily_source_details?: Array<Record<string, any>>;
}

export interface SelectionDualExitTrack {
  track_id: string;
  track_name: string;
  style_summary?: string;
  policy_id?: string;
  policy_name?: string;
  current_judgement?: string;
  status?: 'hold' | 'sell' | 'closed' | string;
  holding_days?: number | null;
  close_return_pct?: number | null;
  max_runup_so_far_pct?: number | null;
  pred_hold_advantage_pp?: number | null;
  pred_extra_upside_pp?: number | null;
  exit_signal_date?: string | null;
  planned_exit_date?: string | null;
  exit_reason?: string | null;
  summary?: string;
}

export interface SelectionCandidatesResponse {
  trade_date: string;
  strategy: SelectionStrategy;
  rank_mode?: string;
  market_environment?: SelectionMarketEnvironment | null;
  items: SelectionCandidateItem[];
  source_runs?: Array<{
    source_id: string;
    label: string;
    status: 'success' | 'failed';
    candidate_count: number;
    error?: string | null;
    finished_at?: string | null;
  }>;
  exit_watchlist?: {
    trade_date: string;
    policy_id: string;
    policy_name: string;
    items: SelectionCandidateItem[];
    skipped?: boolean;
    error?: string;
  };
}

export interface SelectionProfileSeriesItem {
  trade_date: string;
  close?: number | null;
  net_inflow?: number | null;
  activity_ratio?: number | null;
  l1_main_net?: number | null;
  l2_main_net?: number | null;
  event_count?: number | null;
}

export interface SelectionEventTimelineItem {
  kind: 'event' | 'daily_score';
  time: string;
  event_type?: string;
  source?: string;
  content?: string;
  author_name?: string;
  sentiment_score?: number | null;
  direction_label?: string;
  risk_tag?: string;
  summary_text?: string;
}

export interface StockEventFeedItem {
  event_id: string;
  source: string;
  source_label?: string;
  source_type: string;
  source_type_label?: string;
  event_subtype?: string;
  title: string;
  content?: string;
  raw_url?: string | null;
  pdf_url?: string | null;
  published_at?: string | null;
  importance?: number;
  is_official?: boolean;
}

export interface StockEventFeedData {
  items: StockEventFeedItem[];
  latest_event_time?: string | null;
  coverage_status?: string;
}

export interface StockEventCoverageModuleItem {
  module: string;
  label: string;
  covered: boolean;
  count: number;
  latest_event_time?: string | null;
}

export interface StockEventCoverageData {
  symbol: string;
  coverage_status: string;
  alias_count?: number;
  table_total_count?: number;
  symbol_total_count?: number;
  modules: StockEventCoverageModuleItem[];
  by_source_type?: Array<{
    source_type: string;
    label: string;
    count: number;
    latest_event_time?: string | null;
  }>;
  by_source?: Array<{
    source: string;
    source_label: string;
    count: number;
    latest_event_time?: string | null;
  }>;
}

export interface SelectionCompanyResearchCard {
  symbol: string;
  as_of_date: string;
  company_name?: string | null;
  business_profile?: string | null;
  main_business?: string | null;
  profit_drivers?: string[];
  new_business_logic?: string | null;
  theme_tags?: string[];
  valuation_logic?: string | null;
  financial_interpretation?: string | null;
  key_metrics?: Array<Record<string, any>>;
  evidence_event_ids?: string[];
  risk_points?: string[];
  confidence?: number;
  source_coverage?: Record<string, any>;
  source?: string;
  is_generated_fallback?: boolean;
}

export interface SelectionEventInterpretation {
  company_snapshot?: string | null;
  latest_key_event?: StockEventFeedItem | null;
  event_strength?: string;
  persistence?: string;
  fund_consistency?: string;
  action_rhythm?: string;
  key_evidence?: StockEventFeedItem[];
  risk_points?: string[];
  method?: string;
}

export interface SelectionDecisionBrief {
  symbol?: string;
  as_of_date?: string;
  strategy?: string;
  signal_date?: string;
  company_overview?: string | null;
  decision_explanation?: string | null;
  company_overview_generated_at?: string | null;
  decision_explanation_generated_at?: string | null;
  generated_at?: string | null;
  source?: string;
  raw_payload?: Record<string, any>;
}

export interface SelectionResearchEvidenceItem {
  evidence_key?: string;
  source_event_id?: string | null;
  source?: string | null;
  source_type?: string | null;
  published_at?: string | null;
  title?: string | null;
  summary?: string | null;
  claim_tags?: string[];
  raw_url?: string | null;
  pdf_url?: string | null;
  importance?: number;
}

export interface SelectionResearchEvidenceData {
  symbol?: string;
  strategy?: string;
  signal_date?: string;
  as_of_date?: string;
  generated_at?: string | null;
  items?: SelectionResearchEvidenceItem[];
}

export interface SelectionResearchContextData {
  symbol: string;
  name?: string | null;
  trade_date: string;
  requested_trade_date?: string | null;
  strategy: string;
  as_of_cutoff?: string;
  selection_profile: SelectionProfileData;
  price_l2_series?: {
    items: SelectionProfileSeriesItem[];
    count: number;
    coverage_status?: string;
    sources?: string[];
    date_window?: Record<string, any>;
  };
  trade_plan?: SelectionProfileData['trade_plan'];
  stock_event_coverage?: StockEventCoverageData;
  stock_event_feed?: StockEventFeedData;
  sentiment_snapshot?: Record<string, any>;
  company_profile?: Record<string, any>;
  financial_snapshot?: Record<string, any>;
  company_research_card?: SelectionCompanyResearchCard;
  event_interpretation?: SelectionEventInterpretation;
  decision_brief?: SelectionDecisionBrief;
  research_evidence?: SelectionResearchEvidenceData;
  source_audit?: {
    collection_status?: string;
    audit_flags?: Array<{ level: string; code: string; message: string }>;
    recent_items?: StockEventFeedItem[];
    group_counts?: Record<string, number>;
  };
}

export interface SelectionResearchContextPrepareData {
  symbol: string;
  trade_date: string;
  strategy: string;
  prepared_at?: string;
  status?: string;
  stages?: Array<{ step: string; status: string; message?: string; [key: string]: any }>;
  hydrate_result?: Record<string, any>;
  llm_result?: Record<string, any>;
  context: SelectionResearchContextData;
}

export interface SelectionQuickEventJudgeData {
  message_text: string;
  related_symbols: string[];
  primary_symbol: string;
  trade_date?: string;
  event_type: string;
  direction: string;
  event_strength: string;
  persistence: string;
  fund_consistency: string;
  action_rhythm: string;
  follow_up_conditions: string[];
  context?: SelectionResearchContextData;
}

export interface SelectionProfileData {
  symbol: string;
  trade_date: string;
  latest_available_trade_date?: string | null;
  requested_trade_date?: string;
  profile_date_fallback_used?: boolean;
  name?: string | null;
  market_cap?: number | null;
  feature_version: string;
  strategy_version?: string | null;
  stealth_score?: number;
  stealth_signal?: number;
  breakout_score?: number;
  confirm_signal?: number;
  distribution_score?: number;
  exit_signal?: number;
  close: number;
  prev_close?: number | null;
  daily_return_pct?: number | null;
  return_3d_pct?: number | null;
  return_5d_pct?: number | null;
  return_10d_pct?: number | null;
  return_20d_pct?: number | null;
  volatility_10d?: number | null;
  volatility_20d?: number | null;
  ma20?: number | null;
  ma60?: number | null;
  dist_ma20_pct?: number | null;
  dist_ma60_pct?: number | null;
  price_position_20d?: number | null;
  price_position_60d?: number | null;
  breakout_vs_prev20_high_pct?: number | null;
  net_inflow_5d?: number | null;
  net_inflow_10d?: number | null;
  net_inflow_20d?: number | null;
  positive_inflow_ratio_5d?: number | null;
  positive_inflow_ratio_10d?: number | null;
  positive_inflow_ratio_20d?: number | null;
  activity_ratio_5d?: number | null;
  activity_ratio_20d?: number | null;
  l1_main_net_3d?: number | null;
  l2_main_net_3d?: number | null;
  l2_vs_l1_strength?: number | null;
  l2_order_event_available?: number;
  l2_add_buy_3d?: number | null;
  l2_add_sell_3d?: number | null;
  l2_cancel_buy_3d?: number | null;
  l2_cancel_sell_3d?: number | null;
  l2_cvd_3d?: number | null;
  l2_oib_3d?: number | null;
  sentiment_event_count_5d?: number | null;
  sentiment_event_count_20d?: number | null;
  sentiment_heat_ratio?: number | null;
  sentiment_score?: number | null;
  current_judgement?: string;
  breakout_reason_summary?: string;
  distribution_reason_summary?: string;
  distribution_risk_level?: string;
  trade_plan?: {
    signal_date?: string | null;
    entry_date?: string | null;
    entry_price?: number | null;
    exit_signal_date?: string | null;
    exit_date?: string | null;
    exit_price?: number | null;
    exit_reason?: string | null;
    exit_is_simulated?: boolean;
    exit_distribution_score?: number | null;
    return_pct?: number | null;
  };
  explain_cards?: Array<{ title: string; summary: string }>;
  series: SelectionProfileSeriesItem[];
  event_timeline?: SelectionEventTimelineItem[];
  entry_allowed?: boolean;
  entry_block_reasons?: string[];
  market_environment?: SelectionMarketEnvironment | null;
  market_environment_snapshot?: SelectionMarketEnvironment | null;
  source_action_label?: string | null;
  market_gate_status?: SelectionMarketGateStatus | null;
  market_gate_reasons?: string[];
  market_default_action?: string | null;
  final_entry_allowed?: boolean | null;
  final_action_label?: string | null;
  entry_decision_source?: string | null;
  gate_policy_id?: string | null;
  gate_policy_version?: string | null;
  entry_decision_summary?: string | null;
  entry_decision_breakdown?: SelectionEntryDecisionBreakdown | null;
  market_gate_evidence?: SelectionMarketGateEvidence | null;
  intent_profile?: Record<string, any>;
  candidate_types?: string[];
  research?: Record<string, any>;
  strategy_display_name?: string;
  strategy_internal_id?: string;
  policy_id?: string;
  policy_name?: string;
  entry_signal_date?: string | null;
  entry_date?: string | null;
  discovery_date?: string | null;
  launch_start_date?: string | null;
  launch_end_date?: string | null;
  pullback_confirm_date?: string | null;
  exit_signal_date?: string | null;
  exit_date?: string | null;
  risk_count?: number;
  risk_labels?: string[];
  setup_reason?: string;
  launch_reason?: string;
  pullback_reason?: string;
  exit_plan_summary?: string;
  dual_exit_tracks?: SelectionDualExitTrack[];
  spark_exit_meta?: Record<string, any>;
  daily_source_details?: Array<Record<string, any>>;
}

export interface SelectionBacktestRunItem {
  id: number;
  strategy_name: string;
  start_date: string;
  end_date: string;
  holding_days_set: string;
  max_positions_per_day: number;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  feature_version: string;
  strategy_version: string;
  backtest_version: string;
  source_snapshot: string;
  status: string;
  summary_json?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface SelectionBacktestSummaryItem {
  id: number;
  run_id: number;
  strategy_name: string;
  holding_days: number;
  trade_count: number;
  win_rate: number;
  avg_return_pct: number;
  median_return_pct: number;
  max_drawdown_pct: number;
  avg_max_drawdown_pct: number;
  opportunity_win_rate?: number;
  avg_max_runup_pct?: number;
  median_max_runup_pct?: number;
  total_return_pct: number;
}

export interface SelectionBacktestTradeItem {
  id: number;
  run_id: number;
  strategy_name: string;
  holding_days: number;
  symbol: string;
  signal_date: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  max_drawdown_pct: number;
  fixed_exit_return_pct?: number;
  max_runup_within_holding_pct?: number;
  max_drawdown_within_holding_pct?: number;
  exit_reason: string;
  score_value?: number | null;
}

export interface SelectionBacktestDetail {
  run: SelectionBacktestRunItem;
  summaries: SelectionBacktestSummaryItem[];
  trades: SelectionBacktestTradeItem[];
}

export interface PpoBacktestTradeItem {
  symbol: string;
  name?: string | null;
  signal_date?: string;
  entry_bucket: string;
  entry_date: string;
  exit_bucket: string;
  exit_date: string;
  gross_entry_price: number;
  gross_exit_price: number;
  sold_fraction: number;
  cost_cash: number;
  realized_cash: number;
  pnl_cash: number;
  net_return_pct: number;
  holding_days?: number;
  max_runup_pct?: number;
  max_drawdown_pct?: number;
  entry_reason?: string;
  exit_reason: string;
  theme_names?: string;
  theme_hits?: number;
  best_rank?: number;
  selection_score?: number;
}

export interface PpoBacktestReport {
  lab_version: string;
  mode?: string;
  model_path?: string | null;
  report_path?: string | null;
  range?: { start_date?: string; end_date?: string };
  data?: { atomic_db_path?: string; symbols?: number; rows?: number; trade_dates?: string[] };
  training?: Record<string, any>;
  summary: {
    initial_budget?: number;
    final_equity?: number;
    total_return_pct?: number;
    max_drawdown_pct?: number;
    trade_count?: number;
    open_positions?: number;
    cash?: number;
  };
  total_reward?: number;
  steps?: number;
  policy_note?: string;
  feature_names?: string[];
  trades: PpoBacktestTradeItem[];
  actions: Array<Record<string, any>>;
  equity_curve: Array<Record<string, any>>;
  symbol_names?: Record<string, string>;
  by_symbol?: Array<{
    symbol: string;
    name?: string | null;
    trade_count: number;
    pnl_cash: number;
    realized_cash: number;
    invested_cash: number;
    buy_count: number;
    sell_count: number;
    win_count: number;
    loss_count: number;
    max_return_pct?: number | null;
    min_return_pct?: number | null;
    entry_dates: string[];
    exit_dates: string[];
  }>;
  by_day?: Array<{
    date: string;
    trade_count: number;
    pnl_cash: number;
    realized_cash: number;
    open_count: number;
    close_count: number;
  }>;
}
