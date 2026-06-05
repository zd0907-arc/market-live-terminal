import React, { useState, useEffect, Suspense, lazy } from 'react';
import { Activity, ArrowUp, ArrowDown, Wifi, AlertCircle, RefreshCw, BarChart3, TrendingUp, Target, BrainCircuit } from 'lucide-react';
import { HistoryMultiframeGranularity, RealTimeQuote, ReviewPoolItem, SearchResult } from './types';
import * as StockService from './services/stockService';
import ThresholdConfig from './components/dashboard/ThresholdConfig';
import StockQuoteHeroCard from './components/common/StockQuoteHeroCard';
import MarketTopHeader from './components/common/MarketTopHeader';
import QuoteMetaRow from './components/common/QuoteMetaRow';
import { isCurrentCnTradingSession } from './utils/marketTime';
import { CLOUD_LITE_MODE } from './config';

const RealtimeView = lazy(() => import('./components/dashboard/RealtimeView'));
const HistoryMultiframeFusionView = lazy(() => import('./components/dashboard/HistoryMultiframeFusionView'));
const SentimentDashboard = lazy(() => import('./components/sentiment/SentimentDashboard'));
const ReviewPage = lazy(() => import('./components/sandbox/SandboxReviewPage'));
const SelectionResearchPage = lazy(() => import('./components/selection/SelectionResearchPage'));
const PPOBacktestReportPage = lazy(() => import('./components/selection/PPOBacktestReportPage'));
const ModelTrainingPage = lazy(() => import('./components/model/ModelTrainingPage'));
const OpportunityTradeReviewPage = lazy(() => import('./components/selection/OpportunityTradeReviewPage'));
const SparkPatternPrototypePage = lazy(() => import('./components/selection/SparkPatternPrototypePage'));
const SparkPatternResearchPage = lazy(() => import('./components/selection/SparkPatternResearchPage'));
const ProbeSignalResearchPage = lazy(() => import('./components/selection/ProbeSignalResearchPage'));
const MarketHeatPage = lazy(() => import('./components/market/MarketHeatPage'));
const HotThemeLowPositionSamplesPage = lazy(() => import('./components/market/HotThemeLowPositionSamplesPage'));
const TrendResearchPage = lazy(() => import('./components/trend/TrendResearchPage'));

const VALID_SYMBOL_RE = /^(sh|sz|bj)\d{6}$/i;

const getSymbolFromLocation = (): string => {
  if (typeof window === 'undefined') return '';
  const value = new URLSearchParams(window.location.search).get('symbol') || '';
  const normalized = value.trim().toLowerCase();
  return VALID_SYMBOL_RE.test(normalized) ? normalized : '';
};


const CloudLiteBlockedPage: React.FC<{ title: string }> = ({ title }) => (
  <div className="min-h-screen bg-[#0a0f1c] text-slate-200 font-sans selection:bg-blue-900 p-6">
    <div className="mx-auto mt-20 max-w-lg rounded-2xl border border-slate-800 bg-slate-900/80 p-6 text-center shadow-2xl">
      <div className="text-lg font-semibold text-white">{title}暂未在云端开放</div>
      <div className="mt-2 text-sm text-slate-400">当前生产环境只保留盯盘和复盘能力。</div>
      <div className="mt-5 flex justify-center gap-2">
        <a href="/" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 hover:border-slate-500">回到盯盘</a>
        <a href="/review" className="rounded-lg border border-cyan-700/60 bg-cyan-900/30 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-800/40">打开复盘</a>
      </div>
    </div>
  </div>
);

class ViewErrorBoundary extends React.Component<{ title: string; children: React.ReactNode }, { hasError: boolean; message: string }> {
  constructor(props: { title: string; children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: Error) {
    return {
      hasError: true,
      message: error?.message || 'Unknown render error',
    };
  }

  componentDidCatch(error: Error) {
    console.error(`[ViewErrorBoundary] ${this.props.title}`, error);
  }

  componentDidUpdate(prevProps: { title: string; children: React.ReactNode }) {
    if (this.state.hasError && prevProps.children !== this.props.children) {
      this.setState({ hasError: false, message: '' });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 text-sm text-red-200">
          <div className="font-semibold">{this.props.title} 渲染失败</div>
          <div className="mt-1 text-xs text-red-300/90 break-all">{this.state.message}</div>
        </div>
      );
    }
    return this.props.children;
  }
}

