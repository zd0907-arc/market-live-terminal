import React, { useMemo } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { FundsBattleSignalTuning, IntradayFusionData } from '../../types';
import {
  BattlePoint,
  buildBattleSeries,
  DEFAULT_FUNDS_BATTLE_TICKS,
  DEFAULT_FUNDS_BATTLE_TUNING,
  formatFundsYAxis,
  gradientOffset,
} from './fundsBattleUtils';

interface FundsBattleL2PanelProps {
  data: IntradayFusionData | null;
  isLoading?: boolean;
  tuning?: FundsBattleSignalTuning;
}

const EmptyState: React.FC<{ text: string; isLoading?: boolean }> = ({ text, isLoading }) => (
  <div className="min-h-[220px] flex items-center justify-center text-sm text-slate-500">
    {isLoading ? '正在加载资金博弈L2...' : text}
  </div>
);

const SideSummary: React.FC<{ points: BattlePoint[] }> = ({ points }) => {
  const latest = points[points.length - 1];
  const maxAbsOib = Math.max(...points.map((point) => Math.abs(point.oibReal)), 1);
  const positivePct = latest.oibReal > 0 ? Math.min(100, (Math.abs(latest.oibReal) / maxAbsOib) * 100) : 0;
  const negativePct = latest.oibReal < 0 ? Math.min(100, (Math.abs(latest.oibReal) / maxAbsOib) * 100) : 0;

  return (
    <div className="w-[52px] shrink-0 rounded-md bg-slate-950/30 flex flex-col relative overflow-hidden">
      <div className="flex-1 flex flex-col items-center justify-center border-b border-slate-800/50 relative overflow-hidden">
        <div className="text-[9px] text-slate-500 absolute top-1 z-10">L2</div>
        <div className="text-yellow-400 font-bold text-xs mt-2 z-10">{latest.price.toFixed(2)}</div>
      </div>
      <div className="flex-[2] flex flex-col items-center justify-center py-1 gap-1">
        <div className="text-[8px] text-red-400 leading-none text-center">多:{formatFundsYAxis(Math.max(0, latest.oibReal))}</div>
        <div className="w-1.5 flex-1 bg-slate-800 rounded-full overflow-hidden relative flex flex-col">
          <div className="w-full bg-red-500 transition-all duration-300" style={{ height: `${positivePct}%` }} />
          <div className="h-[1px] w-full bg-white z-10 shadow-[0_0_2px_rgba(255,255,255,0.8)]" />
          <div className="w-full bg-green-500 transition-all duration-300 flex-1" style={{ opacity: negativePct > 0 ? 1 : 0.3 }} />
        </div>
        <div className="text-[8px] text-green-400 leading-none text-center">空:{formatFundsYAxis(Math.min(0, latest.oibReal))}</div>
      </div>
    </div>
  );
};

