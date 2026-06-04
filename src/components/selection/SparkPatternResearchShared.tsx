import React, { useEffect, useMemo, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Layers3 } from 'lucide-react';

import { Metric } from '../common/ResearchCard';

echarts.use([
  BarChart,
  CandlestickChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export type PatternBar = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  total_amount: number;
  total_volume: number;
  l2_main_net_amount: number;
  l2_super_net_amount: number;
  return_from_first_signal_pct?: number | null;
  is_limit_up_close?: number;
};

export type PatternSignal = {
  rank: number;
  signal_date: string;
  entry_date: string;
  hard_exit_date: string;
  entry_open: number;
  final_score: number;
  max_runup_22d_pct: number;
  max_drawdown_22d_pct: number;
  close_return_22d_pct: number;
  mdd_to_mfe_pct: number;
  days_to_mfe: number;
};

export type PatternItem = {
  id: string;
  tier: 'top1' | 'top3';
  symbol: string;
  name: string;
  signal_count: number;
  first_signal_date: string;
  last_signal_date: string;
  last_hard_exit_date: string;
  max_final_score: number;
  avg_final_score: number;
  best_max_runup_22d_pct: number;
  avg_max_runup_22d_pct: number;
  avg_close_return_22d_pct: number;
  worst_max_drawdown_22d_pct: number;
  signals: PatternSignal[];
  window: {
    actual_bars: number;
    start_date: string;
    end_date: string;
  };
  bars: PatternBar[];
};

export type PatternSection = {
  id: string;
  title: string;
  description: string;
  source_signal_count: number;
  stock_count: number;
  items: PatternItem[];
};

export type PatternPayload = {
  meta: {
    title: string;
    top1_signal_count: number;
    top1_stock_count: number;
    top3_raw_signal_count: number;
    top3_raw_stock_count: number;
    top3_signal_count: number;
    top3_stock_count: number;
    window_rule: string;
    source?: string;
  };
  sections: PatternSection[];
};

export const fmtNum = (value?: number | null, digits = 2) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(digits);
};

export const fmtPct = (value?: number | null, digits = 2) => `${fmtNum(value, digits)}%`;

export const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  const sign = num < 0 ? '-' : '';
  const abs = Math.abs(num);
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
  return `${sign}${abs.toFixed(0)}`;
};

export const fmtVol = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const abs = Math.abs(Number(value));
  if (abs >= 1e8) return `${(abs / 1e8).toFixed(2)}亿股`;
  if (abs >= 1e4) return `${(abs / 1e4).toFixed(1)}万股`;
  return `${abs.toFixed(0)}股`;
};

export const pctTone = (value?: number | null) => Number(value || 0) >= 0 ? 'text-red-200' : 'text-emerald-200';

export const pathLabel = (item: PatternItem) => {
  if (item.signal_count >= 3) return '多次信号';
  if (item.best_max_runup_22d_pct >= 70) return '强趋势大涨';
  if (item.best_max_runup_22d_pct < 10 && item.avg_close_return_22d_pct < 0) return '弱势失败';
  if (item.avg_close_return_22d_pct < 0 && item.best_max_runup_22d_pct >= 15) return '先冲后回落';
  return '常规冲高';
};

