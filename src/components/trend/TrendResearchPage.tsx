import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, BrainCircuit, CheckCircle2, Database, FileText, Gauge, RefreshCw, ShieldAlert, TrendingUp } from 'lucide-react';
import { fetchTrendDashboard, fetchTrendIdeas, TrendDashboardData, TrendIdeaItem } from '../../services/trendResearchService';

const fmt = (value?: string | number | null) => {
  if (value == null || value === '') return '--';
  const n = Number(value);
  if (!Number.isNaN(n) && Number.isFinite(n)) return Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(2).replace(/\.00$/, '');
  return String(value);
};

const toneByStage = (value?: string) => {
  const text = value || '';
  if (text.includes('一致')) return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (text.includes('主升')) return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  return 'border-slate-700 bg-slate-800/70 text-slate-200';
};

const SectionCard: React.FC<{ title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }> = ({ title, icon, right, children }) => (
  <section className="rounded-2xl border border-slate-800 bg-slate-900/70 shadow-lg">
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

const Metric: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone = 'text-slate-100' }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const Pill: React.FC<{ children: React.ReactNode; tone?: string }> = ({ children, tone = 'border-slate-700 bg-slate-800 text-slate-200' }) => (
  <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}>{children}</span>
);

const MiniTable: React.FC<{
  rows: Array<Record<string, string>>;
  columns: Array<{ key: string; label: string; align?: 'left' | 'right'; render?: (row: Record<string, string>) => React.ReactNode }>;
  empty?: string;
}> = ({ rows, columns, empty = '暂无数据' }) => {
  if (!rows?.length) return <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-500">{empty}</div>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-xs text-slate-500">
            {columns.map((col) => <th key={col.key} className={`whitespace-nowrap px-3 py-2 font-medium ${col.align === 'right' ? 'text-right' : 'text-left'}`}>{col.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${idx}-${row.symbol || row.ticker || row.indicator}`} className="border-b border-slate-800/70 last:border-0 hover:bg-slate-800/30">
              {columns.map((col) => <td key={col.key} className={`whitespace-nowrap px-3 py-2 ${col.align === 'right' ? 'text-right' : 'text-left'}`}>{col.render ? col.render(row) : fmt(row[col.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const TrendResearchPage: React.FC = () => {
  const [ideas, setIdeas] = useState<TrendIdeaItem[]>([]);
  const [activeIdeaId, setActiveIdeaId] = useState('storage');
  const [dashboard, setDashboard] = useState<TrendDashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = async (ideaId = activeIdeaId) => {
    setLoading(true);
    const [ideaList, detail] = await Promise.all([fetchTrendIdeas(), fetchTrendDashboard(ideaId)]);
    setIdeas(ideaList);
    setDashboard(detail);
    setLoading(false);
  };

  useEffect(() => { reload(activeIdeaId); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [activeIdeaId]);

  const activeIdea = dashboard?.idea || ideas.find((item) => item.id === activeIdeaId);
  const latestBullets = useMemo(() => dashboard?.report?.summary?.bullets?.slice(0, 6) || [], [dashboard]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200 font-sans pb-20">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-[#0a0f1c]/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <a href="/" className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
              <ArrowLeft className="h-3.5 w-3.5" /> 首页
            </a>
            <div>
              <div className="flex items-center gap-2 text-lg font-bold text-white">
                <BrainCircuit className="h-5 w-5 text-cyan-300" /> 趋势研究
              </div>
              <div className="text-xs text-slate-500">对话驱动的长期线索跟踪台：行业数据、估值模型、升级/降级规则</div>
            </div>
          </div>
          <button onClick={() => reload()} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> 刷新
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1600px] grid-cols-1 gap-4 p-3 md:grid-cols-[280px_1fr] md:p-6">
        <aside className="space-y-3">
          <SectionCard title="研究线索" icon={<Database className="h-4 w-4 text-cyan-300" />}>
            <div className="space-y-2">
              {ideas.map((idea) => (
                <button
                  key={idea.id}
                  onClick={() => setActiveIdeaId(idea.id)}
                  className={`w-full rounded-xl border p-3 text-left transition-colors ${activeIdeaId === idea.id ? 'border-cyan-500/50 bg-cyan-500/10' : 'border-slate-800 bg-slate-950/40 hover:bg-slate-800/50'}`}
                >
                  <div className="text-sm font-semibold text-white">{idea.name}</div>
                  <div className="mt-1 text-xs text-slate-500">{idea.rating}</div>
                  <div className="mt-2"><Pill tone={toneByStage(idea.stage)}>{idea.stage}</Pill></div>
                </button>
              ))}
              {!ideas.length && <div className="text-sm text-slate-500">暂无线索。后续通过对话新增。</div>}
            </div>
          </SectionCard>

          <SectionCard title="页面设计原则" icon={<FileText className="h-4 w-4 text-slate-400" />}>
            <div className="space-y-2 text-xs leading-relaxed text-slate-400">
              <p>1. 页面只展示跟踪，不做自动交易。</p>
              <p>2. 每条线索独立累计：行业信号、公司池、估值、结论。</p>
              <p>3. 通过你和 AI 的对话更新数据与判断。</p>
            </div>
          </SectionCard>
        </aside>

        <div className="space-y-4">
          {loading && !dashboard ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-slate-400">趋势研究数据加载中...</div>
          ) : null}

          {activeIdea && (
            <section className="rounded-2xl border border-cyan-800/40 bg-gradient-to-br from-cyan-950/40 via-slate-900 to-slate-950 p-4 shadow-lg">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-cyan-300">{activeIdea.rating}</div>
                  <h1 className="mt-1 text-2xl font-bold text-white">{activeIdea.name}</h1>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Pill tone={toneByStage(activeIdea.stage)}>{activeIdea.stage}</Pill>
                    <Pill tone="border-emerald-500/40 bg-emerald-500/10 text-emerald-200">{activeIdea.status}</Pill>
                    {dashboard?.idea?.report_date ? <Pill>日报 {dashboard.idea.report_date}</Pill> : null}
                  </div>
                </div>
                <div className="max-w-xl rounded-xl border border-slate-700/70 bg-slate-950/50 p-3 text-sm text-slate-300">
                  <div className="text-xs text-slate-500">当前动作</div>
                  <div className="mt-1 font-medium text-white">{activeIdea.action}</div>
                </div>
              </div>
            </section>
          )}

          {dashboard && (
            <>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                <Metric label="行业信号" value={dashboard.verdict.industry} tone="text-emerald-200" />
                <Metric label="交易阶段" value={dashboard.verdict.market} tone="text-amber-200" />
                <Metric label="仓位动作" value={dashboard.verdict.position} tone="text-cyan-200" />
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <SectionCard title="升级条件" icon={<CheckCircle2 className="h-4 w-4 text-emerald-300" />}>
                  <ul className="space-y-2 text-sm text-slate-300">
                    {dashboard.upgrade_rules.map((rule) => <li key={rule} className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-400" />{rule}</li>)}
                  </ul>
                </SectionCard>
                <SectionCard title="降级条件" icon={<ShieldAlert className="h-4 w-4 text-rose-300" />}>
                  <ul className="space-y-2 text-sm text-slate-300">
                    {dashboard.downgrade_rules.map((rule) => <li key={rule} className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-rose-400" />{rule}</li>)}
                  </ul>
                </SectionCard>
              </div>

              <SectionCard title="A 股价格阶段" icon={<TrendingUp className="h-4 w-4 text-rose-300" />}>
                <MiniTable
                  rows={dashboard.a_share_price_stage}
                  columns={[
                    { key: 'name', label: '股票' },
                    { key: 'close', label: '收盘', align: 'right' },
                    { key: 'ret_20d_pct', label: '20日', align: 'right', render: (r) => `${fmt(r.ret_20d_pct)}%` },
                    { key: 'ret_60d_pct', label: '60日', align: 'right', render: (r) => `${fmt(r.ret_60d_pct)}%` },
                    { key: 'from_low_pct', label: '低点以来', align: 'right', render: (r) => `${fmt(r.from_low_pct)}%` },
                    { key: 'drawdown_from_high_pct', label: '高点回撤', align: 'right', render: (r) => `${fmt(r.drawdown_from_high_pct)}%` },
                    { key: 'stage', label: '阶段', render: (r) => <Pill tone={toneByStage(r.stage)}>{r.stage}</Pill> },
                  ]}
                />
              </SectionCard>

              <SectionCard title="估值压力测试" icon={<Gauge className="h-4 w-4 text-violet-300" />}>
                <MiniTable
                  rows={dashboard.valuation_scenarios}
                  columns={[
                    { key: 'name', label: '股票' },
                    { key: 'market_cap_yi', label: '市值', align: 'right', render: (r) => `${fmt(r.market_cap_yi)}亿` },
                    { key: 'bear_pe', label: 'Bear PE', align: 'right' },
                    { key: 'base_pe', label: 'Base PE', align: 'right' },
                    { key: 'bull_pe', label: 'Bull PE', align: 'right' },
                    { key: 'super_bull_pe', label: 'Super PE', align: 'right' },
                    { key: 'required_profit_for_upgrade_yi', label: '升级利润', align: 'right', render: (r) => `${fmt(r.required_profit_for_upgrade_yi)}亿` },
                  ]}
                />
              </SectionCard>

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <SectionCard title="行业信号跟踪" icon={<Database className="h-4 w-4 text-cyan-300" />}>
                  <MiniTable
                    rows={dashboard.industry_signals}
                    columns={[
                      { key: 'date', label: '日期' },
                      { key: 'source', label: '来源' },
                      { key: 'indicator', label: '指标' },
                      { key: 'value', label: '变化' },
                      { key: 'confidence', label: '置信' },
                      { key: 'next_check', label: '下次检查' },
                    ]}
                  />
                </SectionCard>

                <SectionCard title="海外原厂价格阶段" icon={<BarChart3 className="h-4 w-4 text-blue-300" />}>
                  <MiniTable
                    rows={dashboard.global_peer_stage}
                    columns={[
                      { key: 'name', label: '标的' },
                      { key: 'close', label: '收盘', align: 'right' },
                      { key: 'ret_20d_pct', label: '20日', align: 'right', render: (r) => `${fmt(r.ret_20d_pct)}%` },
                      { key: 'from_low_pct', label: '低点以来', align: 'right', render: (r) => `${fmt(r.from_low_pct)}%` },
                      { key: 'drawdown_from_high_pct', label: '回撤', align: 'right', render: (r) => `${fmt(r.drawdown_from_high_pct)}%` },
                    ]}
                  />
                </SectionCard>
              </div>

              <SectionCard title="公司财务快照" icon={<Database className="h-4 w-4 text-emerald-300" />}>
                <MiniTable
                  rows={dashboard.company_snapshot}
                  columns={[
                    { key: 'name', label: '股票' },
                    { key: 'role', label: '定位' },
                    { key: 'q1_revenue_yi', label: 'Q1营收', align: 'right', render: (r) => `${fmt(r.q1_revenue_yi)}亿` },
                    { key: 'q1_net_profit_yi', label: 'Q1净利', align: 'right', render: (r) => `${fmt(r.q1_net_profit_yi)}亿` },
                    { key: 'q1_gross_margin_pct', label: '毛利率', align: 'right', render: (r) => `${fmt(r.q1_gross_margin_pct)}%` },
                    { key: 'annualized_q1_pe', label: 'Q1年化PE', align: 'right' },
                    { key: 'core_question', label: '核心问题' },
                  ]}
                />
              </SectionCard>

              <SectionCard title="累计研究结论" icon={<FileText className="h-4 w-4 text-slate-300" />} right={dashboard.report.path ? <span className="text-xs text-slate-500">{dashboard.report.path}</span> : null}>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1.2fr]">
                  <div className="space-y-2">
                    {latestBullets.map((bullet) => <div key={bullet} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">{bullet}</div>)}
                  </div>
                  <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-xs leading-relaxed text-slate-400">
                    {dashboard.report.markdown || '暂无累计结论'}
                  </pre>
                </div>
              </SectionCard>
            </>
          )}
        </div>
      </main>
    </div>
  );
};

export default TrendResearchPage;
