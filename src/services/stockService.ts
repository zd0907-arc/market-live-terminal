import {
  RealTimeQuote,
  TickData,
  SearchResult,
  CapitalFlowTrend,
  HistoryAnalysisData,
  HistoryTrendData,
  HistoryMultiframeGranularity,
  HistoryMultiframeItem,
  IntradayFusionData,
  RealtimeDashboardData,
  SandboxPoolItem,
  SandboxReviewBar,
  ReviewPoolItem,
  ReviewBar,
} from '../types';
import { API_BASE_URL, getWriteHeaders } from '../config';

const fetchWithTimeout = async (input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = 10000): Promise<Response> => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
};

// ==========================================
// 基础网络层：JSONP / Script Injection
// ==========================================
const loadScript = (url: string): Promise<void> => {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;
    script.onload = () => {
      resolve();
      cleanup();
    };
    script.onerror = () => {
      reject(new Error(`Script load failed: ${url}`));
      cleanup();
    };

    const cleanup = () => {
      if (document.body.contains(script)) {
        document.body.removeChild(script);
      }
    };

    document.body.appendChild(script);
  });
};

const jsonp = (url: string, callbackName: string, timeout = 5000): Promise<any> => {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;

    const timeoutId = setTimeout(() => {
      cleanup();
      reject(new Error(`Request timeout: ${url}`));
    }, timeout);

    (window as any)[callbackName] = (data: any) => {
      resolve(data);
      cleanup();
    };

    const cleanup = () => {
      clearTimeout(timeoutId);
      try {
        delete (window as any)[callbackName];
      } catch (e) {
        (window as any)[callbackName] = undefined;
      }
      if (document.body.contains(script)) {
        document.body.removeChild(script);
      }
    };

    script.onerror = () => {
      cleanup();
      reject(new Error(`JSONP failed: ${url}`));
    };

    document.body.appendChild(script);
  });
};

// ==========================================
// 健康检查
// ==========================================
export const checkBackendHealth = async (): Promise<boolean> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000); // 2秒超时

    // 使用新的 /api/health 接口
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    return response.ok;
  } catch (e) {
    return false;
  }
};

// ==========================================
// 1. 股票搜索 (Sina Suggest)
// ==========================================
export const searchStock = (query: string): Promise<SearchResult[]> => {
  return new Promise((resolve) => {
    if (!query) return resolve([]);

    const varName = `suggestdata_${Date.now()}`;
    const url = `https://suggest3.sinajs.cn/suggest/type=&key=${encodeURIComponent(query)}&name=${varName}`;

    const script = document.createElement('script');
    script.src = url;

    script.onload = () => {
      const raw = (window as any)[varName];
      if (!raw) {
        resolve([]);
        return;
      }

      const lines = raw.split(';');
      const results: SearchResult[] = [];

      lines.forEach((line: string) => {
        const parts = line.split(',');
        if (parts.length > 4) {
          const code = parts[2];
          const symbol = parts[3];
          if (/^(sh|sz|bj)\d{6}$/.test(symbol)) {
            results.push({
              name: parts[4],
              code: code,
              symbol: symbol,
              market: parts[3].substring(0, 2)
            });
          }
        }
      });
      resolve(results);
      try { delete (window as any)[varName]; } catch (e) { }
      if (document.body.contains(script)) document.body.removeChild(script);
    };

    script.onerror = () => {
      if (document.body.contains(script)) document.body.removeChild(script);
      resolve([]);
    };
    document.body.appendChild(script);
  });
};

