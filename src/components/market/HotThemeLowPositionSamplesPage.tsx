import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, ChevronRight, Flame, RefreshCw, Target, TrendingUp } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  fetchLowPositionL2SampleDetail,
  fetchLowPositionL2Samples,
  fetchLowPositionL2SampleSummary,
  LowPositionL2SampleDetail,
  LowPositionL2SampleItem,
  LowPositionL2SampleSummary,
} from '../../services/marketHeatService';
import { Metric } from '../common/ResearchCard';
import { APP_VERSION } from '../../version';

const fmt = (value?: number | string | null, digits = 2) => {
  if (value == null || value === '') return '--';
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : String(value);
};
const pct = (value?: number | string | null) => `${fmt(value)}%`;
const yi = (value?: number | string | null) => `${fmt(value)}亿`;
const retTone = (value?: number | string | null) => Number(value ?? 0) >= 0 ? 'text-red-300' : 'text-emerald-300';

const outcomeText = (item?: LowPositionL2SampleItem | null) => {
  const d5 = Number(item?.d5_return_pct ?? 0);
  if (d5 >= 3) return '赢家';
  if (d5 <= -3) return '失败';
  return '中性';
};

const outcomeClass = (item?: LowPositionL2SampleItem | null) => {
  const d5 = Number(item?.d5_return_pct ?? 0);
  if (d5 >= 3) return 'border-red-500/30 bg-red-500/10 text-red-200';
  if (d5 <= -3) return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  return 'border-slate-600 bg-slate-800/60 text-slate-300';
};

