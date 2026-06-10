import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowLeft, BarChart3, Calendar, ChevronDown, ChevronLeft, ChevronRight, RefreshCw, ShieldCheck } from 'lucide-react';

import {
  SelectionBacktestDetail,
  SelectionBacktestRunItem,
  SelectionCandidateItem,
  SelectionHealthData,
  HistoryMultiframeItem,
  SelectionMarketEnvironment,
  SelectionProfileData,
  SelectionStrategy,
  SelectionTradeDateItem,
  SelectionTradeDatesData,
} from '../../types';
import {
  fetchDailySelectionCandidates,
  fetchDailySelectionProfile,
  fetchDailySelectionTradeDates,
  fetchSelectionBacktestDetail,
  fetchSelectionBacktests,
  fetchSelectionHealth,
  fetchSelectionHistoryMultiframeBatch,
  fetchSelectionV2Evaluation,
  fetchStableCallbackEvaluation,
  fetchTrendContinuationEvaluation,
  prewarmSelectionResearchContexts,
  refreshDailySelectionCandidates,
  refreshSelectionResearch,
  runSelectionBacktest,
} from '../../services/selectionService';
import * as StockService from '../../services/stockService';
import QuoteMetaRow from '../common/QuoteMetaRow';
import StockQuoteHeroCard from '../common/StockQuoteHeroCard';
import { Metric, SectionCard } from '../common/ResearchCard';
import MiniKlineChart, { type MiniKlineMarker } from '../common/MiniKlineChart';
import SelectionDecisionPanel from './SelectionDecisionPanel';
import { APP_VERSION } from '../../version';
import { SPARK_PATTERN_RESEARCH_PAGES } from './sparkPatternResearchRegistry';
import { MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE } from './marketEnvironmentGateResearchRegistry';

const STABLE_CALLBACK_STRATEGY: SelectionStrategy = 'stable_capital_callback';
const TREND_CONTINUATION_STRATEGY: SelectionStrategy = 'trend_continuation_callback';
const PRODUCT_STRATEGIES: SelectionStrategy[] = [STABLE_CALLBACK_STRATEGY, TREND_CONTINUATION_STRATEGY];
const HOLDING_HISTORY_TIMEOUT_MS = 22000;
type ActiveStrategy = Extract<SelectionStrategy, 'stable_capital_callback' | 'trend_continuation_callback' | 'v2'>;

const STRATEGY_OPTIONS: Array<{ value: ActiveStrategy; label: string }> = [
  { value: 'stable_capital_callback', label: '资金流回调稳健' },
  { value: 'trend_continuation_callback', label: '趋势中继高质量回踩' },
  { value: 'v2', label: '旧策略对照' },
];

const STRATEGY_LABELS: Record<string, string> = {
  daily_candidate_pool: '每日综合候选池',
  spark_opportunity_selector: '星火机会模型 1.0',
  stable_capital_callback: '资金流回调稳健',
  trend_continuation_callback: '趋势中继高质量回踩',
  probe_day0_watch: '试盘观察池',
  probe_d3_confirmed: '试盘D3确认池',
  v2: '旧策略对照',
};
type CandidateEmptyState = 'idle' | 'not_run' | 'completed_empty' | 'failed';
type NavigatorGroup = 'all' | 'source_buy' | 'watch' | 'blocked' | 'holdings' | 'sell' | 'actionable';

const NAVIGATOR_GROUP_CONFIG: Record<NavigatorGroup, { label: string; shortLabel: string; tone: string; emptyText: string }> = {
  all: {
    label: '全部候选',
    shortLabel: '全部',
    tone: 'text-slate-100',
    emptyText: '当前日期没有每日候选票。',
  },
  source_buy: {
    label: '策略买点',
    shortLabel: '买点',
    tone: 'text-amber-200',
    emptyText: '当前日期没有策略原始买点票。',
  },
  watch: {
    label: '观察池',
    shortLabel: '观察',
    tone: 'text-cyan-200',
    emptyText: '当前日期没有观察池票。',
  },
  blocked: {
    label: '市场拦截',
    shortLabel: '拦截',
    tone: 'text-rose-200',
    emptyText: '当前日期没有被市场水位拦截的候选票。',
  },
  holdings: {
    label: '当前持仓',
    shortLabel: '持仓',
    tone: 'text-sky-200',
    emptyText: '当前日期没有持仓跟踪票。',
  },
  sell: {
    label: '次日卖出',
    shortLabel: '卖出',
    tone: 'text-fuchsia-200',
    emptyText: '当前日期没有次日卖出票。',
  },
  actionable: {
    label: '明日可操作',
    shortLabel: '可操作',
    tone: 'text-emerald-200',
    emptyText: '当前日期没有明日可操作票。',
  },
};

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));
const fmtSourceLabel = (source: Record<string, any>) => {
  const name = source.source_name || STRATEGY_LABELS[String(source.source_id)] || source.source_id || '来源';
  const rank = source.rank != null && !Number.isNaN(Number(source.rank)) ? `源#${Number(source.rank)}` : '';
  const score = source.score != null && !Number.isNaN(Number(source.score)) ? `源分${fmtNum(Number(source.score), 2)}` : '';
  const strength = source.source_strength_label ? `${source.source_strength_label}` : '';
  return [name, rank, score, strength].filter(Boolean).join(' ');
};
const sourceBadgeClass = (sourceId?: string) => {
  if (sourceId === 'spark_opportunity_selector') return 'border-sky-500/40 bg-sky-500/10 text-sky-200';
  if (sourceId === 'trend_continuation_callback') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (sourceId === 'stable_capital_callback') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  if (sourceId === 'probe_day0_watch') return 'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200';
  if (sourceId === 'probe_d3_confirmed') return 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200';
  return 'border-slate-700 bg-slate-950 text-slate-400';
};
const fmtSortScoreLabel = (item: SelectionCandidateItem) => {
  const rankScore = Number(item.selection_rank_score ?? item.score);
  const sourceScore = Number(item.source_score ?? item.score);
  if (Number.isFinite(rankScore) && Number.isFinite(sourceScore) && Math.abs(rankScore - sourceScore) > 0.01) {
    return `排序分｜源分${fmtNum(sourceScore)}`;
  }
  return '综合分';
};

const marketGateToneClass = (status?: string | null, label?: string | null) => {
  const text = `${status || ''} ${label || ''}`.toLowerCase();
  if (text.includes('block') || text.includes('pause') || text.includes('暂停') || text.includes('拦截')) {
    return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  }
  if (text.includes('watch') || text.includes('观察') || text.includes('谨慎') || text.includes('例外未通过')) {
    return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  }
  if (text.includes('allow') || text.includes('pass') || text.includes('允许') || text.includes('可买')) {
    return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  }
  return 'border-slate-700 bg-slate-950 text-slate-300';
};

const marketGateStatusText = (status?: string | null) => {
  if (!status) return '';
  if (status === 'allowed') return '环境允许';
  if (status === 'watch_only') return '仅观察';
  if (status === 'blocked') return '暂停新开仓';
  if (status === 'exception_failed') return '例外未通过';
  return status;
};

const getCandidateMarketGate = (item: SelectionCandidateItem) => {
  const environment = item.market_environment || item.market_environment_snapshot || null;
  const environmentLabel = environment?.market_detail_label || environment?.market_detail || environment?.market_regime || '';
  const sourceActionLabel = item.source_action_label || item.action_label || '';
  const gateActionLabel = item.market_default_action || marketGateStatusText(item.market_gate_status) || '';
  const finalActionLabel = item.final_action_label || (item.final_entry_allowed === false ? '仅观察' : '');
  const reasons = item.market_gate_reasons || [];
  const hasGate = Boolean(
    environmentLabel
    || item.market_gate_status
    || item.market_default_action
    || item.final_action_label
    || item.final_entry_allowed != null
    || reasons.length > 0
  );
  return { hasGate, environmentLabel, sourceActionLabel, gateActionLabel, finalActionLabel, reasons };
};

const getMarketMetric = (environment: SelectionMarketEnvironment | null, key: string) => {
  const value = environment?.metrics?.[key];
  return value == null || Number.isNaN(Number(value)) ? null : Number(value);
};

const marketRegimeColor = (regime?: string | null, actionCode?: string | null) => {
  if (regime === 'attack' || actionCode === 'allowed') return '#34d399';
  if (regime === 'caution' || actionCode === 'watch_only') return '#fbbf24';
  if (regime === 'defense' || actionCode === 'blocked') return '#fb7185';
  return '#94a3b8';
};

