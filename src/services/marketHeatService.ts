import { API_BASE_URL } from '../config';

export interface MarketHeatStock {
  symbol: string;
  name: string;
  role?: string;
  pct_change?: number;
  return_5d?: number;
  return_10d?: number;
  return_20d?: number;
  amount_yi?: number;
  l2_net_inflow_yi?: number;
  close?: number;
  strength?: number;
}

export interface MarketHeatTrendPoint {
  date: string;
  value: number;
}

export interface MarketHeatSector {
  id: string;
  name: string;
  type: string;
  description?: string;
  trade_date: string;
  member_count: number;
  hot_score: number;
  persistence_score: number;
  pct_change: number;
  return_5d: number;
  return_10d: number;
  return_20d: number;
  amount_yi: number;
  amount_ratio: number;
  l2_net_inflow_yi: number;
  l2_positive_ratio: number;
  up_ratio: number;
  big_up_count: number;
  limit_up_count: number;
  risk_tags?: string[];
  readout?: string;
  stocks: MarketHeatStock[];
  trend: MarketHeatTrendPoint[];
  source?: string;
}

export interface MarketHeatSnapshot {
  meta: {
    generated_at: string;
    trade_date: string;
    version: string;
    source: string;
    notes?: string[];
  };
  hot_top: MarketHeatSector[];
  persistence_top: MarketHeatSector[];
  emerging: MarketHeatSector[];
  risk_or_fading: MarketHeatSector[];
  sectors: MarketHeatSector[];
}

export interface MarketHeatHistoryLeader {
  id: string;
  name: string;
  hot_score: number;
  persistence_score: number;
  pct_change: number;
  return_5d: number;
  return_20d: number;
  l2_net_inflow_yi: number;
  risk_tags?: string[];
}

export interface MarketHeatHistorySeries {
  id: string;
  name: string;
  top_count: number;
  latest_hot_score: number;
  latest_persistence_score: number;
  points: Array<{
    date: string;
    hot_score: number;
    persistence_score: number;
    pct_change: number;
    return_5d: number;
    return_20d: number;
  }>;
}

export interface MarketHeatHistorySummary {
  meta: {
    start_date: string;
    end_date: string;
    days: number;
    version: string;
    source: string;
  };
  daily_top: Array<{
    date: string;
    leaders: MarketHeatHistoryLeader[];
  }>;
  series: MarketHeatHistorySeries[];
}

export interface FineHeatTrendPoint {
  date: string;
  rank: number;
  hot_score: number;
  pct_change: number;
}

export interface FineHeatTheme {
  id: string;
  name: string;
  sector_type: string;
  member_count: number;
  lifecycle: string;
  display_score: number;
  rank_today: number;
  rank_prev?: number | null;
  rank_delta: number;
  rank_improve_5d?: number;
  hot_score: number;
  pct_change: number;
  hot_change_5d: number;
  front_hits_5: number;
  hot_hits_5: number;
  watch_hits_5: number;
  front_hits_20: number;
  hot_hits_20: number;
  watch_hits_20: number;
  prev_front_hits_10?: number;
  prev_hot_hits_10?: number;
  limit_up_count: number;
  touch_limit_up_count: number;
  broken_limit_up_count: number;
  evidence: string[];
  reason: string;
  trend: FineHeatTrendPoint[];
  stock_summary?: {
    stock_count: number;
    up_count: number;
    up_ratio: number;
    avg_pct_change: number;
    limit_up_count: number;
    touch_limit_up_count: number;
    broken_limit_up_count: number;
  };
  stock_groups?: Record<string, FineHeatStock[]>;
  stocks?: FineHeatStock[];
}

