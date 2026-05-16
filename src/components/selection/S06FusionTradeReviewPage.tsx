import React, { useEffect, useMemo, useState } from 'react';
import { BarChart3, FileText, RefreshCw, Target, TrendingUp } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, MarkPointComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { HistoryMultiframeItem } from '../../types';
import { fetchSelectionHistoryMultiframe } from '../../services/selectionService';
import MarketTopHeader from '../common/MarketTopHeader';

echarts.use([
  BarChart,
  CandlestickChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  CanvasRenderer,
]);

interface S06Trade {
  trade_id?: string;
  fusion_strategy: string;
  strategy_description?: string;
  shell_label?: string;
  exit_shell?: string;
  mode?: string;
  trade_date: string;
  entry_date: string;
  exit_date: string;
  symbol: string;
  weight?: number;
  final_score?: number;
  score_22?: number | null;
  score_h5?: number | null;
  rank_22_pool?: number | null;
  rank_h5_full?: number | null;
  gross_entry_price?: number;
  gross_exit_price?: number;
  net_entry_price?: number;
  net_exit_price?: number;
  position_cash?: number;
  shares?: number;
  pnl_cash?: number;
  equity_after?: number;
  net_return_pct?: number;
  gross_return_pct?: number;
  max_runup_before_exit_pct?: number;
  max_drawdown_before_exit_pct?: number;
  holding_days?: number;
  exit_reason?: string;
}

interface S06SummaryRow {
  fusion_strategy: string;
  strategy_description?: string;
  shell_label?: string;
  exit_shell?: string;
  trades?: number;
  final_equity?: number;
  total_return_pct?: number;
  max_drawdown_pct?: number;
  win_rate?: number;
  avg_holding_days?: number;
  max_open_positions?: number;
  avg_cash_pct?: number;
}

interface S06Report {
  model_version: string;
  generated_from?: string;
  initial_capital?: number;
  config?: { start_date?: string; end_date?: string; validation_start?: string };
  data?: { signal_dates?: string[]; signal_days?: number; latest_date?: string; candidate_pool?: string };
  summary_rows: S06SummaryRow[];
  trades: S06Trade[];
}

const REPORT_URL = '/research/s06-fusion-h5-22-report.json';
const DEFAULT_STRATEGY = 'baseline_22_top1';
const DEFAULT_EXIT_SHELL = '22_hold_model_tp15_stop12';
const INITIAL_CAPITAL = 1000000;

const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  if (Math.abs(num) >= 1e8) return `${(num / 1e8).toFixed(2)}亿`;
  if (Math.abs(num) >= 1e4) return `${(num / 1e4).toFixed(1)}万`;
  return num.toFixed(0);
};
const fmtPrice = (value?: number | null) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(2));
const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const compactDate = (value?: string | null) => (value || '').slice(5, 10) || '--';
const toTs = (date: string) => new Date(`${date}T00:00:00`).getTime();
const addDays = (date: string, days: number) => {
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

const SectionCard: React.FC<{ title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }> = ({ title, icon, right, children }) => (
  <section className="rounded-2xl border border-slate-800 bg-slate-900/75 shadow-lg">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-3">
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
  <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 truncate text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const buildEquityRows = (trades: S06Trade[], initialCapital: number) => {
  const rows = trades
    .filter((trade) => trade.exit_date)
    .slice()
    .sort((a, b) => a.exit_date.localeCompare(b.exit_date) || a.entry_date.localeCompare(b.entry_date));
  const firstDate = rows[0]?.trade_date || rows[0]?.entry_date || '';
  const equityRows = firstDate ? [{ date: firstDate, equity: initialCapital, pnl: 0 }] : [];
  rows.forEach((trade) => {
    const equity = Number(trade.equity_after);
    if (Number.isFinite(equity)) {
      equityRows.push({ date: trade.exit_date, equity, pnl: Number(trade.pnl_cash || 0) });
    }
  });
  return equityRows;
};

const buildEquityOption = (rows: Array<{ date: string; equity: number; pnl: number }>) => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15, 23, 42, 0.95)',
    borderColor: '#334155',
    textStyle: { color: '#e2e8f0' },
    formatter: (params: any[]) => {
      const item = params?.[0];
      const row = rows[item?.dataIndex || 0];
      if (!row) return '';
      return `<div style="font-size:12px;font-weight:700;margin-bottom:4px;">${row.date}</div>
        <div style="display:flex;gap:16px;justify-content:space-between;"><span>账户金额</span><b>${fmtAmt(row.equity)}</b></div>
        <div style="display:flex;gap:16px;justify-content:space-between;"><span>单笔盈亏</span><b>${fmtAmt(row.pnl)}</b></div>`;
    },
  },
  grid: { left: 48, right: 24, top: 24, bottom: 42 },
  xAxis: { type: 'category', data: rows.map((row) => row.date), axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
  yAxis: { type: 'value', scale: true, axisLabel: { color: '#60a5fa', formatter: (value: number) => fmtAmt(value) }, splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } } },
  dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 8, showDetail: false, borderColor: '#334155', fillerColor: 'rgba(14,165,233,0.18)' }],
  series: [{
    name: '账户金额',
    type: 'line',
    data: rows.map((row) => row.equity),
    showSymbol: rows.length < 30,
    symbolSize: 6,
    lineStyle: { color: '#38bdf8', width: 2.4 },
    itemStyle: { color: '#38bdf8' },
    areaStyle: { color: 'rgba(56,189,248,0.09)' },
  }],
});

