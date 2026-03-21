import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Calendar, RefreshCw, Target } from 'lucide-react';

import { RealTimeQuote, ReviewPoolItem, ReviewBar, SearchResult } from '../../types';
import * as StockService from '../../services/stockService';
import StockQuoteHeroCard from '../common/StockQuoteHeroCard';
import ThresholdConfig from '../dashboard/ThresholdConfig';
import MarketTopHeader from '../common/MarketTopHeader';
import QuoteMetaRow from '../common/QuoteMetaRow';
import { isCurrentCnTradingSession } from '../../utils/marketTime';

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  CandlestickChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

type Granularity = '5m' | '15m' | '30m' | '60m' | '1d';
type GranularityMode = Granularity;
type RangeShortcut = '10d' | '30d' | '60d' | '90d' | '180d' | 'all';

const DEFAULT_SYMBOL = 'sh603629';
const DEFAULT_START = '';
const DEFAULT_END = '';
const DAY_MS = 24 * 60 * 60 * 1000;
const RECENT_RANGE_DAYS = 90;
const SEARCH_DEBOUNCE_MS = 300;
const VALID_SYMBOL_RE = /^(sh|sz|bj)\d{6}$/i;

const RANGE_SHORTCUT_OPTIONS: Array<{ key: RangeShortcut; label: string; days: number | null }> = [
  { key: '10d', label: '10天', days: 10 },
  { key: '30d', label: '30天', days: 30 },
  { key: '60d', label: '60天', days: 60 },
  { key: '90d', label: '90天', days: 90 },
  { key: '180d', label: '180天', days: 180 },
  { key: 'all', label: '全部', days: null },
];

const GRANULARITY_OPTIONS: Array<{ key: GranularityMode; label: string }> = [
  { key: '5m', label: '5m' },
  { key: '15m', label: '15m' },
  { key: '30m', label: '30m' },
  { key: '60m', label: '60m' },
  { key: '1d', label: '1d' },
];

const GRANULARITY_MINUTES: Record<Exclude<Granularity, '1d'>, number> = {
  '5m': 5,
  '15m': 15,
  '30m': 30,
  '60m': 60,
};

const REVIEW_COLORS = {
  mainL2Buy: '#D32F2F',
  mainL1Buy: '#EF9A9A',
  mainL2Sell: '#388E3C',
  mainL1Sell: '#81C784',
  superL2Buy: '#7B1FA2',
  superL1Buy: '#BA68C8',
  superL2Sell: '#00796B',
  superL1Sell: '#4DB6AC',
  closeLine: '#FBBF24',
};

const parseLocalDateTime = (datetimeText: string): Date => {
  const [datePart, timePart = '00:00:00'] = datetimeText.split(' ');
  const [year, month, day] = datePart.split('-').map((v) => parseInt(v, 10));
  const [hour, minute, second] = timePart.split(':').map((v) => parseInt(v, 10));
  return new Date(year, (month || 1) - 1, day || 1, hour || 0, minute || 0, second || 0, 0);
};

const formatLocalDateTime = (date: Date): string => {
  const pad = (value: number) => `${value}`.padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
};

const normalizeRows = (rows: ReviewBar[]): ReviewBar[] => {
  return [...rows].sort((a, b) => parseLocalDateTime(a.datetime).getTime() - parseLocalDateTime(b.datetime).getTime());
};

type Acc = {
  ts: number;
  symbol: string;
  sourceDate: string;
  firstTs: number;
  lastTs: number;
  open: number;
  high: number;
  low: number;
  close: number;
  total_amount: number;
  l1_main_buy: number;
  l1_main_sell: number;
  l1_super_buy: number;
  l1_super_sell: number;
  l2_main_buy: number;
  l2_main_sell: number;
  l2_super_buy: number;
  l2_super_sell: number;
};

const createAccFromRow = (row: ReviewBar, ts: number): Acc => ({
  ts,
  symbol: row.symbol,
  sourceDate: row.source_date,
  firstTs: ts,
  lastTs: ts,
  open: row.open,
  high: row.high,
  low: row.low,
  close: row.close,
  total_amount: Number.isFinite(row.total_amount) ? row.total_amount : 0,
  l1_main_buy: row.l1_main_buy,
  l1_main_sell: row.l1_main_sell,
  l1_super_buy: row.l1_super_buy,
  l1_super_sell: row.l1_super_sell,
  l2_main_buy: row.l2_main_buy,
  l2_main_sell: row.l2_main_sell,
  l2_super_buy: row.l2_super_buy,
  l2_super_sell: row.l2_super_sell,
});

const mergeRowToAcc = (acc: Acc, row: ReviewBar, ts: number): void => {
  acc.high = Math.max(acc.high, row.high);
  acc.low = Math.min(acc.low, row.low);
  if (ts < acc.firstTs) {
    acc.firstTs = ts;
    acc.open = row.open;
  }
  if (ts >= acc.lastTs) {
    acc.lastTs = ts;
    acc.close = row.close;
    acc.sourceDate = row.source_date;
  }
  acc.total_amount += Number.isFinite(row.total_amount) ? row.total_amount : 0;
  acc.l1_main_buy += row.l1_main_buy;
  acc.l1_main_sell += row.l1_main_sell;
  acc.l1_super_buy += row.l1_super_buy;
  acc.l1_super_sell += row.l1_super_sell;
  acc.l2_main_buy += row.l2_main_buy;
  acc.l2_main_sell += row.l2_main_sell;
  acc.l2_super_buy += row.l2_super_buy;
  acc.l2_super_sell += row.l2_super_sell;
};

const toBar = (acc: Acc, datetime: string, granularity: Granularity): ReviewBar => ({
  symbol: acc.symbol,
  datetime,
  open: acc.open,
  high: acc.high,
  low: acc.low,
  close: acc.close,
  total_amount: acc.total_amount,
  l1_main_buy: acc.l1_main_buy,
  l1_main_sell: acc.l1_main_sell,
  l1_main_net: acc.l1_main_buy - acc.l1_main_sell,
  l1_super_buy: acc.l1_super_buy,
  l1_super_sell: acc.l1_super_sell,
  l1_super_net: acc.l1_super_buy - acc.l1_super_sell,
  l2_main_buy: acc.l2_main_buy,
  l2_main_sell: acc.l2_main_sell,
  l2_main_net: acc.l2_main_buy - acc.l2_main_sell,
  l2_super_buy: acc.l2_super_buy,
  l2_super_sell: acc.l2_super_sell,
  l2_super_net: acc.l2_super_buy - acc.l2_super_sell,
  source_date: datetime.slice(0, 10),
  bucket_granularity: granularity,
});

const aggregateRows = (rows: ReviewBar[], granularity: Granularity): ReviewBar[] => {
  if (granularity === '5m') {
    return rows.map((row) => ({
      ...row,
      total_amount: Number.isFinite(row.total_amount) ? row.total_amount : 0,
      bucket_granularity: '5m',
    }));
  }

  if (granularity === '1d') {
    const buckets = new Map<string, Acc>();
    for (const row of rows) {
      const ts = parseLocalDateTime(row.datetime).getTime();
      const bucketKey = row.source_date || row.datetime.slice(0, 10);
      const prev = buckets.get(bucketKey);
      if (!prev) {
        buckets.set(bucketKey, createAccFromRow(row, ts));
      } else {
        mergeRowToAcc(prev, row, ts);
      }
    }

    return Array.from(buckets.entries())
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .map(([dateKey, acc]) => toBar(acc, `${dateKey} 15:00:00`, '1d'));
  }

  const minutes = GRANULARITY_MINUTES[granularity];
  const bucketMs = minutes * 60 * 1000;
  const buckets = new Map<number, Acc>();

  for (const row of rows) {
    const ts = parseLocalDateTime(row.datetime).getTime();
    const bucketTs = Math.floor(ts / bucketMs) * bucketMs;
    const prev = buckets.get(bucketTs);
    if (!prev) {
      buckets.set(bucketTs, createAccFromRow(row, ts));
    } else {
      mergeRowToAcc(prev, row, ts);
    }
  }

  return Array.from(buckets.values())
    .sort((a, b) => a.ts - b.ts)
    .map((acc) => toBar(acc, formatLocalDateTime(new Date(acc.ts)), granularity));
};

const calcVisibleDays = (rows: ReviewBar[], zoomRange: [number, number]): number => {
  if (rows.length <= 1) return 0;

  const denominator = Math.max(1, rows.length - 1);
  const startIdx = Math.floor((zoomRange[0] / 100) * denominator);
  const endIdx = Math.ceil((zoomRange[1] / 100) * denominator);
  const start = parseLocalDateTime(rows[Math.max(0, startIdx)].datetime).getTime();
  const end = parseLocalDateTime(rows[Math.min(rows.length - 1, Math.max(startIdx, endIdx))].datetime).getTime();
  return Math.max(0, (end - start) / DAY_MS);
};

