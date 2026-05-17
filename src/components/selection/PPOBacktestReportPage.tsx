import React, { useEffect, useMemo, useState } from 'react';
import { BarChart3, FileText, Flame, Target, TrendingUp } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent, DataZoomComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { PpoBacktestReport, HistoryMultiframeGranularity, HistoryMultiframeItem } from '../../types';
import { fetchSelectionPpoBacktestReport, fetchSelectionHistoryMultiframe } from '../../services/selectionService';
import MarketTopHeader from '../common/MarketTopHeader';
import HistoryMultiframeFusionView from '../dashboard/HistoryMultiframeFusionView';

echarts.use([LineChart, ScatterChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, CanvasRenderer]);

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));
const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  if (Math.abs(num) >= 1e8) return `${(num / 1e8).toFixed(2)}亿`;
  if (Math.abs(num) >= 1e4) return `${(num / 1e4).toFixed(0)}万`;
  return num.toFixed(0);
};

const SectionCard: React.FC<{ title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }> = ({ title, icon, right, children }) => (
  <section className="rounded-2xl border border-slate-800 bg-slate-900/75 shadow-lg">
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
  <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const getHoldingDays = (entry?: string | null, exit?: string | null) => {
  if (!entry || !exit) return 0;
  const start = new Date(`${entry}T00:00:00`);
  const end = new Date(`${exit}T00:00:00`);
  const diff = Math.round((end.getTime() - start.getTime()) / 86400000);
  return Number.isFinite(diff) ? Math.max(0, diff) : 0;
};

const buildHistoryData = (report: PpoBacktestReport): HistoryMultiframeItem[] => {
  const map = new Map<string, HistoryMultiframeItem>();
  (report.equity_curve || []).forEach((item) => {
    const bucket = String(item.bucket_start || item.trade_date || '');
    const tradeDate = String(item.trade_date || bucket.slice(0, 10));
    if (!bucket || !tradeDate) return;
    map.set(bucket, {
      symbol: 'ppo-report',
      datetime: bucket,
      trade_date: tradeDate,
      granularity: '5m',
      open: null,
      high: null,
      low: null,
      close: Number(item.equity ?? item.cash ?? 0),
      prev_close: null,
      change_pct: null,
      total_amount: null,
      l1_main_buy: null,
      l1_main_sell: null,
      l1_super_buy: null,
      l1_super_sell: null,
      l2_main_buy: null,
      l2_main_sell: null,
      l2_super_buy: null,
      l2_super_sell: null,
      source: 'ppo_report_equity',
      is_finalized: true,
      preview_level: null,
      fallback_used: false,
      quality_info: null,
      is_placeholder: false,
    });
  });
  return [...map.values()];
};

const buildEquityOption = (rows: Array<{ time: string; totalEquity: number; open_positions: number }>) => {
  const times = rows.map((row) => row.time);
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15, 23, 42, 0.92)',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
    },
    legend: { textStyle: { color: '#94a3b8' } },
    grid: { left: '4%', right: '4%', top: '12%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: times, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#60a5fa', formatter: (v: number) => fmtAmt(v) }, splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } } },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 2, height: 14, showDetail: false, borderColor: '#334155', fillerColor: 'rgba(71,85,105,0.22)' },
    ],
    series: [
      {
        name: '账户总资产',
        type: 'line',
        data: rows.map((row) => row.totalEquity),
        showSymbol: false,
        smooth: 0.2,
        areaStyle: { color: 'rgba(244,63,94,0.08)' },
        lineStyle: { color: '#f43f5e', width: 2.4 },
      },
    ],
  };
};

