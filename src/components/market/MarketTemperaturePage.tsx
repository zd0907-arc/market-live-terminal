import React, { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowLeft, BarChart3, Flame, Layers, MoveRight, RefreshCw, ShieldAlert, Thermometer, TrendingUp } from 'lucide-react';

import {
  fetchFineHeatDashboard,
  fetchFineHeatDates,
  fetchMarketHeatLatest,
  FineHeatDashboard,
  FineHeatDatesData,
  FineHeatTheme,
  MarketHeatSnapshot,
  MarketHeatSector,
} from '../../services/marketHeatService';
import { fetchMarketTemperatureSnapshot, MarketTemperatureSnapshot } from '../../services/marketTemperatureService';
import { fetchSelectionMarketEnvironment } from '../../services/selectionService';
import { SelectionMarketEnvironment } from '../../types';
import { APP_VERSION } from '../../version';

const mono = 'font-mono tabular-nums';

const fmt = (value?: number | null, digits = 1) => (
  value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits)
);

const pct = (value?: number | null, digits = 1) => `${fmt(value, digits)}%`;
const yi = (value?: number | null, digits = 0) => `${fmt(value, digits)}亿`;
const ratioPct = (value?: number | null, digits = 1) => (
  value == null || Number.isNaN(Number(value)) ? '--%' : `${fmt(Number(value) * 100, digits)}%`
);

