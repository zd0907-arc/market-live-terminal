import { RealTimeQuote, TickData, SearchResult, CapitalFlowTrend, HistoryAnalysisData } from '../types';

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
    
    const response = await fetch('http://127.0.0.1:8000/', { 
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
      try { delete (window as any)[varName]; } catch(e){}
      if(document.body.contains(script)) document.body.removeChild(script);
    };
    
    script.onerror = () => {
        if(document.body.contains(script)) document.body.removeChild(script);
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

    try { delete (window as any)[varName]; } catch(e){}
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

  const cb = `cb_ticks_${Date.now()}_${Math.floor(Math.random()*10000)}`;
  const url = `https://push2.eastmoney.com/api/qt/stock/details/get?secid=${marketId}.${code}&fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55&pos=-50&iscca=1&invt=2&cb=${cb}`;

  try {
    const res = await jsonp(url, cb, 3000);
    const data = res?.data?.details;
    
    if (!data || !Array.isArray(data)) return [];

    return data.map((itemStr: string) => {
      const parts = itemStr.split(',');
      if(parts.length < 5) return null;

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

// 新版：从本地后端获取全天数据
export const fetchTicks = async (symbol: string): Promise<TickData[]> => {
    const url = `http://127.0.0.1:8000/api/ticks_full?symbol=${symbol}`;
    try {
        const response = await fetch(url);
        if (!response.ok) return [];
        const json = await response.json();
        if (json.code === 200 && Array.isArray(json.data)) {
            return json.data.map((t: any) => ({
                time: t.time,
                price: t.price,
                volume: t.volume,
                amount: t.amount,
                type: t.type,
                color: t.type === 'buy' ? 'text-red-500' : (t.type === 'sell' ? 'text-green-500' : 'text-slate-400')
            }));
        }
        return [];
    } catch (e) {
        console.error("Full tick fetch error:", e);
        return [];
    }
};

// ==========================================
// Watchlist API
// ==========================================
export const addToWatchlist = async (symbol: string, name: string) => {
    await fetch(`http://127.0.0.1:8000/api/watchlist?symbol=${symbol}&name=${encodeURIComponent(name)}`, { method: 'POST' });
};

export const removeFromWatchlist = async (symbol: string) => {
    await fetch(`http://127.0.0.1:8000/api/watchlist?symbol=${symbol}`, { method: 'DELETE' });
};

export const getWatchlist = async (): Promise<any[]> => {
    const res = await fetch('http://127.0.0.1:8000/api/watchlist');
    return await res.json();
};

// ==========================================
// 5. [NEW] 本地历史与配置
// ==========================================
export const fetchHistoryAnalysis = async (symbol: string, source: 'sina' | 'local' = 'sina'): Promise<HistoryAnalysisData[]> => {
  try {
    const url = `http://127.0.0.1:8000/api/history_analysis?symbol=${symbol}&source=${source}`;
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

export const aggregateLocalHistory = async (symbol: string, date?: string) => {
    const url = `http://127.0.0.1:8000/api/aggregate?symbol=${symbol}${date ? `&date=${date}` : ''}`;
    await fetch(url, { method: 'POST' });
};

export const getAppConfig = async () => {
    const res = await fetch('http://127.0.0.1:8000/api/config');
    return await res.json();
};

export const updateAppConfig = async (key: string, value: string) => {
    await fetch(`http://127.0.0.1:8000/api/config?key=${key}&value=${value}`, { method: 'POST' });
};

export const verifyRealtime = async (symbol: string) => {
    const res = await fetch(`http://127.0.0.1:8000/api/verify_realtime?symbol=${symbol}`);
    return await res.json();
};
