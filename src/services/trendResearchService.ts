import { API_BASE_URL } from '../config';

export interface TrendIdeaItem {
  id: string;
  name: string;
  status: string;
  rating: string;
  stage: string;
  action: string;
  latest_report?: string;
  summary?: { title?: string; bullets?: string[] };
}

export interface TrendDashboardData {
  idea: TrendIdeaItem & { report_date?: string };
  verdict: Record<string, string>;
  upgrade_rules: string[];
  downgrade_rules: string[];
  industry_signals: Array<Record<string, string>>;
  watchlist: Array<Record<string, string>>;
  a_share_price_stage: Array<Record<string, string>>;
  company_snapshot: Array<Record<string, string>>;
  global_peer_stage: Array<Record<string, string>>;
  valuation_scenarios: Array<Record<string, string>>;
  report: { path?: string; summary?: { title?: string; bullets?: string[] }; markdown?: string };
  sources: Record<string, string>;
}

const parseApiData = async <T>(res: Response): Promise<T | null> => {
  const json = await res.json().catch(() => null);
  if (!res.ok || !json || json.code !== 200) return null;
  return (json.data ?? null) as T | null;
};

export const fetchTrendIdeas = async (): Promise<TrendIdeaItem[]> => {
  try {
    const res = await fetch(`${API_BASE_URL}/trend-research/ideas`);
    const data = await parseApiData<{ items: TrendIdeaItem[] }>(res);
    return data?.items || [];
  } catch (e) {
    console.error('Fetch trend ideas error:', e);
    return [];
  }
};

export const fetchTrendDashboard = async (ideaId: string): Promise<TrendDashboardData | null> => {
  try {
    const res = await fetch(`${API_BASE_URL}/trend-research/ideas/${ideaId}/dashboard`);
    return await parseApiData<TrendDashboardData>(res);
  } catch (e) {
    console.error('Fetch trend dashboard error:', e);
    return null;
  }
};
