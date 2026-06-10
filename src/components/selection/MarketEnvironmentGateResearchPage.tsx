import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, BarChart3, CheckCircle2, ListFilter, ShieldAlert, Target, TimerReset } from 'lucide-react';

import { Metric, SectionCard } from '../common/ResearchCard';
import {
  MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE,
  getMarketEnvironmentGateResearchPage,
} from './marketEnvironmentGateResearchRegistry';

type AnyRow = Record<string, any>;

type GateCycle = {
  label: string;
  value: string;
};

type GateConclusion = {
  title: string;
  text: string;
};

type SourceMatrixItem = {
  source_id: string;
  source_name: string;
  confidence: string;
  conclusion: string;
  sample_n: number;
  attack_vs_defense?: {
    mfe_lift_pct: number;
    pitfall_reduction_pct: number;
  } | null;
  regimes: AnyRow[];
  details: AnyRow[];
  supportive_metrics: AnyRow[];
};

type BlockedCandidate = {
  id: string;
  trade_date: string;
  symbol: string;
  name: string;
  source_id: string;
  source_name: string;
  rank?: number | null;
  score?: number | null;
  original_action: string;
  environment_action: string;
  market_detail_label: string;
  water_score?: number | null;
  reason_summary?: string | null;
  block_reason?: string | null;
  entry_date: string;
  entry_open?: number | null;
  review_conclusion: string;
  outcomes: {
    d5: OutcomePoint;
    d10: OutcomePoint;
    d22: OutcomePoint;
  };
};

type OutcomePoint = {
  full: boolean;
  days?: number | null;
  mfe_pct?: number | null;
  mae_pct?: number | null;
  close_pct?: number | null;
  pitfall: boolean;
  pitfall_reason?: string | null;
};

type GatePayload = {
  meta: {
    title: string;
    generated_from: string;
    trade_date_min: string;
    trade_date_max: string;
    market_state_rows: number;
    candidate_rows: number;
    buyable_rows: number;
    watch_rows: number;
    payload_scope: string;
  };
  conclusions: GateConclusion[];
  latest_market: AnyRow;
  gate_cycles: GateCycle[];
  period_evidence: {
    conclusion: string;
    cycle_summary: AnyRow[];
    leaderboard_top12: AnyRow[];
  };
  policy_comparison: AnyRow[];
  source_matrix: SourceMatrixItem[];
  source_coverage: AnyRow[];
  blocked_review: {
    definition: string;
    items: BlockedCandidate[];
  };
  recent_market: AnyRow[];
};

const fmtNum = (value?: number | null, digits = 2) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(digits);
};

const fmtPct = (value?: number | null, digits = 2) => `${fmtNum(value, digits)}%`;

const retTone = (value?: number | null) => Number(value || 0) >= 0 ? 'text-red-200' : 'text-emerald-200';

const riskTone = (value?: number | null) => Number(value || 0) >= 0 ? 'text-emerald-200' : 'text-red-200';

const actionClass = (action?: string) => {
  if (action === '暂停新开仓') return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  if (action === '观察为主') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  return 'border-sky-500/40 bg-sky-500/10 text-sky-200';
};

const confidenceClass = (confidence?: string) => {
  if (confidence === '可用') return 'border-sky-500/40 bg-sky-500/10 text-sky-200';
  if (confidence === '方向支持') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  return 'border-slate-700 bg-slate-950 text-slate-300';
};

const regimeLabel = (value?: string) => {
  if (value === 'attack') return '攻击';
  if (value === 'caution') return '谨慎';
  if (value === 'defense') return '防守';
  return value || '--';
};

const outcomeLabel = (item: OutcomePoint) => {
  const suffix = item.full ? '' : '未跑满';
  return [
    `冲高 ${fmtPct(item.mfe_pct)}`,
    `回撤 ${fmtPct(item.mae_pct)}`,
    `收盘 ${fmtPct(item.close_pct)}`,
    item.pitfall ? `痛苦持仓${item.pitfall_reason ? `：${item.pitfall_reason}` : ''}` : '未触发痛苦持仓',
    suffix,
  ].filter(Boolean).join(' / ');
};