const buildTradeChartOption = (trade: S06Trade, rows: HistoryMultiframeItem[]) => {
  const categories = rows.map((row) => row.trade_date || row.datetime);
  const candleData = rows.map((row) => [
    row.open ?? row.close ?? 0,
    row.close ?? 0,
    row.low ?? row.close ?? 0,
    row.high ?? row.close ?? 0,
  ]);
  const amountData = rows.map((row) => Number(row.total_amount || 0));
  const indexOfDate = (date?: string) => {
    if (!date) return -1;
    const exact = rows.findIndex((row) => row.trade_date === date);
    if (exact >= 0) return exact;
    return rows.findIndex((row) => row.trade_date > date);
  };
  const signalIndex = indexOfDate(trade.trade_date);
  const entryIndex = indexOfDate(trade.entry_date);
  const exitIndex = indexOfDate(trade.exit_date);
  const markerData = [
    signalIndex >= 0 ? { name: '信号日', coord: [signalIndex, rows[signalIndex]?.high ?? trade.gross_entry_price], value: '信号', itemStyle: { color: '#a78bfa' }, label: { color: '#ddd6fe' } } : null,
    entryIndex >= 0 ? { name: '买入日', coord: [entryIndex, trade.gross_entry_price ?? rows[entryIndex]?.close], value: `买 ${fmtPrice(trade.gross_entry_price)}`, itemStyle: { color: '#ef4444' }, label: { color: '#fecaca' } } : null,
    exitIndex >= 0 ? { name: '卖出日', coord: [exitIndex, trade.gross_exit_price ?? rows[exitIndex]?.close], value: `卖 ${fmtPrice(trade.gross_exit_price)}`, itemStyle: { color: '#22c55e' }, label: { color: '#bbf7d0' } } : null,
  ].filter(Boolean);

  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
      formatter: (params: any[]) => {
        const index = params?.[0]?.dataIndex ?? 0;
        const row = rows[index];
        if (!row) return '';
        const markerText = [
          row.trade_date === trade.trade_date ? '信号日' : '',
          row.trade_date === trade.entry_date ? `买入 ${fmtPrice(trade.gross_entry_price)} / ${fmtAmt(trade.position_cash)}` : '',
          row.trade_date === trade.exit_date ? `卖出 ${fmtPrice(trade.gross_exit_price)} / ${fmtAmt((trade.shares || 0) * (trade.gross_exit_price || 0))}` : '',
        ].filter(Boolean).join('<br/>');
        return `<div style="font-size:12px;font-weight:700;margin-bottom:4px;">${row.trade_date}</div>
          <div>O:${fmtPrice(row.open)} H:${fmtPrice(row.high)} L:${fmtPrice(row.low)} C:${fmtPrice(row.close)}</div>
          <div>成交额 ${fmtAmt(row.total_amount)}</div>
          ${markerText ? `<div style="margin-top:4px;color:#f8fafc;">${markerText}</div>` : ''}`;
      },
    },
    grid: [
      { left: 48, right: 24, top: 28, height: 210 },
      { left: 48, right: 24, top: 260, height: 56 },
    ],
    xAxis: [
      { type: 'category', data: categories, boundaryGap: true, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#64748b', fontSize: 10, formatter: compactDate } },
      { type: 'category', gridIndex: 1, data: categories, boundaryGap: true, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { show: false } },
    ],
    yAxis: [
      { type: 'value', scale: true, axisLabel: { color: '#fbbf24', formatter: (value: number) => value.toFixed(2) }, splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } } },
      { type: 'value', gridIndex: 1, axisLabel: { color: '#64748b', formatter: (value: number) => fmtAmt(value) }, splitLine: { show: false } },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: candleData,
        itemStyle: { color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' },
        markPoint: {
          symbolSize: 58,
          label: { formatter: '{c}', fontSize: 10, fontWeight: 700 },
          data: markerData,
        },
        markLine: {
          silent: true,
          symbol: ['none', 'none'],
          lineStyle: { type: 'dashed', width: 1 },
          label: { color: '#cbd5e1', fontSize: 10 },
          data: [
            { yAxis: trade.gross_entry_price, name: '买入价', lineStyle: { color: '#ef4444' }, label: { formatter: `买入价 ${fmtPrice(trade.gross_entry_price)}` } },
            { yAxis: trade.gross_exit_price, name: '卖出价', lineStyle: { color: '#22c55e' }, label: { formatter: `卖出价 ${fmtPrice(trade.gross_exit_price)}` } },
          ],
        },
      },
      { name: '成交额', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: amountData, itemStyle: { color: 'rgba(148,163,184,0.26)' }, barMaxWidth: 16 },
    ],
  };
};

