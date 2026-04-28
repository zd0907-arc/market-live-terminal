import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Flame, RefreshCw, Activity, TrendingUp, AlertTriangle, Radio, BarChart3 } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';
import { fetchMarketHeatHistory, fetchMarketHeatLatest, MarketHeatHistorySummary, MarketHeatSector, MarketHeatSnapshot } from '../../services/marketHeatService';
import { APP_VERSION } from '../../version';

const fmt = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));
const pct = (value?: number | null) => `${fmt(value)}%`;
const yi = (value?: number | null) => `${fmt(value)}亿`;

const tagLabel: Record<string, string> = {
  new_emerging: '新冒头',
  mainline: '主线延续',
  overheated: '过热',
  fading: '退潮',
  one_day_spike: '单日脉冲',
  leader_only: '龙头独涨',
};

const tagClass = (tag: string) => {
  if (tag === 'mainline') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  if (tag === 'new_emerging') return 'border-sky-500/30 bg-sky-500/10 text-sky-200';
  if (tag === 'overheated' || tag === 'one_day_spike') return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  if (tag === 'fading') return 'border-red-500/30 bg-red-500/10 text-red-200';
  return 'border-slate-600 bg-slate-800/50 text-slate-300';
};

const trendColors = ['#38bdf8', '#f59e0b', '#a78bfa', '#fb7185', '#34d399', '#f97316'];

const Metric: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone = 'text-white' }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const SectorRankItem: React.FC<{
  sector: MarketHeatSector;
  index: number;
  active: boolean;
  onClick: () => void;
}> = ({ sector, index, active, onClick }) => {
  const tone = sector.pct_change >= 0 ? 'text-red-300' : 'text-emerald-300';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full border-b border-slate-800/80 px-4 py-3 text-left transition last:border-b-0 ${active ? 'bg-sky-500/10' : 'hover:bg-slate-950/40'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">#{index + 1}</span>
            <span className="truncate text-sm font-semibold text-white">{sector.name}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {(sector.risk_tags || []).slice(0, 3).map((tag) => (
              <span key={tag} className={`rounded border px-1.5 py-0.5 text-[10px] ${tagClass(tag)}`}>{tagLabel[tag] || tag}</span>
            ))}
          </div>
        </div>
        <div className="grid min-w-[138px] grid-cols-3 gap-2 text-right text-[10px]">
          <div><div className="text-sm font-semibold text-sky-200">{fmt(sector.hot_score, 1)}</div><div className="text-slate-500">热度</div></div>
          <div><div className="text-sm font-semibold text-violet-200">{fmt(sector.persistence_score, 1)}</div><div className="text-slate-500">持续</div></div>
          <div><div className={`text-sm font-semibold ${tone}`}>{pct(sector.pct_change)}</div><div className="text-slate-500">今日</div></div>
        </div>
      </div>
    </button>
  );
};