const PPOBacktestReportPage: React.FC = () => {
  const [report, setReport] = useState<PpoBacktestReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [granularity, setGranularity] = useState<HistoryMultiframeGranularity>('5m');
  const [rowLimit, setRowLimit] = useState(18);
  const [sortMode, setSortMode] = useState<'pnl' | 'trade_count'>('pnl');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchSelectionPpoBacktestReport()
      .then((payload) => {
        if (cancelled) return;
        setReport(payload);
        setError(payload ? '' : '读取 PPO 回测报告失败');
        if (payload?.by_symbol?.length) {
          setSelectedSymbol(payload.by_symbol[0].symbol);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || '读取 PPO 回测报告失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const summary = report?.summary || {};
  const rankedSymbols = useMemo(() => {
    const items = [...(report?.by_symbol || [])];
    items.sort((a, b) => {
      if (sortMode === 'trade_count') return (b.trade_count || 0) - (a.trade_count || 0);
      return (b.pnl_cash || 0) - (a.pnl_cash || 0);
    });
    return items.slice(0, rowLimit);
  }, [report, rowLimit, sortMode]);

  const tradeRows = useMemo(() => {
    const rows = [...(report?.trades || [])];
    rows.sort((a, b) => b.exit_date.localeCompare(a.exit_date) || b.pnl_cash - a.pnl_cash);
    return selectedSymbol ? rows.filter((row) => row.symbol === selectedSymbol) : rows;
  }, [report, selectedSymbol]);
  const allTradeRows = useMemo(() => {
    const rows = [...(report?.trades || [])];
    rows.sort((a, b) => a.entry_date.localeCompare(b.entry_date) || a.symbol.localeCompare(b.symbol));
    return rows;
  }, [report]);

  const dayRows = useMemo(() => [...(report?.by_day || [])], [report]);
  const equitySeries = useMemo(() => (report?.equity_curve || []).map((item) => ({
    time: String(item.bucket_start || item.trade_date || ''),
    totalEquity: Number(item.equity || item.cash || 0),
    cash: Number(item.cash || 0),
    open_positions: Number(item.open_positions || 0),
  })), [report]);
  const historyRows = useMemo(() => buildHistoryData(report || { lab_version: '', summary: {}, trades: [], actions: [], equity_curve: [] }), [report]);
  const reportStock = useMemo(() => {
    const symbol = selectedSymbol || report?.by_symbol?.[0]?.symbol || '';
    if (!symbol) return null;
    return { symbol, code: symbol.slice(2), market: symbol.slice(0, 2), name: report?.symbol_names?.[symbol] || symbol };
  }, [report, selectedSymbol]);

  const tradeMarkers = useMemo(() => {
    if (!selectedSymbol) return [];
    return tradeRows.map((trade) => ({
      date: trade.entry_date,
      datetime: trade.entry_bucket,
      type: 'entry' as const,
      label: `买 ${fmtPct(trade.net_return_pct)}%`,
      note: `${trade.entry_bucket} / ${fmtAmt(trade.cost_cash)}`,
      simulated: true,
    })).concat(tradeRows.map((trade) => ({
      date: trade.exit_date,
      datetime: trade.exit_bucket,
      type: 'exit' as const,
      label: `卖 ${fmtPct(trade.net_return_pct)}%`,
      note: `${trade.exit_bucket} / ${fmtAmt(trade.realized_cash)}`,
      simulated: true,
    })));
  }, [selectedSymbol, tradeRows]);

  const strategyInsight = useMemo(() => {
    if (!report) return null;
    return {
      title: '完整口径 PPO 复盘',
      subtitle: `${report.range?.start_date || ''} ~ ${report.range?.end_date || ''}`,
      tone: (Number(summary.total_return_pct || 0) >= 0 ? 'positive' : 'negative') as 'positive' | 'negative',
      sections: [
        {
          title: '关键结论',
          rows: [
            { label: '总收益', value: fmtPct(summary.total_return_pct) },
            { label: '最大回撤', value: fmtPct(summary.max_drawdown_pct) },
            { label: '交易数', value: String(summary.trade_count || 0) },
            { label: '持仓数', value: String(summary.open_positions || 0) },
          ],
        },
        {
          title: '特征口径',
          rows: [
            { label: '输入特征', value: (report.feature_names || []).join(', ') || '--' },
            { label: '模型备注', value: report.policy_note || '--' },
          ],
        },
      ],
    };
  }, [report, summary]);

  const tradeStats = useMemo(() => {
    const rows = report?.trades || [];
    const closed = rows.filter((row) => row.exit_bucket);
    const winners = closed.filter((row) => Number(row.pnl_cash || 0) > 0);
    const losers = closed.filter((row) => Number(row.pnl_cash || 0) < 0);
    const holdingDays = closed.map((row) => getHoldingDays(row.entry_date, row.exit_date));
    const avgHold = holdingDays.length ? holdingDays.reduce((sum, item) => sum + item, 0) / holdingDays.length : 0;
    const topWinners = closed.slice().sort((a, b) => Number(b.pnl_cash || 0) - Number(a.pnl_cash || 0)).slice(0, 8);
    const topLosers = closed.slice().sort((a, b) => Number(a.pnl_cash || 0) - Number(b.pnl_cash || 0)).slice(0, 6);
    return {
      winRate: closed.length ? (winners.length / closed.length) * 100 : 0,
      avgHold,
      winnerPnl: winners.reduce((sum, row) => sum + Number(row.pnl_cash || 0), 0),
      loserPnl: losers.reduce((sum, row) => sum + Number(row.pnl_cash || 0), 0),
      topWinners,
      topLosers,
    };
  }, [report]);
  const capitalStats = useMemo(() => {
    const rows = report?.equity_curve || [];
    const exposures = rows.map((row) => {
      const equity = Number(row.equity || row.cash || 0);
      const cash = Number(row.cash || 0);
      if (!equity) return 0;
      return Math.max(0, Math.min(100, ((equity - cash) / equity) * 100));
    });
    const avgExposure = exposures.length ? exposures.reduce((sum, item) => sum + item, 0) / exposures.length : 0;
    const maxExposure = exposures.length ? Math.max(...exposures) : 0;
    const investedDays = exposures.filter((item) => item >= 5).length;
    const fullDays = exposures.filter((item) => item >= 95).length;
    return { avgExposure, maxExposure, investedDays, fullDays, totalDays: rows.length };
  }, [report]);

  if (loading) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-slate-300">正在加载 PPO 回测报告...</div>;
  }

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <MarketTopHeader
        routeHref="/"
        routeLabel="回到首页"
        routeTitle="返回首页"
        secondaryRouteHref="/model-training"
        secondaryRouteLabel="模型训练"
        secondaryRouteTitle="返回模型训练任务清单"
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
        rightSlot={<a href="/model-training" className="rounded-lg border border-fuchsia-700/50 bg-fuchsia-900/25 px-3 py-1.5 text-xs text-fuchsia-200 hover:bg-fuchsia-800/35">返回任务清单</a>}
      />
      <main className="mx-auto max-w-[1600px] space-y-4 p-3 md:p-6">
        {error ? <div className="rounded-xl border border-red-800 bg-red-950/25 px-4 py-3 text-sm text-red-200">{error}</div> : null}
        <SectionCard title="回测总览" icon={<Target className="h-4 w-4 text-cyan-300" />}>
          <div className="grid gap-3 md:grid-cols-6">
            <Metric label="期末权益" value={fmtAmt(summary.final_equity)} tone="text-red-200" />
            <Metric label="总收益" value={fmtPct(summary.total_return_pct)} tone="text-red-200" />
            <Metric label="最大回撤" value={fmtPct(summary.max_drawdown_pct)} tone="text-emerald-200" />
            <Metric label="交易笔数" value={String(summary.trade_count || 0)} />
            <Metric label="特征口径" value={(report?.feature_names || []).includes('oib_ratio') ? '完整口径' : '弱口径'} />
            <Metric label="样本区间" value={`${report?.range?.start_date || '--'} ~ ${report?.range?.end_date || '--'}`} />
          </div>
        </SectionCard>

        <SectionCard title="收益拆解" icon={<Flame className="h-4 w-4 text-amber-300" />}>
          <div className="grid gap-3 md:grid-cols-5">
            <Metric label="胜率" value={fmtPct(tradeStats.winRate)} tone="text-red-200" />
            <Metric label="盈利合计" value={fmtAmt(tradeStats.winnerPnl)} tone="text-red-200" />
            <Metric label="亏损合计" value={fmtAmt(tradeStats.loserPnl)} tone="text-emerald-200" />
            <Metric label="平均持有" value={`${tradeStats.avgHold.toFixed(1)} 天`} />
            <Metric label="平均仓位" value={fmtPct(capitalStats.avgExposure)} />
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-4">
            <Metric label="最高仓位" value={fmtPct(capitalStats.maxExposure)} />
            <Metric label="持仓天数" value={`${capitalStats.investedDays} / ${capitalStats.totalDays}`} />
            <Metric label="近满仓天数" value={`${capitalStats.fullDays} / ${capitalStats.totalDays}`} />
            <Metric label="交易节奏" value="按日信号 / 次日开盘执行" />
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            <div className="rounded-xl border border-red-900/35 bg-red-950/10 p-3">
              <div className="mb-2 text-xs font-semibold text-red-100">最大盈利单</div>
              <div className="space-y-2">
                {tradeStats.topWinners.map((trade, index) => (
                  <div key={`${trade.symbol}-${trade.entry_bucket}-${index}`} className="grid grid-cols-[90px_minmax(0,1fr)_90px] gap-2 text-xs">
                    <span className="truncate text-slate-200">{report?.symbol_names?.[trade.symbol] || trade.symbol}</span>
                    <span className="truncate text-slate-500">{trade.entry_bucket.slice(5, 16)} 买，{trade.exit_bucket.slice(5, 16)} 卖</span>
                    <span className="text-right font-semibold text-red-200">{fmtAmt(trade.pnl_cash)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-emerald-900/35 bg-emerald-950/10 p-3">
              <div className="mb-2 text-xs font-semibold text-emerald-100">最大亏损单</div>
              <div className="space-y-2">
                {tradeStats.topLosers.map((trade, index) => (
                  <div key={`${trade.symbol}-${trade.entry_bucket}-${index}`} className="grid grid-cols-[90px_minmax(0,1fr)_90px] gap-2 text-xs">
                    <span className="truncate text-slate-200">{report?.symbol_names?.[trade.symbol] || trade.symbol}</span>
                    <span className="truncate text-slate-500">{trade.entry_bucket.slice(5, 16)} 买，{trade.exit_bucket.slice(5, 16)} 卖</span>
                    <span className="text-right font-semibold text-emerald-200">{fmtAmt(trade.pnl_cash)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="账户总资产曲线" icon={<BarChart3 className="h-4 w-4 text-red-300" />}>
          <ReactEChartsCore echarts={echarts} option={buildEquityOption(equitySeries)} style={{ width: '100%', height: 320 }} />
        </SectionCard>

        <SectionCard title="按日收益" icon={<BarChart3 className="h-4 w-4 text-violet-300" />}>
          <div className="grid gap-2 md:grid-cols-3">
            {dayRows.slice().sort((a, b) => b.pnl_cash - a.pnl_cash).slice(0, 8).map((row) => (
              <div key={row.date} className={`rounded-lg border px-3 py-2 ${row.pnl_cash >= 0 ? 'border-red-900/40 bg-red-950/15' : 'border-emerald-900/40 bg-emerald-950/15'}`}>
                <div className="text-xs text-slate-400">{row.date}</div>
                <div className={`mt-1 text-sm font-semibold ${row.pnl_cash >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>{fmtAmt(row.pnl_cash)}</div>
                <div className="mt-1 text-[11px] text-slate-500">成交 {row.trade_count} 笔 / 结算 {fmtAmt(row.realized_cash)}</div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="股票汇总" icon={<Flame className="h-4 w-4 text-amber-300" />} right={
          <div className="flex items-center gap-2 text-xs">
            <button onClick={() => setSortMode('pnl')} className={`rounded-lg px-2 py-1 ${sortMode === 'pnl' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800'}`}>按盈亏</button>
            <button onClick={() => setSortMode('trade_count')} className={`rounded-lg px-2 py-1 ${sortMode === 'trade_count' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800'}`}>按交易数</button>
            <button onClick={() => setRowLimit((v) => Math.min(30, v + 6))} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-800">更多</button>
          </div>
        }>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-3">股票</th>
                  <th className="py-2 pr-3">交易笔数</th>
                  <th className="py-2 pr-3">净盈亏</th>
                  <th className="py-2 pr-3">胜/负</th>
                  <th className="py-2 pr-3">买/卖</th>
                  <th className="py-2 pr-3">查看</th>
                </tr>
              </thead>
              <tbody>
                {rankedSymbols.map((row) => (
                  <tr key={row.symbol} className="border-t border-slate-800/70">
                    <td className="py-2 pr-3">
                      <div className="font-semibold text-white">{row.name || row.symbol}</div>
                      <div className="text-[11px] text-slate-500">{row.symbol}</div>
                    </td>
                    <td className="py-2 pr-3">{row.trade_count}</td>
                    <td className={`py-2 pr-3 font-semibold ${row.pnl_cash >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>{fmtAmt(row.pnl_cash)}</td>
                    <td className="py-2 pr-3 text-slate-400">{row.win_count} / {row.loss_count}</td>
                    <td className="py-2 pr-3 text-slate-400">{row.buy_count} / {row.sell_count}</td>
                    <td className="py-2 pr-3">
                      <button onClick={() => setSelectedSymbol(row.symbol)} className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800">看这只</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="持仓与买卖点" icon={<TrendingUp className="h-4 w-4 text-emerald-300" />}>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            {report?.by_symbol?.slice(0, 12).map((row) => (
              <button key={row.symbol} onClick={() => setSelectedSymbol(row.symbol)} className={`rounded-lg border px-2 py-1 ${selectedSymbol === row.symbol ? 'border-cyan-500 bg-cyan-500/15 text-cyan-200' : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}>
                {(row.name || row.symbol).slice(0, 8)}
              </button>
            ))}
          </div>
          {reportStock ? (
            <HistoryMultiframeFusionView
              activeStock={reportStock}
              backendStatus={true}
              granularity={granularity}
              onGranularityChange={setGranularity}
              startDate={report?.range?.start_date}
              endDate={report?.range?.end_date}
              signalDate={report?.range?.start_date}
              signalLabel="回测区间"
              tradeSummaryText={selectedSymbol ? `${selectedSymbol} / ${tradeRows.length} 笔` : `${report?.summary.trade_count || 0} 笔`}
              tradeSummaryTone={(summary.total_return_pct || 0) >= 0 ? 'positive' : 'negative'}
              strategyInsight={strategyInsight}
              tradeMarkers={tradeMarkers}
              fetchRows={async ({ symbol, granularity, days, startDate, endDate, includeTodayPreview }) => {
                const items = await fetchSelectionHistoryMultiframe(symbol, { granularity, days, startDate, endDate, includeTodayPreview });
                return items;
              }}
            />
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-6 text-sm text-slate-500">暂无可展示股票。</div>
          )}
        </SectionCard>

        <SectionCard title="交易流水" icon={<FileText className="h-4 w-4 text-sky-300" />}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-3">股票</th>
                  <th className="py-2 pr-3">发现时间</th>
                  <th className="py-2 pr-3">入场</th>
                  <th className="py-2 pr-3">买入金额</th>
                  <th className="py-2 pr-3">出场</th>
                  <th className="py-2 pr-3">卖出回款</th>
                  <th className="py-2 pr-3">收益</th>
                  <th className="py-2 pr-3">过程</th>
                  <th className="py-2 pr-3">发现依据</th>
                  <th className="py-2 pr-3">退出</th>
                </tr>
              </thead>
              <tbody>
                {allTradeRows.slice(0, 120).map((trade, index) => (
                  <tr key={`${trade.symbol}-${trade.entry_bucket}-${index}`} className="border-t border-slate-800/70">
                    <td className="py-2 pr-3">
                      <div className="font-semibold text-white">{report?.symbol_names?.[trade.symbol] || trade.symbol}</div>
                      <div className="text-[11px] text-slate-500">{trade.symbol}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">{trade.signal_date || '--'}</td>
                    <td className="py-2 pr-3 text-slate-400">
                      <div>{trade.entry_date} {trade.entry_bucket.slice(11, 16)}</div>
                      <div className="text-[11px] text-slate-500">@ {fmtNum(trade.gross_entry_price, 2)}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-300">{fmtAmt(trade.cost_cash)}</td>
                    <td className="py-2 pr-3 text-slate-400">
                      <div>{trade.exit_date} {trade.exit_bucket.slice(11, 16)}</div>
                      <div className="text-[11px] text-slate-500">@ {fmtNum(trade.gross_exit_price, 2)}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-300">{fmtAmt(trade.realized_cash)}</td>
                    <td className={`py-2 pr-3 font-semibold ${trade.pnl_cash >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>
                      <div>{fmtAmt(trade.pnl_cash)}</div>
                      <div className="text-[11px]">{fmtPct(trade.net_return_pct)}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">
                      <div>持有 {trade.holding_days ?? getHoldingDays(trade.entry_date, trade.exit_date)} 天</div>
                      <div className="text-[11px] text-slate-500">浮盈 {fmtPct(trade.max_runup_pct)} / 回撤 {fmtPct(trade.max_drawdown_pct)}</div>
                    </td>
                    <td className="max-w-[280px] py-2 pr-3 text-slate-400">
                      <div className="truncate">{trade.entry_reason || '--'}</div>
                      <div className="truncate text-[11px] text-slate-500">{trade.theme_names || '--'}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-400">{trade.exit_reason}</td>
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

export default PPOBacktestReportPage;
