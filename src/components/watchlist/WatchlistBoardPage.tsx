import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowLeft, LineChart, MoreVertical, RefreshCw, Search, Server, X } from 'lucide-react';

import {
  HistoryMultiframeGranularity,
  HistoryMultiframeItem,
  IntradayFusionData,
  RealTimeQuote,
  RealtimeDashboardData,
  SearchResult,
  WatchlistItem,
} from '../../types';
import * as StockService from '../../services/stockService';
import { APP_VERSION } from '../../version';
import IntradayMonitorChart from '../dashboard/IntradayMonitorChart';

const PRIMARY_CARD_COUNT = 6;

type BoardMode = 'intraday' | 'history';
type HistoryDays = 30 | 90 | 180;
type MoveAction = 'top' | 'up' | 'down' | 'bottom';
type ToastState = { id: number; text: string; tone: 'success' | 'error' } | null;

const GRANULARITY_LABELS: Record<HistoryMultiframeGranularity, string> = {
  '5m': '5分',
  '15m': '15分',
  '30m': '30分',
  '1h': '1小时',
  '1d': '日线',
};

const toSearchResult = (item: WatchlistItem): SearchResult => {
  const symbol = String(item.symbol || '').toLowerCase();
  return {
    symbol,
    code: symbol.slice(2),
    market: symbol.slice(0, 2),
    name: item.name || symbol,
  };
};

const formatPct = (value: number | null | undefined) => (
  value != null && Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : '--'
);

const formatMoney = (value: number | null | undefined) => {
  if (value == null) return '--';
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  const abs = Math.abs(num);
  if (abs >= 100000000) return `${(num / 100000000).toFixed(2)}亿`;
  if (abs >= 10000) return `${(num / 10000).toFixed(0)}万`;
  return num.toFixed(0);
};

const toneClass = (value: number | null | undefined) => {
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return 'text-slate-300';
  return num > 0 ? 'text-red-300' : 'text-green-300';
};

const InlineStat: React.FC<{
  label: string;
  value: string;
  tone?: string;
}> = ({ label, value, tone = 'text-slate-200' }) => (
  <span className="inline-flex min-w-0 items-baseline gap-1 whitespace-nowrap">
    <span className="text-slate-500">{label}</span>
    <span className={`font-mono ${tone}`}>{value}</span>
  </span>
);

const SegmentButton: React.FC<{
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`h-7 rounded px-2 text-[11px] font-medium transition ${
      active ? 'bg-sky-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
    }`}
  >
    {children}
  </button>
);

const historyNetValue = (row?: HistoryMultiframeItem | null) => {
  if (!row) return null;
  const hasL2 = [row.l2_main_buy, row.l2_main_sell, row.l2_super_buy, row.l2_super_sell]
    .some((value) => value !== null && value !== undefined);
  const mainBuy = Number((hasL2 ? row.l2_main_buy : row.l1_main_buy) ?? 0);
  const mainSell = Number((hasL2 ? row.l2_main_sell : row.l1_main_sell) ?? 0);
  const superBuy = Number((hasL2 ? row.l2_super_buy : row.l1_super_buy) ?? 0);
  const superSell = Number((hasL2 ? row.l2_super_sell : row.l1_super_sell) ?? 0);
  return mainBuy + superBuy - mainSell - superSell;
};

