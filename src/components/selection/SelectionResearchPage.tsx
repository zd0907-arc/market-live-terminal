import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, BarChart3, Calendar, ChevronLeft, ChevronRight, RefreshCw, ShieldCheck, TrendingUp } from 'lucide-react';

import {
  SelectionBacktestDetail,
  SelectionBacktestRunItem,
  SelectionCandidateItem,
  SelectionHealthData,
  SelectionProfileData,
  SelectionStrategy,
  SelectionTradeDateItem,
} from '../../types';
import {
  fetchSelectionBacktestDetail,
  fetchSelectionBacktests,
  fetchSelectionCandidates,
  fetchSelectionHealth,
  fetchSelectionProfile,
  fetchSelectionTradeDates,
  refreshSelectionResearch,
  runSelectionBacktest,
} from '../../services/selectionService';
import * as StockService from '../../services/stockService';
import QuoteMetaRow from '../common/QuoteMetaRow';
import StockQuoteHeroCard from '../common/StockQuoteHeroCard';
import SelectionDecisionPanel from './SelectionDecisionPanel';
import { APP_VERSION } from '../../version';

const STRATEGY_OPTIONS: Array<{ value: Extract<SelectionStrategy, 'breakout' | 'stealth'>; label: string }> = [
  { value: 'breakout', label: '启动确认 Top10' },
  { value: 'stealth', label: '吸筹前置 Top10' },
];

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));

const pad2 = (value: number) => String(value).padStart(2, '0');
const parseDateOnly = (value?: string | null): Date | null => {
  if (!value) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day, 0, 0, 0, 0);
};
const formatDateOnly = (value: Date) => `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
const monthLabel = (value: Date) => `${value.getFullYear()}年${pad2(value.getMonth() + 1)}月`;
const isDateWithin = (value: string, minDate?: string, maxDate?: string) => {
  if (minDate && value < minDate) return false;
  if (maxDate && value > maxDate) return false;
  return true;
};

const fmtMarketCap = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value)) || Number(value) <= 0) return '--';
  return `${(Number(value) / 1e8).toFixed(2)}亿`;
};

const scoreTone = (score: number) => {
  if (score >= 75) return 'text-red-300';
  if (score >= 65) return 'text-amber-300';
  return 'text-slate-300';
};

const SectionCard: React.FC<{ title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }> = ({ title, icon, right, children }) => (
  <section className="rounded-2xl border border-slate-800 bg-slate-900/70 shadow-lg">
    <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-white">
        {icon}
        <span>{title}</span>
      </div>
      {right}
    </div>
    <div className="p-4">{children}</div>
  </section>
);

const Metric: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone = 'text-slate-100' }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const TradeDatePicker: React.FC<{
  value: string;
  minDate?: string;
  maxDate?: string;
  latestDate?: string;
  dateMetaByDate?: Record<string, SelectionTradeDateItem>;
  onChange: (value: string) => void;
}> = ({ value, minDate, maxDate, latestDate, dateMetaByDate = {}, onChange }) => {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState<Date>(() => parseDateOnly(value || latestDate || maxDate) || new Date());
  const pickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const next = parseDateOnly(value || latestDate || maxDate);
    if (next) setViewMonth(new Date(next.getFullYear(), next.getMonth(), 1));
  }, [value, latestDate, maxDate]);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (pickerRef.current && target && !pickerRef.current.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [open]);

  const monthStart = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);
  const firstWeekday = monthStart.getDay();
  const daysInMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0).getDate();
  const cells = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, index) => index + 1),
  ];

  const shiftMonth = (offset: number) => {
    setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + offset, 1));
  };

  const pickDate = (day: number) => {
    const dateText = formatDateOnly(new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day));
    const meta = dateMetaByDate[dateText];
    if (!isDateWithin(dateText, minDate, maxDate) || meta?.selectable === false) return;
    onChange(dateText);
    setOpen(false);
  };

  const jumpLatest = () => {
    const target = latestDate || maxDate;
    if (!target) return;
    onChange(target);
    setViewMonth(parseDateOnly(target) || new Date());
    setOpen(false);
  };

  return (
    <div ref={pickerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex h-9 min-w-[150px] items-center justify-between gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 outline-none hover:border-slate-500"
        aria-label="选择交易日"
      >
        <span className="inline-flex min-w-0 items-center gap-2">
          <Calendar className="h-4 w-4 shrink-0 text-slate-500" />
          <span className="truncate">{value || '选择交易日'}</span>
        </span>
      </button>
      {open ? (
        <div className="absolute left-0 z-[100] mt-2 w-[284px] rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-2xl">
          <div className="mb-3 flex items-center justify-between">
            <button
              type="button"
              onClick={() => shiftMonth(-1)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-800"
              aria-label="上个月"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="text-sm font-semibold text-white">{monthLabel(viewMonth)}</div>
            <button
              type="button"
              onClick={() => shiftMonth(1)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-800"
              aria-label="下个月"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-[11px] text-slate-500">
            {['日', '一', '二', '三', '四', '五', '六'].map((day) => <div key={day} className="py-1">{day}</div>)}
            {cells.map((day, index) => {
              if (!day) return <div key={`blank-${index}`} className="h-8" />;
              const dateText = formatDateOnly(new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day));
              const meta = dateMetaByDate[dateText];
              const disabled = !isDateWithin(dateText, minDate, maxDate) || meta?.selectable === false;
              const isClosed = meta?.is_trade_day === false;
              const noScoreData = meta?.is_trade_day === true && meta?.selectable === false;
              const active = value === dateText;
              return (
                <button
                  key={dateText}
                  type="button"
                  onClick={() => pickDate(day)}
                  disabled={disabled}
                  title={meta?.disabled_reason || (meta?.signal_count ? `${meta.signal_count} 个候选信号` : undefined)}
                  className={`relative h-8 rounded-lg text-xs font-medium transition-colors ${
                    active
                      ? 'bg-sky-600 text-white'
                      : disabled && isClosed
                        ? 'cursor-not-allowed text-slate-700 line-through'
                        : disabled && noScoreData
                          ? 'cursor-not-allowed text-slate-600'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  {day}
                  {!disabled && meta?.signal_count ? <span className="absolute bottom-0.5 left-1/2 h-0.5 w-3 -translate-x-1/2 rounded-full bg-emerald-400/80" /> : null}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3 text-[11px]">
            <span className="text-slate-500">亮点=有评分数据，灰色/删除线=不可选</span>
            <button type="button" onClick={jumpLatest} className="rounded-lg border border-slate-700 px-2 py-1 text-slate-200 hover:bg-slate-800">
              最新
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};