const App: React.FC = () => {
  const isReviewRoute = typeof window !== 'undefined' && (window.location.pathname.startsWith('/review') || window.location.pathname.startsWith('/sandbox-review'));
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/sandbox-review')) {
    const next = `/review${window.location.search}${window.location.hash}`;
    window.history.replaceState(null, '', next);
  }
  if (isReviewRoute) {
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">复盘页面加载中...</div>}>
        <ReviewPage />
      </Suspense>
    );
  }


  const isTrendResearchRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/trend-research');
  if (isTrendResearchRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="趋势研究" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">趋势研究台加载中...</div>}>
        <TrendResearchPage />
      </Suspense>
    );
  }

  const isSelectionRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/selection-research');
  if (isSelectionRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="选股研究台" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">选股研究台加载中...</div>}>
        <SelectionResearchPage />
      </Suspense>
    );
  }

  const isModelTrainingPpoRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/model-training/ppo-backtest');
  if (isModelTrainingPpoRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="模型训练" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">模型训练详情加载中...</div>}>
        <PPOBacktestReportPage />
      </Suspense>
    );
  }

  const isModelTrainingRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/model-training');
  if (isModelTrainingRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="模型训练" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">模型训练加载中...</div>}>
        <ModelTrainingPage />
      </Suspense>
    );
  }

  const isPpoBacktestRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/selection-ppo-report');
  if (isPpoBacktestRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="PPO 回测复盘" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">PPO 回测复盘加载中...</div>}>
        <PPOBacktestReportPage />
      </Suspense>
    );
  }

  const isOpportunityTradeReviewRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/selection-opportunity-review');
  if (isOpportunityTradeReviewRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="机会发现交易复盘" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">机会发现交易复盘加载中...</div>}>
        <OpportunityTradeReviewPage />
      </Suspense>
    );
  }

  const isSparkPatternPrototypeRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/selection-spark-pattern-prototype');
  if (isSparkPatternPrototypeRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="星火形态样式版" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">星火形态样式版加载中...</div>}>
        <SparkPatternPrototypePage />
      </Suspense>
    );
  }

  const isSparkPatternResearchRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/selection-spark-pattern-research');
  if (isSparkPatternResearchRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="星火形态研究页" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">星火形态研究页加载中...</div>}>
        <SparkPatternResearchPage />
      </Suspense>
    );
  }

  const isProbeSignalResearchRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/selection-probe-signal-research');
  if (isProbeSignalResearchRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="试盘事件研究页" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">试盘事件研究页加载中...</div>}>
        <ProbeSignalResearchPage />
      </Suspense>
    );
  }

  const isLowPositionSamplesRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/market-heat/low-position-samples');
  if (isLowPositionSamplesRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="热点低位样本" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">热点低位样本加载中...</div>}>
        <HotThemeLowPositionSamplesPage />
      </Suspense>
    );
  }

  const isMarketHeatRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/market-heat');
  if (isMarketHeatRoute) {
    if (CLOUD_LITE_MODE) return <CloudLiteBlockedPage title="市场热点" />;
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#0a0f1c] text-slate-300 p-6">市场热点温度计加载中...</div>}>
        <MarketHeatPage />
      </Suspense>
    );
  }

  // State
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [activeStock, setActiveStock] = useState<SearchResult | null>(null);

  // Search History
  const [searchHistory, setSearchHistory] = useState<SearchResult[]>([]);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [initialSymbol] = useState<string>(() => getSymbolFromLocation());

  // Fusion Navigation
  const [fusionSection, setFusionSection] = useState<'intraday_live' | 'history_multiframe'>('intraday_live');
  const [fusionGranularity, setFusionGranularity] = useState<HistoryMultiframeGranularity>('1d');

  // Shared Data
  const [quote, setQuote] = useState<RealTimeQuote | null>(null);
  const [reviewMeta, setReviewMeta] = useState<ReviewPoolItem | null>(null);
  const [turnoverRate, setTurnoverRate] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  // Watchlist
  const [isWatchlisted, setIsWatchlisted] = useState(false);

  // System Status
  const [backendStatus, setBackendStatus] = useState<boolean>(true);
  const [configVersion, setConfigVersion] = useState(0);
  const backendHealthFailureCountRef = React.useRef(0);

  // Focus Mode (盯盘)
  const [focusMode, setFocusMode] = useState<'normal' | 'focus'>('normal');
  const lastActiveTimeRef = React.useRef<number>(Date.now());

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

  useEffect(() => {
    if (!initialSymbol || activeStock) return;
    const bootstrap = async () => {
      try {
        const quote = await StockService.fetchQuote(initialSymbol);
        handleSelectStock({
          symbol: initialSymbol,
          code: initialSymbol.slice(2),
          market: initialSymbol.slice(0, 2),
          name: quote.name || initialSymbol,
        });
      } catch {
        handleSelectStock({
          symbol: initialSymbol,
          code: initialSymbol.slice(2),
          market: initialSymbol.slice(0, 2),
          name: initialSymbol,
        });
      }
    };
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol, activeStock]);

  // Backend Health Check
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const isHealthy = await StockService.checkBackendHealth();
      if (cancelled) return;
      if (isHealthy) {
        backendHealthFailureCountRef.current = 0;
        setBackendStatus(true);
        return;
      }
      backendHealthFailureCountRef.current += 1;
      if (backendHealthFailureCountRef.current >= 3) {
        setBackendStatus(false);
      }
    };
    check();
    const interval = window.setInterval(check, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  // Idle Timer & Auto-Cancel Focus Mode
  useEffect(() => {
    const handleActivity = () => {
      lastActiveTimeRef.current = Date.now();
    };

    const handleBlur = () => {
      if (focusMode === 'focus') {
        console.log("Window lost focus. Auto-canceling focus mode.");
        setFocusMode('normal');
      }
    };

    window.addEventListener('mousemove', handleActivity);
    window.addEventListener('keydown', handleActivity);
    window.addEventListener('blur', handleBlur);

    const idleCheckInterval = setInterval(() => {
      if (focusMode === 'focus') {
        const idleTime = Date.now() - lastActiveTimeRef.current;
        if (idleTime > 3 * 60 * 1000) { // 3 minutes idle
          console.log("User idle for 3 minutes. Auto-canceling focus mode.");
          setFocusMode('normal');
        }
      }
    }, 10000);

    return () => {
      window.removeEventListener('mousemove', handleActivity);
      window.removeEventListener('keydown', handleActivity);
      window.removeEventListener('blur', handleBlur);
      clearInterval(idleCheckInterval);
    };
  }, [focusMode]);

  // Select Stock
  const handleSelectStock = (stock: SearchResult) => {
    setActiveStock(stock);
    setQuery('');
    setResults([]);
    setQuote(null);
    setError('');
    setIsSearchFocused(false);
    setIsWatchlisted(false);
    setFocusMode('normal'); // Auto-cancel on stock switch

    // Check watchlist
    StockService.getWatchlist().then(list => {
      if (list.find(item => item.symbol === stock.symbol)) {
        setIsWatchlisted(true);
      }
    });

    // Update History
    setSearchHistory((prev) => {
      const newHistory = [stock, ...prev.filter((s) => s.symbol !== stock.symbol)].slice(0, 10);
      localStorage.setItem('stock_search_history', JSON.stringify(newHistory));
      return newHistory;
    });
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
    // Quiet refresh: focus=5s, normal=30s.
    const intervalMs = focusMode === 'focus' ? 5000 : 30000;
    intervalId = setInterval(() => fetchQuote(false), intervalMs);

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [activeStock, focusMode]);

  useEffect(() => {
    if (!activeStock?.symbol) {
      setReviewMeta(null);
      return;
    }
    let cancelled = false;
    StockService.fetchReviewPool(activeStock.symbol, 20)
      .then((pool) => {
        if (cancelled) return;
        const matched = pool.items.find((item) => item.symbol === activeStock.symbol) || null;
        setReviewMeta(matched);
      })
      .catch(() => {
        if (cancelled) return;
        setReviewMeta(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeStock]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    if (activeStock?.symbol) {
      url.searchParams.set('symbol', activeStock.symbol.toLowerCase());
    } else {
      url.searchParams.delete('symbol');
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }, [activeStock]);

  useEffect(() => {
    if (!activeStock?.symbol) {
      setTurnoverRate(null);
      return;
    }
    let cancelled = false;
    StockService.fetchSentimentData(activeStock.symbol)
      .then((data) => {
        if (cancelled) return;
        const value = Number(data?.turnover_rate);
        setTurnoverRate(Number.isFinite(value) ? value : null);
      })
      .catch(() => {
        if (cancelled) return;
        setTurnoverRate(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeStock]);

  // Scroll State for Sticky Header
  const [isScrolled, setIsScrolled] = useState(false);
  const searchContainerRef = React.useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 100);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

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

  const trimTrailingZeros = (valueText: string) => valueText.replace(/\.0+$|(\.\d*[1-9])0+$/, '$1');
  const formatMarketCapYi = (marketCap?: number): string | null => {
    if (!Number.isFinite(marketCap) || (marketCap || 0) <= 0) return null;
    return `${trimTrailingZeros(((marketCap || 0) / 100000000).toFixed(2))}亿`;
  };

  const sectionLoading = (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs text-slate-500">
      组件加载中...
    </div>
  );
  const reviewHref = activeStock?.symbol ? `/review?symbol=${activeStock.symbol.toLowerCase()}` : '/review';
  const selectionHref = '/selection-research';
  const modelTrainingHref = '/model-training';
  const marketHeatHref = '/market-heat';
  const trendResearchHref = '/trend-research';

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200 font-sans selection:bg-blue-900 pb-20 overflow-x-hidden">
      <MarketTopHeader
        routeHref={reviewHref}
        routeLabel="去复盘"
        routeTitle="打开复盘页面"
        secondaryRouteHref={CLOUD_LITE_MODE ? undefined : selectionHref}
        secondaryRouteLabel={CLOUD_LITE_MODE ? undefined : "去选股"}
        secondaryRouteTitle={CLOUD_LITE_MODE ? undefined : "打开选股研究工作台"}
        searchValue={query}
        isSearchFocused={isSearchFocused}
        searchResults={results}
        searchHistory={searchHistory}
        searchContainerRef={searchContainerRef}
        onSearchChange={(value) => setQuery(value)}
        onSearchFocus={() => setIsSearchFocused(true)}
        onSearchBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
        onSearchKeyDown={(e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          if (results.length > 0) {
            handleSelectStock(results[0]);
          }
        }}
        onClearSearch={() => setQuery('')}
        onSelectSearchResult={(res) => handleSelectStock(res)}
        onSelectHistory={(res) => handleSelectStock(res)}
        rightSlot={
          <div className="flex flex-nowrap items-center justify-end gap-2 whitespace-nowrap">
            {!CLOUD_LITE_MODE && (
              <>
                <a
                  href={modelTrainingHref}
                  className="hidden h-9 items-center rounded-lg border border-fuchsia-700/50 bg-fuchsia-900/30 px-3 text-xs font-medium text-fuchsia-200 transition-colors hover:bg-fuchsia-800/40 md:inline-flex"
                  title="打开模型训练模块"
                >
                  模型训练
                </a>
                <a
                  href={trendResearchHref}
                  className="hidden h-9 items-center rounded-lg border border-cyan-700/50 bg-cyan-900/30 px-3 text-xs font-medium text-cyan-200 transition-colors hover:bg-cyan-800/40 md:inline-flex"
                  title="打开长期趋势研究台"
                >
                  趋势研究
                </a>
                <a
                  href={marketHeatHref}
                  className="hidden h-9 items-center rounded-lg border border-amber-700/50 bg-amber-900/30 px-3 text-xs font-medium text-amber-200 transition-colors hover:bg-amber-800/40 md:inline-flex"
                  title="打开市场热点温度计"
                >
                  市场热点
                </a>
              </>
            )}
            <ThresholdConfig onConfigUpdate={handleConfigUpdate} />
          </div>
        }
      />

      {/* Header */}
      <div>
        {/* --- Mobile Sticky Stock Info Bar (Appears on Scroll) --- */}
        {isScrolled && activeStock && quote && (
          <div className="md:hidden border-t border-slate-800 bg-[#0a0f1c]/95 backdrop-blur px-3 py-2 flex items-center justify-between shadow-xl mt-2 animate-in slide-in-from-top-2">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-white">{quote.name}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className={`font-mono font-bold ${getPriceColor(quote.price, quote.lastClose)}`}>
                {quote.price.toFixed(2)}
              </span>
              <span className={`font-mono text-xs flex items-center gap-0.5 ${getPriceColor(quote.price, quote.lastClose)}`}>
                {quote.price >= quote.lastClose ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
                {((quote.price - quote.lastClose) / quote.lastClose * 100).toFixed(2)}%
              </span>
            </div>
          </div>
        )}
      </div>

      <main className="max-w-[1600px] mx-auto p-2 md:p-6 space-y-4 md:space-y-6">

        {/* No Active Stock State */}
        {!activeStock && !loading && !quote && (
          <div className="text-center py-20 text-slate-500">
            <Activity className="w-16 h-16 mx-auto mb-4 opacity-20" />
            <p>请输入股票代码开始监控</p>
            <p className="text-xs mt-2 opacity-60">模式：实时逐笔 (Web) | 历史博弈 (Python Local)</p>
            {!CLOUD_LITE_MODE && (
              <div className="mt-5">
                <a
                  href={selectionHref}
                  className="inline-flex items-center gap-2 rounded-lg border border-emerald-600/40 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20"
                >
                  <TrendingUp className="h-4 w-4" />
                  去选股研究工作台
                </a>
                <a
                  href={trendResearchHref}
                  className="ml-2 inline-flex items-center gap-2 rounded-lg border border-cyan-600/40 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-200 hover:bg-cyan-500/20"
                >
                  <BrainCircuit className="h-4 w-4" />
                  看趋势研究
                </a>
                <a
                  href={marketHeatHref}
                  className="ml-2 inline-flex items-center gap-2 rounded-lg border border-amber-600/40 bg-amber-500/10 px-4 py-2 text-sm font-medium text-amber-200 hover:bg-amber-500/20"
                >
                  <BarChart3 className="h-4 w-4" />
                  看市场热点
                </a>
                <a
                  href={modelTrainingHref}
                  className="ml-2 inline-flex items-center gap-2 rounded-lg border border-fuchsia-600/40 bg-fuchsia-500/10 px-4 py-2 text-sm font-medium text-fuchsia-200 hover:bg-fuchsia-500/20"
                >
                  <BrainCircuit className="h-4 w-4" />
                  模型训练
                </a>
              </div>
            )}
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
          <StockQuoteHeroCard
            name={quote.name}
            symbol={quote.symbol.toUpperCase()}
            price={quote.price}
            previousClose={quote.lastClose}
            open={quote.open}
            high={quote.high}
            low={quote.low}
            volume={quote.volume}
            amount={quote.amount}
            turnoverRate={turnoverRate}
            latestLabel={!isCurrentCnTradingSession() && quote.date ? `最新 ${quote.date}` : undefined}
            marketCapLabel={formatMarketCapYi(reviewMeta?.market_cap) ?? '--'}
            metaRow={
              <QuoteMetaRow
                isWatchlisted={isWatchlisted}
                onToggleWatchlist={toggleWatchlist}
                backendStatus={backendStatus}
              />
            }
          />
        )}

        {/* View Switcher */}
        {quote && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 bg-slate-900 rounded-xl p-2 border border-slate-800 shadow-lg">
              <button
                onClick={() => setFusionSection('intraday_live')}
                className={`inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs md:text-sm font-medium transition-all ${fusionSection === 'intraday_live' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
              >
                <Activity className="w-3.5 h-3.5 md:w-4 md:h-4" />
                当日分时
              </button>
              <button
                onClick={() => setFusionSection('history_multiframe')}
                className={`inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs md:text-sm font-medium transition-all ${fusionSection === 'history_multiframe' ? 'bg-violet-600 text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
              >
                <BarChart3 className="w-3.5 h-3.5 md:w-4 md:h-4" />
                历史多维
              </button>
              <button
                onClick={() => setFocusMode(prev => prev === 'focus' ? 'normal' : 'focus')}
                className={`inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs md:text-sm font-medium transition-all border ${focusMode === 'focus' ? 'text-red-300 bg-red-400/10 border-red-500/40' : 'text-slate-300 bg-slate-800 border-slate-700 hover:text-white hover:bg-slate-700'}`}
                title={focusMode === 'focus' ? '关闭盯盘，恢复 30 秒静默刷新' : '开启盯盘，切换为 5 秒刷新'}
              >
                {focusMode === 'focus' ? (
                  <>
                    <Target className="w-3.5 h-3.5 animate-pulse" />
                    <span className="font-bold">盯盘中 5s</span>
                  </>
                ) : (
                  <>
                    <Activity className="w-3.5 h-3.5" />
                    <span>盯盘关闭 30s</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Content Views */}
        {activeStock && fusionSection === 'intraday_live' && (
          <ViewErrorBoundary title="当日分时">
            <Suspense fallback={sectionLoading}>
              <RealtimeView
                activeStock={activeStock}
                isTradingHours={isTradingHours}
                configVersion={configVersion}
                focusMode={focusMode}
              />
            </Suspense>
          </ViewErrorBoundary>
        )}

        {quote && fusionSection === 'history_multiframe' && (
          <ViewErrorBoundary title="历史多维">
            <Suspense fallback={sectionLoading}>
              <HistoryMultiframeFusionView
                activeStock={activeStock}
                backendStatus={backendStatus}
                granularity={fusionGranularity}
                onGranularityChange={setFusionGranularity}
              />
            </Suspense>
          </ViewErrorBoundary>
        )}

        {/* Retail Sentiment Dashboard (Moved to Bottom) */}
        {activeStock && (
          <ViewErrorBoundary title="散户情绪仪表盘">
            <Suspense fallback={sectionLoading}>
              <SentimentDashboard symbol={activeStock.symbol} />
            </Suspense>
          </ViewErrorBoundary>
        )}

      </main>
    </div>
  );
};

export default App;