export const usePatternPayload = (dataUrl: string) => {
  const [payload, setPayload] = useState<PatternPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setPayload(null);
    fetch(dataUrl)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: PatternPayload) => {
        if (cancelled) return;
        setPayload(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || '形态研究数据读取失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dataUrl]);

  return { payload, loading, error };
};

export const summarizeItems = (items: PatternItem[]) => {
  const count = items.length;
  if (!count) {
    return {
      avgRunup: 0,
      avgCloseReturn: 0,
    };
  }
  return {
    avgRunup: items.reduce((sum, item) => sum + item.avg_max_runup_22d_pct, 0) / count,
    avgCloseReturn: items.reduce((sum, item) => sum + item.avg_close_return_22d_pct, 0) / count,
  };
};

export const buildPatternOption = (item: PatternItem) => {
  const bars = item.bars || [];
  const dates = bars.map((bar) => bar.trade_date.slice(5));
  const candle = bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]);
  const volume = bars.map((bar) => Number(bar.total_volume || 0) / 100000000);
  const l2MainNet = bars.map((bar) => Number(bar.l2_main_net_amount || 0) / 100000000);
  const l2SuperNet = bars.map((bar) => Number(bar.l2_super_net_amount || 0) / 100000000);
  const dateIndex = new Map(bars.map((bar, idx) => [bar.trade_date, idx]));
  const signalColor = item.tier === 'top1' ? '#38bdf8' : '#a78bfa';
  const markLines = item.signals.flatMap((signal, idx) => {
    const signalIndex = dateIndex.get(signal.signal_date);
    const entryIndex = dateIndex.get(signal.entry_date);
    const exitIndex = dateIndex.get(signal.hard_exit_date);
    return [
      signalIndex != null ? { xAxis: signalIndex, name: `信${idx + 1}`, lineStyle: { color: signalColor, width: 1.2 } } : null,
      entryIndex != null ? { xAxis: entryIndex, name: `买${idx + 1}`, lineStyle: { color: '#f87171', width: 1.2 } } : null,
      exitIndex != null ? { xAxis: exitIndex, name: `退${idx + 1}`, lineStyle: { color: '#fbbf24', width: 1.2 } } : null,
    ].filter(Boolean);
  });

  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15,23,42,0.96)',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter: (params: any[]) => {
        const idx = params?.[0]?.dataIndex ?? 0;
        const bar = bars[idx];
        if (!bar) return '';
        return [
          `<b>${bar.trade_date}</b>`,
          `开 ${fmtNum(bar.open)} 高 ${fmtNum(bar.high)} 低 ${fmtNum(bar.low)} 收 ${fmtNum(bar.close)}`,
          `相对首信号 ${fmtPct(bar.return_from_first_signal_pct)}`,
          `成交量 ${fmtVol(bar.total_volume)}`,
          `成交额 ${fmtAmt(bar.total_amount)}`,
          `L2主力净 ${fmtAmt(bar.l2_main_net_amount)}`,
          `L2超大净 ${fmtAmt(bar.l2_super_net_amount)}`,
          ...item.signals
            .map((signal, signalIdx) => signal.signal_date === bar.trade_date ? `信号${signalIdx + 1}：Top${signal.rank} 分${fmtNum(signal.final_score, 2)}` : '')
            .filter(Boolean),
          ...item.signals
            .map((signal, signalIdx) => signal.entry_date === bar.trade_date ? `买入${signalIdx + 1}：次日开盘 ${fmtNum(signal.entry_open, 2)}` : '')
            .filter(Boolean),
          ...item.signals
            .map((signal, signalIdx) => signal.hard_exit_date === bar.trade_date ? `退出${signalIdx + 1}：22日硬退出` : '')
            .filter(Boolean),
          bar.is_limit_up_close ? '涨停收盘' : '',
        ].filter(Boolean).join('<br/>');
      },
    },
    legend: {
      top: 0,
      left: 8,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: '#94a3b8', fontSize: 10 },
    },
    grid: [
      { left: 46, right: 38, top: 30, height: 205 },
      { left: 46, right: 38, top: 260, height: 86 },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLabel: { color: '#94a3b8', fontSize: 10 },
        axisLine: { lineStyle: { color: '#334155' } },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: true,
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#334155' } },
      },
    ],
    yAxis: [
      {
        type: 'value',
        scale: true,
        axisLabel: { color: '#fbbf24', fontSize: 10 },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      {
        type: 'value',
        gridIndex: 1,
        scale: true,
        name: '量',
        axisLabel: { color: '#64748b', fontSize: 10, formatter: (v: number) => `${fmtNum(v, 1)}亿股` },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      {
        type: 'value',
        gridIndex: 1,
        scale: true,
        position: 'right',
        name: '净',
        axisLabel: { color: '#60a5fa', fontSize: 10, formatter: (v: number) => `${fmtNum(v, 1)}亿` },
        splitLine: { show: false },
      },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 }],
    series: [
      {
        name: '日K',
        type: 'candlestick',
        data: candle,
        itemStyle: {
          color: '#ef4444',
          color0: '#22c55e',
          borderColor: '#ef4444',
          borderColor0: '#22c55e',
        },
        markLine: {
          symbol: 'none',
          label: { color: '#cbd5e1', fontSize: 10, formatter: '{b}' },
          lineStyle: { type: 'dashed' },
          data: markLines,
        },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volume,
        itemStyle: { color: 'rgba(148,163,184,0.32)' },
        barMaxWidth: 12,
      },
      {
        name: 'L2主力净',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 2,
        data: l2MainNet,
        itemStyle: { color: (params: any) => Number(params.value || 0) >= 0 ? '#ef4444' : '#22c55e' },
        barMaxWidth: 10,
      },
      {
        name: 'L2超大净',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 2,
        data: l2SuperNet,
        showSymbol: false,
        lineStyle: { color: '#a78bfa', width: 1.4 },
      },
    ],
  };
};