const TradeChartCard: React.FC<{ trade: S06Trade; index: number; active: boolean }> = ({ trade, index, active }) => {
  const [rows, setRows] = useState<HistoryMultiframeItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setLoading(true);
    fetchSelectionHistoryMultiframe(trade.symbol, {
      granularity: '1d',
      startDate: addDays(trade.trade_date, -5),
      endDate: addDays(trade.exit_date || trade.entry_date, 5),
      includeTodayPreview: false,
    }).then((items) => {
      if (!cancelled) setRows(items);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [active, trade.entry_date, trade.exit_date, trade.symbol, trade.trade_date]);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-3">
      <div className="mb-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-white">#{index + 1} {trade.symbol}</div>
            <span className={`rounded-full px-2 py-0.5 text-[11px] ${Number(trade.pnl_cash || 0) >= 0 ? 'bg-red-500/15 text-red-200' : 'bg-emerald-500/15 text-emerald-200'}`}>{fmtPct(trade.net_return_pct)}</span>
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">{trade.exit_reason || '--'}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">
            信号 {trade.trade_date} / 买入 {trade.entry_date} @ {fmtPrice(trade.gross_entry_price)} / 卖出 {trade.exit_date} @ {fmtPrice(trade.gross_exit_price)}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Metric label="买入金额" value={fmtAmt(trade.position_cash)} />
          <Metric label="卖出金额" value={fmtAmt((trade.shares || 0) * (trade.gross_exit_price || 0))} />
        </div>
      </div>
      {loading ? (
        <div className="flex h-[340px] items-center justify-center text-sm text-slate-500">K线加载中...</div>
      ) : rows.length ? (
        <ReactEChartsCore echarts={echarts} option={buildTradeChartOption(trade, rows)} style={{ width: '100%', height: 340 }} />
      ) : (
        <div className="flex h-[340px] items-center justify-center text-sm text-slate-500">暂无 {trade.symbol} 在交易窗口内的K线数据。</div>
      )}
    </div>
  );
};

