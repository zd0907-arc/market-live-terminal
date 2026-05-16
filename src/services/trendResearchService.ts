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
  chain_layers: Array<Record<string, string>>;
  price_radar: Array<Record<string, string>>;
  foundry_supply: Array<Record<string, string>>;
  downstream_demand: Array<Record<string, string>>;
  a_share_mapping_score: Array<Record<string, string>>;
  pre_earnings_warning: Array<Record<string, string>>;
  data_source_matrix: Array<Record<string, string>>;
  watchlist: Array<Record<string, string>>;
  a_share_price_stage: Array<Record<string, string>>;
  a_share_price_history: Array<Record<string, string>>;
  company_snapshot: Array<Record<string, string>>;
  company_validation: Array<Record<string, string>>;
  global_peer_stage: Array<Record<string, string>>;
  global_peer_history: Array<Record<string, string>>;
  valuation_scenarios: Array<Record<string, string>>;
  decision_matrix: Array<Record<string, string>>;
  storage_dashboard?: {
    summary?: Record<string, string>;
    factor_scorecard?: Array<Record<string, string>>;
    operability_summary?: Array<Record<string, string>>;
    score_history?: Array<Record<string, string>>;
    sources?: Record<string, string>;
  } | null;
  rubber_dashboard?: {
    summary?: Record<string, string>;
    factor_scorecard?: Array<Record<string, string>>;
    monitor?: Array<Record<string, string>>;
    weather?: Array<Record<string, string>>;
    trigger_rules?: Array<Record<string, string>>;
    company_transmission?: Array<Record<string, string>>;
    score_history?: Array<Record<string, string>>;
    price_history?: Array<Record<string, string>>;
    long_cycle_price_history?: Array<Record<string, string>>;
    price_snapshot?: {
      ru?: Record<string, string | number | boolean>;
      nr?: Record<string, string | number | boolean>;
      price_confirm_score?: string;
      price_confirm_max?: string;
      price_confirm_state?: string;
    };
    report_path?: string;
    sources?: Record<string, string>;
  } | null;
  agri_basket_dashboard?: {
    summary?: Record<string, string>;
    factor_scorecard?: Array<Record<string, string>>;
    price_basket?: Array<Record<string, string>>;
    watchlist?: Array<Record<string, string>>;
    score_history?: Array<Record<string, string>>;
    sources?: Record<string, string>;
  } | null;
  generic_dashboard?: {
    summary?: Record<string, string>;
    factor_scorecard?: Array<Record<string, string>>;
    market_heat?: Array<Record<string, string>>;
    company_research?: Array<Record<string, string>>;
    watchlist?: Array<Record<string, string>>;
    score_history?: Array<Record<string, string>>;
    sources?: Record<string, string>;
  } | null;
  tracking_tasks: Array<Record<string, string>>;
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