export interface FineHeatStock {
  symbol: string;
  name: string;
  pct_change: number;
  close: number;
  amount_yi: number;
  l2_net_inflow_yi: number;
  is_limit_up: boolean;
  touch_limit_up: boolean;
  broken_limit_up: boolean;
  return_5d?: number;
  return_20d?: number;
  position_20d?: number;
  drawdown_20d?: number;
  amount_ratio_10d?: number;
  l2_net_inflow_3d_yi?: number;
  l2_positive_days_3d?: number;
  ma5?: number;
  ma10?: number;
  signal_label?: string;
  signal_tone?: 'opportunity' | 'strong' | 'hot' | 'risk' | 'watch' | string;
  opportunity_score?: number;
  risk_score?: number;
  history?: FineHeatStockHistoryPoint[];
}

export interface FineHeatStockHistoryPoint {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  pct_change?: number;
  amount_yi?: number;
  l2_net_inflow_yi?: number;
}

export interface FineHeatThemeStockDetail {
  theme_id: string;
  trade_date: string;
  stock_summary?: FineHeatTheme['stock_summary'];
  stock_groups?: Record<string, FineHeatStock[]>;
  stocks: FineHeatStock[];
}

export interface FineHeatForecastItem {
  trade_date: string;
  theme_id: string;
  theme_name: string;
  sector_code: string;
  sector_type: string;
  current_rank: number;
  current_hot_score: number;
  probability: number;
  probability_pct: number;
  score_rank: number;
  probability_percentile: number;
}

export interface FineHeatForecast {
  meta: {
    trade_date: string;
    model_version: string;
    target: string;
    horizon_days: number;
    rank_band: number;
    limit: number;
    model_created_at?: string | null;
    train_start_date?: string | null;
    train_end_date?: string | null;
    validation_start_date?: string | null;
    validation_end_date?: string | null;
    model_path?: string | null;
    feature_count: number;
    universe?: string;
  };
  metrics: Record<string, number | string | null>;
  items: FineHeatForecastItem[];
}

export interface FineHeatDashboard {
  meta: {
    generated_at: string;
    trade_date: string;
    start_date: string;
    end_date: string;
    days: number;
    fine_theme_count: number;
    front_band: number;
    orange_band: number;
    hot_band: number;
    watch_band: number;
    first_hot_band?: number;
    source: string;
    cache_path?: string;
    notes?: string[];
  };
  cards: {
    today_strong: FineHeatTheme[];
    new_hot: FineHeatTheme[];
    returning: FineHeatTheme[];
    warming: FineHeatTheme[];
    mainline: FineHeatTheme[];
    fading: FineHeatTheme[];
  };
  pool: FineHeatTheme[];
}

export interface FineHeatTradeDateItem {
  date: string;
  is_trade_day: boolean;
  selectable: boolean;
  has_cache: boolean;
  is_latest?: boolean;
}

export interface FineHeatDatesData {
  latest_trade_date?: string | null;
  latest_cached_date?: string | null;
  min_date?: string | null;
  max_date?: string | null;
  dates: FineHeatTradeDateItem[];
  cache_ranges?: Array<{ start_date: string; end_date: string; path: string }>;
}

export interface FineHeatRefreshResult {
  trade_date: string;
  start_date: string;
  end_date: string;
  days: number;
  fine_theme_count?: number;
  cache_path: string;
  rebuilt: boolean;
}

export interface LowPositionL2SampleItem {
  trade_date: string;
  symbol: string;
  name: string;
  theme_name: string;
  theme_rank: number;
  theme_recent_hits: number;
  close: number;
  return_5d_pct: number;
  position_20d: number;
  ma60_distance_abs_pct: number;
  amount_ratio_10d: number;
  l2_main_net_2d_yi: number;
  l2_super_net_3d_yi: number;
  super_positive_days_3d: number;
  entry_date?: string;
  open_gap_pct?: number;
  open_gap_bin?: string;
  intraday_fade?: boolean;
  entry_label?: string;
  d1_return_pct?: number;
  d3_return_pct?: number;
  d5_return_pct?: number;
  d5_alpha_pct?: number;
  market_liquidity_label?: string;
  market_advancer_ratio?: number;
  shadow_score: number;
}