// ==========================================
// 2. 实时行情 (Tencent/GTIMG)
// ==========================================
export const fetchQuote = async (symbol: string): Promise<RealTimeQuote> => {
  const url = `https://qt.gtimg.cn/q=${symbol}&_=${Date.now()}`;
  const varName = `v_${symbol}`;

  try {
    await loadScript(url);
    const dataStr = (window as any)[varName];

    if (!dataStr) {
      throw new Error("No data received from Tencent API");
    }

    const parts = dataStr.split('~');
    if (parts.length < 30) {
      throw new Error("Invalid data format");
    }

    const quote: RealTimeQuote = {
      code: parts[2],
      symbol: symbol,
      name: parts[1],
      price: parseFloat(parts[3]),
      lastClose: parseFloat(parts[4]),
      open: parseFloat(parts[5]),
      high: parseFloat(parts[33]),
      low: parseFloat(parts[34]),
      volume: parseFloat(parts[6]) * 100,
      amount: parseFloat(parts[37]) * 10000,
      time: parts[30].substring(8, 14).replace(/(..)(..)(..)/, '$1:$2:$3'),
      date: parts[30].substring(0, 8).replace(/(....)(..)(..)/, '$1-$2-$3'),

      bids: [
        { price: parseFloat(parts[9]), volume: parseInt(parts[10]) },
        { price: parseFloat(parts[11]), volume: parseInt(parts[12]) },
        { price: parseFloat(parts[13]), volume: parseInt(parts[14]) },
        { price: parseFloat(parts[15]), volume: parseInt(parts[16]) },
        { price: parseFloat(parts[17]), volume: parseInt(parts[18]) },
      ],
      asks: [
        { price: parseFloat(parts[19]), volume: parseInt(parts[20]) },
        { price: parseFloat(parts[21]), volume: parseInt(parts[22]) },
        { price: parseFloat(parts[23]), volume: parseInt(parts[24]) },
        { price: parseFloat(parts[25]), volume: parseInt(parts[26]) },
        { price: parseFloat(parts[27]), volume: parseInt(parts[28]) },
      ]
    };

    try { delete (window as any)[varName]; } catch (e) { }
    return quote;

  } catch (error) {
    console.error("Quote fetch error:", error);
    throw error;
  }
};

// ==========================================
// 3. 逐笔成交 (Tencent Full Day via Backend)
// ==========================================
// 旧版前端直连 Eastmoney (仅用于备用或实时性极高的场景)
export const fetchTicksLive = async (symbol: string): Promise<TickData[]> => {
  // ... (保留原有的 Eastmoney 逻辑作为 fetchTicksLive)
  const marketCode = symbol.substring(0, 2);
  const code = symbol.substring(2);
  const marketId = marketCode === 'sh' ? '1' : '0';

  const cb = `cb_ticks_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const url = `https://push2.eastmoney.com/api/qt/stock/details/get?secid=${marketId}.${code}&fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55&pos=-50&iscca=1&invt=2&cb=${cb}`;

  try {
    const res = await jsonp(url, cb, 3000);
    const data = res?.data?.details;

    if (!data || !Array.isArray(data)) return [];

    return data.map((itemStr: string) => {
      const parts = itemStr.split(',');
      if (parts.length < 5) return null;

      const time = parts[0];
      const price = parseFloat(parts[1]);
      const volume = parseInt(parts[2]);
      const typeCode = parseInt(parts[4]);

      const amount = price * volume * 100;

      let type: 'buy' | 'sell' | 'neutral' = 'neutral';
      if (typeCode === 2) type = 'buy';
      if (typeCode === 1) type = 'sell';

      return {
        time: time,
        price: price,
        volume: volume,
        amount: amount,
        type: type,
        color: type === 'buy' ? 'text-red-500' : (type === 'sell' ? 'text-green-500' : 'text-slate-400')
      };
    }).filter((item: any) => item !== null).reverse();
  } catch (e) {
    console.warn("Live tick fetch error:", e);
    return [];
  }
};

export const fetchRealtimeDashboard = async (symbol: string, date?: string): Promise<RealtimeDashboardData | null> => {
  const url = `${API_BASE_URL}/realtime/dashboard?symbol=${symbol}${date ? `&date=${date}` : ''}`;
  try {
    const response = await fetchWithTimeout(url, {}, 10000);
    if (!response.ok) return null;
    const json = await response.json();
    if (json.code === 200) {
      return json.data; // { chart_data, cumulative_data, latest_ticks }
    }
    return null;
  } catch (e) {
    console.error("Realtime dashboard fetch error:", e);
    return null;
  }
};

