import React, { useState, useEffect, useRef } from 'react';
import { Search, Activity, ArrowUp, ArrowDown, Clock, Wifi, AlertCircle, RefreshCw, BarChart3, TrendingUp, Info, Calendar, Zap, Layers, Server, Star, Play, Pause, Eye, BookOpen, Settings, Split, CheckCircle2, Database } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine, AreaChart, Area, ComposedChart, Bar, Cell } from 'recharts';
import { RealTimeQuote, TickData, SearchResult, CapitalRatioData, HistoryAnalysisData } from './types';
import * as StockService from './services/stockService';

// ==========================================
// Sub-Components
// ==========================================

// Config Modal Component
const ConfigModal = ({ isOpen, onClose, onSave }: any) => {
    const [superThreshold, setSuperThreshold] = useState('1000000');
    const [largeThreshold, setLargeThreshold] = useState('200000');

    useEffect(() => {
        if(isOpen) {
            StockService.getAppConfig().then(cfg => {
                if(cfg.super_large_threshold) setSuperThreshold(cfg.super_large_threshold);
                if(cfg.large_threshold) setLargeThreshold(cfg.large_threshold);
            });
        }
    }, [isOpen]);

    const handleSave = async () => {
        await StockService.updateAppConfig('super_large_threshold', superThreshold);
        await StockService.updateAppConfig('large_threshold', largeThreshold);
        onSave();
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[100]">
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-96 shadow-2xl">
                <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                    <Settings className="w-5 h-5 text-blue-400" />
                    本地主力判定规则
                </h3>
                <div className="space-y-4">
                    <div>
                        <label className="block text-xs text-slate-400 mb-1">超大单阈值 (元)</label>
                        <input 
                            type="number" 
                            value={superThreshold}
                            onChange={e => setSuperThreshold(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white font-mono"
                        />
                    </div>
                    <div>
                        <label className="block text-xs text-slate-400 mb-1">大单阈值 (元)</label>
                        <input 
                            type="number" 
                            value={largeThreshold}
                            onChange={e => setLargeThreshold(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white font-mono"
                        />
                    </div>
                </div>
                <div className="flex justify-end gap-3 mt-6">
                    <button onClick={onClose} className="px-4 py-2 text-slate-400 hover:text-white transition-colors">取消</button>
                    <button onClick={handleSave} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">保存规则</button>
                </div>
            </div>
        </div>
    );
};

// Source Control Bar
const DataSourceControl = ({ mode, source, setSource, compareMode, setCompareMode, onVerify }: any) => {
    return (
        <div className="flex items-center gap-3 bg-slate-950/50 p-1.5 rounded-lg border border-slate-800/50">
            <div className="flex items-center gap-2 px-2">
                <Layers className="w-4 h-4 text-slate-500" />
                <span className="text-xs text-slate-400">数据源:</span>
                <select 
                    value={source} 
                    onChange={(e) => setSource(e.target.value)}
                    className="bg-transparent text-sm font-medium text-blue-400 focus:outline-none cursor-pointer"
                >
                    {mode === 'realtime' ? (
                        <>
                            <option value="tencent">🟢 腾讯 (Tencent)</option>
                            <option value="eastmoney">🔵 东财 (Eastmoney)</option>
                        </>
                    ) : (
                        <>
                            <option value="sina">🔴 新浪 (Sina)</option>
                            <option value="local">🟣 本地自算 (Local)</option>
                        </>
                    )}
                </select>
            </div>
            
            <div className="w-px h-4 bg-slate-700"></div>
            
            <button 
                onClick={() => setCompareMode(!compareMode)}
                className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${compareMode ? 'bg-blue-500/20 text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}
                title="开启双屏对比"
            >
                <Split className="w-3.5 h-3.5" />
                <span className="text-xs">对比</span>
            </button>
            
            {mode === 'realtime' && (
                <button 
                    onClick={onVerify}
                    className="flex items-center gap-1.5 px-2 py-1 text-slate-500 hover:text-green-400 transition-colors"
                    title="多源实时校验"
                >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                </button>
            )}
        </div>
    );
};

// 主力资金阈值配置 (参考 Wind/东方财富 机构标准)
const MAIN_FORCE_THRESHOLD = 500000; // 50万
const SUPER_LARGE_THRESHOLD = 1000000; // 100万

const App: React.FC = () => {
  // State
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [activeStock, setActiveStock] = useState<SearchResult | null>(null);
  
  // Search History
  const [searchHistory, setSearchHistory] = useState<SearchResult[]>([]);
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  // View Mode & Source
  const [viewMode, setViewMode] = useState<'realtime' | 'history'>('realtime');
  
  // Realtime State
  const [realtimeSource, setRealtimeSource] = useState('tencent');
  const [realtimeCompareMode, setRealtimeCompareMode] = useState(false);
  const [realtimeCompareSource, setRealtimeCompareSource] = useState('eastmoney');
  const [verifyData, setVerifyData] = useState<any>(null);

  // History State
  const [historySource, setHistorySource] = useState('sina');
  const [historyCompareMode, setHistoryCompareMode] = useState(false);
  const [historyCompareSource, setHistoryCompareSource] = useState('local');
  const [historyCompareData, setHistoryCompareData] = useState<HistoryAnalysisData[]>([]);
  
  // Config
  const [showConfig, setShowConfig] = useState(false);
  
  const [quote, setQuote] = useState<RealTimeQuote | null>(null);
  
  // Realtime Data
  const allTicksRef = useRef<TickData[]>([]);
  const [displayTicks, setDisplayTicks] = useState<TickData[]>([]); 
  const [chartData, setChartData] = useState<CapitalRatioData[]>([]);
  
  // History Data
  const [historyData, setHistoryData] = useState<HistoryAnalysisData[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');

  // Watchlist & Refresh Control
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState<number>(30000); // 默认30秒
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [manualRefreshTrigger, setManualRefreshTrigger] = useState(0);

  // System Status
  const [backendStatus, setBackendStatus] = useState<boolean>(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [lastUpdate, setLastUpdate] = useState<string>('');

  const handleSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
  };
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (query.length > 1) {
        const res = await StockService.searchStock(query);
        setResults(res);
      } else {
        setResults([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // 加载搜索历史
  useEffect(() => {
    try {
      const saved = localStorage.getItem('stock_search_history');
      if (saved) {
        setSearchHistory(JSON.parse(saved));
      }
    } catch (e) {
      console.warn('Failed to load search history');
    }
  }, []);

  // 后端健康检查 (Heartbeat)
  useEffect(() => {
    const check = async () => {
      const isHealthy = await StockService.checkBackendHealth();
      setBackendStatus(isHealthy);
    };
    check();
    const interval = setInterval(check, 5000); // Check every 5s
    return () => clearInterval(interval);
  }, []);

  // 重置数据
  const handleSelectStock = (stock: SearchResult) => {
    setActiveStock(stock);
    setQuery('');
    setResults([]);
    setQuote(null);
    allTicksRef.current = []; // 清空历史
    setDisplayTicks([]);
    setChartData([]);
    setError('');
    setIsSearchFocused(false);
    setIsWatchlisted(false);
    
    // Check if watchlisted
    StockService.getWatchlist().then(list => {
        if (list.find(item => item.symbol === stock.symbol)) {
            setIsWatchlisted(true);
        }
    });

    // 更新历史记录
    const newHistory = [stock, ...searchHistory.filter(s => s.symbol !== stock.symbol)].slice(0, 10);
    setSearchHistory(newHistory);
    localStorage.setItem('stock_search_history', JSON.stringify(newHistory));

    // 重置历史数据
    setHistoryData([]);
    setHistoryError('');
    if (viewMode === 'history') {
      loadHistoryData(stock.symbol);
    }
  };

  const toggleWatchlist = async () => {
      if (!activeStock) return;
      if (isWatchlisted) {
          await StockService.removeFromWatchlist(activeStock.symbol);
          setIsWatchlisted(false);
      } else {
          await StockService.addToWatchlist(activeStock.symbol, activeStock.name);
          setIsWatchlisted(true);
      }
  };

  // 切换模式时加载数据
  useEffect(() => {
    if (viewMode === 'history' && activeStock && historyData.length === 0) {
      loadHistoryData(activeStock.symbol);
    }
  }, [viewMode, activeStock]);

  const loadHistoryData = async (symbol: string, source: 'sina' | 'local' = 'sina') => {
    setHistoryLoading(true);
    setHistoryError('');
    try {
      const data = await StockService.fetchHistoryAnalysis(symbol, source);
      if (source === 'sina') {
          setHistoryData(data);
      } else {
          setHistoryCompareData(data);
      }
    } catch (e: any) {
      setHistoryError(e.message || '获取历史数据失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleVerifyRealtime = async () => {
      if(!activeStock) return;
      const res = await StockService.verifyRealtime(activeStock.symbol);
      setVerifyData(res);
      setTimeout(() => setVerifyData(null), 5000); // 5秒后自动关闭校验提示
  };
  
  // Check trading hours
  const isTradingHours = () => {
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const time = hours * 100 + minutes;
    return (time >= 930 && time <= 1130) || (time >= 1300 && time <= 1500);
  };

  const hasRealtimeData = displayTicks.length > 0;
  const showEmptyState = !loading && !hasRealtimeData && !isTradingHours();

  // 监听历史源切换
  useEffect(() => {
      if (viewMode === 'history' && activeStock) {
          loadHistoryData(activeStock.symbol, historySource as any);
      }
  }, [historySource, activeStock, viewMode]);

  // 监听历史对比源切换
  useEffect(() => {
      if (viewMode === 'history' && activeStock && historyCompareMode) {
          loadHistoryData(activeStock.symbol, historyCompareSource as any);
      }
  }, [historyCompareSource, historyCompareMode, activeStock]);

  // 核心计算逻辑：基于分钟聚合计算三条曲线
  const recalcChartData = () => {
    const ticks = allTicksRef.current;
    if (ticks.length === 0) return;

    // 按分钟聚合
    const buckets: { [key: string]: { mainBuy: number, mainSell: number, totalAmount: number } } = {};

    ticks.forEach(t => {
      // time format HH:mm:ss -> key HH:mm
      const key = t.time.substring(0, 5);
      if (!buckets[key]) buckets[key] = { mainBuy: 0, mainSell: 0, totalAmount: 0 };

      buckets[key].totalAmount += t.amount;

      if (t.amount >= MAIN_FORCE_THRESHOLD) {
        if (t.type === 'buy') buckets[key].mainBuy += t.amount;
        if (t.type === 'sell') buckets[key].mainSell += t.amount;
      }
    });

    // 转换为数组并按时间排序
    const sortedKeys = Object.keys(buckets).sort();
    
    const result: CapitalRatioData[] = sortedKeys.map(timeKey => {
      const b = buckets[timeKey];
      const safeTotal = b.totalAmount || 1; // 避免除以0
      
      const mainBuyRatio = (b.mainBuy / safeTotal) * 100;
      const mainSellRatio = (b.mainSell / safeTotal) * 100;
      const mainParticipationRatio = ((b.mainBuy + b.mainSell) / safeTotal) * 100;

      return {
        time: timeKey,
        mainBuyRatio: parseFloat(mainBuyRatio.toFixed(1)),
        mainSellRatio: parseFloat(mainSellRatio.toFixed(1)),
        mainParticipationRatio: parseFloat(mainParticipationRatio.toFixed(1))
      };
    });

    setChartData(result);
  };

  // 逐笔成交数据处理 (Table & Chart Accumulation)
  const processNewTicks = (newTicks: TickData[]) => {
    if (newTicks.length === 0) return;
    const currentAll = allTicksRef.current;
    
    let uniqueNewTicks: TickData[] = [];

    if (currentAll.length === 0) {
      uniqueNewTicks = [...newTicks].reverse();
    } else {
      const lastKnownTick = currentAll[currentAll.length - 1];
      const sortedNewTicks = [...newTicks].reverse();
      
      let matchIndex = -1;
      // 倒序查找，匹配最近的相同 tick
      for (let i = sortedNewTicks.length - 1; i >= 0; i--) {
        const t = sortedNewTicks[i];
        if (
          t.time === lastKnownTick.time && 
          t.price === lastKnownTick.price && 
          t.volume === lastKnownTick.volume &&
          t.type === lastKnownTick.type
        ) {
          matchIndex = i;
          break;
        }
      }
      
      if (matchIndex !== -1) {
        uniqueNewTicks = sortedNewTicks.slice(matchIndex + 1);
      } else {
        if (sortedNewTicks[0].time >= lastKnownTick.time) {
             uniqueNewTicks = sortedNewTicks;
        }
      }
    }

    if (uniqueNewTicks.length > 0) {
      allTicksRef.current = [...allTicksRef.current, ...uniqueNewTicks];
      const uiList = [...allTicksRef.current].reverse().slice(0, 100);
      setDisplayTicks(uiList);
      recalcChartData();
    }
  };

  // 数据轮询
  useEffect(() => {
    if (!activeStock) return;

    let isMounted = true;
    let intervalId: any = null;

    const fetchData = async (isFirstLoad = false) => {
      if (!isMounted) return;
      if (isFirstLoad) setLoading(true);
      
      try {
        const quotePromise = StockService.fetchQuote(activeStock.symbol);
        // 使用新的 fetchTicks (优先从后端获取全天数据)
        const ticksPromise = StockService.fetchTicks(activeStock.symbol);
        
        const q = await quotePromise;
        if (isMounted) {
          setQuote(q);
          setLastUpdate(new Date().toLocaleTimeString());
          setError('');
        }

        try {
          const t = await ticksPromise;
          if (isMounted) processNewTicks(t);
        } catch (tickErr) {
          console.warn("Ticks update failed", tickErr);
        }

      } catch (err) {
        console.error("Main fetch loop error:", err);
        if (isMounted && !quote) {
             setError('无法连接行情服务器');
        }
      } finally {
        if (isMounted && isFirstLoad) setLoading(false);
      }
    };

    fetchData(true);
    
    // 只有在 isRefreshing 为 true 时才启动定时器
    if (isRefreshing && refreshInterval > 0) {
        intervalId = setInterval(() => fetchData(false), refreshInterval);
    }

    return () => {
        isMounted = false;
        if (intervalId) clearInterval(intervalId);
    };
  }, [activeStock, isRefreshing, refreshInterval, manualRefreshTrigger]);

  const getPriceColor = (current: number, base: number) => {
    if (current > base) return 'text-red-500';
    if (current < base) return 'text-green-500';
    return 'text-slate-200';
  };

  const formatAmount = (num: number) => {
    if (num > 100000000) return (num / 100000000).toFixed(2) + '亿';
    if (num > 10000) return (num / 10000).toFixed(0) + '万';
    return num.toFixed(0);
  };

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200 font-sans selection:bg-blue-900 pb-20">
      {/* 顶部导航与搜索 */}
      <header className="sticky top-0 z-50 bg-[#0f1623]/95 backdrop-blur border-b border-slate-800 p-4">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 font-bold text-lg text-red-500">
            <Activity className="w-6 h-6" />
            <span>ZhangData</span>
          </div>
          
          <div className="flex-1 flex justify-center">
             {/* 彻底移除顶部中央的切换按钮 */}
          </div>
          
          <div className="relative flex-1 max-w-md w-full flex items-center gap-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 text-slate-400 w-5 h-5" />
                <input
                  type="text"
                  placeholder="输入代码 (600519) 或简称 (茅台)..."
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-10 pr-4 py-2 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                  value={query}
                  onChange={handleSearch}
                  onFocus={() => setIsSearchFocused(true)}
                  onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
                />
                {/* Search Results Dropdown ... */}
                {/* ... */}
              </div>

              {/* 唯一的视图切换入口 (Toggle Group) */}
              <div className="flex gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800">
                  <button 
                    onClick={() => setViewMode('realtime')}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${viewMode === 'realtime' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
                  >
                    <Activity className="w-4 h-4" /> 实时
                  </button>
                  <button 
                    onClick={() => setViewMode('history')}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${viewMode === 'history' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
                  >
                    <BarChart3 className="w-4 h-4" /> 历史
                  </button>
               </div>
          </div>

            {/* 搜索历史下拉框 */}
            {isSearchFocused && !query && searchHistory.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-80 overflow-y-auto z-50">
                 <div className="px-3 py-2 text-xs text-slate-500 bg-slate-900/50 border-b border-slate-700 flex justify-between items-center">
                    <span>最近访问</span>
                    <span className="text-[10px] bg-slate-700 px-1.5 py-0.5 rounded text-slate-300">History</span>
                 </div>
                 {searchHistory.map((res) => (
                    <button
                      key={res.symbol}
                      onClick={() => handleSelectStock(res)}
                      className="w-full text-left px-4 py-2 hover:bg-slate-700 flex justify-between items-center group transition-colors border-b border-slate-800/50 last:border-0"
                    >
                       <div className="flex items-center gap-2">
                          <Clock className="w-3.5 h-3.5 text-slate-500 group-hover:text-blue-400 transition-colors" />
                          <span className="font-medium text-slate-300">{res.name}</span>
                       </div>
                       <div className="flex items-center gap-2">
                          <span className="text-xs text-slate-500 font-mono">{res.code}</span>
                          <span className="text-[10px] text-slate-600 uppercase border border-slate-700 px-1 rounded">{res.market}</span>
                       </div>
                    </button>
                  ))}
              </div>
            )}

            {results.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-60 overflow-y-auto z-50">
                {results.map((res) => (
                  <button
                    key={res.symbol}
                    onClick={() => handleSelectStock(res)}
                    className="w-full text-left px-4 py-3 hover:bg-slate-700 flex justify-between items-center group transition-colors"
                  >
                    <div>
                      <span className="font-bold text-white">{res.name}</span>
                      <span className="ml-2 text-xs text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded">{res.code}</span>
                    </div>
                    <span className="text-xs text-slate-500 group-hover:text-blue-400 uppercase">{res.market}</span>
                  </button>
                ))}
              </div>
            )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 md:p-6 space-y-6">
        <ConfigModal isOpen={showConfig} onClose={() => setShowConfig(false)} onSave={() => {
            // 重新加载本地数据
            if(historySource === 'local') loadHistoryData(activeStock!.symbol, 'local');
            if(historyCompareMode && historyCompareSource === 'local') loadHistoryData(activeStock!.symbol, 'local');
        }} />
        
        {/* 多源验证浮窗 (Verify Toast) */}
        {verifyData && (
            <div className="fixed top-20 right-4 z-50 bg-slate-900 border border-slate-700 p-4 rounded-lg shadow-2xl animate-in fade-in slide-in-from-right-10">
                <h4 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-green-400" /> 多源实时校验
                </h4>
                <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                        <div className="text-slate-500 mb-1">腾讯 (Tencent)</div>
                        <div className="font-mono text-white text-lg">{verifyData.tencent.price?.toFixed(2)}</div>
                        <div className="text-slate-400">{verifyData.tencent.time}</div>
                    </div>
                    <div className="border-l border-slate-700 pl-4">
                        <div className="text-slate-500 mb-1">东财 (Eastmoney)</div>
                        <div className={`font-mono text-lg ${verifyData.eastmoney.price === verifyData.tencent.price ? 'text-green-400' : 'text-yellow-400'}`}>
                            {verifyData.eastmoney.price?.toFixed(2)}
                        </div>
                        <div className="text-slate-400">{verifyData.eastmoney.time}</div>
                    </div>
                </div>
            </div>
        )}

        {activeStock && (
             <div className="flex justify-end items-center mb-2">
                    {/* 数据源控制器 (Moved here) */}
                    <div className="flex gap-2">
                        {viewMode === 'history' && (historySource === 'local' || (historyCompareMode && historyCompareSource === 'local')) && (
                            <button 
                              onClick={() => setShowConfig(true)}
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-slate-400 hover:text-white hover:border-slate-600 transition-colors text-xs"
                            >
                                <Settings className="w-3.5 h-3.5" /> 规则设置
                            </button>
                        )}
                        
                        <DataSourceControl 
                            mode={viewMode}
                            source={viewMode === 'realtime' ? realtimeSource : historySource}
                            setSource={viewMode === 'realtime' ? setRealtimeSource : setHistorySource}
                            compareMode={viewMode === 'realtime' ? realtimeCompareMode : historyCompareMode}
                            setCompareMode={viewMode === 'realtime' ? setRealtimeCompareMode : setHistoryCompareMode}
                            onVerify={handleVerifyRealtime}
                        />
                    </div>
             </div>
         )}
         {activeStock && (
             <div className="flex justify-between items-center mb-4 hidden">
                    {/* 彻底移除旧的切换区域 */}
             </div>
         )}
        {!activeStock && !loading && !quote && (
          <div className="text-center py-20 text-slate-500">
            <Activity className="w-16 h-16 mx-auto mb-4 opacity-20" />
            <p>请输入股票代码开始监控</p>
            <p className="text-xs mt-2 opacity-60">模式：实时逐笔 (Web) | 历史博弈 (Python Local)</p>
          </div>
        )}

        {loading && !quote && (
          <div className="text-center py-20 text-blue-400 flex flex-col items-center gap-3">
             <RefreshCw className="w-8 h-8 animate-spin" />
             <span>正在建立高速数据链路...</span>
          </div>
        )}

        {error && !quote && (
          <div className="bg-red-900/20 border border-red-800 p-4 rounded-lg flex items-center gap-3 text-red-200">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        {quote && (
           <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg relative overflow-hidden mb-6">
              <div className={`absolute -top-10 -right-10 w-40 h-40 rounded-full blur-[80px] opacity-20 pointer-events-none ${quote.price >= quote.lastClose ? 'bg-red-500' : 'bg-green-500'}`}></div>

              <div className="flex justify-between items-start mb-6 relative z-10">
                <div>
                  <h1 className="text-2xl font-bold text-white mb-1 flex items-center gap-3">
                    {quote.name} 
                    <span className="text-sm font-mono text-slate-500 font-normal bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                      {quote.symbol.toUpperCase()}
                    </span>
                    <button 
                        onClick={toggleWatchlist}
                        className={`p-1.5 rounded-full transition-colors ${isWatchlisted ? 'text-yellow-400 bg-yellow-400/10' : 'text-slate-600 hover:text-slate-400 hover:bg-slate-800'}`}
                        title={isWatchlisted ? "取消全天监控" : "加入全天监控 (后台自动存储)"}
                    >
                        <Star className={`w-5 h-5 ${isWatchlisted ? 'fill-yellow-400' : ''}`} />
                    </button>
                  </h1>
                  <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 mt-2">
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {quote.date} {quote.time}</span>
                      
                      <span className="w-px h-3 bg-slate-700"></span>
                      
                      {/* Refresh Controls (Only for Realtime) */}
                      {viewMode === 'realtime' && (
                        <div className="flex items-center gap-2 bg-slate-950 px-2 py-1 rounded border border-slate-800">
                            <button 
                               onClick={() => setIsRefreshing(!isRefreshing)}
                               className={`p-1 rounded hover:bg-slate-800 ${isRefreshing ? 'text-green-400' : 'text-slate-500'}`}
                               title={isRefreshing ? "暂停刷新" : "继续刷新"}
                            >
                                {isRefreshing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                            </button>
                            
                            <select 
                               value={refreshInterval} 
                               onChange={(e) => setRefreshInterval(Number(e.target.value))}
                               className="bg-transparent text-slate-400 text-xs focus:outline-none border-none cursor-pointer w-16"
                               disabled={!isRefreshing}
                            >
                                <option value="5000">5秒</option>
                                <option value="15000">15秒</option>
                                <option value="30000">30秒</option>
                                <option value="60000">1分钟</option>
                            </select>

                            <button 
                               onClick={() => setManualRefreshTrigger(prev => prev + 1)}
                               className="p-1 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
                               title="立即刷新"
                            >
                                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                            </button>
                        </div>
                      )}
                      
                      {viewMode === 'history' && (
                         <div className="flex items-center gap-2 text-slate-400">
                            <BookOpen className="w-3 h-3" />
                            <span>历史复盘模式</span>
                         </div>
                      )}

                      <span className="w-px h-3 bg-slate-700"></span>
                      
                      {/* API Status Indicators */}
                      <span className="flex items-center gap-1 text-slate-400">
                         <Wifi className="w-3 h-3 text-green-500" /> API: Tencent
                      </span>

                      <span className="w-px h-3 bg-slate-700"></span>

                      <span className={`flex items-center gap-1 transition-colors ${backendStatus ? 'text-green-500' : 'text-red-500'}`}>
                         <Server className="w-3 h-3" />
                         {backendStatus ? 'Python: Connected' : 'Python: Disconnected'}
                      </span>
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-5xl font-mono font-bold tracking-tight ${getPriceColor(quote.price, quote.lastClose)}`}>
                    {quote.price.toFixed(2)}
                  </div>
                  <div className={`mt-2 text-lg font-mono flex items-center justify-end gap-3 ${getPriceColor(quote.price, quote.lastClose)}`}>
                      <span className="flex items-center">
                        {quote.price >= quote.lastClose ? <ArrowUp className="w-4 h-4 mr-1"/> : <ArrowDown className="w-4 h-4 mr-1"/>}
                        {(quote.price - quote.lastClose).toFixed(2)}
                      </span>
                      <span className="bg-slate-800 px-2 py-0.5 rounded text-sm">
                        {((quote.price - quote.lastClose) / quote.lastClose * 100).toFixed(2)}%
                      </span>
                  </div>
                </div>
              </div>

              {/* Context-Aware Info Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 relative z-10">
                  {viewMode === 'realtime' ? (
                      <>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1 flex items-center gap-1"><Activity className="w-3 h-3"/> 实时成交量</div>
                            <div className="font-mono text-slate-200">{formatAmount(quote.volume)}股</div>
                        </div>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1 flex items-center gap-1"><Activity className="w-3 h-3"/> 实时成交额</div>
                            <div className="font-mono text-slate-200">{formatAmount(quote.amount)}</div>
                        </div>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1">今开/昨收</div>
                            <div className="font-mono text-slate-200">{quote.open.toFixed(2)} / {quote.lastClose.toFixed(2)}</div>
                        </div>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1">最高/最低</div>
                            <div className="font-mono text-slate-200">{quote.high.toFixed(2)} / {quote.low.toFixed(2)}</div>
                        </div>
                      </>
                  ) : (
                      <>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1 flex items-center gap-1"><Calendar className="w-3 h-3"/> 数据日期</div>
                            <div className="font-mono text-slate-200">{historyData.length > 0 ? historyData[historyData.length-1].date : '-'}</div>
                        </div>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1 flex items-center gap-1"><TrendingUp className="w-3 h-3"/> 主力净流入(最新)</div>
                            <div className={`font-mono ${historyData.length > 0 && historyData[historyData.length-1].net_inflow > 0 ? 'text-red-500' : 'text-green-500'}`}>
                                {historyData.length > 0 ? (historyData[historyData.length-1].net_inflow / 100000000).toFixed(2) + '亿' : '-'}
                            </div>
                        </div>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1 flex items-center gap-1"><Zap className="w-3 h-3"/> 主力活跃度(最新)</div>
                            <div className="font-mono text-yellow-400">
                                {historyData.length > 0 ? historyData[historyData.length-1].activityRatio.toFixed(1) + '%' : '-'}
                            </div>
                        </div>
                        <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800/50">
                            <div className="text-xs text-slate-500 mb-1">收盘价(最新)</div>
                            <div className="font-mono text-slate-200">
                                {historyData.length > 0 ? historyData[historyData.length-1].close.toFixed(2) : '-'}
                            </div>
                        </div>
                      </>
                  )}
              </div>
           </div>
        )}

        {/* ======================= 实时视图 ======================= */}
        {quote && viewMode === 'realtime' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
               {/* 实时主力监控图表 */}
               <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg relative">
                  {/* Control Bar inside Chart Card */}
                  <div className="absolute top-4 right-4 z-20">
                    <DataSourceControl 
                        mode="realtime"
                        source={realtimeSource}
                        setSource={setRealtimeSource}
                        compareMode={realtimeCompareMode}
                        setCompareMode={setRealtimeCompareMode}
                        onVerify={handleVerifyRealtime}
                    />
                  </div>

                  <div className="flex items-center justify-between mb-6">
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-blue-400" />
                      主力动态 (实时)
                    </h3>
                    <div className="text-xs text-slate-500 flex items-center gap-2">
                       <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-red-500 mr-1"></span>主买</span>
                       <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-green-500 mr-1"></span>主卖</span>
                       <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-yellow-400 mr-1"></span>参与度</span>
                    </div>
                  </div>
                  
                  <div className="h-[300px] w-full">
                    {chartData.length > 1 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                          <XAxis dataKey="time" stroke="#64748b" tick={{fontSize: 12}} minTickGap={30} />
                          <YAxis stroke="#64748b" tick={{fontSize: 12}} unit="%" domain={[0, 'auto']} />
                          <Tooltip 
                            contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                            itemStyle={{fontSize: 12}}
                          />
                          <Legend wrapperStyle={{fontSize: 12}} />
                          <Line type="monotone" dataKey="mainBuyRatio" name="买入占比" stroke="#ef4444" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="mainSellRatio" name="卖出占比" stroke="#22c55e" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="mainParticipationRatio" name="参与度" stroke="#eab308" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                        等待更多交易数据生成图表...
                      </div>
                    )}
                  </div>
               </div>
            </div>

            {/* 右侧：逐笔成交明细 */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg h-[400px] flex flex-col">
               <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                 <h3 className="font-bold text-slate-200 flex items-center gap-2">
                   <Layers className="w-4 h-4 text-blue-400" />
                   Level-1 逐笔
                 </h3>
                 <span className="text-xs text-slate-500 animate-pulse flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Live
                 </span>
               </div>
               <div className="flex-1 overflow-y-auto p-0">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-950 sticky top-0 text-slate-500">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium">时间</th>
                        <th className="px-3 py-2 text-right font-medium">价格</th>
                        <th className="px-3 py-2 text-right font-medium">量(手)</th>
                        <th className="px-3 py-2 text-right font-medium">额(万)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                       {displayTicks.map((t, idx) => (
                         <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                           <td className="px-3 py-1.5 text-slate-400 font-mono">{t.time}</td>
                           <td className={`px-3 py-1.5 text-right font-mono font-medium ${t.color}`}>
                             {t.price.toFixed(2)}
                           </td>
                           <td className="px-3 py-1.5 text-right text-slate-300 font-mono">
                             {t.volume}
                           </td>
                           <td className="px-3 py-1.5 text-right text-slate-500 font-mono">
                             {(t.amount / 10000).toFixed(1)}
                             {t.amount > SUPER_LARGE_THRESHOLD && <span className="ml-1 text-purple-400 font-bold">*</span>}
                           </td>
                         </tr>
                       ))}
                       {displayTicks.length === 0 && (
                         <tr><td colSpan={4} className="text-center py-10 text-slate-600">等待逐笔数据...</td></tr>
                       )}
                    </tbody>
                  </table>
               </div>
            </div>
          </div>
        )}

        {/* ======================= 历史博弈视图 ======================= */}
        {quote && viewMode === 'history' && (
          <div className="space-y-6">
            {/* 后端状态提示 (如果断开) */}
            {!backendStatus && (
               <div className="bg-red-950/30 border border-red-900/50 p-3 rounded-lg flex items-center gap-3 text-red-300 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  <span>
                    本地 Python 服务未连接 (端口 8001)。请在终端运行：
                    <code className="bg-black/30 px-2 py-0.5 rounded ml-2 text-red-200 font-mono">python server.py</code>
                  </span>
               </div>
            )}

            {historyError && (
              <div className="bg-red-900/20 border border-red-800 p-4 rounded-lg flex items-center gap-3 text-red-200">
                <AlertCircle className="w-5 h-5" />
                <span>{historyError}</span>
              </div>
            )}

            {historyLoading && (
              <div className="py-20 text-center text-blue-400 flex flex-col items-center">
                 <RefreshCw className="w-8 h-8 animate-spin mb-4" />
                 <p>正在从本地引擎加载历史资金数据...</p>
              </div>
            )}

            {!historyLoading && !historyError && historyData.length > 0 && (
            <div className={`grid ${historyCompareMode ? 'grid-cols-2' : 'grid-cols-1'} gap-6`}>
               {/* 左侧 (主) */}
               <div className="space-y-6">
                 {/* 1. 主力净流入 */}
                 <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg relative">
                    {/* Control Bar inside Chart Card (For History View - Main) */}
                    {!historyCompareMode && (
                        <div className="absolute top-4 right-4 z-20">
                            <DataSourceControl 
                                mode="history"
                                source={historySource}
                                setSource={setHistorySource}
                                compareMode={historyCompareMode}
                                setCompareMode={setHistoryCompareMode}
                            />
                        </div>
                    )}

                    <div className="mb-6 flex justify-between items-center">
                       <h3 className="text-lg font-bold text-white flex items-center gap-2">
                           {historySource === 'sina' ? <span className="text-red-500">🔴 新浪数据</span> : <span className="text-purple-500">🟣 本地自算</span>}
                           主力净流入
                       </h3>
                    </div>
                    <div className="h-[300px]">
                       <ResponsiveContainer width="100%" height="100%">
                         <ComposedChart data={historyData} syncId="historyGraph">
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                    <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 12}} />
                                    {/* Left Y-Axis: Net Inflow */}
                                    <YAxis yAxisId="left" stroke="#64748b" tick={{fontSize: 12}} tickFormatter={(val) => (val/100000000).toFixed(0)} />
                                    {/* Right Y-Axis: Price */}
                                    <YAxis yAxisId="right" orientation="right" stroke="#fbbf24" tick={{fontSize: 12}} domain={['auto', 'auto']} />
                                    
                                    <Tooltip 
                                        position={{ y: 0 }}
                                        contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                        formatter={(val: number, name: string) => {
                                            if (name === '收盘价') return val.toFixed(2);
                                            return (val/100000000).toFixed(2) + '亿';
                                        }} 
                                    />
                                    <Legend />
                                    <ReferenceLine y={0} yAxisId="left" stroke="#334155" />
                                    <Bar yAxisId="left" dataKey="net_inflow" name="主力净流入">
                                      {historyData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.net_inflow > 0 ? '#ef4444' : '#22c55e'} />
                                      ))}
                                    </Bar>
                                    <Line yAxisId="right" type="monotone" dataKey="close" name="收盘价" stroke="#fbbf24" strokeWidth={2} dot={false} />
                                 </ComposedChart>
                       </ResponsiveContainer>
                    </div>
                 </div>

                 {/* 2. 买卖力度分离 */}
                 <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
                    <div className="mb-6 flex items-center gap-2">
                       <h3 className="text-lg font-bold text-white">买卖力度分离监控</h3>
                       <div className="group relative">
                          <Info className="w-4 h-4 text-slate-500 cursor-help hover:text-blue-400" />
                          <div className="absolute left-0 bottom-full mb-2 w-64 p-3 bg-slate-800 border border-slate-700 rounded-lg shadow-xl text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                             分析：当买入额（红）持续高于卖出额（绿）时，即便股价不涨，也可能是吸筹信号。<br/>
                             <span className="text-yellow-400">主力交易占比</span>：反映主力资金在当天的统治力，占比越高说明散户越少。
                          </div>
                       </div>
                    </div>
                    <div className="h-[300px]">
                       <ResponsiveContainer width="100%" height="100%">
                         <ComposedChart data={historyData} syncId="historyGraph">
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 12}} />
                            <YAxis yAxisId="left" stroke="#64748b" tick={{fontSize: 12}} unit="%" domain={[0, 100]} />
                            <YAxis yAxisId="right" orientation="right" stroke="#fbbf24" tick={{fontSize: 12}} unit="%" domain={[0, 100]} />
                            <Tooltip 
                                position={{ y: 0 }}
                                contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                formatter={(val: number, name: string, props: any) => {
                                    if (name === '主力交易占比') return val.toFixed(1) + '%';
                                    let amount = 0;
                                    if (name === '主力买入占比') amount = props.payload.main_buy_amount;
                                    if (name === '主力卖出占比') amount = props.payload.main_sell_amount;
                                    return `${val.toFixed(1)}% (${(amount/100000000).toFixed(2)}亿)`;
                                }} 
                            />
                            <Legend />
                            <Area yAxisId="left" type="monotone" dataKey="buyRatio" name="主力买入占比" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.1} />
                            <Area yAxisId="left" type="monotone" dataKey="sellRatio" name="主力卖出占比" stackId="2" stroke="#22c55e" fill="#22c55e" fillOpacity={0.1} />
                            <Line yAxisId="right" type="monotone" dataKey="activityRatio" name="主力交易占比" stroke="#fbbf24" strokeWidth={2} dot={false} />
                         </ComposedChart>
                       </ResponsiveContainer>
                    </div>
                 </div>
               </div>

               {/* 右侧 (对比) */}
               {historyCompareMode && (
                   <div className="space-y-6 border-l border-slate-800 pl-6 border-dashed relative">
                     {/* Global Controls for Split View (Right Side) */}
                     <div className="absolute top-0 right-0 z-20">
                          <DataSourceControl 
                                mode="history"
                                source={historySource} // In split view, left is fixed to 'source', right is 'compareSource'
                                setSource={setHistorySource}
                                compareMode={historyCompareMode}
                                setCompareMode={setHistoryCompareMode}
                            />
                     </div>

                     {/* 1. 对比-主力净流入 */}
                     <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg opacity-90 mt-12 relative">
                        <div className="mb-6">
                           <h3 className="text-lg font-bold text-slate-300 flex items-center gap-2">
                               {historyCompareSource === 'sina' ? <span className="text-red-500">🔴 新浪数据</span> : <span className="text-purple-500">🟣 本地自算</span>}
                               主力净流入
                           </h3>
                        </div>
                        <div className="h-[300px]">
                           {/* Empty State for Local Data */}
                           {historyCompareSource === 'local' && historyCompareData.length === 0 ? (
                               <div className="h-full flex flex-col items-center justify-center text-slate-500">
                                   <Database className="w-12 h-12 mb-4 opacity-20" />
                                   <p>暂无本地数据</p>
                                   <p className="text-xs mt-2 opacity-60">请先加关注并等待收盘计算</p>
                               </div>
                           ) : (
                               <ResponsiveContainer width="100%" height="100%">
                                 <ComposedChart data={historyCompareData} syncId="historyGraph">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                    <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 12}} />
                                    <YAxis stroke="#64748b" tick={{fontSize: 12}} tickFormatter={(val) => (val/100000000).toFixed(0)} />
                                    <Tooltip 
                                        position={{ y: 0 }}
                                        contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                        formatter={(val: number) => (val/100000000).toFixed(2) + '亿'} 
                                    />
                                    <Legend />
                                    <ReferenceLine y={0} stroke="#334155" />
                                    <Bar dataKey="net_inflow" name="主力净流入">
                                      {historyCompareData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.net_inflow > 0 ? '#ef4444' : '#22c55e'} />
                                      ))}
                                    </Bar>
                                 </ComposedChart>
                               </ResponsiveContainer>
                           )}
                        </div>
                     </div>

                     {/* 2. 对比-买卖力度分离 */}
                     <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg opacity-90">
                        <div className="mb-6">
                           <h3 className="text-lg font-bold text-slate-300">买卖力度分离监控</h3>
                        </div>
                        <div className="h-[300px]">
                           <ResponsiveContainer width="100%" height="100%">
                             <ComposedChart data={historyCompareData} syncId="historyGraph">
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 12}} />
                                <YAxis yAxisId="left" stroke="#64748b" tick={{fontSize: 12}} unit="%" domain={[0, 100]} />
                                <YAxis yAxisId="right" orientation="right" stroke="#fbbf24" tick={{fontSize: 12}} unit="%" domain={[0, 100]} />
                                <Tooltip 
                                    position={{ y: 0 }}
                                    contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                    formatter={(val: number, name: string, props: any) => {
                                        if (name === '主力交易占比') return val.toFixed(1) + '%';
                                        let amount = 0;
                                        if (name === '主力买入占比') amount = props.payload.main_buy_amount;
                                        if (name === '主力卖出占比') amount = props.payload.main_sell_amount;
                                        return `${val.toFixed(1)}% (${(amount/100000000).toFixed(2)}亿)`;
                                    }} 
                                />
                                <Legend />
                                <Area yAxisId="left" type="monotone" dataKey="buyRatio" name="主力买入占比" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.1} />
                                <Area yAxisId="left" type="monotone" dataKey="sellRatio" name="主力卖出占比" stackId="2" stroke="#22c55e" fill="#22c55e" fillOpacity={0.1} />
                                <Line yAxisId="right" type="monotone" dataKey="activityRatio" name="主力交易占比" stroke="#fbbf24" strokeWidth={2} dot={false} />
                             </ComposedChart>
                           </ResponsiveContainer>
                        </div>
                     </div>
                   </div>
               )}
            </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
};

export default App;