const S06FusionTradeReviewPage: React.FC = () => {
  const [report, setReport] = useState<S06Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [strategy, setStrategy] = useState(DEFAULT_STRATEGY);
  const [exitShell, setExitShell] = useState(DEFAULT_EXIT_SHELL);
  const [visibleCount, setVisibleCount] = useState(12);

  useEffect(() => {
    let cancelled = false;
    fetch(REPORT_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((payload: S06Report) => {
        if (cancelled) return;
        setReport(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || '读取机会发现融合回测报告失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const strategyOptions = useMemo(() => {
    const map = new Map<string, string>();
    (report?.summary_rows || []).forEach((row) => map.set(row.fusion_strategy, row.strategy_description || row.fusion_strategy));
    return [...map.entries()];
  }, [report]);

  const exitShellOptions = useMemo(() => {
    const set = new Set<string>();
    (report?.summary_rows || []).filter((row) => row.fusion_strategy === strategy).forEach((row) => row.exit_shell && set.add(row.exit_shell));
    return [...set];
  }, [report, strategy]);

  useEffect(() => {
    if (!exitShellOptions.length) return;
    if (!exitShellOptions.includes(exitShell)) setExitShell(exitShellOptions[0]);
  }, [exitShell, exitShellOptions]);

  const selectedTrades = useMemo(() => {
    const rows = (report?.trades || []).filter((trade) => trade.fusion_strategy === strategy && trade.exit_shell === exitShell);
    return rows.sort((a, b) => a.trade_date.localeCompare(b.trade_date) || a.symbol.localeCompare(b.symbol));
  }, [report, strategy, exitShell]);

  const selectedSummary = useMemo(
    () => (report?.summary_rows || []).find((row) => row.fusion_strategy === strategy && row.exit_shell === exitShell) || null,
    [report, strategy, exitShell],
  );

  const equityRows = useMemo(() => buildEquityRows(selectedTrades, report?.initial_capital || INITIAL_CAPITAL), [report?.initial_capital, selectedTrades]);
  const visibleTrades = selectedTrades.slice(0, visibleCount);

  if (loading) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-slate-300">机会发现融合回测页面加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <MarketTopHeader
        routeHref="/selection-research"
        routeLabel="返回选股"
        routeTitle="返回选股研究台"
        secondaryRouteHref="/selection-ppo-report"
        secondaryRouteLabel="PPO复盘"
        secondaryRouteTitle="打开 PPO 回测复盘"
        searchValue=""
        isSearchFocused={false}
        searchResults={[]}
        searchHistory={[]}
        onSearchChange={() => {}}
        onSearchFocus={() => {}}
        onSearchBlur={() => {}}
        onSearchKeyDown={() => {}}
        onClearSearch={() => {}}
        onSelectSearchResult={() => {}}
        onSelectHistory={() => {}}
      />

      <main className="mx-auto max-w-[1600px] space-y-4 p-3 md:p-6">
        {error ? <div className="rounded-xl border border-red-800 bg-red-950/25 px-4 py-3 text-sm text-red-200">{error}</div> : null}

        <SectionCard title="机会发现 / 融合回测" icon={<Target className="h-4 w-4 text-cyan-300" />} right={
          <div className="text-xs text-slate-500">{report?.model_version || '--'} / {report?.data?.latest_date || '--'}</div>
        }>
          <div className="grid gap-3 md:grid-cols-6">
            <Metric label="初始资金" value={fmtAmt(report?.initial_capital || INITIAL_CAPITAL)} />
            <Metric label="期末金额" value={fmtAmt(selectedSummary?.final_equity)} tone={Number(selectedSummary?.total_return_pct || 0) >= 0 ? 'text-red-200' : 'text-emerald-200'} />
            <Metric label="总收益" value={fmtPct(selectedSummary?.total_return_pct)} tone={Number(selectedSummary?.total_return_pct || 0) >= 0 ? 'text-red-200' : 'text-emerald-200'} />
            <Metric label="最大回撤" value={fmtPct(selectedSummary?.max_drawdown_pct)} tone="text-emerald-200" />
            <Metric label="交易笔数" value={String(selectedSummary?.trades ?? selectedTrades.length)} />
            <Metric label="胜率" value={selectedSummary?.win_rate == null ? '--' : fmtPct(Number(selectedSummary.win_rate) * 100)} />
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
            <label className="text-xs text-slate-500">
              策略
              <select value={strategy} onChange={(event) => { setStrategy(event.target.value); setVisibleCount(12); }} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                {strategyOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="text-xs text-slate-500">
              交易壳
              <select value={exitShell} onChange={(event) => { setExitShell(event.target.value); setVisibleCount(12); }} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                {exitShellOptions.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          </div>
        </SectionCard>

        <SectionCard title="绝对账户金额曲线" icon={<BarChart3 className="h-4 w-4 text-sky-300" />}>
          <ReactEChartsCore echarts={echarts} option={buildEquityOption(equityRows)} style={{ width: '100%', height: 320 }} />
        </SectionCard>

        <SectionCard title="每笔交易K线" icon={<TrendingUp className="h-4 w-4 text-amber-300" />} right={
          <button type="button" onClick={() => setVisibleCount((value) => Math.min(selectedTrades.length, value + 8))} className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs text-slate-200 hover:bg-slate-800" disabled={visibleCount >= selectedTrades.length}>
            <RefreshCw className="h-3.5 w-3.5" />
            更多交易
          </button>
        }>
          <div className="grid gap-3 xl:grid-cols-2">
            {visibleTrades.map((trade, index) => (
              <TradeChartCard key={trade.trade_id || `${trade.symbol}-${trade.trade_date}-${index}`} trade={trade} index={index} active={index < visibleCount} />
            ))}
          </div>
        </SectionCard>

        <SectionCard title="交易明细" icon={<FileText className="h-4 w-4 text-violet-300" />}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-3">股票</th>
                  <th className="py-2 pr-3">信号日</th>
                  <th className="py-2 pr-3">买入日/价</th>
                  <th className="py-2 pr-3">卖出日/价</th>
                  <th className="py-2 pr-3">买入金额</th>
                  <th className="py-2 pr-3">卖出金额</th>
                  <th className="py-2 pr-3">盈亏</th>
                  <th className="py-2 pr-3">账户金额</th>
                  <th className="py-2 pr-3">评分</th>
                  <th className="py-2 pr-3">退出</th>
                </tr>
              </thead>
              <tbody>
                {selectedTrades.map((trade, index) => (
                  <tr key={trade.trade_id || `${trade.symbol}-${trade.trade_date}-${index}`} className="border-t border-slate-800/70">
                    <td className="py-2 pr-3 font-semibold text-white">{trade.symbol}</td>
                    <td className="py-2 pr-3 text-slate-400">{trade.trade_date}</td>
                    <td className="py-2 pr-3 text-slate-400">{trade.entry_date}<div className="text-[11px] text-red-200">@ {fmtPrice(trade.gross_entry_price)}</div></td>
                    <td className="py-2 pr-3 text-slate-400">{trade.exit_date}<div className="text-[11px] text-emerald-200">@ {fmtPrice(trade.gross_exit_price)}</div></td>
                    <td className="py-2 pr-3 text-slate-300">{fmtAmt(trade.position_cash)}</td>
                    <td className="py-2 pr-3 text-slate-300">{fmtAmt((trade.shares || 0) * (trade.gross_exit_price || 0))}</td>
                    <td className={`py-2 pr-3 font-semibold ${Number(trade.pnl_cash || 0) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>{fmtAmt(trade.pnl_cash)}<div className="text-[11px]">{fmtPct(trade.net_return_pct)}</div></td>
                    <td className="py-2 pr-3 text-slate-300">{fmtAmt(trade.equity_after)}</td>
                    <td className="py-2 pr-3 text-slate-400">22 #{trade.rank_22_pool ?? '--'} / H5 #{trade.rank_h5_full ?? '--'}</td>
                    <td className="py-2 pr-3 text-slate-400">{trade.exit_reason || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </main>
    </div>
  );
};

export default S06FusionTradeReviewPage;
