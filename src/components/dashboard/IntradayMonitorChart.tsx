import React, { useMemo, useRef } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { GraphicComponent, GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { HistoryMultiframeGranularity, HistoryMultiframeItem, IntradayFusionBar, IntradayFusionData } from '../../types';
import { buildIntradaySlots, COMPACT_INTRADAY_AXIS_TICKS, inferIntradayStepFromTimes } from '../../utils/intradayTimeAxis';
import { BattlePoint, buildBattleSeries, DEFAULT_FUNDS_BATTLE_TUNING } from './fundsBattleUtils';

echarts.use([
  BarChart,
  CandlestickChart,
  LineChart,
  ScatterChart,
  GraphicComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
]);

type MonitorTrack = 'l1' | 'l2';
type MonitorMode = 'intraday' | 'history';

interface IntradayMonitorChartProps {
  data: IntradayFusionData | null;
  historyRows?: HistoryMultiframeItem[];
  mode?: MonitorMode;
  granularity?: HistoryMultiframeGranularity;
  isLoading?: boolean;
  height?: number;
  previousClose?: number | null;
  quoteDate?: string | null;
}

type MonitorRow = {
  key: string;
  axisLabel: string;
  title: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  totalAmount: number | null;
  mainBuy: number;
  mainSell: number;
  superBuy: number;
  superSell: number;
  mainParticipation: number | null;
  superParticipation: number | null;
};

const INTRADAY_VISIBLE_TICKS = new Set(COMPACT_INTRADAY_AXIS_TICKS);

const COLORS = {
  candleUp: '#ef4444',
  candleDown: '#22c55e',
  closeLine: '#fbbf24',
  mainBuy: '#ef4444',
  mainSell: '#22c55e',
  superBuy: '#a855f7',
  superSell: '#0f766e',
  mainParticipation: '#f8fafc',
  superParticipation: '#a855f7',
  oibPositive: '#ef4444',
  oibNegative: '#22c55e',
  grid: '#1e293b',
  axis: '#64748b',
};

const toFiniteNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const compactAmount = (value: number | null | undefined): string => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '--';
  const num = Number(value);
  const sign = num < 0 ? '-' : '';
  const abs = Math.abs(num);
  if (abs >= 100000000) return `${sign}${(abs / 100000000).toFixed(abs >= 1000000000 ? 1 : 2).replace(/\.0$/, '')}亿`;
  if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(abs >= 1000000 ? 1 : 2).replace(/\.0$/, '')}万`;
  return `${sign}${abs.toFixed(0)}`;
};

const formatPrice = (value: number | null | undefined): string => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '--';
  return Number(value).toFixed(2);
};

const formatPctValue = (value: number | null | undefined): string => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '--';
  return `${Number(value).toFixed(2)}%`;
};

const calcPriceChangePct = (price: number | null | undefined, previousClose: number | null | undefined) => {
  if (price === null || price === undefined || previousClose === null || previousClose === undefined) return null;
  const close = Number(price);
  const base = Number(previousClose);
  if (!Number.isFinite(close) || !Number.isFinite(base) || base <= 0) return null;
  return ((close - base) / base) * 100;
};

const pctAxisDomain = (values: Array<number | null>): [number, number] => {
  const finiteValues = values
    .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number);
  if (!finiteValues.length) return [-1, 1];
  const min = Math.min(0, ...finiteValues);
  const max = Math.max(0, ...finiteValues);
  const span = Math.max(Math.abs(min), Math.abs(max), 1);
  if (max <= 0) return [-span * 1.08, 0];
  if (min >= 0) return [0, span * 1.08];
  return [-span * 1.08, span * 1.08];
};

const pickTrackValue = (track: MonitorTrack, l2Value: unknown, l1Value: unknown) => {
  const l2 = toFiniteNumber(l2Value);
  const l1 = toFiniteNumber(l1Value);
  return Number(track === 'l2' ? (l2 ?? l1 ?? 0) : (l1 ?? 0));
};

const intradayTrackValue = (
  bar: IntradayFusionBar,
  track: MonitorTrack,
  field: 'mainBuy' | 'mainSell' | 'superBuy' | 'superSell',
) => {
  const values = track === 'l2'
    ? {
        mainBuy: bar.l2_main_buy,
        mainSell: bar.l2_main_sell,
        superBuy: bar.l2_super_buy,
        superSell: bar.l2_super_sell,
      }
    : {
        mainBuy: bar.l1_main_buy,
        mainSell: bar.l1_main_sell,
        superBuy: bar.l1_super_buy,
        superSell: bar.l1_super_sell,
      };
  return Number(values[field] ?? 0);
};

const chooseIntradayTrack = (data: IntradayFusionData | null): MonitorTrack => (
  data?.is_l2_finalized && data.source !== 'history_l1_fallback' ? 'l2' : 'l1'
);

const chooseHistoryTrack = (rows: HistoryMultiframeItem[] = []): MonitorTrack => (
  rows.some((row) => row.is_finalized && [row.l2_main_buy, row.l2_main_sell, row.l2_super_buy, row.l2_super_sell].some((value) => toFiniteNumber(value) !== null))
    ? 'l2'
    : 'l1'
);

const axisLabelForHistory = (row: HistoryMultiframeItem, granularity: HistoryMultiframeGranularity) => {
  if (granularity === '1d') return row.trade_date.slice(5);
  return `${row.trade_date.slice(5)}\n${row.datetime.slice(11, 16)}`;
};

const buildIntradayRows = (bars: IntradayFusionBar[], track: MonitorTrack): MonitorRow[] => bars
  .map((bar) => {
    const open = toFiniteNumber(bar.open);
    const high = toFiniteNumber(bar.high);
    const low = toFiniteNumber(bar.low);
    const close = toFiniteNumber(bar.close);
    const totalAmount = toFiniteNumber(bar.total_amount);
    const mainBuy = intradayTrackValue(bar, track, 'mainBuy');
    const mainSell = intradayTrackValue(bar, track, 'mainSell');
    const superBuy = intradayTrackValue(bar, track, 'superBuy');
    const superSell = intradayTrackValue(bar, track, 'superSell');
    const time = bar.datetime.slice(11, 16);
    return {
      key: bar.datetime,
      axisLabel: time,
      title: `${bar.trade_date} ${time}`,
      open,
      high,
      low,
      close,
      totalAmount,
      mainBuy,
      mainSell,
      superBuy,
      superSell,
      mainParticipation: totalAmount && totalAmount > 0 ? ((mainBuy + mainSell) / totalAmount) * 100 : null,
      superParticipation: totalAmount && totalAmount > 0 ? ((superBuy + superSell) / totalAmount) * 100 : null,
    };
  })
  .filter((row) => row.close !== null || row.mainBuy || row.mainSell || row.superBuy || row.superSell);

const buildHistoryRows = (
  rows: HistoryMultiframeItem[],
  track: MonitorTrack,
  granularity: HistoryMultiframeGranularity,
): MonitorRow[] => rows
  .map((row) => {
    const open = toFiniteNumber(row.open);
    const high = toFiniteNumber(row.high);
    const low = toFiniteNumber(row.low);
    const close = toFiniteNumber(row.close);
    const totalAmount = toFiniteNumber(row.total_amount);
    const mainBuy = pickTrackValue(track, row.l2_main_buy, row.l1_main_buy);
    const mainSell = pickTrackValue(track, row.l2_main_sell, row.l1_main_sell);
    const superBuy = pickTrackValue(track, row.l2_super_buy, row.l1_super_buy);
    const superSell = pickTrackValue(track, row.l2_super_sell, row.l1_super_sell);
    return {
      key: row.datetime,
      axisLabel: axisLabelForHistory(row, granularity),
      title: granularity === '1d' ? row.trade_date : row.datetime.slice(0, 16),
      open,
      high,
      low,
      close,
      totalAmount,
      mainBuy,
      mainSell,
      superBuy,
      superSell,
      mainParticipation: totalAmount && totalAmount > 0 ? ((mainBuy + mainSell) / totalAmount) * 100 : null,
      superParticipation: totalAmount && totalAmount > 0 ? ((superBuy + superSell) / totalAmount) * 100 : null,
    };
  })
  .filter((row) => row.close !== null || row.mainBuy || row.mainSell || row.superBuy || row.superSell)
  .sort((a, b) => a.key.localeCompare(b.key));

const buildHistoryBattlePoints = (rows: MonitorRow[]): BattlePoint[] => {
  let cvd = 0;
  return rows.map((row) => {
    const oibReal = row.mainBuy + row.superBuy - row.mainSell - row.superSell;
    cvd += oibReal;
    return {
      timestamp: row.key,
      cvd,
      oib: oibReal,
      oibReal,
      price: row.close ?? 0,
    };
  });
};

const linearAmountBound = (values: Array<number | null>) => {
  const absValues = values
    .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map((value) => Math.abs(Number(value)))
    .filter((value) => value > 0);
  if (!absValues.length) return 1;
  return Math.max(...absValues) * 1.12;
};

const paddedSignedDomain = (values: Array<number | null>, padRatio = 0.28): [number, number] => {
  const finiteValues = values
    .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number);
  if (!finiteValues.length) return [-1, 1];
  const min = Math.min(0, ...finiteValues);
  const max = Math.max(0, ...finiteValues);
  const span = Math.max(max - min, 1);
  const pad = span * padRatio;
  return [min - pad, max + pad];
};

const paddedValueDomain = (values: Array<number | null>, padRatio = 0.08): [number, number] | undefined => {
  const finiteValues = values
    .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number);
  if (!finiteValues.length) return undefined;
  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.004, 0.01);
    return [min - pad, max + pad];
  }
  const span = Math.max(max - min, 0.01);
  const pad = span * padRatio;
  return [min - pad, max + pad];
};

const axisMidInterval = (domain?: [number, number]) => {
  if (!domain) return undefined;
  const span = domain[1] - domain[0];
  return Number.isFinite(span) && span > 0 ? span / 2 : undefined;
};

const AXIS_BOUNDARY_LINE = { color: 'rgba(100,116,139,0.34)', width: 1, type: 'solid' };
const PRICE_ZERO_LINE = { color: 'rgba(251,191,36,0.42)', width: 1, type: 'dashed' };
const FUNDS_ZERO_LINE = { color: 'rgba(100,116,139,0.58)', width: 1, type: 'solid' };

const buildAxisReferenceMarkLine = (domain?: [number, number], zeroLineStyle = FUNDS_ZERO_LINE) => {
  if (!domain) return undefined;
  const [min, max] = domain;
  const values = [min, max];
  if (min < 0 && max > 0) values.push(0);
  return {
    silent: true,
    symbol: 'none',
    label: { show: false },
    data: values.map((value) => ({
      yAxis: value,
      lineStyle: Math.abs(value) < 1e-8 ? zeroLineStyle : AXIS_BOUNDARY_LINE,
    })),
  };
};

const axisPercentMax = (value: { max?: number; min?: number }) => {
  const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
  if (maxAbs <= 0) return 20;
  return Math.min(100, Math.max(20, Math.ceil((maxAbs * 1.18) / 10) * 10));
};

const cumulativeValues = (values: Array<number | null>) => {
  let running = 0;
  const validIndexes = values
    .map((value, index) => (value !== null && value !== undefined && Number.isFinite(Number(value)) ? index : -1))
    .filter((index) => index >= 0);
  const firstValidIndex = validIndexes[0] ?? -1;
  const lastValidIndex = validIndexes[validIndexes.length - 1] ?? -1;
  return values.map((value, index) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      return firstValidIndex >= 0 && index > firstValidIndex && index < lastValidIndex ? running : null;
    }
    running += Number(value);
    return running;
  });
};

const splitPositiveArea = (values: Array<number | null>) => values.map((value) => (value !== null && value >= 0 ? value : null));
const splitNegativeArea = (values: Array<number | null>) => values.map((value) => (value !== null && value < 0 ? value : null));

const tooltipRow = (label: string, value: string, color: string) => (
  `<div style="display:flex;align-items:center;justify-content:space-between;gap:14px;line-height:18px;">
    <span><span style="display:inline-block;width:7px;height:7px;border-radius:999px;background:${color};margin-right:5px;"></span>${label}</span>
    <span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#f8fafc;">${value}</span>
  </div>`
);

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const getMonitorTooltipPosition = (
  point: [number, number],
  size: { contentSize?: [number, number]; viewSize?: [number, number] },
  container: HTMLElement | null,
) => {
  const tooltipWidth = Number(size.contentSize?.[0] ?? 220);
  const tooltipHeight = Number(size.contentSize?.[1] ?? 150);
  const chartWidth = Number(size.viewSize?.[0] ?? 0);
  const chartHeight = Number(size.viewSize?.[1] ?? 0);
  const mouseX = Number(point?.[0] ?? 0);
  const mouseY = Number(point?.[1] ?? 0);

  if (!container || typeof window === 'undefined') {
    const x = mouseX < chartWidth / 2 ? mouseX + 12 : mouseX - tooltipWidth - 12;
    return [x, clamp(mouseY - tooltipHeight / 2, 6, Math.max(6, chartHeight - tooltipHeight - 6))];
  }

  const chartRect = container.getBoundingClientRect();
  const anchorRect = (container.closest('article') ?? container).getBoundingClientRect();
  const viewportWidth = window.innerWidth || chartRect.right;
  const viewportHeight = window.innerHeight || chartRect.bottom;
  const gap = 12;
  const edge = 8;
  const globalMouseX = chartRect.left + mouseX;
  const globalMouseY = chartRect.top + mouseY;
  const centerY = clamp(globalMouseY - tooltipHeight / 2, edge, Math.max(edge, viewportHeight - tooltipHeight - edge));
  const centerX = clamp(globalMouseX - tooltipWidth / 2, edge, Math.max(edge, viewportWidth - tooltipWidth - edge));
  const sideOrder = anchorRect.left + anchorRect.width / 2 <= viewportWidth / 2
    ? ['right', 'left']
    : ['left', 'right'];

  for (const side of sideOrder) {
    const x = side === 'right' ? anchorRect.right + gap : anchorRect.left - tooltipWidth - gap;
    if (x >= edge && x + tooltipWidth <= viewportWidth - edge) {
      return [x - chartRect.left, centerY - chartRect.top];
    }
  }

  const topY = anchorRect.top - tooltipHeight - gap;
  if (topY >= edge) {
    return [centerX - chartRect.left, topY - chartRect.top];
  }

  const bottomY = anchorRect.bottom + gap;
  if (bottomY + tooltipHeight <= viewportHeight - edge) {
    return [centerX - chartRect.left, bottomY - chartRect.top];
  }

  const fallbackX = mouseX <= chartWidth / 2 ? mouseX + gap : mouseX - tooltipWidth - gap;
  const fallbackY = mouseY <= chartHeight / 2 ? mouseY + gap : mouseY - tooltipHeight - gap;
  return [
    clamp(fallbackX, edge, Math.max(edge, chartWidth - tooltipWidth - edge)),
    clamp(fallbackY, edge, Math.max(edge, chartHeight - tooltipHeight - edge)),
  ];
};

const IntradayMonitorChart: React.FC<IntradayMonitorChartProps> = ({
  data,
  historyRows = [],
  mode = 'intraday',
  granularity = '1d',
  isLoading = false,
  height = 286,
  previousClose,
  quoteDate,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const track = mode === 'history' ? chooseHistoryTrack(historyRows) : chooseIntradayTrack(data);
  const rows = useMemo(
    () => (mode === 'history'
      ? buildHistoryRows(historyRows, track, granularity)
      : buildIntradayRows(data?.bars ?? [], track)),
    [data?.bars, granularity, historyRows, mode, track],
  );
  const battlePoints = useMemo(() => {
    if (mode === 'history') return buildHistoryBattlePoints(rows);
    return buildBattleSeries(data?.bars ?? [], track, DEFAULT_FUNDS_BATTLE_TUNING, { enableSignals: track === 'l2' }).points;
  }, [data?.bars, mode, rows, track]);

  const option = useMemo(() => {
    if (!rows.length) return {};

    const isIntradayMode = mode === 'intraday';
    const priceReference = (
      isIntradayMode
      && previousClose !== null
      && previousClose !== undefined
      && Number.isFinite(Number(previousClose))
      && Number(previousClose) > 0
      && (!quoteDate || !data?.trade_date || quoteDate === data.trade_date)
    )
      ? Number(previousClose)
      : null;
    const categories = isIntradayMode
      ? buildIntradaySlots(inferIntradayStepFromTimes(rows.map((row) => row.axisLabel), data?.bucket_granularity))
      : rows.map((row) => row.key);
    const rowByTime = new Map(rows.map((row) => [row.axisLabel, row]));
    const displayRows: Array<MonitorRow | null> = isIntradayMode
      ? categories.map((time) => rowByTime.get(time) ?? null)
      : rows;
    const battleByTime = new Map(battlePoints.map((point) => [point.timestamp, point]));
    const displayBattlePoints: Array<BattlePoint | null> = isIntradayMode
      ? categories.map((time) => battleByTime.get(time) ?? null)
      : categories.map((_, index) => battlePoints[index] ?? null);
    const labelInterval = isIntradayMode ? 0 : Math.max(0, Math.ceil(displayRows.length / 4) - 1);
    const candleData = displayRows.map((row) => (
      row && row.open !== null && row.close !== null && row.low !== null && row.high !== null
        ? [row.open, row.close, row.low, row.high]
        : ['-', '-', '-', '-']
    ));
    const closeLine = displayRows.map((row) => row?.close ?? null);
    const priceChangeLine = displayRows.map((row) => (
      isIntradayMode ? calcPriceChangePct(row?.close ?? null, priceReference) : null
    ));
    const usesPctPriceAxis = isIntradayMode && priceChangeLine.some((value) => value !== null);
    const priceLine = usesPctPriceAxis
      ? priceChangeLine
      : closeLine;
    const priceAxisDomain = usesPctPriceAxis
      ? pctAxisDomain(priceChangeLine)
      : paddedValueDomain(displayRows.flatMap((row) => [row?.open ?? null, row?.high ?? null, row?.low ?? null, row?.close ?? null]));
    const priceAxisInterval = axisMidInterval(priceAxisDomain);
    const mainParticipation = displayRows.map((row) => row?.mainParticipation ?? null);
    const superParticipation = displayRows.map((row) => row?.superParticipation ?? null);
    const mainBuy = displayRows.map((row) => row?.mainBuy ?? null);
    const mainSell = displayRows.map((row) => row ? -row.mainSell : null);
    const superBuy = displayRows.map((row) => row?.superBuy ?? null);
    const superSell = displayRows.map((row) => row ? -row.superSell : null);
    const bucketNet = displayRows.map((row) => (
      row ? row.mainBuy + row.superBuy - row.mainSell - row.superSell : null
    ));
    const cumulativeNet = isIntradayMode ? cumulativeValues(bucketNet) : displayRows.map(() => null);
    const cumulativeNetPositive = splitPositiveArea(cumulativeNet);
    const cumulativeNetNegative = splitNegativeArea(cumulativeNet);
    const oib = displayBattlePoints.map((point) => point?.oib ?? null);
    const cvd = displayBattlePoints.map((point) => point?.cvd ?? null);
    const fundingAxisBound = linearAmountBound([...mainBuy, ...mainSell, ...superBuy, ...superSell]);
    const fundingAxisDomain: [number, number] = [-fundingAxisBound, fundingAxisBound];
    const cumulativeAxisDomain = paddedSignedDomain(cumulativeNet, 0.55);
    const oibAxisBound = linearAmountBound(oib);
    const oibAxisDomain: [number, number] = [-oibAxisBound, oibAxisBound];
    const cvdAxisDomain = paddedSignedDomain(cvd, 0.24);
    const signalData = displayBattlePoints
      .map((point, index) => {
        if (!point?.signal) return null;
        return {
          value: [index, point.cvd],
          itemStyle: { color: point.signal.color, borderColor: '#020617', borderWidth: 1 },
          label: {
            show: true,
            formatter: point.signal.label,
            color: point.signal.color,
            fontSize: 9,
            fontWeight: 700,
            position: 'top',
          },
        };
      })
      .filter(Boolean);

    return {
      animation: false,
      backgroundColor: 'transparent',
      graphic: [
        { type: 'text', left: 6, top: 0, silent: true, style: { text: `${track.toUpperCase()} ${mode === 'history' ? 'K线' : '分时'} + 参与度`, fill: 'rgba(226,232,240,0.72)', fontSize: 9, fontWeight: 600 } },
        { type: 'text', left: 6, top: '44%', silent: true, style: { text: isIntradayMode ? '资金流入流出 / 累计净流' : '资金流入流出', fill: 'rgba(226,232,240,0.62)', fontSize: 9, fontWeight: 600 } },
        { type: 'text', left: 6, top: '71%', silent: true, style: { text: 'OIB红绿柱 / CVD白线', fill: 'rgba(226,232,240,0.62)', fontSize: 9, fontWeight: 600 } },
      ],
      axisPointer: { link: [{ xAxisIndex: [0, 1, 2] }] },
      tooltip: {
        trigger: 'axis',
        renderMode: 'html',
        appendTo: 'body',
        confine: false,
        position: (point: [number, number], _params: any, _el: unknown, _rect: unknown, size: { contentSize?: [number, number]; viewSize?: [number, number] }) => (
          getMonitorTooltipPosition(point, size, containerRef.current)
        ),
        axisPointer: { type: 'cross', label: { backgroundColor: '#0f172a' } },
        backgroundColor: 'rgba(2, 6, 23, 0.96)',
        borderColor: '#334155',
        textStyle: { color: '#cbd5e1', fontSize: 11 },
        extraCssText: 'box-shadow:0 12px 28px rgba(0,0,0,0.35);border-radius:8px;z-index:9999;pointer-events:none;',
        formatter: (params: any) => {
          const first = Array.isArray(params) ? params[0] : params;
          const index = Number(first?.dataIndex ?? 0);
          const row = displayRows[index];
          const point = displayBattlePoints[index];
          if (!row) {
            return `
              <div style="min-width:130px;">
                <div style="font-weight:700;color:#fff;margin-bottom:3px;">${categories[index] || ''} ${track.toUpperCase()}</div>
                <div style="color:#64748b;font-size:11px;">暂无数据</div>
              </div>
            `;
          }
          return `
            <div style="min-width:190px;">
              <div style="font-weight:700;color:#fff;margin-bottom:5px;">${row.title} ${track.toUpperCase()}</div>
              ${tooltipRow(mode === 'history' ? 'K线' : '价格', mode === 'history' ? `O ${formatPrice(row.open)} H ${formatPrice(row.high)} L ${formatPrice(row.low)} C ${formatPrice(row.close)}` : `${formatPrice(row.close)} / ${formatPctValue(priceChangeLine[index])}`, COLORS.closeLine)}
              ${tooltipRow('主力参与度', row.mainParticipation === null ? '--' : `${row.mainParticipation.toFixed(1)}%`, COLORS.mainParticipation)}
              ${tooltipRow('超大参与度', row.superParticipation === null ? '--' : `${row.superParticipation.toFixed(1)}%`, COLORS.superParticipation)}
              ${isIntradayMode ? tooltipRow('累计净流', compactAmount(cumulativeNet[index] ?? null), (cumulativeNet[index] ?? 0) >= 0 ? COLORS.oibPositive : COLORS.oibNegative) : ''}
              ${tooltipRow('主力买 / 卖', `${compactAmount(row.mainBuy)} / ${compactAmount(row.mainSell)}`, COLORS.mainBuy)}
              ${tooltipRow('超大买 / 卖', `${compactAmount(row.superBuy)} / ${compactAmount(row.superSell)}`, COLORS.superBuy)}
              ${tooltipRow('OIB净差', compactAmount(point?.oibReal ?? null), (point?.oibReal ?? 0) >= 0 ? COLORS.oibPositive : COLORS.oibNegative)}
              ${tooltipRow('CVD累计白线', compactAmount(point?.cvd ?? null), 'rgba(226,232,240,0.72)')}
            </div>
          `;
        },
      },
      grid: [
        { left: 6, right: 6, top: 14, height: '36%', containLabel: false },
        { left: 6, right: 6, top: '45%', height: '20%', containLabel: false },
        { left: 6, right: 6, top: '72%', height: '21%', containLabel: false },
      ],
      xAxis: [0, 1, 2].map((gridIndex) => ({
        type: 'category',
        gridIndex,
        data: categories,
        boundaryGap: true,
        axisLine: { lineStyle: { color: COLORS.grid } },
        axisTick: { show: false },
        axisLabel: gridIndex === 2
          ? {
              color: COLORS.axis,
              fontSize: 8,
              interval: labelInterval,
              hideOverlap: true,
              formatter: (value: string, index: number) => (
                isIntradayMode
                  ? (INTRADAY_VISIBLE_TICKS.has(value) ? value : '')
                  : displayRows[index]?.axisLabel ?? ''
              ),
            }
          : { show: false },
      })),
      yAxis: [
        {
          type: 'value',
          gridIndex: 0,
          scale: true,
          min: priceAxisDomain?.[0],
          max: priceAxisDomain?.[1],
          interval: priceAxisInterval,
          splitNumber: 2,
          axisLabel: {
            inside: true,
            color: 'rgba(251,191,36,0.65)',
            fontSize: 8,
            formatter: (value: number) => (usesPctPriceAxis ? `${value.toFixed(1)}%` : value.toFixed(2)),
          },
          axisTick: { show: false },
          axisLine: { show: false },
          splitLine: { show: false },
        },
        {
          type: 'value',
          gridIndex: 0,
          min: 0,
          max: axisPercentMax,
          show: false,
          splitLine: { show: false },
        },
        {
          type: 'value',
          gridIndex: 1,
          min: fundingAxisDomain[0],
          max: fundingAxisDomain[1],
          interval: fundingAxisBound,
          splitNumber: 2,
          axisLabel: { inside: true, color: 'rgba(148,163,184,0.62)', fontSize: 8, formatter: compactAmount },
          axisTick: { show: false },
          axisLine: { show: false },
          splitLine: { show: false },
        },
        {
          type: 'value',
          gridIndex: 1,
          min: cumulativeAxisDomain[0],
          max: cumulativeAxisDomain[1],
          show: false,
          splitLine: { show: false },
        },
        {
          type: 'value',
          gridIndex: 2,
          min: oibAxisDomain[0],
          max: oibAxisDomain[1],
          interval: oibAxisBound,
          splitNumber: 2,
          axisLabel: { inside: true, color: 'rgba(148,163,184,0.62)', fontSize: 8, formatter: compactAmount },
          axisTick: { show: false },
          axisLine: { show: false },
          splitLine: { show: false },
        },
        {
          type: 'value',
          gridIndex: 2,
          min: cvdAxisDomain[0],
          max: cvdAxisDomain[1],
          show: false,
          splitLine: { show: false },
        },
      ],
      series: [
        ...(mode === 'history'
          ? [
              {
                name: '价格K线',
                type: 'candlestick',
                xAxisIndex: 0,
                yAxisIndex: 0,
                data: candleData,
                itemStyle: {
                  color: COLORS.candleUp,
                  color0: COLORS.candleDown,
                  borderColor: COLORS.candleUp,
                  borderColor0: COLORS.candleDown,
                },
                barMaxWidth: 7,
                z: 5,
              },
              {
                name: '收盘价',
                type: 'line',
                xAxisIndex: 0,
                yAxisIndex: 0,
                data: priceLine,
                showSymbol: false,
                connectNulls: true,
                lineStyle: { color: COLORS.closeLine, width: 1, opacity: 0.95 },
                markLine: buildAxisReferenceMarkLine(priceAxisDomain, PRICE_ZERO_LINE),
                z: 6,
              },
            ]
          : [
              {
                name: '分时价格',
                type: 'line',
                xAxisIndex: 0,
                yAxisIndex: 0,
                data: priceLine,
                showSymbol: false,
                connectNulls: true,
                smooth: 0.25,
                markLine: buildAxisReferenceMarkLine(priceAxisDomain, PRICE_ZERO_LINE),
                lineStyle: { color: COLORS.closeLine, width: 1.6, opacity: 0.98 },
                z: 6,
              },
            ]),
        {
          name: '主力参与度',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 1,
          data: mainParticipation,
          showSymbol: false,
          connectNulls: true,
          smooth: 0.25,
          lineStyle: { color: COLORS.mainParticipation, width: 0.9, opacity: 0.24 },
          z: 4,
        },
        {
          name: '超大参与度',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 1,
          data: superParticipation,
          showSymbol: false,
          connectNulls: true,
          smooth: 0.25,
          lineStyle: { color: COLORS.superParticipation, width: 0.95, opacity: 0.30 },
          z: 4,
        },
        {
          name: '累计净流正区',
          type: 'line',
          xAxisIndex: 1,
          yAxisIndex: 3,
          data: cumulativeNetPositive,
          showSymbol: false,
          lineStyle: { width: 0, opacity: 0 },
          areaStyle: { color: 'rgba(239,68,68,0.30)' },
          z: 1,
          tooltip: { show: false },
        },
        {
          name: '累计净流负区',
          type: 'line',
          xAxisIndex: 1,
          yAxisIndex: 3,
          data: cumulativeNetNegative,
          showSymbol: false,
          lineStyle: { width: 0, opacity: 0 },
          areaStyle: { color: 'rgba(34,197,94,0.30)' },
          z: 1,
          tooltip: { show: false },
        },
        { name: '主力买入', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, data: mainBuy, barWidth: 3, itemStyle: { color: COLORS.mainBuy }, markLine: buildAxisReferenceMarkLine(fundingAxisDomain), z: 3 },
        { name: '主力卖出', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, data: mainSell, barWidth: 3, itemStyle: { color: COLORS.mainSell }, z: 3 },
        { name: '超大买入', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, data: superBuy, barWidth: 2.5, itemStyle: { color: COLORS.superBuy }, z: 4 },
        { name: '超大卖出', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, data: superSell, barWidth: 2.5, itemStyle: { color: COLORS.superSell }, z: 4 },
        {
          name: 'OIB',
          type: 'bar',
          xAxisIndex: 2,
          yAxisIndex: 4,
          data: oib,
          barWidth: 3.5,
          itemStyle: {
            color: (params: any) => Number(params.value) >= 0 ? COLORS.oibPositive : COLORS.oibNegative,
            opacity: 0.82,
          },
          markLine: buildAxisReferenceMarkLine(oibAxisDomain),
          z: 4,
        },
        {
          name: 'CVD走势',
          type: 'line',
          xAxisIndex: 2,
          yAxisIndex: 5,
          data: cvd,
          showSymbol: false,
          connectNulls: true,
          lineStyle: { color: 'rgba(226,232,240,0.58)', width: 1.05 },
          z: 7,
          tooltip: { show: false },
        },
        {
          name: '信号',
          type: 'scatter',
          xAxisIndex: 2,
          yAxisIndex: 5,
          data: signalData,
          symbolSize: 7,
          z: 10,
          tooltip: { show: false },
        },
      ],
    };
  }, [battlePoints, data?.bucket_granularity, data?.trade_date, mode, previousClose, quoteDate, rows, track]);

  if (isLoading && !rows.length) {
    return (
      <div className="flex items-center justify-center rounded border border-slate-800 bg-slate-950/45 text-xs text-slate-500" style={{ height }}>
        正在加载盯盘资金图...
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="flex items-center justify-center rounded border border-slate-800 bg-slate-950/45 text-xs text-slate-500" style={{ height }}>
        当前暂无可用资金融合数据
      </div>
    );
  }

  return (
    <div ref={containerRef} className="overflow-hidden rounded border border-slate-800 bg-slate-950/45">
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        notMerge
        lazyUpdate
        style={{ width: '100%', height }}
      />
    </div>
  );
};

export default IntradayMonitorChart;
