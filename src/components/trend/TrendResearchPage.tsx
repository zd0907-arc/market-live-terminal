import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  Database,
  FileText,
  Gauge,
  GitBranch,
  Layers3,
  RefreshCw,
  ServerCog,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { APP_VERSION } from '../../version';
import { fetchTrendDashboard, fetchTrendIdeas, TrendDashboardData, TrendIdeaItem } from '../../services/trendResearchService';
import { Metric, SectionCard } from '../common/ResearchCard';

type Row = Record<string, string>;
type RubberPriceRow = { date: string; ru_close?: string; nr_close?: string };

const fmt = (value?: string | number | null, digits = 2) => {
  if (value == null || value === '') return '--';
  const n = Number(value);
  if (!Number.isNaN(n) && Number.isFinite(n)) {
    const fixed = Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(digits);
    return fixed.replace(/\.00$/, '');
  }
  return String(value);
};

const num = (value?: string | number | null) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

const pct = (value?: string | number | null) => `${fmt(value)}%`;
const hasRows = (rows?: Row[]) => Array.isArray(rows) && rows.length > 0;
const hasPriceRows = (rows?: RubberPriceRow[]) => Array.isArray(rows) && rows.length > 0;

const toneByStage = (value?: string) => {
  const text = value || '';
  if (text.includes('一致') || text.includes('高位')) return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (text.includes('主升')) return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  if (text.includes('强')) return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  if (text.includes('待')) return 'border-slate-600 bg-slate-800/70 text-slate-300';
  return 'border-slate-700 bg-slate-800/70 text-slate-200';
};

const toneByImportance = (value?: string) => {
  if (value === 'S') return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  if (value === 'A') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (value === 'B') return 'border-sky-500/40 bg-sky-500/10 text-sky-200';
  return 'border-slate-700 bg-slate-800/70 text-slate-300';
};

const chartTooltipStyle = {
  background: '#0f172a',
  border: '1px solid #334155',
  borderRadius: 12,
  color: '#e2e8f0',
};

const lineColors = ['#22d3ee', '#f97316', '#a78bfa', '#34d399', '#f43f5e', '#eab308', '#60a5fa', '#fb7185'];

const Pill: React.FC<{ children: React.ReactNode; tone?: string }> = ({ children, tone = 'border-slate-700 bg-slate-800 text-slate-200' }) => (
  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}>{children}</span>
);

const InfoTip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="group relative inline-flex">
    <span className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-600 bg-slate-800 text-[10px] font-bold text-slate-300">!</span>
    <span className="pointer-events-none absolute left-1/2 top-6 z-50 hidden w-72 -translate-x-1/2 rounded-xl border border-slate-700 bg-slate-950 p-3 text-left text-[11px] leading-relaxed text-slate-300 shadow-2xl group-hover:block">
      {children}
    </span>
  </span>
);

const TextList: React.FC<{ rows: string[]; tone: 'green' | 'red' }> = ({ rows, tone }) => {
  const dot = tone === 'green' ? 'bg-emerald-400' : 'bg-rose-400';
  return (
    <ul className="space-y-2 text-sm text-slate-300">
      {rows.map((rule) => (
        <li key={rule} className="flex gap-2">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
          <span className="min-w-0 break-words">{rule}</span>
        </li>
      ))}
    </ul>
  );
};

const ScoreBar: React.FC<{ label: string; value: number; max?: number; color?: string; suffix?: string }> = ({ label, value, max = 100, color = 'bg-cyan-400', suffix = '' }) => {
  const width = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-slate-500">
        <span>{label}</span>
        <span className="font-mono text-slate-300">{fmt(value, 1)}{suffix}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
};

const ChainFlow: React.FC<{ rows: Row[] }> = ({ rows }) => {
  const groups = useMemo(() => {
    const map = new Map<string, Row[]>();
    [...rows].sort((a, b) => num(a.order) - num(b.order)).forEach((row) => {
      const key = row.segment || '其他';
      map.set(key, [...(map.get(key) || []), row]);
    });
    return Array.from(map.entries());
  }, [rows]);

  if (!groups.length) return <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-500">暂无数据</div>;

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      {groups.map(([segment, items], index) => (
        <div key={segment} className="relative min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-white">{segment}</div>
            <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">L{index + 1}</span>
          </div>
          <div className="space-y-2">
            {items.map((item) => (
              <div key={`${item.order}-${item.layer}`} className="rounded-lg border border-slate-800/80 bg-slate-900/60 p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-cyan-100">{item.layer}</span>
                  <Pill tone={toneByStage(item.status)}>{item.status}</Pill>
                </div>
                <div className="mt-1 text-[11px] leading-relaxed text-slate-400">{item.key_indicator}</div>
                <div className="mt-2 text-xs text-slate-300">{item.a_share_mapping}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

const PriceStageChart: React.FC<{ rows: Row[] }> = ({ rows }) => {
  const data = rows.map((r) => ({
    name: r.name,
    ret20: num(r.ret_20d_pct),
    fromLow: num(r.from_low_pct),
    drawdown: num(r.drawdown_from_high_pct),
    stage: r.stage,
  }));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <Pill tone="border-orange-500/30 bg-orange-500/10 text-orange-200">橙色：从本轮低点涨了多少</Pill>
        <Pill tone="border-sky-500/30 bg-sky-500/10 text-sky-200">蓝色：近20日涨幅</Pill>
        <InfoTip>
          <div className="font-semibold text-white">怎么看</div>
          <div className="mt-1">橙色越长，说明离底部越远；蓝色越长，说明短期越热。两者都很长时，通常不是舒服买点，要等分歧后确认。</div>
        </InfoTip>
      </div>
      <div className="h-[320px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }} barCategoryGap={12}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
            <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={72} tick={{ fill: '#cbd5e1', fontSize: 12 }} />
            <Tooltip contentStyle={chartTooltipStyle} formatter={(value: number, name: string) => [`${fmt(value)}%`, name === 'ret20' ? '近20日涨幅' : name === 'fromLow' ? '本轮低点以来' : '回撤']} />
            <Bar dataKey="fromLow" name="本轮低点以来" fill="#f97316" radius={[0, 4, 4, 0]} />
            <Bar dataKey="ret20" name="近20日涨幅" fill="#38bdf8" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const ValuationChart: React.FC<{ rows: Row[] }> = ({ rows }) => {
  const data = rows.map((r) => ({
    name: r.name,
    basePe: num(r.base_pe),
    upgradePe: num(r.upgrade_pe_at_required_profit),
    superPe: num(r.super_bull_pe),
  }));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <Pill tone="border-violet-500/30 bg-violet-500/10 text-violet-200">紫色：基准利润PE</Pill>
        <Pill tone="border-cyan-500/30 bg-cyan-500/10 text-cyan-200">青色：升级利润PE</Pill>
        <Pill tone="border-emerald-500/30 bg-emerald-500/10 text-emerald-200">绿色：乐观利润PE</Pill>
        <InfoTip>
          <div className="font-semibold text-white">怎么看</div>
          <div className="mt-1">PE越高，说明股价已经透支越多利润。若基准PE仍很高，就不能只看行业涨价，还要等财报兑现。</div>
        </InfoTip>
      </div>
      <div className="h-[320px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: '#cbd5e1', fontSize: 12 }} interval={0} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={34} />
            <Tooltip contentStyle={chartTooltipStyle} formatter={(value: number, name: string) => [fmt(value), name === 'basePe' ? '基准利润PE' : name === 'upgradePe' ? '升级利润PE' : '乐观利润PE']} />
            <Bar dataKey="basePe" name="基准利润PE" fill="#a78bfa" radius={[4, 4, 0, 0]} />
            <Bar dataKey="upgradePe" name="升级利润PE" fill="#22d3ee" radius={[4, 4, 0, 0]} />
            <Bar dataKey="superPe" name="乐观利润PE" fill="#34d399" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const HistoryLineChart: React.FC<{ rows: Row[]; idKey: 'symbol' | 'ticker'; description?: string }> = ({ rows, idKey, description }) => {
  const { data, names, startDate } = useMemo(() => {
    const nameById = new Map<string, string>();
    const byDate = new Map<string, Row>();
    rows.forEach((r) => {
      const id = r[idKey] || r.name;
      const name = r.name || id;
      nameById.set(id, name);
      const current = byDate.get(r.date) || { date: r.date };
      current[name] = String(num(r.indexed_return_pct));
      byDate.set(r.date, current);
    });
    return {
      data: Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date))),
      names: Array.from(nameById.values()),
      startDate: rows.map((r) => r.date).filter(Boolean).sort()[0] || '',
    };
  }, [rows, idKey]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span>{description || `从 ${startDate || '起点'} 开始归一化为 0%，看谁跑得更强。`}</span>
        <InfoTip>
          <div className="font-semibold text-white">为什么都从0开始</div>
          <div className="mt-1">这是相对收益图，不是股价图。把起点统一设为0%，方便比较同一时间窗口里谁更强、谁先走弱。</div>
        </InfoTip>
      </div>
      <div className="h-[340px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} minTickGap={24} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={42} tickFormatter={(v) => `${v}%`} />
            <Tooltip contentStyle={chartTooltipStyle} formatter={(value: number, name: string) => [`${fmt(value)}%`, name]} labelFormatter={(label) => `日期 ${label}`} />
            <Legend wrapperStyle={{ color: '#cbd5e1', fontSize: 12 }} />
            {names.map((name, idx) => (
              <Line key={name} type="monotone" dataKey={name} stroke={lineColors[idx % lineColors.length]} strokeWidth={2} dot={false} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const PriceRadarCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
    {rows.map((r) => (
      <div key={`${r.category}-${r.indicator}`} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Pill>{r.category}</Pill>
          <Pill tone={toneByImportance(r.importance)}>{r.importance}</Pill>
          <Pill tone={toneByStage(r.signal_state)}>{r.signal_state}</Pill>
        </div>
        <div className="mt-3 text-sm font-semibold text-white">{r.indicator}</div>
        <div className="mt-1 break-words text-sm text-cyan-100">{r.current_value}</div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-400">
          <div><span className="text-slate-500">频率 </span>{r.frequency || '--'}</div>
          <div><span className="text-slate-500">检查 </span>{r.next_check || '--'}</div>
          <div className="col-span-2 break-words"><span className="text-slate-500">用途 </span>{r.decision_use || '--'}</div>
        </div>
      </div>
    ))}
  </div>
);

const MappingScoreCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r) => (
      <div key={r.symbol} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-white">{r.name}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{r.symbol} · {r.tracking_priority}</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-cyan-100">{fmt(r.total_score, 0)}</div>
            <div className="text-[10px] text-slate-500">总分</div>
          </div>
        </div>
        <div className="mt-3 space-y-2">
          <ScoreBar label="业务纯度" value={num(r.purity_score)} color="bg-cyan-400" />
          <ScoreBar label="利润弹性" value={num(r.profit_elasticity_score)} color="bg-emerald-400" />
          <ScoreBar label="估值压力" value={num(r.valuation_pressure_score)} color="bg-violet-400" />
          <ScoreBar label="位置风险" value={num(r.price_stage_risk_score)} color="bg-amber-400" />
        </div>
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-xs text-slate-300">{r.action}</div>
        <div className="mt-2 text-[11px] leading-relaxed text-slate-500">{r.core_verification}</div>
      </div>
    ))}
  </div>
);

const companyDecisionTone = (value?: string) => {
  const text = value || '';
  if (text.includes('核心') || text.includes('进入') || text.includes('观察池')) return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  if (text.includes('候选') || text.includes('待验证') || text.includes('旁路')) return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (text.includes('剔除') || text.includes('排除')) return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  return 'border-slate-700 bg-slate-800/70 text-slate-300';
};

const sourceLinks = (value?: string) => splitSourceUrls(value).slice(0, 2);

const CompanyResearchCards: React.FC<{ rows: Row[]; compact?: boolean }> = ({ rows, compact = false }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r, idx) => {
      const title = r.name || r.symbol || `公司 ${idx + 1}`;
      const branch = r.branch || r.layer || r.role || '--';
      const decision = r.include_decision || r.pool_tier || r.action || r.current_action || '待研究';
      const business = r.business_summary || r.role || '';
      const trendLink = r.trend_link || r.core_verification || '';
      const profitDriver = r.profit_driver || '';
      const growthSpace = r.growth_space || '';
      const valuation = r.valuation_snapshot || '';
      const validation = r.latest_validation || '';
      const risk = r.key_risk || r.risk || '';
      const nextData = r.next_data_to_watch || r.next_validation || '';
      const action = r.action || r.current_action || '';
      const links = sourceLinks(r.source_url);
      return (
        <div key={`${r.symbol || title}-${idx}`} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="break-words text-sm font-semibold text-white">{title}</div>
              <div className="mt-0.5 text-[11px] text-slate-500">{r.symbol || '--'} · {branch}</div>
            </div>
            <Pill tone={companyDecisionTone(decision)}>{decision}</Pill>
          </div>
          {business ? <div className="mt-3 text-xs leading-relaxed text-slate-300">{business}</div> : null}
          <div className="mt-3 grid gap-2 text-[11px] leading-relaxed text-slate-400">
            {trendLink ? <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-2"><span className="text-cyan-200">趋势关系 </span>{trendLink}</div> : null}
            {!compact && profitDriver ? <div><span className="text-emerald-300">利润来源 </span>{profitDriver}</div> : null}
            {!compact && growthSpace ? <div><span className="text-slate-300">成长空间 </span>{growthSpace}</div> : null}
            {valuation ? <div><span className="text-amber-300">估值/位置 </span>{valuation}</div> : null}
            {validation ? <div><span className="text-violet-300">最近验证 </span>{validation}</div> : null}
            {risk ? <div><span className="text-rose-300">核心风险 </span>{risk}</div> : null}
            {nextData ? <div><span className="text-white">下一步看 </span>{nextData}</div> : null}
          </div>
          {action ? <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-xs font-semibold text-cyan-100">{action}</div> : null}
          {links.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {links.map((link, linkIdx) => (
                <a key={link} href={link} target="_blank" rel="noreferrer" className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] text-slate-400 hover:border-cyan-500 hover:text-cyan-200">
                  来源{linkIdx + 1}
                </a>
              ))}
            </div>
          ) : null}
        </div>
      );
    })}
  </div>
);

const PriceStageCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r) => (
      <div key={r.symbol} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-white">{r.name}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{r.latest_trade_date} · 成交 {fmt(r.amount_yi)}亿</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-white">{fmt(r.close)}</div>
            <div className={num(r.change_pct) >= 0 ? 'text-xs text-red-300' : 'text-xs text-emerald-300'}>{pct(r.change_pct)}</div>
          </div>
        </div>
        <div className="mt-3 space-y-2">
          <ScoreBar label="20日" value={num(r.ret_20d_pct)} max={80} color="bg-sky-400" suffix="%" />
          <ScoreBar label="低点以来" value={num(r.from_low_pct)} max={180} color="bg-orange-400" suffix="%" />
          <ScoreBar label="高点回撤" value={Math.abs(num(r.drawdown_from_high_pct))} max={25} color="bg-rose-400" suffix="%" />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Pill tone={toneByStage(r.stage)}>{r.stage}</Pill>
          <Pill>换手 {pct(r.turnover_pct)}</Pill>
        </div>
        <div className="mt-3 grid gap-2 text-xs text-slate-400">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2"><span className="text-emerald-300">强 </span>{r.strong_trigger}</div>
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-2"><span className="text-rose-300">弱 </span>{r.weak_trigger}</div>
        </div>
      </div>
    ))}
  </div>
);

const ValuationCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r) => (
      <div key={r.symbol} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-white">{r.name}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">市值 {fmt(r.market_cap_yi)}亿</div>
          </div>
          <Pill tone={num(r.base_pe) > 40 ? toneByStage('高位') : 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200'}>Base {fmt(r.base_pe)}x</Pill>
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2 text-center">
          <Metric label="Bear" value={`${fmt(r.bear_pe)}x`} />
          <Metric label="Base" value={`${fmt(r.base_pe)}x`} />
          <Metric label="Bull" value={`${fmt(r.bull_pe)}x`} />
          <Metric label="Super" value={`${fmt(r.super_bull_pe)}x`} />
        </div>
        <div className="mt-3 text-xs text-slate-400">升级利润 {fmt(r.required_profit_for_upgrade_yi)}亿 · 升级PE {fmt(r.upgrade_pe_at_required_profit)}x</div>
        <div className="mt-2 text-[11px] leading-relaxed text-slate-500">{r.required_condition}</div>
      </div>
    ))}
  </div>
);

const CompanyValidationCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r) => (
      <div key={r.symbol} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-white">{r.name}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{r.report_date}</div>
          </div>
          <Pill tone={toneByStage(r.validation_state)}>{r.validation_state}</Pill>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label="存货" value={`${fmt(r.inventory_yi)}亿`} />
          <Metric label="合同负债" value={`${fmt(r.contract_liab_yi)}亿`} tone="text-cyan-200" />
          <Metric label="经营现金流" value={`${fmt(r.netcash_operate_yi)}亿`} tone={num(r.netcash_operate_yi) >= 0 ? 'text-emerald-200' : 'text-rose-200'} />
        </div>
        <div className="mt-3 space-y-2">
          <ScoreBar label="存货同比" value={Math.max(0, num(r.inventory_yoy_pct))} max={600} color="bg-amber-400" suffix="%" />
          <ScoreBar label="合同负债/存货" value={Math.max(0, num(r.contract_liab_to_inventory_pct))} max={30} color="bg-cyan-400" suffix="%" />
          <ScoreBar label="OCF/净利" value={Math.max(0, num(r.ocf_to_np_pct))} max={200} color="bg-emerald-400" suffix="%" />
        </div>
        <div className="mt-3 grid gap-2 text-[11px] text-slate-400">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2"><span className="text-emerald-300">升 </span>{r.upgrade_if}</div>
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-2"><span className="text-rose-300">降 </span>{r.downgrade_if}</div>
        </div>
      </div>
    ))}
  </div>
);

const DecisionCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r) => (
      <div key={r.symbol} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-white">{r.name}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{r.tracking_role}</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-cyan-100">{fmt(r.total_score, 0)}</div>
            <div className="text-[10px] text-slate-500">评分</div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Pill tone={toneByStage(r.stage)}>{r.stage}</Pill>
          {r.base_pe ? <Pill>Base PE {fmt(r.base_pe)}x</Pill> : null}
        </div>
        <div className="mt-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-2 text-sm font-semibold text-cyan-100">{r.current_action}</div>
        <div className="mt-3 grid gap-2 text-[11px] leading-relaxed text-slate-400">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2"><span className="text-emerald-300">入 </span>{r.entry_condition}</div>
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-2"><span className="text-rose-300">错 </span>{r.invalidation}</div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-2">{r.position_rule}</div>
          <div className="text-slate-500">{r.next_validation}</div>
        </div>
      </div>
    ))}
  </div>
);

const TrackingTaskCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
    {rows.map((r) => (
      <div key={r.task} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={toneByImportance(r.priority)}>{r.priority}</Pill>
          <Pill tone={toneByStage(r.status)}>{r.status}</Pill>
        </div>
        <div className="mt-3 text-sm font-semibold text-white">{r.task}</div>
        <div className="mt-1 text-[11px] text-slate-500">{r.target}</div>
        <div className="mt-3 text-xs text-cyan-100">检查 {r.next_check}</div>
        <div className="mt-3 grid gap-2 text-[11px] leading-relaxed text-slate-400">
          <div><span className="text-emerald-300">升 </span>{r.upgrade_use}</div>
          <div><span className="text-rose-300">降 </span>{r.downgrade_use}</div>
        </div>
      </div>
    ))}
  </div>
);

const WarningCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
    {rows.map((r) => (
      <div key={`${r.target}-${r.watch_item}`} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={toneByImportance(r.decision_weight)}>{r.decision_weight}</Pill>
          <Pill>{r.next_data_date}</Pill>
        </div>
        <div className="mt-3 text-sm font-semibold text-white">{r.watch_item}</div>
        <div className="mt-0.5 text-xs text-slate-500">{r.target}</div>
        <div className="mt-3 text-xs text-slate-300">{r.current_state}</div>
        <div className="mt-3 grid gap-2 text-[11px] text-slate-400">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2"><span className="text-emerald-300">升 </span>{r.upgrade_if}</div>
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-2"><span className="text-rose-300">降 </span>{r.downgrade_if}</div>
        </div>
      </div>
    ))}
  </div>
);

const SignalCards: React.FC<{ rows: Row[]; kind: 'industry' | 'supply' | 'demand' | 'source' }> = ({ rows, kind }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
    {rows.map((r, idx) => {
      const title = r.indicator || r.object || r.demand_link || r.module || `信号 ${idx + 1}`;
      const value = r.value || r.current_signal || r.current_value || r.status || '--';
      const tag = r.confidence || r.decision_weight || r.status || r.importance || '';
      const next = r.next_check || r.next_step || '';
      return (
        <div key={`${title}-${idx}`} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            {tag ? <Pill tone={toneByImportance(tag) || toneByStage(tag)}>{tag}</Pill> : null}
            {r.source || r.source_type ? <Pill>{r.source || r.source_type}</Pill> : null}
          </div>
          <div className="mt-3 break-words text-sm font-semibold text-white">{title}</div>
          <div className="mt-1 break-words text-sm text-cyan-100">{value}</div>
          <div className="mt-3 space-y-1 text-[11px] leading-relaxed text-slate-500">
            {kind === 'industry' ? <div>{r.affected_links}</div> : null}
            {r.positive_threshold || r.positive_signal ? <div><span className="text-emerald-300">强 </span>{r.positive_threshold || r.positive_signal}</div> : null}
            {r.negative_threshold || r.risk_signal ? <div><span className="text-rose-300">弱 </span>{r.negative_threshold || r.risk_signal}</div> : null}
            {r.method ? <div>{r.method}</div> : null}
            {next ? <div>检查 {next}</div> : null}
          </div>
        </div>
      );
    })}
  </div>
);

const CompanyCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    {rows.map((r) => (
      <div key={r.symbol} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-white">{r.name}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{r.role}</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-white">{fmt(r.market_cap_yi)}亿</div>
            <div className="text-[10px] text-slate-500">市值</div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label="Q1营收" value={`${fmt(r.q1_revenue_yi)}亿`} />
          <Metric label="Q1净利" value={`${fmt(r.q1_net_profit_yi)}亿`} tone="text-emerald-200" />
          <Metric label="毛利率" value={pct(r.q1_gross_margin_pct)} tone="text-cyan-200" />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Pill>年化PE {fmt(r.annualized_q1_pe)}x</Pill>
          <Pill>收盘 {fmt(r.latest_close)}</Pill>
        </div>
        <div className="mt-3 text-xs leading-relaxed text-slate-400">{r.core_question}</div>
      </div>
    ))}
  </div>
);

const PeerCards: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
    {rows.map((r) => (
      <div key={r.ticker} className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <div className="text-sm font-semibold text-white">{r.name}</div>
        <div className="mt-0.5 text-[11px] text-slate-500">{r.ticker} · {r.latest_trade_date}</div>
        <div className="mt-3 text-lg font-bold text-cyan-100">{fmt(r.close)}</div>
        <div className="mt-3 space-y-2">
          <ScoreBar label="20日" value={num(r.ret_20d_pct)} max={90} color="bg-sky-400" suffix="%" />
          <ScoreBar label="低点以来" value={num(r.from_low_pct)} max={140} color="bg-orange-400" suffix="%" />
          <ScoreBar label="回撤" value={Math.abs(num(r.drawdown_from_high_pct))} max={10} color="bg-rose-400" suffix="%" />
        </div>
      </div>
    ))}
  </div>
);

const weatherRatioTone = (value?: string) => {
  const ratio = num(value);
  if (ratio > 0 && ratio < 0.65) return 'border-amber-500/50 bg-amber-500/15 text-amber-100';
  if (ratio > 1.35) return 'border-rose-500/50 bg-rose-500/15 text-rose-100';
  return 'border-slate-700 bg-slate-800 text-slate-300';
};

const factorTone = (scorePct?: string) => {
  const score = num(scorePct);
  if (score >= 80) return 'border-emerald-500/35 bg-emerald-500/10';
  if (score >= 60) return 'border-amber-500/35 bg-amber-500/10';
  return 'border-slate-800 bg-slate-950/50';
};

const detailRows = (rows: Row[], category: string) => rows.filter((r) => r.category === category);