export interface LowPositionL2SampleSummary {
  meta: {
    start_date?: string;
    end_date?: string;
    sample_count?: number;
    strategy?: string;
    db_path?: string;
  };
  summary: {
    horizon_stats?: Record<string, {
      n: number;
      avg: number;
      median: number;
      win_rate: number;
      alpha: number;
      market_avg: number;
      market_win_rate: number;
    }>;
    groups?: Record<string, Record<string, number | string | null>>;
    entry_gap_bins?: Record<string, Record<string, number | string | null>>;
    amount_ratio_bins?: Record<string, Record<string, number | string | null>>;
    ma60_abs_bins?: Record<string, Record<string, number | string | null>>;
    d1_fade_bins?: Record<string, Record<string, number | string | null>>;
    top_themes?: Array<[string, number]>;
  };
  filters: {
    themes: Array<{ theme_name: string; count: number }>;
    outcomes: Array<{ value: string; label: string }>;
  };
}

export interface LowPositionL2SamplesResponse {
  items: LowPositionL2SampleItem[];
  total: number;
  limit: number;
  offset: number;
  sort: string;
}

export interface LowPositionL2SampleDetail {
  sample: LowPositionL2SampleItem & Record<string, number | string | boolean | null | undefined>;
  readout: {
    setup: string;
    funding: string;
    entry: string;
    verdict: string;
  };
  price_window: Array<{
    trade_date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    amount_yi: number;
    l2_main_net_yi: number;
    l2_super_net_yi: number;
    is_signal_day: boolean;
  }>;
}

const parseApiData = async <T>(res: Response): Promise<T | null> => {
  const json = await res.json().catch(() => null);
  if (!res.ok || !json || json.code !== 200) {
    return null;
  }
  return (json.data ?? null) as T | null;
};

export const fetchMarketHeatLatest = async (date?: string, refresh = false): Promise<MarketHeatSnapshot | null> => {
  try {
    const params = new URLSearchParams();
    if (date) params.set('date', date);
    if (refresh) params.set('refresh', 'true');
    const res = await fetch(`${API_BASE_URL}/market_heat/latest${params.toString() ? `?${params.toString()}` : ''}`);
    return await parseApiData<MarketHeatSnapshot>(res);
  } catch (e) {
    console.error('Fetch market heat error:', e);
    return null;
  }
};

export const fetchMarketHeatHistory = async (days = 63, endDate?: string): Promise<MarketHeatHistorySummary | null> => {
  try {
    const params = new URLSearchParams({ days: String(days) });
    if (endDate) params.set('end_date', endDate);
    const res = await fetch(`${API_BASE_URL}/market_heat/history?${params.toString()}`);
    return await parseApiData<MarketHeatHistorySummary>(res);
  } catch (e) {
    console.error('Fetch market heat history error:', e);
    return null;
  }
};

export const fetchFineHeatDashboard = async (days = 63, endDate?: string, poolSize = 18): Promise<FineHeatDashboard | null> => {
  try {
    const params = new URLSearchParams({ days: String(days), pool_size: String(poolSize) });
    if (endDate) params.set('end_date', endDate);
    const res = await fetch(`${API_BASE_URL}/market_heat/fine_dashboard?${params.toString()}`);
    return await parseApiData<FineHeatDashboard>(res);
  } catch (e) {
    console.error('Fetch fine heat dashboard error:', e);
    return null;
  }
};

export const fetchFineHeatDates = async (days = 260, endDate?: string): Promise<FineHeatDatesData | null> => {
  try {
    const params = new URLSearchParams({ days: String(days) });
    if (endDate) params.set('end_date', endDate);
    const res = await fetch(`${API_BASE_URL}/market_heat/fine_dates?${params.toString()}`);
    return await parseApiData<FineHeatDatesData>(res);
  } catch (e) {
    console.error('Fetch fine heat dates error:', e);
    return null;
  }
};