const SelectionResearchPage: React.FC = () => {
  const [health, setHealth] = useState<SelectionHealthData | null>(null);
  const [activeStrategy, setActiveStrategy] = useState<Extract<SelectionStrategy, 'breakout' | 'stealth'>>('breakout');
  const [tradeDate, setTradeDate] = useState('');
  const [pendingTradeDate, setPendingTradeDate] = useState('');
  const [candidates, setCandidates] = useState<SelectionCandidateItem[]>([]);
  const [selected, setSelected] = useState<SelectionCandidateItem | null>(null);
  const [profile, setProfile] = useState<SelectionProfileData | null>(null);
  const [quote, setQuote] = useState<any | null>(null);
  const [turnoverRate, setTurnoverRate] = useState<number | null>(null);
  const [backendStatus, setBackendStatus] = useState(false);
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [backtestRuns, setBacktestRuns] = useState<SelectionBacktestRunItem[]>([]);
  const [backtestDetail, setBacktestDetail] = useState<SelectionBacktestDetail | null>(null);
  const [nameOverrides, setNameOverrides] = useState<Record<string, string>>({});
  const [tradeDateMetaByDate, setTradeDateMetaByDate] = useState<Record<string, SelectionTradeDateItem>>({});
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [backtestStartDate, setBacktestStartDate] = useState('2025-10-01');
  const [backtestEndDate, setBacktestEndDate] = useState('2026-02-27');
  const [error, setError] = useState('');

  const hydrateCandidateNames = async (items: SelectionCandidateItem[]) => {
    const targets = items.filter((item) => !item.name || item.name === item.symbol);
    if (!targets.length) return;
    const results = await Promise.allSettled(targets.map((item) => StockService.fetchQuote(item.symbol.toLowerCase())));
    const next: Record<string, string> = {};
    results.forEach((result, index) => {
      const symbol = targets[index]?.symbol;
      if (!symbol || result.status !== 'fulfilled') return;
      const name = String(result.value?.name || '').trim();
      if (name) next[symbol.toLowerCase()] = name;
    });
    if (Object.keys(next).length > 0) {
      setNameOverrides((prev) => ({ ...prev, ...next }));
    }
  };

  const loadHealth = async () => {
    const data = await fetchSelectionHealth();
    setHealth(data);
    if (data?.latest_signal_date && !tradeDate) {
      setTradeDate(data.latest_signal_date);
      setPendingTradeDate(data.latest_signal_date);
    }
  };

  const loadCandidates = async (dateArg = tradeDate) => {
    setLoadingCandidates(true);
    setError('');
    try {
      const data = await fetchSelectionCandidates(dateArg || undefined, activeStrategy, 10);
      const items = data?.items || [];
      setCandidates(items);
      await hydrateCandidateNames(items);
      const nextDate = data?.trade_date || dateArg;
      if (nextDate) setTradeDate(nextDate);
      const keepSelected = items.find((item) => item.symbol === selected?.symbol) || items[0] || null;
      setSelected(keepSelected);
    } catch (e) {
      setError('候选加载失败');
    } finally {
      setLoadingCandidates(false);
    }
  };

  const loadBacktests = async () => {
    const items = await fetchSelectionBacktests();
    const runs = items as SelectionBacktestRunItem[];
    setBacktestRuns(runs);
    if (runs.length > 0 && !backtestDetail) {
      const detail = await fetchSelectionBacktestDetail(runs[0].id);
      setBacktestDetail(detail);
    }
  };

  useEffect(() => {
    loadHealth();
    loadBacktests();
  }, []);

  useEffect(() => {
    if (!tradeDate) return;
    loadCandidates(tradeDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradeDate, activeStrategy]);

  const handleApplyTradeDate = async () => {
    if (!pendingTradeDate) return;
    if (pendingTradeDate === tradeDate) {
      await loadCandidates(pendingTradeDate);
      return;
    }
    setTradeDate(pendingTradeDate);
  };

  useEffect(() => {
    if (!selected) {
      setProfile(null);
      return;
    }
    let cancelled = false;
    setLoadingProfile(true);
    fetchSelectionProfile(selected.symbol, tradeDate || undefined)
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .finally(() => {
        if (!cancelled) setLoadingProfile(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, tradeDate]);

  useEffect(() => {
    if (!selected) {
      setQuote(null);
      setTurnoverRate(null);
      setIsWatchlisted(false);
      return;
    }
    const symbol = selected.symbol.toLowerCase();
    let cancelled = false;
    StockService.fetchQuote(symbol).then((res) => {
      if (!cancelled) setQuote(res);
    }).catch(() => {
      if (!cancelled) setQuote(null);
    });
    StockService.fetchSentimentData(symbol).then((data) => {
      if (!cancelled) {
        const value = Number(data?.turnover_rate);
        setTurnoverRate(Number.isFinite(value) ? value : null);
      }
    }).catch(() => {
      if (!cancelled) setTurnoverRate(null);
    });
    StockService.getWatchlist().then((items) => {
      if (!cancelled) setIsWatchlisted(Boolean(items.find((item) => item.symbol === symbol)));
    }).catch(() => {
      if (!cancelled) setIsWatchlisted(false);
    });
    StockService.checkBackendHealth().then((ok) => {
      if (!cancelled) setBackendStatus(ok);
    }).catch(() => {
      if (!cancelled) setBackendStatus(false);
    });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const handleToggleWatchlist = async () => {
    if (!selected) return;
    const symbol = selected.symbol.toLowerCase();
    const resolvedName = (selectedDisplayName || selected.name || symbol).trim();
    if (isWatchlisted) {
      await StockService.removeFromWatchlist(symbol);
      setIsWatchlisted(false);
      return;
    }
    await StockService.addToWatchlist(symbol, resolvedName);
    setIsWatchlisted(true);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError('');
    try {
      await refreshSelectionResearch(undefined, tradeDate || undefined);
      await loadHealth();
      await loadCandidates(tradeDate);
      await loadBacktests();
    } catch (e) {
      setError('刷新失败，请检查写权限或后端日志');
    } finally {
      setRefreshing(false);
    }
  };

  const handleRunBacktest = async () => {
    setRunningBacktest(true);
    setError('');
    try {
      const detail = await runSelectionBacktest({
        strategy_name: activeStrategy,
        start_date: backtestStartDate,
        end_date: backtestEndDate,
        holding_days_set: [5, 10, 20, 40],
        max_positions_per_day: 10,
      });
      setBacktestDetail(detail);
      await loadBacktests();
    } catch (e) {
      setError('回测执行失败，请检查写权限或后端日志');
    } finally {
      setRunningBacktest(false);
    }
  };

  const displayCandidates = useMemo(
    () => candidates.map((item) => ({ ...item, displayName: nameOverrides[item.symbol.toLowerCase()] || item.name || item.symbol })),
    [candidates, nameOverrides]
  );

  const selectedDisplayName = selected ? (nameOverrides[selected.symbol.toLowerCase()] || profile?.name || selected.name || selected.symbol) : '';
  const heroPrice = Number(quote?.price ?? profile?.close ?? selected?.close ?? 0);
  const previousClose = Number(quote?.lastClose ?? profile?.prev_close ?? profile?.close ?? selected?.close ?? 0);
  const open = Number(quote?.open ?? profile?.close ?? selected?.close ?? 0);
  const high = Number(quote?.high ?? profile?.close ?? selected?.close ?? 0);
  const low = Number(quote?.low ?? profile?.close ?? selected?.close ?? 0);
  const heroName = (quote?.name || selectedDisplayName || profile?.name || selected?.name || selected?.symbol || '').trim();
  const datePickerMin = String(health?.source_snapshot?.history_bounds?.min_date || health?.source_snapshot?.atomic_bounds?.min_date || '2025-01-01');
  const datePickerMax = String(health?.latest_signal_date || health?.source_snapshot?.history_bounds?.max_date || health?.source_snapshot?.atomic_bounds?.max_date || '');

  useEffect(() => {
    if (!datePickerMin || !datePickerMax) return;
    let cancelled = false;
    fetchSelectionTradeDates(datePickerMin, datePickerMax, activeStrategy)
      .then((data) => {
        if (cancelled) return;
        const next: Record<string, SelectionTradeDateItem> = {};
        (data?.items || []).forEach((item) => {
          next[item.date] = item;
        });
        setTradeDateMetaByDate(next);
      })
      .catch(() => {
        if (!cancelled) setTradeDateMetaByDate({});
      });
    return () => {
      cancelled = true;
    };
  }, [activeStrategy, datePickerMax, datePickerMin]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a
            href="/"
            className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回主页面
          </a>
          <div className="mr-2 text-base font-bold text-white">选股研究工作台</div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
            v{APP_VERSION}
          </span>
          <select
            value={activeStrategy}
            onChange={(e) => setActiveStrategy(e.target.value as Extract<SelectionStrategy, 'breakout' | 'stealth'>)}
            className="h-9 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 outline-none hover:border-slate-500"
            aria-label="选择策略"
          >
            {STRATEGY_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
          <TradeDatePicker
            value={pendingTradeDate}
            minDate={datePickerMin}
            maxDate={datePickerMax}
            latestDate={health?.latest_signal_date || undefined}
            dateMetaByDate={tradeDateMetaByDate}
            onChange={setPendingTradeDate}
          />
          <button
            type="button"
            onClick={handleApplyTradeDate}
            disabled={!pendingTradeDate || loadingCandidates}
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ShieldCheck className={`h-4 w-4 ${loadingCandidates ? 'animate-pulse' : ''}`} />
            {loadingCandidates ? '查询中' : '查询候选'}
          </button>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        {error && <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}

        {selected && profile ? (
          <StockQuoteHeroCard
            name={heroName}
            symbol={selected.symbol.toUpperCase()}
            price={heroPrice}
            previousClose={previousClose}
            open={open}
            high={high}
            low={low}
            volume={quote?.volume}
            amount={quote?.amount}
            turnoverRate={turnoverRate}
            latestLabel={`最新 ${selected.trade_date}`}
            marketCapLabel={fmtMarketCap(profile.market_cap)}
            metaRow={
              <QuoteMetaRow
                isWatchlisted={isWatchlisted}
                onToggleWatchlist={handleToggleWatchlist}
                backendStatus={backendStatus}
              />
            }
          />
        ) : null}

        <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70">
            <div className="flex items-start justify-between gap-3 border-b border-slate-800 px-4 py-4">
              <div>
                <div className="flex items-center gap-2 text-lg font-bold text-white">
                  <TrendingUp className="h-5 w-5 text-amber-400" />
                  当日 Top10 候选
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  当前日期：{tradeDate || pendingTradeDate || health?.latest_signal_date || '--'}
                </div>
              </div>
              {loadingCandidates ? <span className="text-xs text-slate-500">加载中...</span> : null}
            </div>
            <div className="divide-y divide-slate-800/80">
              {displayCandidates.map((item) => (
                <button
                  key={`${item.symbol}-${item.trade_date}`}
                  type="button"
                  onClick={() => setSelected(item)}
                  className={`w-full px-4 py-3 text-left transition ${selected?.symbol === item.symbol ? 'bg-sky-500/10' : 'hover:bg-slate-950/35'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-slate-500">#{item.rank || '--'}</span>
                        <span className="truncate text-sm font-semibold text-white">{item.displayName}</span>
                        <span className="shrink-0 text-[11px] text-slate-500">{item.symbol}</span>
                      </div>
                    </div>
                    <div className="grid min-w-[128px] shrink-0 grid-cols-3 gap-1 text-right text-[10px]">
                      <div>
                        <div className={`text-sm font-semibold ${scoreTone(item.breakout_score)}`}>{fmtNum(item.breakout_score)}</div>
                        <div className="text-slate-500">确认</div>
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-violet-200">{fmtNum(item.stealth_score)}</div>
                        <div className="text-slate-500">吸筹</div>
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-amber-200">{fmtNum(item.distribution_score)}</div>
                        <div className="text-slate-500">出货</div>
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">
                    {item.reason_summary || '当前未生成解释'}
                  </div>
                </button>
              ))}
              {!loadingCandidates && displayCandidates.length === 0 && (
                <div className="px-4 py-10 text-center text-sm text-slate-500">暂无候选，请先刷新数据或切换日期。</div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-2">
            {loadingProfile ? (
              <div className="py-16 text-center text-sm text-slate-500">右侧复盘视图加载中...</div>
            ) : (
              <SelectionDecisionPanel
                candidate={selected}
                profile={profile}
                displayName={selectedDisplayName}
                backendStatus={backendStatus}
              />
            )}
          </div>
        </div>

        <details className="rounded-2xl border border-slate-800 bg-slate-900/70">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-white">
            <span className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-emerald-400" />
              策略验证 / 回测
            </span>
            <span className="text-xs font-normal text-slate-500">默认收起，不影响日常选股</span>
          </summary>
          <div className="space-y-4 border-t border-slate-800 px-4 py-4">
            <div className="grid gap-3 md:grid-cols-[180px_180px_auto_auto] md:items-end">
              <label className="text-xs text-slate-400">
                开始日期
                <input type="date" value={backtestStartDate} onChange={(e) => setBacktestStartDate(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
              </label>
              <label className="text-xs text-slate-400">
                结束日期
                <input type="date" value={backtestEndDate} onChange={(e) => setBacktestEndDate(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
              </label>
              <button
                type="button"
                onClick={handleRunBacktest}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500"
              >
                <RefreshCw className={`h-4 w-4 ${runningBacktest ? 'animate-spin' : ''}`} />
                运行回测
              </button>
              <div className="text-xs text-slate-500">看固定持有收益，也看窗口内最高机会。</div>
            </div>

            <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
              <div className="space-y-2">
                {backtestRuns.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={async () => setBacktestDetail(await fetchSelectionBacktestDetail(run.id))}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-3 text-left hover:border-slate-600"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-white">#{run.id} · {run.strategy_name}</div>
                      <span className="text-[11px] text-slate-500">{run.status}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">{run.start_date} ~ {run.end_date}</div>
                    <div className="mt-1 text-[11px] text-slate-500">{run.holding_days_set}</div>
                  </button>
                ))}
              </div>
              <div>
                {backtestDetail ? (
                  <div className="space-y-3">
                    <div>
                      <div className="text-sm font-semibold text-white">Run #{backtestDetail.run.id}</div>
                      <div className="text-xs text-slate-500">{backtestDetail.run.strategy_name} · {backtestDetail.run.start_date} ~ {backtestDetail.run.end_date}</div>
                    </div>
                    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2">
                      <table className="min-w-full text-xs">
                        <thead className="text-left text-slate-500">
                          <tr>
                            <th className="pb-2 pr-3">持有</th>
                            <th className="pb-2 pr-3">交易数</th>
                            <th className="pb-2 pr-3">固定胜率</th>
                            <th className="pb-2 pr-3">固定均值</th>
                            <th className="pb-2 pr-3">窗口正收益率</th>
                            <th className="pb-2 pr-3">平均最高涨幅</th>
                            <th className="pb-2 pr-3">最大回撤</th>
                          </tr>
                        </thead>
                        <tbody>
                          {backtestDetail.summaries.map((item) => (
                            <tr key={item.id} className="border-t border-slate-800/70">
                              <td className="py-1.5 pr-3">{item.holding_days}D</td>
                              <td className="py-1.5 pr-3">{item.trade_count}</td>
                              <td className="py-1.5 pr-3">{fmtPct(item.win_rate)}</td>
                              <td className="py-1.5 pr-3">{fmtPct(item.avg_return_pct)}</td>
                              <td className="py-1.5 pr-3">{fmtPct(item.opportunity_win_rate)}</td>
                              <td className="py-1.5 pr-3">{fmtPct(item.avg_max_runup_pct)}</td>
                              <td className="py-1.5 pr-3">{fmtPct(item.max_drawdown_pct)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="max-h-64 overflow-auto rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2">
                      <div className="mb-2 text-xs font-semibold text-slate-400">样本交易（前 40 条）</div>
                      <table className="min-w-full text-xs">
                        <thead className="text-left text-slate-500">
                          <tr>
                            <th className="pb-2 pr-3">股票</th>
                            <th className="pb-2 pr-3">信号</th>
                            <th className="pb-2 pr-3">固定收益</th>
                            <th className="pb-2 pr-3">窗口最高涨幅</th>
                            <th className="pb-2 pr-3">最大回撤</th>
                          </tr>
                        </thead>
                        <tbody>
                          {backtestDetail.trades.slice(0, 40).map((trade) => (
                            <tr key={trade.id} className="border-t border-slate-800/70">
                              <td className="py-1.5 pr-3">{trade.symbol}</td>
                              <td className="py-1.5 pr-3">{trade.signal_date}</td>
                              <td className="py-1.5 pr-3">{fmtPct(trade.fixed_exit_return_pct ?? trade.return_pct)}</td>
                              <td className="py-1.5 pr-3">{fmtPct(trade.max_runup_within_holding_pct)}</td>
                              <td className="py-1.5 pr-3">{fmtPct(trade.max_drawdown_within_holding_pct ?? trade.max_drawdown_pct)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="py-10 text-center text-sm text-slate-500">选择一条回测记录查看结果，或先运行新回测。</div>
                )}
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>
  );
};

export default SelectionResearchPage;