const waterTone = (score?: number | null) => {
  const value = Number(score ?? 0);
  if (value >= 70) return { label: '进攻', className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200', bar: 'bg-emerald-400' };
  if (value >= 45) return { label: '结构', className: 'border-amber-500/40 bg-amber-500/10 text-amber-200', bar: 'bg-amber-400' };
  if (value >= 25) return { label: '防守', className: 'border-orange-500/40 bg-orange-500/10 text-orange-200', bar: 'bg-orange-400' };
  return { label: '冰点', className: 'border-rose-500/40 bg-rose-500/10 text-rose-200', bar: 'bg-rose-400' };
};

const lifecycleTone = (label?: string | null) => {
  if (label === '首次新热') return 'border-red-500/35 bg-red-500/10 text-red-200';
  if (label === '主线再加速') return 'border-orange-500/35 bg-orange-500/10 text-orange-200';
  if (label === '持续升温') return 'border-amber-500/35 bg-amber-500/10 text-amber-200';
  if (label === '持续主线') return 'border-violet-500/35 bg-violet-500/10 text-violet-200';
  if (label === '退潮观察') return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-200';
  return 'border-slate-700 bg-slate-800/60 text-slate-300';
};

const uniqueThemes = (dashboard: FineHeatDashboard | null): FineHeatTheme[] => {
  if (!dashboard) return [];
  const groups = [
    dashboard.cards?.today_strong || [],
    dashboard.cards?.new_hot || [],
    dashboard.cards?.returning || [],
    dashboard.cards?.warming || [],
    dashboard.cards?.mainline || [],
    dashboard.cards?.fading || [],
    dashboard.pool || [],
  ];
  const byId = new Map<string, FineHeatTheme>();
  groups.flat().forEach((item) => {
    if (!byId.has(item.id)) byId.set(item.id, item);
  });
  return [...byId.values()];
};

const coarseNameFor = (name: string) => {
  const text = name.toLowerCase();
  if (/cpo|光通信|光模块|算力|服务器|数据中心|pcb|元件|高速连接|铜缆/.test(name)) return 'AI算力硬件';
  if (/半导体|芯片|存储|中芯|封测|光刻|电子化学|数字芯片|晶圆|oled|microled|miniled|显示/.test(name)) return '半导体/电子';
  if (/玻纤|玻璃|化学|材料|pvdf|氟|有机硅|工程|塑料/.test(name)) return '化工/新材料';
  if (/机器人|执行器|减速器|机器视觉|工业母机/.test(name)) return '机器人';
  if (/电池|锂|储能|光伏|新能源|固态/.test(name)) return '新能源';
  if (/白酒|食品|饮料|旅游|酒店|零售|消费|家电/.test(name)) return '消费';
  if (/煤炭|电力|石油|天然气|银行|保险|证券|红利/.test(name)) return '高股息/防守';
  if (/军工|航天|航空|船舶|卫星/.test(name)) return '军工航天';
  if (/医药|创新药|医疗|cxo|cro/.test(name) || text.includes('cxo')) return '医药';
  return '其他主题';
};

interface CoarseTheme {
  name: string;
  count: number;
  hotScore: number;
  avgRank: number;
  avgPct: number;
  amountRatio: number;
  l2Net: number;
  upRatio: number;
  topThemes: FineHeatTheme[];
  lifecycle: string;
}

const buildCoarseThemes = (dashboard: FineHeatDashboard | null): CoarseTheme[] => {
  const themes = uniqueThemes(dashboard);
  const groups = new Map<string, FineHeatTheme[]>();
  themes.forEach((item) => {
    const name = coarseNameFor(item.name);
    groups.set(name, [...(groups.get(name) || []), item]);
  });
  return [...groups.entries()].map(([name, items]) => {
    const sorted = [...items].sort((a, b) => Number(a.rank_today || 999) - Number(b.rank_today || 999));
    const avg = (selector: (item: FineHeatTheme) => number | undefined | null) => (
      items.reduce((sum, item) => sum + Number(selector(item) || 0), 0) / Math.max(items.length, 1)
    );
    const lifecycle = sorted.find((item) => item.lifecycle === '主线再加速')?.lifecycle
      || sorted.find((item) => item.lifecycle === '持续主线')?.lifecycle
      || sorted.find((item) => item.lifecycle === '持续升温')?.lifecycle
      || sorted[0]?.lifecycle
      || '观察';
    return {
      name,
      count: items.length,
      hotScore: avg((item) => item.hot_score),
      avgRank: avg((item) => item.rank_today),
      avgPct: avg((item) => item.pct_change),
      amountRatio: avg((item) => item.stock_summary?.avg_pct_change == null ? item.hot_change_5d : item.hot_change_5d),
      l2Net: items.reduce((sum, item) => sum + Number((item as any).l2_net_inflow_yi || 0), 0),
      upRatio: avg((item) => item.stock_summary?.up_ratio),
      topThemes: sorted.slice(0, 4),
      lifecycle,
    };
  }).sort((a, b) => b.hotScore - a.hotScore || a.avgRank - b.avgRank);
};

const MiniLine: React.FC<{
  points: Array<{ value?: number | null; label?: string | null }>;
  stroke?: string;
  height?: number;
  min?: number;
  max?: number;
}> = ({ points, stroke = '#38bdf8', height = 72, min, max }) => {
  const values = points.map((point) => Number(point.value)).filter(Number.isFinite);
  if (values.length < 2) return <div className="flex h-full items-center justify-center text-xs text-slate-600">暂无曲线</div>;
  const lo = min ?? Math.min(...values);
  const hi = max ?? Math.max(...values);
  const width = 360;
  const padX = 8;
  const padY = 8;
  const x = (index: number) => padX + index / Math.max(points.length - 1, 1) * (width - padX * 2);
  const y = (value: number) => padY + (hi - value) / Math.max(hi - lo, 1) * (height - padY * 2);
  const path = points.map((point, index) => {
    const value = Number(point.value);
    return `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${y(Number.isFinite(value) ? value : lo).toFixed(1)}`;
  }).join(' ');
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full" preserveAspectRatio="none" role="img">
      <line x1="0" y1={y((hi + lo) / 2)} x2={width} y2={y((hi + lo) / 2)} stroke="#334155" strokeDasharray="4 6" opacity="0.55" />
      <path d={path} fill="none" stroke="#020617" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" opacity="0.55" />
      <path d={path} fill="none" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(points.length - 1)} cy={y(Number(points[points.length - 1]?.value || 0))} r="3.5" fill={stroke} />
    </svg>
  );
};

