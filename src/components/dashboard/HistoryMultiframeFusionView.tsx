import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { CandlestickChart, CustomChart, LineChart, ScatterChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { AlertCircle, CircleHelp, Database, Minus, Plus, RefreshCw } from 'lucide-react';

import { HistoryMultiframeGranularity, HistoryMultiframeItem, SearchResult } from '../../types';
import * as StockService from '../../services/stockService';

echarts.use([
  CandlestickChart,
  CustomChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
]);

interface HistoryMultiframeFusionViewProps {
  activeStock: SearchResult | null;
  backendStatus: boolean;
  granularity: HistoryMultiframeGranularity;
  onGranularityChange: (value: HistoryMultiframeGranularity) => void;
}

type FusionRow = {
  key: string;
  label: string;
  datetime: string;
  tradeDate: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  totalAmount: number | null;
  source: string;
  isFinalized: boolean;
  previewLevel: string | null;
  fallbackUsed: boolean;
  isPreviewOnly: boolean;
  isPlaceholder: boolean;
  qualityInfo: string | null;
  l1MainBuy: number | null;
  l1MainSell: number | null;
  l1SuperBuy: number | null;
  l1SuperSell: number | null;
  l2MainBuy: number | null;
  l2MainSell: number | null;
  l2SuperBuy: number | null;
  l2SuperSell: number | null;
};

type FlowPanelKind = 'absolute' | 'net' | 'ratio';

type CustomSeriesDatum = {
  value: Array<number | null>;
};

type ZoomWindow = {
  start: number;
  end: number;
};

const LOOKBACK_DAYS: Record<HistoryMultiframeGranularity, number> = {
  '5m': 32,
  '15m': 32,
  '30m': 180,
  '1h': 180,
  '1d': 360,
};

const LABELS: Record<HistoryMultiframeGranularity, string> = {
  '5m': '5分钟',
  '15m': '15分钟',
  '30m': '30分钟',
  '1h': '1小时',
  '1d': '日线',
};

const GRANULARITY_BUTTONS: Array<{ value: HistoryMultiframeGranularity; label: string }> = [
  { value: '5m', label: '5分' },
  { value: '15m', label: '15分' },
  { value: '30m', label: '30分' },
  { value: '1h', label: '1小时' },
  { value: '1d', label: '日线' },
];

const BARS_PER_DAY: Record<HistoryMultiframeGranularity, number> = {
  '5m': 48,
  '15m': 16,
  '30m': 8,
  '1h': 4,
  '1d': 1,
};

const ZOOM_PRESETS: Record<HistoryMultiframeGranularity, Array<{ label: string; tradingDays: number }>> = {
  '5m': [
    { label: '当天', tradingDays: 1 },
    { label: '2天', tradingDays: 2 },
    { label: '5天', tradingDays: 5 },
    { label: '10天', tradingDays: 10 },
    { label: '1月', tradingDays: 22 },
  ],
  '15m': [
    { label: '当天', tradingDays: 1 },
    { label: '2天', tradingDays: 2 },
    { label: '5天', tradingDays: 5 },
    { label: '10天', tradingDays: 10 },
    { label: '1月', tradingDays: 22 },
  ],
  '30m': [
    { label: '1周', tradingDays: 5 },
    { label: '2周', tradingDays: 10 },
    { label: '1月', tradingDays: 22 },
    { label: '3月', tradingDays: 66 },
    { label: '半年', tradingDays: 132 },
  ],
  '1h': [
    { label: '1周', tradingDays: 5 },
    { label: '2周', tradingDays: 10 },
    { label: '1月', tradingDays: 22 },
    { label: '3月', tradingDays: 66 },
    { label: '半年', tradingDays: 132 },
  ],
  '1d': [
    { label: '1月', tradingDays: 20 },
    { label: '3月', tradingDays: 60 },
    { label: '半年', tradingDays: 120 },
    { label: '1年', tradingDays: 240 },
    { label: '全部', tradingDays: 320 },
  ],
};

const DEFAULT_ZOOM_INDEX: Record<HistoryMultiframeGranularity, number> = {
  '5m': 2,
  '15m': 2,
  '30m': 2,
  '1h': 2,
  '1d': 2,
};

const COLORS = {
  mainL2Buy: '#D32F2F',
  mainL1Buy: '#FFCDD2',
  mainL2Sell: '#388E3C',
  mainL1Sell: '#C8E6C9',
  superL2Buy: '#7B1FA2',
  superL1Buy: '#E1BEE7',
  superL2Sell: '#00796B',
  superL1Sell: '#B2DFDB',
  closeLine: '#FBBF24',
  candleUp: '#EF4444',
  candleDown: '#22C55E',
  border: '#1E293B',
  zeroLine: '#64748B',
  quality: '#F59E0B',
};

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);

const toFiniteNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const compactAmount = (value: number | null): string => {
  if (value === null || !Number.isFinite(value)) return '--';
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${sign}${(abs / 100000000).toFixed(abs >= 1000000000 ? 1 : 2).replace(/\.0$/, '')}亿`;
  if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(abs >= 1000000 ? 1 : 2).replace(/\.0$/, '')}万`;
  return `${sign}${abs.toFixed(0)}`;
};

const compactPercent = (value: number | null): string => {
  if (value === null || !Number.isFinite(value)) return '--';
  return `${value.toFixed(value >= 10 ? 1 : 2)}%`;
};

const formatPrice = (value: number | null): string => {
  if (value === null || !Number.isFinite(value)) return '--';
  return value.toFixed(2);
};

const toNet = (buy: number | null, sell: number | null): number | null => {
  if (buy === null || sell === null) return null;
  return buy - sell;
};

const toRatio = (value: number | null, totalAmount: number | null): number | null => {
  if (value === null || totalAmount === null || !Number.isFinite(totalAmount) || totalAmount <= 0) return null;
  return value / totalAmount * 100;
};

