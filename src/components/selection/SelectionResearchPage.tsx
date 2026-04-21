import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, RefreshCw, ShieldCheck, TrendingUp } from 'lucide-react';

import {
  SelectionBacktestDetail,
  SelectionBacktestRunItem,
  SelectionCandidateItem,
  SelectionHealthData,
  SelectionProfileData,
} from '../../types';
import {
  fetchSelectionBacktestDetail,
  fetchSelectionBacktests,
  fetchSelectionCandidates,
  fetchSelectionHealth,
  fetchSelectionProfile,
  refreshSelectionResearch,
  runSelectionBacktest,
} from '../../services/selectionService';
import { fetchQuote } from '../../services/stockService';
import SelectionDecisionPanel from './SelectionDecisionPanel';

const ACTIVE_STRATEGY = 'breakout' as const;

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));

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

const SelectionResearchPage: React.FC = () => {
  const [health, setHealth] = useState<SelectionHealthData | null>(null);
  const [tradeDate, setTradeDate] = useState('');
  const [pendingTradeDate, setPendingTradeDate] = useState('');
  const [candidates, setCandidates] = useState<SelectionCandidateItem[]>([]);
  const [selected, setSelected] = useState<SelectionCandidateItem | null>(null);
  const [profile, setProfile] = useState<SelectionProfileData | null>(null);
  const [backtestRuns, setBacktestRuns] = useState<SelectionBacktestRunItem[]>([]);
  const [backtestDetail, setBacktestDetail] = useState<SelectionBacktestDetail | null>(null);
  const [nameOverrides, setNameOverrides] = useState<Record<string, string>>({});
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
    const results = await Promise.allSettled(targets.map((item) => fetchQuote(item.symbol.toLowerCase())));
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
      const data = await fetchSelectionCandidates(dateArg || undefined, ACTIVE_STRATEGY, 10);
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
  }, [tradeDate]);

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
        strategy_name: ACTIVE_STRATEGY,
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

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="mx-auto max-w-[1800px] px-4 py-5 md:px-6 md:py-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-3">
              <a
                href="/"
                className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-slate-500"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                返回主页面
              </a>
            </div>
            <h1 className="mt-3 text-2xl font-bold text-white">选股研究工作台</h1>
            <p className="mt-1 text-sm text-slate-400">先选交易日，再快速扫当天 Top10 候选；右侧直接做单票决策判断。</p>
          </div>
        </div>

        {error && <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[180px] text-xs text-slate-400">
              交易日
              <input
                type="date"
                value={pendingTradeDate}
                onChange={(e) => setPendingTradeDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              />
            </label>
            <button
              type="button"
              onClick={handleApplyTradeDate}
              disabled={!pendingTradeDate || loadingCandidates}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-sky-600 px-4 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ShieldCheck className={`h-4 w-4 ${loadingCandidates ? 'animate-pulse' : ''}`} />
              {loadingCandidates ? '查询中...' : '查询候选'}
            </button>
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              刷新数据
            </button>
            <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2.5 py-1 text-sky-300">策略：启动确认 Top10</span>
              <span className="text-slate-500">最新信号日：{health?.latest_signal_date || '--'}</span>
              <span className="text-slate-500">候选数：{loadingCandidates ? '--' : displayCandidates.length}</span>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <TrendingUp className="h-4 w-4 text-amber-400" />
                当日 Top10 候选
              </div>
              <span className="text-xs text-slate-500">{loadingCandidates ? '加载中...' : `${displayCandidates.length} 条`}</span>
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
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-slate-500">#{item.rank || '--'}</span>
                        <span className="truncate text-sm font-semibold text-white">{item.displayName}</span>
                        <span className="shrink-0 text-[11px] text-slate-500">{item.symbol}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                        <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-sky-300">{item.signal_label || '启动确认'}</span>
                        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">{item.current_judgement || '继续观察'}</span>
                        <span className={`${item.risk_level === '高' ? 'text-red-300' : item.risk_level === '中' ? 'text-amber-300' : 'text-emerald-300'}`}>风险{item.risk_level || '低'}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className={`text-base font-semibold ${scoreTone(item.score)}`}>{fmtNum(item.score)}</div>
                      <div className="text-[11px] text-slate-500">确认分</div>
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

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
              <ShieldCheck className="h-4 w-4 text-violet-400" />
              复盘决策视图
            </div>
            {loadingProfile ? (
              <div className="py-16 text-center text-sm text-slate-500">右侧复盘视图加载中...</div>
            ) : (
              <SelectionDecisionPanel
                candidate={selected}
                profile={profile}
                displayName={selectedDisplayName}
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