const RubberMiniMetric: React.FC<{ row: Row }> = ({ row }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-2">
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] text-slate-500">{row.indicator}</span>
      <Pill tone={toneByStage(row.status)}>{row.status}</Pill>
    </div>
    <div className="mt-1 text-base font-bold text-cyan-100">{fmt(row.value)}{row.unit}</div>
    <div className="mt-1 text-[11px] leading-relaxed text-slate-500">{row.interpretation}</div>
  </div>
);

const RubberDetailCard: React.FC<{ factor?: Row; title: string; children: React.ReactNode; source?: string }> = ({ factor, title, children, source }) => (
  <div className="min-w-0 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <span>{title}</span>
          {factor ? (
            <InfoTip>
              <div className="font-semibold text-white">底层逻辑</div>
              <div className="mt-1">{factor.logic}</div>
              <div className="mt-2 font-semibold text-white">评分原则</div>
              <div className="mt-1">{factor.score_rule}</div>
              <div className="mt-2 font-semibold text-white">重点看什么</div>
              <div className="mt-1">{factor.watch_focus}</div>
            </InfoTip>
          ) : null}
        </div>
        {factor ? <div className="mt-1 text-xs text-slate-400">{factor.current_points}/{factor.max_points} 分 · 权重 {factor.weight_pct}% · {factor.status}</div> : null}
      </div>
      {factor ? <Pill tone={num(factor.score_pct) >= 80 ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200' : 'border-amber-500/40 bg-amber-500/10 text-amber-200'}>{fmt(factor.score_pct, 0)}%</Pill> : null}
    </div>
    <div className="mt-3">{children}</div>
    {source ? <div className="mt-2 text-[10px] text-slate-600">来源：{source}</div> : null}
  </div>
);

const summaryText = (summary: Row, key: string, legacyKey?: string) => summary[key] || (legacyKey ? summary[legacyKey] : '') || '';

const rubberDecisionText = (summary: Row) => {
  const conclusion = summaryText(summary, 'conclusion') || summaryText(summary, 'stage') || '研究观察';
  const action = summaryText(summary, 'action') || (summary.decision?.includes('不建仓') ? '当前不建仓' : '');
  return action ? `${conclusion} / ${action}` : conclusion;
};

const rubberChangeSummary = (history: Row[], currentSummary: Row) => {
  if (history.length < 2) {
    return {
      title: '暂无历史对比，已建立首条快照',
      lines: [
        `当前综合分 ${fmt(currentSummary.total_score, 0)}/${fmt(currentSummary.max_score || 100, 0)}`,
        `价格确认 ${fmt(summaryText(currentSummary, 'price_confirm_score', 'price_gate_score'), 0)}/${fmt(summaryText(currentSummary, 'price_confirm_max', 'price_gate_max'), 0)}`,
      ],
    };
  }

  const prev = history[history.length - 2];
  const last = history[history.length - 1];
  const factorLabels: Array<[keyof Row, string]> = [
    ['demand', '需求'],
    ['oil', '原油'],
    ['supply', '供给'],
    ['weather', '天气'],
    ['inventory', '库存'],
    ['macro', '宏观'],
  ];
  const biggest = factorLabels
    .map(([key, label]) => ({ label, prev: num(prev[key]), next: num(last[key]), delta: num(last[key]) - num(prev[key]) }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0];
  const prevPriceConfirm = `${fmt(prev.price_confirm, 0)}/2`;
  const lastPriceConfirm = `${fmt(last.price_confirm, 0)}/2`;
  const decisionLine = prev.decision === last.decision ? `结论不变：${last.decision}` : `结论变化：${prev.decision} → ${last.decision}`;

  return {
    title: `总分 ${fmt(prev.total_score, 0)} → ${fmt(last.total_score, 0)}`,
    lines: [
      biggest && Math.abs(biggest.delta) > 0 ? `主要变化：${biggest.label} ${fmt(biggest.prev, 0)} → ${fmt(biggest.next, 0)}` : '分项变化不大',
      prevPriceConfirm === lastPriceConfirm ? `价格确认不变：${lastPriceConfirm}` : `价格确认变化：${prevPriceConfirm} → ${lastPriceConfirm}`,
      decisionLine,
    ],
  };
};

const boolText = (value?: string | number | boolean, yes = '是', no = '否') => (value ? yes : no);

const RUBBER_RU_CSV_PATH = '/data/selection/long_term_trends/el_nino/rubber_ru_main_daily_2024_2026.csv';
const RUBBER_NR_CSV_PATH = '/data/selection/long_term_trends/el_nino/rubber_nr_main_daily_2024_2026.csv';
const RUBBER_SCORE_HISTORY_CSV_PATH = '/data/selection/long_term_trends/el_nino/rubber_score_history.csv';
const RUBBER_LONG_CYCLE_CSV_PATH = '/data/selection/long_term_trends/el_nino/rubber_worldbank_monthly_1960_2026.csv';

const parseSimpleCsv = (text: string): Row[] => {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];
  const splitCsvLine = (line: string) => {
    const cells: string[] = [];
    let current = '';
    let inQuote = false;
    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      if (char === '"') {
        if (inQuote && line[i + 1] === '"') {
          current += '"';
          i += 1;
        } else {
          inQuote = !inQuote;
        }
      } else if (char === ',' && !inQuote) {
        cells.push(current);
        current = '';
      } else {
        current += char;
      }
    }
    cells.push(current);
    return cells.map((cell) => cell.trim());
  };
  const headers = splitCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    const row: Row = {};
    headers.forEach((header, index) => {
      row[header] = values[index] ?? '';
    });
    return row;
  });
};

const buildPriceHistoryFromCsvRows = (ruRows: Row[], nrRows: Row[]): RubberPriceRow[] => {
  const nrByDate = new Map(nrRows.map((row) => [row.date, row]));
  return ruRows.slice(-160).map((row) => ({
    date: row.date,
    ru_close: row.close,
    nr_close: nrByDate.get(row.date)?.close || '',
  })).filter((row) => row.date && (row.ru_close || row.nr_close));
};

const extractNumberFromText = (text?: string, pattern?: RegExp) => {
  if (!text || !pattern) return null;
  const match = text.match(pattern);
  return match ? Number(match[1]) : null;
};

const buildPriceSnapshotFromMonitor = (monitor: Row[], priceHistory: RubberPriceRow[]) => {
  const latest = priceHistory[priceHistory.length - 1];
  const ruMonitor = monitor.find((row) => row.indicator === 'RU主连收盘');
  const nrMonitor = monitor.find((row) => row.indicator === 'NR主连收盘');
  const ruClose = latest?.ru_close || ruMonitor?.value || '';
  const nrClose = latest?.nr_close || nrMonitor?.value || '';
  const ruDrawdown = extractNumberFromText(ruMonitor?.interpretation, /距2024以来高点(-?\d+(?:\.\d+)?)/);
  const nrDrawdown = extractNumberFromText(nrMonitor?.interpretation, /距2024以来高点(-?\d+(?:\.\d+)?)/);
  const ruMa20 = extractNumberFromText(ruMonitor?.interpretation, /20日均线(\d+(?:\.\d+)?)/);
  const nrMa20 = extractNumberFromText(nrMonitor?.interpretation, /20日均线(\d+(?:\.\d+)?)/);
  const ruCloseNum = Number(ruClose);
  const nrCloseNum = Number(nrClose);

  return {
    ru: {
      close: ruClose,
      drawdown_from_high_pct: ruDrawdown,
      ma20: ruMa20,
      above_ma20: Number.isFinite(ruCloseNum) && Number.isFinite(ruMa20 || NaN) ? ruCloseNum > Number(ruMa20) : null,
      above_ma60: null,
    },
    nr: {
      close: nrClose,
      drawdown_from_high_pct: nrDrawdown,
      ma20: nrMa20,
      above_ma20: Number.isFinite(nrCloseNum) && Number.isFinite(nrMa20 || NaN) ? nrCloseNum > Number(nrMa20) : null,
      above_ma60: null,
    },
  };
};

const RubberTradeChart: React.FC<{ rows: Array<{ date: string; ru: number | null; nr: number | null }>; description: string }> = ({ rows, description }) => {
  const validValues = rows.flatMap((row) => [row.ru, row.nr]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!validValues.length) {
    return <div className="flex h-full items-center justify-center rounded-xl border border-slate-800 bg-slate-950/50 text-sm text-slate-500">暂无交易确认价格数据，请检查 RU/NR 历史文件或接口返回。</div>;
  }
  const rawMin = Math.min(...validValues);
  const rawMax = Math.max(...validValues);
  const spread = Math.max(rawMax - rawMin, 1);
  const domainMin = Math.floor(rawMin - Math.max(150, spread * 0.08));
  const domainMax = Math.ceil(rawMax + Math.max(150, spread * 0.08));
  return (
    <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950/40 p-2">
      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: 8, left: 4, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(value) => String(value).slice(5)} minTickGap={36} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={56} domain={[domainMin, domainMax]} />
            <Tooltip
              contentStyle={chartTooltipStyle}
              labelFormatter={(label) => `日期 ${label}`}
              formatter={(value: number | null, name: string) => [`${fmt(value, 0)} 元/吨`, name === 'ru' ? 'RU 主连' : 'NR 主连']}
            />
            <Legend wrapperStyle={{ color: '#cbd5e1', fontSize: 12 }} formatter={(value) => (value === 'ru' ? 'RU 主连' : 'NR 主连')} />
            <Line type="monotone" dataKey="ru" stroke="#f97316" strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="nr" stroke="#22d3ee" strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 text-[11px] text-slate-500">{description}</div>
    </div>
  );
};

const RubberLongCycleChart: React.FC<{ rows: Array<{ date: string; rss3: number | null; tsr20: number | null }>; description: string }> = ({ rows, description }) => {
  const validValues = rows.flatMap((row) => [row.rss3, row.tsr20]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!validValues.length) {
    return <div className="flex h-full items-center justify-center rounded-xl border border-slate-800 bg-slate-950/50 text-sm text-slate-500">长周期数据未接入</div>;
  }
  const rawMin = Math.min(...validValues);
  const rawMax = Math.max(...validValues);
  const spread = Math.max(rawMax - rawMin, 0.1);
  const domainMin = Math.max(0, rawMin - spread * 0.08);
  const domainMax = rawMax + spread * 0.08;
  return (
    <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950/40 p-2">
      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: 8, left: 4, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(value) => String(value).slice(0, 7)} minTickGap={42} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={52} domain={[domainMin, domainMax]} tickFormatter={(value) => `${fmt(value, 1)}`} />
            <Tooltip
              contentStyle={chartTooltipStyle}
              labelFormatter={(label) => `日期 ${label}`}
              formatter={(value: number | null, name: string) => [`${fmt(value, 2)} 美元/公斤`, name === 'rss3' ? 'RSS3' : 'TSR20']}
            />
            <Legend wrapperStyle={{ color: '#cbd5e1', fontSize: 12 }} formatter={(value) => (value === 'rss3' ? 'RSS3' : 'TSR20')} />
            <Line type="monotone" dataKey="rss3" stroke="#a78bfa" strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="tsr20" stroke="#34d399" strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 text-[11px] text-slate-500">{description}</div>
    </div>
  );
};

