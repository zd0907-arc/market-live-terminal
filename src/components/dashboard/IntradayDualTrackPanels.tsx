import React, { useMemo } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { IntradayFusionBar, IntradayFusionData } from '../../types';

const SIGNAL_DIFF_THRESHOLD = 5_000_000;
const SIGNAL_CANCEL_THRESHOLD = 5_000_000;
const VWAP_DISTANCE_THRESHOLD = 0.003;
const VOLATILITY_CHANNEL_RATIO = 0.01;
const VOLUME_RESONANCE_RATIO = 1.2;

type TrackKey = 'l1' | 'l2';

interface PanelProps {
  data: IntradayFusionData | null;
  isLoading?: boolean;
}

interface MainFlowPoint {
  time: string;
  mainBuyAmount: number;
  mainSellAmount: number;
  mainSellAmountPlot: number;
  superBuyAmount: number;
  superSellAmount: number;
  superSellAmountPlot: number;
  mainParticipationRatio: number;
  superParticipationRatio: number;
  closePrice: number;
}

interface CumulativePoint {
  time: string;
  cumMainBuy: number;
  cumMainSell: number;
  cumNetInflow: number;
  cumSuperBuy: number;
  cumSuperSell: number;
  cumSuperNetInflow: number;
}

interface BattlePoint {
  time: string;
  cvd: number;
  oib: number;
  close: number;
  vwap: number;
  signal?: {
    label: '吃' | '出' | '诱空' | '诱多';
    color: string;
  };
}

const DEFAULT_TICKS = ['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00'];

function formatAmount(val?: number | null) {
  if (val === null || val === undefined || Number.isNaN(val)) return '--';
  return `${(Math.abs(val) / 10000).toFixed(1)}万`;
}

function formatAxisAmount(val: number) {
  if (!Number.isFinite(val)) return '--';
  return `${(val / 10000).toFixed(0)}`;
}

function trackValue(bar: IntradayFusionBar, key: TrackKey, field: 'main_buy' | 'main_sell' | 'super_buy' | 'super_sell' | 'net_inflow') {
  const map = {
    l1: {
      main_buy: bar.l1_main_buy,
      main_sell: bar.l1_main_sell,
      super_buy: bar.l1_super_buy,
      super_sell: bar.l1_super_sell,
      net_inflow: bar.l1_net_inflow,
    },
    l2: {
      main_buy: bar.l2_main_buy,
      main_sell: bar.l2_main_sell,
      super_buy: bar.l2_super_buy,
      super_sell: bar.l2_super_sell,
      net_inflow: bar.l2_net_inflow,
    },
  } as const;
  return Number(map[key][field] ?? 0);
}

function buildMainFlowSeries(bars: IntradayFusionBar[], key: TrackKey) {
  let cumMainBuy = 0;
  let cumMainSell = 0;
  let cumSuperBuy = 0;
  let cumSuperSell = 0;

  const instant: MainFlowPoint[] = [];
  const cumulative: CumulativePoint[] = [];

  for (const bar of bars) {
    const time = bar.datetime.slice(11, 16);
    const totalAmount = Number(bar.total_amount ?? 0);
    const mainBuy = trackValue(bar, key, 'main_buy');
    const mainSell = trackValue(bar, key, 'main_sell');
    const superBuy = trackValue(bar, key, 'super_buy');
    const superSell = trackValue(bar, key, 'super_sell');

    cumMainBuy += mainBuy;
    cumMainSell += mainSell;
    cumSuperBuy += superBuy;
    cumSuperSell += superSell;

    instant.push({
      time,
      mainBuyAmount: mainBuy,
      mainSellAmount: mainSell,
      mainSellAmountPlot: -mainSell,
      superBuyAmount: superBuy,
      superSellAmount: superSell,
      superSellAmountPlot: -superSell,
      mainParticipationRatio: totalAmount > 0 ? ((mainBuy + mainSell) / totalAmount) * 100 : 0,
      superParticipationRatio: totalAmount > 0 ? ((superBuy + superSell) / totalAmount) * 100 : 0,
      closePrice: Number(bar.close ?? 0),
    });

    cumulative.push({
      time,
      cumMainBuy,
      cumMainSell,
      cumNetInflow: cumMainBuy - cumMainSell,
      cumSuperBuy,
      cumSuperSell,
      cumSuperNetInflow: cumSuperBuy - cumSuperSell,
    });
  }

  return { instant, cumulative };
}