const marketTrendLabel = (points: SelectionMarketEnvironment['recent']) => {
  const valid = (points || []).filter((point) => Number.isFinite(Number(point.water_score)));
  if (valid.length < 2) return '近期走势不足';
  const first = Number(valid[0].water_score);
  const last = Number(valid[valid.length - 1].water_score);
  const delta = last - first;
  if (delta >= 8) return '水位抬升';
  if (delta <= -8) return '水位走低';
  return last < 30 ? '低位震荡' : '区间震荡';
};

const MarketWaterTrendChart: React.FC<{ points: SelectionMarketEnvironment['recent']; className?: string }> = ({ points = [], className = '' }) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const valid = points.filter((point) => Number.isFinite(Number(point.water_score)));
  if (valid.length < 2) {
    return (
      <div className={`flex items-center justify-center text-xs text-slate-500 ${className || 'h-28'}`}>
        暂无近期水位走势
      </div>
    );
  }
  const width = 640;
  const height = 172;
  const padX = 18;
  const top = 18;
  const bottom = 148;
  const yFor = (score: number) => top + (100 - Math.max(0, Math.min(100, score))) / 100 * (bottom - top);
  const xFor = (index: number) => padX + (valid.length <= 1 ? 0 : index / (valid.length - 1) * (width - padX * 2));
  const path = valid.map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(1)} ${yFor(Number(point.water_score)).toFixed(1)}`).join(' ');
  const last = valid[valid.length - 1];
  const first = valid[0];
  const lastX = xFor(valid.length - 1);
  const lastY = yFor(Number(last.water_score));
  const hoverPoint = hoverIndex == null ? null : valid[hoverIndex];
  const hoverX = hoverIndex == null ? null : xFor(hoverIndex);
  const hoverY = hoverPoint ? yFor(Number(hoverPoint.water_score)) : null;
  const hoverTooltipX = hoverX == null ? 0 : Math.min(Math.max(hoverX - 78, 8), width - 164);
  const hoverTooltipY = hoverY == null ? 0 : Math.max(12, hoverY - 54);
  const handleMouseMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const rawX = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * width;
    const ratio = (rawX - padX) / Math.max(width - padX * 2, 1);
    const nextIndex = Math.min(valid.length - 1, Math.max(0, Math.round(ratio * (valid.length - 1))));
    setHoverIndex(nextIndex);
  };
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={`h-full w-full cursor-crosshair ${className}`}
      role="img"
      aria-label="近90日市场水位走势"
      preserveAspectRatio="none"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoverIndex(null)}
    >
        <rect x="0" y="0" width={width} height={height} fill="#020617" opacity="0.95" />
        <rect x="0" y={yFor(100)} width={width} height={yFor(55) - yFor(100)} fill="#064e3b" opacity="0.18" />
        <rect x="0" y={yFor(55)} width={width} height={yFor(30) - yFor(55)} fill="#78350f" opacity="0.16" />
        <rect x="0" y={yFor(30)} width={width} height={yFor(0) - yFor(30)} fill="#7f1d1d" opacity="0.2" />
        <line x1="0" y1={yFor(55)} x2={width} y2={yFor(55)} stroke="#64748b" strokeDasharray="4 7" opacity="0.42" />
        <line x1="0" y1={yFor(30)} x2={width} y2={yFor(30)} stroke="#64748b" strokeDasharray="4 7" opacity="0.42" />
        <text x="18" y={yFor(72)} fill="#86efac" fontSize="11" opacity="0.86">进攻</text>
        <text x="18" y={yFor(43)} fill="#fde68a" fontSize="11" opacity="0.86">观察</text>
        <text x="18" y={yFor(15)} fill="#fecdd3" fontSize="11" opacity="0.86">防守</text>
        <path d={path} fill="none" stroke="#0f172a" strokeWidth="5.8" strokeLinecap="round" strokeLinejoin="round" opacity="0.58" />
        <path d={path} fill="none" stroke="#e2e8f0" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {valid.map((point, index) => (
          <circle
            key={`${point.trade_date || index}-${index}`}
            cx={xFor(index)}
            cy={yFor(Number(point.water_score))}
            r={index === valid.length - 1 ? 5.5 : index % 8 === 0 ? 2.2 : 1.4}
            fill={marketRegimeColor(point.market_regime, point.action_code)}
            opacity={index === valid.length - 1 ? 1 : 0.8}
          />
        ))}
        <line x1={lastX} y1={lastY} x2={lastX} y2={bottom + 10} stroke="#cbd5e1" strokeDasharray="3 5" opacity="0.5" />
        {hoverPoint && hoverX != null && hoverY != null ? (
          <g>
            <line x1={hoverX} y1={top} x2={hoverX} y2={bottom + 10} stroke="#f8fafc" strokeDasharray="3 4" opacity="0.72" />
            <circle cx={hoverX} cy={hoverY} r="6.5" fill="none" stroke="#f8fafc" strokeWidth="1.4" />
            <circle cx={hoverX} cy={hoverY} r="3.8" fill={marketRegimeColor(hoverPoint.market_regime, hoverPoint.action_code)} />
            <rect x={hoverTooltipX} y={hoverTooltipY} width="156" height="44" rx="6" fill="#020617" opacity="0.92" stroke="#475569" />
            <text x={hoverTooltipX + 10} y={hoverTooltipY + 17} fill="#e2e8f0" fontSize="11" fontWeight="700">
              {compactDateText(hoverPoint.trade_date)}
            </text>
            <text x={hoverTooltipX + 10} y={hoverTooltipY + 34} fill="#cbd5e1" fontSize="11">
              水位 {fmtNum(hoverPoint.water_score, 1)} · {hoverPoint.market_detail_label || hoverPoint.market_regime || '--'}
            </text>
          </g>
        ) : null}
        <text x={padX} y="163" fill="#94a3b8" fontSize="11">{compactDateText(first.trade_date).slice(5)}</text>
        <text x={width - padX} y="163" fill="#cbd5e1" fontSize="11" textAnchor="end">{compactDateText(last.trade_date).slice(5)}</text>
    </svg>
  );
};

const MarketEnvironmentSummaryCard: React.FC<{
  environment: SelectionMarketEnvironment | null;
}> = ({ environment }) => {
  if (!environment?.available) return null;
  const label = environment.market_detail_label || environment.market_detail || environment.market_regime || '市场环境';
  const actionLabel = environment.default_action || marketGateStatusText(environment.action_code) || '--';
  const trendText = marketTrendLabel(environment.recent);
  const statusLabel = `${label.replace(/[-_/]/g, '')} · 90日${trendText}`;
  const evidenceLabel = environment.action_code === 'blocked'
    ? '弱势证据'
    : environment.action_code === 'watch_only'
      ? '观察证据'
      : '环境证据';
  const evidenceText = `${evidenceLabel}：全市场5日上涨 ${fmtPct(getMarketMetric(environment, 'all_up_ratio_5d'), 1)}，小盘5日 ${fmtPct(getMarketMetric(environment, 'small_up_ratio_5d'), 1)}，中证1000 5日 ${fmtPct(getMarketMetric(environment, 'csi1000_return_5d_pct'), 1)}`;
  return (
    <div className="relative h-[172px] overflow-hidden border-b border-slate-800/80 bg-slate-950">
      <MarketWaterTrendChart points={environment.recent} className="absolute inset-0" />
      <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-3 px-4 pt-3">
        <div className="min-w-0 drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="shrink-0 text-xs font-semibold text-white">近期市场趋势</span>
            <span className="pointer-events-auto group relative inline-flex h-4 w-4 shrink-0 items-center justify-center text-amber-300">
              <AlertCircle className="h-3.5 w-3.5" />
              <span className="absolute left-0 top-full z-30 mt-1 hidden w-[340px] rounded-md border border-amber-400/30 bg-slate-950/95 px-2.5 py-2 text-[11px] font-normal leading-5 text-amber-50 shadow-xl group-hover:block">
                {evidenceText}
              </span>
            </span>
            <span className="truncate whitespace-nowrap text-xs font-semibold text-slate-200">{statusLabel}</span>
          </div>
        </div>
        <div className="shrink-0 text-right drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">
          <span className={`inline-flex rounded border px-2 py-1 text-[11px] font-semibold ${marketGateToneClass(environment.action_code, actionLabel)}`}>
            {actionLabel}
          </span>
          <div className="mt-1 font-mono text-xs text-slate-400">水位 {fmtNum(environment.water_score, 1)}</div>
        </div>
      </div>
    </div>
  );
};

const dualTrackToneClass = (status?: string) => {
  if (status === 'sell') return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  if (status === 'hold') return 'border-sky-500/40 bg-sky-500/10 text-sky-200';
  if (status === 'closed') return 'border-slate-700 bg-slate-950 text-slate-400';
  return 'border-slate-700 bg-slate-950 text-slate-300';
};

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

const maxDateText = (...values: Array<string | null | undefined>) => {
  const valid = values.map((item) => String(item || '').slice(0, 10)).filter(Boolean);
  return valid.sort().pop() || '';
};

const compactDateText = (value?: string | null) => String(value || '').slice(0, 10) || '--';

const withTimeoutFallback = async <T,>(promise: Promise<T>, timeoutMs: number, fallback: T): Promise<T> => new Promise((resolve) => {
  const timer = window.setTimeout(() => resolve(fallback), timeoutMs);
  promise
    .then(resolve)
    .catch(() => resolve(fallback))
    .finally(() => window.clearTimeout(timer));
});

const fmtMarketCap = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value)) || Number(value) <= 0) return '--';
  return `${(Number(value) / 1e8).toFixed(2)}亿`;
};

const mergeTradeDateItems = (datasets: Array<SelectionTradeDatesData | null | undefined>): SelectionTradeDatesData => {
  const byDate: Record<string, SelectionTradeDateItem> = {};
  datasets.flatMap((data) => data?.items || []).forEach((item) => {
    const prev = byDate[item.date];
    byDate[item.date] = {
      ...item,
      signal_count: (prev?.signal_count || 0) + (item.signal_count || 0),
      candidate_count: (prev?.candidate_count || 0) + (item.candidate_count || 0),
      feature_count: Math.max(prev?.feature_count || 0, item.feature_count || 0),
      has_feature: Boolean(prev?.has_feature || item.has_feature),
      has_candidates: Boolean(prev?.has_candidates || item.has_candidates),
      can_generate: Boolean(prev?.can_generate || item.can_generate),
      has_run: Boolean(prev?.has_run || item.has_run),
      run_count: (prev?.run_count || 0) + (item.run_count || 0),
      successful_run_count: (prev?.successful_run_count || 0) + (item.successful_run_count || 0),
      failed_run_count: (prev?.failed_run_count || 0) + (item.failed_run_count || 0),
      run_candidate_count: (prev?.run_candidate_count || 0) + (item.run_candidate_count || 0),
      last_run_finished_at: item.last_run_finished_at || prev?.last_run_finished_at,
      selectable: Boolean(prev?.selectable || item.selectable),
      disabled_reason: prev?.selectable || item.selectable ? null : item.disabled_reason,
    };
  });
  return { items: Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date)) };
};

const candidateEmptyStateForMeta = (meta?: SelectionTradeDateItem): CandidateEmptyState => {
  if (!meta) return 'idle';
  if (meta.has_candidates || (meta.candidate_count || meta.signal_count || 0) > 0) return 'idle';
  if (meta.has_run) return (meta.successful_run_count || 0) > 0 ? 'completed_empty' : 'failed';
  if (meta.can_generate || meta.has_feature) return 'not_run';
  return 'idle';
};

const latestSelectableDate = (items: SelectionTradeDateItem[]) => (
  items.filter((item) => item.selectable).map((item) => item.date).sort().pop() || ''
);

const findShiftedDate = (dates: string[], current: string, direction: -1 | 1) => {
  const sorted = [...dates].sort();
  if (!sorted.length || !current) return '';
  const exactIndex = sorted.indexOf(current);
  if (exactIndex >= 0) return sorted[exactIndex + direction] || '';
  if (direction < 0) {
    return [...sorted].reverse().find((date) => date < current) || '';
  }
  return sorted.find((date) => date > current) || '';
};

const tradeDateItemsToMap = (items: SelectionTradeDateItem[]) => {
  const next: Record<string, SelectionTradeDateItem> = {};
  items.forEach((item) => {
    next[item.date] = item;
  });
  return next;
};

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
  const hasDateMetadata = Object.keys(dateMetaByDate).length > 0;
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
    if (!isDateWithin(dateText, minDate, maxDate) || (hasDateMetadata ? meta?.selectable !== true : meta?.selectable === false)) return;
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
              const disabled = !isDateWithin(dateText, minDate, maxDate) || (hasDateMetadata ? meta?.selectable !== true : meta?.selectable === false);
              const isClosed = meta?.is_trade_day === false;
              const noScoreData = meta?.is_trade_day === true && meta?.selectable === false;
              const active = value === dateText;
              const title = meta?.has_candidates
                ? `${meta.candidate_count || meta.signal_count || 0} 个候选`
                : meta?.has_run
                  ? '已跑完，这天没有可推荐的股票'
                  : meta?.can_generate
                    ? '有评分数据，可运行当日候选'
                    : meta?.disabled_reason;
              return (
                <button
                  key={dateText}
                  type="button"
                  onClick={() => pickDate(day)}
                  disabled={disabled}
                  title={title}
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
                  {!disabled && !meta?.signal_count && meta?.can_generate ? <span className="absolute bottom-0.5 left-1/2 h-0.5 w-3 -translate-x-1/2 rounded-full bg-amber-400/80" /> : null}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3 text-[11px]">
            <span className="text-slate-500">绿点=有候选，黄点=可运行，灰色=不可选</span>
            <button type="button" onClick={jumpLatest} className="rounded-lg border border-slate-700 px-2 py-1 text-slate-200 hover:bg-slate-800">
              最新
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};

const SelectionTrendNavCard: React.FC<{
  item: SelectionCandidateItem & { displayName?: string };
  index: number;
  group: NavigatorGroup;
  active: boolean;
  history?: HistoryMultiframeItem[];
  loading?: boolean;
  onClick: () => void;
}> = ({ item, index, group, active, history = [], loading = false, onClick }) => {
  const dualTracks = item.dual_exit_tracks || [];
  const holdTrack = dualTracks.find((track) => track.status === 'hold') || dualTracks[0];
  const marketGate = getCandidateMarketGate(item);
  const latest = history[history.length - 1];
  const prevClose = Number(latest?.prev_close ?? history[history.length - 2]?.close ?? 0);
  const latestClose = Number(latest?.close ?? item.close ?? 0);
  const latestPct = prevClose > 0 && latestClose > 0 ? (latestClose / prevClose - 1) * 100 : null;
  const latestTone = Number(latestPct ?? item.return_5d_pct ?? 0) >= 0 ? 'text-red-300' : 'text-emerald-300';
  const score = Number(item.selection_rank_score ?? item.score);
  const sourceId = item.strategy_internal_id || item.primary_source_id || 'daily_candidate_pool';
  const isExitGroup = group === 'holdings' || group === 'sell';
  const buyDate = item.entry_date || item.replay_entry_date || item.entry_signal_date || item.trade_date || '';
  const signalDate = item.trade_date || buyDate;
  const trackExitDate = dualTracks
    .map((track) => track.exit_signal_date)
    .filter((date): date is string => Boolean(date))
    .sort()[0] || '';
  const sellDate = item.exit_signal_date || trackExitDate || item.replay_exit_signal_date || item.exit_date || '';
  const sourceAction = marketGate.sourceActionLabel || item.action_label || item.lifecycle_phase_label || '策略候选';
  const statusLabel = isExitGroup
    ? (holdTrack?.current_judgement || item.current_judgement || item.action_label || '继续持有')
    : group === 'source_buy'
      ? sourceAction
      : group === 'watch'
        ? (item.action_label || item.lifecycle_phase_label || '观察')
        : group === 'blocked'
          ? (marketGate.finalActionLabel || marketGate.gateActionLabel || '市场拦截')
          : (marketGate.finalActionLabel || item.final_action_label || item.action_label || '策略候选');
  const statusClass = isExitGroup
    ? dualTrackToneClass(holdTrack?.status)
    : marketGateToneClass(item.market_gate_status, statusLabel);
  const sourceCount = Number(item.source_count || item.source_details?.length || 1);
  const chartMarkers = isExitGroup
    ? [
      buyDate ? { date: buyDate, label: '买', tone: 'buy' as const } : null,
      sellDate ? { date: sellDate, label: '卖', tone: 'sell' as const } : null,
    ].filter((marker): marker is MiniKlineMarker => Boolean(marker))
    : [
      signalDate ? { date: signalDate, label: group === 'source_buy' ? '买' : '荐', tone: 'buy' as const } : null,
    ].filter((marker): marker is MiniKlineMarker => Boolean(marker));
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg border p-2 text-left transition ${active ? 'border-sky-400/70 bg-sky-500/15' : 'border-slate-800 bg-slate-950/35 hover:border-slate-600 hover:bg-slate-950/70'}`}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-[11px] text-slate-500">#{index + 1}</span>
            <span className="truncate text-sm font-bold leading-4 text-white">{item.displayName || item.name || item.symbol}</span>
            <span className="shrink-0 font-mono text-[10px] text-slate-500">{item.symbol}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
            <span className={`rounded border px-1.5 py-0.5 ${sourceBadgeClass(sourceId)}`}>
              {item.primary_source_name || item.strategy_display_name || STRATEGY_LABELS[sourceId] || sourceId}
            </span>
            <span className={`rounded border px-1.5 py-0.5 ${statusClass}`}>
              {statusLabel}
            </span>
          </div>
        </div>
        <div className="shrink-0 text-right font-mono">
          <div className="text-sm font-bold text-sky-200">{Number.isFinite(score) ? fmtNum(score) : '--'}</div>
          <div className={`text-[11px] font-semibold ${latestTone}`}>
            {latestPct != null ? `${latestPct >= 0 ? '+' : ''}${fmtPct(latestPct, 2)}` : fmtPct(item.return_5d_pct)}
          </div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <div>
          <div className="text-slate-500">{isExitGroup ? '买点' : '推荐'}</div>
          <div className="truncate font-mono text-sky-200">{compactDateText(isExitGroup ? buyDate : signalDate)}</div>
        </div>
        <div>
          <div className="text-slate-500">{isExitGroup ? '卖点' : '动作'}</div>
          <div className={`truncate font-mono ${isExitGroup && sellDate ? 'text-rose-200' : 'text-slate-300'}`}>
            {isExitGroup ? (sellDate ? compactDateText(sellDate) : '持有中') : statusLabel}
          </div>
        </div>
        <div>
          <div className="text-slate-500">{isExitGroup ? '持有' : '来源'}</div>
          <div className="truncate font-mono text-slate-300">{isExitGroup ? (holdTrack?.holding_days != null ? `${holdTrack.holding_days}天` : '--') : `${sourceCount}源`}</div>
        </div>
        <div>
          <div className="text-slate-500">5/20日</div>
          <div className={`truncate font-mono ${Number(item.return_5d_pct ?? item.return_20d_pct ?? 0) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>
            {fmtPct(item.return_5d_pct, 1)} / {fmtPct(item.return_20d_pct, 1)}
          </div>
        </div>
      </div>

      <div className="-mx-1 mt-2">
        <MiniKlineChart points={history} height={112} pointKeyPrefix={item.symbol} emptyText={loading ? 'K线加载中' : '暂无K线'} markers={chartMarkers} maxPoints={90} />
      </div>

      <div className="mt-1 truncate text-[11px] text-slate-500">
        {isExitGroup
          ? (holdTrack?.summary || item.reason_summary || item.pullback_reason || '暂无持仓说明')
          : (item.reason_summary || item.pullback_reason || marketGate.environmentLabel || '暂无来源解释')}
      </div>
    </button>
  );
};

const SelectionResearchPage: React.FC = () => {
  const [health, setHealth] = useState<SelectionHealthData | null>(null);
  const [activeStrategy, setActiveStrategy] = useState<ActiveStrategy>(STABLE_CALLBACK_STRATEGY);
  const [tradeDate, setTradeDate] = useState('');
  const [pendingTradeDate, setPendingTradeDate] = useState('');
  const [candidates, setCandidates] = useState<SelectionCandidateItem[]>([]);
  const [exitWatchlist, setExitWatchlist] = useState<SelectionCandidateItem[]>([]);
  const [marketEnvironment, setMarketEnvironment] = useState<SelectionMarketEnvironment | null>(null);
  const [sourceRuns, setSourceRuns] = useState<Array<{
    source_id: string;
    label: string;
    status: 'success' | 'failed';
    candidate_count: number;
    error?: string | null;
    finished_at?: string | null;
  }>>([]);
  const [selected, setSelected] = useState<SelectionCandidateItem | null>(null);
  const [navigatorGroup, setNavigatorGroup] = useState<NavigatorGroup>('all');
  const [profile, setProfile] = useState<SelectionProfileData | null>(null);
  const [quote, setQuote] = useState<any | null>(null);
  const [turnoverRate, setTurnoverRate] = useState<number | null>(null);
  const [trendHistoryBySymbol, setTrendHistoryBySymbol] = useState<Record<string, HistoryMultiframeItem[]>>({});
  const [backendStatus, setBackendStatus] = useState(true);
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [backtestRuns, setBacktestRuns] = useState<SelectionBacktestRunItem[]>([]);
  const [backtestDetail, setBacktestDetail] = useState<SelectionBacktestDetail | null>(null);
  const [v2Evaluation, setV2Evaluation] = useState<any | null>(null);
  const [nameOverrides, setNameOverrides] = useState<Record<string, string>>({});
  const [tradeDateMetaByDate, setTradeDateMetaByDate] = useState<Record<string, SelectionTradeDateItem>>({});
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidateEmptyStateByDate, setCandidateEmptyStateByDate] = useState<Record<string, CandidateEmptyState>>({});
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [loadingTrendHistory, setLoadingTrendHistory] = useState(false);
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [researchMenuOpen, setResearchMenuOpen] = useState(false);
  const [backtestStartDate, setBacktestStartDate] = useState('2026-03-02');
  const [backtestEndDate, setBacktestEndDate] = useState('2026-04-24');
  const [error, setError] = useState('');
  const selectedRef = useRef<SelectionCandidateItem | null>(null);
  const lastLoadedKeyRef = useRef('');
  const candidatesRequestSeqRef = useRef(0);
  const profileRequestSeqRef = useRef(0);
  const candidateLoadDateRef = useRef('');
  const backendHealthFailureCountRef = useRef(0);
  const dateInitializedRef = useRef(false);
  const prewarmNextLoadRef = useRef(false);
  const researchMenuRef = useRef<HTMLDivElement | null>(null);
  const datePickerMin = String(health?.source_snapshot?.history_bounds?.min_date || health?.source_snapshot?.atomic_bounds?.min_date || '2025-01-01');
  const datePickerMax = String(health?.source_snapshot?.history_bounds?.max_date || health?.source_snapshot?.atomic_bounds?.max_date || health?.latest_signal_date || '');

  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  const hydrateCandidateNames = async (items: SelectionCandidateItem[]) => {
    const seen = new Set<string>();
    const targets = items.filter((item) => {
      const symbol = String(item.symbol || '').toLowerCase();
      if (!symbol || seen.has(symbol)) return false;
      seen.add(symbol);
      return !item.name || item.name === item.symbol;
    });
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

  const triggerResearchPrewarm = (items: SelectionCandidateItem[], dateText?: string) => {
    if (!items.length) return;
    const actionable = items.filter((item) => item.entry_allowed !== false);
    const watch = items.filter((item) => item.entry_allowed === false).slice(0, 5);
    const picked = [...actionable, ...watch].slice(0, 12);
    if (!picked.length) return;
    void prewarmSelectionResearchContexts({
      date: dateText || tradeDate,
      strategy: 'daily_candidate_pool',
      limit: 12,
      items: picked.map((item) => ({
        symbol: item.symbol.toLowerCase(),
        trade_date: item.trade_date || dateText || tradeDate,
        strategy: item.strategy_internal_id || 'daily_candidate_pool',
        rank: item.rank,
        entry_allowed: item.entry_allowed,
        action_label: item.action_label,
      })),
    });
  };

  const loadHealth = async () => {
    const data = await fetchSelectionHealth();
    setHealth(data);
    return data;
  };

  const loadSelectableDates = async (minDate: string, maxDate: string): Promise<SelectionTradeDatesData | null> => {
    if (!minDate || !maxDate) return null;
    return fetchDailySelectionTradeDates(minDate, maxDate);
  };

  const reloadSelectableDates = async (minDate = datePickerMin, maxDate = datePickerMax): Promise<Record<string, SelectionTradeDateItem>> => {
    if (!minDate || !maxDate) return tradeDateMetaByDate;
    const data = await loadSelectableDates(minDate, maxDate);
    const next = tradeDateItemsToMap(data?.items || []);
    setTradeDateMetaByDate(next);
    return next;
  };

  const ensureDailyCandidates = async (dateText: string) => {
    const meta = tradeDateMetaByDate[dateText];
    if (!dateText) return { generated: false, mergedCount: 0, meta };
    if (!meta) {
      const nextMetaByDate = await reloadSelectableDates();
      const nextMeta = nextMetaByDate[dateText];
      if (!nextMeta || nextMeta.has_candidates || !nextMeta.can_generate || nextMeta.has_run) {
        return { generated: false, mergedCount: nextMeta?.candidate_count || 0, meta: nextMeta };
      }
    } else if (meta.has_candidates || !meta.can_generate || meta.has_run) {
      return { generated: false, mergedCount: meta?.candidate_count || 0, meta };
    }
    const result = await refreshDailySelectionCandidates(dateText, 80);
    if (!result) {
      setCandidateEmptyStateByDate((prev) => ({ ...prev, [dateText]: 'failed' }));
      throw new Error('daily-refresh failed');
    }
    const mergedCount = Number(result?.merged_count ?? 0);
    setCandidateEmptyStateByDate((prev) => ({
      ...prev,
      [dateText]: mergedCount > 0 ? 'idle' : 'completed_empty',
    }));
    const nextMetaByDate = await reloadSelectableDates();
    return {
      generated: true,
      mergedCount,
      meta: nextMetaByDate[dateText],
    };
  };

  const selectableDates = useMemo(() => (
    Object.values(tradeDateMetaByDate)
      .filter((item) => item.selectable)
      .map((item) => item.date)
      .sort()
  ), [tradeDateMetaByDate]);

  const currentDateText = pendingTradeDate || tradeDate;
  const prevSelectableDate = useMemo(
    () => findShiftedDate(selectableDates, currentDateText, -1),
    [currentDateText, selectableDates],
  );
  const nextSelectableDate = useMemo(
    () => findShiftedDate(selectableDates, currentDateText, 1),
    [currentDateText, selectableDates],
  );
  const canShiftPrev = Boolean(prevSelectableDate);
  const canShiftNext = Boolean(nextSelectableDate);

  const shiftSelectableDate = (direction: -1 | 1) => {
    const next = direction < 0 ? prevSelectableDate : nextSelectableDate;
    if (!next) return;
    lastLoadedKeyRef.current = '';
    setError('');
    setPendingTradeDate(next);
    setTradeDate(next);
  };

  const loadCandidates = async (dateArg = tradeDate, force = false, prewarm = false) => {
    const targetDate = dateArg || tradeDate;
    if (!targetDate) return;
    const loadKey = `daily_candidate_pool:${targetDate}`;
    if (!force && lastLoadedKeyRef.current === loadKey) return;
    lastLoadedKeyRef.current = loadKey;
    const shouldPrewarm = prewarm || prewarmNextLoadRef.current;
    prewarmNextLoadRef.current = false;
    const requestSeq = candidatesRequestSeqRef.current + 1;
    candidatesRequestSeqRef.current = requestSeq;
    candidateLoadDateRef.current = targetDate;
    setLoadingCandidates(true);
    setError('');
    if (selectedRef.current?.trade_date !== targetDate) {
      setCandidates([]);
      setExitWatchlist([]);
      setMarketEnvironment(null);
      setSourceRuns([]);
      setSelected(null);
      setProfile(null);
    }
    try {
      const data = await fetchDailySelectionCandidates(targetDate, 80, undefined, true);
      if (requestSeq !== candidatesRequestSeqRef.current || targetDate !== candidateLoadDateRef.current) return;
      const items = data?.items || [];
      const watchItems = data?.exit_watchlist?.items || [];
      const runs = data?.source_runs || [];
      const nextDate = targetDate || data?.trade_date || '';
      setCandidates(items);
      setExitWatchlist(watchItems);
      setMarketEnvironment(data?.market_environment || null);
      setSourceRuns(runs);
      setCandidateEmptyStateByDate((prev) => {
        if (items.length > 0) return { ...prev, [targetDate]: 'idle' };
        const nextState = prev[targetDate] || candidateEmptyStateForMeta(tradeDateMetaByDate[targetDate]);
        return { ...prev, [targetDate]: nextState };
      });
      if (shouldPrewarm) {
        triggerResearchPrewarm(items, nextDate || targetDate);
      }
      const prevSelected = selectedRef.current;
      const keepSelected = (
        prevSelected?.trade_date === targetDate
          ? [...items, ...watchItems].find((item) => item.symbol === prevSelected?.symbol && item.trade_date === prevSelected.trade_date)
          : null
      ) || items[0] || watchItems[0] || null;
      setSelected(keepSelected);
      if (!keepSelected) setProfile(null);
      void hydrateCandidateNames([...items, ...watchItems]);
    } catch (e) {
      if (requestSeq === candidatesRequestSeqRef.current) {
        lastLoadedKeyRef.current = '';
        setError('候选加载失败');
        setMarketEnvironment(null);
      }
    } finally {
      if (requestSeq === candidatesRequestSeqRef.current) setLoadingCandidates(false);
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
    void loadHealth();
    loadBacktests();
    let cancelled = false;
    const check = () => {
      StockService.checkBackendHealth().then((ok) => {
        if (cancelled) return;
        if (ok) {
          backendHealthFailureCountRef.current = 0;
          setBackendStatus(true);
          return;
        }
        backendHealthFailureCountRef.current += 1;
        if (backendHealthFailureCountRef.current >= 3) setBackendStatus(false);
      });
    };
    check();
    const timer = window.setInterval(check, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!tradeDate) return;
    loadCandidates(tradeDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradeDate]);

  const handleApplyTradeDate = async () => {
    if (!pendingTradeDate) return;
    setLoadingCandidates(true);
    setError('');
    try {
      await ensureDailyCandidates(pendingTradeDate);
    } catch (e) {
      setError('候选生成失败，请检查写权限或后端日志');
      setCandidates([]);
      setSelected(null);
      setProfile(null);
      setLoadingCandidates(false);
      return;
    }
    if (pendingTradeDate === tradeDate) {
      await loadCandidates(pendingTradeDate, true, true);
      return;
    }
    prewarmNextLoadRef.current = true;
    setTradeDate(pendingTradeDate);
  };

  useEffect(() => {
    if (!selected) {
      profileRequestSeqRef.current += 1;
      setProfile(null);
      setLoadingProfile(false);
      return;
    }
    let cancelled = false;
    const requestSeq = profileRequestSeqRef.current + 1;
    profileRequestSeqRef.current = requestSeq;
    const profileDate = selected.trade_date || tradeDate;
    const profileSymbol = selected.symbol;
    setLoadingProfile(true);
    fetchDailySelectionProfile(profileSymbol, profileDate)
      .then((data) => {
        if (!cancelled && requestSeq === profileRequestSeqRef.current) setProfile(data);
      })
      .finally(() => {
        if (!cancelled && requestSeq === profileRequestSeqRef.current) setLoadingProfile(false);
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
      const beforeHealth = await loadHealth();
      const latestDate = String(
        beforeHealth?.source_snapshot?.history_bounds?.max_date
          || beforeHealth?.source_snapshot?.atomic_bounds?.max_date
          || beforeHealth?.latest_signal_date
          || tradeDate
          || ''
      );
      const refreshResult = latestDate
        ? await refreshSelectionResearch(latestDate, latestDate)
        : await refreshSelectionResearch();
      if (latestDate) {
        await refreshDailySelectionCandidates(latestDate, 80);
      }
      const afterHealth = await loadHealth();
      const minDate = String(afterHealth?.source_snapshot?.history_bounds?.min_date || afterHealth?.source_snapshot?.atomic_bounds?.min_date || datePickerMin || '2025-01-01');
      const maxDate = String(refreshResult?.end_date || afterHealth?.latest_signal_date || latestDate || datePickerMax || '');
      const datesData = await loadSelectableDates(minDate, maxDate);
      setTradeDateMetaByDate(tradeDateItemsToMap(datesData?.items || []));
      const nextDate = latestSelectableDate(datesData?.items || []) || tradeDate || pendingTradeDate || '';
      if (nextDate) {
        setTradeDate(nextDate);
        setPendingTradeDate(nextDate);
        await loadCandidates(nextDate, true, true);
      } else {
        await loadCandidates(tradeDate, true, true);
      }
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
      if (PRODUCT_STRATEGIES.includes(activeStrategy) || activeStrategy === 'v2') {
        const payload = activeStrategy === STABLE_CALLBACK_STRATEGY ? await fetchStableCallbackEvaluation({
          start_date: backtestStartDate,
          end_date: backtestEndDate,
          top_n: 10,
        }) : activeStrategy === TREND_CONTINUATION_STRATEGY ? await fetchTrendContinuationEvaluation({
          start_date: backtestStartDate,
          end_date: backtestEndDate,
          top_n: 20,
        }) : await fetchSelectionV2Evaluation({
          start_date: backtestStartDate,
          end_date: backtestEndDate,
          top_n: 10,
        });
        setV2Evaluation(payload);
        setBacktestDetail(null);
        return;
      }
      setV2Evaluation(null);
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

  const displayCandidates = useMemo(() => {
    return candidates.map((item) => ({
      ...item,
      displayName: nameOverrides[item.symbol.toLowerCase()] || item.name || item.symbol,
    }));
  }, [candidates, nameOverrides]);

  const displayExitWatchlist = useMemo(() => {
    return exitWatchlist.map((item) => ({
      ...item,
      displayName: nameOverrides[item.symbol.toLowerCase()] || item.name || item.symbol,
    }));
  }, [exitWatchlist, nameOverrides]);

  const dailyGroups = useMemo(() => {
    const isFinalAllowed = (item: SelectionCandidateItem) => (
      item.final_entry_allowed != null ? item.final_entry_allowed !== false : item.entry_allowed !== false
    );
    const isSourceBuy = (item: SelectionCandidateItem) => (
      item.entry_allowed !== false
      || item.action_label?.includes('买')
      || item.lifecycle_phase === 'candidate_buy'
      || item.candidate_types?.some((type) => String(type).includes('buy'))
    );
    const isMarketBlocked = (item: SelectionCandidateItem) => (
      item.market_gate_status === 'blocked'
      || item.market_default_action?.includes('暂停')
      || item.final_action_label === '仅观察'
      || item.final_entry_allowed === false
    );
    const isWatch = (item: SelectionCandidateItem) => !isSourceBuy(item) && (
      item.market_gate_status === 'watch_only' ||
      item.lifecycle_phase === 'watch' ||
      item.lifecycle_phase === 'trend_observation_pool' ||
      item.candidate_types?.some((type) => {
        const text = String(type);
        return text.includes('observe') || text.includes('watch') || text.includes('probe');
      }) ||
      item.action_label === '观察中' ||
      item.action_label === '观察'
    );
    return {
      all: displayCandidates,
      actionable: displayCandidates.filter((item) => isFinalAllowed(item)),
      sourceBuy: displayCandidates.filter((item) => isSourceBuy(item)),
      watch: displayCandidates.filter((item) => isWatch(item)),
      blocked: displayCandidates.filter((item) => isMarketBlocked(item) || !isFinalAllowed(item)),
    };
  }, [displayCandidates]);

  const exitGroups = useMemo(() => {
    return {
      sell: displayExitWatchlist.filter((item) => item.exit_signal_date),
      hold: displayExitWatchlist.filter((item) => !item.exit_signal_date),
    };
  }, [displayExitWatchlist]);
  const navigationGroupItems = useMemo<Record<NavigatorGroup, Array<SelectionCandidateItem & { displayName?: string }>>>(() => ({
    all: dailyGroups.all,
    source_buy: dailyGroups.sourceBuy,
    watch: dailyGroups.watch,
    blocked: dailyGroups.blocked,
    holdings: exitGroups.hold,
    sell: exitGroups.sell,
    actionable: dailyGroups.actionable,
  }), [dailyGroups.actionable, dailyGroups.all, dailyGroups.blocked, dailyGroups.sourceBuy, dailyGroups.watch, exitGroups.hold, exitGroups.sell]);
  const resolvedNavigatorGroup = navigationGroupItems[navigatorGroup]?.length
    ? navigatorGroup
    : dailyGroups.all.length > 0
      ? 'all'
      : exitGroups.hold.length > 0
        ? 'holdings'
        : navigatorGroup;
  const activeNavigatorItems = navigationGroupItems[resolvedNavigatorGroup] || [];
  const navigatorGroupTabs = useMemo(() => ([
    { id: 'all' as const, count: dailyGroups.all.length },
    { id: 'source_buy' as const, count: dailyGroups.sourceBuy.length },
    { id: 'watch' as const, count: dailyGroups.watch.length },
    { id: 'blocked' as const, count: dailyGroups.blocked.length },
    { id: 'holdings' as const, count: exitGroups.hold.length },
    { id: 'sell' as const, count: exitGroups.sell.length },
    { id: 'actionable' as const, count: dailyGroups.actionable.length },
  ]), [
    dailyGroups.actionable.length,
    dailyGroups.all.length,
    dailyGroups.blocked.length,
    dailyGroups.sourceBuy.length,
    dailyGroups.watch.length,
    exitGroups.hold.length,
    exitGroups.sell.length,
  ]);
  const activeNavigatorKey = activeNavigatorItems.map((item) => `${item.symbol}:${item.trade_date}:${item.rank}`).join('|');
  const activeNavigatorSymbols = useMemo(() => (
    Array.from(new Set(activeNavigatorItems.map((item) => item.symbol.toLowerCase()))).sort()
  ), [activeNavigatorKey]);
  const activeNavigatorSymbolsKey = activeNavigatorSymbols.join('|');

  useEffect(() => {
    if (resolvedNavigatorGroup !== navigatorGroup) {
      setNavigatorGroup(resolvedNavigatorGroup);
    }
  }, [navigatorGroup, resolvedNavigatorGroup]);

  useEffect(() => {
    if (!activeNavigatorItems.length) return;
    const selectedInGroup = selected
      ? activeNavigatorItems.some((item) => item.symbol === selected.symbol && item.trade_date === selected.trade_date)
      : false;
    if (!selectedInGroup) {
      setSelected(activeNavigatorItems[0]);
    }
  }, [activeNavigatorKey, selected?.symbol, selected?.trade_date]);

  useEffect(() => {
    if (!activeNavigatorSymbols.length) return undefined;
    const missing = activeNavigatorSymbols.filter((symbol) => !trendHistoryBySymbol[symbol]);
    if (!missing.length) return undefined;
    let cancelled = false;
    setLoadingTrendHistory(true);
    withTimeoutFallback(
      fetchSelectionHistoryMultiframeBatch(missing, {
        days: 90,
        granularity: '1d',
        includeTodayPreview: false,
        allowCloudFallback: false,
      }),
      HOLDING_HISTORY_TIMEOUT_MS,
      {},
    )
      .then((rowsBySymbol) => {
        if (cancelled) return;
        setTrendHistoryBySymbol((prev) => {
          const next = { ...prev };
          missing.forEach((symbol) => {
            if (!next[symbol] && Object.prototype.hasOwnProperty.call(rowsBySymbol, symbol)) {
              next[symbol] = rowsBySymbol[symbol] || [];
            }
          });
          return next;
        });
      })
      .finally(() => {
        if (!cancelled) setLoadingTrendHistory(false);
      });

    return () => {
      cancelled = true;
    };
    // trendHistoryBySymbol intentionally stays out: the batch marks missing symbols as loaded when it completes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeNavigatorSymbolsKey, activeNavigatorSymbols]);

  const candidateListDate = tradeDate || pendingTradeDate;
  const candidateDateMeta = candidateListDate ? tradeDateMetaByDate[candidateListDate] : undefined;
  const candidateEmptyState = candidateListDate
    ? candidateEmptyStateByDate[candidateListDate] || candidateEmptyStateForMeta(candidateDateMeta)
    : 'idle';
  const candidateEmptyMessage = (() => {
    if (candidateEmptyState === 'completed_empty') return '已跑完，今天没有可推荐的股票。';
    if (candidateEmptyState === 'failed') return '这天候选生成失败，请检查写权限或后端日志。';
    if (candidateEmptyState === 'not_run') return '这天还没有运行当日候选，点击“查看候选”后会执行模型和策略。';
    return '暂无候选；该日期没有模型或策略产出。';
  })();

  const latestSelectableTradeDate = useMemo(() => {
    return Object.values(tradeDateMetaByDate)
      .filter((item) => item.selectable)
      .map((item) => item.date)
      .sort()
      .pop() || '';
  }, [tradeDateMetaByDate]);
  const latestDataTradeDate = maxDateText(datePickerMax, health?.latest_signal_date, latestSelectableTradeDate) || undefined;
  const selectedDisplayName = selected ? (nameOverrides[selected.symbol.toLowerCase()] || profile?.name || selected.name || selected.symbol) : '';
  const heroPrice = Number(quote?.price ?? profile?.close ?? selected?.close ?? 0);
  const previousClose = Number(quote?.lastClose ?? profile?.prev_close ?? profile?.close ?? selected?.close ?? 0);
  const open = Number(quote?.open ?? profile?.close ?? selected?.close ?? 0);
  const high = Number(quote?.high ?? profile?.close ?? selected?.close ?? 0);
  const low = Number(quote?.low ?? profile?.close ?? selected?.close ?? 0);
  const heroName = (quote?.name || selectedDisplayName || profile?.name || selected?.name || selected?.symbol || '').trim();
  const profileMatchesSelected = Boolean(
    selected && profile && String(profile.symbol || '').toLowerCase() === String(selected.symbol || '').toLowerCase(),
  );

  useEffect(() => {
    if (!datePickerMin || !datePickerMax) return;
    let cancelled = false;
    const loadDates = fetchDailySelectionTradeDates(datePickerMin, datePickerMax);
    loadDates
      .then((data) => {
        if (cancelled) return;
        const next = tradeDateItemsToMap(data?.items || []);
        setTradeDateMetaByDate(next);
        const latestSelectable = (data?.items || []).filter((item) => item.selectable).map((item) => item.date).sort().pop();
        const currentApplied = tradeDate;
        const shouldInitialize = !dateInitializedRef.current;
        const currentInvalid = Boolean(currentApplied && (next[currentApplied]?.selectable === false || !next[currentApplied]));
        if (latestSelectable && (shouldInitialize || currentInvalid)) {
          dateInitializedRef.current = true;
          lastLoadedKeyRef.current = '';
          setTradeDate(latestSelectable);
          setPendingTradeDate(latestSelectable);
        }
      })
      .catch(() => {
        if (!cancelled) setTradeDateMetaByDate({});
      });
    return () => {
      cancelled = true;
    };
  }, [datePickerMax, datePickerMin]);

  useEffect(() => {
    if (!researchMenuOpen) return undefined;
    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (researchMenuRef.current && target && !researchMenuRef.current.contains(target)) {
        setResearchMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [researchMenuOpen]);

  const renderCandidateItem = (item: SelectionCandidateItem & { displayName?: string }, sectionRank: number) => {
    const strategyId = item.strategy_internal_id || item.primary_source_id || 'daily_candidate_pool';
    const active = selected?.symbol === item.symbol && selected?.trade_date === item.trade_date;
    const sourceLabels = (item.source_details?.length ? item.source_details : [{ source_id: strategyId, source_name: item.strategy_display_name || STRATEGY_LABELS[String(strategyId)] || strategyId }]).slice(0, 3);
    const dualTracks = item.dual_exit_tracks || [];
    const marketGate = getCandidateMarketGate(item);
    const finalAllowed = item.final_entry_allowed != null ? item.final_entry_allowed !== false : item.entry_allowed !== false;
    const displayActionLabel = item.final_action_label || item.action_label || '--';
    return (
      <button
        key={`daily_candidate_pool-${item.symbol}-${item.trade_date}-${item.rank}`}
        type="button"
        onClick={() => {
          setSelected(item);
        }}
        className={`w-full px-4 py-3 text-left transition ${active ? 'bg-sky-500/10' : 'hover:bg-slate-950/35'}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-500">#{sectionRank || '--'}</span>
              <span className="truncate text-sm font-semibold text-white">{item.displayName}</span>
              <span className="shrink-0 text-[11px] text-slate-500">{item.symbol}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
              {sourceLabels.map((source: Record<string, any>) => (
                <span key={`${item.symbol}-${source.source_id || source.source_name}`} className={`rounded border px-1.5 py-0.5 ${sourceBadgeClass(String(source.source_id || ''))}`}>
                  {fmtSourceLabel(source)}
                </span>
              ))}
              {(item.source_count || 0) > sourceLabels.length ? (
                <span className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-500">+{(item.source_count || 0) - sourceLabels.length}</span>
              ) : null}
            </div>
            {dualTracks.length > 0 ? (
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
                {dualTracks.map((track) => (
                  <span key={`${item.symbol}-${track.track_id}`} className={`rounded border px-1.5 py-0.5 ${dualTrackToneClass(track.status)}`}>
                    {track.track_name}：{track.current_judgement || '--'}
                  </span>
                ))}
              </div>
            ) : null}
            {marketGate.hasGate ? (
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
                {marketGate.environmentLabel ? (
                  <span className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-300">
                    市场：{marketGate.environmentLabel}
                  </span>
                ) : null}
                {marketGate.sourceActionLabel ? (
                  <span className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-400">
                    来源：{marketGate.sourceActionLabel}
                  </span>
                ) : null}
                {marketGate.gateActionLabel ? (
                  <span className={`rounded border px-1.5 py-0.5 ${marketGateToneClass(item.market_gate_status, marketGate.gateActionLabel)}`}>
                    环境：{marketGate.gateActionLabel}
                  </span>
                ) : null}
                {marketGate.finalActionLabel ? (
                  <span className={`rounded border px-1.5 py-0.5 ${marketGateToneClass(item.market_gate_status, marketGate.finalActionLabel)}`}>
                    最终：{marketGate.finalActionLabel}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="grid min-w-[132px] shrink-0 grid-cols-2 gap-2 text-right text-[10px]">
            <div>
              <div className="text-sm font-semibold text-sky-200">{fmtNum(item.selection_rank_score ?? item.score)}</div>
              <div className="whitespace-nowrap text-slate-500">{fmtSortScoreLabel(item)}</div>
            </div>
            <div>
              <div className={`text-sm font-semibold ${finalAllowed ? 'text-emerald-200' : 'text-amber-200'}`}>{displayActionLabel}</div>
              <div className="text-slate-500">{marketGate.hasGate ? '最终动作' : dualTracks.length > 0 ? '双轨判断' : '动作'}</div>
            </div>
          </div>
        </div>
        <div className="mt-1 truncate text-xs text-slate-500">
          {item.reason_summary || item.pullback_reason || '暂无来源解释'}
        </div>
      </button>
    );
  };

  const renderCandidateSection = (title: string, items: Array<SelectionCandidateItem & { displayName?: string }>, tone: string) => {
    if (!items.length) return null;
    return (
      <div className="border-b border-slate-800/80 last:border-b-0">
        <div className="bg-slate-950/35 px-4 py-2 text-xs font-semibold text-slate-300">
          <span className={tone}>{title}</span>
          <span className="ml-2 text-slate-600">{items.length}</span>
        </div>
        <div className="divide-y divide-slate-800/80">{items.map((item, index) => renderCandidateItem(item, index + 1))}</div>
      </div>
    );
  };

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
          <button
            type="button"
            onClick={() => shiftSelectableDate(-1)}
            disabled={!canShiftPrev}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 bg-slate-950 text-slate-200 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="前一个可选日期"
            title="前一个可选日期"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <TradeDatePicker
            value={pendingTradeDate}
            minDate={datePickerMin}
            maxDate={datePickerMax}
            latestDate={latestSelectableTradeDate || undefined}
            dateMetaByDate={tradeDateMetaByDate}
            onChange={setPendingTradeDate}
          />
          <button
            type="button"
            onClick={() => shiftSelectableDate(1)}
            disabled={!canShiftNext}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 bg-slate-950 text-slate-200 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="后一个可选日期"
            title="后一个可选日期"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleApplyTradeDate}
            disabled={!pendingTradeDate || loadingCandidates}
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ShieldCheck className={`h-4 w-4 ${loadingCandidates ? 'animate-pulse' : ''}`} />
            {loadingCandidates ? '查询中' : '查看候选'}
          </button>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? '刷新中' : '刷新当日候选'}
          </button>
          <div ref={researchMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setResearchMenuOpen((prev) => !prev)}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500"
            >
              <BarChart3 className="h-4 w-4" />
              研究入口
              <ChevronDown className={`h-4 w-4 transition ${researchMenuOpen ? 'rotate-180' : ''}`} />
            </button>
            {researchMenuOpen ? (
              <div className="absolute right-0 top-full z-[120] mt-2 w-[420px] overflow-hidden rounded-xl border border-slate-600 bg-[#020617] p-2 shadow-[0_24px_60px_rgba(2,6,23,0.82)]">
                {[MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE, ...SPARK_PATTERN_RESEARCH_PAGES].map((item) => (
                  item.enabled ? (
                    <a
                      key={item.id}
                      href={item.href}
                      className="block rounded-lg px-3 py-3 transition hover:bg-slate-900"
                    >
                      <div className="text-sm font-medium text-white">{item.title}</div>
                      <div className="mt-1 text-xs leading-5 text-slate-400">{item.description}</div>
                    </a>
                  ) : (
                    <div key={item.id} className="rounded-lg px-3 py-3 opacity-60">
                      <div className="text-sm font-medium text-slate-300">{item.title}</div>
                      <div className="mt-1 text-xs leading-5 text-slate-500">{item.description}</div>
                    </div>
                  )
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        {error && <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}

        <div className="grid gap-4 xl:grid-cols-[minmax(600px,1.06fr)_minmax(600px,0.94fr)] xl:items-start">
          <div className="flex min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-900/70 xl:sticky xl:top-[72px] xl:max-h-[calc(100vh-88px)]">
            <div className="min-h-0 xl:overflow-y-auto">
              <div className="border-b border-slate-800 px-4 py-2.5">
                <div className="flex flex-nowrap items-center gap-1.5 overflow-x-auto whitespace-nowrap text-[11px]">
                  <span className="inline-flex h-7 shrink-0 items-center rounded-full border border-slate-800 bg-slate-950/50 px-2.5 font-mono text-[11px] text-slate-400">
                    {tradeDate || pendingTradeDate || health?.latest_signal_date || '--'}
                  </span>
                  {sourceRuns.length > 0 ? (
                    <div className="group relative shrink-0">
                      <button
                        type="button"
                        className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-800 bg-slate-950/50 text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-100"
                        aria-label="查看当日策略状态"
                      >
                        <AlertCircle className="h-3.5 w-3.5" />
                      </button>
                      <div className="pointer-events-none absolute left-0 top-full z-20 hidden pt-2 group-hover:block">
                        <div className="w-72 rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-[11px] leading-5 text-slate-200 shadow-2xl">
                          <div className="space-y-1.5">
                            {sourceRuns.map((item) => (
                              <div key={item.source_id} className="flex items-start justify-between gap-3">
                                <span className="text-slate-300">{item.label}</span>
                                <span className={item.status === 'failed' ? 'text-rose-300' : 'text-slate-400'}>
                                  {item.status === 'failed' ? '失败' : `成功 ${item.candidate_count} 条`}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {navigatorGroupTabs.map((group) => {
                    const config = NAVIGATOR_GROUP_CONFIG[group.id];
                    return (
                      <button
                        key={group.id}
                        type="button"
                        onClick={() => setNavigatorGroup(group.id)}
                        aria-pressed={resolvedNavigatorGroup === group.id}
                        className={`inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 font-medium transition ${
                          resolvedNavigatorGroup === group.id
                            ? 'border-sky-400/70 bg-sky-500/20 text-white'
                            : 'border-slate-800 bg-slate-950/35 text-slate-400 hover:border-slate-600 hover:bg-slate-950/70 hover:text-slate-100'
                        }`}
                      >
                        <span className={resolvedNavigatorGroup === group.id ? config.tone : ''}>{config.shortLabel}</span>
                        <span className="font-mono text-[10px] text-slate-500">{group.count}</span>
                      </button>
                    );
                  })}
                  {loadingCandidates ? <span className="shrink-0 px-1 text-[11px] text-slate-500">加载中...</span> : null}
                </div>
              </div>
              <MarketEnvironmentSummaryCard
                environment={marketEnvironment}
              />
              {activeNavigatorItems.length > 0 ? (
                <div className="space-y-2 px-3 pb-3">
                  <div className="flex items-center justify-between gap-2 px-1 pt-3">
                    <div className="text-sm font-bold text-white">{NAVIGATOR_GROUP_CONFIG[resolvedNavigatorGroup].label}</div>
                    <div className="flex items-center gap-2">
                      {loadingTrendHistory ? <span className="text-[11px] text-slate-500">加载走势...</span> : null}
                      <span className="font-mono text-[11px] text-slate-500">{activeNavigatorItems.length} 只</span>
                    </div>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {activeNavigatorItems.map((item, index) => {
                      const symbol = item.symbol.toLowerCase();
                      const historyLoaded = Object.prototype.hasOwnProperty.call(trendHistoryBySymbol, symbol);
                      return (
                        <SelectionTrendNavCard
                          key={`trend-nav-${resolvedNavigatorGroup}-${symbol}-${item.trade_date}-${index}`}
                          item={item}
                          index={index}
                          group={resolvedNavigatorGroup}
                          active={selected?.symbol === item.symbol && selected?.trade_date === item.trade_date}
                          history={trendHistoryBySymbol[symbol]}
                          loading={loadingTrendHistory && !historyLoaded}
                          onClick={() => setSelected(item)}
                        />
                      );
                    })}
                  </div>
                </div>
              ) : !loadingCandidates && displayCandidates.length === 0 && displayExitWatchlist.length === 0 ? (
                <div className="px-4 py-10 text-center text-sm text-slate-500">
                  {candidateEmptyMessage}
                </div>
              ) : (
                <div className="px-4 py-10 text-center text-sm text-slate-500">
                  {NAVIGATOR_GROUP_CONFIG[resolvedNavigatorGroup].emptyText}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-2 xl:max-h-[calc(100vh-88px)] xl:overflow-y-auto">
            {selected ? (
              <div className="mb-2">
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
                  latestLabel={`最新 ${latestDataTradeDate || selected.trade_date}`}
                  marketCapLabel={fmtMarketCap(profile?.market_cap ?? selected.market_cap)}
                  metaRow={
                    <QuoteMetaRow
                      isWatchlisted={isWatchlisted}
                      onToggleWatchlist={handleToggleWatchlist}
                      backendStatus={backendStatus}
                    />
                  }
                />
              </div>
            ) : null}
            <SelectionDecisionPanel
              candidate={selected}
              profile={profile}
              displayName={selectedDisplayName}
              backendStatus={backendStatus}
              latestTradeDate={latestDataTradeDate}
            />
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
            <div className="grid gap-3 md:grid-cols-[220px_180px_180px_auto_auto] md:items-end">
              <label className="text-xs text-slate-400">
                验证策略
                <select
                  value={activeStrategy}
                  onChange={(e) => setActiveStrategy(e.target.value as ActiveStrategy)}
                  className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 outline-none hover:border-slate-500"
                  aria-label="选择验证策略"
                >
                  {STRATEGY_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </label>
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

	            {PRODUCT_STRATEGIES.includes(activeStrategy) || activeStrategy === 'v2' ? (
	              <div>
	                {v2Evaluation ? (
	                  <div className="space-y-3">
	                    <div className="grid gap-2 md:grid-cols-5">
	                      <Metric label="交易数" value={String(v2Evaluation.summary?.trade_count ?? 0)} />
	                      <Metric label="胜率" value={fmtPct(v2Evaluation.summary?.win_rate)} />
	                      <Metric label="平均净收益" value={fmtPct(v2Evaluation.summary?.avg_return_pct)} />
	                      <Metric label="中位净收益" value={fmtPct(v2Evaluation.summary?.median_return_pct)} />
	                      <Metric label="最大亏损" value={fmtPct(v2Evaluation.summary?.max_loss_pct ?? v2Evaluation.summary?.min_return_pct)} tone="text-red-200" />
	                    </div>
                    <div className="max-h-80 overflow-auto rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2">
                      <table className="min-w-full text-xs">
                        <thead className="text-left text-slate-500">
                          <tr>
                            <th className="pb-2 pr-3">股票</th>
                            <th className="pb-2 pr-3">排名</th>
                            <th className="pb-2 pr-3">信号</th>
                            <th className="pb-2 pr-3">入场</th>
                            <th className="pb-2 pr-3">出场</th>
	                            <th className="pb-2 pr-3">阶段</th>
	                            <th className="pb-2 pr-3">风险</th>
	                            <th className="pb-2 pr-3">收益</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(v2Evaluation.trades || []).slice(0, 80).map((trade: any, index: number) => (
                            <tr key={`${trade.symbol}-${trade.signal_date}-${index}`} className="border-t border-slate-800/70">
                              <td className="py-1.5 pr-3">{trade.symbol}</td>
                              <td className="py-1.5 pr-3">#{trade.rank ?? '--'}</td>
                              <td className="py-1.5 pr-3">{trade.signal_date}</td>
                              <td className="py-1.5 pr-3">{trade.entry_date}</td>
	                              <td className="py-1.5 pr-3">{trade.exit_signal_date || trade.exit_date}</td>
	                              <td className="py-1.5 pr-3">{trade.lifecycle_phase_label || '--'}</td>
	                              <td className="py-1.5 pr-3">{trade.risk_count ?? '--'}</td>
	                              <td className="py-1.5 pr-3">{fmtPct(trade.net_return_pct ?? trade.return_pct)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
	                  <div className="py-10 text-center text-sm text-slate-500">运行策略评估后展示每日 Top10 候选的入场、出场和收益。</div>
                )}
              </div>
            ) : (
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
            )}
          </div>
        </details>
      </div>
    </div>
  );
};

export default SelectionResearchPage;