export const PatternCard: React.FC<{ item: PatternItem }> = ({ item }) => {
  const option = useMemo(() => buildPatternOption(item), [item]);
  const tierClass = item.tier === 'top1'
    ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
    : 'border-violet-500/40 bg-violet-500/10 text-violet-200';
  const tierLabel = item.tier === 'top1' ? 'Top1' : 'Top3';
  return (
    <section className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/70 shadow-lg">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-white">{item.name}</span>
            <span className={`rounded border px-2 py-0.5 text-[11px] ${tierClass}`}>{tierLabel}</span>
            <span className="rounded border border-slate-600/60 bg-slate-950/50 px-2 py-0.5 text-[11px] text-slate-300">{pathLabel(item)}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {item.symbol} · {item.signal_count} 次信号 · {item.first_signal_date} 至 {item.last_signal_date} · 末次退出 {item.last_hard_exit_date}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-500">最高分</div>
          <div className="font-mono text-sm font-semibold text-slate-100">{fmtNum(item.max_final_score, 2)}</div>
        </div>
      </div>
      <div className="grid gap-2 px-4 pt-3 md:grid-cols-5">
        <Metric label="信号次数" value={`${item.signal_count} 次`} className="rounded-lg border border-slate-800 bg-slate-950/45 p-2" />
        <Metric label="最佳22日冲高" value={fmtPct(item.best_max_runup_22d_pct)} tone="text-red-200" className="rounded-lg border border-slate-800 bg-slate-950/45 p-2" />
        <Metric label="平均22日冲高" value={fmtPct(item.avg_max_runup_22d_pct)} tone="text-red-200" className="rounded-lg border border-slate-800 bg-slate-950/45 p-2" />
        <Metric label="平均22日收盘" value={fmtPct(item.avg_close_return_22d_pct)} tone={pctTone(item.avg_close_return_22d_pct)} className="rounded-lg border border-slate-800 bg-slate-950/45 p-2" />
        <Metric label="最差最大回撤" value={fmtPct(item.worst_max_drawdown_22d_pct)} tone="text-emerald-200" className="rounded-lg border border-slate-800 bg-slate-950/45 p-2" />
      </div>
      <div className="mx-4 mt-2 flex flex-wrap gap-1.5 text-[11px] text-slate-400">
        {item.signals.map((signal, idx) => (
          <span key={`${signal.signal_date}_${idx}`} className="rounded border border-slate-800 bg-slate-950/45 px-2 py-1">
            信{idx + 1} {signal.signal_date} / 买 {signal.entry_date} / 退 {signal.hard_exit_date}
          </span>
        ))}
      </div>
      <div className="px-2 pb-3 pt-2">
        <ReactEChartsCore echarts={echarts} option={option} style={{ width: '100%', height: 365 }} />
      </div>
    </section>
  );
};

export const PatternSectionBlock: React.FC<{ section: PatternSection }> = ({ section }) => (
  <section className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <Layers3 className="h-4 w-4 text-sky-300" />
          {section.title}
        </div>
        <div className="mt-1 text-xs text-slate-500">{section.description}</div>
      </div>
      <div className="text-xs text-slate-400">
        合并后 {section.stock_count} 只 · 原始信号 {section.source_signal_count} 次
      </div>
    </div>
    <div className="grid gap-4 xl:grid-cols-2">
      {section.items.map((item) => <PatternCard key={item.id} item={item} />)}
    </div>
  </section>
);