const normalizeQualityInfo = (value: string | null | undefined): string | null => {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (!text) return null;
  if (['none', 'null', 'nan', 'undefined'].includes(text.toLowerCase())) return null;
  return text;
};

const buildLabel = (row: HistoryMultiframeItem, granularity: HistoryMultiframeGranularity): string => {
  if (granularity === '1d') return row.trade_date.slice(5);
  const timePart = row.datetime.slice(11, 16);
  const datePart = row.trade_date.slice(5);
  if (timePart === '09:30' || timePart === '13:00') return `${datePart}\n${timePart}`;
  return timePart;
};

const buildRows = (
  rows: HistoryMultiframeItem[],
  granularity: HistoryMultiframeGranularity,
): FusionRow[] => rows
  .map((row) => {
    const source = row.source || 'unknown';
    const previewLevel = row.preview_level || null;
    const isFinalized = row.is_finalized === true;
    const isPreviewOnly = !isFinalized;
    const isPlaceholder = row.is_placeholder === true;
    const qualityInfo = normalizeQualityInfo(row.quality_info);
    const hasUsableL2 = isFinalized
      && [row.l2_main_buy, row.l2_main_sell, row.l2_super_buy, row.l2_super_sell].some((item) => toFiniteNumber(item) !== null);
    const hasUsableL1 = [row.l1_main_buy, row.l1_main_sell, row.l1_super_buy, row.l1_super_sell].some((item) => toFiniteNumber(item) !== null);

    if (!hasUsableL2 && !hasUsableL1 && !isPreviewOnly && !isPlaceholder) {
      return null;
    }

    return {
      key: row.datetime,
      label: buildLabel(row, granularity),
      datetime: row.datetime,
      tradeDate: row.trade_date,
      open: toFiniteNumber(row.open),
      high: toFiniteNumber(row.high),
      low: toFiniteNumber(row.low),
      close: toFiniteNumber(row.close),
      totalAmount: toFiniteNumber(row.total_amount),
      source,
      isFinalized,
      previewLevel,
      fallbackUsed: row.fallback_used === true,
      isPreviewOnly,
      isPlaceholder,
      qualityInfo,
      l1MainBuy: toFiniteNumber(row.l1_main_buy),
      l1MainSell: toFiniteNumber(row.l1_main_sell),
      l1SuperBuy: toFiniteNumber(row.l1_super_buy),
      l1SuperSell: toFiniteNumber(row.l1_super_sell),
      l2MainBuy: hasUsableL2 ? toFiniteNumber(row.l2_main_buy) : null,
      l2MainSell: hasUsableL2 ? toFiniteNumber(row.l2_main_sell) : null,
      l2SuperBuy: hasUsableL2 ? toFiniteNumber(row.l2_super_buy) : null,
      l2SuperSell: hasUsableL2 ? toFiniteNumber(row.l2_super_sell) : null,
    };
  })
  .filter((row): row is FusionRow => !!row)
  .sort((a, b) => a.datetime.localeCompare(b.datetime));

const buildPanelData = (rows: FusionRow[], kind: FlowPanelKind): CustomSeriesDatum[] => rows.map((row, index) => {
  if (kind === 'net') {
    return {
      value: [
        index,
        toNet(row.l2SuperBuy, row.l2SuperSell),
        toNet(row.l1SuperBuy, row.l1SuperSell),
        toNet(row.l2MainBuy, row.l2MainSell),
        toNet(row.l1MainBuy, row.l1MainSell),
      ],
    };
  }

  if (kind === 'ratio') {
    const l2SuperSell = toRatio(row.l2SuperSell, row.totalAmount);
    const l1SuperSell = toRatio(row.l1SuperSell, row.totalAmount);
    const l2MainSell = toRatio(row.l2MainSell, row.totalAmount);
    const l1MainSell = toRatio(row.l1MainSell, row.totalAmount);

    return {
      value: [
        index,
        toRatio(row.l2SuperBuy, row.totalAmount),
        toRatio(row.l1SuperBuy, row.totalAmount),
        l2SuperSell === null ? null : -l2SuperSell,
        l1SuperSell === null ? null : -l1SuperSell,
        toRatio(row.l2MainBuy, row.totalAmount),
        toRatio(row.l1MainBuy, row.totalAmount),
        l2MainSell === null ? null : -l2MainSell,
        l1MainSell === null ? null : -l1MainSell,
      ],
    };
  }

  return {
    value: [
      index,
      row.l2SuperBuy,
      row.l1SuperBuy,
      row.l2SuperSell === null ? null : -row.l2SuperSell,
      row.l1SuperSell === null ? null : -row.l1SuperSell,
      row.l2MainBuy,
      row.l1MainBuy,
      row.l2MainSell === null ? null : -row.l2MainSell,
      row.l1MainSell === null ? null : -row.l1MainSell,
    ],
  };
});

const getTooltipPosition = (point: number[], size: { viewSize: number[]; contentSize: number[] }): number[] => {
  const [x, y] = point;
  const [viewWidth, viewHeight] = size.viewSize;
  const [contentWidth, contentHeight] = size.contentSize;

  let left = x + 18;
  if (left + contentWidth > viewWidth - 12) {
    left = x - contentWidth - 18;
  }
  left = clamp(left, 12, Math.max(12, viewWidth - contentWidth - 12));

  let top = y - contentHeight / 2;
  if (top + contentHeight > viewHeight - 12) {
    top = viewHeight - contentHeight - 12;
  }
  top = clamp(top, 12, Math.max(12, viewHeight - contentHeight - 12));

  return [left, top];
};