export const FundsBattleL2Panel: React.FC<FundsBattleL2PanelProps> = ({ data, isLoading = false, tuning = DEFAULT_FUNDS_BATTLE_TUNING }) => {
  const bars = data?.bars ?? [];
  const enableSignals = Boolean(data?.is_l2_finalized && data?.source !== 'history_l1_fallback');
  const { points, lacksOrderEventFactors } = useMemo(
    () =>
      buildBattleSeries(bars, 'l2', tuning, {
        enableSignals,
      }),
    [bars, tuning, enableSignals]
  );
  const off = useMemo(() => gradientOffset(points), [points]);
  const signalCount = useMemo(() => points.filter((point) => point.signal).length, [points]);
  const showSignalText = signalCount > 0 && signalCount <= 6;

  if (isLoading) return <EmptyState text="正在加载资金博弈L2..." isLoading />;
  if (!data) return <EmptyState text="暂无资金博弈L2数据" />;
  if (!data.is_l2_finalized || data.source === 'history_l1_fallback') {
    return (
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
        当前日期尚无 finalized L2，资金博弈L2 暂不可用。
      </div>
    );
  }
  if (points.length === 0) return <EmptyState text="当前日期暂无可用的 L2 资金博弈样本" />;

  return (
    <div className="rounded-lg bg-slate-900/35 p-1.5">
      <div className="mb-1 px-1">
        <h4 className="text-[11px] font-bold text-slate-300">L2 真实资金</h4>
        {lacksOrderEventFactors && (
          <div className="mt-0.5 text-[10px] text-slate-500">
            撤单因子未回补，信号保守。
          </div>
        )}
      </div>

      <div className="flex gap-1">
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          <div className="rounded bg-slate-950/20 p-1 relative">
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={points} syncId="fundsBattle5m" margin={{ top: 6, right: 0, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id={`funds-battle-l2-${data.symbol}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset={off} stopColor="#ef4444" stopOpacity={0.4} />
                    <stop offset={off} stopColor="#22c55e" stopOpacity={0.4} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" opacity={0.1} stroke="#334155" />
                <XAxis dataKey="timestamp" hide ticks={DEFAULT_FUNDS_BATTLE_TICKS} />
                <YAxis yAxisId="left" width={32} tickFormatter={formatFundsYAxis} style={{ fontSize: '9px' }} tick={{ fill: '#64748b' }} tickMargin={3} />
                <YAxis yAxisId="right" orientation="right" domain={['auto', 'auto']} hide />
                <Tooltip
                  contentStyle={{ backgroundColor: '#020617', borderColor: '#334155' }}
                  itemStyle={{ fontSize: 10 }}
                  formatter={(value: number, name: string) => (name === '价格' ? [value.toFixed(2), name] : [formatFundsYAxis(value), name])}
                />
                <ReferenceLine y={0} yAxisId="left" stroke="#475569" strokeDasharray="3 3" />
                <Area yAxisId="left" type="monotone" dataKey="cvd" name="L2 CVD" stroke="none" fill={`url(#funds-battle-l2-${data.symbol})`} isAnimationActive={false} />
                <Line yAxisId="right" type="monotone" dataKey="price" name="价格" stroke="#facc15" strokeWidth={2} dot={false} connectNulls />
                {points.map((entry, index) =>
                  entry.signal ? (
                    <ReferenceDot
                      yAxisId="left"
                      key={`${entry.timestamp}-${entry.signal.label}-${index}`}
                      x={entry.timestamp}
                      y={entry.cvd}
                      r={showSignalText ? 2.5 : 2}
                      fill={entry.signal.color}
                      stroke="#020617"
                      strokeWidth={showSignalText ? 1 : 0}
                      label={showSignalText ? {
                        position: 'top',
                        value: entry.signal.label,
                        fontSize: 9,
                        fontWeight: 600,
                        fill: entry.signal.color,
                      } : undefined}
                    />
                  ) : null
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded bg-slate-950/20 p-1">
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={points} syncId="fundsBattle5m" margin={{ top: 2, right: 0, left: -8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.1} stroke="#334155" />
                <XAxis dataKey="timestamp" style={{ fontSize: '9px' }} tick={{ fill: '#64748b' }} minTickGap={22} ticks={DEFAULT_FUNDS_BATTLE_TICKS} />
                <YAxis width={32} tickFormatter={formatFundsYAxis} style={{ fontSize: '9px' }} tick={{ fill: '#64748b' }} tickMargin={3} />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                  contentStyle={{ backgroundColor: '#020617', borderColor: '#334155' }}
                  itemStyle={{ fontSize: 10 }}
                  formatter={(_: number, __: string, item: any) => [formatFundsYAxis(item?.payload?.oibReal), 'L2 OIB']}
                />
                <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                <Bar dataKey="oib" isAnimationActive={false} name="L2 OIB">
                  {points.map((entry, index) => (
                    <Cell
                      key={`l2-oib-${index}`}
                      fill={entry.oib >= 0 ? '#ef4444' : '#22c55e'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <SideSummary points={points} />
      </div>
    </div>
  );
};

export default FundsBattleL2Panel;