function gradientOffset(data: CumulativePoint[]) {
  if (data.length === 0) return 0.5;
  const max = Math.max(...data.map((i) => i.cumNetInflow));
  const min = Math.min(...data.map((i) => i.cumNetInflow));
  if (max <= 0) return 0;
  if (min >= 0) return 1;
  return max / (max - min);
}

function rollingAverage(values: number[]) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function buildBattleSeries(bars: IntradayFusionBar[], key: TrackKey, enableSignals: boolean) {
  const points: BattlePoint[] = [];
  let cumulativeCvd = 0;
  let cumulativeAmount = 0;
  let cumulativeVolume = 0;
  const recentAmounts: number[] = [];

  for (const bar of bars) {
    const totalAmount = Number(bar.total_amount ?? 0);
    const totalVolume = Number(bar.total_volume ?? 0);
    cumulativeAmount += totalAmount;
    cumulativeVolume += totalVolume;
    const close = Number(bar.close ?? 0);
    const vwap = cumulativeVolume > 0 ? cumulativeAmount / cumulativeVolume : close;
    recentAmounts.push(totalAmount);
    if (recentAmounts.length > 5) recentAmounts.shift();
    const avgAmount = rollingAverage(recentAmounts);
    const volumeResonance = avgAmount > 0 ? totalAmount >= avgAmount * VOLUME_RESONANCE_RATIO : false;
    const lowerChannel = vwap * (1 - VOLATILITY_CHANNEL_RATIO);
    const upperChannel = vwap * (1 + VOLATILITY_CHANNEL_RATIO);
    const belowVwap = close <= vwap * (1 - VWAP_DISTANCE_THRESHOLD);
    const aboveVwap = close >= vwap * (1 + VWAP_DISTANCE_THRESHOLD);
    const lowZone = close <= lowerChannel;
    const highZone = close >= upperChannel;

    const l1Net = Number(bar.l1_net_inflow ?? 0);
    const l2Net = Number(bar.l2_net_inflow ?? 0);
    const cvdDelta = key === 'l2' ? Number(bar.l2_cvd_delta ?? l2Net) : l1Net;
    const oibDelta = key === 'l2' ? Number(bar.l2_oib_delta ?? l2Net) : l1Net;
    cumulativeCvd += cvdDelta;

    let signal: BattlePoint['signal'];
    if (enableSignals && key === 'l2') {
      const diffBuy = l2Net - l1Net;
      const diffSell = l1Net - l2Net;
      const cancelBuy = Number(bar.cancel_buy_amount ?? 0);
      const cancelSell = Number(bar.cancel_sell_amount ?? 0);

      if (diffBuy > SIGNAL_DIFF_THRESHOLD && belowVwap && volumeResonance) {
        signal = { label: '吃', color: '#ef4444' };
      } else if (cancelSell > SIGNAL_CANCEL_THRESHOLD && (belowVwap || lowZone) && volumeResonance) {
        signal = { label: '诱空', color: '#ef4444' };
      } else if (diffSell > SIGNAL_DIFF_THRESHOLD && aboveVwap && volumeResonance) {
        signal = { label: '出', color: '#22c55e' };
      } else if (cancelBuy > SIGNAL_CANCEL_THRESHOLD && (aboveVwap || highZone) && volumeResonance) {
        signal = { label: '诱多', color: '#22c55e' };
      }
    }

    points.push({
      time: bar.datetime.slice(11, 16),
      cvd: cumulativeCvd,
      oib: oibDelta,
      close,
      vwap,
      signal,
    });
  }

  return points;
}

const EmptyState: React.FC<{ isLoading?: boolean; text: string }> = ({ isLoading, text }) => (
  <div className="h-full min-h-[240px] flex items-center justify-center text-sm text-slate-500">
    {isLoading ? '正在加载双轨数据...' : text}
  </div>
);

const FallbackNotice: React.FC<{ text: string }> = ({ text }) => (
  <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
    {text}
  </div>
);

