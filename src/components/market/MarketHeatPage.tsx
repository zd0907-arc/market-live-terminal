import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Flame, RefreshCw, Activity, TrendingUp, Zap, ShieldAlert, Crosshair, X, ChevronRight, Calendar, ChevronLeft } from 'lucide-react';
import { fetchFineHeatDashboard, fetchFineHeatDates, fetchFineThemeForecast, fetchFineThemeStockDetail, refreshFineHeatDashboard, FineHeatDashboard, FineHeatDatesData, FineHeatForecast, FineHeatForecastItem, FineHeatStock, FineHeatTheme, FineHeatThemeStockDetail, FineHeatTradeDateItem } from '../../services/marketHeatService';
import * as StockService from '../../services/stockService';
import { HistoryMultiframeGranularity, SearchResult } from '../../types';
import HistoryMultiframeFusionView from '../dashboard/HistoryMultiframeFusionView';
import { APP_VERSION } from '../../version';

const fmt = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));
const pct = (value?: number | null) => `${fmt(value)}%`;
const yi = (value?: number | null) => `${fmt(value)}亿`;

const mono = 'font-mono tabular-nums';
const pad2 = (value: number) => String(value).padStart(2, '0');
const parseDateOnly = (value?: string | null): Date | null => {
  if (!value) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day, 0, 0, 0, 0);
};
const formatDateOnly = (value: Date) => `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
const monthLabel = (value: Date) => `${value.getFullYear()}年${pad2(value.getMonth() + 1)}月`;
const isDateWithin = (value: string, minDate?: string | null, maxDate?: string | null) => {
  if (minDate && value < minDate) return false;
  if (maxDate && value > maxDate) return false;
  return true;
};

const lifecycleClass = (label?: string) => {
  if (label === '首次新热') return 'border-red-500/30 bg-red-500/10 text-red-200';
  if (label === '主线再加速') return 'border-orange-500/30 bg-orange-500/10 text-orange-200';
  if (label === '持续升温') return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  if (label === '持续主线') return 'border-violet-500/30 bg-violet-500/10 text-violet-200';
  if (label === '退潮观察') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  if (label === '主线延续预警') return 'border-sky-500/30 bg-sky-500/10 text-sky-200';
  return 'border-slate-700 bg-slate-800/50 text-slate-300';
};

const rankColor = (rank: number, frontBand: number, orangeBand: number, hotBand: number, watchBand: number) => {
  if (rank <= frontBand) return 'bg-red-500';
  if (rank <= orangeBand) return 'bg-orange-500';
  if (rank <= hotBand) return 'bg-sky-500';
  if (rank <= watchBand) return 'bg-slate-500';
  return 'bg-transparent';
};

const SparkBars: React.FC<{ theme?: FineHeatTheme | null; frontBand: number; orangeBand: number; hotBand: number; watchBand: number; height?: number }> = ({ theme, frontBand, orangeBand, hotBand, watchBand, height = 34 }) => {
  const points = theme?.trend || [];
  if (!points.length) return <div className="h-8 rounded bg-slate-950/60" />;
  return (
    <div className="flex w-full items-end gap-[1px]" style={{ height }}>
      {points.map((point) => {
        const rank = Number(point.rank);
        const active = rank <= watchBand;
        const rankHeight = active ? Math.max(0.22, 1 - (rank - 1) * 0.02) : 0;
        const barHeight = active ? Math.max(3, Math.min(height, rankHeight * height)) : 2;
        return (
          <div
            key={`${theme?.id}-${point.date}`}
            className={`min-w-[2px] flex-1 rounded-[1px] ${active ? rankColor(rank, frontBand, orangeBand, hotBand, watchBand) : 'bg-slate-700'}`}
            style={{ height: barHeight, opacity: active ? 0.95 : 0.55 }}
            title={`${point.date} 排名 #${point.rank} 热度 ${fmt(point.hot_score, 1)}`}
          />
        );
      })}
    </div>
  );
};

const HotspotMiniCard: React.FC<{
  item: FineHeatTheme;
  active: boolean;
  dashboard: FineHeatDashboard | null;
  onSelect: () => void;
}> = ({ item, active, dashboard, onSelect }) => (
  <button
    type="button"
    onClick={onSelect}
    className={`w-full rounded-md border px-1.5 pb-1 pt-0.5 text-left transition ${active ? 'border-sky-400/60 bg-sky-500/15' : 'border-slate-800/70 bg-slate-950/45 hover:border-slate-600/80 hover:bg-slate-950/75'}`}
  >
    <div className="flex h-4 items-center gap-1.5">
      <div className="min-w-0 flex-1 truncate text-[13px] font-bold leading-none text-white">{item.name}</div>
      <div className={`shrink-0 text-[10px] leading-none ${mono} text-slate-500`}>
        #{item.rank_today} · 封{item.stock_summary?.limit_up_count ?? item.limit_up_count}/炸{item.stock_summary?.broken_limit_up_count ?? item.broken_limit_up_count}
      </div>
    </div>
    <div className="-mx-1 mt-0.5">
      <SparkBars
        theme={item}
        frontBand={dashboard?.meta.front_band ?? 5}
        orangeBand={dashboard?.meta.orange_band ?? 10}
        hotBand={dashboard?.meta.hot_band ?? 15}
        watchBand={dashboard?.meta.watch_band ?? 30}
        height={32}
      />
    </div>
  </button>
);