const buildMetricTable = (
  title: string,
  accent: string,
  rows: Array<{ label: string; l2: number | null; l1: number | null; formatter: (value: number | null) => string }>,
): string => {
  const body = rows.map((item) => `
    <tr>
      <td style="padding:3px 0;color:#94A3B8;white-space:nowrap;">${item.label}</td>
      <td style="padding:3px 0;text-align:right;color:#E2E8F0;white-space:nowrap;">${item.formatter(item.l2)}</td>
      <td style="padding:3px 0;text-align:right;color:#E2E8F0;white-space:nowrap;">${item.formatter(item.l1)}</td>
    </tr>
  `).join('');

  return `
    <div style="border:1px solid rgba(51,65,85,.92);border-radius:10px;background:rgba(15,23,42,.72);padding:10px 12px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span style="display:inline-block;width:8px;height:8px;border-radius:999px;background:${accent};"></span>
        <span style="font-size:12px;font-weight:700;color:#F8FAFC;">${title}</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed;">
        <thead>
          <tr>
            <th style="text-align:left;color:#64748B;font-weight:600;padding-bottom:5px;white-space:nowrap;">指标</th>
            <th style="text-align:right;color:#64748B;font-weight:600;padding-bottom:5px;white-space:nowrap;">L2</th>
            <th style="text-align:right;color:#64748B;font-weight:600;padding-bottom:5px;white-space:nowrap;">L1</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
};

const buildTooltipHtml = (row: FusionRow): string => {
  const statusBadges = [
    row.isPreviewOnly ? '<span style="padding:2px 6px;border-radius:999px;background:rgba(245,158,11,.14);border:1px solid rgba(245,158,11,.25);color:#FCD34D;white-space:nowrap;">未结算</span>' : '',
    row.isPlaceholder ? '<span style="padding:2px 6px;border-radius:999px;background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.2);color:#BFDBFE;white-space:nowrap;">缺失占位</span>' : '',
    row.fallbackUsed ? '<span style="padding:2px 6px;border-radius:999px;background:rgba(148,163,184,.12);border:1px solid rgba(148,163,184,.2);color:#CBD5E1;white-space:nowrap;">fallback</span>' : '',
  ].filter(Boolean).join('');

  const notices = [
    row.isPreviewOnly ? '未结算 / 当前仅 L1 实时口径，L2 待盘后覆盖。' : '',
    row.qualityInfo ? `质量提示：${row.qualityInfo}` : '',
  ].filter(Boolean);

  return `
    <div style="width:332px;max-width:332px;color:#E2E8F0;">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px;">
        <div>
          <div style="font-size:14px;font-weight:700;color:#F8FAFC;white-space:nowrap;">${row.datetime}</div>
          <div style="margin-top:4px;font-size:11px;color:#94A3B8;white-space:nowrap;">source ${row.source} ｜ finalized ${row.isFinalized ? 'true' : 'false'}</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;">${statusBadges}</div>
      </div>

      <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:10px;table-layout:fixed;">
        <tbody>
          <tr>
            <td style="color:#94A3B8;padding:2px 0;white-space:nowrap;">日期</td>
            <td style="text-align:right;color:#E2E8F0;padding:2px 0;white-space:nowrap;">${row.tradeDate}</td>
          </tr>
          <tr>
            <td style="color:#94A3B8;padding:2px 0;white-space:nowrap;">OHLC</td>
            <td style="text-align:right;color:#E2E8F0;padding:2px 0;white-space:nowrap;">${formatPrice(row.open)} / ${formatPrice(row.high)} / ${formatPrice(row.low)} / ${formatPrice(row.close)}</td>
          </tr>
          <tr>
            <td style="color:#94A3B8;padding:2px 0;white-space:nowrap;">成交额</td>
            <td style="text-align:right;color:#E2E8F0;padding:2px 0;white-space:nowrap;">${compactAmount(row.totalAmount)}</td>
          </tr>
        </tbody>
      </table>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        ${buildMetricTable('超大单（左柱）', COLORS.superL2Buy, [
          { label: '买入', l2: row.l2SuperBuy, l1: row.l1SuperBuy, formatter: compactAmount },
          { label: '卖出', l2: row.l2SuperSell, l1: row.l1SuperSell, formatter: compactAmount },
          { label: '净流入', l2: toNet(row.l2SuperBuy, row.l2SuperSell), l1: toNet(row.l1SuperBuy, row.l1SuperSell), formatter: compactAmount },
          { label: '买入力度', l2: toRatio(row.l2SuperBuy, row.totalAmount), l1: toRatio(row.l1SuperBuy, row.totalAmount), formatter: compactPercent },
          { label: '卖出力度', l2: toRatio(row.l2SuperSell, row.totalAmount), l1: toRatio(row.l1SuperSell, row.totalAmount), formatter: compactPercent },
        ])}
        ${buildMetricTable('主力（右柱）', COLORS.mainL2Buy, [
          { label: '买入', l2: row.l2MainBuy, l1: row.l1MainBuy, formatter: compactAmount },
          { label: '卖出', l2: row.l2MainSell, l1: row.l1MainSell, formatter: compactAmount },
          { label: '净流入', l2: toNet(row.l2MainBuy, row.l2MainSell), l1: toNet(row.l1MainBuy, row.l1MainSell), formatter: compactAmount },
          { label: '买入力度', l2: toRatio(row.l2MainBuy, row.totalAmount), l1: toRatio(row.l1MainBuy, row.totalAmount), formatter: compactPercent },
          { label: '卖出力度', l2: toRatio(row.l2MainSell, row.totalAmount), l1: toRatio(row.l1MainSell, row.totalAmount), formatter: compactPercent },
        ])}
      </div>

      ${notices.length ? `<div style="margin-top:10px;border-radius:10px;border:1px solid rgba(250,204,21,.18);background:rgba(250,204,21,.08);padding:9px 10px;font-size:11px;line-height:1.6;color:#FDE68A;word-break:break-word;">${notices.join('<br/>')}</div>` : ''}
    </div>
  `;
};

const createFlowCustomSeries = (
  name: string,
  panel: FlowPanelKind,
  xAxisIndex: number,
  yAxisIndex: number,
  data: CustomSeriesDatum[],
  categoryCount: number,
): any => {
  const encode = panel === 'net'
    ? { x: 0, y: [1, 2, 3, 4] }
    : { x: 0, y: [1, 2, 3, 4, 5, 6, 7, 8] };

  return {
    name,
    type: 'custom',
    xAxisIndex,
    yAxisIndex,
    coordinateSystem: 'cartesian2d',
    data,
    encode,
    silent: false,
    z: 3,
    animation: false,
    markLine: {
      silent: true,
      symbol: ['none', 'none'],
      label: { show: false },
      lineStyle: { color: COLORS.zeroLine, width: 1, opacity: 0.9 },
      data: [{ yAxis: 0 }],
    },
    renderItem: (params: any, api: any) => {
      const categoryIndex = Number(api.value(0));
      const coordSys = params.coordSys;
      const xCenter = api.coord([categoryIndex, 0])[0];
      const zeroY = api.coord([categoryIndex, 0])[1];
      const bandWidth = coordSys.width / Math.max(categoryCount, 1);
      const barWidth = clamp(bandWidth * 0.22, 4, panel === '1d' ? 14 : 12);
      const groupGap = clamp(barWidth * 0.55, 3, 10);
      const superCenter = xCenter - (barWidth / 2 + groupGap / 2);
      const mainCenter = xCenter + (barWidth / 2 + groupGap / 2);
      const chartRect = { x: coordSys.x, y: coordSys.y, width: coordSys.width, height: coordSys.height };

      const makeRect = (centerX: number, value: number | null, color: string) => {
        if (value === null || !Number.isFinite(value)) return null;
        const valueY = api.coord([categoryIndex, value])[1];
        const rectShape = echarts.graphic.clipRectByRect({
          x: centerX - barWidth / 2,
          y: Math.min(zeroY, valueY),
          width: barWidth,
          height: Math.max(Math.abs(zeroY - valueY), 1),
        }, chartRect);
        if (!rectShape) return null;
        return {
          type: 'rect',
          shape: rectShape,
          style: {
            fill: color,
            stroke: undefined,
          },
          silent: true,
        };
      };

      const children: any[] = [];

      if (panel === 'net') {
        children.push(makeRect(superCenter, api.value(1), Number(api.value(1)) >= 0 ? COLORS.superL2Buy : COLORS.superL2Sell));
        children.push(makeRect(superCenter, api.value(2), Number(api.value(2)) >= 0 ? COLORS.superL1Buy : COLORS.superL1Sell));
        children.push(makeRect(mainCenter, api.value(3), Number(api.value(3)) >= 0 ? COLORS.mainL2Buy : COLORS.mainL2Sell));
        children.push(makeRect(mainCenter, api.value(4), Number(api.value(4)) >= 0 ? COLORS.mainL1Buy : COLORS.mainL1Sell));
      } else {
        children.push(makeRect(superCenter, api.value(1), COLORS.superL2Buy));
        children.push(makeRect(superCenter, api.value(3), COLORS.superL2Sell));
        children.push(makeRect(superCenter, api.value(2), COLORS.superL1Buy));
        children.push(makeRect(superCenter, api.value(4), COLORS.superL1Sell));
        children.push(makeRect(mainCenter, api.value(5), COLORS.mainL2Buy));
        children.push(makeRect(mainCenter, api.value(7), COLORS.mainL2Sell));
        children.push(makeRect(mainCenter, api.value(6), COLORS.mainL1Buy));
        children.push(makeRect(mainCenter, api.value(8), COLORS.mainL1Sell));
      }

      return {
        type: 'group',
        children: children.filter(Boolean),
      };
    },
  };
};

const buildZoomWindowFromVisibleBars = (totalBars: number, visibleBars: number): ZoomWindow => {
  if (totalBars <= 0) return { start: 0, end: 100 };
  const safeVisible = clamp(visibleBars, 1, totalBars);
  if (safeVisible >= totalBars) return { start: 0, end: 100 };
  const start = ((totalBars - safeVisible) / totalBars) * 100;
  return { start, end: 100 };
};

const normalizeZoomWindow = (start: number, end: number, minRange: number): ZoomWindow => {
  const safeMin = clamp(minRange, 0.2, 100);
  let nextStart = clamp(start, 0, 100);
  let nextEnd = clamp(end, 0, 100);
  if (nextEnd - nextStart < safeMin) {
    const center = (nextStart + nextEnd) / 2;
    nextStart = clamp(center - safeMin / 2, 0, 100 - safeMin);
    nextEnd = clamp(nextStart + safeMin, safeMin, 100);
  }
  if (nextStart <= 0 && nextEnd >= 100) return { start: 0, end: 100 };
  return { start: nextStart, end: nextEnd };
};

const getVisibleBarsForPreset = (granularity: HistoryMultiframeGranularity, presetIndex: number): number => {
  const preset = ZOOM_PRESETS[granularity][presetIndex] ?? ZOOM_PRESETS[granularity][DEFAULT_ZOOM_INDEX[granularity]];
  return preset.tradingDays * BARS_PER_DAY[granularity];
};

const inferNearestPresetIndex = (granularity: HistoryMultiframeGranularity, totalBars: number, zoomWindow: ZoomWindow): number => {
  if (totalBars <= 0) return DEFAULT_ZOOM_INDEX[granularity];
  const visibleBars = totalBars * Math.max(0.01, (zoomWindow.end - zoomWindow.start) / 100);
  let bestIndex = DEFAULT_ZOOM_INDEX[granularity];
  let bestDistance = Number.POSITIVE_INFINITY;
  ZOOM_PRESETS[granularity].forEach((preset, index) => {
    const presetBars = preset.tradingDays * BARS_PER_DAY[granularity];
    const distance = Math.abs(presetBars - visibleBars);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
};

const formatAxisLabel = (rows: FusionRow[], granularity: HistoryMultiframeGranularity, index: number): string => {
  const row = rows[index];
  if (!row) return '';
  const prev = rows[index - 1];

  if (granularity === '1d') {
    const month = row.tradeDate.slice(0, 7);
    const prevMonth = prev?.tradeDate.slice(0, 7);
    if (index === 0 || month !== prevMonth) return row.tradeDate.slice(2, 7);
    if (index === rows.length - 1) return row.tradeDate.slice(5);
    return '';
  }

  const time = row.datetime.slice(11, 16);
  const isDayStart = !prev || prev.tradeDate !== row.tradeDate;
  if (isDayStart) return `${row.tradeDate.slice(5)}\n${time}`;

  if ((granularity === '30m' || granularity === '1h') && time === '13:00') return '13:00';
  if ((granularity === '5m' || granularity === '15m') && (time === '10:30' || time === '14:00')) return time;
  if (index === rows.length - 1) return time;
  return '';
};

const InfoPopover: React.FC<{
  children: React.ReactNode;
  align?: 'left' | 'right';
  widthClass?: string;
}> = ({ children, align = 'left', widthClass = 'w-[300px] sm:w-[340px]' }) => (
  <div className="relative group inline-flex">
    <button
      type="button"
      className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-700 bg-slate-900/80 text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-100"
    >
      <CircleHelp className="h-3.5 w-3.5" />
    </button>
    <div
      className={`pointer-events-none absolute top-full z-20 mt-2 hidden rounded-xl border border-slate-700 bg-slate-950/95 p-3 text-left text-[11px] leading-5 text-slate-300 shadow-2xl backdrop-blur group-hover:block ${widthClass} ${align === 'right' ? 'right-0' : 'left-0'}`}
    >
      {children}
    </div>
  </div>
);

const HistoryMultiframeFusionView: React.FC<HistoryMultiframeFusionViewProps> = ({
  activeStock,
  backendStatus,
  granularity,
  onGranularityChange,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [rows, setRows] = useState<HistoryMultiframeItem[]>([]);
  const [zoomWindow, setZoomWindow] = useState<ZoomWindow>({ start: 0, end: 100 });
  const [isTouchDevice, setIsTouchDevice] = useState(false);

  const chartRef = useRef<ReactEChartsCore | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const longPressTimerRef = useRef<number | null>(null);
  const touchActiveRef = useRef(false);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      if (!activeStock) return;
      setLoading(true);
      setError('');
      try {
        const data = await StockService.fetchHistoryMultiframe(activeStock.symbol, {
          granularity,
          days: LOOKBACK_DAYS[granularity],
          includeTodayPreview: true,
        });
        setRows(data);
      } catch (e: any) {
        setError(e?.message || '获取历史多维数据失败');
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [activeStock, granularity, refreshKey]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const media = window.matchMedia('(pointer: coarse)');
    const sync = () => setIsTouchDevice(media.matches || window.innerWidth < 768);
    sync();
    media.addEventListener?.('change', sync);
    window.addEventListener('resize', sync);
    return () => {
      media.removeEventListener?.('change', sync);
      window.removeEventListener('resize', sync);
    };
  }, []);

  const fusionRows = useMemo(() => buildRows(rows, granularity), [rows, granularity]);
  const issueRows = useMemo(() => fusionRows.filter((row) => !!row.qualityInfo), [fusionRows]);

  const hasFormalL2History = fusionRows.some(
    (row) => row.isFinalized && !row.isPlaceholder && [row.l2MainBuy, row.l2MainSell, row.l2SuperBuy, row.l2SuperSell].some((item) => item !== null),
  );
  const hasPreviewRows = fusionRows.some((row) => row.isPreviewOnly);
  const issueCount = issueRows.length;

  useEffect(() => {
    if (!fusionRows.length) {
      setZoomWindow({ start: 0, end: 100 });
      return;
    }
    const defaultVisibleBars = getVisibleBarsForPreset(granularity, DEFAULT_ZOOM_INDEX[granularity]);
    setZoomWindow(buildZoomWindowFromVisibleBars(fusionRows.length, defaultVisibleBars));
  }, [fusionRows.length, granularity]);

  const sourceLabel = useMemo(() => {
    if (hasFormalL2History && hasPreviewRows) return '正式L2 + 今日L1';
    if (hasFormalL2History) return '正式L2';
    if (hasPreviewRows) return '今日L1预览';
    if (fusionRows.length) return '占位 / 待补';
    return '暂无正式L2';
  }, [fusionRows.length, hasFormalL2History, hasPreviewRows]);

  const issueTagLabel = issueCount > 0 ? `${issueCount}条缺失 / 异常` : '数据完整';

  const handleZoomStep = useCallback((direction: 'in' | 'out') => {
    const totalBars = fusionRows.length;
    if (!totalBars) return;
    const currentIndex = inferNearestPresetIndex(granularity, totalBars, zoomWindow);
    const nextIndex = clamp(
      currentIndex + (direction === 'in' ? -1 : 1),
      0,
      ZOOM_PRESETS[granularity].length - 1,
    );
    const visibleBars = getVisibleBarsForPreset(granularity, nextIndex);
    setZoomWindow(buildZoomWindowFromVisibleBars(totalBars, visibleBars));
  }, [fusionRows.length, granularity, zoomWindow]);

  const handleDataZoom = useCallback((event: any) => {
    const payload = Array.isArray(event?.batch) && event.batch.length ? event.batch[event.batch.length - 1] : event;
    const start = Number(payload?.start);
    const end = Number(payload?.end);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    setZoomWindow({ start, end });
  }, []);

  useEffect(() => {
    if (!chartContainerRef.current) return undefined;
    const element = chartContainerRef.current;
    const handleWheel = (event: WheelEvent) => {
      if (!event.metaKey || event.ctrlKey) return;
      event.preventDefault();
      setZoomWindow((prev) => {
        const totalBars = fusionRows.length;
        const minRange = totalBars > 0 ? Math.max((2 / totalBars) * 100, 0.6) : 0.6;
        const currentRange = Math.max(prev.end - prev.start, minRange);
        const nextRange = clamp(currentRange * (event.deltaY > 0 ? 1.16 : 0.86), minRange, 100);
        const center = (prev.start + prev.end) / 2;
        return normalizeZoomWindow(center - nextRange / 2, center + nextRange / 2, minRange);
      });
    };

    element.addEventListener('wheel', handleWheel, { passive: false });
    return () => element.removeEventListener('wheel', handleWheel);
  }, [fusionRows.length]);

  const showTouchTooltip = useCallback((clientX: number, clientY: number) => {
    const chartInstance = chartRef.current?.getEchartsInstance?.();
    if (!chartInstance) return;

    const dom = chartInstance.getDom();
    const rect = dom.getBoundingClientRect();
    const point = [clientX - rect.left, clientY - rect.top];
    const converted = chartInstance.convertFromPixel({ xAxisIndex: 0 }, point);
    const rawIndex = Array.isArray(converted) ? Number(converted[0]) : Number(converted);
    if (!Number.isFinite(rawIndex)) return;

    const dataIndex = clamp(Math.round(rawIndex), 0, Math.max(fusionRows.length - 1, 0));
    chartInstance.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex });
    chartInstance.dispatchAction({ type: 'updateAxisPointer', x: point[0], y: point[1] });
  }, [fusionRows.length]);

  useEffect(() => {
    if (!isTouchDevice || !chartContainerRef.current) return undefined;
    const element = chartContainerRef.current;

    const clearLongPress = () => {
      if (longPressTimerRef.current !== null) {
        window.clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = null;
      }
    };

    const hideTouchTooltip = () => {
      clearLongPress();
      if (touchActiveRef.current) {
        chartRef.current?.getEchartsInstance?.().dispatchAction({ type: 'hideTip' });
      }
      touchActiveRef.current = false;
      touchStartRef.current = null;
    };

    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 1) return;
      const touch = event.touches[0];
      touchStartRef.current = { x: touch.clientX, y: touch.clientY };
      clearLongPress();
      longPressTimerRef.current = window.setTimeout(() => {
        touchActiveRef.current = true;
        showTouchTooltip(touch.clientX, touch.clientY);
      }, 380);
    };

    const onTouchMove = (event: TouchEvent) => {
      if (event.touches.length !== 1) return;
      const touch = event.touches[0];
      const start = touchStartRef.current;
      if (!touchActiveRef.current && start) {
        const moved = Math.hypot(touch.clientX - start.x, touch.clientY - start.y);
        if (moved > 12) clearLongPress();
        return;
      }
      if (touchActiveRef.current) {
        event.preventDefault();
        showTouchTooltip(touch.clientX, touch.clientY);
      }
    };

    element.addEventListener('touchstart', onTouchStart, { passive: true });
    element.addEventListener('touchmove', onTouchMove, { passive: false });
    element.addEventListener('touchend', hideTouchTooltip, { passive: true });
    element.addEventListener('touchcancel', hideTouchTooltip, { passive: true });

    return () => {
      clearLongPress();
      element.removeEventListener('touchstart', onTouchStart);
      element.removeEventListener('touchmove', onTouchMove);
      element.removeEventListener('touchend', hideTouchTooltip);
      element.removeEventListener('touchcancel', hideTouchTooltip);
    };
  }, [isTouchDevice, showTouchTooltip]);

  const chartOption = useMemo(() => {
    if (!fusionRows.length) return {};

    const category = fusionRows.map((row) => row.label);
    const candleData = fusionRows.map((row) => (
      row.open !== null && row.high !== null && row.low !== null && row.close !== null
        ? [row.open, row.close, row.low, row.high]
        : ['-', '-', '-', '-']
    ));
    const closeLine = fusionRows.map((row) => row.close);
    const qualityMarks = fusionRows.map((row, index) => {
      if (!row.qualityInfo) return null;
      return row.close ?? fusionRows[index - 1]?.close ?? fusionRows[index + 1]?.close ?? null;
    });

    const absoluteData = buildPanelData(fusionRows, 'absolute');
    const netData = buildPanelData(fusionRows, 'net');
    const ratioData = buildPanelData(fusionRows, 'ratio');

    const amountAxisBound = (value: { max?: number; min?: number }) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      return maxAbs === 0 ? 1 : maxAbs * 1.08;
    };

    const percentAxisBound = (value: { max?: number; min?: number }) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      if (maxAbs === 0) return 5;
      const padded = Math.min(100, maxAbs * 1.15);
      return Math.max(5, Math.ceil(padded / 5) * 5);
    };

    const axisLabelFormatter = (_value: string, index: number) => formatAxisLabel(fusionRows, granularity, index);

    return {
      animation: false,
      backgroundColor: 'transparent',
      axisPointer: {
        link: [{ xAxisIndex: [0, 1, 2, 3] }],
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: isTouchDevice ? 'none' : 'mousemove|click',
        axisPointer: { type: 'cross', label: { backgroundColor: '#0F172A' } },
        backgroundColor: 'rgba(15, 23, 42, 0.98)',
        borderColor: '#334155',
        borderWidth: 1,
        padding: 12,
        textStyle: { color: '#E2E8F0', fontSize: 12 },
        extraCssText: 'box-shadow: 0 18px 40px rgba(2,6,23,0.52); border-radius: 14px; white-space: normal; max-width: 344px; pointer-events:none;',
        confine: true,
        appendToBody: false,
        position: (pos: number[], _params: any, _dom: HTMLElement, _rect: any, size: { viewSize: number[]; contentSize: number[] }) => getTooltipPosition(pos, size),
        formatter: (params: any) => {
          const items = Array.isArray(params) ? params : [params];
          if (!items.length) return '';
          const idx = Number(items[0]?.dataIndex ?? 0);
          const row = fusionRows[idx];
          if (!row) return '';
          return buildTooltipHtml(row);
        },
      },
      grid: [
        { left: '6%', right: '4%', top: 30, height: '21%' },
        { left: '6%', right: '4%', top: '31%', height: '22%' },
        { left: '6%', right: '4%', top: '58%', height: '13%' },
        { left: '6%', right: '4%', top: '76%', height: '13%' },
      ],
      xAxis: [
        {
          type: 'category',
          data: category,
          boundaryGap: true,
          axisLine: { lineStyle: { color: COLORS.border } },
          axisTick: { show: false },
          axisLabel: {
            show: true,
            color: '#64748B',
            fontSize: 10,
            interval: 0,
            formatter: axisLabelFormatter,
            hideOverlap: true,
            margin: 10,
          },
          min: 'dataMin',
          max: 'dataMax',
        },
        {
          type: 'category',
          gridIndex: 1,
          data: category,
          boundaryGap: true,
          axisLine: { lineStyle: { color: COLORS.border } },
          axisTick: { show: false },
          axisLabel: { show: false },
          min: 'dataMin',
          max: 'dataMax',
        },
        {
          type: 'category',
          gridIndex: 2,
          data: category,
          boundaryGap: true,
          axisLine: { lineStyle: { color: COLORS.border } },
          axisTick: { show: false },
          axisLabel: { show: false },
          min: 'dataMin',
          max: 'dataMax',
        },
        {
          type: 'category',
          gridIndex: 3,
          data: category,
          boundaryGap: true,
          axisLine: { lineStyle: { color: COLORS.border } },
          axisTick: { show: false },
          axisLabel: {
            color: '#64748B',
            fontSize: 10,
            interval: 0,
            formatter: axisLabelFormatter,
            hideOverlap: true,
          },
          min: 'dataMin',
          max: 'dataMax',
        },
      ],
      yAxis: [
        {
          type: 'value',
          scale: true,
          name: '价格',
          nameGap: 10,
          nameTextStyle: { color: COLORS.closeLine, fontSize: 11 },
          axisLabel: { color: COLORS.closeLine, fontSize: 10, formatter: (v: number) => v.toFixed(2) },
          splitLine: { lineStyle: { color: COLORS.border, type: 'dashed' } },
          axisLine: { show: true, lineStyle: { color: COLORS.border } },
        },
        {
          type: 'value',
          gridIndex: 1,
          scale: true,
          name: '资金绝对值',
          nameGap: 10,
          nameTextStyle: { color: '#CBD5E1', fontSize: 11 },
          min: (value: { max?: number; min?: number }) => -amountAxisBound(value),
          max: (value: { max?: number; min?: number }) => amountAxisBound(value),
          axisLabel: { color: '#CBD5E1', fontSize: 10, formatter: (v: number) => compactAmount(v) },
          splitLine: { lineStyle: { color: COLORS.border, type: 'dashed' } },
          axisLine: { show: true, lineStyle: { color: COLORS.zeroLine } },
        },
        {
          type: 'value',
          gridIndex: 2,
          scale: true,
          name: '净流入',
          nameGap: 10,
          nameTextStyle: { color: '#CBD5E1', fontSize: 11 },
          min: (value: { max?: number; min?: number }) => -amountAxisBound(value),
          max: (value: { max?: number; min?: number }) => amountAxisBound(value),
          axisLabel: { color: '#CBD5E1', fontSize: 10, formatter: (v: number) => compactAmount(v) },
          splitLine: { lineStyle: { color: COLORS.border, type: 'dashed' } },
          axisLine: { show: true, lineStyle: { color: COLORS.zeroLine } },
        },
        {
          type: 'value',
          gridIndex: 3,
          scale: true,
          name: '买卖力度',
          nameGap: 10,
          nameTextStyle: { color: '#CBD5E1', fontSize: 11 },
          min: (value: { max?: number; min?: number }) => -percentAxisBound(value),
          max: (value: { max?: number; min?: number }) => percentAxisBound(value),
          axisLabel: { color: '#CBD5E1', fontSize: 10, formatter: (v: number) => `${v.toFixed(0)}%` },
          splitLine: { lineStyle: { color: COLORS.border, type: 'dashed' } },
          axisLine: { show: true, lineStyle: { color: COLORS.zeroLine } },
        },
      ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1, 2, 3],
          filterMode: 'filter',
          zoomOnMouseWheel: 'ctrl',
          moveOnMouseWheel: 'shift',
          moveOnMouseMove: false,
          start: zoomWindow.start,
          end: zoomWindow.end,
        },
        {
          type: 'slider',
          xAxisIndex: [0, 1, 2, 3],
          bottom: 8,
          height: 18,
          showDetail: false,
          brushSelect: false,
          filterMode: 'filter',
          borderColor: '#334155',
          fillerColor: 'rgba(71, 85, 105, 0.22)',
          start: zoomWindow.start,
          end: zoomWindow.end,
        },
      ],
      series: [
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
          barMaxWidth: 16,
          z: 3,
        },
        {
          name: '收盘价',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: closeLine,
          showSymbol: false,
          lineStyle: { color: COLORS.closeLine, width: 1.2, opacity: 0.9 },
          itemStyle: { color: COLORS.closeLine },
          z: 4,
        },
        {
          name: '质量提示',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: qualityMarks,
          symbolSize: 16,
          itemStyle: { color: COLORS.quality },
          label: {
            show: true,
            formatter: '!',
            color: '#0F172A',
            fontSize: 10,
            fontWeight: 800,
            offset: [0, -1],
          },
          emphasis: { scale: false },
          z: 6,
        },
        createFlowCustomSeries('资金绝对值双柱', 'absolute', 1, 1, absoluteData, fusionRows.length),
        createFlowCustomSeries('净流入双柱', 'net', 2, 2, netData, fusionRows.length),
        createFlowCustomSeries('买卖力度双柱', 'ratio', 3, 3, ratioData, fusionRows.length),
      ],
    };
  }, [fusionRows, granularity, isTouchDevice, zoomWindow]);

  if (!activeStock) return null;

  return (
    <div className="space-y-4">
      {!backendStatus && (
        <div className="bg-red-950/30 border border-red-900/50 p-2 rounded-lg flex items-center gap-3 text-red-300 text-xs">
          <AlertCircle className="w-4 h-4" />
          <span>
            本地 Python 服务未连接 (端口 8000)。请在终端运行：
            <code className="bg-black/30 px-2 py-0.5 rounded ml-2 text-red-200 font-mono">python -m backend.app.main</code>
          </span>
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg">
        <div className="mb-3 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <h3 className="text-sm font-semibold tracking-wide text-white">波段复盘</h3>
            <span className="rounded-full border border-slate-700 bg-slate-950/70 px-2 py-1 text-[11px] text-cyan-200">{sourceLabel}</span>
            <InfoPopover>
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-100">图例说明</div>
                <div>左柱 = 超大单，右柱 = 主力；深色是 L2 底柱，浅色是 L1 芯柱。</div>
                <div>资金绝对值 / 净流入 / 买卖力度三张副图都共用同一视觉语言。</div>
                <div>黄色 <span className="font-bold text-amber-300">!</span> 表示该点存在 `quality_info`；若为当日未结算，则 tooltip 会额外提示 “当前仅 L1 实时口径”。</div>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.superL2Buy }} />超大 L2 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.superL1Buy }} />超大 L1 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.mainL2Buy }} />主力 L2 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.mainL1Buy }} />主力 L1 买</span>
                </div>
              </div>
            </InfoPopover>
            <span className={`rounded-full border px-2 py-1 text-[11px] ${issueCount > 0 ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200'}`}>
              {issueTagLabel}
            </span>
            <InfoPopover widthClass="w-[320px] sm:w-[380px]">
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-100">缺失 / 异常详情</div>
                {issueRows.length === 0 ? (
                  <div className="text-slate-300">当前窗口暂无 `quality_info`，历史点位视为正常可读。</div>
                ) : (
                  <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
                    {issueRows.slice(0, 16).map((row) => (
                      <div key={row.key} className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2">
                        <div className="font-medium text-amber-100">{row.datetime}</div>
                        <div className="mt-1 text-slate-300">{row.qualityInfo}</div>
                      </div>
                    ))}
                    {issueRows.length > 16 && (
                      <div className="text-slate-400">其余 {issueRows.length - 16} 条请缩放后在 tooltip 内查看。</div>
                    )}
                  </div>
                )}
              </div>
            </InfoPopover>
          </div>

          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <div className="flex flex-wrap items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/50 p-1">
              {GRANULARITY_BUTTONS.map((item) => (
                <button
                  key={item.value}
                  onClick={() => onGranularityChange(item.value)}
                  className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors ${granularity === item.value ? 'bg-violet-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'}`}
                  title={`切换到 ${LABELS[item.value]}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/50 p-1">
              <button
                onClick={() => handleZoomStep('out')}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
                title={`缩小查看更多（当前 ${ZOOM_PRESETS[granularity][inferNearestPresetIndex(granularity, fusionRows.length || 1, zoomWindow)]?.label || '默认'}）`}
              >
                <Minus className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleZoomStep('in')}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
                title={`放大查看细节（当前 ${ZOOM_PRESETS[granularity][inferNearestPresetIndex(granularity, fusionRows.length || 1, zoomWindow)]?.label || '默认'}）`}
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            <button
              onClick={() => setRefreshKey((prev) => prev + 1)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/50 text-slate-300 transition-colors hover:border-slate-600 hover:text-white"
              title="刷新历史多维数据"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-3 bg-red-900/20 border border-red-800 p-3 rounded-lg flex items-center gap-3 text-red-200 text-xs">
            <AlertCircle className="w-4 h-4" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="py-24 text-center text-blue-400 flex flex-col items-center">
            <RefreshCw className="w-8 h-8 animate-spin mb-4" />
            <p>正在加载{LABELS[granularity]}融合数据...</p>
          </div>
        ) : !fusionRows.length ? (
          <div className="min-h-[420px] flex flex-col items-center justify-center text-center bg-slate-950/30 rounded-lg border border-slate-800/50 px-6">
            <Database className="w-14 h-14 mb-4 text-slate-700" />
            <h4 className="text-slate-200 font-semibold mb-2">暂无可用正式 L2 {LABELS[granularity]}历史</h4>
            <p className="text-sm text-slate-500 max-w-xl leading-6">
              新版历史多维只消费正式 L2 历史底座，并在今天未结算时追加 L1 preview。
              当前股票若尚未完成盘后 L2 回补，请先切回旧版查看原有图表，或等待该股票对应交易日的正式 L2 数据入库。
            </p>
          </div>
        ) : (
          <div
            ref={chartContainerRef}
            className="w-full min-h-[980px] rounded-xl border border-slate-800/70 bg-slate-950/35 p-2"
          >
            <ReactEChartsCore
              ref={chartRef}
              echarts={echarts}
              option={chartOption}
              notMerge
              lazyUpdate
              onEvents={{ datazoom: handleDataZoom }}
              style={{ width: '100%', height: 960 }}
            />
            {isTouchDevice && (
              <div className="px-3 pb-1 pt-2 text-[11px] text-slate-500">
                手机端：单指可直接滚页面，长按图表约 0.4 秒后再左右拖动查看详细数据。
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default HistoryMultiframeFusionView;
