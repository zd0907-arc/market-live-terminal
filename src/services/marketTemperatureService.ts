import { API_BASE_URL } from '../config';

export interface MarketTemperatureState {
  trade_date: string;
  market_total_amount_yi?: number | null;
  market_total_amount_ma20_yi?: number | null;
  market_amount_ratio_20d?: number | null;
  market_mean_return_pct?: number | null;
  market_median_return_pct?: number | null;
  market_advancer_ratio?: number | null;
  market_decliner_ratio?: number | null;
  limit_up_count?: number | null;
  limit_down_count?: number | null;
  touch_limit_up_count?: number | null;
  broken_limit_up_count?: number | null;
  sealed_limit_up_count?: number | null;
  broken_limit_up_ratio?: number | null;
  csi1000_return_5d_pct?: number | null;
  csi500_return_5d_pct?: number | null;
  hs300_return_5d_pct?: number | null;
  sh_index_return_5d_pct?: number | null;
  gem_index_return_5d_pct?: number | null;
  hot_theme_top5_avg_score?: number | null;
  hot_theme_top10_amount_ratio?: number | null;
  hot_theme_top10_l2_net_yi?: number | null;
  hot_theme_new_count?: number | null;
  hot_theme_continuing_count?: number | null;
  hot_theme_fading_count?: number | null;
  hot_theme_concentration_top3?: number | null;
}

export interface MarketTemperatureSnapshot {
  available: boolean;
  message?: string;
  meta: {
    source: string;
    db_path?: string;
    requested_date?: string | null;
    trade_date?: string;
    days?: number;
    history_count?: number;
  };
  current: MarketTemperatureState | null;
  history: MarketTemperatureState[];
}

const parseApiData = async <T>(res: Response): Promise<T | null> => {
  const json = await res.json().catch(() => null);
  if (!res.ok || !json || json.code !== 200) {
    return null;
  }
  return (json.data ?? null) as T | null;
};

export const fetchMarketTemperatureSnapshot = async (
  days = 120,
  date?: string,
): Promise<MarketTemperatureSnapshot | null> => {
  try {
    const params = new URLSearchParams({ days: String(days) });
    if (date) params.set('date', date);
    const res = await fetch(`${API_BASE_URL}/market_temperature/snapshot?${params.toString()}`);
    return await parseApiData<MarketTemperatureSnapshot>(res);
  } catch (e) {
    console.error('Fetch market temperature snapshot error:', e);
    return null;
  }
};