const RankBars: React.FC<{ theme: FineHeatTheme; front?: number; hot?: number; watch?: number }> = ({ theme, front = 5, hot = 15, watch = 30 }) => {
  const points = theme.trend || [];
  if (!points.length) return <div className="h-6 rounded bg-slate-950/50" />;
  return (
    <div className="flex h-7 items-end gap-[1px]">
      {points.map((point) => {
        const rank = Number(point.rank || 999);
        const active = rank <= watch;
        const height = active ? Math.max(3, Math.min(28, (1 - (rank - 1) * 0.025) * 28)) : 2;
        const color = rank <= front ? 'bg-red-400' : rank <= hot ? 'bg-amber-400' : rank <= watch ? 'bg-sky-500' : 'bg-slate-700';
        return (
          <div
            key={`${theme.id}-${point.date}`}
            className={`min-w-[2px] flex-1 rounded-[1px] ${color}`}
            style={{ height, opacity: active ? 0.95 : 0.45 }}
            title={`${point.date} #${point.rank}`}
          />
        );
      })}
    </div>
  );
};

const StatCard: React.FC<{ label: string; value: React.ReactNode; note?: React.ReactNode; tone?: string }> = ({ label, value, note, tone = 'text-slate-100' }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-lg font-bold ${mono} ${tone}`}>{value}</div>
    {note ? <div className="mt-0.5 truncate text-[11px] text-slate-500">{note}</div> : null}
  </div>
);

const ThemeRow: React.FC<{ theme: FineHeatTheme; active?: boolean; onClick?: () => void }> = ({ theme, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`w-full border-b border-slate-800/80 px-3 py-2 text-left transition last:border-b-0 ${active ? 'bg-sky-500/10 shadow-[inset_3px_0_0_#38bdf8]' : 'bg-slate-950/25 hover:bg-slate-950/55'}`}
  >
    <div className="flex min-w-0 items-center justify-between gap-2">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-bold text-white">{theme.name}</span>
          <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] leading-3 ${lifecycleTone(theme.lifecycle)}`}>{theme.lifecycle}</span>
        </div>
        <div className={`mt-1 text-[11px] ${mono} text-slate-500`}>
          #{theme.rank_today} · 5日热区 {theme.hot_hits_5}/5 · 20日热区 {theme.hot_hits_20}/20
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className={`text-sm font-bold ${mono} ${Number(theme.pct_change) >= 0 ? 'text-red-300' : 'text-emerald-300'}`}>
          {Number(theme.pct_change) >= 0 ? '+' : ''}{fmt(theme.pct_change, 2)}%
        </div>
        <div className="text-[11px] text-slate-500">热度 {fmt(theme.hot_score, 1)}</div>
      </div>
    </div>
    <div className="mt-1.5"><RankBars theme={theme} /></div>
  </button>
);

