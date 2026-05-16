import React, { useEffect, useMemo, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, MarkPointComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { ArrowLeft, BarChart3, FileText, Target, TrendingUp } from 'lucide-react';

echarts.use([
  BarChart,
  CandlestickChart,
  LineChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkPointComponent,
  CanvasRenderer,
]);

type DailyBar = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  total_amount?: number;
  l2_main_net_amount?: number;
  l2_super_net_amount?: number;
  l2_main_net_ratio?: number;
  active_buy_strength?: number;
  is_limit_up_close?: number;
  limit_state_label?: string;
};

type ReviewTrade = {
  trade_id: string;
  trade_date: string;
  entry_date: string;
  exit_date: string;
  symbol: string;
  name: string;
  final_score: number;
  gross_entry_price: number;
  gross_exit_price: number;
  net_entry_price: number;
  net_exit_price: number;
  shares: number;
  buy_amount: number;
  sell_amount: number;
  pnl_cash: number;
  position_cash: number;
  equity_after: number;
  net_return_pct: number;
  gross_return_pct: number;
  holding_days: number;
  exit_reason: string;
  max_runup_22d_pct: number;
  max_runup_before_exit_pct: number;
  max_drawdown_before_exit_pct: number;
  bars: DailyBar[];
};

type EquityPoint = {
  trade_date: string;
  cash: number;
  market_value: number;
  equity: number;
  open_positions: number;
  return_pct: number;
};

type ReviewPayload = {
  meta: {
    strategy: string;
    description: string;
    initial_capital: number;
    trade_count: number;
    signal_start: string;
    signal_end: string;
    entry_start: string;
    exit_end: string;
    review_window?: {
      lookback_trading_days: number;
      forward_trading_days: number;
      anchor: string;
    };
  };
  summary: Record<string, any>;
  trades: ReviewTrade[];
  equity_curve: EquityPoint[];
};

const DATA_URL = '/research/opportunity_trade_review_payload.json';

const fmtNum = (value?: number | null, digits = 2) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(digits);
};

const fmtPct = (value?: number | null, digits = 2) => `${fmtNum(value, digits)}%`;

const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  const sign = num < 0 ? '-' : '';
  const abs = Math.abs(num);
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
  return `${sign}${abs.toFixed(0)}`;
};

const retTone = (value?: number | null) => Number(value || 0) >= 0 ? 'text-red-200' : 'text-emerald-200';

const exitText = (reason?: string) => {
  if (reason === 'take_profit_intraday') return '止盈';
  if (reason === 'hard_stop_intraday') return '止损';
  if (reason === 'time_exit') return '到期';
  return reason || '--';
};

const Metric: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone = 'text-slate-100' }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const Section: React.FC<{ title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }> = ({ title, icon, right, children }) => (
  <section className="rounded-xl border border-slate-800 bg-slate-900/70 shadow-lg">
    <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-white">
        {icon}
        <span>{title}</span>
      </div>
      {right}
    </div>
    <div className="p-4">{children}</div>
  </section>
);

const buildEquityOption = (rows: EquityPoint[]) => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.94)',
    borderColor: '#334155',
    textStyle: { color: '#e2e8f0' },
    formatter: (params: any[]) => {
      const idx = params?.[0]?.dataIndex ?? 0;
      const row = rows[idx];
      if (!row) return '';
      return [
        `<b>${row.trade_date}</b>`,
        `总资产 ${fmtAmt(row.equity)}`,
        `现金 ${fmtAmt(row.cash)}`,
        `持仓市值 ${fmtAmt(row.market_value)}`,
        `持仓数 ${row.open_positions}`,
        `收益 ${fmtPct(row.return_pct)}`,
      ].join('<br/>');
    },
  },
  grid: { left: 48, right: 24, top: 28, bottom: 36 },
  xAxis: {
    type: 'category',
    data: rows.map((row) => row.trade_date.slice(5)),
    axisLabel: { color: '#94a3b8', fontSize: 10 },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value',
    scale: true,
    axisLabel: { color: '#93c5fd', formatter: (v: number) => fmtAmt(v) },
    splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
  },
  dataZoom: [
    { type: 'inside', start: 0, end: 100 },
    { type: 'slider', bottom: 4, height: 16, showDetail: false, borderColor: '#334155', fillerColor: 'rgba(59,130,246,0.16)' },
  ],
  series: [
    {
      name: '账户总资产',
      type: 'line',
      data: rows.map((row) => row.equity),
      showSymbol: false,
      smooth: 0.18,
      lineStyle: { color: '#f87171', width: 2.4 },
      areaStyle: { color: 'rgba(248,113,113,0.10)' },
      markLine: {
        symbol: 'none',
        label: { color: '#94a3b8' },
        lineStyle: { color: '#475569', type: 'dashed' },
        data: [{ yAxis: 1000000, name: '100万起点' }],
      },
    },
  ],
});