export const fetchIntradayFusion = async (symbol: string, date?: string): Promise<IntradayFusionData | null> => {
  const url = `${API_BASE_URL}/realtime/intraday_fusion?symbol=${symbol}${date ? `&date=${date}` : ''}`;
  try {
    const response = await fetchWithTimeout(url, {}, 10000);
    if (!response.ok) return null;
    const json = await response.json();
    if (json.code === 200) {
      return json.data;
    }
    return null;
  } catch (e) {
    console.error("Intraday fusion fetch error:", e);
    return null;
  }
};

// ==========================================
// Watchlist API
// ==========================================
export const addToWatchlist = async (symbol: string, name: string) => {
  await fetch(`${API_BASE_URL}/watchlist?symbol=${symbol}&name=${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: getWriteHeaders()
  });
};

export const removeFromWatchlist = async (symbol: string) => {
  await fetch(`${API_BASE_URL}/watchlist?symbol=${symbol}`, {
    method: 'DELETE',
    headers: getWriteHeaders()
  });
};

export const getWatchlist = async (): Promise<any[]> => {
  const res = await fetch(`${API_BASE_URL}/watchlist`);
  return await res.json();
};

// ==========================================
// 5. [NEW] 本地历史与配置
// ==========================================
export const fetchHistoryAnalysis = async (symbol: string, source: 'sina' | 'local' = 'sina'): Promise<HistoryAnalysisData[]> => {
  try {
    const url = `${API_BASE_URL}/history_analysis?symbol=${symbol}&source=${source}`;
    const res = await fetch(url);
    const json = await res.json();
    // 统一处理后端返回的 {code: 200, data: [...]} 格式
    if (json && json.data && Array.isArray(json.data)) {
      return json.data;
    }
    return [];
  } catch (e) {
    console.error("Fetch history error:", e);
    return [];
  }
};

export const fetchHistoryTrend = async (
  symbol: string,
  days: number = 20,
  granularity: '5m' | '15m' | '30m' | '1h' | '1d' = '30m'
): Promise<HistoryTrendData[]> => {
  try {
    const url = `${API_BASE_URL}/history/trend?symbol=${symbol}&days=${days}&granularity=${granularity}`;
    const res = await fetch(url);
    const json = await res.json();
    if (json.code === 200 && Array.isArray(json.data)) {
      return json.data;
    }
    return [];
  } catch (e) {
    console.error("Fetch history trend error:", e);
    return [];
  }
};

export const fetchHistoryMultiframe = async (
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
      granularity: options.granularity || '30m',
      days: String(options.days || 20),
      include_today_preview: options.includeTodayPreview === false ? 'false' : 'true',
    });
    if (options.startDate) params.set('start_date', options.startDate);
    if (options.endDate) params.set('end_date', options.endDate);

    const res = await fetch(`${API_BASE_URL}/history/multiframe?${params.toString()}`);
    const json = await res.json();
    if (json?.code === 200 && Array.isArray(json?.data?.items)) {
      return json.data.items as HistoryMultiframeItem[];
    }
    return [];
  } catch (e) {
    console.error('Fetch history multiframe error:', e);
    return [];
  }
};

export const aggregateLocalHistory = async (symbol: string, date?: string) => {
  const url = `${API_BASE_URL}/aggregate?symbol=${symbol}${date ? `&date=${date}` : ''}`;
  await fetch(url, { method: 'POST' });
};

export const fetchSandboxReviewData = async (
  symbol: string,
  startDate: string,
  endDate: string,
  granularity: '5m' | '15m' | '30m' | '60m' | '1d' = '5m'
): Promise<SandboxReviewBar[]> => {
  const params = new URLSearchParams({
    symbol,
    start_date: startDate,
    end_date: endDate,
    granularity,
  });

  // 兼容不同部署版本的路由前缀，优先新路由。
  const candidates = [
    `${API_BASE_URL}/sandbox/review_data?${params.toString()}`,
    `${API_BASE_URL}/review_data?${params.toString()}`,
    `/sandbox/review_data?${params.toString()}`,
  ];

  let lastError: Error | null = null;
  let saw404 = false;
  for (const url of candidates) {
    try {
      const res = await fetch(url);
      const json = await res.json().catch(() => null);
      if (res.status === 404) {
        saw404 = true;
        continue;
      }
      if (!res.ok) {
        throw new Error(json?.message || `沙盒接口请求失败（HTTP ${res.status}）`);
      }
      if (json?.code === 200 && Array.isArray(json.data)) {
        return json.data as SandboxReviewBar[];
      }
      throw new Error(json?.message || '沙盒接口返回异常');
    } catch (e) {
      lastError = e instanceof Error ? e : new Error('沙盒数据查询失败');
    }
  }

  const routeHint = saw404
    ? `（候选路由均返回404，请确认后端已部署 sandbox 路由并重启：${candidates.join(' / ')}）`
    : '';
  const errorMessage = lastError?.message || '沙盒数据查询失败';
  console.error('Fetch sandbox review data error:', errorMessage, routeHint);
  throw new Error(`${errorMessage}${routeHint}`);
};

export const fetchSandboxReviewPool = async (keyword = '', limit = 0): Promise<{
  total: number;
  as_of_date: string;
  items: SandboxPoolItem[];
}> => {
  const params = new URLSearchParams();
  if (keyword) params.set('keyword', keyword);
  if (limit > 0) params.set('limit', String(limit));

  const candidates = [
    `${API_BASE_URL}/sandbox/pool?${params.toString()}`,
    `${API_BASE_URL}/pool?${params.toString()}`,
    `/sandbox/pool?${params.toString()}`,
  ];

  let lastError: Error | null = null;
  for (const url of candidates) {
    try {
      const res = await fetch(url);
      const json = await res.json().catch(() => null);
      if (res.status === 404) {
        continue;
      }
      if (!res.ok) {
        throw new Error(json?.message || `股票池请求失败（HTTP ${res.status}）`);
      }
      if (json?.code === 200 && json?.data) {
        return {
          total: Number(json.data.total || 0),
          as_of_date: json.data.as_of_date || '',
          items: Array.isArray(json.data.items) ? (json.data.items as SandboxPoolItem[]) : [],
        };
      }
      throw new Error(json?.message || '股票池返回异常');
    } catch (e) {
      lastError = e instanceof Error ? e : new Error('股票池查询失败');
    }
  }

  throw new Error(lastError?.message || '股票池查询失败');
};

export const fetchReviewData = async (
  symbol: string,
  startDate: string,
  endDate: string,
  granularity: '5m' | '15m' | '30m' | '60m' | '1d' = '5m'
): Promise<ReviewBar[]> => {
  const params = new URLSearchParams({
    symbol,
    start_date: startDate,
    end_date: endDate,
    granularity,
  });

  const url = `${API_BASE_URL}/review/data?${params.toString()}`;
  try {
    const res = await fetch(url);
    const json = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(json?.message || `正式复盘接口请求失败（HTTP ${res.status}）`);
    }
    if (json?.code === 200 && Array.isArray(json.data)) {
      return json.data as ReviewBar[];
    }
    throw new Error(json?.message || '正式复盘接口返回异常');
  } catch (e) {
    const errorMessage = e instanceof Error ? e.message : '正式复盘数据查询失败';
    console.error('Fetch review data error:', errorMessage);
    throw new Error(errorMessage);
  }
};

export const fetchReviewPool = async (keyword = '', limit = 0): Promise<{
  total: number;
  as_of_date: string;
  latest_date: string;
  items: ReviewPoolItem[];
}> => {
  const params = new URLSearchParams();
  if (keyword) params.set('keyword', keyword);
  if (limit > 0) params.set('limit', String(limit));

  const url = `${API_BASE_URL}/review/pool?${params.toString()}`;
  try {
    const res = await fetch(url);
    const json = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(json?.message || `正式复盘股票池请求失败（HTTP ${res.status}）`);
    }
    if (json?.code === 200 && json?.data) {
      return {
        total: Number(json.data.total || 0),
        as_of_date: json.data.as_of_date || '',
        latest_date: json.data.latest_date || '',
        items: Array.isArray(json.data.items) ? (json.data.items as ReviewPoolItem[]) : [],
      };
    }
    throw new Error(json?.message || '正式复盘股票池返回异常');
  } catch (e) {
    const errorMessage = e instanceof Error ? e.message : '正式复盘股票池查询失败';
    console.error('Fetch review pool error:', errorMessage);
    throw new Error(errorMessage);
  }
};

export interface SandboxEtlStatus {
  running: boolean;
  mode: string;
  symbol: string;
  start_date: string;
  end_date: string;
  src_root: string;
  output_db: string;
  started_at: string;
  finished_at: string;
  exit_code: number | null;
  message: string;
  log_tail: string[];
}

export const runSandboxReviewEtl = async (payload: {
  mode: 'pilot' | 'full';
  symbol: string;
  start_date: string;
  end_date: string;
  src_root?: string;
  output_db?: string;
}): Promise<{ code: number; message?: string; data?: SandboxEtlStatus }> => {
  const res = await fetch(`${API_BASE_URL}/sandbox/run_etl`, {
    method: 'POST',
    headers: getWriteHeaders(true),
    body: JSON.stringify(payload),
  });
  return await res.json();
};

export const fetchSandboxReviewEtlStatus = async (): Promise<SandboxEtlStatus | null> => {
  try {
    const res = await fetch(`${API_BASE_URL}/sandbox/etl_status`);
    const json = await res.json();
    if (json?.code === 200 && json?.data) {
      return json.data;
    }
    return null;
  } catch (e) {
    console.error('Fetch sandbox etl status error:', e);
    return null;
  }
};

export const getAppConfig = async () => {
  const res = await fetch(`${API_BASE_URL}/config`);
  return await res.json();
};

export const updateAppConfig = async (key: string, value: string) => {
  await fetch(`${API_BASE_URL}/config`, {
    method: 'POST',
    headers: getWriteHeaders(true),
    body: JSON.stringify({ key, value })
  });
};

export const getLLMInfo = async () => {
  try {
    const res = await fetch(`${API_BASE_URL}/config/llm-info`);
    const json = await res.json();
    return json.data || { model: '未配置', base_url: '未配置', key_configured: false };
  } catch (e) {
    return { model: '未配置', base_url: '未配置', key_configured: false };
  }
};

export const testLLMConnection = async () => {
  const res = await fetch(`${API_BASE_URL}/config/test-llm`, {
    method: 'POST',
    headers: getWriteHeaders(true),
    body: JSON.stringify({})
  });
  return await res.json();
};

export const verifyRealtime = async (symbol: string) => {
  const res = await fetch(`${API_BASE_URL}/verify_realtime?symbol=${symbol}`);
  return await res.json();
};

export const fetchSentimentData = async (symbol: string) => {
  const res = await fetch(`${API_BASE_URL}/sentiment?symbol=${symbol}`);
  const json = await res.json();
  return json.data;
};

export const fetchSentimentHistory = async (symbol: string, date?: string) => {
  const url = date
    ? `${API_BASE_URL}/sentiment/history?symbol=${symbol}&date=${date}`
    : `${API_BASE_URL}/sentiment/history?symbol=${symbol}`;
  const res = await fetch(url);
  const json = await res.json();
  return json.data;
};

// ==========================================
// Focus Management (Hot/Cold Queue)
// ==========================================
export const focusSymbol = async (symbol: string) => {
  try {
    await fetch(`${API_BASE_URL}/monitor/focus`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol })
    });
  } catch (e) {
    console.error("Focus error:", e);
  }
};

export const sendHeartbeat = async (symbol: string, mode: 'focus' | 'warm' = 'warm') => {
  try {
    await fetch(`${API_BASE_URL}/monitor/heartbeat?symbol=${symbol}&mode=${mode}`, { method: 'POST' });
  } catch (e) {
    console.error("Heartbeat error:", e);
  }
};

export const unfocusSymbol = async () => {
  try {
    await fetch(`${API_BASE_URL}/monitor/unfocus`, { method: 'POST' });
  } catch (e) {
    console.error("Unfocus error:", e);
  }
};