const SampleCard: React.FC<{
  item: LowPositionL2SampleItem;
  active: boolean;
  onClick: () => void;
}> = ({ item, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`w-full border-b border-slate-800/80 px-4 py-3 text-left transition last:border-b-0 ${active ? 'bg-sky-500/10' : 'hover:bg-slate-950/50'}`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{item.trade_date}</span>
          <span className={`rounded border px-1.5 py-0.5 text-[10px] ${outcomeClass(item)}`}>{outcomeText(item)}</span>
        </div>
        <div className="mt-1 flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-white">{item.name}</span>
          <span className="font-mono text-[11px] text-slate-500">{item.symbol}</span>
        </div>
        <div className="mt-1 truncate text-xs text-slate-400">{item.theme_name}</div>
      </div>
      <div className="text-right">
        <div className={`text-base font-bold ${retTone(item.d5_return_pct)}`}>{pct(item.d5_return_pct)}</div>
        <div className="text-[10px] text-slate-500">D+5</div>
      </div>
    </div>
    <div className="mt-2 grid grid-cols-4 gap-2 text-[10px] text-slate-500">
      <div><span className="text-slate-300">{fmt(item.amount_ratio_10d)}</span><br />量能比</div>
      <div><span className="text-slate-300">{fmt(item.position_20d)}</span><br />20日位</div>
      <div><span className="text-slate-300">{pct(item.ma60_distance_abs_pct)}</span><br />60乖离</div>
      <div><span className="text-slate-300">{fmt(item.super_positive_days_3d, 0)}/3</span><br />超大单</div>
    </div>
  </button>
);

const SummaryStrip: React.FC<{ summary: LowPositionL2SampleSummary | null }> = ({ summary }) => {
  const h = summary?.summary?.horizon_stats || {};
  const noFade = summary?.summary?.d1_fade_bins?.d1_no_fade;
  const fade = summary?.summary?.d1_fade_bins?.d1_fade;
  return (
    <div className="grid gap-3 md:grid-cols-6">
      <Metric label="历史样本" value={`${summary?.meta?.sample_count ?? 0} 只次`} tone="text-sky-200" />
      <Metric label="D+1" value={`${fmt(h['1']?.avg)}% / 胜率 ${fmt((h['1']?.win_rate ?? 0) * 100, 1)}%`} />
      <Metric label="D+3" value={`${fmt(h['3']?.avg)}% / Alpha ${fmt(h['3']?.alpha)}%`} tone="text-red-200" />
      <Metric label="D+5" value={`${fmt(h['5']?.avg)}% / 胜率 ${fmt((h['5']?.win_rate ?? 0) * 100, 1)}%`} tone="text-red-200" />
      <Metric label="D+1不回落" value={`${fmt(noFade?.avg_d5)}% / ${fmt((Number(noFade?.d5_win_rate ?? 0)) * 100, 1)}%`} tone="text-red-200" />
      <Metric label="D+1冲高回落" value={`${fmt(fade?.avg_d5)}% / ${fmt((Number(fade?.d5_win_rate ?? 0)) * 100, 1)}%`} tone="text-amber-200" />
    </div>
  );
};

const DetailPanel: React.FC<{ detail: LowPositionL2SampleDetail | null; loading: boolean }> = ({ detail, loading }) => {
  const sample = detail?.sample;
  const chartData = useMemo(() => (detail?.price_window || []).map((row) => ({
    ...row,
    label: row.trade_date.slice(5),
  })), [detail]);
  if (loading && !detail) {
    return <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-10 text-center text-sm text-slate-500">样本详情加载中...</div>;
  }
  if (!detail || !sample) {
    return <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-10 text-center text-sm text-slate-500">选择左侧样本查看单票复盘。</div>;
  }
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="text-xl font-bold text-white">{sample.name}</div>
              <div className="font-mono text-xs text-slate-500">{sample.symbol}</div>
              <span className={`rounded border px-2 py-0.5 text-xs ${outcomeClass(sample)}`}>{outcomeText(sample)}</span>
            </div>
            <div className="mt-1 text-sm text-slate-400">{sample.trade_date} 信号，{sample.theme_name}，D+1 入场日 {sample.entry_date || '--'}</div>
          </div>
          <a
            href={`/?symbol=${sample.symbol}`}
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-3 text-xs text-slate-200 hover:border-slate-500"
          >
            去主图看这只票 <ChevronRight className="h-3.5 w-3.5" />
          </a>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4 xl:grid-cols-8">
          <Metric label="D+1" value={pct(sample.d1_return_pct)} tone={retTone(sample.d1_return_pct)} />
          <Metric label="D+3" value={pct(sample.d3_return_pct)} tone={retTone(sample.d3_return_pct)} />
          <Metric label="D+5" value={pct(sample.d5_return_pct)} tone={retTone(sample.d5_return_pct)} />
          <Metric label="D+5 Alpha" value={pct(sample.d5_alpha_pct)} tone={retTone(sample.d5_alpha_pct)} />
          <Metric label="量能比" value={fmt(sample.amount_ratio_10d)} />
          <Metric label="20日位置" value={fmt(sample.position_20d)} />
          <Metric label="60日乖离" value={pct(sample.ma60_distance_abs_pct)} />
          <Metric label="评分" value={fmt(sample.shadow_score, 1)} tone="text-sky-200" />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><Target className="h-4 w-4 text-sky-300" />这笔样本怎么看</div>
        <div className="space-y-2 text-sm leading-6 text-slate-300">
          <p>{detail.readout.setup}</p>
          <p>{detail.readout.funding}</p>
          <p>{detail.readout.entry}</p>
          <p className="text-sky-200">{detail.readout.verdict}</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><TrendingUp className="h-4 w-4 text-red-300" />价格窗口</div>
          <div className="h-[310px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 14, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 11 }} minTickGap={20} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={42} domain={['dataMin', 'dataMax']} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                <ReferenceLine x={String(sample.trade_date).slice(5)} stroke="#38bdf8" strokeDasharray="4 4" label={{ value: '信号', fill: '#38bdf8', fontSize: 11 }} />
                <Line type="monotone" dataKey="close" stroke="#f87171" strokeWidth={2} dot={false} name="收盘价" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="mb-3 text-sm font-semibold text-white">关键因子</div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">热点排名</span><span className="text-slate-200">Top {fmt(sample.theme_rank, 0)}</span></div>
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">近5日上榜</span><span className="text-slate-200">{fmt(sample.theme_recent_hits, 0)} 次</span></div>
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">D+1开盘缺口</span><span className={retTone(sample.open_gap_pct)}>{pct(sample.open_gap_pct)}</span></div>
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">D+1状态</span><span className="text-slate-200">{sample.entry_label || '--'}</span></div>
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">冲高回落</span><span className={sample.intraday_fade ? 'text-amber-200' : 'text-slate-200'}>{sample.intraday_fade ? '是' : '否'}</span></div>
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">L2两日净流入</span><span className="text-red-200">{yi(sample.l2_main_net_2d_yi)}</span></div>
            <div className="flex justify-between border-b border-slate-800 pb-2"><span className="text-slate-500">超大单三日</span><span className="text-red-200">{yi(sample.l2_super_net_3d_yi)}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">市场环境</span><span className="text-slate-200">{sample.market_liquidity_label || '--'}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
};

const HotThemeLowPositionSamplesPage: React.FC = () => {
  const [summary, setSummary] = useState<LowPositionL2SampleSummary | null>(null);
  const [items, setItems] = useState<LowPositionL2SampleItem[]>([]);
  const [selected, setSelected] = useState<LowPositionL2SampleItem | null>(null);
  const [detail, setDetail] = useState<LowPositionL2SampleDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [outcome, setOutcome] = useState('all');
  const [theme, setTheme] = useState('');
  const [sort, setSort] = useState('date_desc');

  const loadList = async () => {
    setLoading(true);
    setError('');
    try {
      const [s, list] = await Promise.all([
        fetchLowPositionL2SampleSummary(),
        fetchLowPositionL2Samples({ outcome, theme, sort, limit: 300 }),
      ]);
      if (s) setSummary(s);
      if (list) {
        setItems(list.items || []);
        setSelected((prev) => {
          if (prev && list.items.some((item) => item.trade_date === prev.trade_date && item.symbol === prev.symbol)) return prev;
          return list.items[0] || null;
        });
      } else {
        setError('历史样本加载失败，请检查后端是否已生成样本库。');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outcome, theme, sort]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    const loadDetail = async () => {
      setDetailLoading(true);
      const data = await fetchLowPositionL2SampleDetail(selected.trade_date, selected.symbol);
      setDetail(data);
      setDetailLoading(false);
    };
    loadDetail();
  }, [selected]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/market-heat" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />返回热点页
          </a>
          <div className="mr-2 flex items-center gap-2 text-base font-bold text-white"><Flame className="h-5 w-5 text-amber-400" />热点低位 L2 历史样本</div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">v{APP_VERSION}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            {summary?.meta?.start_date || '--'} 至 {summary?.meta?.end_date || '--'}
          </span>
          <button type="button" onClick={loadList} disabled={loading} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:opacity-60">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />刷新
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        {error ? <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}
        <SummaryStrip summary={summary} />

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-sm leading-6 text-slate-300">
          当前结论：D+1 不冲高回落是强持仓确认；但不能“一冲高回落就卖”，更合理的是冲高回落且 D+1 跌幅超过 2% 时做风险处置。
        </div>

        <div className="grid gap-4 xl:grid-cols-[430px_minmax(0,1fr)]">
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
            <div className="border-b border-slate-800 p-3">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><BarChart3 className="h-4 w-4 text-sky-300" />历史命中清单</div>
              <div className="grid grid-cols-3 gap-2">
                <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-slate-200 outline-none">
                  {(summary?.filters?.outcomes || [{ value: 'all', label: '全部' }]).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <select value={theme} onChange={(e) => setTheme(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-slate-200 outline-none">
                  <option value="">全部板块</option>
                  {(summary?.filters?.themes || []).map((item) => <option key={item.theme_name} value={item.theme_name}>{item.theme_name}({item.count})</option>)}
                </select>
                <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-slate-200 outline-none">
                  <option value="date_desc">日期倒序</option>
                  <option value="d5_desc">D+5最好</option>
                  <option value="d5_asc">D+5最差</option>
                  <option value="score_desc">评分最高</option>
                </select>
              </div>
              <div className="mt-2 text-xs text-slate-500">当前 {items.length} 条；点击样本在右侧复盘。</div>
            </div>
            <div className="max-h-[calc(100vh-310px)] overflow-y-auto">
              {items.map((item) => (
                <SampleCard
                  key={`${item.trade_date}-${item.symbol}`}
                  item={item}
                  active={selected?.trade_date === item.trade_date && selected?.symbol === item.symbol}
                  onClick={() => setSelected(item)}
                />
              ))}
              {!loading && !items.length ? <div className="px-4 py-12 text-center text-sm text-slate-500">没有符合筛选条件的样本</div> : null}
            </div>
          </div>

          <DetailPanel detail={detail} loading={detailLoading} />
        </div>
      </div>
    </div>
  );
};

export default HotThemeLowPositionSamplesPage;