const useGatePayload = (dataUrl: string) => {
  const [payload, setPayload] = useState<GatePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    fetch(dataUrl)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: GatePayload) => {
        if (cancelled) return;
        setPayload(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || '市场环境门控数据读取失败');
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

const CompactTable: React.FC<{ rows: AnyRow[]; columns: Array<{ key: string; label: string; render?: (row: AnyRow) => React.ReactNode }> }> = ({ rows, columns }) => (
  <div className="overflow-x-auto">
    <table className="min-w-full text-left text-sm">
      <thead className="text-xs text-slate-500">
        <tr>
          {columns.map((column) => <th key={column.key} className="whitespace-nowrap py-2 pr-4">{column.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${row.id || row.metric || row.source_id || row.policy || index}`} className="border-t border-slate-800/70 hover:bg-slate-950/35">
            {columns.map((column) => (
              <td key={column.key} className="whitespace-nowrap py-2 pr-4 text-slate-300">
                {column.render ? column.render(row) : String(row[column.key] ?? '--')}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const BlockedCandidateButton: React.FC<{ item: BlockedCandidate; active: boolean; onClick: () => void }> = ({ item, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`w-full border-b border-slate-800 px-3 py-3 text-left last:border-b-0 ${active ? 'bg-rose-500/10' : 'hover:bg-slate-950/60'}`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500">{item.trade_date}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[10px] text-slate-400">{item.source_name}</span>
        </div>
        <div className="mt-1 flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-semibold text-white">{item.name}</span>
          <span className="font-mono text-[11px] text-slate-500">{item.symbol}</span>
        </div>
        <div className="mt-1 truncate text-xs text-slate-500">{item.market_detail_label} · {item.block_reason}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className={`text-xs font-semibold ${item.review_conclusion === '正确拦截' ? 'text-emerald-200' : 'text-amber-200'}`}>{item.review_conclusion}</div>
        <div className={`text-[11px] ${retTone(item.outcomes.d10.close_pct)}`}>10日 {fmtPct(item.outcomes.d10.close_pct)}</div>
      </div>
    </div>
  </button>
);

const MarketEnvironmentGateResearchPage: React.FC = () => {
  const page = getMarketEnvironmentGateResearchPage(typeof window === 'undefined' ? '' : window.location.pathname) || MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE;
  const { payload, loading, error } = useGatePayload(page.dataUrl);
  const [activeId, setActiveId] = useState('');

  useEffect(() => {
    const firstId = payload?.blocked_review?.items?.[0]?.id || '';
    setActiveId((prev) => (payload?.blocked_review?.items?.some((item) => item.id === prev) ? prev : firstId));
  }, [payload]);

  const blockedItems = payload?.blocked_review?.items || [];
  const activeCandidate = useMemo(
    () => blockedItems.find((item) => item.id === activeId) || blockedItems[0],
    [activeId, blockedItems],
  );
  const blockedCorrect = useMemo(
    () => blockedItems.filter((item) => item.review_conclusion === '正确拦截').length,
    [blockedItems],
  );

  if (loading) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-slate-300">正在加载市场环境门控研究页...</div>;
  }

  if (error || !payload) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-red-200">读取失败：{error || '无数据'}</div>;
  }

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/selection-research" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />
            返回选股研究
          </a>
          <div className="flex items-center gap-2 text-base font-bold text-white">
            <ShieldAlert className="h-5 w-5 text-rose-300" />
            {page.title}
          </div>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">{page.modelLabel}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            {payload.meta.trade_date_min} ~ {payload.meta.trade_date_max}
          </span>
        </div>
      </div>

      <main className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        <SectionCard title="结论卡" icon={<Target className="h-4 w-4 text-rose-300" />}>
          <div className="grid gap-3 md:grid-cols-4">
            {payload.conclusions.map((item) => (
              <div key={item.title} className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                <div className="text-sm font-semibold text-white">{item.title}</div>
                <div className="mt-2 text-sm leading-6 text-slate-300">{item.text}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-7">
            <Metric label="最新日期" value={payload.latest_market.trade_date} />
            <Metric label="当前水位" value={payload.latest_market.market_detail_label || payload.latest_market.market_regime} tone="text-rose-200" />
            <Metric label="默认动作" value={payload.latest_market.default_action} tone="text-rose-200" />
            <Metric label="水位分数" value={fmtNum(payload.latest_market.water_score, 2)} />
            {payload.gate_cycles.map((item) => <Metric key={item.label} label={item.label} value={item.value} />)}
          </div>
          <div className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm leading-6 text-rose-100">
            {payload.latest_market.reason_top3}
          </div>
        </SectionCard>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
          <SectionCard title="周期选择证据" icon={<TimerReset className="h-4 w-4 text-sky-300" />}>
            <div className="mb-3 text-sm leading-6 text-slate-300">{payload.period_evidence.conclusion}</div>
            <div className="grid gap-3 md:grid-cols-4">
              {payload.period_evidence.cycle_summary.map((row) => (
                <div key={row.window} className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-white">{row.window} 日</div>
                    <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[11px] text-slate-300">{row.role}</span>
                  </div>
                  <div className="mt-2 text-xs leading-5 text-slate-400">{row.conclusion}</div>
                  <div className="mt-2 text-xs text-slate-500">{row.top_metric?.metric_label || '--'}</div>
                  <div className="mt-1 text-lg font-bold text-sky-100">{fmtNum(row.top_metric?.business_rank_score, 2)}</div>
                </div>
              ))}
            </div>
            <div className="mt-4">
              <CompactTable
                rows={payload.period_evidence.leaderboard_top12}
                columns={[
                  { key: 'metric_label', label: '指标' },
                  { key: 'window', label: '周期', render: (row) => `${row.window}日` },
                  { key: 'support_count', label: '支持数' },
                  { key: 'avg_mfe_lift', label: 'MFE提升', render: (row) => fmtPct(row.avg_mfe_lift) },
                  { key: 'avg_close_lift', label: '收盘提升', render: (row) => fmtPct(row.avg_close_lift) },
                  { key: 'avg_pitfall_reduction', label: '痛苦下降', render: (row) => fmtPct(row.avg_pitfall_reduction) },
                  { key: 'business_rank_score', label: '业务分', render: (row) => fmtNum(row.business_rank_score, 2) },
                ]}
              />
            </div>
          </SectionCard>

          <SectionCard title="门控效果快照" icon={<CheckCircle2 className="h-4 w-4 text-emerald-300" />}>
            <div className="grid gap-3 sm:grid-cols-2">
              {payload.policy_comparison.map((row) => {
                const closeKey = row.horizon === '5d' ? 'avg_close_5d_pct' : 'avg_close_10d_pct';
                const pitfallKey = 'pitfall_rate';
                return (
                  <div key={`${row.horizon}_${row.policy}`} className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs font-semibold text-white">{row.horizon} · {row.policy}</div>
                      <span className="text-[11px] text-slate-500">{row.n} 样本</span>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                      <div>
                        <div className="text-slate-500">覆盖</div>
                        <div className="mt-1 text-slate-200">{fmtPct(row.coverage_rate)}</div>
                      </div>
                      <div>
                        <div className="text-slate-500">收盘</div>
                        <div className={`mt-1 ${retTone(row[closeKey])}`}>{fmtPct(row[closeKey])}</div>
                      </div>
                      <div>
                        <div className="text-slate-500">痛苦</div>
                        <div className="mt-1 text-amber-200">{fmtPct(row[pitfallKey])}</div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </SectionCard>
        </div>

        <SectionCard title="来源 x 市场状态矩阵" icon={<BarChart3 className="h-4 w-4 text-amber-300" />}>
          <div className="grid gap-4 xl:grid-cols-2">
            {payload.source_matrix.map((source) => (
              <div key={source.source_id} className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-white">{source.source_name}</div>
                    <div className="mt-1 text-xs leading-5 text-slate-400">{source.conclusion}</div>
                  </div>
                  <span className={`rounded border px-2 py-1 text-xs ${confidenceClass(source.confidence)}`}>{source.confidence}</span>
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-4">
                  <Metric label="样本" value={`${source.sample_n} 条`} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2" valueClassName="mt-1 text-sm font-semibold" />
                  <Metric label="攻防MFE差" value={fmtPct(source.attack_vs_defense?.mfe_lift_pct)} tone={retTone(source.attack_vs_defense?.mfe_lift_pct)} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2" valueClassName="mt-1 text-sm font-semibold" />
                  <Metric label="攻防痛苦差" value={fmtPct(source.attack_vs_defense?.pitfall_reduction_pct)} tone={riskTone(source.attack_vs_defense?.pitfall_reduction_pct)} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2" valueClassName="mt-1 text-sm font-semibold" />
                  <Metric label="证据指标" value={`${source.supportive_metrics.length} 条`} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2" valueClassName="mt-1 text-sm font-semibold" />
                </div>
                <div className="mt-3">
                  <CompactTable
                    rows={source.regimes}
                    columns={[
                      { key: 'market_regime', label: '水位', render: (row) => regimeLabel(row.market_regime) },
                      { key: 'n', label: '样本' },
                      { key: 'avg_mfe_22d_pct', label: '22日冲高', render: (row) => fmtPct(row.avg_mfe_22d_pct) },
                      { key: 'avg_close_22d_pct', label: '22日收盘', render: (row) => <span className={retTone(row.avg_close_22d_pct)}>{fmtPct(row.avg_close_22d_pct)}</span> },
                      { key: 'pitfall_rate', label: '痛苦率', render: (row) => fmtPct(row.pitfall_rate) },
                    ]}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <CompactTable
              rows={payload.source_coverage}
              columns={[
                { key: 'business_source_name', label: '来源' },
                { key: 'suggested_action', label: '动作' },
                { key: 'n', label: '样本' },
                { key: 'min_trade_date', label: '起始' },
                { key: 'max_trade_date', label: '结束' },
              ]}
            />
          </div>
        </SectionCard>

        <div className="grid gap-4 xl:grid-cols-[430px_minmax(0,1fr)]">
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
            <div className="border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <ListFilter className="h-4 w-4 text-rose-300" />
                被拦截候选复盘清单
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">{payload.blocked_review.definition}</div>
              <div className="mt-2 text-xs text-slate-400">当前载入 {blockedItems.length} 条，正确拦截 {blockedCorrect} 条。</div>
            </div>
            <div className="max-h-[760px] overflow-y-auto">
              {blockedItems.map((item) => (
                <BlockedCandidateButton
                  key={item.id}
                  item={item}
                  active={activeCandidate?.id === item.id}
                  onClick={() => setActiveId(item.id)}
                />
              ))}
            </div>
          </div>

          {activeCandidate ? (
            <SectionCard title={`${activeCandidate.name} ${activeCandidate.symbol}`} icon={<AlertTriangle className="h-4 w-4 text-rose-300" />} right={
              <a href={`/?symbol=${activeCandidate.symbol}`} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300 hover:border-slate-500">打开主图</a>
            }>
              <div className="grid gap-3 md:grid-cols-6">
                <Metric label="信号日" value={activeCandidate.trade_date} />
                <Metric label="假设买入日" value={activeCandidate.entry_date} />
                <Metric label="假设买入价" value={fmtNum(activeCandidate.entry_open)} />
                <Metric label="来源" value={activeCandidate.source_name} />
                <Metric label="原始动作" value={activeCandidate.original_action} />
                <Metric label="环境动作" value={activeCandidate.environment_action} tone="text-rose-200" />
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-4">
                <Metric label="环境状态" value={activeCandidate.market_detail_label} />
                <Metric label="水位分数" value={fmtNum(activeCandidate.water_score)} />
                <Metric label="来源排序/分数" value={`#${activeCandidate.rank ?? '--'} / ${fmtNum(activeCandidate.score)}`} />
                <Metric label="复盘结论" value={activeCandidate.review_conclusion} tone={activeCandidate.review_conclusion === '正确拦截' ? 'text-emerald-200' : 'text-amber-200'} />
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                  <div className="text-xs font-semibold text-white">5 日观察点</div>
                  <div className="mt-2 text-sm leading-6 text-slate-300">{outcomeLabel(activeCandidate.outcomes.d5)}</div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                  <div className="text-xs font-semibold text-white">10 日观察点</div>
                  <div className="mt-2 text-sm leading-6 text-slate-300">{outcomeLabel(activeCandidate.outcomes.d10)}</div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                  <div className="text-xs font-semibold text-white">22 日硬观察点</div>
                  <div className="mt-2 text-sm leading-6 text-slate-300">{outcomeLabel(activeCandidate.outcomes.d22)}</div>
                </div>
              </div>
              <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/45 p-3 text-sm leading-6 text-slate-300">
                <div><span className="text-slate-500">环境拦截原因：</span>{activeCandidate.block_reason || '--'}</div>
                <div className="mt-1"><span className="text-slate-500">来源原始理由：</span>{activeCandidate.reason_summary || '--'}</div>
              </div>
              <div className={`mt-3 inline-flex rounded border px-2 py-1 text-xs ${actionClass(activeCandidate.environment_action)}`}>
                买入日和买入价为假设口径，不代表真实操作。
              </div>
            </SectionCard>
          ) : null}
        </div>
      </main>
    </div>
  );
};

export default MarketEnvironmentGateResearchPage;