const calcRangeDaysInclusive = (startDate: string, endDate: string): number => {
  const start = parseDateOnly(startDate);
  const end = parseDateOnly(endDate);
  if (!start || !end) return 0;
  return Math.max(1, Math.round((end.getTime() - start.getTime()) / DAY_MS) + 1);
};

const chooseGranularityForDateRange = (startDate: string, endDate: string): Granularity => {
  const days = calcRangeDaysInclusive(startDate, endDate);
  if (days <= 1) return '5m';
  if (days <= 5) return '15m';
  if (days <= 20) return '30m';
  if (days <= 30) return '60m';
  return '1d';
};

const estimateVisibleCount = (rows: ReviewBar[], zoomRange: [number, number]): number => {
  if (!rows.length) return 0;
  const ratio = Math.max(0.01, (zoomRange[1] - zoomRange[0]) / 100);
  return Math.max(1, Math.round(rows.length * ratio));
};

const formatFlowValueW = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  return `${(value / 10000).toFixed(2)}w`;
};

const trimTrailingZeros = (valueText: string): string => valueText.replace(/\.0+$|(\.\d*[1-9])0+$/, '$1');

const formatAmountCompact = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${sign}${trimTrailingZeros((abs / 100000000).toFixed(2))}亿`;
  if (abs >= 10000) return `${sign}${trimTrailingZeros((abs / 10000).toFixed(2))}万`;
  return `${sign}${trimTrailingZeros(abs.toFixed(0))}`;
};

const formatPercentValue = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  return `${value.toFixed(2)}%`;
};

const formatPercentAxis = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  return `${Math.round(value)}%`;
};

const formatMarketCapYi = (marketCap?: number): string | null => {
  if (!Number.isFinite(marketCap) || (marketCap || 0) <= 0) return null;
  return `${trimTrailingZeros(((marketCap || 0) / 100000000).toFixed(2))}亿`;
};

const isDateInReviewWindow = (
  startDate: string,
  endDate: string,
  minDate?: string,
  maxDate?: string
): boolean => {
  if (!startDate || !endDate || endDate < startDate) return false;
  if (minDate && startDate < minDate) return false;
  if (maxDate && endDate > maxDate) return false;
  return true;
};

const calcRatioPercent = (numerator: number, denominator: number): number | null => {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return null;
  return (numerator / denominator) * 100;
};

const splitSignedSeriesNullable = (
  values: Array<number | null>
): { positive: Array<number | null>; negative: Array<number | null> } => ({
  positive: values.map((value) => (value === null ? null : value > 0 ? value : 0)),
  negative: values.map((value) => (value === null ? null : value < 0 ? value : 0)),
});

const parseDateOnly = (dateText: string): Date | null => {
  if (!dateText) return null;
  const [year, month, day] = dateText.split('-').map((value) => parseInt(value, 10));
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day, 0, 0, 0, 0);
};

const formatDateOnly = (date: Date): string => {
  const pad = (value: number) => `${value}`.padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

const minusDays = (dateText: string, days: number): string => {
  const date = parseDateOnly(dateText);
  if (!date) return dateText;
  date.setDate(date.getDate() - days);
  return formatDateOnly(date);
};

const buildRecentRange = (maxDate: string, minDate?: string, days = RECENT_RANGE_DAYS) => {
  const endDate = maxDate;
  const shiftedStart = minusDays(endDate, Math.max(0, days - 1));
  const startDate = minDate && shiftedStart < minDate ? minDate : shiftedStart;
  return { startDate, endDate };
};

const normalizeSymbolText = (value: string): string => {
  const normalized = value.trim().toLowerCase();
  return VALID_SYMBOL_RE.test(normalized) ? normalized : '';
};

const getInitialReviewSymbol = (): string => {
  if (typeof window === 'undefined') return DEFAULT_SYMBOL;
  const value = new URLSearchParams(window.location.search).get('symbol') || '';
  return normalizeSymbolText(value) || DEFAULT_SYMBOL;
};

const buildStockDisplayName = (symbol: string, name?: string) => {
  if (name && name.trim()) return name.trim();
  return symbol;
};

const SandboxReviewPage: React.FC = () => {
  const [poolItems, setPoolItems] = useState<ReviewPoolItem[]>([]);
  const [poolLatestDate, setPoolLatestDate] = useState('');
  const [symbolInput, setSymbolInput] = useState(() => getInitialReviewSymbol());
  const [searchQuery, setSearchQuery] = useState(DEFAULT_SYMBOL);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [searchHistory, setSearchHistory] = useState<SearchResult[]>([]);
  const [isSearchDirty, setIsSearchDirty] = useState(false);
  const [selectedSearchStock, setSelectedSearchStock] = useState<SearchResult | null>(null);
  const [selectedQuote, setSelectedQuote] = useState<RealTimeQuote | null>(null);
  const [turnoverRate, setTurnoverRate] = useState<number | null>(null);
  const [startDateInput, setStartDateInput] = useState(DEFAULT_START);
  const [endDateInput, setEndDateInput] = useState(DEFAULT_END);
  const [isRangePickerOpen, setIsRangePickerOpen] = useState(false);
  const [draftStartDate, setDraftStartDate] = useState(DEFAULT_START);
  const [draftEndDate, setDraftEndDate] = useState(DEFAULT_END);
  const [activeRangeShortcut, setActiveRangeShortcut] = useState<RangeShortcut>('90d');
  const [rawData, setRawData] = useState<ReviewBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [emptyMessage, setEmptyMessage] = useState('');
  const [zoomRange, setZoomRange] = useState<[number, number]>([0, 100]);
  const [granularityMode, setGranularityMode] = useState<GranularityMode>('60m');
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [backendStatus, setBackendStatus] = useState(false);
  const [focusMode, setFocusMode] = useState<'normal' | 'focus'>('normal');
  const [anchorModeEnabled, setAnchorModeEnabled] = useState(false);
  const [anchorTs, setAnchorTs] = useState<number | null>(null);
  const searchRef = useRef<HTMLDivElement | null>(null);
  const rangePickerRef = useRef<HTMLDivElement | null>(null);

  const fetchData = useCallback(async (symbol: string, startDate: string, endDate: string) => {
    setLoading(true);
    setError('');
    setEmptyMessage('');
    try {
      const rows = await StockService.fetchReviewData(symbol, startDate, endDate, '5m');
      if (!rows.length) {
        setRawData([]);
        setZoomRange([0, 100]);
        setEmptyMessage(`正式复盘暂未覆盖 ${symbol} 在 ${startDate} ~ ${endDate} 的数据。`);
        return;
      }

      const sortedRows = normalizeRows(rows);
      setRawData(sortedRows);
      setZoomRange([0, 100]);
    } catch (err: any) {
      setRawData([]);
      setError(err?.message || '查询失败，请检查正式复盘接口与生产历史库。');
    } finally {
      setLoading(false);
    }
  }, []);

  const resolveDefaultRange = useCallback(
    (symbol: string) => {
      const matched = poolItems.find((item) => item.symbol === symbol);
      if (matched) return buildRecentRange(matched.max_date, matched.min_date, RECENT_RANGE_DAYS);
      const fallbackEnd = poolLatestDate || formatDateOnly(new Date());
      return buildRecentRange(fallbackEnd, undefined, RECENT_RANGE_DAYS);
    },
    [poolItems, poolLatestDate]
  );

  const applySelectedStock = useCallback(
    async (stock: Pick<SearchResult, 'symbol' | 'name' | 'code' | 'market'> | { symbol: string; name?: string }) => {
      const normalizedSymbol = stock.symbol.trim().toLowerCase();
      if (!normalizedSymbol) return;
      const matched = poolItems.find((item) => item.symbol === normalizedSymbol);
      const displayName = stock.name || matched?.name || '';
      const range = matched
        ? buildRecentRange(matched.max_date, matched.min_date, RECENT_RANGE_DAYS)
        : resolveDefaultRange(normalizedSymbol);

      setSymbolInput(normalizedSymbol);
      setSearchQuery('');
      setIsSearchDirty(false);
      setIsSearchFocused(false);
      setSearchResults([]);
      setSelectedSearchStock({
        symbol: normalizedSymbol,
        name: displayName || normalizedSymbol,
        code: 'code' in stock && stock.code ? stock.code : normalizedSymbol.slice(2),
        market: 'market' in stock && stock.market ? stock.market : normalizedSymbol.slice(0, 2),
      });
      setStartDateInput(range.startDate);
      setEndDateInput(range.endDate);
      setDraftStartDate(range.startDate);
      setDraftEndDate(range.endDate);
      setActiveRangeShortcut('90d');
      setGranularityMode(chooseGranularityForDateRange(range.startDate, range.endDate));
      setAnchorTs(null);
      const historyItem = {
        symbol: normalizedSymbol,
        name: displayName || normalizedSymbol,
        code: 'code' in stock && stock.code ? stock.code : normalizedSymbol.slice(2),
        market: 'market' in stock && stock.market ? stock.market : normalizedSymbol.slice(0, 2),
      };
      setSearchHistory((prev) => {
        const next = [historyItem, ...prev.filter((item) => item.symbol !== historyItem.symbol)].slice(0, 10);
        localStorage.setItem('stock_search_history', JSON.stringify(next));
        return next;
      });
      await fetchData(normalizedSymbol, range.startDate, range.endDate);
    },
    [fetchData, poolItems, resolveDefaultRange]
  );

  useEffect(() => {
    const init = async () => {
      try {
        const pool = await StockService.fetchReviewPool('', 5000);
        setPoolItems(pool.items);
        setPoolLatestDate(pool.latest_date || '');
        if (pool.items.length > 0) {
          const preferredSymbol = getInitialReviewSymbol();
          const picked = pool.items.find((item) => item.symbol === preferredSymbol) || pool.items.find((item) => item.symbol === DEFAULT_SYMBOL) || pool.items[0];
          const range = buildRecentRange(picked.max_date, picked.min_date, RECENT_RANGE_DAYS);
          setSymbolInput(picked.symbol);
          setSearchQuery('');
          setSelectedSearchStock({
            symbol: picked.symbol,
            name: picked.name,
            code: picked.symbol.slice(2),
            market: picked.symbol.slice(0, 2),
          });
          setStartDateInput(range.startDate);
          setEndDateInput(range.endDate);
          setDraftStartDate(range.startDate);
          setDraftEndDate(range.endDate);
          setGranularityMode(chooseGranularityForDateRange(range.startDate, range.endDate));
          await fetchData(picked.symbol, range.startDate, range.endDate);
          return;
        }
        setError('正式复盘股票池为空，请先迁移历史数据并刷新股票元数据。');
      } catch (e: any) {
        setError(e?.message || '股票池加载失败，请检查 /api/review/pool');
      }
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    const check = async () => {
      const isHealthy = await StockService.checkBackendHealth();
      setBackendStatus(isHealthy);
    };
    check();
    const interval = setInterval(check, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const matched = poolItems.find((item) => item.symbol === symbolInput.trim().toLowerCase());
    if (!matched) return;

    setStartDateInput((prev) => {
      if (!prev || prev < matched.min_date || prev > matched.max_date) return matched.min_date;
      return prev;
    });
    setEndDateInput((prev) => {
      if (!prev || prev > matched.max_date || prev < matched.min_date) return matched.max_date;
      return prev;
    });
  }, [poolItems, symbolInput]);

  useEffect(() => {
    if (!isSearchDirty) {
      setSearchResults([]);
      return;
    }

    const keyword = searchQuery.trim();
    if (keyword.length < 2) {
      setSearchResults([]);
      return;
    }

    const timer = window.setTimeout(async () => {
      const results = await StockService.searchStock(keyword);
      setSearchResults(results);
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [isSearchDirty, searchQuery]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (searchRef.current && !searchRef.current.contains(target)) {
        setIsSearchFocused(false);
        setSearchResults([]);
      }
      if (rangePickerRef.current && !rangePickerRef.current.contains(target)) {
        setIsRangePickerOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, []);

  useEffect(() => {
    const symbol = symbolInput.trim().toLowerCase();
    if (!symbol) {
      setSelectedQuote(null);
      return;
    }
    let cancelled = false;
    StockService.fetchQuote(symbol)
      .then((quote) => {
        if (cancelled) return;
        setSelectedQuote(quote);
      })
      .catch(() => {
        if (cancelled) return;
        setSelectedQuote(null);
      });
    return () => {
      cancelled = true;
    };
  }, [symbolInput]);

  useEffect(() => {
    const symbol = symbolInput.trim().toLowerCase();
    if (!symbol) {
      setTurnoverRate(null);
      return;
    }
    let cancelled = false;
    StockService.fetchSentimentData(symbol)
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
  }, [symbolInput]);

  useEffect(() => {
    const symbol = symbolInput.trim().toLowerCase();
    if (!symbol) {
      setIsWatchlisted(false);
      return;
    }
    StockService.getWatchlist().then((list) => {
      setIsWatchlisted(Boolean(list.find((item) => item.symbol === symbol)));
    });
  }, [symbolInput]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    if (symbolInput) {
      url.searchParams.set('symbol', symbolInput.toLowerCase());
    } else {
      url.searchParams.delete('symbol');
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }, [symbolInput]);

  const toggleWatchlist = async () => {
    if (!symbolInput) return;
    const symbol = symbolInput.trim().toLowerCase();
    if (isWatchlisted) {
      await StockService.removeFromWatchlist(symbol);
      setIsWatchlisted(false);
    } else {
      await StockService.addToWatchlist(symbol, selectedDisplayName);
      setIsWatchlisted(true);
    }
  };

  const aggregatedByGranularity = useMemo(() => {
    const sortedRaw = normalizeRows(rawData);
    return {
      '5m': aggregateRows(sortedRaw, '5m'),
      '15m': aggregateRows(sortedRaw, '15m'),
      '30m': aggregateRows(sortedRaw, '30m'),
      '60m': aggregateRows(sortedRaw, '60m'),
      '1d': aggregateRows(sortedRaw, '1d'),
    } as Record<Granularity, ReviewBar[]>;
  }, [rawData]);

  const viewState = useMemo(() => {
    const baseRows = aggregatedByGranularity['5m'];
    const visibleDays = calcVisibleDays(baseRows, zoomRange);
    const granularity: Granularity = granularityMode;

    return {
      bars: aggregatedByGranularity[granularity],
      granularity,
      visibleDays,
      visibleCount: estimateVisibleCount(aggregatedByGranularity[granularity], zoomRange),
    };
  }, [aggregatedByGranularity, granularityMode, zoomRange]);

  const correlationData = useMemo(() => {
    const rows = aggregatedByGranularity['5m'];
    if (!rows.length) {
      return {
        points: [] as Array<{
          datetime: string;
          priceReturn: number;
          nextPriceReturn: number | null;
          l1Net: number;
          l2Net: number;
          l1ActivityRatio: number;
          l2ActivityRatio: number;
        }>,
      };
    }

    const points = rows.map((row, index) => {
      const open = row.open;
      const close = row.close;
      const totalAmount = Number(row.total_amount) || 0;
      const priceReturn = open > 0 ? ((close - open) / open) * 100 : NaN;
      const nextRow = rows[index + 1];
      const nextPriceReturn =
        nextRow && nextRow.open > 0 ? ((nextRow.close - nextRow.open) / nextRow.open) * 100 : null;

      const l1Abs = row.l1_main_buy + row.l1_main_sell;
      const l2Abs = row.l2_main_buy + row.l2_main_sell;

      return {
        datetime: row.datetime,
        priceReturn,
        nextPriceReturn,
        l1Net: row.l1_main_net,
        l2Net: row.l2_main_net,
        l1ActivityRatio: totalAmount > 0 ? (l1Abs / totalAmount) * 100 : NaN,
        l2ActivityRatio: totalAmount > 0 ? (l2Abs / totalAmount) * 100 : NaN,
      };
    });

    return { points };
  }, [aggregatedByGranularity]);

  const correlationStats = useMemo(() => {
    const points = correlationData.points.filter(
      (p) =>
        Number.isFinite(p.priceReturn) &&
        Number.isFinite(p.l1Net) &&
        Number.isFinite(p.l2Net) &&
        Number.isFinite(p.l1ActivityRatio) &&
        Number.isFinite(p.l2ActivityRatio)
    );

    const pearson = (x: number[], y: number[]): number | null => {
      if (x.length < 2 || y.length < 2 || x.length !== y.length) return null;
      const mx = x.reduce((a, b) => a + b, 0) / x.length;
      const my = y.reduce((a, b) => a + b, 0) / y.length;
      let cov = 0;
      let vx = 0;
      let vy = 0;
      for (let i = 0; i < x.length; i += 1) {
        const dx = x[i] - mx;
        const dy = y[i] - my;
        cov += dx * dy;
        vx += dx * dx;
        vy += dy * dy;
      }
      if (vx <= 0 || vy <= 0) return null;
      return cov / Math.sqrt(vx * vy);
    };

    const concurrent = points;
    const leadLag = points.filter((p) => Number.isFinite(p.nextPriceReturn));
    const highActivity = leadLag.filter((p) => (p.l2ActivityRatio || 0) > 30);

    const l1Concurrent = pearson(
      concurrent.map((p) => p.l1Net),
      concurrent.map((p) => p.priceReturn)
    );
    const l2Concurrent = pearson(
      concurrent.map((p) => p.l2Net),
      concurrent.map((p) => p.priceReturn)
    );

    const l1Lead = pearson(
      leadLag.map((p) => p.l1Net),
      leadLag.map((p) => p.nextPriceReturn as number)
    );
    const l2Lead = pearson(
      leadLag.map((p) => p.l2Net),
      leadLag.map((p) => p.nextPriceReturn as number)
    );

    const l2Conditional = pearson(
      highActivity.map((p) => p.l2Net),
      highActivity.map((p) => p.nextPriceReturn as number)
    );

    return {
      concurrentCount: concurrent.length,
      leadCount: leadLag.length,
      highActivityCount: highActivity.length,
      highActivityRatio: leadLag.length ? (highActivity.length / leadLag.length) * 100 : 0,
      l1Concurrent,
      l2Concurrent,
      l1Lead,
      l2Lead,
      l2Conditional,
    };
  }, [correlationData]);

  const scatterData = useMemo(() => {
    const points = correlationData.points.filter((p) => Number.isFinite(p.priceReturn));
    const buildScatter = (netKey: 'l1Net' | 'l2Net', ratioKey: 'l1ActivityRatio' | 'l2ActivityRatio') =>
      points.map((p) => ({
        value: [p[netKey], p.priceReturn, p[ratioKey], p.datetime],
      }));
    return {
      l1: buildScatter('l1Net', 'l1ActivityRatio'),
      l2: buildScatter('l2Net', 'l2ActivityRatio'),
    };
  }, [correlationData]);

  const makeScatterOption = useCallback(
    (title: string, data: Array<{ value: [number, number, number, string] }>) => ({
      animation: false,
      title: {
        text: title,
        left: 'center',
        top: 6,
        textStyle: { color: '#cbd5e1', fontSize: 12, fontWeight: 'normal' },
      },
      grid: { left: '8%', right: '5%', top: 36, bottom: 36 },
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: '#334155',
        borderWidth: 1,
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        formatter: (params: any) => {
          const value = params?.value || [];
          const net = Number(value[0] || 0);
          const ret = Number(value[1] || 0);
          const ratio = Number(value[2] || 0);
          const dt = value[3] || '--';
          return [
            `${dt}`,
            `净流入: ${formatFlowValueW(net)}`,
            `涨跌幅: ${ret.toFixed(3)}%`,
            `活跃度: ${ratio.toFixed(2)}%`,
          ].join('<br/>');
        },
      },
      xAxis: {
        type: 'value',
        axisLabel: {
          color: '#94a3b8',
          formatter: (v: number) => formatFlowValueW(v),
        },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8', formatter: (v: number) => formatPercentAxis(v) },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      series: [
        {
          type: 'scatter',
          data,
          symbolSize: (val: any) => {
            const ratio = Number(val?.[2] || 0);
            return Math.max(6, Math.min(20, 6 + ratio * 0.4));
          },
          itemStyle: {
            color: (params: any) => {
              const ratio = Number(params?.value?.[2] || 0);
              if (ratio >= 50) return '#ef4444';
              if (ratio >= 30) return '#f97316';
              if (ratio >= 15) return '#f59e0b';
              return '#94a3b8';
            },
            opacity: 0.8,
          },
        },
      ],
    }),
    []
  );

  const scatterOptionL1 = useMemo(
    () => makeScatterOption('L1净流入 vs 5分钟涨跌幅', scatterData.l1),
    [makeScatterOption, scatterData.l1]
  );
  const scatterOptionL2 = useMemo(
    () => makeScatterOption('L2净流入 vs 5分钟涨跌幅', scatterData.l2),
    [makeScatterOption, scatterData.l2]
  );

  const selectedInputPoolItem = useMemo(
    () => poolItems.find((item) => item.symbol === symbolInput.trim().toLowerCase()) || null,
    [poolItems, symbolInput]
  );

  const selectedDisplayName = useMemo(() => {
    const normalizedSymbol = symbolInput.trim().toLowerCase();
    if (selectedQuote?.symbol === normalizedSymbol && selectedQuote?.name) return selectedQuote.name;
    if (selectedInputPoolItem?.name) return buildStockDisplayName(normalizedSymbol, selectedInputPoolItem.name);
    if (selectedSearchStock?.symbol === normalizedSymbol) return buildStockDisplayName(normalizedSymbol, selectedSearchStock.name);
    return normalizedSymbol || DEFAULT_SYMBOL;
  }, [selectedInputPoolItem?.name, selectedQuote, selectedSearchStock, symbolInput]);

  const latestDailySummary = useMemo(() => {
    const dailyBars = aggregatedByGranularity['1d'];
    if (!dailyBars.length) return null;
    const latest = dailyBars[dailyBars.length - 1];
    const previous = dailyBars.length > 1 ? dailyBars[dailyBars.length - 2] : null;
    const previousClose = previous?.close ?? latest.open;
    const delta = latest.close - previousClose;
    const pct = previousClose > 0 ? (delta / previousClose) * 100 : 0;
    return {
      latest,
      previousClose,
      delta,
      pct,
    };
  }, [aggregatedByGranularity]);

  const searchDropdownVisible = isSearchFocused && isSearchDirty && searchResults.length > 0;

  const resolveShortcutRange = useCallback(
    (shortcut: RangeShortcut) => {
      if (shortcut === 'all') {
        if (selectedInputPoolItem) {
          return {
            startDate: selectedInputPoolItem.min_date,
            endDate: selectedInputPoolItem.max_date,
          };
        }
        const fallbackEnd = poolLatestDate || formatDateOnly(new Date());
        return {
          startDate: minusDays(fallbackEnd, RECENT_RANGE_DAYS - 1),
          endDate: fallbackEnd,
        };
      }

      const option = RANGE_SHORTCUT_OPTIONS.find((item) => item.key === shortcut);
      const days = option?.days ?? RECENT_RANGE_DAYS;
      if (selectedInputPoolItem) {
        return buildRecentRange(selectedInputPoolItem.max_date, selectedInputPoolItem.min_date, days || RECENT_RANGE_DAYS);
      }

      const fallbackEnd = poolLatestDate || formatDateOnly(new Date());
      return buildRecentRange(fallbackEnd, undefined, days || RECENT_RANGE_DAYS);
    },
    [poolLatestDate, selectedInputPoolItem]
  );

  const executeReviewQuery = useCallback(
    async (symbol: string, startDate: string, endDate: string, minDate?: string, maxDate?: string) => {
      if (!symbol) {
        setError('请先选择股票');
        return;
      }
      if (!isDateInReviewWindow(startDate, endDate, minDate, maxDate)) {
        if (minDate && maxDate) {
          setError(`日期范围仅支持 ${minDate} ~ ${maxDate}`);
        } else {
          setError('日期范围无效，请确认开始/结束日期');
        }
        return;
      }
      setAnchorTs(null);
      await fetchData(symbol, startDate, endDate);
    },
    [fetchData]
  );

  const handleExecuteQuery = useCallback(async () => {
    const normalizedFromInput = normalizeSymbolText(searchQuery);
    const symbol = isSearchDirty ? normalizedFromInput : symbolInput.trim().toLowerCase();
    if (isSearchDirty && searchResults.length > 0) {
      await applySelectedStock(searchResults[0]);
      return;
    }
    if (!symbol) {
      setError('请先从搜索结果选择股票，或输入完整代码（如 sh603629）');
      return;
    }
    if (isSearchDirty) {
      if (symbol !== symbolInput.trim().toLowerCase()) {
        const matched = poolItems.find((item) => item.symbol === symbol);
        await applySelectedStock({ symbol, name: matched?.name });
        return;
      }
      const matched = poolItems.find((item) => item.symbol === symbol) || null;
      setSearchQuery(buildStockDisplayName(symbol, matched?.name || selectedSearchStock?.name));
      setIsSearchDirty(false);
    }
    const matched = poolItems.find((item) => item.symbol === symbol) || null;
    await executeReviewQuery(symbol, startDateInput, endDateInput, matched?.min_date, matched?.max_date);
  }, [applySelectedStock, endDateInput, executeReviewQuery, isSearchDirty, poolItems, searchQuery, searchResults, selectedSearchStock?.name, startDateInput, symbolInput]);

  const handleSelectSearchResult = useCallback(
    async (stock: SearchResult) => {
      await applySelectedStock(stock);
    },
    [applySelectedStock]
  );

  const openRangePicker = useCallback(() => {
    setDraftStartDate(startDateInput);
    setDraftEndDate(endDateInput);
    setIsRangePickerOpen((prev) => !prev);
  }, [endDateInput, startDateInput]);

  const handleQuickRangeShortcut = useCallback(
    async (shortcut: RangeShortcut) => {
      const symbol = symbolInput.trim().toLowerCase();
      if (!symbol) {
        setError('请先选择股票');
        return;
      }
      const range = resolveShortcutRange(shortcut);
      setActiveRangeShortcut(shortcut);
      setStartDateInput(range.startDate);
      setEndDateInput(range.endDate);
      setDraftStartDate(range.startDate);
      setDraftEndDate(range.endDate);
      setGranularityMode(chooseGranularityForDateRange(range.startDate, range.endDate));
      await executeReviewQuery(symbol, range.startDate, range.endDate, selectedInputPoolItem?.min_date, selectedInputPoolItem?.max_date);
    },
    [executeReviewQuery, resolveShortcutRange, selectedInputPoolItem?.max_date, selectedInputPoolItem?.min_date, symbolInput]
  );

  const handleConfirmRange = useCallback(async () => {
    const symbol = symbolInput.trim().toLowerCase();
    if (!symbol) {
      setError('请先选择股票');
      return;
    }
    setStartDateInput(draftStartDate);
    setEndDateInput(draftEndDate);
    setGranularityMode(chooseGranularityForDateRange(draftStartDate, draftEndDate));
    setIsRangePickerOpen(false);
    await executeReviewQuery(symbol, draftStartDate, draftEndDate, selectedInputPoolItem?.min_date, selectedInputPoolItem?.max_date);
  }, [draftEndDate, draftStartDate, executeReviewQuery, selectedInputPoolItem?.max_date, selectedInputPoolItem?.min_date, symbolInput]);

  const handleDataZoom = useCallback((event: any) => {
    const payload = event?.batch?.[0] ?? event;
    const nextStart = typeof payload?.start === 'number' ? payload.start : zoomRange[0];
    const nextEnd = typeof payload?.end === 'number' ? payload.end : zoomRange[1];
    const normalized: [number, number] = [
      Math.max(0, Math.min(100, nextStart)),
      Math.max(0, Math.min(100, nextEnd)),
    ];

    if (Math.abs(normalized[0] - zoomRange[0]) > 0.01 || Math.abs(normalized[1] - zoomRange[1]) > 0.01) {
      setZoomRange(normalized);
    }
  }, [zoomRange]);

  const handleChartClick = useCallback((event: any) => {
    if (!anchorModeEnabled) return;
    if (event?.seriesType !== 'candlestick') return;
    const dataIndex = typeof event?.dataIndex === 'number' ? event.dataIndex : -1;
    if (dataIndex < 0 || dataIndex >= viewState.bars.length) return;
    const row = viewState.bars[dataIndex];
    if (!row?.datetime) return;
    setAnchorTs(parseLocalDateTime(row.datetime).getTime());
  }, [anchorModeEnabled, viewState.bars]);

  const option = useMemo(() => {
    const data = viewState.bars;
    if (!data.length) {
      return {};
    }

    const category = data.map((row) => (
      viewState.granularity === '1d' ? row.datetime.substring(5, 10) : row.datetime.substring(5, 16)
    ));
    const candles = data.map((row) => [row.open, row.close, row.low, row.high]);

    const l1MainBuy = data.map((row) => row.l1_main_buy);
    const l1MainSell = data.map((row) => -row.l1_main_sell);
    const l1SuperBuy = data.map((row) => row.l1_super_buy);
    const l1SuperSell = data.map((row) => -row.l1_super_sell);
    const l1MainNet = data.map((row) => row.l1_main_net);
    const l1SuperNet = data.map((row) => row.l1_super_net);

    const l2MainBuy = data.map((row) => row.l2_main_buy);
    const l2MainSell = data.map((row) => -row.l2_main_sell);
    const l2SuperBuy = data.map((row) => row.l2_super_buy);
    const l2SuperSell = data.map((row) => -row.l2_super_sell);
    const l2MainNet = data.map((row) => row.l2_main_net);
    const l2SuperNet = data.map((row) => row.l2_super_net);

    const resolvedTotalAmount = data.map((row) => {
      if (row.total_amount > 0) return row.total_amount;
      return Math.max(
        0,
        row.l1_main_buy + row.l1_main_sell + row.l1_super_buy + row.l1_super_sell,
        row.l2_main_buy + row.l2_main_sell + row.l2_super_buy + row.l2_super_sell
      );
    });

    const l1MainActivity = data.map((row, idx) => calcRatioPercent(row.l1_main_buy + row.l1_main_sell, resolvedTotalAmount[idx]));
    const l2MainActivity = data.map((row, idx) => calcRatioPercent(row.l2_main_buy + row.l2_main_sell, resolvedTotalAmount[idx]));
    const l1SuperActivity = data.map((row, idx) => calcRatioPercent(row.l1_super_buy + row.l1_super_sell, resolvedTotalAmount[idx]));
    const l2SuperActivity = data.map((row, idx) => calcRatioPercent(row.l2_super_buy + row.l2_super_sell, resolvedTotalAmount[idx]));
    const l1NetRatio = data.map((row, idx) => calcRatioPercent(row.l1_main_net + row.l1_super_net, resolvedTotalAmount[idx]));
    const l2NetRatio = data.map((row, idx) => calcRatioPercent(row.l2_main_net + row.l2_super_net, resolvedTotalAmount[idx]));

    const timestamps = data.map((row) => parseLocalDateTime(row.datetime).getTime());
    const anchorIndex = anchorModeEnabled && anchorTs !== null ? timestamps.findIndex((ts) => ts >= anchorTs) : -1;
    const hasAnchorSelection = anchorModeEnabled && anchorIndex >= 0;
    const anchorCategory = hasAnchorSelection ? category[anchorIndex] : null;

    const buildCumulative = (series: number[]): Array<number | null> => {
      let cumulative = 0;
      return series.map((value, idx) => {
        if (!hasAnchorSelection || idx < anchorIndex) return null;
        cumulative += Number.isFinite(value) ? value : 0;
        return cumulative;
      });
    };

    const l1MainCum = buildCumulative(l1MainNet);
    const l1SuperCum = buildCumulative(l1SuperNet);
    const l2MainCum = buildCumulative(l2MainNet);
    const l2SuperCum = buildCumulative(l2SuperNet);

    const anchorMarkLine = anchorCategory
      ? {
          silent: true,
          symbol: ['none', 'none'],
          lineStyle: { color: '#f59e0b', width: 1, type: 'dashed' },
          label: { show: false },
          data: [{ xAxis: anchorCategory }],
        }
      : undefined;

    const symmetricMin = (value: any) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      return maxAbs === 0 ? -1 : -maxAbs;
    };
    const symmetricMax = (value: any) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      return maxAbs === 0 ? 1 : maxAbs;
    };

    type RowMeta = {
      key: string;
      title: string;
      top: number;
      height: number;
      kind: 'price' | 'abs' | 'net' | 'ratio' | 'cum';
      labelColor: string;
      axisName: string;
    };

    const rowMetas: RowMeta[] = anchorModeEnabled
      ? [
          { key: 'price', title: '股价K线', top: 4, height: 13, kind: 'price', labelColor: REVIEW_COLORS.closeLine, axisName: '价格' },
          { key: 'mainAbs', title: '主力绝对资金 + 活跃度', top: 20, height: 7.5, kind: 'abs', labelColor: '#fca5a5', axisName: '主力资金' },
          { key: 'superAbs', title: '超大绝对资金 + 活跃度', top: 30.5, height: 7.5, kind: 'abs', labelColor: '#c4b5fd', axisName: '超大资金' },
          { key: 'mainNet', title: '主力净流入对比', top: 41, height: 7.5, kind: 'net', labelColor: '#fca5a5', axisName: '主力净流' },
          { key: 'superNet', title: '超大净流入对比', top: 51.5, height: 7.5, kind: 'net', labelColor: '#c4b5fd', axisName: '超大净流' },
          { key: 'netRatio', title: '净流比对比', top: 62, height: 7, kind: 'ratio', labelColor: '#fca5a5', axisName: '净流比' },
          { key: 'l2Cum', title: 'L2锚点累计净流入（主力 + 超大）', top: 72, height: 9, kind: 'cum', labelColor: '#c4b5fd', axisName: 'L2累计' },
          { key: 'l1Cum', title: 'L1锚点累计净流入（主力 + 超大）', top: 84, height: 9, kind: 'cum', labelColor: '#86efac', axisName: 'L1累计' },
        ]
      : [
          { key: 'price', title: '股价K线', top: 4, height: 14, kind: 'price', labelColor: REVIEW_COLORS.closeLine, axisName: '价格' },
          { key: 'mainAbs', title: '主力绝对资金 + 活跃度', top: 21, height: 10, kind: 'abs', labelColor: '#fca5a5', axisName: '主力资金' },
          { key: 'superAbs', title: '超大绝对资金 + 活跃度', top: 34, height: 10, kind: 'abs', labelColor: '#c4b5fd', axisName: '超大资金' },
          { key: 'mainNet', title: '主力净流入对比', top: 47, height: 10, kind: 'net', labelColor: '#fca5a5', axisName: '主力净流' },
          { key: 'superNet', title: '超大净流入对比', top: 60, height: 10, kind: 'net', labelColor: '#c4b5fd', axisName: '超大净流' },
          { key: 'netRatio', title: '净流比对比', top: 73, height: 9, kind: 'ratio', labelColor: '#fca5a5', axisName: '净流比' },
        ];

    const gridIndexMap = Object.fromEntries(rowMetas.map((row, index) => [row.key, index]));

    const xAxis = rowMetas.map((row, index) => ({
      type: 'category',
      data: category,
      boundaryGap: true,
      gridIndex: index,
      min: 'dataMin',
      max: 'dataMax',
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel:
        index === rowMetas.length - 1
          ? { color: '#64748b', fontSize: 10, margin: 10 }
          : { show: false },
    }));

    const yAxis: any[] = [];
    const yIndexMap: Record<string, { primary: number; secondary?: number }> = {};
    rowMetas.forEach((row) => {
      const primaryIndex = yAxis.length;
      if (row.kind === 'price') {
        yAxis.push({
          type: 'value',
          scale: true,
          name: row.axisName,
          nameLocation: 'middle',
          nameGap: 42,
          nameTextStyle: { color: row.labelColor, fontSize: 11 },
          axisLabel: { color: row.labelColor },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
        });
        yIndexMap[row.key] = { primary: primaryIndex };
        return;
      }

      if (row.kind === 'abs') {
        yAxis.push({
          type: 'value',
          scale: true,
          gridIndex: gridIndexMap[row.key],
          name: row.axisName,
          nameLocation: 'middle',
          nameGap: 48,
          nameTextStyle: { color: row.labelColor, fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLabel: { color: row.labelColor, formatter: (v: number) => formatAmountCompact(v) },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
        });
        yAxis.push({
          type: 'value',
          scale: true,
          gridIndex: gridIndexMap[row.key],
          position: 'right',
          show: false,
          min: 0,
        });
        yIndexMap[row.key] = { primary: primaryIndex, secondary: primaryIndex + 1 };
        return;
      }

      yAxis.push({
        type: 'value',
        scale: true,
        gridIndex: gridIndexMap[row.key],
        name: row.axisName,
        nameLocation: 'middle',
        nameGap: 44,
        nameTextStyle: { color: row.labelColor, fontSize: 11 },
        min: row.kind === 'ratio' ? symmetricMin : symmetricMin,
        max: row.kind === 'ratio' ? symmetricMax : symmetricMax,
        axisLabel: {
          color: row.labelColor,
          formatter: (v: number) => (row.kind === 'ratio' ? formatPercentAxis(v) : formatAmountCompact(v)),
        },
        axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      });
      yIndexMap[row.key] = { primary: primaryIndex };
    });

    const series: any[] = [
      {
        name: 'K线',
        type: 'candlestick',
        xAxisIndex: gridIndexMap.price,
        yAxisIndex: yIndexMap.price.primary,
        data: candles,
        itemStyle: {
          color: '#ef4444',
          color0: '#22c55e',
          borderColor: '#ef4444',
          borderColor0: '#22c55e',
        },
        markLine: anchorMarkLine,
      },
      { name: 'L2主力买', type: 'bar', xAxisIndex: gridIndexMap.mainAbs, yAxisIndex: yIndexMap.mainAbs.primary, data: l2MainBuy, itemStyle: { color: REVIEW_COLORS.mainL2Buy }, z: 2, markLine: anchorMarkLine },
      { name: 'L1主力买', type: 'bar', xAxisIndex: gridIndexMap.mainAbs, yAxisIndex: yIndexMap.mainAbs.primary, data: l1MainBuy, itemStyle: { color: REVIEW_COLORS.mainL1Buy }, barGap: '-100%', z: 3 },
      { name: 'L2主力卖', type: 'bar', xAxisIndex: gridIndexMap.mainAbs, yAxisIndex: yIndexMap.mainAbs.primary, data: l2MainSell, itemStyle: { color: REVIEW_COLORS.mainL2Sell }, z: 2 },
      { name: 'L1主力卖', type: 'bar', xAxisIndex: gridIndexMap.mainAbs, yAxisIndex: yIndexMap.mainAbs.primary, data: l1MainSell, itemStyle: { color: REVIEW_COLORS.mainL1Sell }, barGap: '-100%', z: 3 },
      { name: 'L2主力活跃度', type: 'line', xAxisIndex: gridIndexMap.mainAbs, yAxisIndex: yIndexMap.mainAbs.secondary, data: l2MainActivity, showSymbol: false, lineStyle: { color: '#991B1B', width: 1.4 }, itemStyle: { color: '#991B1B' }, z: 5 },
      { name: 'L1主力活跃度', type: 'line', xAxisIndex: gridIndexMap.mainAbs, yAxisIndex: yIndexMap.mainAbs.secondary, data: l1MainActivity, showSymbol: false, lineStyle: { color: '#FCA5A5', width: 1.4 }, itemStyle: { color: '#FCA5A5' }, z: 5 },
      { name: 'L2超大买', type: 'bar', xAxisIndex: gridIndexMap.superAbs, yAxisIndex: yIndexMap.superAbs.primary, data: l2SuperBuy, itemStyle: { color: REVIEW_COLORS.superL2Buy }, z: 2, markLine: anchorMarkLine },
      { name: 'L1超大买', type: 'bar', xAxisIndex: gridIndexMap.superAbs, yAxisIndex: yIndexMap.superAbs.primary, data: l1SuperBuy, itemStyle: { color: REVIEW_COLORS.superL1Buy }, barGap: '-100%', z: 3 },
      { name: 'L2超大卖', type: 'bar', xAxisIndex: gridIndexMap.superAbs, yAxisIndex: yIndexMap.superAbs.primary, data: l2SuperSell, itemStyle: { color: REVIEW_COLORS.superL2Sell }, z: 2 },
      { name: 'L1超大卖', type: 'bar', xAxisIndex: gridIndexMap.superAbs, yAxisIndex: yIndexMap.superAbs.primary, data: l1SuperSell, itemStyle: { color: REVIEW_COLORS.superL1Sell }, barGap: '-100%', z: 3 },
      { name: 'L2超大活跃度', type: 'line', xAxisIndex: gridIndexMap.superAbs, yAxisIndex: yIndexMap.superAbs.secondary, data: l2SuperActivity, showSymbol: false, lineStyle: { color: '#991B1B', width: 1.4 }, itemStyle: { color: '#991B1B' }, z: 5 },
      { name: 'L1超大活跃度', type: 'line', xAxisIndex: gridIndexMap.superAbs, yAxisIndex: yIndexMap.superAbs.secondary, data: l1SuperActivity, showSymbol: false, lineStyle: { color: '#FCA5A5', width: 1.4 }, itemStyle: { color: '#FCA5A5' }, z: 5 },
      {
        name: 'L2主力净',
        type: 'bar',
        xAxisIndex: gridIndexMap.mainNet,
        yAxisIndex: yIndexMap.mainNet.primary,
        data: l2MainNet,
        itemStyle: {
          color: (params: any) =>
            Number(params?.value || 0) >= 0 ? REVIEW_COLORS.mainL2Buy : REVIEW_COLORS.mainL2Sell,
        },
        barWidth: '32%',
        z: 2,
        markLine: anchorMarkLine,
      },
      {
        name: 'L1主力净',
        type: 'bar',
        xAxisIndex: gridIndexMap.mainNet,
        yAxisIndex: yIndexMap.mainNet.primary,
        data: l1MainNet,
        itemStyle: {
          color: (params: any) =>
            Number(params?.value || 0) >= 0 ? REVIEW_COLORS.mainL1Buy : REVIEW_COLORS.mainL1Sell,
        },
        barWidth: '32%',
        z: 3,
      },
      {
        name: 'L2超大净',
        type: 'bar',
        xAxisIndex: gridIndexMap.superNet,
        yAxisIndex: yIndexMap.superNet.primary,
        data: l2SuperNet,
        itemStyle: {
          color: (params: any) =>
            Number(params?.value || 0) >= 0 ? REVIEW_COLORS.superL2Buy : REVIEW_COLORS.superL2Sell,
        },
        barWidth: '32%',
        z: 2,
        markLine: anchorMarkLine,
      },
      {
        name: 'L1超大净',
        type: 'bar',
        xAxisIndex: gridIndexMap.superNet,
        yAxisIndex: yIndexMap.superNet.primary,
        data: l1SuperNet,
        itemStyle: {
          color: (params: any) =>
            Number(params?.value || 0) >= 0 ? REVIEW_COLORS.superL1Buy : REVIEW_COLORS.superL1Sell,
        },
        barWidth: '32%',
        z: 3,
      },
      { name: 'L2净流比', type: 'line', xAxisIndex: gridIndexMap.netRatio, yAxisIndex: yIndexMap.netRatio.primary, data: l2NetRatio, showSymbol: false, lineStyle: { color: '#6D28D9', width: 1.7 }, itemStyle: { color: '#6D28D9' }, z: 4, markLine: anchorMarkLine },
      { name: 'L1净流比', type: 'line', xAxisIndex: gridIndexMap.netRatio, yAxisIndex: yIndexMap.netRatio.primary, data: l1NetRatio, showSymbol: false, lineStyle: { color: '#DC2626', width: 1.6 }, itemStyle: { color: '#DC2626' }, z: 4 },
    ];

    if (anchorModeEnabled) {
      series.push(
        {
          name: 'L2主力累计净',
          type: 'line',
          xAxisIndex: gridIndexMap.l2Cum,
          yAxisIndex: yIndexMap.l2Cum.primary,
          data: l2MainCum,
          showSymbol: false,
          lineStyle: { color: REVIEW_COLORS.mainL2Buy, width: 1.4 },
          itemStyle: { color: REVIEW_COLORS.mainL2Buy },
          areaStyle: { color: 'rgba(211,47,47,0.10)' },
          z: 4,
          markLine: anchorMarkLine,
        },
        {
          name: 'L2超大累计净',
          type: 'line',
          xAxisIndex: gridIndexMap.l2Cum,
          yAxisIndex: yIndexMap.l2Cum.primary,
          data: l2SuperCum,
          showSymbol: false,
          lineStyle: { color: REVIEW_COLORS.superL2Buy, width: 1.3 },
          itemStyle: { color: REVIEW_COLORS.superL2Buy },
          areaStyle: { color: 'rgba(123,31,162,0.08)' },
          z: 4,
        },
        {
          name: 'L1主力累计净',
          type: 'line',
          xAxisIndex: gridIndexMap.l1Cum,
          yAxisIndex: yIndexMap.l1Cum.primary,
          data: l1MainCum,
          showSymbol: false,
          lineStyle: { color: REVIEW_COLORS.mainL1Sell, width: 1.4 },
          itemStyle: { color: REVIEW_COLORS.mainL1Sell },
          areaStyle: { color: 'rgba(129,199,132,0.10)' },
          z: 4,
          markLine: anchorMarkLine,
        },
        {
          name: 'L1超大累计净',
          type: 'line',
          xAxisIndex: gridIndexMap.l1Cum,
          yAxisIndex: yIndexMap.l1Cum.primary,
          data: l1SuperCum,
          showSymbol: false,
          lineStyle: { color: REVIEW_COLORS.superL2Sell, width: 1.3 },
          itemStyle: { color: REVIEW_COLORS.superL2Sell },
          areaStyle: { color: 'rgba(0,121,107,0.08)' },
          z: 4,
        }
      );
    }

    const anchorPromptRows = anchorModeEnabled
      ? rowMetas.filter((row) => row.key === 'l2Cum' || row.key === 'l1Cum')
      : [];

    return {
      animation: false,
      backgroundColor: 'transparent',
      legend: {
        type: 'scroll',
        top: 0,
        textStyle: { color: '#94a3b8', fontSize: 11 },
        data: series.map((item) => item.name),
      },
      title: rowMetas.map((row) => ({
        text: row.title,
        left: '6.2%',
        top: `${Math.max(0, row.top - 2.3)}%`,
        textStyle: { color: row.labelColor, fontSize: 11, fontWeight: 'normal' },
      })),
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: '#334155',
        borderWidth: 1,
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        extraCssText: 'box-shadow: 0 10px 24px rgba(2,6,23,0.45); max-width: 340px; white-space: normal;',
        position: (point: number[], _params: any, _dom: HTMLElement, _rect: any, size: any) => {
          const contentWidth = size?.contentSize?.[0] || 0;
          const contentHeight = size?.contentSize?.[1] || 0;
          const viewWidth = size?.viewSize?.[0] || 0;
          const viewHeight = size?.viewSize?.[1] || 0;
          let x = (point?.[0] || 0) + 18;
          if (x + contentWidth > viewWidth - 12) {
            x = (point?.[0] || 0) - contentWidth - 18;
          }
          x = Math.max(12, Math.min(x, viewWidth - contentWidth - 12));
          let y = (point?.[1] || 0) - contentHeight / 2;
          y = Math.max(12, Math.min(y, viewHeight - contentHeight - 12));
          return [x, y];
        },
        axisPointer: { type: 'line' },
        formatter: (params: any) => {
          const items = Array.isArray(params) ? params : [params];
          if (!items.length) return '';
          const idx = Number(items[0]?.dataIndex ?? 0);
          const axisLabel = items[0]?.axisValueLabel || items[0]?.name || '--';
          const row = data[idx];
          if (!row) return `${axisLabel}`;

          const marker = (color: string) =>
            `<span style="display:inline-block;margin-right:6px;border-radius:50%;width:8px;height:8px;background:${color};"></span>`;
          const section = (title: string, lines: string[]) =>
            [`<div style="margin-top:6px;color:#cbd5e1;font-weight:600;">${title}</div>`, ...lines].join('<br/>');

          const blocks: string[] = [
            `<div style="font-weight:700;color:#f8fafc;">${axisLabel}</div>`,
            section('股价K线', [
              `${marker('#fbbf24')}开 ${row.open.toFixed(2)} / 高 ${row.high.toFixed(2)} / 低 ${row.low.toFixed(2)} / 收 ${row.close.toFixed(2)}`,
              `${marker('#94a3b8')}成交额: ${formatAmountCompact(resolvedTotalAmount[idx])}`,
            ]),
            section('主力', [
              `${marker('#6D28D9')}L2净: ${formatAmountCompact(row.l2_main_net)} ｜ 活跃度 ${formatPercentValue(l2MainActivity[idx] ?? NaN)}`,
              `${marker('#DC2626')}L1净: ${formatAmountCompact(row.l1_main_net)} ｜ 活跃度 ${formatPercentValue(l1MainActivity[idx] ?? NaN)}`,
            ]),
            section('超大单', [
              `${marker('#F59E0B')}L2净: ${formatAmountCompact(row.l2_super_net)} ｜ 活跃度 ${formatPercentValue(l2SuperActivity[idx] ?? NaN)}`,
              `${marker('#10B981')}L1净: ${formatAmountCompact(row.l1_super_net)} ｜ 活跃度 ${formatPercentValue(l1SuperActivity[idx] ?? NaN)}`,
            ]),
            section('净流比', [
              `${marker('#6D28D9')}L2净流比: ${formatPercentValue(l2NetRatio[idx] ?? NaN)}`,
              `${marker('#DC2626')}L1净流比: ${formatPercentValue(l1NetRatio[idx] ?? NaN)}`,
            ]),
          ];

          if (anchorModeEnabled) {
            blocks.push(
              section('锚点累计', [
                `${marker('#6D28D9')}L2主力/超大: ${l2MainCum[idx] === null ? '--' : formatAmountCompact(l2MainCum[idx] ?? NaN)} / ${l2SuperCum[idx] === null ? '--' : formatAmountCompact(l2SuperCum[idx] ?? NaN)}`,
                `${marker('#DC2626')}L1主力/超大: ${l1MainCum[idx] === null ? '--' : formatAmountCompact(l1MainCum[idx] ?? NaN)} / ${l1SuperCum[idx] === null ? '--' : formatAmountCompact(l1SuperCum[idx] ?? NaN)}`,
              ])
            );
          }

          return blocks.join('<br/>');
        },
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: rowMetas.map((row) => ({ left: '6%', right: '4%', top: `${row.top}%`, height: `${row.height}%` })),
      xAxis,
      yAxis,
      dataZoom: [
        {
          type: 'slider',
          xAxisIndex: rowMetas.map((_, index) => index),
          start: zoomRange[0],
          end: zoomRange[1],
          realtime: true,
          bottom: '1.4%',
          height: 16,
          showDetail: false,
          brushSelect: false,
          zoomLock: false,
          filterMode: 'filter',
          handleSize: '105%',
        },
      ],
      series,
      graphic:
        anchorModeEnabled && !hasAnchorSelection
          ? anchorPromptRows.map((row) => ({
              type: 'text',
              left: '50%',
              top: `${row.top + row.height / 2 - 1.5}%`,
              z: 100,
              style: {
                text: '点击K线设置锚点',
                fill: '#64748b',
                font: '12px sans-serif',
                textAlign: 'center',
              },
            }))
          : [],
    };
  }, [viewState, zoomRange, anchorModeEnabled, anchorTs]);

  const rangeTriggerText = startDateInput && endDateInput ? `${startDateInput} ~ ${endDateInput}` : '选择日期区间';
  const queryDisabled =
    loading ||
    !startDateInput ||
    !endDateInput ||
    endDateInput < startDateInput ||
    (isSearchDirty && !normalizeSymbolText(searchQuery) && searchResults.length === 0) ||
    (!isSearchDirty && !symbolInput);
  const chartHeight = '108vh';
  const shouldShowQuoteCard = Boolean(selectedQuote || latestDailySummary);
  const homeHref = symbolInput ? `/?symbol=${symbolInput.toLowerCase()}` : '/';

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200 font-sans selection:bg-blue-900 pb-16 overflow-x-hidden">
      <MarketTopHeader
        routeHref={homeHref}
        routeLabel="回到首页"
        routeTitle="返回首页"
        searchValue={searchQuery}
        isSearchFocused={isSearchFocused}
        searchResults={searchDropdownVisible ? searchResults : []}
        searchHistory={searchHistory}
        searchContainerRef={searchRef}
        onSearchChange={(value) => {
          setSearchQuery(value);
          setIsSearchDirty(true);
          setIsSearchFocused(true);
        }}
        onSearchFocus={() => setIsSearchFocused(true)}
        onSearchBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
        onSearchKeyDown={async (e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          if (searchResults.length > 0) {
            await handleSelectSearchResult(searchResults[0]);
            return;
          }
          await handleExecuteQuery();
        }}
        onClearSearch={() => {
          setSearchQuery('');
          setIsSearchDirty(true);
          setSearchResults([]);
        }}
        onSelectSearchResult={handleSelectSearchResult}
        onSelectHistory={handleSelectSearchResult}
        rightSlot={<ThresholdConfig onConfigUpdate={() => {}} />}
      />

      <main className="max-w-[1600px] mx-auto p-2 md:p-6 space-y-4">
        {shouldShowQuoteCard && (
          <StockQuoteHeroCard
            name={selectedDisplayName}
            symbol={symbolInput.toUpperCase()}
            price={selectedQuote?.price ?? latestDailySummary?.latest.close ?? 0}
            previousClose={selectedQuote?.lastClose ?? latestDailySummary?.previousClose ?? latestDailySummary?.latest.open ?? 0}
            open={selectedQuote?.open ?? latestDailySummary?.latest.open ?? 0}
            high={selectedQuote?.high ?? latestDailySummary?.latest.high ?? 0}
            low={selectedQuote?.low ?? latestDailySummary?.latest.low ?? 0}
            volume={selectedQuote?.volume}
            amount={selectedQuote?.amount ?? latestDailySummary?.latest.total_amount}
            turnoverRate={turnoverRate}
            latestLabel={!isCurrentCnTradingSession() ? (selectedQuote?.date ? `最新 ${selectedQuote.date}` : latestDailySummary ? `最新 ${latestDailySummary.latest.source_date}` : undefined) : undefined}
            marketCapLabel={formatMarketCapYi(selectedInputPoolItem?.market_cap) ?? '--'}
            metaRow={
              <QuoteMetaRow
                isWatchlisted={isWatchlisted}
                onToggleWatchlist={toggleWatchlist}
                backendStatus={backendStatus}
              />
            }
          />
        )}

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-3">
          <div className="flex flex-col xl:flex-row xl:flex-wrap xl:items-center gap-2.5">
            <div ref={rangePickerRef} className="relative min-w-[220px] xl:w-[280px] xl:flex-none">
              <button
                onClick={openRangePicker}
                className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-left text-sm text-slate-100 hover:border-slate-600"
              >
                <span className="inline-flex items-center gap-2 min-w-0">
                  <Calendar className="h-4 w-4 text-slate-500 shrink-0" />
                  <span className="truncate">{rangeTriggerText}</span>
                </span>
              </button>
              {isRangePickerOpen && (
                <div className="absolute right-0 z-30 mt-2 w-[320px] max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700 bg-slate-950/95 p-3 shadow-2xl backdrop-blur">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <label className="flex flex-col gap-1 text-xs text-slate-400">
                      <span>开始日期</span>
                      <input
                        type="date"
                        min={selectedInputPoolItem?.min_date || ''}
                        max={selectedInputPoolItem?.max_date || ''}
                        value={draftStartDate}
                        onChange={(e) => {
                          setDraftStartDate(e.target.value);
                          setActiveRangeShortcut('all');
                        }}
                        className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-xs text-slate-400">
                      <span>结束日期</span>
                      <input
                        type="date"
                        min={selectedInputPoolItem?.min_date || ''}
                        max={selectedInputPoolItem?.max_date || ''}
                        value={draftEndDate}
                        onChange={(e) => {
                          setDraftEndDate(e.target.value);
                          setActiveRangeShortcut('all');
                        }}
                        className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                      />
                    </label>
                  </div>
                  <div className="mt-3 text-[11px] text-slate-500">默认粒度会按区间自动落档，60天 / 90天 默认优先 1d。</div>
                  <div className="mt-3 flex items-center justify-end gap-2">
                    <button
                      onClick={() => {
                        setDraftStartDate(startDateInput);
                        setDraftEndDate(endDateInput);
                        setIsRangePickerOpen(false);
                      }}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-300"
                    >
                      取消
                    </button>
                    <button
                      onClick={handleConfirmRange}
                      className="rounded-lg border border-cyan-500 bg-cyan-700/30 px-3 py-1.5 text-sm text-cyan-200"
                    >
                      确认
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-1 xl:flex-none">
              {RANGE_SHORTCUT_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  onClick={async () => handleQuickRangeShortcut(option.key)}
                  className={`rounded-md border px-1.5 py-1 text-[11px] leading-none ${
                    activeRangeShortcut === option.key
                      ? 'border-cyan-500 bg-cyan-700/30 text-cyan-200'
                      : 'border-slate-700 bg-slate-950 text-slate-300'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-1 xl:flex-1">
              {GRANULARITY_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  onClick={() => setGranularityMode(option.key)}
                  className={`rounded-md border px-1.5 py-1 text-[11px] leading-none ${
                    granularityMode === option.key
                      ? 'border-violet-500 bg-violet-700/30 text-violet-200'
                      : 'border-slate-700 bg-slate-950 text-slate-300'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-1">
              <button
                onClick={() => setAnchorModeEnabled((prev) => !prev)}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] leading-none ${
                  anchorModeEnabled
                    ? 'border-amber-500 bg-amber-700/30 text-amber-200'
                    : 'border-slate-700 bg-slate-950 text-slate-300'
                }`}
              >
                <Target className="h-3.5 w-3.5" />
                {anchorModeEnabled ? '锚点累计开' : '锚点累计关'}
              </button>
              <button
                onClick={() => setAnchorTs(null)}
                disabled={anchorTs === null}
                className={`rounded-md border px-2 py-1 text-[11px] leading-none ${
                  anchorTs === null
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900 text-slate-600'
                    : 'border-slate-700 bg-slate-950 text-slate-300'
                }`}
              >
                清除锚点
              </button>
              <button
                onClick={handleExecuteQuery}
                disabled={queryDisabled}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] leading-none ${
                  queryDisabled
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900 text-slate-600'
                    : 'border-cyan-500 bg-cyan-700/30 text-cyan-200 hover:bg-cyan-700/40'
                }`}
              >
                {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : null}
                执行查询
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}

        {!error && emptyMessage && (
          <div className="bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300">
            {emptyMessage}
          </div>
        )}

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-2">
          {!error && viewState.bars.length > 0 ? (
            <ReactEChartsCore
              echarts={echarts}
              option={option}
              style={{ width: '100%', height: chartHeight }}
              onEvents={{ datazoom: handleDataZoom, click: handleChartClick }}
            />
          ) : (
            <div className="h-[58vh] flex items-center justify-center text-slate-500 text-sm">
              {error || emptyMessage || '暂无可视化数据。'}
            </div>
          )}
        </div>

        {!error && correlationData.points.length > 0 && (
          <>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 md:p-4">
              <div className="text-sm text-slate-200 mb-3">相关性统计结论（5分钟口径，活跃阈值30%）</div>
              {correlationStats.concurrentCount === 0 && (
                <div className="text-xs text-amber-300 mb-3">
                  当前样本不足。请先重跑含 total_amount 的 sandbox ETL（1-2月真实逐笔），再查看相关性统计。
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="text-slate-400 mb-1">同期解释力（净流入 vs 当期涨跌幅）</div>
                  <div className="text-slate-100">L1: {correlationStats.l1Concurrent?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-100">L2: {correlationStats.l2Concurrent?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-500 mt-1">样本: {correlationStats.concurrentCount}</div>
                </div>
                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="text-slate-400 mb-1">未来预测力（净流入 vs 下一根涨跌幅）</div>
                  <div className="text-slate-100">L1: {correlationStats.l1Lead?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-100">L2: {correlationStats.l2Lead?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-500 mt-1">样本: {correlationStats.leadCount}</div>
                </div>
                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="text-slate-400 mb-1">高活跃过滤（L2活跃度&gt;30%）</div>
                  <div className="text-slate-100">相关系数: {correlationStats.l2Conditional?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-500 mt-1">
                    样本: {correlationStats.highActivityCount} / {correlationStats.leadCount} ({correlationStats.highActivityRatio.toFixed(1)}%)
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <ReactEChartsCore echarts={echarts} option={scatterOptionL1} style={{ width: '100%', height: '320px' }} />
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <ReactEChartsCore echarts={echarts} option={scatterOptionL2} style={{ width: '100%', height: '320px' }} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
};

export default SandboxReviewPage;
