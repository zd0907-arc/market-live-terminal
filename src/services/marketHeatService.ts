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