const HotspotPool: React.FC<{
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  items: FineHeatTheme[];
  dashboard: FineHeatDashboard | null;
  selectedId: string;
  onSelect: (id: string) => void;
  tone: string;
}> = ({ title, subtitle, icon, items, dashboard, selectedId, onSelect, tone }) => (
  <section className={`rounded-lg border ${tone} bg-slate-900/70 p-1.5`}>
    <div className="mb-1 flex h-5 items-center justify-between gap-2 px-0.5">
      <div>
        <div className="flex items-center gap-1.5 text-[13px] font-bold text-white">{icon}{title}</div>
      </div>
      <div className="flex items-center gap-2">
        <span className="hidden text-[10px] text-slate-500 2xl:inline">{subtitle}</span>
        <span className={`rounded-full border border-slate-700 bg-slate-950 px-1.5 py-0 text-[10px] leading-4 ${mono} text-slate-400`}>{items.length}</span>
      </div>
    </div>
    <div className="space-y-0.5">
      {items.map((item) => (
        <HotspotMiniCard key={`${title}-${item.id}`} item={item} active={selectedId === item.id} dashboard={dashboard} onSelect={() => onSelect(item.id)} />
      ))}
      {!items.length ? <div className="rounded-md border border-slate-800 bg-slate-950/40 px-2 py-3 text-center text-xs text-slate-500">暂无符合条件热点</div> : null}
    </div>
  </section>
);