export const refreshFineHeatDashboard = async (endDate?: string, days = 63, force = true): Promise<FineHeatRefreshResult | null> => {
  try {
    const params = new URLSearchParams({ days: String(days), force: String(force) });
    if (endDate) params.set('end_date', endDate);
    const res = await fetch(`${API_BASE_URL}/market_heat/fine_dashboard/refresh?${params.toString()}`, { method: 'POST' });
    return await parseApiData<FineHeatRefreshResult>(res);
  } catch (e) {
    console.error('Refresh fine heat dashboard error:', e);
    return null;
  }
};

export const fetchFineThemeStockDetail = async (themeId: string, endDate?: string, historyDays = 45): Promise<FineHeatThemeStockDetail | null> => {
  try {
    const params = new URLSearchParams({ theme_id: themeId, history_days: String(historyDays) });
    if (endDate) params.set('end_date', endDate);
    const res = await fetch(`${API_BASE_URL}/market_heat/fine_theme_stock_detail?${params.toString()}`);
    return await parseApiData<FineHeatThemeStockDetail>(res);
  } catch (e) {
    console.error('Fetch fine theme stock detail error:', e);
    return null;
  }
};

export const fetchFineThemeForecast = async (
  tradeDate?: string,
  target = 'future_mainline_extension_5d',
  limit = 5,
  modelVersion?: string,
): Promise<FineHeatForecast | null> => {
  try {
    const params = new URLSearchParams({ target, limit: String(limit) });
    if (tradeDate) params.set('trade_date', tradeDate);
    if (modelVersion) params.set('model_version', modelVersion);
    const res = await fetch(`${API_BASE_URL}/market_heat/fine_theme_forecast?${params.toString()}`);
    return await parseApiData<FineHeatForecast>(res);
  } catch (e) {
    console.error('Fetch fine theme forecast error:', e);
    return null;
  }
};

export const fetchLowPositionL2SampleSummary = async (): Promise<LowPositionL2SampleSummary | null> => {
  try {
    const res = await fetch(`${API_BASE_URL}/market_heat/low_position_l2_samples/summary`);
    return await parseApiData<LowPositionL2SampleSummary>(res);
  } catch (e) {
    console.error('Fetch low-position L2 sample summary error:', e);
    return null;
  }
};

export const fetchLowPositionL2Samples = async (params: {
  startDate?: string;
  endDate?: string;
  outcome?: string;
  theme?: string;
  sort?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<LowPositionL2SamplesResponse | null> => {
  try {
    const query = new URLSearchParams();
    if (params.startDate) query.set('start_date', params.startDate);
    if (params.endDate) query.set('end_date', params.endDate);
    if (params.outcome && params.outcome !== 'all') query.set('outcome', params.outcome);
    if (params.theme) query.set('theme', params.theme);
    if (params.sort) query.set('sort', params.sort);
    query.set('limit', String(params.limit ?? 200));
    query.set('offset', String(params.offset ?? 0));
    const res = await fetch(`${API_BASE_URL}/market_heat/low_position_l2_samples?${query.toString()}`);
    return await parseApiData<LowPositionL2SamplesResponse>(res);
  } catch (e) {
    console.error('Fetch low-position L2 samples error:', e);
    return null;
  }
};

export const fetchLowPositionL2SampleDetail = async (tradeDate: string, symbol: string): Promise<LowPositionL2SampleDetail | null> => {
  try {
    const query = new URLSearchParams({ trade_date: tradeDate, symbol });
    const res = await fetch(`${API_BASE_URL}/market_heat/low_position_l2_samples/detail?${query.toString()}`);
    return await parseApiData<LowPositionL2SampleDetail>(res);
  } catch (e) {
    console.error('Fetch low-position L2 sample detail error:', e);
    return null;
  }
};
