import React, { useState, useEffect } from 'react';
import { Search, Activity, ArrowUp, ArrowDown, Clock, Wifi, AlertCircle, RefreshCw, BarChart3, Pause, Play, BookOpen, Star, Server } from 'lucide-react';
import { RealTimeQuote, SearchResult } from './types';
import * as StockService from './services/stockService';
import RealtimeView from './components/dashboard/RealtimeView';
import HistoryView from './components/dashboard/HistoryView';
import SentimentDashboard from './components/sentiment/SentimentDashboard';
import ThresholdConfig from './components/dashboard/ThresholdConfig';
import RealTimeClock from './components/common/RealTimeClock';
import { APP_VERSION } from './version';

const App: React.FC = () => {
  // State
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [activeStock, setActiveStock] = useState<SearchResult | null>(null);
  
  // Search History
  const [searchHistory, setSearchHistory] = useState<SearchResult[]>([]);
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  // View Mode
  const [viewMode, setViewMode] = useState<'realtime' | 'history'>('realtime');
  
  // Shared Data
  const [quote, setQuote] = useState<RealTimeQuote | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  
  // Watchlist
  const [isWatchlisted, setIsWatchlisted] = useState(false);

  // System Status
  const [backendStatus, setBackendStatus] = useState<boolean>(false);
  const [configVersion, setConfigVersion] = useState(0);

  const handleConfigUpdate = () => {
    setConfigVersion(prev => prev + 1);
  };

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

  // Load Search History
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

  // Backend Health Check
  useEffect(() => {
    const check = async () => {
      const isHealthy = await StockService.checkBackendHealth();
      setBackendStatus(isHealthy);
    };
    check();
    const interval = setInterval(check, 5000); 
    return () => clearInterval(interval);
  }, []);

  // Select Stock
  const handleSelectStock = (stock: SearchResult) => {
    setActiveStock(stock);
    setQuery('');
    setResults([]);
    setQuote(null);
    setError('');
    setIsSearchFocused(false);
    setIsWatchlisted(false);
    
    // Check watchlist
    StockService.getWatchlist().then(list => {
        if (list.find(item => item.symbol === stock.symbol)) {
            setIsWatchlisted(true);
        }
    });

    // Update History
    const newHistory = [stock, ...searchHistory.filter(s => s.symbol !== stock.symbol)].slice(0, 10);
    setSearchHistory(newHistory);
    localStorage.setItem('stock_search_history', JSON.stringify(newHistory));
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

  // Quote Polling (Only fetches Quote, Ticks handled by RealtimeView)
  useEffect(() => {
    if (!activeStock) return;

    let isMounted = true;
    let intervalId: any = null;

    const fetchQuote = async (isFirstLoad = false) => {
      if (!isMounted) return;
      if (isFirstLoad) setLoading(true);
      
      try {
        const q = await StockService.fetchQuote(activeStock.symbol);
        if (isMounted) {
          setQuote(q);
          setError('');
        }
      } catch (err) {
        console.error("Quote fetch error:", err);
        if (isMounted && !quote) {
             setError('无法连接行情服务器');
        }
      } finally {
        if (isMounted && isFirstLoad) setLoading(false);
      }
    };

    fetchQuote(true);
    // Refresh quote every 5s regardless of view mode (to keep header updated)
    intervalId = setInterval(() => fetchQuote(false), 5000);

    return () => {
        isMounted = false;
        if (intervalId) clearInterval(intervalId);
    };
  }, [activeStock]);

  const isTradingHours = () => {
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const time = hours * 100 + minutes;
    return (time >= 930 && time <= 1130) || (time >= 1300 && time <= 1500);
  };

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
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#0f1623]/95 backdrop-blur border-b border-slate-800 p-4">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 font-bold text-lg text-red-500 w-full md:w-auto">
            <Activity className="w-6 h-6" />
            <span>ZhangData</span>
            <span className="text-xs text-slate-500 bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded font-mono">v{APP_VERSION}</span>
          </div>
          
          <div className="relative flex-1 max-w-3xl w-full flex items-center gap-4">
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
                
                {/* Search History Dropdown */}
                {isSearchFocused && !query && searchHistory.length > 0 && (
                  <div className="absolute top-full left-0 mt-2 w-full md:w-96 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-80 overflow-y-auto z-50">
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
                           </div>
                        </button>
                      ))}
                  </div>
                )}

                {/* Search Results Dropdown */}
                {results.length > 0 && (
                  <div className="absolute top-full left-0 mt-2 w-full md:w-96 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-60 overflow-y-auto z-50">
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

              {/* View Toggle */}
              <div className="flex gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 shrink-0">
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
          
          {/* Spacer for centering */}
          <div className="hidden md:flex items-center gap-4 w-48 justify-end">
             <ThresholdConfig onConfigUpdate={handleConfigUpdate} />
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 md:p-6 space-y-6">
        
        {/* No Active Stock State */}
        {!activeStock && !loading && !quote && (
          <div className="text-center py-20 text-slate-500">
            <Activity className="w-16 h-16 mx-auto mb-4 opacity-20" />
            <p>请输入股票代码开始监控</p>
            <p className="text-xs mt-2 opacity-60">模式：实时逐笔 (Web) | 历史博弈 (Python Local)</p>
          </div>
        )}

        {/* Loading State */}
        {loading && !quote && (
          <div className="text-center py-20 text-blue-400 flex flex-col items-center gap-3">
             <RefreshCw className="w-8 h-8 animate-spin" />
             <span>正在建立高速数据链路...</span>
          </div>
        )}

        {/* Error State */}
        {error && !quote && (
          <div className="bg-red-900/20 border border-red-800 p-4 rounded-lg flex items-center gap-3 text-red-200">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        {/* Quote Header Card */}
        {quote && (
           <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative overflow-hidden mb-6">
              <div className={`absolute -top-10 -right-10 w-40 h-40 rounded-full blur-[80px] opacity-20 pointer-events-none ${quote.price >= quote.lastClose ? 'bg-red-500' : 'bg-green-500'}`}></div>

              <div className="flex justify-between items-center relative z-10">
                {/* Left Section: Stock Info + Indicators */}
                <div className="flex flex-col md:flex-row md:items-center gap-4 md:gap-8 flex-1">
                    
                    {/* 1. Name & Status */}
                    <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-3">
                            <h1 className="text-2xl font-bold text-white tracking-tight">
                                {quote.name}
                            </h1>
                            <span className="text-xs font-mono text-slate-400 font-normal bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
                                {quote.symbol.toUpperCase()}
                            </span>
                            <button 
                                onClick={toggleWatchlist}
                                className={`p-1 rounded-full transition-colors ${isWatchlisted ? 'text-yellow-400 bg-yellow-400/10' : 'text-slate-600 hover:text-slate-400 hover:bg-slate-800'}`}
                            >
                                <Star className={`w-4 h-4 ${isWatchlisted ? 'fill-yellow-400' : ''}`} />
                            </button>
                        </div>
                        
                        <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono">
                             <RealTimeClock />
                             <span className={`flex items-center gap-1 ${backendStatus ? 'text-green-500/80' : 'text-red-500/80'}`}>
                                <Server className="w-3 h-3" />
                                {backendStatus ? '核心服务: 已连接' : '核心服务: 断开'}
                             </span>
                        </div>
                    </div>

                    {/* 2. Key Indicators (Grid) */}
                    <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs font-mono border-l border-slate-800 pl-6">
                        <div className="flex items-center gap-2">
                            <span className="text-slate-500">成交:</span>
                            <span className="text-slate-200">{formatAmount(quote.volume)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-slate-500">金额:</span>
                            <span className="text-slate-200">{formatAmount(quote.amount)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-slate-500">高/低:</span>
                            <span>
                                <span className="text-red-400">{quote.high.toFixed(2)}</span>
                                <span className="text-slate-600 mx-0.5">/</span>
                                <span className="text-green-400">{quote.low.toFixed(2)}</span>
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-slate-500">开/收:</span>
                             <span>
                                <span className={quote.open > quote.lastClose ? 'text-red-400' : 'text-green-400'}>{quote.open.toFixed(2)}</span>
                                <span className="text-slate-600 mx-0.5">/</span>
                                <span className="text-slate-200">{quote.lastClose.toFixed(2)}</span>
                            </span>
                        </div>
                    </div>

                </div>

                {/* Right Section: Price */}
                <div className="text-right pl-4">
                  <div className={`text-4xl font-mono font-bold tracking-tight ${getPriceColor(quote.price, quote.lastClose)}`}>
                    {quote.price.toFixed(2)}
                  </div>
                  <div className={`text-sm font-mono flex items-center justify-end gap-2 mt-1 ${getPriceColor(quote.price, quote.lastClose)}`}>
                      <span className="flex items-center">
                        {quote.price >= quote.lastClose ? <ArrowUp className="w-3 h-3 mr-1"/> : <ArrowDown className="w-3 h-3 mr-1"/>}
                        {(quote.price - quote.lastClose).toFixed(2)}
                      </span>
                      <span className="bg-slate-800/50 px-1.5 py-0.5 rounded">
                        {((quote.price - quote.lastClose) / quote.lastClose * 100).toFixed(2)}%
                      </span>
                  </div>
                </div>
              </div>
           </div>
        )}

        {/* Retail Sentiment Dashboard */}
        {activeStock && (
            <SentimentDashboard symbol={activeStock.code} />
        )}

        {/* Content Views */}
        {quote && viewMode === 'realtime' && (
            <RealtimeView 
                activeStock={activeStock} 
                quote={quote} 
                isTradingHours={isTradingHours} 
                configVersion={configVersion}
            />
        )}

        {quote && viewMode === 'history' && (
            <HistoryView 
                activeStock={activeStock} 
                backendStatus={backendStatus} 
                configVersion={configVersion}
            />
        )}

      </main>
    </div>
  );
};

export default App;