const StockRow: React.FC<{ stock: MarketHeatSector['stocks'][number]; index: number }> = ({ stock, index }) => (
  <tr className="border-b border-slate-800/70 last:border-b-0">
    <td className="px-3 py-2 text-xs text-slate-500">#{index + 1}</td>
    <td className="px-3 py-2">
      <div className="text-sm font-semibold text-white">{stock.name}</div>
      <div className="text-[11px] text-slate-500">{stock.symbol}</div>
    </td>
    <td className="px-3 py-2 text-xs text-slate-300">{stock.role || '--'}</td>
    <td className={`px-3 py-2 text-right text-sm font-semibold ${Number(stock.pct_change) >= 0 ? 'text-red-300' : 'text-emerald-300'}`}>{pct(stock.pct_change)}</td>
    <td className="px-3 py-2 text-right text-sm text-slate-200">{pct(stock.return_5d)}</td>
    <td className="px-3 py-2 text-right text-sm text-slate-200">{pct(stock.return_20d)}</td>
    <td className={`px-3 py-2 text-right text-sm font-semibold ${Number(stock.l2_net_inflow_yi) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>{yi(stock.l2_net_inflow_yi)}</td>
    <td className="px-3 py-2 text-right text-sm text-slate-300">{yi(stock.amount_yi)}</td>
  </tr>
);

const MarketHeatPage: React.FC = () => {
  const [snapshot, setSnapshot] = useState<MarketHeatSnapshot | null>(null);
  const [history, setHistory] = useState<MarketHeatHistorySummary | null>(null);
  const [selectedId, setSelectedId] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (refresh = false) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchMarketHeatLatest(undefined, refresh);
      if (!data) {
        setError('市场热度加载失败，请检查后端日志');
        return;
      }
      setSnapshot(data);
      setSelectedId((prev) => prev || data.hot_top?.[0]?.id || data.sectors?.[0]?.id || '');
      const historyData = await fetchMarketHeatHistory(63, data.meta?.trade_date);
      if (historyData) setHistory(historyData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(false);
  }, []);

  const selected = useMemo(() => {
    if (!snapshot) return null;
    return snapshot.sectors.find((item) => item.id === selectedId) || snapshot.hot_top?.[0] || null;
  }, [snapshot, selectedId]);

  const leaderNames = useMemo(() => (selected?.stocks || []).slice(0, 3).map((s) => s.name).join(' / '), [selected]);
  const topHistorySeries = useMemo(() => (history?.series || []).slice(0, 6), [history]);
  const historyChartData = useMemo(() => {
    if (!topHistorySeries.length) return [];
    const dates = topHistorySeries[0]?.points?.map((point) => point.date) || [];
    return dates.map((date) => {
      const row: Record<string, string | number | null> = { date };
      topHistorySeries.forEach((series) => {
        const point = series.points.find((item) => item.date === date);
        row[series.id] = point?.hot_score ?? null;
      });
      return row;
    });
  }, [topHistorySeries]);
  const recentDailyTop = useMemo(() => [...(history?.daily_top || [])].slice(-18).reverse(), [history]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />返回主页面
          </a>
          <div className="mr-2 flex items-center gap-2 text-base font-bold text-white"><Flame className="h-5 w-5 text-amber-400" />市场热点温度计</div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">v{APP_VERSION}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">交易日 {snapshot?.meta?.trade_date || '--'}</span>
          <button type="button" onClick={() => load(true)} disabled={loading} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:opacity-60">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />{loading ? '生成中' : '重新生成'}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        {error ? <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}

        <div className="grid gap-4 lg:grid-cols-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-300"><Flame className="h-4 w-4 text-amber-400" />今日最热</div>
            <div className="mt-2 text-2xl font-bold text-white">{snapshot?.hot_top?.[0]?.name || '--'}</div>
            <div className="mt-1 text-xs text-slate-500">热度 {fmt(snapshot?.hot_top?.[0]?.hot_score, 1)}</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-300"><TrendingUp className="h-4 w-4 text-violet-300" />持续最强</div>
            <div className="mt-2 text-2xl font-bold text-white">{snapshot?.persistence_top?.[0]?.name || '--'}</div>
            <div className="mt-1 text-xs text-slate-500">持续 {fmt(snapshot?.persistence_top?.[0]?.persistence_score, 1)}</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-300"><Radio className="h-4 w-4 text-sky-300" />新冒头</div>
            <div className="mt-2 text-2xl font-bold text-white">{snapshot?.emerging?.[0]?.name || '暂无'}</div>
            <div className="mt-1 text-xs text-slate-500">今日升温但仍需验证</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-300"><AlertTriangle className="h-4 w-4 text-amber-300" />风险提示</div>
            <div className="mt-2 text-2xl font-bold text-white">{snapshot?.risk_or_fading?.[0]?.name || '--'}</div>
            <div className="mt-1 text-xs text-slate-500">过热/退潮/单日脉冲</div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-white">近3个月热门板块趋势</div>
                <div className="mt-1 text-xs text-slate-500">
                  {history?.meta?.start_date || '--'} 至 {history?.meta?.end_date || '--'}，按每日 hot_score 重建
                </div>
              </div>
              <div className="text-xs text-slate-500">{history?.meta?.days || 0} 个交易日</div>
            </div>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={historyChartData} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} minTickGap={26} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={38} domain={[0, 100]} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                  {topHistorySeries.map((series, index) => (
                    <Line
                      key={series.id}
                      type="monotone"
                      dataKey={series.id}
                      name={series.name}
                      stroke={trendColors[index % trendColors.length]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {topHistorySeries.map((series, index) => (
                <button
                  key={series.id}
                  type="button"
                  onClick={() => setSelectedId(series.id)}
                  className="rounded-lg border border-slate-800 bg-slate-950/50 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-600"
                >
                  <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: trendColors[index % trendColors.length] }} />
                  {series.name}
                  <span className="ml-1 text-slate-500">Top3 {series.top_count}天</span>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="mb-3 text-sm font-semibold text-white">最近每日热门板块</div>
            <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">
              {recentDailyTop.map((day) => {
                const leader = day.leaders?.[0];
                return (
                  <div key={day.date} className="rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs text-slate-500">{day.date}</div>
                      <button
                        type="button"
                        onClick={() => leader?.id && setSelectedId(leader.id)}
                        className="truncate text-sm font-semibold text-white hover:text-sky-200"
                      >
                        {leader?.name || '--'}
                      </button>
                      <div className="text-sm font-semibold text-sky-200">{fmt(leader?.hot_score, 1)}</div>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(day.leaders || []).slice(0, 3).map((item) => (
                        <button
                          key={`${day.date}-${item.id}`}
                          type="button"
                          onClick={() => setSelectedId(item.id)}
                          className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-400 hover:border-slate-500"
                        >
                          {item.name} {fmt(item.hot_score, 0)}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
              {!history && <div className="py-8 text-center text-sm text-slate-500">历史热度加载中...</div>}
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[430px_minmax(0,1fr)]">
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-white"><BarChart3 className="h-4 w-4 text-sky-300" />热点排行</div>
              <div className="text-xs text-slate-500">{snapshot?.meta?.source || 'local'}</div>
            </div>
            <div className="max-h-[720px] overflow-y-auto">
              {(snapshot?.hot_top || []).map((sector, index) => (
                <SectorRankItem key={sector.id} sector={sector} index={index} active={selected?.id === sector.id} onClick={() => setSelectedId(sector.id)} />
              ))}
              {!loading && !snapshot ? <div className="px-4 py-10 text-center text-sm text-slate-500">暂无市场热度数据</div> : null}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xl font-bold text-white">{selected?.name || '--'}</div>
                  <div className="mt-1 max-w-3xl text-sm text-slate-400">{selected?.description || selected?.readout || '--'}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(selected?.risk_tags || []).map((tag) => <span key={tag} className={`rounded border px-2 py-0.5 text-xs ${tagClass(tag)}`}>{tagLabel[tag] || tag}</span>)}
                  </div>
                </div>
                <div className="text-right text-xs text-slate-500">代表票<br /><span className="text-slate-300">{leaderNames || '--'}</span></div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-4 xl:grid-cols-8">
                <Metric label="热度" value={fmt(selected?.hot_score, 1)} tone="text-sky-200" />
                <Metric label="持续" value={fmt(selected?.persistence_score, 1)} tone="text-violet-200" />
                <Metric label="今日" value={pct(selected?.pct_change)} tone={Number(selected?.pct_change) >= 0 ? 'text-red-300' : 'text-emerald-300'} />
                <Metric label="5日" value={pct(selected?.return_5d)} />
                <Metric label="20日" value={pct(selected?.return_20d)} />
                <Metric label="L2净流入" value={yi(selected?.l2_net_inflow_yi)} tone={Number(selected?.l2_net_inflow_yi) >= 0 ? 'text-red-200' : 'text-emerald-200'} />
                <Metric label="上涨家数" value={pct(selected?.up_ratio)} />
                <Metric label="大涨/涨停" value={`${selected?.big_up_count ?? 0}/${selected?.limit_up_count ?? 0}`} />
              </div>
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
                {selected?.readout || '选择左侧板块查看判断。'}
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="mb-3 text-sm font-semibold text-white">近20日主题强度曲线</div>
                <div className="h-[280px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={selected?.trend || []} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                      <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} minTickGap={24} />
                      <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={42} />
                      <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                      <Line type="monotone" dataKey="value" stroke="#38bdf8" strokeWidth={2} dot={false} name="相对强度" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="mb-3 text-sm font-semibold text-white">持续性排行</div>
                <div className="space-y-2">
                  {(snapshot?.persistence_top || []).slice(0, 8).map((sector, index) => (
                    <button key={sector.id} type="button" onClick={() => setSelectedId(sector.id)} className="flex w-full items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-left hover:border-slate-600">
                      <span className="w-5 text-xs text-slate-500">{index + 1}</span>
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{sector.name}</span>
                      <span className="text-sm font-semibold text-violet-200">{fmt(sector.persistence_score, 1)}</span>
                      <span className="w-16 text-right text-xs text-slate-500">5日 {pct(sector.return_5d)}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
              <div className="border-b border-slate-800 px-4 py-3 text-sm font-semibold text-white">板块代表票</div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left">
                  <thead className="bg-slate-950/50 text-xs text-slate-500">
                    <tr>
                      <th className="px-3 py-2">排名</th><th className="px-3 py-2">股票</th><th className="px-3 py-2">角色</th><th className="px-3 py-2 text-right">今日</th><th className="px-3 py-2 text-right">5日</th><th className="px-3 py-2 text-right">20日</th><th className="px-3 py-2 text-right">L2净流入</th><th className="px-3 py-2 text-right">成交额</th>
                    </tr>
                  </thead>
                  <tbody>{(selected?.stocks || []).map((stock, index) => <StockRow key={stock.symbol} stock={stock} index={index} />)}</tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs leading-6 text-slate-500">
          说明：第一版使用自定义主题篮子 + 本地 atomic_trade_daily/L2 数据计算市场热度；不全市场拉新闻、公告、财报。历史成分股暂按当前主题篮子近似回填，适合做市场温度计和后续回测验证。
        </div>
      </div>
    </div>
  );
};

export default MarketHeatPage;