const WatchlistCard: React.FC<{
  item: WatchlistItem;
  index: number;
  boardMode: BoardMode;
  historyDays: HistoryDays;
  historyGranularity: HistoryMultiframeGranularity;
  total: number;
  onRemove: (item: WatchlistItem) => Promise<void>;
  onMove: (symbol: string, action: MoveAction) => void;
}> = ({ item, index, boardMode, historyDays, historyGranularity, total, onRemove, onMove }) => {
  const stock = useMemo(() => toSearchResult(item), [item]);
  const mode = index < PRIMARY_CARD_COUNT ? 'focus' : 'warm';
  const intervalMs = mode === 'focus' ? 5000 : 30000;
  const [quote, setQuote] = useState<RealTimeQuote | null>(null);
  const [dashboard, setDashboard] = useState<RealtimeDashboardData | null>(null);
  const [fusion, setFusion] = useState<IntradayFusionData | null>(null);
  const [historyRows, setHistoryRows] = useState<HistoryMultiframeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const isMountedRef = useRef(true);

  const loadQuote = async () => {
    try {
      const next = await StockService.fetchQuote(stock.symbol);
      if (isMountedRef.current) {
        setQuote(next);
        setError('');
      }
    } catch {
      if (isMountedRef.current && !quote) setError('行情失败');
    }
  };

  const loadMarketData = async () => {
    try {
      if (boardMode === 'history') {
        const nextRows = await StockService.fetchHistoryMultiframe(stock.symbol, {
          days: historyDays,
          granularity: historyGranularity,
          includeTodayPreview: true,
        });
        if (!isMountedRef.current) return;
        setHistoryRows(nextRows);
        setDashboard(null);
        setFusion(null);
        return;
      }

      const [nextDashboard, nextFusion] = await Promise.all([
        StockService.fetchRealtimeDashboard(stock.symbol),
        StockService.fetchIntradayFusion(stock.symbol),
      ]);
      if (!isMountedRef.current) return;
      setDashboard(nextDashboard);
      setFusion(nextFusion);
      setHistoryRows([]);
    } catch {
      if (isMountedRef.current) setError(boardMode === 'history' ? '历史失败' : '分时失败');
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    setLoading(true);
    setError('');
    setDashboard(null);
    setFusion(null);
    setHistoryRows([]);
    void loadQuote();
    void loadMarketData();
    if (boardMode === 'intraday') StockService.sendHeartbeat(stock.symbol, mode);

    const quoteTimer = window.setInterval(loadQuote, intervalMs);
    const dataTimer = window.setInterval(() => loadMarketData(), boardMode === 'intraday' ? intervalMs : 60000);
    const heartbeatTimer = boardMode === 'intraday'
      ? window.setInterval(() => StockService.sendHeartbeat(stock.symbol, mode), 10000)
      : null;

    return () => {
      isMountedRef.current = false;
      window.clearInterval(quoteTimer);
      window.clearInterval(dataTimer);
      if (heartbeatTimer) window.clearInterval(heartbeatTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stock.symbol, mode, intervalMs, boardMode, historyDays, historyGranularity]);

  useEffect(() => {
    if (!menuOpen) return;
    const closeMenu = () => setMenuOpen(false);
    window.addEventListener('click', closeMenu);
    return () => window.removeEventListener('click', closeMenu);
  }, [menuOpen]);

  const pct = quote && quote.lastClose > 0 ? ((quote.price - quote.lastClose) / quote.lastClose) * 100 : null;
  const intradayNetValue = useMemo(() => {
    const rows = dashboard?.cumulative_data || [];
    return rows.length ? Number(rows[rows.length - 1]?.cumNetInflow) : null;
  }, [dashboard]);
  const latestHistoryRow = historyRows[historyRows.length - 1];
  const netValue = boardMode === 'history' ? historyNetValue(latestHistoryRow) : intradayNetValue;
  const displayName = quote?.name || item.name || stock.symbol;
  const price = Number(quote?.price);
  const displayDate = boardMode === 'history'
    ? latestHistoryRow?.trade_date
    : (quote?.date || dashboard?.display_date || fusion?.trade_date || item.added_at?.slice(0, 10));
  const moveDisabled = {
    top: index === 0,
    up: index === 0,
    down: index >= total - 1,
    bottom: index >= total - 1,
  };
  const runMove = (action: MoveAction) => {
    if (moveDisabled[action]) return;
    setMenuOpen(false);
    onMove(item.symbol, action);
  };

  return (
    <>
      <article
        className="relative min-h-[360px] cursor-pointer rounded-lg border border-slate-800 bg-slate-900/80 p-2.5 shadow-lg transition hover:border-slate-700"
        onClick={() => setDetailOpen(true)}
      >
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            void onRemove(item);
          }}
          className="absolute right-1.5 top-1.5 z-10 inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 transition hover:bg-rose-500/15 hover:text-rose-200"
          aria-label={`移除${displayName}`}
          title="移出盯盘页"
        >
          <X className="h-3.5 w-3.5" />
        </button>
        <div
          className="absolute right-7 top-1.5 z-20"
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setMenuOpen((prev) => !prev);
            }}
            className="inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 transition hover:bg-slate-800 hover:text-slate-200"
            aria-label={`${displayName}排序`}
            title="调整顺序"
          >
            <MoreVertical className="h-3.5 w-3.5" />
          </button>
          {menuOpen ? (
            <div className="absolute right-0 top-6 w-24 overflow-hidden rounded-md border border-slate-700 bg-slate-950 py-1 text-xs shadow-xl">
              <button
                type="button"
                disabled={moveDisabled.top}
                onClick={() => runMove('top')}
                className="block w-full px-3 py-1.5 text-left text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-600 disabled:hover:bg-transparent"
              >
                置顶
              </button>
              <button
                type="button"
                disabled={moveDisabled.up}
                onClick={() => runMove('up')}
                className="block w-full px-3 py-1.5 text-left text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-600 disabled:hover:bg-transparent"
              >
                上移
              </button>
              <button
                type="button"
                disabled={moveDisabled.down}
                onClick={() => runMove('down')}
                className="block w-full px-3 py-1.5 text-left text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-600 disabled:hover:bg-transparent"
              >
                下移
              </button>
              <button
                type="button"
                disabled={moveDisabled.bottom}
                onClick={() => runMove('bottom')}
                className="block w-full px-3 py-1.5 text-left text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-600 disabled:hover:bg-transparent"
              >
                置底
              </button>
            </div>
          ) : null}
        </div>

        <div className="h-11 overflow-hidden pr-12">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-bold leading-5 text-white">{displayName}</h2>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0 text-[10px] leading-4">
                <InlineStat label="开" value={Number.isFinite(Number(quote?.open)) ? Number(quote?.open).toFixed(2) : '--'} />
                <InlineStat label="高" value={Number.isFinite(Number(quote?.high)) ? Number(quote?.high).toFixed(2) : '--'} tone="text-red-200" />
                <InlineStat label="低" value={Number.isFinite(Number(quote?.low)) ? Number(quote?.low).toFixed(2) : '--'} tone="text-emerald-200" />
                <InlineStat label="额" value={formatMoney(quote?.amount)} />
                <InlineStat label="资金净" value={formatMoney(netValue)} tone={toneClass(netValue)} />
                {error ? <span className="text-rose-300">{error}</span> : null}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className={`font-mono text-xl font-bold leading-none ${toneClass(pct)}`}>
                {Number.isFinite(price) ? price.toFixed(2) : '--'}
              </div>
              <div className={`mt-0.5 font-mono text-xs font-semibold ${toneClass(pct)}`}>{formatPct(pct)}</div>
            </div>
          </div>
        </div>

        <div className="mt-1.5">
          <IntradayMonitorChart
            data={fusion}
            historyRows={historyRows}
            mode={boardMode}
            granularity={historyGranularity}
            isLoading={loading}
            height={286}
            previousClose={quote?.lastClose}
            quoteDate={quote?.date}
          />
        </div>
      </article>

      {detailOpen ? (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/78 p-4 backdrop-blur-sm"
          onClick={() => setDetailOpen(false)}
        >
          <div
            className="max-h-[92vh] w-full max-w-6xl overflow-hidden rounded-lg border border-slate-700 bg-slate-950 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-lg font-bold text-white">{displayName}</div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                  <InlineStat label="开" value={Number.isFinite(Number(quote?.open)) ? Number(quote?.open).toFixed(2) : '--'} />
                  <InlineStat label="高" value={Number.isFinite(Number(quote?.high)) ? Number(quote?.high).toFixed(2) : '--'} tone="text-red-200" />
                  <InlineStat label="低" value={Number.isFinite(Number(quote?.low)) ? Number(quote?.low).toFixed(2) : '--'} tone="text-emerald-200" />
                  <InlineStat label="额" value={formatMoney(quote?.amount)} />
                  <InlineStat label="资金净" value={formatMoney(netValue)} tone={toneClass(netValue)} />
                  <span className="whitespace-nowrap font-mono text-slate-500">{displayDate || '--'}</span>
                </div>
              </div>
              <div className="flex shrink-0 items-start gap-3">
                <div className="text-right">
                  <div className={`font-mono text-3xl font-bold leading-none ${toneClass(pct)}`}>
                    {Number.isFinite(price) ? price.toFixed(2) : '--'}
                  </div>
                  <div className={`mt-1 font-mono text-sm font-semibold ${toneClass(pct)}`}>{formatPct(pct)}</div>
                </div>
                <button
                  type="button"
                  onClick={() => setDetailOpen(false)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded text-slate-400 hover:bg-slate-800 hover:text-white"
                  aria-label="关闭浮窗"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="p-3">
              <IntradayMonitorChart
                data={fusion}
                historyRows={historyRows}
                mode={boardMode}
                granularity={historyGranularity}
                isLoading={loading}
                height={560}
                previousClose={quote?.lastClose}
                quoteDate={quote?.date}
              />
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
};

const WatchlistBoardPage: React.FC = () => {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchHistory, setSearchHistory] = useState<SearchResult[]>([]);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [backendStatus, setBackendStatus] = useState(true);
  const [toast, setToast] = useState<ToastState>(null);
  const [error, setError] = useState('');
  const [boardMode, setBoardMode] = useState<BoardMode>('intraday');
  const [historyDays, setHistoryDays] = useState<HistoryDays>(30);
  const [historyGranularity, setHistoryGranularity] = useState<HistoryMultiframeGranularity>('1d');
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const showToast = useCallback((text: string, tone: 'success' | 'error' = 'success') => {
    setToast({ id: Date.now(), text, tone });
  }, []);

  const loadItems = async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    try {
      const next = await StockService.getWatchlist();
      setItems(next);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '盯盘池加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    try {
      const saved = localStorage.getItem('stock_search_history');
      if (saved) setSearchHistory(JSON.parse(saved));
    } catch {
      setSearchHistory([]);
    }
    void loadItems(false);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2400);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const ok = await StockService.checkBackendHealth();
      if (!cancelled) setBackendStatus(ok);
    };
    check();
    const timer = window.setInterval(check, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      if (query.trim().length <= 1) {
        setResults([]);
        return;
      }
      const next = await StockService.searchStock(query.trim());
      setResults(next);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  const persistSearchHistory = (stock: SearchResult) => {
    setSearchHistory((prev) => {
      const next = [stock, ...prev.filter((item) => item.symbol !== stock.symbol)].slice(0, 10);
      localStorage.setItem('stock_search_history', JSON.stringify(next));
      return next;
    });
  };

  const handleAddStock = async (stock: SearchResult) => {
    const symbol = stock.symbol.toLowerCase();
    setSaving(true);
    setError('');
    try {
      if (items.some((item) => item.symbol.toLowerCase() === symbol)) {
        showToast(`${stock.name}已在盯盘页`);
      } else {
        await StockService.addToWatchlist(symbol, stock.name);
        showToast(`已加入 ${stock.name}`);
        await loadItems(false);
      }
      persistSearchHistory({ ...stock, symbol });
      setQuery('');
      setResults([]);
      searchInputRef.current?.blur();
    } catch (err) {
      showToast(err instanceof Error ? err.message : '加入失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (item: WatchlistItem) => {
    const name = item.name || item.symbol;
    if (!window.confirm(`从盯盘页移除 ${name}？`)) return;
    setError('');
    try {
      await StockService.removeFromWatchlist(item.symbol);
      setItems((prev) => prev.filter((row) => row.symbol !== item.symbol));
      showToast(`已移除 ${name}`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : '移除失败', 'error');
    }
  };

  const handleMove = (symbol: string, action: MoveAction) => {
    const currentIndex = items.findIndex((item) => item.symbol === symbol);
    if (currentIndex < 0) return;
    const targetIndex = action === 'top'
      ? 0
      : action === 'bottom'
        ? items.length - 1
        : action === 'up'
          ? currentIndex - 1
          : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= items.length || targetIndex === currentIndex) return;

    const next = [...items];
    const [moving] = next.splice(currentIndex, 1);
    next.splice(targetIndex, 0, moving);
    setItems(next);
    StockService.reorderWatchlist(next.map((item) => item.symbol))
      .then(() => showToast('顺序已更新'))
      .catch((err) => {
        showToast(err instanceof Error ? err.message : '顺序保存失败', 'error');
        void loadItems(false);
      });
  };

  const handleEnter = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const target = results[0];
    if (target) void handleAddStock(target);
  };

  const activeCount = Math.min(items.length, PRIMARY_CARD_COUNT);

  return (
    <div className="min-h-screen bg-[#0a0f1c] pb-8 text-slate-200">
      {toast ? (
        <div
          key={toast.id}
          className={`fixed left-1/2 top-3 z-[120] -translate-x-1/2 rounded-md border px-3 py-1.5 text-xs shadow-xl backdrop-blur ${
            toast.tone === 'success'
              ? 'border-emerald-400/30 bg-emerald-500/15 text-emerald-100'
              : 'border-rose-400/30 bg-rose-500/15 text-rose-100'
          }`}
        >
          {toast.text}
        </div>
      ) : null}
      <div className="sticky top-0 z-50 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-2 md:px-6">
          <a
            href="/"
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 text-xs font-medium text-slate-200 hover:border-slate-500"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            单票
          </a>
          <div className="flex items-center gap-2 text-base font-bold text-white">
            <Activity className="h-5 w-5 text-red-400" />
            盯盘页
          </div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
            v{APP_VERSION}
          </span>
          <a
            href="/selection-research"
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-emerald-700/50 bg-emerald-900/30 px-2.5 text-xs font-medium text-emerald-200 hover:bg-emerald-800/40"
          >
            选股
          </a>
          <a
            href="/review"
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-cyan-700/50 bg-cyan-900/30 px-2.5 text-xs font-medium text-cyan-200 hover:bg-cyan-800/40"
          >
            复盘
          </a>

          <div className="flex h-8 items-center gap-px rounded-lg border border-slate-800 bg-slate-950/60 p-0.5">
            <SegmentButton active={boardMode === 'intraday'} onClick={() => setBoardMode('intraday')}>当日</SegmentButton>
            <SegmentButton active={boardMode === 'history'} onClick={() => setBoardMode('history')}>历史</SegmentButton>
          </div>
          <div className="flex h-8 items-center gap-px rounded-lg border border-slate-800 bg-slate-950/60 p-0.5">
            {[30, 90, 180].map((days) => (
              <SegmentButton
                key={days}
                active={boardMode === 'history' && historyDays === days}
                onClick={() => {
                  setBoardMode('history');
                  setHistoryDays(days as HistoryDays);
                }}
              >
                {days}天
              </SegmentButton>
            ))}
          </div>
          <div className="flex h-8 items-center gap-px rounded-lg border border-slate-800 bg-slate-950/60 p-0.5">
            {(['1h', '1d'] as HistoryMultiframeGranularity[]).map((granularity) => (
              <SegmentButton
                key={granularity}
                active={boardMode === 'history' && historyGranularity === granularity}
                onClick={() => {
                  setBoardMode('history');
                  setHistoryGranularity(granularity);
                }}
              >
                {GRANULARITY_LABELS[granularity]}
              </SegmentButton>
            ))}
          </div>

          <div ref={searchContainerRef} className="relative min-w-[240px] flex-1 md:max-w-xl">
            <Search className="absolute left-3 top-2 h-4 w-4 text-slate-400" />
            <input
              ref={searchInputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              onBlur={() => window.setTimeout(() => setIsSearchFocused(false), 180)}
              onKeyDown={handleEnter}
              placeholder="添加代码或简称"
              className="h-8 w-full rounded-lg border border-slate-700 bg-slate-900 pl-9 pr-9 text-sm text-white outline-none transition focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
            />
            {query ? (
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  setResults([]);
                }}
                className="absolute right-3 top-2 text-slate-500 hover:text-slate-200"
                aria-label="清空"
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
            {isSearchFocused && !query && searchHistory.length > 0 ? (
              <div className="absolute left-0 top-full z-50 mt-2 max-h-72 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-800 shadow-xl md:w-96">
                {searchHistory.map((stock) => (
                  <button
                    key={stock.symbol}
                    type="button"
                    disabled={saving}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleAddStock(stock)}
                    className="flex w-full items-center justify-between border-b border-slate-900/40 px-3 py-2 text-left transition last:border-0 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span className="truncate text-sm font-medium text-slate-200">{stock.name}</span>
                    <span className="font-mono text-xs text-slate-500">{stock.symbol}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {results.length > 0 ? (
              <div className="absolute left-0 top-full z-50 mt-2 max-h-72 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-800 shadow-xl md:w-96">
                {results.map((stock) => (
                  <button
                    key={stock.symbol}
                    type="button"
                    disabled={saving}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleAddStock(stock)}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span className="truncate text-sm font-semibold text-white">{stock.name}</span>
                    <span className="font-mono text-xs uppercase text-slate-500">{stock.symbol}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            onClick={() => loadItems(true)}
            disabled={refreshing}
            className="inline-flex h-8 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-2.5 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <span className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 font-mono text-xs text-slate-400">
            <LineChart className="h-3.5 w-3.5 text-sky-300" />
            {activeCount}/{items.length}
          </span>
          <span className={`inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 text-xs ${backendStatus ? 'text-emerald-300' : 'text-rose-300'}`}>
            <Server className="h-3.5 w-3.5" />
            {backendStatus ? '正常' : '断开'}
          </span>
        </div>
      </div>

      <main className="mx-auto max-w-[1800px] px-3 py-3 md:px-4">
        {error ? <div className="mb-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{error}</div> : null}

        {loading ? (
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-12 text-center text-sm text-slate-500">
            加载中
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-12 text-center text-sm text-slate-500">
            当前没有盯盘票
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(390px,1fr))] gap-2.5">
            {items.map((item, index) => (
              <WatchlistCard
                key={item.symbol}
                item={item}
                index={index}
                boardMode={boardMode}
                historyDays={historyDays}
                historyGranularity={historyGranularity}
                total={items.length}
                onRemove={handleRemove}
                onMove={handleMove}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
};

export default WatchlistBoardPage;