const buildTradeKlineOption = (trade: ReviewTrade) => {
  const bars = trade.bars || [];
  const dates = bars.map((bar) => bar.trade_date.slice(5));
  const candle = bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]);
  const l2MainNet = bars.map((bar) => Number(bar.l2_main_net_amount || 0) / 10000);
  const l2SuperNet = bars.map((bar) => Number(bar.l2_super_net_amount || 0) / 10000);
  const findIndex = (date: string) => bars.findIndex((bar) => bar.trade_date === date);
  const signalIndex = findIndex(trade.trade_date);
  const entryIndex = findIndex(trade.entry_date);
  const exitIndex = findIndex(trade.exit_date);
  const markerLines = [
    signalIndex >= 0 ? { xAxis: signalIndex, name: '信号', lineStyle: { color: '#38bdf8' } } : null,
    entryIndex >= 0 ? { xAxis: entryIndex, name: '买入', lineStyle: { color: '#f87171' } } : null,
    exitIndex >= 0 ? { xAxis: exitIndex, name: '卖出', lineStyle: { color: '#34d399' } } : null,
  ].filter(Boolean);
  const markerPoints = [
    entryIndex >= 0 ? { name: '买入', coord: [entryIndex, trade.gross_entry_price], value: '买', itemStyle: { color: '#f87171' } } : null,
    exitIndex >= 0 ? { name: '卖出', coord: [exitIndex, trade.gross_exit_price], value: '卖', itemStyle: { color: '#34d399' } } : null,
  ].filter(Boolean);
  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15,23,42,0.94)',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
      formatter: (params: any[]) => {
        const idx = params?.[0]?.dataIndex ?? 0;
        const bar = bars[idx];
        if (!bar) return '';
        return [
          `<b>${bar.trade_date}</b>`,
          `开 ${fmtNum(bar.open)} 高 ${fmtNum(bar.high)} 低 ${fmtNum(bar.low)} 收 ${fmtNum(bar.close)}`,
          `成交额 ${fmtAmt(bar.total_amount)}`,
          `L2主力净 ${fmtAmt(bar.l2_main_net_amount)}`,
          `L2超大净 ${fmtAmt(bar.l2_super_net_amount)}`,
          bar.is_limit_up_close ? '涨停收盘' : '',
        ].filter(Boolean).join('<br/>');
      },
    },
    legend: { top: 2, textStyle: { color: '#94a3b8' } },
    grid: [
      { left: 50, right: 42, top: 34, height: 210 },
      { left: 50, right: 42, top: 270, height: 90 },
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
        data: dates,
        gridIndex: 1,
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
        scale: true,
        gridIndex: 1,
        axisLabel: { color: '#60a5fa', fontSize: 10, formatter: (v: number) => `${v.toFixed(0)}万` },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
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
          label: { color: '#cbd5e1', formatter: '{b}' },
          lineStyle: { type: 'dashed', width: 1.2 },
          data: markerLines,
        },
        markPoint: {
          symbolSize: 54,
          label: { color: '#020617', fontSize: 10 },
          data: markerPoints,
        },
      },
      {
        name: '买入价',
        type: 'line',
        data: bars.map(() => trade.gross_entry_price),
        showSymbol: false,
        lineStyle: { color: '#f87171', type: 'dashed', width: 1 },
      },
      {
        name: '卖出价',
        type: 'line',
        data: bars.map(() => trade.gross_exit_price),
        showSymbol: false,
        lineStyle: { color: '#34d399', type: 'dashed', width: 1 },
      },
      {
        name: 'L2主力净',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: l2MainNet,
        itemStyle: { color: (params: any) => Number(params.value || 0) >= 0 ? '#ef4444' : '#22c55e' },
      },
      {
        name: 'L2超大净',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: l2SuperNet,
        showSymbol: false,
        lineStyle: { color: '#a78bfa', width: 1.5 },
      },
    ],
  };
};