const ForecastStrip: React.FC<{
  forecast: FineHeatForecast | null;
  dashboard: FineHeatDashboard | null;
  selectedId: string;
  onSelect: (item: FineHeatForecastItem) => void;
}> = ({ forecast, dashboard, selectedId, onSelect }) => {
  const items = forecast?.items || [];
  if (!forecast || !items.length) return null;
  const metric = forecast.metrics || {};
  return (
    <section className="mb-2 rounded-lg border border-sky-500/20 bg-slate-950/55 p-2">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[13px] font-bold text-white">
          <Crosshair className="h-4 w-4 text-sky-300" />
          主线延续预警
          <span className={`rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[10px] ${mono} text-sky-100`}>
            未来{forecast.meta.horizon_days}日延续
          </span>
        </div>
        <div className={`text-[10px] ${mono} text-slate-500`}>
          Top5命中 {fmt(Number(metric.precision_at_5 ?? metric.precision_at_10) * 100, 1)}% · 候选宇宙 {forecast.meta.universe || 'all'}
        </div>
      </div>
      <div className="flex gap-1 overflow-x-auto pb-0.5">
        {items.slice(0, 5).map((item) => {
          const active = selectedId === item.theme_id;
          const live = dashboard?.pool?.find((theme) => theme.id === item.theme_id);
          return (
            <button
              key={`forecast-${item.theme_id}`}
              type="button"
              onClick={() => onSelect(item)}
              className={`shrink-0 rounded-md border px-2 py-1.5 text-left transition ${active ? 'border-sky-400/70 bg-sky-500/20' : 'border-slate-800 bg-slate-900/70 hover:border-slate-600'}`}
              title={`${item.theme_name}，模型概率 ${fmt(item.probability_pct, 1)}%，当前排名 #${item.current_rank}`}
            >
              <div className="flex items-center gap-1.5">
                <span className="max-w-[90px] truncate text-xs font-bold text-white">{item.theme_name}</span>
                <span className={`${mono} text-[10px] text-sky-200`}>{fmt(item.probability_pct, 0)}%</span>
              </div>
              <div className={`mt-0.5 text-[10px] ${mono} text-slate-500`}>
                预警#{item.score_rank} · 今#{item.current_rank}{live?.lifecycle ? ` · ${live.lifecycle}` : ''}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
};

const StockMiniCard: React.FC<{ stock: NonNullable<FineHeatTheme['stocks']>[number] }> = ({ stock }) => {
  const positive = Number(stock.pct_change) >= 0;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{stock.name}</div>
          <div className={`text-[10px] ${mono} text-slate-500`}>{stock.symbol}</div>
        </div>
        <div className={`shrink-0 text-right text-sm font-bold ${mono} ${positive ? 'text-red-300' : 'text-emerald-300'}`}>{positive ? '+' : ''}{fmt(stock.pct_change, 2)}%</div>
      </div>
      <div className={`mt-2 flex items-center justify-between text-[10px] ${mono} text-slate-500`}>
        <span>{fmt(stock.amount_yi, 1)}亿</span>
        <span className={Number(stock.l2_net_inflow_yi) >= 0 ? 'text-red-200' : 'text-emerald-200'}>{fmt(stock.l2_net_inflow_yi, 1)}亿</span>
        {stock.is_limit_up ? <span className="text-red-200">封板</span> : stock.broken_limit_up ? <span className="text-amber-200">炸板</span> : null}
      </div>
    </div>
  );
};

const StockGroup: React.FC<{ title: string; items?: NonNullable<FineHeatTheme['stocks']>; empty: string }> = ({ title, items = [], empty }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
    <div className="mb-2 flex items-center justify-between">
      <div className="text-xs font-bold text-slate-300">{title}</div>
      <div className={`text-[10px] ${mono} text-slate-600`}>{items.length}</div>
    </div>
    <div className="grid gap-2 sm:grid-cols-2">
      {items.slice(0, 6).map((stock) => <StockMiniCard key={`${title}-${stock.symbol}`} stock={stock} />)}
    </div>
    {!items.length ? <div className="py-3 text-center text-xs text-slate-600">{empty}</div> : null}
  </div>
);

const stockSignalClass = (tone?: string) => {
  if (tone === 'opportunity') return 'border-sky-500/35 bg-sky-500/10 text-sky-100';
  if (tone === 'strong') return 'border-red-500/35 bg-red-500/10 text-red-100';
  if (tone === 'hot') return 'border-amber-500/35 bg-amber-500/10 text-amber-100';
  if (tone === 'risk') return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-100';
  return 'border-slate-700 bg-slate-800/60 text-slate-300';
};

const movingAverage = (values: number[], windowSize: number) => values.map((_, index) => {
  if (index + 1 < windowSize) return null;
  const slice = values.slice(index + 1 - windowSize, index + 1);
  return slice.reduce((sum, value) => sum + value, 0) / windowSize;
});

const MiniKlineSvg: React.FC<{ stock: FineHeatStock }> = ({ stock }) => {
  const points = (stock.history || []).slice(-45);
  if (points.length < 2) {
    return <div className="flex h-[86px] items-center justify-center text-[10px] text-slate-600">暂无K线</div>;
  }
  const width = 360;
  const height = 86;
  const top = 4;
  const bottom = 4;
  const left = 4;
  const right = 4;
  const innerW = width - left - right;
  const innerH = height - top - bottom;
  const closes = points.map((point) => Number(point.close || 0));
  const ma5 = movingAverage(closes, 5);
  const ma10 = movingAverage(closes, 10);
  const allValues = [
    ...points.flatMap((point) => [Number(point.high || 0), Number(point.low || 0)]),
    ...ma5.filter((value): value is number => value != null),
    ...ma10.filter((value): value is number => value != null),
  ].filter((value) => Number.isFinite(value) && value > 0);
  if (!allValues.length) {
    return <div className="flex h-[86px] items-center justify-center text-[10px] text-slate-600">暂无K线</div>;
  }
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max > min ? max - min : Math.max(1, max * 0.04);
  const y = (value: number) => top + (max - value) / span * innerH;
  const step = innerW / Math.max(1, points.length - 1);
  const candleW = Math.max(2.2, Math.min(4.2, step * 0.5));
  const linePath = (values: Array<number | null>) => values
    .map((value, index) => value == null ? null : `${index === values.findIndex((v) => v != null) ? 'M' : 'L'} ${left + index * step} ${y(value)}`)
    .filter(Boolean)
    .join(' ');
  const ma5Path = linePath(ma5);
  const ma10Path = linePath(ma10);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" shapeRendering="geometricPrecision" className="h-[86px] w-full overflow-hidden">
      <line x1={left} x2={width - right} y1={height - bottom} y2={height - bottom} stroke="#1e293b" strokeWidth="0.8" />
      {points.map((point, index) => {
        const open = Number(point.open || 0);
        const close = Number(point.close || 0);
        const high = Number(point.high || 0);
        const low = Number(point.low || 0);
        const up = close >= open;
        const color = up ? '#fb7185' : '#22c55e';
        const wickColor = up ? '#f87171' : '#34d399';
        const x = left + index * step;
        const yOpen = y(open);
        const yClose = y(close);
        const bodyY = Math.min(yOpen, yClose);
        const bodyH = Math.max(1.5, Math.abs(yClose - yOpen));
        const isLast = index === points.length - 1;
        return (
          <g key={`${stock.symbol}-${point.trade_date}`}>
            <line x1={x} x2={x} y1={y(high)} y2={y(low)} stroke={wickColor} strokeWidth={isLast ? 1.1 : 0.8} opacity={isLast ? 0.95 : 0.78} />
            <rect
              x={x - candleW / 2}
              y={bodyY}
              width={candleW}
              height={bodyH}
              rx={0}
              fill={color}
              stroke="none"
              opacity={isLast ? 1 : 0.9}
            />
            {isLast ? <circle cx={x} cy={y(close)} r="1.9" fill="#38bdf8" stroke="#0f172a" strokeWidth="0.8" /> : null}
          </g>
        );
      })}
      {ma10Path ? <path d={ma10Path} fill="none" stroke="#a78bfa" strokeWidth="1.25" opacity="0.9" strokeLinecap="round" strokeLinejoin="round" /> : null}
      {ma5Path ? <path d={ma5Path} fill="none" stroke="#fbbf24" strokeWidth="1.25" opacity="0.95" strokeLinecap="round" strokeLinejoin="round" /> : null}
    </svg>
  );
};

const StockTrendCard: React.FC<{
  stock: FineHeatStock;
  index: number;
  active: boolean;
  onClick: () => void;
}> = ({ stock, index, active, onClick }) => {
  const positive = Number(stock.pct_change) >= 0;
  const boardTag = stock.is_limit_up ? '封' : stock.broken_limit_up ? '炸' : stock.touch_limit_up ? '摸' : '';
  const boardTone = stock.is_limit_up ? 'text-red-200' : stock.broken_limit_up ? 'text-amber-200' : stock.touch_limit_up ? 'text-orange-200' : 'text-slate-500';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg border px-2 py-1.5 text-left transition ${active ? 'border-sky-400/70 bg-sky-500/15' : 'border-slate-800 bg-slate-950/35 hover:border-slate-600 hover:bg-slate-950/70'}`}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[10px]">
        <span className={`${mono} text-slate-600`}>#{index + 1}</span>
        <span className="max-w-[92px] truncate text-sm font-bold leading-4 text-white">{stock.name}</span>
        <span className={`${mono} font-bold ${positive ? 'text-red-300' : 'text-emerald-300'}`}>{positive ? '+' : ''}{fmt(stock.pct_change, 2)}%</span>
        <span className={`rounded border px-1.5 py-0.5 leading-3 ${stockSignalClass(stock.signal_tone)}`}>{stock.signal_label || '观察'}</span>
        {boardTag ? <span className={`rounded border border-slate-700 bg-slate-900 px-1 py-0.5 leading-3 ${boardTone}`}>{boardTag}</span> : null}
        <span className={`${mono} text-slate-400`}>20位 {fmt(stock.position_20d, 0)}%</span>
        <span className={`${mono} ${Number(stock.return_5d ?? 0) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>5日 {Number(stock.return_5d ?? 0) >= 0 ? '+' : ''}{fmt(stock.return_5d, 1)}%</span>
        <span className={`${mono} text-slate-400`}>量 {fmt(stock.amount_ratio_10d, 1)}x</span>
        <span className={`${mono} ${Number(stock.l2_net_inflow_3d_yi ?? stock.l2_net_inflow_yi ?? 0) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>L2 {fmt(stock.l2_net_inflow_3d_yi ?? stock.l2_net_inflow_yi, 1)}亿</span>
      </div>
      <div className="-mx-1 mt-1">
        <MiniKlineSvg stock={stock} />
      </div>
    </button>
  );
};

const stockToSearchResult = (stock: FineHeatStock): SearchResult => ({
  symbol: stock.symbol,
  code: stock.symbol.slice(2),
  market: stock.symbol.slice(0, 2),
  name: stock.name,
});

const StockInlineDetailPanel: React.FC<{
  stock: FineHeatStock;
  theme: FineHeatTheme | null;
  onClose: () => void;
}> = ({ stock, theme, onClose }) => {
  const [granularity, setGranularity] = useState<HistoryMultiframeGranularity>('1d');
  const activeStock = useMemo(() => stockToSearchResult(stock), [stock]);
  const positive = Number(stock.pct_change) >= 0;
  return (
    <div className="rounded-xl border border-sky-500/25 bg-slate-900/85 p-3 shadow-xl shadow-black/20">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="truncate text-lg font-bold text-white">{stock.name}</div>
            <span className={`${mono} text-xs text-slate-500`}>{stock.symbol}</span>
            <span className={`rounded border px-2 py-0.5 text-xs ${stockSignalClass(stock.signal_tone)}`}>{stock.signal_label || '观察'}</span>
            <span className={`rounded border border-slate-700 bg-slate-950 px-2 py-0.5 text-xs ${positive ? 'text-red-200' : 'text-emerald-200'}`}>
              {positive ? '+' : ''}{fmt(stock.pct_change, 2)}%
            </span>
          </div>
          <div className="mt-1 text-xs text-slate-500">
            当前热点：{theme?.name || '--'}；20日位置 {fmt(stock.position_20d, 0)}%，距20日高点 {fmt(stock.drawdown_20d, 1)}%，量能 {fmt(stock.amount_ratio_10d, 1)}x
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a href={`/?symbol=${stock.symbol}`} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 text-xs text-slate-200 hover:border-slate-500">
            打开全页 <ChevronRight className="h-3.5 w-3.5" />
          </a>
          <button type="button" onClick={onClose} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      <HistoryMultiframeFusionView
        activeStock={activeStock}
        backendStatus
        granularity={granularity}
        onGranularityChange={setGranularity}
        includeTodayPreview={false}
      />
    </div>
  );
};

const sortFineStocks = (stocks: FineHeatStock[], sort: string) => {
  const list = [...stocks];
  if (sort === 'opportunity') return list.sort((a, b) => Number(b.opportunity_score ?? 0) - Number(a.opportunity_score ?? 0) || Number(b.pct_change ?? 0) - Number(a.pct_change ?? 0));
  if (sort === 'funding') return list.sort((a, b) => Number(b.l2_net_inflow_3d_yi ?? b.l2_net_inflow_yi ?? 0) - Number(a.l2_net_inflow_3d_yi ?? a.l2_net_inflow_yi ?? 0));
  if (sort === 'risk') return list.sort((a, b) => Number(b.risk_score ?? 0) - Number(a.risk_score ?? 0) || Number(a.pct_change ?? 0) - Number(b.pct_change ?? 0));
  if (sort === 'amount') return list.sort((a, b) => Number(b.amount_yi ?? 0) - Number(a.amount_yi ?? 0));
  return list.sort((a, b) => Number(b.pct_change ?? -999) - Number(a.pct_change ?? -999));
};

const hydrateStocksWithHistoryFallback = async (stocks: FineHeatStock[], days = 45): Promise<FineHeatStock[]> => {
  const out: FineHeatStock[] = [];
  const batchSize = 8;
  for (let start = 0; start < stocks.length; start += batchSize) {
    const batch = stocks.slice(start, start + batchSize);
    const hydrated = await Promise.all(batch.map(async (stock) => {
      try {
        const rows = await StockService.fetchHistoryMultiframe(stock.symbol, {
          days,
          granularity: '1d',
          includeTodayPreview: false,
        });
        const clean = rows
          .filter((row) => Number(row.open) > 0 && Number(row.high) > 0 && Number(row.low) > 0 && Number(row.close) > 0)
          .slice(-days);
        if (!clean.length) return stock;
        const history = clean.map((row, index) => {
          const prevClose = Number(row.prev_close ?? clean[index - 1]?.close ?? row.open ?? 0);
          const close = Number(row.close ?? 0);
          const pctChange = prevClose > 0 ? (close / prevClose - 1) * 100 : 0;
          const l2Net = (Number(row.l2_main_buy ?? 0) - Number(row.l2_main_sell ?? 0)) / 1e8;
          return {
            trade_date: String(row.trade_date || row.datetime?.slice(0, 10) || ''),
            open: Number(row.open),
            high: Number(row.high),
            low: Number(row.low),
            close,
            pct_change: Number(pctChange.toFixed(2)),
            amount_yi: Number((Number(row.total_amount ?? 0) / 1e8).toFixed(2)),
            l2_net_inflow_yi: Number(l2Net.toFixed(2)),
          };
        });
        const closes = history.map((row) => row.close);
        const latest = history[history.length - 1];
        const recent20 = history.slice(-20);
        const high20 = Math.max(...recent20.map((row) => row.high));
        const low20 = Math.min(...recent20.map((row) => row.low));
        const position20 = high20 > low20 ? (latest.close - low20) / (high20 - low20) * 100 : 50;
        const drawdown20 = high20 > 0 ? (latest.close / high20 - 1) * 100 : 0;
        const returnFrom = (lookback: number) => {
          const base = history[Math.max(0, history.length - 1 - lookback)]?.close;
          return base > 0 ? (latest.close / base - 1) * 100 : 0;
        };
        const priorAmounts = history.slice(-11, -1).map((row) => Number(row.amount_yi || 0)).filter((value) => value > 0);
        const avgAmount = priorAmounts.length ? priorAmounts.reduce((sum, value) => sum + value, 0) / priorAmounts.length : 0;
        const l2Last3 = history.slice(-3).map((row) => Number(row.l2_net_inflow_yi || 0));
        const l2Net3 = l2Last3.reduce((sum, value) => sum + value, 0);
        const avgClose = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : latest.close;
        return {
          ...stock,
          history,
          return_5d: Number(returnFrom(5).toFixed(2)),
          return_20d: Number(returnFrom(20).toFixed(2)),
          position_20d: Number(position20.toFixed(1)),
          drawdown_20d: Number(drawdown20.toFixed(1)),
          amount_ratio_10d: Number((avgAmount > 0 ? latest.amount_yi / avgAmount : 1).toFixed(2)),
          l2_net_inflow_3d_yi: Number(l2Net3.toFixed(2)),
          l2_positive_days_3d: l2Last3.filter((value) => value > 0).length,
          ma5: Number(avgClose(closes.slice(-5)).toFixed(2)),
          ma10: Number(avgClose(closes.slice(-10)).toFixed(2)),
        };
      } catch {
        return stock;
      }
    }));
    out.push(...hydrated);
  }
  return out;
};

const FineThemeDetail: React.FC<{
  item: FineHeatTheme | null;
  dashboard: FineHeatDashboard | null;
  activeStockSymbol?: string;
  stockLoading?: boolean;
  panelHeight?: number;
  onStockSelect?: (stock: FineHeatStock) => void;
}> = ({ item, dashboard, activeStockSymbol, stockLoading, panelHeight, onStockSelect }) => {
  const [stockSort, setStockSort] = useState('pct_desc');
  if (!item) {
    return <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-sm text-slate-500">选择左侧主题查看详情。</div>;
  }
  const summary = item.stock_summary;
  const confirmation = (summary?.limit_up_count || 0) >= 2 && (summary?.up_ratio || 0) >= 60
    ? '强确认'
    : (summary?.up_ratio || 0) >= 55
      ? '扩散中'
      : (summary?.limit_up_count || 0) <= 0
        ? '弱确认'
        : '观察';
  const stocks = sortFineStocks(item.stocks || [], stockSort);
  const statItems = [
    ['排名', `#${item.rank_today}`, 'text-sky-200'],
    ['均涨', pct(summary?.avg_pct_change ?? item.pct_change), (summary?.avg_pct_change ?? item.pct_change) >= 0 ? 'text-red-300' : 'text-emerald-300'],
    ['上涨', `${summary?.up_count ?? '--'}/${summary?.stock_count ?? '--'}`, 'text-slate-200'],
    ['占比', pct(summary?.up_ratio), 'text-red-200'],
    ['封/炸', `${summary?.limit_up_count ?? item.limit_up_count}/${summary?.broken_limit_up_count ?? item.broken_limit_up_count}`, 'text-red-200'],
    ['确认', confirmation, confirmation === '强确认' ? 'text-red-200' : confirmation === '扩散中' ? 'text-amber-200' : 'text-slate-300'],
  ];
  return (
    <div
      className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 xl:overflow-y-auto"
      style={panelHeight ? { height: Math.max(420, panelHeight) } : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <div className="truncate text-lg font-bold text-white">{item.name}</div>
            <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] leading-3 ${lifecycleClass(item.lifecycle)}`}>{item.lifecycle}</span>
          </div>
          <div className={`mt-1 truncate text-[11px] ${mono} text-slate-500`}>
            {item.sector_type} · 成员 {summary?.stock_count || item.member_count || '--'} · {dashboard?.meta.trade_date}
          </div>
        </div>
        <div className={`shrink-0 text-right text-[11px] ${mono} text-slate-500`}>
          <div className="text-sky-200">#{item.rank_today}</div>
          <div>封{summary?.limit_up_count ?? item.limit_up_count}/炸{summary?.broken_limit_up_count ?? item.broken_limit_up_count}</div>
        </div>
      </div>

      <div className="mt-3 border-y border-slate-800/80 py-2">
        <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
          <span>近30日排名形态</span>
          <span>红Top5 / 橙Top10 / 蓝Top15 / 灰Top30 / 暗线占位</span>
        </div>
        <SparkBars theme={item} frontBand={dashboard?.meta.front_band ?? 5} orangeBand={dashboard?.meta.orange_band ?? 10} hotBand={dashboard?.meta.hot_band ?? 15} watchBand={dashboard?.meta.watch_band ?? 30} height={50} />
      </div>

      <div className="grid grid-cols-3 gap-x-3 gap-y-1 py-2 text-[11px]">
        {statItems.map(([label, value, tone]) => (
          <div key={label as string} className="flex items-center justify-between gap-2">
            <span className="text-slate-500">{label}</span>
            <span className={`${mono} ${tone}`}>{value}</span>
          </div>
        ))}
      </div>

      <div className="border-t border-slate-800/80 pt-2">
        <div className="mb-2 flex items-center justify-between gap-2 text-xs">
          <div>
            <span className="font-bold text-slate-200">成分股趋势卡片</span>
            {stockLoading ? <span className="ml-2 text-[10px] text-sky-300">K线加载中...</span> : null}
          </div>
          <span className={`${mono} text-slate-500`}>{stocks.length} 只</span>
        </div>
        <div className="mb-2 grid grid-cols-2 gap-1 text-[10px] sm:grid-cols-5">
          {[
            ['pct_desc', '今日涨幅'],
            ['opportunity', '机会线索'],
            ['funding', '资金确认'],
            ['risk', '退潮风险'],
            ['amount', '成交额'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setStockSort(value)}
              className={`rounded-lg border px-2 py-1 ${stockSort === value ? 'border-sky-500/50 bg-sky-500/15 text-sky-100' : 'border-slate-800 bg-slate-950/50 text-slate-400 hover:border-slate-600'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="space-y-2">
          {stocks.map((stock, index) => (
            <StockTrendCard
              key={`trend-${item.id}-${stock.symbol}`}
              stock={stock}
              index={index}
              active={activeStockSymbol === stock.symbol}
              onClick={() => onStockSelect?.(stock)}
            />
          ))}
          {!stocks.length ? <div className="py-6 text-center text-xs text-slate-500">暂无成分股数据</div> : null}
        </div>
      </div>
    </div>
  );
};

const HeatTradeDatePicker: React.FC<{
  value: string;
  minDate?: string | null;
  maxDate?: string | null;
  latestDate?: string | null;
  dateMetaByDate?: Record<string, FineHeatTradeDateItem>;
  onChange: (value: string) => void;
}> = ({ value, minDate, maxDate, latestDate, dateMetaByDate = {}, onChange }) => {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState<Date>(() => parseDateOnly(value || latestDate || maxDate) || new Date());
  const pickerRef = React.useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const next = parseDateOnly(value || latestDate || maxDate);
    if (next) setViewMonth(new Date(next.getFullYear(), next.getMonth(), 1));
  }, [value, latestDate, maxDate]);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (pickerRef.current && target && !pickerRef.current.contains(target)) setOpen(false);
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

  const pickDate = (day: number) => {
    const dateText = formatDateOnly(new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day));
    const meta = dateMetaByDate[dateText];
    if (!meta || !isDateWithin(dateText, minDate, maxDate) || meta.selectable === false) return;
    onChange(dateText);
    setOpen(false);
  };

  const jumpLatest = () => {
    const target = latestDate || maxDate || '';
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
        aria-label="选择热点交易日"
      >
        <span className="inline-flex min-w-0 items-center gap-2">
          <Calendar className="h-4 w-4 shrink-0 text-slate-500" />
          <span className="truncate">{value || '选择日期'}</span>
        </span>
      </button>
      {open ? (
        <div className="absolute left-0 z-[100] mt-2 w-[284px] rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-2xl">
          <div className="mb-3 flex items-center justify-between">
            <button type="button" onClick={() => setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-800" aria-label="上个月">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="text-sm font-semibold text-white">{monthLabel(viewMonth)}</div>
            <button type="button" onClick={() => setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-800" aria-label="下个月">
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-[11px] text-slate-500">
            {['日', '一', '二', '三', '四', '五', '六'].map((day) => <div key={day} className="py-1">{day}</div>)}
            {cells.map((day, index) => {
              if (!day) return <div key={`blank-${index}`} className="h-8" />;
              const dateText = formatDateOnly(new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day));
              const meta = dateMetaByDate[dateText];
              const disabled = !meta || !isDateWithin(dateText, minDate, maxDate) || meta.selectable === false;
              const active = value === dateText;
              return (
                <button
                  key={dateText}
                  type="button"
                  onClick={() => pickDate(day)}
                  disabled={disabled}
                  title={meta?.has_cache ? '已有热点缓存' : meta ? '有底层数据，需刷新生成热点缓存' : '无交易数据'}
                  className={`relative h-8 rounded-lg text-xs font-medium transition-colors ${
                    active
                      ? 'bg-sky-600 text-white'
                      : disabled
                        ? 'cursor-not-allowed text-slate-700 line-through'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  {day}
                  {!disabled && meta?.has_cache ? <span className="absolute bottom-0.5 left-1/2 h-0.5 w-3 -translate-x-1/2 rounded-full bg-emerald-400/80" /> : null}
                  {!disabled && !meta?.has_cache ? <span className="absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-amber-400/80" /> : null}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3 text-[11px]">
            <span className="text-slate-500">绿线=已有热点缓存，黄点=可生成</span>
            <button type="button" onClick={jumpLatest} className="rounded-lg border border-slate-700 px-2 py-1 text-slate-200 hover:bg-slate-800">最新</button>
          </div>
        </div>
      ) : null}
    </div>
  );
};

const MarketHeatPage: React.FC = () => {
  const [fineDashboard, setFineDashboard] = useState<FineHeatDashboard | null>(null);
  const [fineForecast, setFineForecast] = useState<FineHeatForecast | null>(null);
  const [fineDates, setFineDates] = useState<FineHeatDatesData | null>(null);
  const [heatDate, setHeatDate] = useState<string>('');
  const [selectedFineId, setSelectedFineId] = useState<string>('');
  const [fineStockDetail, setFineStockDetail] = useState<FineHeatThemeStockDetail | null>(null);
  const [fineStockLoading, setFineStockLoading] = useState(false);
  const [selectedFineStock, setSelectedFineStock] = useState<FineHeatStock | null>(null);
  const [fineLeftHeight, setFineLeftHeight] = useState(0);
  const [loading, setLoading] = useState(false);
  const [refreshingFine, setRefreshingFine] = useState(false);
  const [error, setError] = useState('');
  const fineLeftRef = React.useRef<HTMLDivElement | null>(null);

  const refreshFineDates = async () => {
    const data = await fetchFineHeatDates(260);
    if (data) setFineDates(data);
    return data;
  };

  const load = async (dateOverride?: string) => {
    setLoading(true);
    setError('');
    const targetDate = dateOverride || heatDate || undefined;
    try {
      const fineData = await fetchFineHeatDashboard(63, targetDate, 18);
      if (fineData) {
        setFineDashboard(fineData);
        setHeatDate(fineData.meta.trade_date);
        fetchFineThemeForecast(fineData.meta.trade_date, 'future_mainline_extension_5d', 5).then(setFineForecast);
        setSelectedFineId((prev) => {
          const all = [
            ...(fineData.pool || []),
            ...(fineData.cards?.today_strong || []),
            ...(fineData.cards?.new_hot || []),
            ...(fineData.cards?.returning || []),
            ...(fineData.cards?.warming || []),
            ...(fineData.cards?.mainline || []),
            ...(fineData.cards?.fading || []),
          ];
          const ids = new Set(all.map((item) => item.id));
          return prev && ids.has(prev) ? prev : fineData.pool?.[0]?.id || fineData.cards?.returning?.[0]?.id || fineData.cards?.new_hot?.[0]?.id || '';
        });
      } else {
        setFineDashboard(null);
        setFineForecast(null);
        setSelectedFineId('');
        setError((prev) => prev || `所选日 ${targetDate || '最新'} 还没有细颗粒热点缓存，请点击“刷新最新数据”生成`);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      const dates = await fetchFineHeatDates(260);
      if (cancelled) return;
      if (dates) setFineDates(dates);
      const initialDate = dates?.latest_cached_date || dates?.latest_trade_date || '';
      if (initialDate) setHeatDate(initialDate);
      await load(initialDate || undefined);
    };
    init();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRefreshLatestFine = async () => {
    const target = fineDates?.latest_trade_date || heatDate || undefined;
    setRefreshingFine(true);
    setLoading(true);
    setError('');
    try {
      const result = await refreshFineHeatDashboard(target, 63, true);
      if (!result) {
        setError('细颗粒热点缓存刷新失败，请检查后端日志');
        return;
      }
      const dates = await refreshFineDates();
      const nextDate = result.trade_date || dates?.latest_cached_date || target || '';
      if (nextDate) setHeatDate(nextDate);
      await load(nextDate || undefined);
    } finally {
      setRefreshingFine(false);
      setLoading(false);
    }
  };

  const selectedFine = useMemo(() => {
    if (!fineDashboard) return null;
    const all = [
      ...(fineDashboard.pool || []),
      ...(fineDashboard.cards?.today_strong || []),
      ...(fineDashboard.cards?.new_hot || []),
      ...(fineDashboard.cards?.returning || []),
      ...(fineDashboard.cards?.warming || []),
      ...(fineDashboard.cards?.mainline || []),
      ...(fineDashboard.cards?.fading || []),
    ];
    const found = all.find((item) => item.id === selectedFineId);
    if (found) return found;
    const forecastItem = fineForecast?.items?.find((item) => item.theme_id === selectedFineId);
    if (forecastItem) {
      return {
        id: forecastItem.theme_id,
        name: forecastItem.theme_name,
        sector_type: forecastItem.sector_type,
        member_count: 0,
        lifecycle: '主线延续预警',
        display_score: forecastItem.probability,
        rank_today: forecastItem.current_rank,
        rank_delta: 0,
        hot_score: forecastItem.current_hot_score,
        pct_change: 0,
        hot_change_5d: 0,
        front_hits_5: 0,
        hot_hits_5: 0,
        watch_hits_5: 0,
        front_hits_20: 0,
        hot_hits_20: 0,
        watch_hits_20: 0,
        limit_up_count: 0,
        touch_limit_up_count: 0,
        broken_limit_up_count: 0,
        evidence: [`模型概率 ${fmt(forecastItem.probability_pct, 1)}%`, `预警排名 #${forecastItem.score_rank}`],
        reason: `模型预测未来${fineForecast?.meta.horizon_days || 5}日主线延续`,
        trend: [],
      } as FineHeatTheme;
    }
    return fineDashboard.pool?.[0] || null;
  }, [fineDashboard, fineForecast, selectedFineId]);

  useEffect(() => {
    setSelectedFineStock(null);
    setFineStockDetail(null);
  }, [selectedFineId]);

  useEffect(() => {
    if (!selectedFine?.id) {
      setFineStockLoading(false);
      return;
    }
    let cancelled = false;
    const loadStockDetail = async () => {
      setFineStockLoading(true);
      let detail = await fetchFineThemeStockDetail(selectedFine.id, fineDashboard?.meta?.trade_date, 45);
      const hasHistory = (detail?.stocks || []).some((stock) => (stock.history || []).length >= 2);
      if (!hasHistory && selectedFine.stocks?.length) {
        const fallbackStocks = await hydrateStocksWithHistoryFallback(selectedFine.stocks, 45);
        detail = {
          theme_id: selectedFine.id,
          trade_date: fineDashboard?.meta?.trade_date || '',
          stock_summary: selectedFine.stock_summary,
          stock_groups: selectedFine.stock_groups,
          stocks: fallbackStocks,
        };
      }
      if (!cancelled) {
        setFineStockDetail(detail);
        setFineStockLoading(false);
      }
    };
    loadStockDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedFine, fineDashboard?.meta?.trade_date]);

  const selectedFineWithStocks = useMemo<FineHeatTheme | null>(() => {
    if (!selectedFine) return null;
    if (!fineStockDetail || fineStockDetail.theme_id !== selectedFine.id) return selectedFine;
    return {
      ...selectedFine,
      stock_summary: fineStockDetail.stock_summary || selectedFine.stock_summary,
      stock_groups: fineStockDetail.stock_groups || selectedFine.stock_groups,
      stocks: fineStockDetail.stocks || selectedFine.stocks,
    };
  }, [fineStockDetail, selectedFine]);

  const activeFineStock = useMemo(() => {
    if (!selectedFineStock) return null;
    const latest = (selectedFineWithStocks?.stocks || []).find((stock) => stock.symbol === selectedFineStock.symbol);
    return latest || selectedFineStock;
  }, [selectedFineStock, selectedFineWithStocks]);

  const fineDateMetaByDate = useMemo(() => {
    const out: Record<string, FineHeatTradeDateItem> = {};
    (fineDates?.dates || []).forEach((item) => {
      out[item.date] = item;
    });
    return out;
  }, [fineDates]);

  const latestFineNeedsRefresh = Boolean(
    fineDates?.latest_trade_date
    && fineDashboard?.meta?.trade_date
    && fineDates.latest_trade_date > fineDashboard.meta.trade_date
  );

  useEffect(() => {
    const node = fineLeftRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const update = () => setFineLeftHeight(Math.round(node.getBoundingClientRect().height));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [activeFineStock, fineDashboard]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />返回主页面
          </a>
          <div className="mr-2 flex items-center gap-2 text-base font-bold text-white"><Flame className="h-5 w-5 text-amber-400" />市场热点温度计</div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">v{APP_VERSION}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">当前 {fineDashboard?.meta?.trade_date || heatDate || '--'}</span>
          <HeatTradeDatePicker
            value={heatDate}
            minDate={fineDates?.min_date}
            maxDate={fineDates?.max_date}
            latestDate={fineDates?.latest_trade_date}
            dateMetaByDate={fineDateMetaByDate}
            onChange={setHeatDate}
          />
          <button type="button" onClick={() => load(heatDate)} disabled={loading || !heatDate} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:opacity-60">
            查询
          </button>
          <button type="button" onClick={handleRefreshLatestFine} disabled={loading || refreshingFine} className="inline-flex h-9 items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 text-sm font-medium text-sky-100 hover:border-sky-400 disabled:opacity-60">
            <RefreshCw className={`h-4 w-4 ${refreshingFine ? 'animate-spin' : ''}`} />{refreshingFine ? '刷新中' : '刷新最新数据'}
          </button>
          <a href="/market-heat/low-position-samples" className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500">
            热点低位样本
          </a>
          {latestFineNeedsRefresh ? <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">底层最新 {fineDates?.latest_trade_date}，热点缓存待刷新</span> : null}
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        {error ? <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}

        <div className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-950 to-[#08111f] p-2.5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-base font-bold text-white"><Crosshair className="h-5 w-5 text-sky-300" />市场主线情报看板</div>
              <div className="mt-1 text-xs text-slate-500">细颗粒主题 {fineDashboard?.meta.fine_theme_count ?? '--'} 个；Top{fineDashboard?.meta.front_band ?? 5} 当日最强 / Top{fineDashboard?.meta.orange_band ?? 10} 前排热点 / Top{fineDashboard?.meta.hot_band ?? 15} 热区 / Top{fineDashboard?.meta.watch_band ?? 30} 观察边界。</div>
            </div>
            <div className={`text-right text-xs ${mono} text-slate-500`}>
              <div>{fineDashboard?.meta.start_date || '--'} → {fineDashboard?.meta.end_date || '--'}</div>
              <div>source: fine cache + limit state</div>
            </div>
          </div>
          <div className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_470px]">
            <div ref={fineLeftRef}>
              {activeFineStock ? (
                <StockInlineDetailPanel stock={activeFineStock} theme={selectedFineWithStocks} onClose={() => setSelectedFineStock(null)} />
              ) : (
                <>
                  <ForecastStrip
                    forecast={fineForecast}
                    dashboard={fineDashboard}
                    selectedId={selectedFine?.id || ''}
                    onSelect={(item) => setSelectedFineId(item.theme_id)}
                  />
                  <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
                    <HotspotPool
                      title="今日最强"
                      subtitle="今日排名 Top5"
                      icon={<Flame className="h-4 w-4 text-red-300" />}
                      items={fineDashboard?.cards?.today_strong || []}
                      dashboard={fineDashboard}
                      selectedId={selectedFine?.id || ''}
                      onSelect={setSelectedFineId}
                      tone="border-red-500/20"
                    />
                    <HotspotPool
                      title="首次新热"
                      subtitle="近20日少热，今天进Top15"
                      icon={<Zap className="h-4 w-4 text-red-300" />}
                      items={fineDashboard?.cards?.new_hot || []}
                      dashboard={fineDashboard}
                      selectedId={selectedFine?.id || ''}
                      onSelect={setSelectedFineId}
                      tone="border-red-500/20"
                    />
                    <HotspotPool
                      title="主线再加速"
                      subtitle="近20日反复活跃，今天进Top10"
                      icon={<RefreshCw className="h-4 w-4 text-orange-300" />}
                      items={fineDashboard?.cards?.returning || []}
                      dashboard={fineDashboard}
                      selectedId={selectedFine?.id || ''}
                      onSelect={setSelectedFineId}
                      tone="border-orange-500/20"
                    />
                    <HotspotPool
                      title="持续升温"
                      subtitle="Top6-Top30，近5日明显抬升"
                      icon={<TrendingUp className="h-4 w-4 text-amber-300" />}
                      items={fineDashboard?.cards?.warming || []}
                      dashboard={fineDashboard}
                      selectedId={selectedFine?.id || ''}
                      onSelect={setSelectedFineId}
                      tone="border-amber-500/20"
                    />
                    <HotspotPool
                      title="持续主线"
                      subtitle="仍在Top30，近20日反复热"
                      icon={<Activity className="h-4 w-4 text-violet-300" />}
                      items={fineDashboard?.cards?.mainline || []}
                      dashboard={fineDashboard}
                      selectedId={selectedFine?.id || ''}
                      onSelect={setSelectedFineId}
                      tone="border-violet-500/20"
                    />
                    <HotspotPool
                      title="退潮观察"
                      subtitle="跌出Top30，近期从前排掉队"
                      icon={<ShieldAlert className="h-4 w-4 text-emerald-300" />}
                      items={fineDashboard?.cards?.fading || []}
                      dashboard={fineDashboard}
                      selectedId={selectedFine?.id || ''}
                      onSelect={setSelectedFineId}
                      tone="border-emerald-500/20"
                    />
                  </div>
                </>
              )}
              {!fineDashboard ? <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/40 p-6 text-center text-sm text-slate-500">细颗粒热点看板加载中...</div> : null}
            </div>
            <FineThemeDetail
              item={selectedFineWithStocks}
              dashboard={fineDashboard}
              activeStockSymbol={activeFineStock?.symbol}
              stockLoading={fineStockLoading}
              panelHeight={fineLeftHeight}
              onStockSelect={setSelectedFineStock}
            />
          </div>
        </div>

      </div>
    </div>
  );
};

export default MarketHeatPage;
