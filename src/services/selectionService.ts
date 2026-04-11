import { API_BASE_URL, getWriteHeaders } from '../config';
import {
  HistoryMultiframeGranularity,
  HistoryMultiframeItem,
  SelectionBacktestDetail,
  SelectionCandidatesResponse,
  SelectionHealthData,
  SelectionProfileData,
  SelectionStrategy,
} from '../types';

const parseApiData = async <T>(res: Response): Promise<T | null> => {
  const json = await res.json().catch(() => null);
  if (!res.ok || !json || json.code !== 200) {
    return null;
  }
  return (json.data ?? null) as T | null;
};

export const fetchSelectionHealth = async (): Promise<SelectionHealthData | null> => {
  try {
    const res = await fetch(`${API_BASE_URL}/selection/health`);
    return await parseApiData<SelectionHealthData>(res);
  } catch (e) {
    console.error('Fetch selection health error:', e);
    return null;
  }
};

export const fetchSelectionCandidates = async (
  date?: string,
  strategy: SelectionStrategy = 'breakout',
  limit = 50
): Promise<SelectionCandidatesResponse | null> => {
  try {
    const params = new URLSearchParams({ strategy, limit: String(limit) });
    if (date) params.set('date', date);
    const res = await fetch(`${API_BASE_URL}/selection/candidates?${params.toString()}`);
    return await parseApiData<SelectionCandidatesResponse>(res);
  } catch (e) {
    console.error('Fetch selection candidates error:', e);
    return null;
  }
};

export const fetchSelectionProfile = async (symbol: string, date?: string): Promise<SelectionProfileData | null> => {
  try {
    const params = new URLSearchParams();
    if (date) params.set('date', date);
    const query = params.toString();
    const res = await fetch(`${API_BASE_URL}/selection/profile/${symbol}${query ? `?${query}` : ''}`);
    return await parseApiData<SelectionProfileData>(res);
  } catch (e) {
    console.error('Fetch selection profile error:', e);
    return null;
  }
};

export const fetchSelectionBacktests = async (): Promise<any[]> => {
  try {
    const res = await fetch(`${API_BASE_URL}/selection/backtests`);
    const data = await parseApiData<{ items: any[] }>(res);
    return data?.items || [];
  } catch (e) {
    console.error('Fetch selection backtests error:', e);
    return [];
  }
};

export const fetchSelectionBacktestDetail = async (runId: number): Promise<SelectionBacktestDetail | null> => {
  try {
    const res = await fetch(`${API_BASE_URL}/selection/backtests/${runId}`);
    return await parseApiData<SelectionBacktestDetail>(res);
  } catch (e) {
    console.error('Fetch selection backtest detail error:', e);
    return null;
  }
};

export const runSelectionBacktest = async (payload: {
  strategy_name: SelectionStrategy;
  start_date: string;
  end_date: string;
  holding_days_set: number[];
  max_positions_per_day: number;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
}): Promise<SelectionBacktestDetail | null> => {
  try {
    const res = await fetch(`${API_BASE_URL}/selection/backtests/run`, {
      method: 'POST',
      headers: getWriteHeaders(true),
      body: JSON.stringify(payload),
    });
    return await parseApiData<SelectionBacktestDetail>(res);
  } catch (e) {
    console.error('Run selection backtest error:', e);
    return null;
  }
};

export const refreshSelectionResearch = async (startDate?: string, endDate?: string): Promise<any | null> => {
  try {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    const res = await fetch(`${API_BASE_URL}/selection/refresh?${params.toString()}`, {
      method: 'POST',
      headers: getWriteHeaders(),
    });
    return await parseApiData<any>(res);
  } catch (e) {
    console.error('Refresh selection research error:', e);
    return null;
  }
};

export const fetchSelectionHistoryMultiframe = async (
  symbol: string,
  options: {
    days?: number;
    granularity?: HistoryMultiframeGranularity;
    startDate?: string;
    endDate?: string;
    includeTodayPreview?: boolean;
  } = {}
): Promise<HistoryMultiframeItem[]> => {
  try {
    const params = new URLSearchParams({
      symbol,
      granularity: options.granularity || '1d',
      days: String(options.days || 20),
      include_today_preview: options.includeTodayPreview === false ? 'false' : 'true',
    });
    if (options.startDate) params.set('start_date', options.startDate);
    if (options.endDate) params.set('end_date', options.endDate);
    const res = await fetch(`${API_BASE_URL}/selection/history/multiframe?${params.toString()}`);
    const data = await parseApiData<{ items: HistoryMultiframeItem[] }>(res);
    return data?.items || [];
  } catch (e) {
    console.error('Fetch selection history multiframe error:', e);
    return [];
  }
};