const RubberDashboardPanel: React.FC<{ data: NonNullable<TrendDashboardData['rubber_dashboard']> }> = ({ data }) => {
  const [fallbackPriceHistory, setFallbackPriceHistory] = useState<RubberPriceRow[]>([]);
  const [fallbackScoreHistory, setFallbackScoreHistory] = useState<Row[]>([]);
  const [fallbackLongCycleHistory, setFallbackLongCycleHistory] = useState<Row[]>([]);
  const [priceView, setPriceView] = useState<'trade' | 'long_cycle'>('trade');
  const [tradeRange, setTradeRange] = useState<'all' | '1y'>('all');
  const [longCycleRange, setLongCycleRange] = useState<'20y' | 'all'>('20y');
  const summary = data.summary || {};
  const factors = data.factor_scorecard || [];
  const monitor = data.monitor || [];
  const weather = data.weather || [];
  const triggerRules = data.trigger_rules || [];
  const scoreHistory = hasRows(data.score_history) ? (data.score_history || []) : fallbackScoreHistory;
  const effectivePriceHistory = hasPriceRows(data.price_history as RubberPriceRow[] | undefined) ? (data.price_history as RubberPriceRow[]) : fallbackPriceHistory;
  const effectiveLongCycleHistory = hasRows(data.long_cycle_price_history) ? (data.long_cycle_price_history || []) : fallbackLongCycleHistory;
  const monitorDerivedSnapshot = buildPriceSnapshotFromMonitor(monitor, effectivePriceHistory);
  const priceSnapshot = data.price_snapshot || {};
  const ruSnapshot = ((priceSnapshot.ru && Object.keys(priceSnapshot.ru).length ? priceSnapshot.ru : monitorDerivedSnapshot.ru) || {}) as Record<string, string | number | boolean | null>;
  const nrSnapshot = ((priceSnapshot.nr && Object.keys(priceSnapshot.nr).length ? priceSnapshot.nr : monitorDerivedSnapshot.nr) || {}) as Record<string, string | number | boolean | null>;
  const fullTradePriceData = effectivePriceHistory
    .map((r) => {
      const ru = Number(r.ru_close);
      const nr = Number(r.nr_close);
      return {
        date: r.date,
        ru: Number.isFinite(ru) ? ru : null,
        nr: Number.isFinite(nr) ? nr : null,
      };
    })
    .filter((r) => r.ru !== null || r.nr !== null);
  const tradePriceData = tradeRange === '1y' ? fullTradePriceData.slice(-250) : fullTradePriceData;
  const longCycleDataAll = effectiveLongCycleHistory
    .map((r) => {
      const rss3 = Number(r.rss3 ?? r.rubber_rss3_usd_kg);
      const tsr20 = Number(r.tsr20 ?? r.rubber_tsr20_usd_kg);
      return {
        date: r.date || r.month || r.year,
        rss3: Number.isFinite(rss3) ? rss3 : null,
        tsr20: Number.isFinite(tsr20) ? tsr20 : null,
      };
    })
    .filter((r) => r.date && (r.rss3 !== null || r.tsr20 !== null));
  const longCycleData = longCycleRange === '20y' ? longCycleDataAll.slice(-240) : longCycleDataAll;
  const totalScore = num(summary.total_score);
  const maxScore = num(summary.max_score) || 100;
  const decisionText = rubberDecisionText(summary);
  const priceConfirmScore = summaryText(summary, 'price_confirm_score', 'price_gate_score');
  const priceConfirmMax = summaryText(summary, 'price_confirm_max', 'price_gate_max') || '2';
  const priceConfirmState = summaryText(summary, 'price_confirm_status') || summaryText(summary, 'price_confirm_state', 'price_gate_status');
  const changeSummary = rubberChangeSummary(scoreHistory, summary);
  const byFactor = new Map(factors.map((r) => [r.factor, r]));
  const demand = detailRows(monitor, '需求');
  const inventory = detailRows(monitor, '库存');
  const oil = detailRows(monitor, '原油/合成胶');
  const supply = detailRows(monitor, '供给');
  const macroRows = detailRows(monitor, '宏观');
  const currentStage = summaryText(summary, 'stage') || '研究观察';
  const nextStage = summaryText(summary, 'next_stage') || '小仓试错';
  const nextStageConditions = summaryText(summary, 'next_stage_conditions', 'buy_threshold') || '总分>=75、价格确认=2/2、天气或库存连续确认';
  const downgradeConditions = summaryText(summary, 'downgrade_conditions', 'reduce_threshold') || '总分<65、RU/NR跌破60日线、库存转累、天气扰动消失';
  const blockReason = summaryText(summary, 'block_reason') || 'RU/NR 尚未同步强确认';
  const nextTrigger = summaryText(summary, 'next_trigger') || 'RU/NR 同步突破或回踩不破';
  const priceConfirmDisplayScore = String(priceSnapshot.price_confirm_score || summaryText(summary, 'price_confirm_score', 'price_gate_score') || '--');
  const priceConfirmDisplayMax = String(priceSnapshot.price_confirm_max || summaryText(summary, 'price_confirm_max', 'price_gate_max') || '--');
  const priceConfirmDisplayState = String(priceSnapshot.price_confirm_state || summaryText(summary, 'price_confirm_state', 'price_gate_status') || '--');
  const latestLongCycle = longCycleDataAll[longCycleDataAll.length - 1];
  const rss3Peak = longCycleDataAll.reduce((max, row) => (row.rss3 !== null && row.rss3 > max ? row.rss3 : max), 0);
  const rss3VsPeakPct = latestLongCycle?.rss3 && rss3Peak ? (latestLongCycle.rss3 / rss3Peak) * 100 : null;
  const peakMultiple = latestLongCycle?.rss3 && rss3Peak ? rss3Peak / latestLongCycle.rss3 : null;

  useEffect(() => {
    let cancelled = false;
    const loadFallbacks = async () => {
      if (!hasPriceRows(data.price_history as RubberPriceRow[] | undefined)) {
        try {
          const [ruRes, nrRes] = await Promise.all([fetch(RUBBER_RU_CSV_PATH), fetch(RUBBER_NR_CSV_PATH)]);
          if (ruRes.ok && nrRes.ok) {
            const [ruText, nrText] = await Promise.all([ruRes.text(), nrRes.text()]);
            if (!cancelled) {
              setFallbackPriceHistory(buildPriceHistoryFromCsvRows(parseSimpleCsv(ruText), parseSimpleCsv(nrText)));
            }
          }
        } catch (error) {
          console.error('Load rubber price history fallback error:', error);
        }
      }
      if (!hasRows(data.score_history)) {
        try {
          const res = await fetch(RUBBER_SCORE_HISTORY_CSV_PATH);
          if (res.ok) {
            const text = await res.text();
            if (!cancelled) {
              setFallbackScoreHistory(parseSimpleCsv(text));
            }
          }
        } catch (error) {
          console.error('Load rubber score history fallback error:', error);
        }
      }
      if (!hasRows(data.long_cycle_price_history)) {
        try {
          const res = await fetch(RUBBER_LONG_CYCLE_CSV_PATH);
          if (res.ok) {
            const text = await res.text();
            if (!cancelled) {
              setFallbackLongCycleHistory(parseSimpleCsv(text));
            }
          }
        } catch (error) {
          console.error('Load rubber long cycle history fallback error:', error);
        }
      }
    };
    loadFallbacks();
    return () => {
      cancelled = true;
    };
  }, [data.price_history, data.score_history, data.long_cycle_price_history]);

  return (
    <div className="space-y-4">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-950/40 via-slate-900 to-slate-950 p-4 shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-3xl font-black text-white">厄尔尼诺-橡胶</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Pill tone="border-cyan-500/40 bg-cyan-500/10 text-cyan-100">{summaryText(summary, 'conclusion') || '研究观察'}</Pill>
                <Pill tone="border-slate-600 bg-slate-800/80 text-slate-100">{summaryText(summary, 'action') || '当前不建仓'}</Pill>
                <Pill tone="border-amber-500/40 bg-amber-500/10 text-amber-200">价格确认 {priceConfirmState || '未完成'}</Pill>
              </div>
              <div className="mt-3 text-sm text-slate-300">{decisionText}</div>
            </div>
            <div className="rounded-2xl border border-amber-400/20 bg-slate-950/40 px-4 py-3 text-right">
              <div className="text-[11px] text-slate-500">综合分</div>
              <div className="mt-1 text-4xl font-black text-amber-100">{fmt(totalScore, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(maxScore, 0)}</span></div>
              <div className="mt-2 text-[11px] text-slate-500">数据更新：{summaryText(summary, 'data_updated_at') || '--'}</div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="价格确认" value={`${fmt(priceConfirmScore, 0)}/${fmt(priceConfirmMax, 0)}，${priceConfirmState || '--'}`} tone="text-amber-200" />
            <Metric label="卡住原因" value={blockReason} tone="text-rose-200" />
            <Metric label="下一触发" value={nextTrigger} tone="text-cyan-200" />
            <Metric label="天气分" value={`${fmt(summary.weather_score, 0)}/${fmt(summary.weather_max_score, 0)} · ${summary.weather_status || '--'}`} tone="text-emerald-200" />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="text-xs text-slate-500">本次变化摘要</div>
          <div className="mt-2 text-lg font-semibold text-white">{changeSummary.title}</div>
          <div className="mt-3 space-y-2">
            {changeSummary.lines.map((line) => (
              <div key={line} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm text-slate-300">{line}</div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="grid gap-3 lg:grid-cols-[repeat(4,minmax(0,1fr))_minmax(260px,1fr)]">
          <Metric label="当前阶段" value={currentStage} tone="text-white" />
          <Metric label="下一阶段" value={nextStage} tone="text-cyan-100" />
          <Metric label="进入下一阶段条件" value={nextStageConditions} tone="text-emerald-200" />
          <Metric label="恶化 / 降级条件" value={downgradeConditions} tone="text-rose-200" />
          <details className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-300">
            <summary className="cursor-pointer list-none font-semibold text-white">展开完整规则</summary>
            <div className="mt-3 space-y-2">
              {triggerRules.map((r) => (
                <div key={r.stage} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2">
                  <div className="text-xs font-semibold text-cyan-100">{r.stage}</div>
                  <div className="mt-1 text-[11px] leading-relaxed text-slate-400">{r.conditions}</div>
                  <div className="mt-1 text-[11px] text-slate-300">{r.allowed_action}</div>
                  <div className="mt-1 text-[11px] text-rose-300">降级条件：{r.downgrade_condition || r.invalidation || '--'}</div>
                </div>
              ))}
            </div>
          </details>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {factors.map((r) => (
          <div key={r.factor} className={`min-w-0 rounded-xl border p-3 ${factorTone(r.score_pct)}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <div className="truncate text-sm font-semibold text-white">{r.factor}</div>
                <InfoTip>
                  <div className="font-semibold text-white">底层逻辑</div>
                  <div className="mt-1">{r.logic}</div>
                  <div className="mt-2 font-semibold text-white">评分原则</div>
                  <div className="mt-1">{r.score_rule}</div>
                  <div className="mt-2 font-semibold text-white">重点看什么</div>
                  <div className="mt-1">{r.watch_focus}</div>
                </InfoTip>
              </div>
              <span className="shrink-0 text-[10px] text-slate-400">{r.weight_pct}%</span>
            </div>
            <div className="mt-2 text-2xl font-black text-cyan-100">{r.current_points}<span className="text-xs font-medium text-slate-500">/{r.max_points}</span></div>
            <div className="mt-2">
              <ScoreBar label={r.status || ''} value={num(r.current_points)} max={num(r.max_points) || 1} color={num(r.score_pct) >= 80 ? 'bg-emerald-400' : num(r.score_pct) >= 60 ? 'bg-amber-400' : 'bg-slate-500'} />
            </div>
            <div className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-slate-500">{r.main_evidence}</div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.75fr)]">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-white">价格确认模块</div>
              <div className="mt-1 text-[11px] text-slate-500">
                {priceView === 'trade'
                  ? 'RU/NR = 国内期货，用于买点与价格确认'
                  : 'RSS3/TSR20 = 国际天然橡胶价格，用于判断长周期位置，不直接等同交易价格'}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => setPriceView('trade')} className={`rounded-full border px-3 py-1 text-xs ${priceView === 'trade' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>交易确认</button>
              <button type="button" onClick={() => setPriceView('long_cycle')} className={`rounded-full border px-3 py-1 text-xs ${priceView === 'long_cycle' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>长周期位置</button>
            </div>
          </div>
          <div className="mb-3 flex flex-wrap gap-2">
            {priceView === 'trade' ? (
              <>
                <button type="button" onClick={() => setTradeRange('all')} className={`rounded-full border px-3 py-1 text-[11px] ${tradeRange === 'all' ? 'border-amber-500/50 bg-amber-500/10 text-amber-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>全部 RU/NR</button>
                <button type="button" onClick={() => setTradeRange('1y')} className={`rounded-full border px-3 py-1 text-[11px] ${tradeRange === '1y' ? 'border-amber-500/50 bg-amber-500/10 text-amber-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>近1年</button>
              </>
            ) : (
              <>
                <button type="button" onClick={() => setLongCycleRange('20y')} className={`rounded-full border px-3 py-1 text-[11px] ${longCycleRange === '20y' ? 'border-violet-500/50 bg-violet-500/10 text-violet-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>20年</button>
                <button type="button" onClick={() => setLongCycleRange('all')} className={`rounded-full border px-3 py-1 text-[11px] ${longCycleRange === 'all' ? 'border-violet-500/50 bg-violet-500/10 text-violet-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>全部</button>
              </>
            )}
          </div>
          <div className="h-[340px] w-full">
            {priceView === 'trade' ? (
              <RubberTradeChart
                rows={tradePriceData}
                description={`区间：${tradePriceData[0]?.date || '--'} ~ ${tradePriceData[tradePriceData.length - 1]?.date || '--'}。鼠标悬停可查看任一日期 RU/NR 价格。`}
              />
            ) : (
              <RubberLongCycleChart
                rows={longCycleData}
                description={`区间：${longCycleData[0]?.date || '--'} ~ ${longCycleData[longCycleData.length - 1]?.date || '--'}。用来判断天然橡胶是否处于历史高位，不直接替代国内期货交易价。`}
              />
            )}
          </div>
          <div className="mt-2 text-[11px] text-slate-500">
            {priceView === 'trade'
              ? '判定逻辑：RU 和 NR 要同步突破/回踩不破；只有 RU 强、NR 不跟，容易只是资金或交割结构行情。'
              : '长周期只回答“历史位置高不高”，不直接回答“今天能不能买”。'}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          {priceView === 'trade' ? (
            <>
              <div className="mb-3 text-sm font-semibold text-white">交易确认判断卡</div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="text-lg font-semibold text-amber-200">价格确认：{priceConfirmDisplayScore}/{priceConfirmDisplayMax}，{priceConfirmState || '未完成'}</div>
                <div className="mt-3 space-y-2 text-sm text-slate-300">
                  <div>RU：<span className="font-semibold text-white">{fmt(ruSnapshot.close, 0)}</span>，站上20/60日 <span className="text-emerald-200">{`${ruSnapshot.above_ma20 == null ? '待接入' : boolText(ruSnapshot.above_ma20)}/${ruSnapshot.above_ma60 == null ? '待接入' : boolText(ruSnapshot.above_ma60)}`}</span>，距高点 <span className="text-slate-100">{fmt(ruSnapshot.drawdown_from_high_pct, 1)}%</span></div>
                  <div>NR：<span className="font-semibold text-white">{fmt(nrSnapshot.close, 0)}</span>，站上20/60日 <span className="text-emerald-200">{`${nrSnapshot.above_ma20 == null ? '待接入' : boolText(nrSnapshot.above_ma20)}/${nrSnapshot.above_ma60 == null ? '待接入' : boolText(nrSnapshot.above_ma60)}`}</span>，距高点 <span className="text-slate-100">{fmt(nrSnapshot.drawdown_from_high_pct, 1)}%</span></div>
                  <div>判断：<span className="text-cyan-100">{priceConfirmDisplayState || '价格偏强，但未同步突破'}</span></div>
                  <div>下一触发：<span className="text-white">{nextTrigger}</span></div>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="mb-3 text-sm font-semibold text-white">长周期位置卡</div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                {latestLongCycle ? (
                  <div className="space-y-2 text-sm text-slate-300">
                    <div>RSS3 当前约为 2011 高点的 <span className="font-semibold text-white">{fmt(rss3VsPeakPct, 0)}%</span></div>
                    <div>2011 极端高点约为当前的 <span className="font-semibold text-white">{fmt(peakMultiple, 1)} 倍</span></div>
                    <div>当前月度价格：RSS3 <span className="text-violet-200">{fmt(latestLongCycle.rss3, 2)}</span> / TSR20 <span className="text-emerald-200">{fmt(latestLongCycle.tsr20, 2)}</span> 美元/公斤</div>
                    <div className="pt-2 text-slate-400">结论：当前不是历史极高，但若要复制 2011 年那种极端高位，仍需要需求、库存、天气、流动性共振。</div>
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">长周期数据未接入</div>
                )}
              </div>
            </>
          )}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <RubberDetailCard factor={byFactor.get('轮胎/汽车需求')} title="1. 轮胎/汽车需求" source={demand[0]?.source}>
          <div className="grid gap-2 sm:grid-cols-2">{demand.map((r) => <RubberMiniMetric key={r.indicator} row={r} />)}</div>
        </RubberDetailCard>

        <RubberDetailCard factor={byFactor.get('原油/合成橡胶')} title="2. 原油 / 合成橡胶" source={oil[0]?.source}>
          <div className="grid gap-2 sm:grid-cols-2">{oil.map((r) => <RubberMiniMetric key={r.indicator} row={r} />)}</div>
        </RubberDetailCard>

        <RubberDetailCard factor={byFactor.get('天然橡胶供给周期')} title="3. 天然橡胶供给周期" source={supply[0]?.source}>
          <div className="grid gap-2 sm:grid-cols-2">{supply.map((r) => <RubberMiniMetric key={r.indicator} row={r} />)}</div>
        </RubberDetailCard>

        <RubberDetailCard factor={byFactor.get('天气/厄尔尼诺落地')} title="4. 天气 / 厄尔尼诺落地" source="Open-Meteo Archive/Forecast">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="px-2 py-2">产区</th>
                  <th className="px-2 py-2">倍率</th>
                  <th className="px-2 py-2">30日/常年</th>
                  <th className="px-2 py-2">14日预报</th>
                  <th className="px-2 py-2">判定</th>
                </tr>
              </thead>
              <tbody>
                {weather.map((r) => (
                  <tr key={r.region} className="border-t border-slate-800 text-slate-300">
                    <td className="px-2 py-2 font-medium text-white">{r.region}</td>
                    <td className="px-2 py-2"><Pill tone={weatherRatioTone(r.rain_ratio_vs_normal)}>{fmt(r.rain_ratio_vs_normal, 2)}x</Pill></td>
                    <td className="px-2 py-2">{fmt(r.actual_30d_rain_mm)} / {fmt(r.baseline_1991_2020_same_window_rain_mm)}mm</td>
                    <td className="px-2 py-2">{fmt(r.forecast_14d_rain_mm)}mm</td>
                    <td className="px-2 py-2">{r.weather_status === '天气正常' ? <span className="text-slate-400">中性</span> : <span className="text-amber-200">供给扰动利多</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </RubberDetailCard>

        <RubberDetailCard factor={byFactor.get('库存/仓单')} title="5. 库存 / 仓单" source={inventory[0]?.source}>
          <div className="grid gap-2 sm:grid-cols-2">{inventory.map((r) => <RubberMiniMetric key={r.indicator} row={r} />)}</div>
        </RubberDetailCard>

        <RubberDetailCard factor={byFactor.get('宏观流动性/商品周期')} title="6. 宏观流动性 / 商品周期" source={macroRows[0]?.source}>
          <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-[11px] text-slate-400">宏观只做加减分，不单独构成买入理由。</div>
          <div className="grid gap-2 sm:grid-cols-2">{macroRows.map((r) => <RubberMiniMetric key={r.indicator} row={r} />)}</div>
        </RubberDetailCard>
      </section>
    </div>
  );
};

const splitSourceUrls = (value?: string) => (value || '').split('|').map((item) => item.trim()).filter(Boolean);

const storageFactorTone = (score?: string) => {
  const n = num(score);
  if (n >= 85) return 'border-emerald-500/35 bg-emerald-500/10';
  if (n >= 70) return 'border-amber-500/35 bg-amber-500/10';
  return 'border-slate-800 bg-slate-950/50';
};

const storageChangeSummary = (history: Row[], summary: Row) => {
  if (history.length < 2) {
    return {
      title: '本次建立监控基线',
      lines: [
        `行业趋势分 ${fmt(summary.industry_trend_score, 0)}/${fmt(summary.industry_trend_max, 0)}`,
        `A股可操作分 ${fmt(summary.a_share_operability_score, 0)}/${fmt(summary.a_share_operability_max, 0)}`,
        `结论：${summary.conclusion || '--'}`,
      ],
    };
  }
  const prev = history[history.length - 2];
  const last = history[history.length - 1];
  const factors: Array<[keyof Row, string]> = [
    ['price_cycle', '价格周期'],
    ['ai_demand', 'AI需求'],
    ['supply_constraint', '供给约束'],
    ['inventory_cycle', '库存周期'],
    ['tech_upgrade', '技术升级'],
    ['overseas_validation', '海外验证'],
  ];
  const biggest = factors
    .map(([key, label]) => ({ label, prev: num(prev[key]), next: num(last[key]), delta: num(last[key]) - num(prev[key]) }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0];
  return {
    title: `行业 ${fmt(prev.industry_trend_score, 0)} → ${fmt(last.industry_trend_score, 0)} / A股 ${fmt(prev.a_share_operability_score, 0)} → ${fmt(last.a_share_operability_score, 0)}`,
    lines: [
      biggest && Math.abs(biggest.delta) > 0 ? `主要变化：${biggest.label} ${fmt(biggest.prev, 0)} → ${fmt(biggest.next, 0)}` : '主要因子暂无明显变化',
      prev.conclusion === last.conclusion ? `结论不变：${last.conclusion}` : `结论变化：${prev.conclusion} → ${last.conclusion}`,
      `当前结论：${summary.conclusion || last.conclusion || '--'}`,
    ],
  };
};

const storageFactorMeaning = (row: Row) => {
  if (row.factor === '存储价格周期') return '涨价是否还在延续';
  if (row.factor === 'AI需求强度') return 'AI基建是否真的拉需求';
  if (row.factor === '供给约束') return '供给是否仍然紧';
  if (row.factor === '库存周期') return '补库有没有订单和现金流支撑';
  if (row.factor === '技术结构升级') return '是不是从消费存储升级到服务器/HBM/eSSD';
  if (row.factor === '海外原厂验证') return '全球原厂和股价是否验证景气';
  return row.watch_focus || '';
};

const StorageEvidenceGrid: React.FC<{ row: Row }> = ({ row }) => {
  const items = [1, 2, 3].map((idx) => ({
    label: row[`evidence_${idx}_label`],
    value: row[`evidence_${idx}_value`],
    meaning: row[`evidence_${idx}_meaning`],
  })).filter((item) => item.label || item.value || item.meaning);
  if (!items.length) return null;
  return (
    <div className="mt-3 grid gap-2">
      {items.map((item) => (
        <div key={item.label} className="grid grid-cols-[78px_minmax(0,1fr)] gap-2 rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2">
          <div className="text-[11px] text-slate-500">{item.label}</div>
          <div className="min-w-0">
            <div className="break-words text-sm font-semibold text-cyan-100">{item.value}</div>
            <div className="mt-0.5 break-words text-[11px] text-slate-400">{item.meaning}</div>
          </div>
        </div>
      ))}
    </div>
  );
};

const StorageDashboardPanel: React.FC<{ dashboard: TrendDashboardData }> = ({ dashboard }) => {
  const storage = dashboard.storage_dashboard || {};
  const summary = storage.summary || {};
  const factorRows = storage.factor_scorecard || [];
  const operabilityRows = (storage.operability_summary && storage.operability_summary.length ? storage.operability_summary : dashboard.decision_matrix) || [];
  const scoreHistory = storage.score_history || [];
  const changeSummary = storageChangeSummary(scoreHistory, summary);

  return (
    <div className="space-y-4">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <div className="rounded-2xl border border-cyan-500/25 bg-gradient-to-br from-cyan-950/40 via-slate-900 to-slate-950 p-4 shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-3xl font-black text-white">AI 存储 / 内存涨价</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {summary.industry_status ? <Pill tone="border-emerald-500/40 bg-emerald-500/10 text-emerald-200">{summary.industry_status}</Pill> : null}
                {summary.operability_state ? <Pill tone="border-amber-500/40 bg-amber-500/10 text-amber-200">{summary.operability_state}</Pill> : null}
                {summary.conclusion ? <Pill tone="border-cyan-500/40 bg-cyan-500/10 text-cyan-100">{summary.conclusion}</Pill> : null}
              </div>
              <div className="mt-3 text-sm text-slate-300">{summary.current_view || dashboard.verdict.position}</div>
            </div>
            <div className="grid min-w-[240px] gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-emerald-500/20 bg-slate-950/40 px-4 py-3">
                <div className="text-[11px] text-slate-500">行业趋势分</div>
                <div className="mt-1 text-4xl font-black text-emerald-100">{fmt(summary.industry_trend_score, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(summary.industry_trend_max, 0)}</span></div>
              </div>
              <div className="rounded-2xl border border-amber-500/20 bg-slate-950/40 px-4 py-3">
                <div className="text-[11px] text-slate-500">A股可操作分</div>
                <div className="mt-1 text-4xl font-black text-amber-100">{fmt(summary.a_share_operability_score, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(summary.a_share_operability_max, 0)}</span></div>
              </div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="当前结论" value={summary.conclusion || '--'} tone="text-cyan-100" />
            <Metric label="卡住原因" value={summary.block_reason || '--'} tone="text-rose-200" />
            <Metric label="下一触发" value={summary.next_trigger || '--'} tone="text-emerald-200" />
            <Metric label="数据更新时间" value={summary.updated_at || '--'} tone="text-slate-100" />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="text-xs text-slate-500">变化摘要</div>
          <div className="mt-2 text-lg font-semibold text-white">{changeSummary.title}</div>
          <div className="mt-3 space-y-2">
            {changeSummary.lines.map((line) => (
              <div key={line} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm text-slate-300">{line}</div>
            ))}
          </div>
        </div>
      </section>

      {hasRows(factorRows) ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {factorRows.map((row) => (
            <div key={row.factor} className={`min-w-0 rounded-2xl border p-4 ${storageFactorTone(row.score_pct)}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="truncate text-sm font-semibold text-white">{row.factor}</div>
                  <InfoTip>
                    <div className="font-semibold text-white">底层逻辑</div>
                    <div className="mt-1">{row.logic}</div>
                    <div className="mt-2 font-semibold text-white">评分原则</div>
                    <div className="mt-1">{row.score_rule}</div>
                    <div className="mt-2 font-semibold text-white">重点看什么</div>
                    <div className="mt-1">{row.watch_focus}</div>
                  </InfoTip>
                </div>
                <Pill tone={toneByStage(row.status)}>{row.status}</Pill>
              </div>
              <div className="mt-3 flex items-end justify-between gap-3">
                <div>
                  <div className="text-3xl font-black text-cyan-100">{row.current_points}<span className="text-xs font-medium text-slate-500">/{row.max_points}</span></div>
                  <div className="mt-1 text-[11px] text-slate-500">权重 {row.weight_pct}%</div>
                </div>
                <div className="max-w-[160px] text-right text-xs leading-relaxed text-slate-300">{storageFactorMeaning(row)}</div>
              </div>
              <StorageEvidenceGrid row={row} />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-3 text-[11px] text-slate-500">
                <span>Source 收在说明里</span>
                {splitSourceUrls(row.source_url).length ? <span>{splitSourceUrls(row.source_url).length} 个来源</span> : null}
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {hasRows(operabilityRows) ? (
        <SectionCard title="A股可操作分 / 标的池" icon={<BrainCircuit className="h-4 w-4 text-cyan-300" />}>
          <div className="mb-4 grid gap-3 lg:grid-cols-3">
            <Metric label="整体动作" value={summary.operability_state || '--'} tone="text-amber-200" />
            <Metric label="当前结论" value={summary.conclusion || '--'} tone="text-cyan-100" />
            <Metric label="为什么不能买" value={summary.block_reason || '--'} tone="text-rose-200" />
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2">标的</th>
                  <th className="px-3 py-2">角色</th>
                  <th className="px-3 py-2">总分 / 阶段</th>
                  <th className="px-3 py-2">当前动作</th>
                  <th className="px-3 py-2">触发条件</th>
                  <th className="px-3 py-2">失效条件</th>
                  <th className="px-3 py-2">财报验证要点</th>
                </tr>
              </thead>
              <tbody>
                {operabilityRows.map((row) => (
                  <tr key={row.symbol || row.name} className="border-t border-slate-800 align-top text-slate-300">
                    <td className="px-3 py-3">
                      <div className="font-semibold text-white">{row.name}</div>
                      {row.base_pe ? <div className="mt-1 text-xs text-slate-500">Base PE {fmt(row.base_pe)}x</div> : null}
                    </td>
                    <td className="px-3 py-3">
                      <div>{row.role || row.tracking_role || '--'}</div>
                      {row.validation_state ? <div className="mt-1 text-xs text-slate-500">{row.validation_state}</div> : null}
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-semibold text-cyan-100">{fmt(row.total_score, 0)}</div>
                      <div className="mt-1"><Pill tone={toneByStage(row.stage)}>{row.stage || '--'}</Pill></div>
                    </td>
                    <td className="px-3 py-3 text-amber-100">{row.current_action || '--'}</td>
                    <td className="px-3 py-3 text-emerald-200">{row.trigger_condition || row.entry_condition || '--'}</td>
                    <td className="px-3 py-3 text-rose-200">{row.failure_condition || row.invalidation || '--'}</td>
                    <td className="px-3 py-3 text-slate-400">{row.earnings_validation_focus || row.next_validation || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      ) : null}

      {hasRows(dashboard.a_share_price_history) || hasRows(dashboard.global_peer_history) ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {hasRows(dashboard.a_share_price_history) ? (
            <SectionCard title="A股相对收益" icon={<TrendingUp className="h-4 w-4 text-cyan-300" />}>
              <HistoryLineChart rows={dashboard.a_share_price_history || []} idKey="symbol" description="从当前样本起点归一化为 0%，看存储核心票谁更强、谁先走弱。" />
            </SectionCard>
          ) : null}
          {hasRows(dashboard.global_peer_history) ? (
            <SectionCard title="海外原厂验证" icon={<BarChart3 className="h-4 w-4 text-blue-300" />}>
              <HistoryLineChart rows={dashboard.global_peer_history || []} idKey="ticker" description="海外原厂从同一起点归一化，看全球景气是否还被股价确认。" />
            </SectionCard>
          ) : null}
        </div>
      ) : null}

      {hasRows(dashboard.a_share_price_stage) || hasRows(dashboard.valuation_scenarios) ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {hasRows(dashboard.a_share_price_stage) ? (
            <SectionCard title="A股价格阶段" icon={<TrendingUp className="h-4 w-4 text-rose-300" />}>
              <PriceStageChart rows={dashboard.a_share_price_stage || []} />
            </SectionCard>
          ) : null}
          {hasRows(dashboard.valuation_scenarios) ? (
            <SectionCard title="估值压力" icon={<Gauge className="h-4 w-4 text-violet-300" />}>
              <ValuationChart rows={dashboard.valuation_scenarios || []} />
            </SectionCard>
          ) : null}
        </div>
      ) : null}

      {hasRows(dashboard.global_peer_stage) ? (
        <SectionCard title="海外原厂阶段卡" icon={<BarChart3 className="h-4 w-4 text-blue-300" />}>
          <PeerCards rows={dashboard.global_peer_stage || []} />
        </SectionCard>
      ) : null}

      {hasRows(dashboard.company_validation) ? (
        <SectionCard title="财报验证" icon={<ShieldAlert className="h-4 w-4 text-amber-300" />}>
          <CompanyValidationCards rows={dashboard.company_validation || []} />
        </SectionCard>
      ) : null}

      <details className="rounded-2xl border border-slate-800 bg-slate-900/50">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-300">原始信号 / 数据源</summary>
        <div className="space-y-4 border-t border-slate-800 p-4">
          {hasRows(dashboard.price_radar) ? <PriceRadarCards rows={dashboard.price_radar || []} /> : null}
          {hasRows(dashboard.data_source_matrix) ? <SignalCards rows={dashboard.data_source_matrix || []} kind="source" /> : null}
        </div>
      </details>
    </div>
  );
};

const agriFactorTone = (score?: string) => {
  const n = num(score);
  if (n >= 75) return 'border-emerald-500/35 bg-emerald-500/10';
  if (n >= 55) return 'border-amber-500/35 bg-amber-500/10';
  return 'border-slate-800 bg-slate-950/50';
};

const AgriBasketPriceChart: React.FC<{ rows: Row[] }> = ({ rows }) => {
  const data = rows.map((row) => ({
    name: row.category,
    d20: num(row.change_20d_pct),
    d60: num(row.change_60d_pct),
    status: row.price_status,
    split: row.split_research,
  }));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <Pill tone="border-cyan-500/30 bg-cyan-500/10 text-cyan-200">蓝色：近20日变化</Pill>
        <Pill tone="border-emerald-500/30 bg-emerald-500/10 text-emerald-200">绿色：近60日变化</Pill>
        <InfoTip>
          <div className="font-semibold text-white">怎么看</div>
          <div className="mt-1">这个图先筛品类，不直接给股票结论。20日和60日同时为正且幅度较大，说明该品类更值得后续拆成单品页。</div>
        </InfoTip>
      </div>
      <div className="h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 8, right: 18, bottom: 8, left: 8 }} barCategoryGap={10}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
            <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
            <YAxis type="category" dataKey="name" width={72} tick={{ fill: '#cbd5e1', fontSize: 12 }} />
            <Tooltip contentStyle={chartTooltipStyle} formatter={(value: number, name: string) => [`${fmt(value)}%`, name === 'd20' ? '近20日' : '近60日']} />
            <Bar dataKey="d20" name="近20日" fill="#38bdf8" radius={[0, 4, 4, 0]} />
            <Bar dataKey="d60" name="近60日" fill="#34d399" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const AgriBasketPanel: React.FC<{ dashboard: TrendDashboardData }> = ({ dashboard }) => {
  const basket = dashboard.agri_basket_dashboard || {};
  const summary = basket.summary || {};
  const factors = basket.factor_scorecard || [];
  const prices = basket.price_basket || [];
  const watchlist = basket.watchlist || [];

  return (
    <div className="space-y-4">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <div className="rounded-2xl border border-emerald-500/25 bg-gradient-to-br from-emerald-950/35 via-slate-900 to-slate-950 p-4 shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-3xl font-black text-white">厄尔尼诺-农产品价格篮子</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Pill tone="border-amber-500/40 bg-amber-500/10 text-amber-200">{summary.conclusion || '观察中'}</Pill>
                <Pill tone="border-cyan-500/40 bg-cyan-500/10 text-cyan-100">最强：{summary.strongest_category || '--'}</Pill>
                <Pill>数据：{summary.data_status || '--'}</Pill>
              </div>
              <div className="mt-3 text-sm text-slate-300">{summary.current_action || dashboard.verdict.position}</div>
            </div>
            <div className="grid min-w-[240px] gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-emerald-500/20 bg-slate-950/40 px-4 py-3">
                <div className="text-[11px] text-slate-500">农产品传导分</div>
                <div className="mt-1 text-4xl font-black text-emerald-100">{fmt(summary.transmission_score, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(summary.transmission_max, 0)}</span></div>
              </div>
              <div className="rounded-2xl border border-cyan-500/20 bg-slate-950/40 px-4 py-3">
                <div className="text-[11px] text-slate-500">价格确认</div>
                <div className="mt-1 text-4xl font-black text-cyan-100">{fmt(summary.price_confirm_score, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(summary.price_confirm_max, 0)}</span></div>
              </div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="当前结论" value={summary.conclusion || '--'} tone="text-cyan-100" />
            <Metric label="预备拆分" value={summary.split_research_needed || '--'} tone="text-amber-200" />
            <Metric label="下一触发" value={summary.next_trigger || '--'} tone="text-emerald-200" />
            <Metric label="更新时间" value={summary.updated_at || '--'} tone="text-slate-100" />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="text-xs text-slate-500">变化摘要</div>
          <div className="mt-2 text-lg font-semibold text-white">{summary.change_summary || '本次建立监控基线'}</div>
          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-400">{summary.source_note || '后续可替换为实时价格源。'}</div>
        </div>
      </section>

      {hasRows(factors) ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {factors.map((row) => (
            <div key={row.factor} className={`min-w-0 rounded-2xl border p-4 ${agriFactorTone(row.score_pct)}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="truncate text-sm font-semibold text-white">{row.factor}</div>
                  <InfoTip>
                    <div className="font-semibold text-white">底层逻辑</div>
                    <div className="mt-1">{row.logic}</div>
                    <div className="mt-2 font-semibold text-white">评分原则</div>
                    <div className="mt-1">{row.score_rule}</div>
                    <div className="mt-2 font-semibold text-white">重点看什么</div>
                    <div className="mt-1">{row.watch_focus}</div>
                    <div className="mt-2 text-slate-500">Source：{row.source || '--'}</div>
                  </InfoTip>
                </div>
                <Pill tone={toneByStage(row.status)}>{row.status}</Pill>
              </div>
              <div className="mt-3 flex items-end justify-between gap-3">
                <div>
                  <div className="text-3xl font-black text-cyan-100">{row.current_points}<span className="text-xs font-medium text-slate-500">/{row.max_points}</span></div>
                  <div className="mt-1 text-[11px] text-slate-500">权重 {row.weight_pct}%</div>
                </div>
                <div className="text-right text-xs text-slate-400">{fmt(row.score_pct, 0)}%</div>
              </div>
              <div className="mt-3 grid gap-2">
                {[row.evidence_1, row.evidence_2, row.evidence_3].filter(Boolean).map((item) => (
                  <div key={item} className="rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2 text-xs leading-relaxed text-slate-300">{item}</div>
                ))}
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {hasRows(prices) ? (
        <SectionCard title="价格篮子筛选" icon={<Activity className="h-4 w-4 text-emerald-300" />}>
          <AgriBasketPriceChart rows={prices} />
        </SectionCard>
      ) : null}

      {hasRows(prices) ? (
        <SectionCard title="品类状态" icon={<Database className="h-4 w-4 text-cyan-300" />}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2">品类</th>
                  <th className="px-3 py-2">20日 / 60日</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2">是否拆分</th>
                  <th className="px-3 py-2">跟踪价格</th>
                  <th className="px-3 py-2">触发条件</th>
                </tr>
              </thead>
              <tbody>
                {prices.map((row) => (
                  <tr key={row.category} className="border-t border-slate-800 align-top text-slate-300">
                    <td className="px-3 py-3 font-semibold text-white">{row.category}</td>
                    <td className="px-3 py-3"><span className="text-cyan-200">{pct(row.change_20d_pct)}</span> / <span className="text-emerald-200">{pct(row.change_60d_pct)}</span></td>
                    <td className="px-3 py-3"><Pill tone={toneByStage(row.price_status)}>{row.price_status}</Pill></td>
                    <td className="px-3 py-3 text-amber-100">{row.split_research}</td>
                    <td className="px-3 py-3 text-slate-400">{row.tracking_price}</td>
                    <td className="px-3 py-3 text-emerald-200">{row.split_trigger}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      ) : null}

      {hasRows(watchlist) ? (
        <details className="rounded-2xl border border-slate-800 bg-slate-900/50">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-300">品类传导逻辑 / A股潜在映射</summary>
          <div className="grid gap-3 border-t border-slate-800 p-4 md:grid-cols-2 xl:grid-cols-4">
            {watchlist.map((row) => (
              <div key={row.category} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                <div className="text-sm font-semibold text-white">{row.category}</div>
                <div className="mt-1 text-[11px] text-slate-500">{row.climate_regions}</div>
                <div className="mt-3 text-xs leading-relaxed text-slate-300">{row.transmission_logic}</div>
                <div className="mt-3 text-[11px] text-slate-500">映射：{row.a_share_mapping}</div>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
};

const genericChangeSummary = (history: Row[], summary: Row) => {
  if (history.length < 2) {
    return {
      title: '本次建立监控基线',
      lines: [
        `行业趋势分 ${fmt(summary.industry_trend_score, 0)}/${fmt(summary.industry_trend_max || 100, 0)}`,
        `A股可操作分 ${fmt(summary.a_share_operability_score, 0)}/${fmt(summary.a_share_operability_max || 100, 0)}`,
        `结论：${summary.conclusion || '--'}`,
      ],
    };
  }
  const prev = history[history.length - 2];
  const last = history[history.length - 1];
  return {
    title: `行业 ${fmt(prev.industry_trend_score, 0)} → ${fmt(last.industry_trend_score, 0)} / A股 ${fmt(prev.a_share_operability_score, 0)} → ${fmt(last.a_share_operability_score, 0)}`,
    lines: [
      prev.conclusion === last.conclusion ? `结论不变：${last.conclusion}` : `结论变化：${prev.conclusion} → ${last.conclusion}`,
      `当前阶段：${summary.stage || last.stage || '--'}`,
      `下一触发：${summary.next_trigger || last.next_trigger || '--'}`,
    ],
  };
};

const genericFactorTone = (score?: string) => {
  const n = num(score);
  if (n >= 80) return 'border-emerald-500/35 bg-emerald-500/10';
  if (n >= 60) return 'border-amber-500/35 bg-amber-500/10';
  return 'border-slate-800 bg-slate-950/50';
};

const GenericTrendPanel: React.FC<{ dashboard: TrendDashboardData }> = ({ dashboard }) => {
  const generic = dashboard.generic_dashboard || {};
  const summary = generic.summary || {};
  const factors = generic.factor_scorecard || [];
  const heatRows = generic.market_heat || [];
  const watchlist = generic.watchlist || [];
  const companyResearch = hasRows(generic.company_research) ? (generic.company_research || []) : (dashboard.a_share_mapping_score || []);
  const scoreHistory = generic.score_history || [];
  const changeSummary = genericChangeSummary(scoreHistory, summary);
  const topicName = summary.topic_name || dashboard.idea.name;
  const researchByDecision = useMemo(() => {
    const groups = new Map<string, Row[]>();
    companyResearch.forEach((row) => {
      const key = row.include_decision || row.pool_tier || '待研究';
      groups.set(key, [...(groups.get(key) || []), row]);
    });
    return Array.from(groups.entries());
  }, [companyResearch]);

  return (
    <div className="space-y-4">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <div className="rounded-2xl border border-cyan-500/25 bg-gradient-to-br from-cyan-950/35 via-slate-900 to-slate-950 p-4 shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-3xl font-black text-white">{topicName}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Pill tone="border-cyan-500/40 bg-cyan-500/10 text-cyan-100">{summary.conclusion || dashboard.idea.stage}</Pill>
                <Pill tone={toneByStage(summary.industry_status)}>{summary.industry_status || '行业观察'}</Pill>
                <Pill tone="border-amber-500/40 bg-amber-500/10 text-amber-200">{summary.operability_state || '等待买点'}</Pill>
              </div>
              <div className="mt-3 text-sm text-slate-300">{summary.current_view || dashboard.verdict.position}</div>
            </div>
            <div className="grid min-w-[240px] gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-emerald-500/20 bg-slate-950/40 px-4 py-3">
                <div className="text-[11px] text-slate-500">行业趋势分</div>
                <div className="mt-1 text-4xl font-black text-emerald-100">{fmt(summary.industry_trend_score, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(summary.industry_trend_max || 100, 0)}</span></div>
              </div>
              <div className="rounded-2xl border border-amber-500/20 bg-slate-950/40 px-4 py-3">
                <div className="text-[11px] text-slate-500">A股可操作分</div>
                <div className="mt-1 text-4xl font-black text-amber-100">{fmt(summary.a_share_operability_score, 0)}<span className="text-base font-medium text-slate-400">/ {fmt(summary.a_share_operability_max || 100, 0)}</span></div>
              </div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="当前结论" value={summary.conclusion || '--'} tone="text-cyan-100" />
            <Metric label="卡住原因" value={summary.block_reason || '--'} tone="text-rose-200" />
            <Metric label="下一触发" value={summary.next_trigger || '--'} tone="text-emerald-200" />
            <Metric label="数据更新时间" value={summary.updated_at || dashboard.idea.report_date || '--'} tone="text-slate-100" />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="text-xs text-slate-500">变化摘要</div>
          <div className="mt-2 text-lg font-semibold text-white">{changeSummary.title}</div>
          <div className="mt-3 space-y-2">
            {changeSummary.lines.map((line) => (
              <div key={line} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm text-slate-300">{line}</div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="grid gap-3 lg:grid-cols-[repeat(4,minmax(0,1fr))_minmax(260px,1fr)]">
          <Metric label="当前阶段" value={summary.stage || dashboard.idea.stage || '--'} tone="text-white" />
          <Metric label="下一阶段" value={summary.next_stage || '小仓试错'} tone="text-cyan-100" />
          <Metric label="进入下一阶段条件" value={summary.next_stage_conditions || '--'} tone="text-emerald-200" />
          <Metric label="恶化 / 降级条件" value={summary.downgrade_conditions || '--'} tone="text-rose-200" />
          <details className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-300">
            <summary className="cursor-pointer list-none font-semibold text-white">展开固定规则</summary>
            <div className="mt-3 grid gap-2 text-[11px] leading-relaxed text-slate-400">
              <div><span className="text-emerald-300">升级：</span>{dashboard.upgrade_rules?.join(' / ') || '--'}</div>
              <div><span className="text-rose-300">降级：</span>{dashboard.downgrade_rules?.join(' / ') || '--'}</div>
            </div>
          </details>
        </div>
      </section>

      {hasRows(factors) ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {factors.map((row) => {
            const evidence = [
              [row.evidence_1_label, row.evidence_1_value, row.evidence_1_meaning],
              [row.evidence_2_label, row.evidence_2_value, row.evidence_2_meaning],
              [row.evidence_3_label, row.evidence_3_value, row.evidence_3_meaning],
            ].filter(([label, value, meaning]) => label || value || meaning);
            return (
              <div key={row.factor} className={`min-w-0 rounded-2xl border p-4 ${genericFactorTone(row.score_pct)}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="truncate text-sm font-semibold text-white">{row.factor}</div>
                    <InfoTip>
                      <div className="font-semibold text-white">底层逻辑</div>
                      <div className="mt-1">{row.logic}</div>
                      <div className="mt-2 font-semibold text-white">评分原则</div>
                      <div className="mt-1">{row.score_rule}</div>
                      <div className="mt-2 font-semibold text-white">重点看什么</div>
                      <div className="mt-1">{row.watch_focus}</div>
                      <div className="mt-2 text-slate-500">来源：{row.source_name || '--'}</div>
                    </InfoTip>
                  </div>
                  <Pill tone={toneByStage(row.status)}>{row.status || `${fmt(row.score_pct, 0)}%`}</Pill>
                </div>
                <div className="mt-3 flex items-end justify-between gap-3">
                  <div>
                    <div className="text-3xl font-black text-cyan-100">{row.current_points}<span className="text-xs font-medium text-slate-500">/{row.max_points}</span></div>
                    <div className="mt-1 text-[11px] text-slate-500">权重 {row.weight_pct}%</div>
                  </div>
                  <div className="max-w-[160px] text-right text-xs leading-relaxed text-slate-300">{row.meaning || row.watch_focus || ''}</div>
                </div>
                <div className="mt-3 grid gap-2">
                  {evidence.map(([label, value, meaning]) => (
                    <div key={`${label}-${value}`} className="grid grid-cols-[76px_minmax(0,1fr)] gap-2 rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2">
                      <div className="text-[11px] text-slate-500">{label}</div>
                      <div className="min-w-0">
                        <div className="break-words text-sm font-semibold text-cyan-100">{value}</div>
                        <div className="mt-0.5 break-words text-[11px] text-slate-400">{meaning}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      ) : null}

      {hasRows(heatRows) ? (
        <SectionCard title="热点确认" icon={<Activity className="h-4 w-4 text-cyan-300" />}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2">主题</th>
                  <th className="px-3 py-2">今日排名 / 热度</th>
                  <th className="px-3 py-2">5日 / 20日</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2">解释</th>
                </tr>
              </thead>
              <tbody>
                {heatRows.map((row) => (
                  <tr key={row.theme || row.theme_name || row.sector_name || row.name} className="border-t border-slate-800 align-top text-slate-300">
                    <td className="px-3 py-3 font-semibold text-white">{row.theme || row.theme_name || row.sector_name || row.name}</td>
                    <td className="px-3 py-3"><span className="text-cyan-100">#{fmt(row.rank_today || row.hot_rank || row.rank || row.best_rank, 0)}</span> / {fmt(row.hot_score || row.avg_hot_score, 1)}</td>
                    <td className="px-3 py-3">{fmt(row.hot_hits_5 || row.top15_5d || row.top15_days_63d || row.top30_days, 0)} / {fmt(row.hot_hits_20 || row.top30_20d || row.top30_days_63d || row.days_seen, 0)}</td>
                    <td className="px-3 py-3"><Pill tone={toneByStage(row.lifecycle || row.status)}>{row.lifecycle || row.status || '--'}</Pill></td>
                    <td className="px-3 py-3 text-slate-400">{row.reason || row.interpretation || row.evidence || row.meaning || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      ) : null}

      {hasRows(watchlist) ? (
        <SectionCard
          title="观察池"
          icon={<BrainCircuit className="h-4 w-4 text-cyan-300" />}
          right={<span className="text-xs text-slate-500">只放已研究后值得持续跟踪的公司</span>}
        >
          <div className="mb-4 grid gap-3 lg:grid-cols-3">
            <Metric label="整体动作" value={summary.operability_state || '--'} tone="text-amber-200" />
            <Metric label="当前结论" value={summary.conclusion || '--'} tone="text-cyan-100" />
            <Metric label="未买原因" value={summary.block_reason || '--'} tone="text-rose-200" />
          </div>
          <CompanyResearchCards rows={watchlist} compact />
        </SectionCard>
      ) : null}

      {hasRows(companyResearch) ? (
        <details className="rounded-2xl border border-slate-800 bg-slate-900/50">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-300">完整公司研究</summary>
          <div className="space-y-4 border-t border-slate-800 p-4">
            {researchByDecision.map(([decision, rows]) => (
              <div key={decision} className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={companyDecisionTone(decision)}>{decision}</Pill>
                  <span className="text-xs text-slate-500">{rows.length} 家</span>
                </div>
                <CompanyResearchCards rows={rows} />
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {hasRows(dashboard.price_radar) ? (
        <details className="rounded-2xl border border-slate-800 bg-slate-900/50">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-300">价格雷达 / 数据源</summary>
          <div className="space-y-4 border-t border-slate-800 p-4">
            <PriceRadarCards rows={dashboard.price_radar || []} />
            {hasRows(dashboard.data_source_matrix) ? <SignalCards rows={dashboard.data_source_matrix || []} kind="source" /> : null}
          </div>
        </details>
      ) : null}
    </div>
  );
};

const TrendResearchPage: React.FC = () => {
  const [ideas, setIdeas] = useState<TrendIdeaItem[]>([]);
  const [activeIdeaId, setActiveIdeaId] = useState(() => new URLSearchParams(window.location.search).get('idea') || 'storage');
  const [dashboard, setDashboard] = useState<TrendDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const reload = async (ideaId = activeIdeaId) => {
    setLoading(true);
    setError('');
    try {
      const [ideaList, detail] = await Promise.all([fetchTrendIdeas(), fetchTrendDashboard(ideaId)]);
      setIdeas(ideaList);
      setDashboard(detail);
      if (!detail) setError('趋势研究数据加载失败，请检查后端 /api/trend-research 接口。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(activeIdeaId); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [activeIdeaId]);

  const activeIdea = dashboard?.idea || ideas.find((item) => item.id === activeIdeaId);
  const latestBullets = useMemo(() => dashboard?.report?.summary?.bullets?.slice(0, 8) || [], [dashboard]);
  const isRubberStandalone = dashboard?.idea?.id === 'el_nino_rubber';
  const isStorageStandalone = dashboard?.idea?.id === 'storage';
  const isAgriBasketStandalone = dashboard?.idea?.id === 'el_nino_agri_basket';
  const isGenericStandalone = Boolean(dashboard?.generic_dashboard?.summary && Object.keys(dashboard.generic_dashboard.summary).length);

  return (
    <div className="min-h-screen bg-[#0a0f1c] pb-20 font-sans text-slate-200">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />首页
          </a>
          <div className="mr-1 flex items-center gap-2 text-base font-bold text-white"><BrainCircuit className="h-5 w-5 text-cyan-300" />趋势研究</div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">v{APP_VERSION}</span>
          <select
            value={activeIdeaId}
            onChange={(event) => {
              const next = event.target.value;
              setActiveIdeaId(next);
              window.history.replaceState(null, '', `/trend-research?idea=${next}`);
            }}
            className="h-9 min-w-[210px] rounded-lg border border-cyan-700/60 bg-slate-950 px-3 text-sm font-medium text-cyan-100 outline-none hover:border-cyan-500 focus:border-cyan-400"
          >
            {ideas.length ? ideas.map((idea) => <option key={idea.id} value={idea.id}>{idea.name}</option>) : <option value="storage">AI 存储 / 内存涨价</option>}
          </select>
          {activeIdea ? <Pill tone={toneByStage(activeIdea.stage)}>{activeIdea.stage}</Pill> : null}
          {dashboard?.idea?.report_date ? <Pill>日报 {dashboard.idea.report_date}</Pill> : null}
          <button type="button" onClick={() => reload()} disabled={loading} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:opacity-60">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />刷新
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-[1800px] space-y-4 px-3 py-4 md:px-6">
        {loading && !dashboard ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-slate-400">趋势研究数据加载中...</div>
        ) : null}
        {error ? <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}

        {activeIdea && !isRubberStandalone && !isStorageStandalone && !isAgriBasketStandalone && !isGenericStandalone && (
          <section className="rounded-2xl border border-cyan-800/40 bg-gradient-to-br from-cyan-950/40 via-slate-900 to-slate-950 p-4 shadow-lg">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs text-cyan-300">{activeIdea.rating}</div>
                <h1 className="mt-1 break-words text-2xl font-bold text-white">{activeIdea.name}</h1>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Pill tone={toneByStage(activeIdea.stage)}>{activeIdea.stage}</Pill>
                  <Pill tone="border-emerald-500/40 bg-emerald-500/10 text-emerald-200">{activeIdea.status}</Pill>
                </div>
              </div>
              <div className="min-w-0 max-w-3xl rounded-xl border border-slate-700/70 bg-slate-950/50 p-3 text-sm text-slate-300">
                <div className="text-xs text-slate-500">当前动作</div>
                <div className="mt-1 break-words font-medium text-white">{activeIdea.action}</div>
              </div>
            </div>
          </section>
        )}

        {dashboard && (
          <>
            {isRubberStandalone ? (
              dashboard.rubber_dashboard?.summary ? <RubberDashboardPanel data={dashboard.rubber_dashboard} /> : null
            ) : isStorageStandalone ? (
              dashboard.storage_dashboard?.summary ? <StorageDashboardPanel dashboard={dashboard} /> : null
            ) : isAgriBasketStandalone ? (
              dashboard.agri_basket_dashboard?.summary ? <AgriBasketPanel dashboard={dashboard} /> : null
            ) : isGenericStandalone ? (
              <GenericTrendPanel dashboard={dashboard} />
            ) : (
              <>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                  <Metric label="行业信号" value={dashboard.verdict.industry} tone="text-emerald-200" />
                  <Metric label="交易阶段" value={dashboard.verdict.market} tone="text-amber-200" />
                  <Metric label="仓位动作" value={dashboard.verdict.position} tone="text-cyan-200" />
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <SectionCard title="升级条件" icon={<CheckCircle2 className="h-4 w-4 text-emerald-300" />}>
                    <TextList rows={dashboard.upgrade_rules || []} tone="green" />
                  </SectionCard>
                  <SectionCard title="降级条件" icon={<ShieldAlert className="h-4 w-4 text-rose-300" />}>
                    <TextList rows={dashboard.downgrade_rules || []} tone="red" />
                  </SectionCard>
                </div>

                {hasRows(dashboard.decision_matrix) ? (
              <SectionCard title="当前决策矩阵" icon={<BrainCircuit className="h-4 w-4 text-cyan-300" />}>
                <DecisionCards rows={dashboard.decision_matrix || []} />
              </SectionCard>
                ) : null}

                {hasRows(dashboard.chain_layers) ? (
              <SectionCard title="产业链传导" icon={<GitBranch className="h-4 w-4 text-cyan-300" />}>
                <ChainFlow rows={dashboard.chain_layers || []} />
              </SectionCard>
                ) : null}

                {hasRows(dashboard.price_radar) ? (
              <SectionCard title="价格雷达" icon={<Activity className="h-4 w-4 text-sky-300" />}>
                <PriceRadarCards rows={dashboard.price_radar || []} />
              </SectionCard>
                ) : null}

            {hasRows(dashboard.a_share_price_history) || hasRows(dashboard.global_peer_history) ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {hasRows(dashboard.a_share_price_history) ? (
                  <SectionCard title="A 股逐日相对收益" icon={<TrendingUp className="h-4 w-4 text-cyan-300" />}>
                    <HistoryLineChart rows={dashboard.a_share_price_history || []} idKey="symbol" />
                  </SectionCard>
                ) : null}
                {hasRows(dashboard.global_peer_history) ? (
                  <SectionCard title="海外同业逐日相对收益" icon={<BarChart3 className="h-4 w-4 text-blue-300" />}>
                    <HistoryLineChart rows={dashboard.global_peer_history || []} idKey="ticker" />
                  </SectionCard>
                ) : null}
              </div>
            ) : null}

            {hasRows(dashboard.a_share_price_stage) || hasRows(dashboard.valuation_scenarios) ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {hasRows(dashboard.a_share_price_stage) ? (
                  <SectionCard title="A 股价格阶段图" icon={<TrendingUp className="h-4 w-4 text-rose-300" />}>
                    <PriceStageChart rows={dashboard.a_share_price_stage || []} />
                  </SectionCard>
                ) : null}
                {hasRows(dashboard.valuation_scenarios) ? (
                  <SectionCard title="估值压力图" icon={<Gauge className="h-4 w-4 text-violet-300" />}>
                    <ValuationChart rows={dashboard.valuation_scenarios || []} />
                  </SectionCard>
                ) : null}
              </div>
            ) : null}

            {hasRows(dashboard.a_share_mapping_score) ? (
              <SectionCard title="A 股映射评分" icon={<BarChart3 className="h-4 w-4 text-cyan-300" />}>
                <MappingScoreCards rows={dashboard.a_share_mapping_score || []} />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.a_share_price_stage) ? (
              <SectionCard title="A 股价格阶段卡" icon={<TrendingUp className="h-4 w-4 text-rose-300" />}>
                <PriceStageCards rows={dashboard.a_share_price_stage || []} />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.valuation_scenarios) ? (
              <SectionCard title="估值压力测试" icon={<Gauge className="h-4 w-4 text-violet-300" />}>
                <ValuationCards rows={dashboard.valuation_scenarios || []} />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.pre_earnings_warning) ? (
              <SectionCard title="季报前预警" icon={<AlertTriangle className="h-4 w-4 text-amber-300" />}>
                <WarningCards rows={dashboard.pre_earnings_warning || []} />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.company_validation) ? (
              <SectionCard title="公司验证矩阵" icon={<ShieldAlert className="h-4 w-4 text-amber-300" />}>
                <CompanyValidationCards rows={dashboard.company_validation || []} />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.foundry_supply) || hasRows(dashboard.downstream_demand) ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {hasRows(dashboard.foundry_supply) ? (
                  <SectionCard title="供给/约束追踪" icon={<ServerCog className="h-4 w-4 text-blue-300" />}>
                    <SignalCards rows={dashboard.foundry_supply || []} kind="supply" />
                  </SectionCard>
                ) : null}
                {hasRows(dashboard.downstream_demand) ? (
                  <SectionCard title="需求/传导观察" icon={<Layers3 className="h-4 w-4 text-emerald-300" />}>
                    <SignalCards rows={dashboard.downstream_demand || []} kind="demand" />
                  </SectionCard>
                ) : null}
              </div>
            ) : null}

            {hasRows(dashboard.company_snapshot) ? (
              <SectionCard title="公司/主体快照" icon={<Database className="h-4 w-4 text-emerald-300" />}>
                <CompanyCards rows={dashboard.company_snapshot || []} />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.industry_signals) || hasRows(dashboard.global_peer_stage) ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {hasRows(dashboard.industry_signals) ? (
                  <SectionCard title="行业信号跟踪" icon={<Database className="h-4 w-4 text-cyan-300" />}>
                    <SignalCards rows={dashboard.industry_signals || []} kind="industry" />
                  </SectionCard>
                ) : null}
                {hasRows(dashboard.global_peer_stage) ? (
                  <SectionCard title="海外/外部价格阶段" icon={<BarChart3 className="h-4 w-4 text-blue-300" />}>
                    <PeerCards rows={dashboard.global_peer_stage || []} />
                  </SectionCard>
                ) : null}
              </div>
            ) : null}

            {hasRows(dashboard.data_source_matrix) ? (
              <SectionCard title="数据接入状态" icon={<Database className="h-4 w-4 text-slate-300" />}>
                <SignalCards rows={dashboard.data_source_matrix || []} kind="source" />
              </SectionCard>
            ) : null}

            {hasRows(dashboard.tracking_tasks) ? (
              <SectionCard title="后续跟踪任务" icon={<RefreshCw className="h-4 w-4 text-slate-300" />}>
                <TrackingTaskCards rows={dashboard.tracking_tasks || []} />
              </SectionCard>
            ) : null}

            <SectionCard title="累计研究结论" icon={<FileText className="h-4 w-4 text-slate-300" />} right={dashboard.report.path ? <span className="break-all text-xs text-slate-500">{dashboard.report.path}</span> : null}>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {latestBullets.map((bullet) => <div key={bullet} className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">{bullet}</div>)}
              </div>
            </SectionCard>
          </>
        )}
          </>
        )}
      </main>
    </div>
  );
};

export default TrendResearchPage;