const MarketTemperaturePage: React.FC = () => {
  const [dashboard, setDashboard] = useState<FineHeatDashboard | null>(null);
  const [marketEnv, setMarketEnv] = useState<SelectionMarketEnvironment | null>(null);
  const [temperatureSnapshot, setTemperatureSnapshot] = useState<MarketTemperatureSnapshot | null>(null);
  const [coarseSnapshot, setCoarseSnapshot] = useState<MarketHeatSnapshot | null>(null);
  const [fineDates, setFineDates] = useState<FineHeatDatesData | null>(null);
  const [selectedThemeId, setSelectedThemeId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [dates, fineData, envData, coarseData, temperatureData] = await Promise.all([
        fetchFineHeatDates(260),
        fetchFineHeatDashboard(120, undefined, 50),
        fetchSelectionMarketEnvironment(),
        fetchMarketHeatLatest(),
        fetchMarketTemperatureSnapshot(120),
      ]);
      setFineDates(dates);
      setDashboard(fineData);
      setMarketEnv(envData);
      setCoarseSnapshot(coarseData);
      setTemperatureSnapshot(temperatureData);
      const all = uniqueThemes(fineData);
      setSelectedThemeId((prev) => (prev && all.some((item) => item.id === prev) ? prev : all[0]?.id || ''));
    } catch (err) {
      setError(err instanceof Error ? err.message : '市场温度数据加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const allThemes = useMemo(() => uniqueThemes(dashboard), [dashboard]);
  const coarseThemes = useMemo(() => buildCoarseThemes(dashboard), [dashboard]);
  const selectedTheme = useMemo(() => allThemes.find((item) => item.id === selectedThemeId) || allThemes[0] || null, [allThemes, selectedThemeId]);
  const tone = waterTone(marketEnv?.water_score);
  const currentMarketState = temperatureSnapshot?.current || null;
  const csi1000Return5d = currentMarketState?.csi1000_return_5d_pct ?? marketEnv?.metrics?.csi1000_return_5d_pct;
  const risingThemes = useMemo(() => [
    ...(dashboard?.cards?.returning || []),
    ...(dashboard?.cards?.warming || []),
    ...(dashboard?.cards?.new_hot || []),
  ].slice(0, 8), [dashboard]);
  const coolingThemes = dashboard?.cards?.fading?.slice(0, 8) || [];
  const hotThemes = dashboard?.cards?.today_strong?.slice(0, 8) || [];
  const hotTop5Avg = useMemo(() => {
    const items = (dashboard?.cards?.today_strong || []).slice(0, 5);
    if (!items.length) return null;
    return items.reduce((sum, item) => sum + Number(item.hot_score || 0), 0) / items.length;
  }, [dashboard]);
  const recentTemperature = (marketEnv?.recent || []).map((point) => ({
    label: point.trade_date,
    value: point.water_score,
  }));
  const latestCoarse = coarseSnapshot?.hot_top?.slice(0, 6) || [];
  const latestFineDate = fineDates?.latest_cached_date || dashboard?.meta?.trade_date || marketEnv?.trade_date || '--';
  const latestTradeDate = fineDates?.latest_trade_date || latestFineDate;
  const staleFine = Boolean(fineDates?.latest_trade_date && dashboard?.meta?.trade_date && fineDates.latest_trade_date > dashboard.meta.trade_date);

  const explain = useMemo(() => {
    const score = Number(marketEnv?.water_score ?? 0);
    const themeText = hotThemes.slice(0, 3).map((item) => item.name).join('、') || '暂无热点';
    const risingText = risingThemes.slice(0, 2).map((item) => item.name).join('、') || '暂无升温';
    if (!marketEnv?.available) return '市场水位暂不可用，先按热点页状态观察。';
    if (score < 35) return `市场水位偏防守，但热点仍集中在 ${themeText}；可先看 ${risingText} 是否延续，不适合把热点当成普涨。`;
    if (score < 60) return `市场处于结构行情，主线集中在 ${themeText}；观察 ${risingText} 是否从细分热点扩散成粗赛道。`;
    return `市场温度偏热，${themeText} 处于活跃区；需要同步观察退潮池和炸板比例，避免追后排补涨。`;
  }, [marketEnv, hotThemes, risingThemes]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />返回主页面
          </a>
          <div className="mr-2 flex items-center gap-2 text-base font-bold text-white">
            <Thermometer className="h-5 w-5 text-orange-300" />市场温度雷达
          </div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">v{APP_VERSION}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">热点 {latestFineDate}</span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">底层 {latestTradeDate}</span>
          {staleFine ? <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">热点缓存待刷新</span> : null}
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm font-medium text-slate-100 hover:border-slate-500 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />刷新
          </button>
          <a href="/market-heat" className="inline-flex h-9 items-center gap-2 rounded-lg border border-amber-700/50 bg-amber-900/25 px-3 text-sm font-medium text-amber-100 hover:bg-amber-800/35">
            市场热点
          </a>
          <a href="/selection-research" className="inline-flex h-9 items-center gap-2 rounded-lg border border-emerald-700/50 bg-emerald-900/25 px-3 text-sm font-medium text-emerald-100 hover:bg-emerald-800/35">
            选股工作台
          </a>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-3 px-4 py-4 md:px-6">
        {error ? <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}

        <section className="grid gap-3 md:grid-cols-[210px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_360px]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">市场温度</span>
              <span className={`rounded border px-2 py-0.5 text-xs ${tone.className}`}>{tone.label}</span>
            </div>
            <div className="mt-2 flex items-end gap-2">
              <div className={`text-5xl font-black leading-none ${mono} text-orange-300`}>{fmt(marketEnv?.water_score, 0)}</div>
              <div className="pb-1 text-sm text-slate-500">/100</div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
              <div className={`h-full ${tone.bar}`} style={{ width: `${Math.max(0, Math.min(100, Number(marketEnv?.water_score ?? 0)))}%` }} />
            </div>
            <div className="mt-3 text-xs leading-5 text-slate-400">
              {marketEnv?.market_detail_label || marketEnv?.default_action || '暂无市场水位'}
            </div>
            <div className="mt-3 h-20 rounded-lg border border-slate-800 bg-slate-950/45 p-2">
              <MiniLine points={recentTemperature} min={0} max={100} stroke="#fb923c" />
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/75">
            <div className="border-b border-slate-800 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-base font-bold text-white">
                    <Activity className="h-5 w-5 text-sky-300" />盘后总览
                  </div>
                  <div className="mt-1 text-xs leading-5 text-slate-400">{explain}</div>
                </div>
                <div className={`text-right text-xs ${mono} text-slate-500`}>
                  <div>{dashboard?.meta?.start_date || '--'} → {dashboard?.meta?.end_date || '--'}</div>
                  <div>fine themes {dashboard?.meta?.fine_theme_count ?? '--'}</div>
                </div>
              </div>
            </div>
            <div className="grid gap-2 p-3 md:grid-cols-3 xl:grid-cols-6">
              <StatCard label="成交额" value={yi(currentMarketState?.market_total_amount_yi, 0)} note={`20日量比 ${fmt(currentMarketState?.market_amount_ratio_20d, 2)}`} />
              <StatCard label="上涨占比" value={ratioPct(currentMarketState?.market_advancer_ratio)} note={`中位 ${pct(currentMarketState?.market_median_return_pct, 2)}`} tone="text-sky-200" />
              <StatCard label="涨停/跌停" value={`${currentMarketState?.limit_up_count ?? '--'} / ${currentMarketState?.limit_down_count ?? '--'}`} note={`炸板率 ${ratioPct(currentMarketState?.broken_limit_up_ratio)}`} tone="text-red-200" />
              <StatCard label="CSI1000 5日" value={pct(csi1000Return5d)} note="小盘指数" tone={Number(csi1000Return5d || 0) >= 0 ? 'text-red-200' : 'text-emerald-200'} />
              <StatCard label="热点Top5均分" value={fmt(currentMarketState?.hot_theme_top5_avg_score ?? hotTop5Avg, 1)} note={`${hotThemes.length} 个前排主题`} tone="text-amber-200" />
              <StatCard label="热点L2净流" value={yi(currentMarketState?.hot_theme_top10_l2_net_yi, 1)} note="Top10 主题合计" tone={Number(currentMarketState?.hot_theme_top10_l2_net_yi || 0) >= 0 ? 'text-red-200' : 'text-emerald-200'} />
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/75 p-3 md:col-span-2 xl:col-span-1">
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-white">
              <ShieldAlert className="h-4 w-4 text-amber-300" />当前判断
            </div>
            <div className="space-y-2 text-xs leading-5 text-slate-400">
              <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-2">
                <b className="text-slate-200">主线：</b>{hotThemes.slice(0, 3).map((item) => item.name).join('、') || '--'}
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-2">
                <b className="text-slate-200">迁移：</b>{risingThemes.slice(0, 3).map((item) => item.name).join('、') || '--'} 升温；{coolingThemes.slice(0, 2).map((item) => item.name).join('、') || '暂无'} 退潮观察。
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-2">
                <b className="text-slate-200">动作：</b>{marketEnv?.default_action || '先观察'}；热点强不等同于全市场可做。
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-3 xl:grid-cols-[minmax(620px,1.1fr)_minmax(420px,0.9fr)]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/75">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-bold text-white"><Layers className="h-4 w-4 text-cyan-300" />粗赛道雷达</div>
                <div className="mt-1 text-xs text-slate-500">由细颗粒热点按关键词临时聚合；正式版建议落后端 canonical 粗主题聚合。</div>
              </div>
              <span className={`text-xs ${mono} text-slate-500`}>{coarseThemes.length} 个粗方向</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-xs">
                <thead className="border-b border-slate-800 bg-slate-950/45 text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">粗赛道</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 text-right font-medium">细分数</th>
                    <th className="px-3 py-2 text-right font-medium">均热度</th>
                    <th className="px-3 py-2 text-right font-medium">均排名</th>
                    <th className="px-3 py-2 font-medium">前排细分</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {coarseThemes.slice(0, 14).map((item) => (
                    <tr key={item.name} className="bg-slate-950/20 hover:bg-slate-950/45">
                      <td className="px-3 py-2 font-semibold text-white">{item.name}</td>
                      <td className="px-3 py-2"><span className={`rounded border px-1.5 py-0.5 text-[10px] ${lifecycleTone(item.lifecycle)}`}>{item.lifecycle}</span></td>
                      <td className={`px-3 py-2 text-right ${mono} text-slate-300`}>{item.count}</td>
                      <td className={`px-3 py-2 text-right ${mono} text-amber-200`}>{fmt(item.hotScore, 1)}</td>
                      <td className={`px-3 py-2 text-right ${mono} text-sky-200`}>#{fmt(item.avgRank, 0)}</td>
                      <td className="px-3 py-2 text-slate-400">{item.topThemes.map((theme) => theme.name).join('、')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/75">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-bold text-white">
                <MoveRight className="h-4 w-4 text-violet-300" />成交重心迁移
              </div>
              <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">升温 vs 退潮</span>
            </div>
            <div className="grid gap-3 p-3 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
              <div className="rounded-xl border border-red-500/20 bg-red-500/5">
                <div className="border-b border-red-500/20 px-3 py-2 text-xs font-bold text-red-200">正在增强</div>
                <div className="divide-y divide-slate-800/80">
                  {risingThemes.slice(0, 6).map((theme) => <ThemeRow key={`rising-${theme.id}`} theme={theme} active={selectedTheme?.id === theme.id} onClick={() => setSelectedThemeId(theme.id)} />)}
                </div>
              </div>
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5">
                <div className="border-b border-emerald-500/20 px-3 py-2 text-xs font-bold text-emerald-200">退潮观察</div>
                <div className="divide-y divide-slate-800/80">
                  {coolingThemes.slice(0, 6).map((theme) => <ThemeRow key={`cooling-${theme.id}`} theme={theme} active={selectedTheme?.id === theme.id} onClick={() => setSelectedThemeId(theme.id)} />)}
                  {!coolingThemes.length ? <div className="px-3 py-8 text-center text-xs text-slate-500">暂无退潮观察主题</div> : null}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-3 xl:grid-cols-[minmax(520px,0.82fr)_minmax(620px,1.18fr)]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/75">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-bold text-white"><Flame className="h-4 w-4 text-amber-300" />主题生命周期</div>
              <span className="text-xs text-slate-500">选择主题看近30日排名形态</span>
            </div>
            <div className="grid gap-3 p-3 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="max-h-[440px] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/35">
                {allThemes.slice(0, 24).map((theme) => <ThemeRow key={theme.id} theme={theme} active={selectedTheme?.id === theme.id} onClick={() => setSelectedThemeId(theme.id)} />)}
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-3">
                {selectedTheme ? (
                  <>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <div className="text-lg font-bold text-white">{selectedTheme.name}</div>
                          <span className={`rounded border px-2 py-0.5 text-xs ${lifecycleTone(selectedTheme.lifecycle)}`}>{selectedTheme.lifecycle}</span>
                        </div>
                        <div className={`mt-1 text-xs ${mono} text-slate-500`}>
                          今日#{selectedTheme.rank_today} · 近20日Top30 {selectedTheme.watch_hits_20}/20 · 最好#{selectedTheme.best_rank_20}
                        </div>
                      </div>
                      <div className={`text-right text-sm ${mono}`}>
                        <div className={Number(selectedTheme.pct_change) >= 0 ? 'text-red-300' : 'text-emerald-300'}>{Number(selectedTheme.pct_change) >= 0 ? '+' : ''}{fmt(selectedTheme.pct_change, 2)}%</div>
                        <div className="text-xs text-slate-500">热度 {fmt(selectedTheme.hot_score, 1)}</div>
                      </div>
                    </div>
                    <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/55 p-3">
                      <RankBars theme={selectedTheme} front={dashboard?.meta.front_band} hot={dashboard?.meta.hot_band} watch={dashboard?.meta.watch_band} />
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-3">
                      <StatCard label="近5日热区" value={`${selectedTheme.hot_hits_5}/5`} />
                      <StatCard label="近20日热区" value={`${selectedTheme.hot_hits_20}/20`} />
                      <StatCard label="热度变化" value={`${Number(selectedTheme.hot_change_5d) >= 0 ? '+' : ''}${fmt(selectedTheme.hot_change_5d, 1)}`} tone={Number(selectedTheme.hot_change_5d) >= 0 ? 'text-red-200' : 'text-emerald-200'} />
                    </div>
                    <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs leading-5 text-slate-400">
                      {selectedTheme.reason || selectedTheme.evidence?.join(' / ') || '暂无阶段解释'}
                    </div>
                  </>
                ) : (
                  <div className="py-12 text-center text-sm text-slate-500">暂无主题数据</div>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/75">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-bold text-white"><BarChart3 className="h-4 w-4 text-sky-300" />已有粗颗粒板块快照</div>
              <span className="text-xs text-slate-500">market_heat/latest</span>
            </div>
            <div className="grid gap-2 p-3 md:grid-cols-2 xl:grid-cols-3">
              {latestCoarse.map((sector: MarketHeatSector) => (
                <div key={sector.id} className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-bold text-white">{sector.name}</div>
                      <div className="mt-1 text-[11px] text-slate-500">{sector.readout || sector.description || '粗颗粒主题篮子'}</div>
                    </div>
                    <div className={`shrink-0 text-right ${mono}`}>
                      <div className="text-amber-200">{fmt(sector.hot_score, 0)}</div>
                      <div className="text-[11px] text-slate-500">热度</div>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                    <div><div className="text-slate-500">当日</div><div className={`${mono} ${Number(sector.pct_change) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>{Number(sector.pct_change) >= 0 ? '+' : ''}{pct(sector.pct_change, 2)}</div></div>
                    <div><div className="text-slate-500">成交</div><div className={`${mono} text-slate-200`}>{yi(sector.amount_yi, 0)}</div></div>
                    <div><div className="text-slate-500">L2</div><div className={`${mono} ${Number(sector.l2_net_inflow_yi) >= 0 ? 'text-red-200' : 'text-emerald-200'}`}>{yi(sector.l2_net_inflow_yi, 1)}</div></div>
                  </div>
                </div>
              ))}
              {!latestCoarse.length && !loading ? <div className="rounded-xl border border-slate-800 p-6 text-center text-sm text-slate-500">暂无粗颗粒板块快照</div> : null}
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
            <TrendingUp className="h-4 w-4 text-cyan-300" />第一版数据口径说明
          </div>
          <div className="grid gap-3 text-xs leading-5 text-slate-400 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3"><b className="text-slate-200">市场温度</b><br />暂复用选股环境门控水位，后续可拆成交、广度、情绪、指数位置贡献。</div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3"><b className="text-slate-200">赛道强度</b><br />细颗粒热点已经有排名、热度、Top30 命中、涨停和成分股确认。</div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3"><b className="text-slate-200">重心迁移</b><br />用主线再加速/持续升温/首次新热对照退潮观察，表示注意力迁移。</div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3"><b className="text-slate-200">粗细分层</b><br />当前前端临时聚合；正式版建议由 `tradable_theme_map` 后端输出稳定粗主题。</div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MarketTemperaturePage;
