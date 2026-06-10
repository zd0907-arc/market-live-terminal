import React from 'react';

export type MiniKlinePoint = {
  trade_date?: string;
  datetime?: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
};

export type MiniKlineMarker = {
  date: string;
  label: string;
  tone?: 'buy' | 'sell' | 'neutral';
};

interface MiniKlineChartProps {
  points?: MiniKlinePoint[];
  height?: number;
  emptyText?: string;
  pointKeyPrefix?: string;
  markers?: MiniKlineMarker[];
  maxPoints?: number;
}

const movingAverage = (values: number[], windowSize: number) => values.map((_, index) => {
  if (index + 1 < windowSize) return null;
  const slice = values.slice(index + 1 - windowSize, index + 1);
  return slice.reduce((sum, value) => sum + value, 0) / windowSize;
});

const dateKey = (value?: string | null) => String(value || '').slice(0, 10);

const markerColor = (tone?: MiniKlineMarker['tone']) => {
  if (tone === 'buy') return '#38bdf8';
  if (tone === 'sell') return '#fb7185';
  return '#94a3b8';
};

const MiniKlineChart: React.FC<MiniKlineChartProps> = ({
  points = [],
  height = 86,
  emptyText = '暂无K线',
  pointKeyPrefix = 'mini-kline',
  markers = [],
  maxPoints = 45,
}) => {
  const clean = points
    .filter((point) => Number(point.open) > 0 && Number(point.high) > 0 && Number(point.low) > 0 && Number(point.close) > 0)
    .slice(-maxPoints);
  if (clean.length < 2) {
    return <div className="flex items-center justify-center text-[10px] text-slate-600" style={{ height }}>{emptyText}</div>;
  }

  const width = 360;
  const top = 4;
  const bottom = 4;
  const left = 4;
  const right = 4;
  const innerW = width - left - right;
  const innerH = height - top - bottom;
  const closes = clean.map((point) => Number(point.close || 0));
  const ma5 = movingAverage(closes, 5);
  const ma10 = movingAverage(closes, 10);
  const allValues = [
    ...clean.flatMap((point) => [Number(point.high || 0), Number(point.low || 0)]),
    ...ma5.filter((value): value is number => value != null),
    ...ma10.filter((value): value is number => value != null),
  ].filter((value) => Number.isFinite(value) && value > 0);
  if (!allValues.length) {
    return <div className="flex items-center justify-center text-[10px] text-slate-600" style={{ height }}>{emptyText}</div>;
  }

  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max > min ? max - min : Math.max(1, max * 0.04);
  const y = (value: number) => top + (max - value) / span * innerH;
  const step = innerW / Math.max(1, clean.length - 1);
  const candleW = Math.max(2.2, Math.min(4.2, step * 0.5));
  const markerIndexByDate = new Map(clean.map((point, index) => [dateKey(point.trade_date || point.datetime), index]));
  const linePath = (values: Array<number | null>) => values
    .map((value, index) => value == null ? null : `${index === values.findIndex((v) => v != null) ? 'M' : 'L'} ${left + index * step} ${y(value)}`)
    .filter(Boolean)
    .join(' ');
  const ma5Path = linePath(ma5);
  const ma10Path = linePath(ma10);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      shapeRendering="geometricPrecision"
      className="w-full overflow-hidden"
      style={{ height }}
    >
      <line x1={left} x2={width - right} y1={height - bottom} y2={height - bottom} stroke="#1e293b" strokeWidth="0.8" />
      {clean.map((point, index) => {
        const open = Number(point.open || 0);
        const close = Number(point.close || 0);
        const high = Number(point.high || 0);
        const low = Number(point.low || 0);
        const up = close >= open;
        const color = up ? '#fb7185' : '#22c55e';
        const wickColor = up ? '#f87171' : '#34d399';
        const x = left + index * step;
        const yOpen = y(open);
        const yClose = y(close);
        const bodyY = Math.min(yOpen, yClose);
        const bodyH = Math.max(1.5, Math.abs(yClose - yOpen));
        const isLast = index === clean.length - 1;
        const key = point.trade_date || point.datetime || `${pointKeyPrefix}-${index}`;
        return (
          <g key={`${pointKeyPrefix}-${key}`}>
            <line x1={x} x2={x} y1={y(high)} y2={y(low)} stroke={wickColor} strokeWidth={isLast ? 1.1 : 0.8} opacity={isLast ? 0.95 : 0.78} />
            <rect
              x={x - candleW / 2}
              y={bodyY}
              width={candleW}
              height={bodyH}
              rx={0}
              fill={color}
              stroke="none"
              opacity={isLast ? 1 : 0.9}
            />
            {isLast ? <circle cx={x} cy={y(close)} r="1.9" fill="#38bdf8" stroke="#0f172a" strokeWidth="0.8" /> : null}
          </g>
        );
      })}
      {ma10Path ? <path d={ma10Path} fill="none" stroke="#a78bfa" strokeWidth="1.25" opacity="0.9" strokeLinecap="round" strokeLinejoin="round" /> : null}
      {ma5Path ? <path d={ma5Path} fill="none" stroke="#fbbf24" strokeWidth="1.25" opacity="0.95" strokeLinecap="round" strokeLinejoin="round" /> : null}
      {markers.map((marker) => {
        const markerDate = dateKey(marker.date);
        const markerIndex = markerIndexByDate.get(markerDate);
        if (markerIndex == null) return null;
        const x = left + markerIndex * step;
        const color = markerColor(marker.tone);
        const labelX = Math.max(left + 10, Math.min(width - right - 10, x));
        return (
          <g key={`${pointKeyPrefix}-marker-${markerDate}-${marker.label}`}>
            <line x1={x} x2={x} y1={top} y2={height - bottom} stroke={color} strokeWidth="0.9" strokeDasharray="2 2" opacity="0.82" />
            <rect x={labelX - 9} y={top} width="18" height="11" rx="3" fill="#0f172a" stroke={color} strokeWidth="0.7" opacity="0.94" />
            <text x={labelX} y={top + 8} textAnchor="middle" fontSize="8" fontWeight="700" fill={color}>{marker.label}</text>
          </g>
        );
      })}
    </svg>
  );
};

export default MiniKlineChart;