const MainFlowTrackChart: React.FC<{ title: string; bars: IntradayFusionBar[]; track: TrackKey }> = ({ title, bars, track }) => {
  const { instant, cumulative } = useMemo(() => buildMainFlowSeries(bars, track), [bars, track]);
  const offset = useMemo(() => gradientOffset(cumulative), [cumulative]);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <div className="mb-3 text-sm font-bold text-slate-200">{title}</div>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={instant}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 11 }} ticks={DEFAULT_TICKS} interval="preserveStartEnd" />
              <YAxis yAxisId="amount" stroke="#94a3b8" tick={{ fontSize: 10 }} tickFormatter={formatAxisAmount} />
              <YAxis yAxisId="ratio" orientation="right" stroke="#cbd5e1" tick={{ fontSize: 10 }} unit="%" domain={[0, 100]} hide />
              <YAxis yAxisId="price" orientation="right" hide domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                itemStyle={{ fontSize: 12 }}
                formatter={(val: number, name: string) => {
                  if (name.includes('参与度')) return [`${val.toFixed(1)}%`, name];
                  if (name === '股价') return [val.toFixed(2), name];
                  return [formatAmount(val), name];
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" height={28} />
              <Bar yAxisId="amount" dataKey="mainBuyAmount" name="主力买入" fill="#f87171" barSize={5} />
              <Bar yAxisId="amount" dataKey="mainSellAmountPlot" name="主力卖出" fill="#4ade80" barSize={5} />
              <Bar yAxisId="amount" dataKey="superBuyAmount" name="超大单买入" fill="#9333ea" barSize={3} />
              <Bar yAxisId="amount" dataKey="superSellAmountPlot" name="超大单卖出" fill="#14532d" barSize={3} />
              <Line yAxisId="ratio" type="monotone" dataKey="mainParticipationRatio" name="主力参与度" stroke="#f8fafc" strokeWidth={1} dot={false} strokeOpacity={0.25} />
              <Line yAxisId="ratio" type="monotone" dataKey="superParticipationRatio" name="超大单参与度" stroke="#a855f7" strokeWidth={1} dot={false} strokeOpacity={0.3} />
              <Line yAxisId="price" type="monotone" dataKey="closePrice" name="股价" stroke="#facc15" strokeWidth={1} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={cumulative}>
              <defs>
                <linearGradient id={`splitColor-${title.replace(/\s+/g, '-')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset={offset} stopColor="#ef4444" stopOpacity={0.28} />
                  <stop offset={offset} stopColor="#22c55e" stopOpacity={0.28} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 11 }} ticks={DEFAULT_TICKS} interval="preserveStartEnd" />
              <YAxis yAxisId="net" stroke="#a78bfa" tick={{ fontSize: 10 }} tickFormatter={formatAxisAmount} />
              <YAxis yAxisId="total" orientation="right" hide />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                itemStyle={{ fontSize: 12 }}
                formatter={(val: number) => [formatAmount(val), '']}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" height={28} />
              <Area yAxisId="net" type="monotone" dataKey="cumNetInflow" name="主力净流入" stroke="none" fill={`url(#splitColor-${title.replace(/\s+/g, '-')})`} />
              <Line yAxisId="net" type="monotone" dataKey="cumSuperNetInflow" name="超大单净流入" stroke="#d946ef" strokeWidth={2} dot={false} strokeDasharray="5 5" />
              <Line yAxisId="total" type="monotone" dataKey="cumMainBuy" name="主力买入" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeOpacity={0.85} />
              <Line yAxisId="total" type="monotone" dataKey="cumMainSell" name="主力卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} strokeOpacity={0.85} />
              <Line yAxisId="total" type="monotone" dataKey="cumSuperBuy" name="超大单买入" stroke="#ef4444" strokeWidth={1.2} dot={false} strokeDasharray="3 3" strokeOpacity={0.85} />
              <Line yAxisId="total" type="monotone" dataKey="cumSuperSell" name="超大单卖出" stroke="#22c55e" strokeWidth={1.2} dot={false} strokeDasharray="3 3" strokeOpacity={0.85} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

const BattleTrackChart: React.FC<{
  title: string;
  bars: IntradayFusionBar[];
  track: TrackKey;
  enableSignals?: boolean;
}> = ({ title, bars, track, enableSignals = false }) => {
  const points = useMemo(() => buildBattleSeries(bars, track, enableSignals), [bars, track, enableSignals]);
  if (points.length === 0) return <EmptyState text="暂无资金博弈数据" />;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <div className="mb-3 text-sm font-bold text-slate-200">{title}</div>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points}>
              <defs>
                <linearGradient id={`battle-${track}-${title}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#60a5fa" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 11 }} ticks={DEFAULT_TICKS} interval="preserveStartEnd" />
              <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} tickFormatter={formatAxisAmount} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                itemStyle={{ fontSize: 12 }}
                formatter={(val: number, name: string) => [formatAmount(val), name]}
              />
              <ReferenceLine y={0} stroke="#475569" strokeDasharray="4 4" />
              <Area type="monotone" dataKey="cvd" name="CVD" stroke="#60a5fa" fill={`url(#battle-${track}-${title})`} strokeWidth={2} />
              {enableSignals &&
                points
                  .filter((point) => point.signal)
                  .map((point) => (
                    <ReferenceDot
                      key={`${title}-${point.time}-${point.signal?.label}`}
                      x={point.time}
                      y={point.cvd}
                      r={3}
                      fill={point.signal?.color}
                      stroke="none"
                      label={{
                        value: point.signal?.label,
                        position: 'top',
                        fill: point.signal?.color,
                        fontSize: 12,
                        fontWeight: 700,
                      }}
                    />
                  ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 11 }} ticks={DEFAULT_TICKS} interval="preserveStartEnd" />
              <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} tickFormatter={formatAxisAmount} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                itemStyle={{ fontSize: 12 }}
                formatter={(val: number, name: string) => [formatAmount(val), name]}
              />
              <ReferenceLine y={0} stroke="#475569" strokeDasharray="4 4" />
              <Bar dataKey="oib" name="OIB">
                {points.map((point) => (
                  <Cell key={`${title}-${point.time}`} fill={point.oib >= 0 ? '#f87171' : '#22c55e'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export const MainFlowDualTrackPanel: React.FC<PanelProps> = ({ data, isLoading = false }) => {
  const bars = data?.bars ?? [];
  const mode = data?.mode;
  const isHistoricalL1Fallback = data?.source === 'history_l1_fallback';

  if (isLoading) return <EmptyState isLoading text="正在加载主力动态..." />;
  if (bars.length === 0) return <EmptyState text="当前暂无主力动态 5m 数据" />;

  return (
    <div className="space-y-3">
      {isHistoricalL1Fallback && (
        <FallbackNotice text="当前交易日本地尚无 finalized L2，先回放 L1 5m 结果供本地联调查看。" />
      )}
      {mode === 'intraday_l1_only' || isHistoricalL1Fallback ? (
        <MainFlowTrackChart title="主力动态（盘中 L1 5m）" bars={bars} track="l1" />
      ) : (
        <>
          <MainFlowTrackChart title="L1 表象主力动态" bars={bars} track="l1" />
          <MainFlowTrackChart title="L2 真实主力动态" bars={bars} track="l2" />
        </>
      )}
    </div>
  );
};

export const FundsBattleDualTrackPanel: React.FC<PanelProps> = ({ data, isLoading = false }) => {
  const bars = data?.bars ?? [];
  const mode = data?.mode;
  const isHistoricalL1Fallback = data?.source === 'history_l1_fallback';

  if (isLoading) return <EmptyState isLoading text="正在加载资金博弈..." />;
  if (bars.length === 0) return <EmptyState text="当前暂无资金博弈 5m 数据" />;

  return (
    <div className="space-y-3">
      {isHistoricalL1Fallback && (
        <FallbackNotice text="当前交易日本地尚无 finalized L2，资金博弈先展示 L1 5m 回放；L2 双轨将在当日正式回补后自动切换。" />
      )}
      {mode === 'intraday_l1_only' ? (
        <BattleTrackChart title="[ 🕒 盘中 L1 快照估算 ]" bars={bars} track="l1" enableSignals={false} />
      ) : isHistoricalL1Fallback ? (
        <BattleTrackChart title="[ L1 历史回放 (缺少 finalized L2) ]" bars={bars} track="l1" enableSignals={false} />
      ) : (
        <>
          <BattleTrackChart title="[ L1 表象资金博弈 (快照推演) ]" bars={bars} track="l1" enableSignals={false} />
          <BattleTrackChart title="[ L2 真实资金博弈 (逐笔穿透) ]" bars={bars} track="l2" enableSignals />
        </>
      )}
    </div>
  );
};