const TradeListItem: React.FC<{ trade: ReviewTrade; active: boolean; onClick: () => void }> = ({ trade, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`w-full border-b border-slate-800 px-3 py-3 text-left last:border-b-0 ${active ? 'bg-sky-500/10' : 'hover:bg-slate-950/60'}`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">{trade.trade_id}</span>
          <span className="text-xs text-slate-500">{trade.trade_date} 信号</span>
        </div>
        <div className="mt-1 flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-white">{trade.name}</span>
          <span className="font-mono text-[11px] text-slate-500">{trade.symbol}</span>
        </div>
        <div className="mt-1 text-xs text-slate-500">{trade.entry_date} 买 → {trade.exit_date} 卖</div>
      </div>
      <div className="text-right">
        <div className={`text-sm font-bold ${retTone(trade.net_return_pct)}`}>{fmtPct(trade.net_return_pct)}</div>
        <div className={`text-[11px] ${retTone(trade.pnl_cash)}`}>{fmtAmt(trade.pnl_cash)}</div>
      </div>
    </div>
  </button>
);

const OpportunityTradeReviewPage: React.FC = () => {
  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTradeId, setActiveTradeId] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(DATA_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: ReviewPayload) => {
        if (cancelled) return;
        setPayload(data);
        setActiveTradeId(data.trades?.[0]?.trade_id || '');
        setError('');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || '交易复盘数据读取失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const trades = payload?.trades || [];
  const activeTrade = useMemo(() => trades.find((trade) => trade.trade_id === activeTradeId) || trades[0], [activeTradeId, trades]);
  const winners = useMemo(() => trades.filter((trade) => Number(trade.pnl_cash) > 0), [trades]);
  const losers = useMemo(() => trades.filter((trade) => Number(trade.pnl_cash) < 0), [trades]);
  const totalPnl = useMemo(() => trades.reduce((sum, trade) => sum + Number(trade.pnl_cash || 0), 0), [trades]);

  if (loading) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-slate-300">正在加载机会发现交易复盘...</div>;
  }

  if (error || !payload) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-red-200">读取失败：{error || '无数据'}</div>;
  }

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/selection-research" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />返回选股研究
          </a>
          <div className="flex items-center gap-2 text-base font-bold text-white">
            <Target className="h-5 w-5 text-cyan-300" />
            机会发现交易复盘
          </div>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            {payload.meta.signal_start} ~ {payload.meta.exit_end}
          </span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            单票图固定：信号前{payload.meta.review_window?.lookback_trading_days ?? 10}日 / 信号后{payload.meta.review_window?.forward_trading_days ?? 22}日
          </span>
        </div>
      </div>

      <main className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        <Section title="账户总览" icon={<BarChart3 className="h-4 w-4 text-cyan-300" />}>
          <div className="grid gap-3 md:grid-cols-6">
            <Metric label="期初资金" value={fmtAmt(payload.meta.initial_capital)} />
            <Metric label="期末权益" value={fmtAmt(payload.summary.final_equity)} tone="text-red-200" />
            <Metric label="总收益" value={fmtPct(payload.summary.total_return_pct)} tone="text-red-200" />
            <Metric label="最大回撤" value={fmtPct(payload.summary.max_drawdown_pct)} tone="text-emerald-200" />
            <Metric label="交易笔数" value={`${payload.summary.trades || trades.length} 笔`} />
            <Metric label="胜率" value={fmtPct(Number(payload.summary.win_rate || 0) * 100)} />
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-4">
            <Metric label="总盈亏" value={fmtAmt(totalPnl)} tone={retTone(totalPnl)} />
            <Metric label="盈利/亏损" value={`${winners.length} / ${losers.length}`} />
            <Metric label="平均持仓" value={`${fmtNum(payload.summary.avg_holding_days)} 天`} />
            <Metric label="策略壳" value={payload.meta.description} />
          </div>
        </Section>

        <Section title="100万账户绝对金额曲线" icon={<TrendingUp className="h-4 w-4 text-red-300" />}>
          <ReactEChartsCore echarts={echarts} option={buildEquityOption(payload.equity_curve || [])} style={{ width: '100%', height: 330 }} />
        </Section>

        <div className="grid gap-4 xl:grid-cols-[390px_minmax(0,1fr)]">
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
            <div className="border-b border-slate-800 px-4 py-3">
              <div className="text-sm font-semibold text-white">交易清单</div>
              <div className="mt-1 text-xs text-slate-500">点击左侧交易，右侧展示固定操作窗口K线。</div>
            </div>
            <div className="max-h-[760px] overflow-y-auto">
              {trades.map((trade) => (
                <TradeListItem
                  key={trade.trade_id}
                  trade={trade}
                  active={activeTrade?.trade_id === trade.trade_id}
                  onClick={() => setActiveTradeId(trade.trade_id)}
                />
              ))}
            </div>
          </div>

          {activeTrade ? (
            <div className="space-y-4">
              <Section title={`${activeTrade.name} ${activeTrade.symbol}`} icon={<TrendingUp className="h-4 w-4 text-amber-300" />} right={
                <a href={`/?symbol=${activeTrade.symbol}`} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300 hover:border-slate-500">打开主图</a>
              }>
                <div className="grid gap-3 md:grid-cols-7">
                  <Metric label="信号日" value={activeTrade.trade_date} />
                  <Metric label="买入日" value={activeTrade.entry_date} />
                  <Metric label="卖出日" value={activeTrade.exit_date} />
                  <Metric label="买入价" value={fmtNum(activeTrade.gross_entry_price)} />
                  <Metric label="卖出价" value={fmtNum(activeTrade.gross_exit_price)} />
                  <Metric label="股数" value={`${Number(activeTrade.shares || 0).toLocaleString()} 股`} />
                  <Metric label="退出原因" value={exitText(activeTrade.exit_reason)} />
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-6">
                  <Metric label="买入金额" value={fmtAmt(activeTrade.buy_amount)} />
                  <Metric label="卖出回款" value={fmtAmt(activeTrade.sell_amount)} />
                  <Metric label="盈亏金额" value={fmtAmt(activeTrade.pnl_cash)} tone={retTone(activeTrade.pnl_cash)} />
                  <Metric label="净收益率" value={fmtPct(activeTrade.net_return_pct)} tone={retTone(activeTrade.net_return_pct)} />
                  <Metric label="期间最大浮盈" value={fmtPct(activeTrade.max_runup_before_exit_pct)} tone="text-red-200" />
                  <Metric label="期间最大回撤" value={fmtPct(activeTrade.max_drawdown_before_exit_pct)} tone="text-emerald-200" />
                </div>
                <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/45 p-2">
                  <div className="px-2 pb-2 text-xs text-slate-500">
                    固定窗口：从信号日前{payload.meta.review_window?.lookback_trading_days ?? 10}个交易日看到信号日后{payload.meta.review_window?.forward_trading_days ?? 22}个交易日，不按实际持仓天数截断。
                  </div>
                  <ReactEChartsCore echarts={echarts} option={buildTradeKlineOption(activeTrade)} style={{ width: '100%', height: 390 }} />
                </div>
              </Section>
            </div>
          ) : null}
        </div>

        <Section title="交易明细" icon={<FileText className="h-4 w-4 text-sky-300" />}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-3">股票</th>
                  <th className="py-2 pr-3">信号</th>
                  <th className="py-2 pr-3">买入</th>
                  <th className="py-2 pr-3">卖出</th>
                  <th className="py-2 pr-3">金额</th>
                  <th className="py-2 pr-3">收益</th>
                  <th className="py-2 pr-3">过程</th>
                  <th className="py-2 pr-3">原因</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr key={trade.trade_id} className="border-t border-slate-800/70 hover:bg-slate-950/35">
                    <td className="py-2 pr-3">
                      <button type="button" onClick={() => setActiveTradeId(trade.trade_id)} className="text-left">
                        <div className="font-semibold text-white">{trade.name}</div>
                        <div className="font-mono text-[11px] text-slate-500">{trade.trade_id} · {trade.symbol}</div>
                      </button>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">{trade.trade_date}</td>
                    <td className="py-2 pr-3 text-slate-400">
                      <div>{trade.entry_date}</div>
                      <div className="text-[11px] text-slate-500">@ {fmtNum(trade.gross_entry_price)} / {Number(trade.shares || 0).toLocaleString()}股</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">
                      <div>{trade.exit_date}</div>
                      <div className="text-[11px] text-slate-500">@ {fmtNum(trade.gross_exit_price)}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-300">
                      <div>买 {fmtAmt(trade.buy_amount)}</div>
                      <div className="text-[11px] text-slate-500">卖 {fmtAmt(trade.sell_amount)}</div>
                    </td>
                    <td className={`py-2 pr-3 font-semibold ${retTone(trade.pnl_cash)}`}>
                      <div>{fmtAmt(trade.pnl_cash)}</div>
                      <div className="text-[11px]">{fmtPct(trade.net_return_pct)}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">
                      <div>{trade.holding_days} 天</div>
                      <div className="text-[11px] text-slate-500">浮盈 {fmtPct(trade.max_runup_before_exit_pct)} / 回撤 {fmtPct(trade.max_drawdown_before_exit_pct)}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">{exitText(trade.exit_reason)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </main>
    </div>
  );
};

export default OpportunityTradeReviewPage;
