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
