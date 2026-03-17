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

const ZOOM_POINT_PRESETS = [20, 40, 80, 160];
const DEFAULT_VISIBLE_POINTS = 40;
const MIN_VISIBLE_POINTS = 20;
const MAX_VISIBLE_POINTS = 160;

const COLORS = {
  mainL2Buy: '#D32F2F',
  mainL1Buy: '#EF9A9A',
  mainL2Sell: '#388E3C',
  mainL1Sell: '#81C784',
  superL2Buy: '#7B1FA2',
  superL1Buy: '#BA68C8',
  superL2Sell: '#00796B',
  superL1Sell: '#4DB6AC',
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
  const abs = Math.abs(value);
  return `${value.toFixed(abs >= 10 ? 1 : 2)}%`;
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
  const hasL2Super = row.l2SuperBuy !== null || row.l2SuperSell !== null;
  const hasL2Main = row.l2MainBuy !== null || row.l2MainSell !== null;

  if (kind === 'net') {
    return {
      value: [
        index,
        toNet(row.l2SuperBuy, row.l2SuperSell),
        toNet(row.l1SuperBuy, row.l1SuperSell),
        toNet(row.l2MainBuy, row.l2MainSell),
        toNet(row.l1MainBuy, row.l1MainSell),
        hasL2Super ? 1 : 0,
        hasL2Main ? 1 : 0,
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
        hasL2Super ? 1 : 0,
        hasL2Main ? 1 : 0,
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
      hasL2Super ? 1 : 0,
      hasL2Main ? 1 : 0,
    ],
  };
});

const getZoomBarLimits = (totalBars: number): { minBars: number; maxBars: number } => {
  if (totalBars <= 0) return { minBars: 1, maxBars: 1 };
  const maxBars = Math.min(totalBars, MAX_VISIBLE_POINTS);
  const minBars = Math.min(totalBars, MIN_VISIBLE_POINTS, maxBars);
  return { minBars: Math.max(1, minBars), maxBars: Math.max(1, maxBars) };
};

const getVisibleIndexRange = (rowCount: number, zoom: ZoomWindow): { startIndex: number; endIndex: number } => {
  if (rowCount <= 0) return { startIndex: 0, endIndex: 0 };
  const denominator = Math.max(1, rowCount - 1);
  const startIndex = clamp(Math.floor((zoom.start / 100) * denominator), 0, rowCount - 1);
  const endIndex = clamp(Math.ceil((zoom.end / 100) * denominator), startIndex, rowCount - 1);
  return { startIndex, endIndex };
};

const resolveDataIndexFromEvent = (event: any, rowCount: number): number | null => {
  const candidates = [
    event?.dataIndex,
    event?.batch?.[0]?.dataIndex,
    event?.seriesData?.[0]?.dataIndex,
    event?.axesInfo?.[0]?.dataIndex,
    event?.axesInfo?.[0]?.value,
  ];

  for (const candidate of candidates) {
    const next = Number(candidate);
    if (Number.isFinite(next) && next >= 0 && next < rowCount) {
      return next;
    }
  }
  return null;
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
        const hasL2Super = Number(api.value(5)) === 1;
        const hasL2Main = Number(api.value(6)) === 1;
        children.push(hasL2Super ? makeRect(superCenter, api.value(1), Number(api.value(1)) >= 0 ? COLORS.superL2Buy : COLORS.superL2Sell) : null);
        children.push(makeRect(superCenter, api.value(2), Number(api.value(2)) >= 0 ? COLORS.superL1Buy : COLORS.superL1Sell));
        children.push(hasL2Main ? makeRect(mainCenter, api.value(3), Number(api.value(3)) >= 0 ? COLORS.mainL2Buy : COLORS.mainL2Sell) : null);
        children.push(makeRect(mainCenter, api.value(4), Number(api.value(4)) >= 0 ? COLORS.mainL1Buy : COLORS.mainL1Sell));
      } else {
        const hasL2Super = Number(api.value(9)) === 1;
        const hasL2Main = Number(api.value(10)) === 1;
        children.push(hasL2Super ? makeRect(superCenter, api.value(1), COLORS.superL2Buy) : null);
        children.push(hasL2Super ? makeRect(superCenter, api.value(3), COLORS.superL2Sell) : null);
        children.push(makeRect(superCenter, api.value(2), COLORS.superL1Buy));
        children.push(makeRect(superCenter, api.value(4), COLORS.superL1Sell));
        children.push(hasL2Main ? makeRect(mainCenter, api.value(5), COLORS.mainL2Buy) : null);
        children.push(hasL2Main ? makeRect(mainCenter, api.value(7), COLORS.mainL2Sell) : null);
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
  const { minBars, maxBars } = getZoomBarLimits(totalBars);
  const safeVisible = clamp(visibleBars, minBars, maxBars);
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

const normalizeZoomWindowByBarLimits = (totalBars: number, start: number, end: number): ZoomWindow => {
  if (totalBars <= 0) return { start: 0, end: 100 };
  const { minBars, maxBars } = getZoomBarLimits(totalBars);
  const minRange = (minBars / totalBars) * 100;
  const maxRange = totalBars <= maxBars ? 100 : (maxBars / totalBars) * 100;
  let normalized = normalizeZoomWindow(start, end, minRange);
  const currentRange = normalized.end - normalized.start;
  if (currentRange > maxRange) {
    const center = (normalized.start + normalized.end) / 2;
    normalized = normalizeZoomWindow(center - maxRange / 2, center + maxRange / 2, minRange);
  }
  return normalized;
};

const getVisibleBarsForPreset = (presetIndex: number): number => {
  return ZOOM_POINT_PRESETS[presetIndex] ?? DEFAULT_VISIBLE_POINTS;
};

const inferNearestPresetIndex = (totalBars: number, zoomWindow: ZoomWindow): number => {
  if (totalBars <= 0) return 1;
  const visibleBars = totalBars * Math.max(0.01, (zoomWindow.end - zoomWindow.start) / 100);
  let bestIndex = 1;
  let bestDistance = Number.POSITIVE_INFINITY;
  ZOOM_POINT_PRESETS.forEach((presetBars, index) => {
    const distance = Math.abs(presetBars - visibleBars);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
};

const formatAxisLabel = (
  rows: FusionRow[],
  granularity: HistoryMultiframeGranularity,
  index: number,
  visibleRange: { startIndex: number; endIndex: number },
): string => {
  const row = rows[index];
  if (!row) return '';

  const { startIndex, endIndex } = visibleRange;
  if (index <= startIndex || index > endIndex) return '';

  const visibleCount = Math.max(1, endIndex - startIndex + 1);
  const desiredLabels = visibleCount <= 32 ? 4 : visibleCount <= 80 ? 5 : 6;
  const slots = Math.max(2, desiredLabels);
  const chosen = new Set<number>();
  for (let slot = 1; slot < slots; slot += 1) {
    const ratio = slot / (slots - 1);
    const nextIndex = Math.round(startIndex + (visibleCount - 1) * ratio);
    if (nextIndex > startIndex && nextIndex <= endIndex) {
      chosen.add(nextIndex);
    }
  }
  chosen.add(endIndex);
  if (!chosen.has(index)) return '';

  if (granularity === '1d') {
    return visibleCount > 90 ? row.tradeDate.slice(2, 7) : row.tradeDate.slice(5);
  }

  const time = row.datetime.slice(11, 16);
  if (visibleCount > 96) return row.tradeDate.slice(5);
  if (visibleCount > 48) return `${row.tradeDate.slice(5)}\n${time}`;
  return `${row.tradeDate.slice(5)}\n${time}`;
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

const InfoStripSection: React.FC<{
  title: string;
  accentClass: string;
  rows: Array<{ label: string; value: React.ReactNode }>;
}> = ({ title, accentClass, rows }) => (
  <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 px-3 py-2.5">
    <div className={`mb-2 text-[10px] font-semibold tracking-wide ${accentClass}`}>{title}</div>
    <div className="space-y-1.5">
      {rows.map((row) => (
        <div key={row.label} className="grid grid-cols-[84px_minmax(0,1fr)] items-start gap-2 text-[11px] leading-5">
          <span className="whitespace-nowrap text-slate-500">{row.label}</span>
          <span className="min-w-0 whitespace-nowrap text-right font-mono text-slate-100">{row.value}</span>
        </div>
      ))}
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
  const [activeDataIndex, setActiveDataIndex] = useState<number | null>(null);

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
  const visibleIndexRange = useMemo(
    () => getVisibleIndexRange(fusionRows.length, zoomWindow),
    [fusionRows.length, zoomWindow],
  );
  const defaultVisibleIndex = visibleIndexRange.endIndex;
  const selectedDataIndex = useMemo(() => {
    if (!fusionRows.length) return null;
    if (activeDataIndex !== null && activeDataIndex >= 0 && activeDataIndex < fusionRows.length) {
      return activeDataIndex;
    }
    return defaultVisibleIndex;
  }, [activeDataIndex, defaultVisibleIndex, fusionRows.length]);
  const selectedRow = selectedDataIndex === null ? null : fusionRows[selectedDataIndex] ?? null;
  const selectedPeriodChangePct = useMemo(() => {
    if (!selectedRow || selectedRow.open === null || selectedRow.close === null || selectedRow.open === 0) return null;
    return ((selectedRow.close - selectedRow.open) / selectedRow.open) * 100;
  }, [selectedRow]);

  const hasFormalL2History = fusionRows.some(
    (row) => row.isFinalized && !row.isPlaceholder && [row.l2MainBuy, row.l2MainSell, row.l2SuperBuy, row.l2SuperSell].some((item) => item !== null),
  );
  const hasPreviewRows = fusionRows.some((row) => row.isPreviewOnly);
  const issueCount = issueRows.length;

  useEffect(() => {
    if (!fusionRows.length) {
      setZoomWindow({ start: 0, end: 100 });
      setActiveDataIndex(null);
      return;
    }
    const defaultVisibleBars = DEFAULT_VISIBLE_POINTS;
    setZoomWindow(buildZoomWindowFromVisibleBars(fusionRows.length, defaultVisibleBars));
    setActiveDataIndex(null);
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
    const currentIndex = inferNearestPresetIndex(totalBars, zoomWindow);
    const nextIndex = clamp(
      currentIndex + (direction === 'in' ? -1 : 1),
      0,
      ZOOM_POINT_PRESETS.length - 1,
    );
    const visibleBars = getVisibleBarsForPreset(nextIndex);
    setZoomWindow(buildZoomWindowFromVisibleBars(totalBars, visibleBars));
  }, [fusionRows.length, zoomWindow]);

  const handleDataZoom = useCallback((event: any) => {
    const payload = Array.isArray(event?.batch) && event.batch.length ? event.batch[event.batch.length - 1] : event;
    const start = Number(payload?.start);
    const end = Number(payload?.end);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    setZoomWindow(normalizeZoomWindowByBarLimits(fusionRows.length, start, end));
  }, [fusionRows.length]);

  const handleActivePointer = useCallback((event: any) => {
    const nextIndex = resolveDataIndexFromEvent(event, fusionRows.length);
    if (nextIndex !== null) {
      setActiveDataIndex(nextIndex);
    }
  }, [fusionRows.length]);

  const handlePointerLeave = useCallback(() => {
    setActiveDataIndex(null);
  }, []);

  useEffect(() => {
    if (!chartContainerRef.current) return undefined;
    const element = chartContainerRef.current;
    const handleWheel = (event: WheelEvent) => {
      const isZoomGesture = event.ctrlKey || event.metaKey;
      const isPanGesture = event.shiftKey;
      if (!isZoomGesture && !isPanGesture) return;

      event.preventDefault();
      setZoomWindow((prev) => {
        const totalBars = fusionRows.length;
        const { minBars, maxBars } = getZoomBarLimits(totalBars);
        const minRange = totalBars > 0 ? Math.max((minBars / totalBars) * 100, 0.6) : 0.6;
        const maxRange = totalBars > 0 ? Math.min(100, (maxBars / totalBars) * 100) : 100;
        const currentRange = clamp(Math.max(prev.end - prev.start, minRange), minRange, maxRange);

        if (isPanGesture) {
          const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
          const shift = (delta > 0 ? 1 : -1) * Math.max(currentRange * 0.12, 1.5);
          return normalizeZoomWindowByBarLimits(totalBars, prev.start + shift, prev.end + shift);
        }

        const nextRange = clamp(currentRange * (event.deltaY > 0 ? 1.16 : 0.86), minRange, maxRange);
        const center = (prev.start + prev.end) / 2;
        return normalizeZoomWindowByBarLimits(totalBars, center - nextRange / 2, center + nextRange / 2);
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
    setActiveDataIndex(dataIndex);
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
      setActiveDataIndex(null);
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

    const category = fusionRows.map((row) => row.datetime);
    const candleData = fusionRows.map((row) => (
      row.open !== null && row.high !== null && row.low !== null && row.close !== null
        ? [row.open, row.close, row.low, row.high]
        : ['-', '-', '-', '-']
    ));
    const closeLine = fusionRows.map((row) => row.close);
    const superL2ActivityLine = fusionRows.map((row) => {
      const buy = row.l2SuperBuy;
      const sell = row.l2SuperSell;
      if (buy === null || sell === null) return null;
      return toRatio(buy + sell, row.totalAmount);
    });
    const superL1ActivityLine = fusionRows.map((row) => {
      const buy = row.l1SuperBuy;
      const sell = row.l1SuperSell;
      if (buy === null || sell === null) return null;
      return toRatio(buy + sell, row.totalAmount);
    });
    const mainL2ActivityLine = fusionRows.map((row) => {
      const buy = row.l2MainBuy;
      const sell = row.l2MainSell;
      if (buy === null || sell === null) return null;
      return toRatio(buy + sell, row.totalAmount);
    });
    const mainL1ActivityLine = fusionRows.map((row) => {
      const buy = row.l1MainBuy;
      const sell = row.l1MainSell;
      if (buy === null || sell === null) return null;
      return toRatio(buy + sell, row.totalAmount);
    });
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

    const axisLabelFormatter = (_value: string, index: number) => formatAxisLabel(fusionRows, granularity, index, visibleIndexRange);
    const makeYAxis = (
      gridIndex: number,
      formatter: (value: number) => string,
      options: {
        min?: ((value: { max?: number; min?: number }) => number) | undefined;
        max?: ((value: { max?: number; min?: number }) => number) | undefined;
      } = {},
    ) => ({
      type: 'value',
      gridIndex,
      scale: true,
      position: 'left' as const,
      splitNumber: 2,
      min: options.min,
      max: options.max,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        inside: true,
        align: 'left' as const,
        margin: 8,
        padding: [0, 0, 0, 6],
        color: 'rgba(148, 163, 184, 0.58)',
        fontSize: 10,
        showMinLabel: true,
        showMaxLabel: true,
        formatter,
      },
      splitLine: { lineStyle: { color: 'rgba(30, 41, 59, 0.72)', type: 'dashed' } },
    });

    return {
      animation: false,
      backgroundColor: 'transparent',
      graphic: [
        { type: 'text', left: '6.2%', top: '1.6%', silent: true, style: { text: '价格K线', fill: 'rgba(251,191,36,0.88)', fontSize: 11, fontWeight: 500 } },
        { type: 'text', left: '6.2%', top: '40.6%', silent: true, style: { text: '资金绝对值', fill: 'rgba(226,232,240,0.78)', fontSize: 11, fontWeight: 500 } },
        { type: 'text', left: '6.2%', top: '59.6%', silent: true, style: { text: '净流入', fill: 'rgba(226,232,240,0.78)', fontSize: 11, fontWeight: 500 } },
        { type: 'text', left: '6.2%', top: '78.6%', silent: true, style: { text: '买卖力度', fill: 'rgba(226,232,240,0.78)', fontSize: 11, fontWeight: 500 } },
      ],
      axisPointer: {
        link: [{ xAxisIndex: [0, 1, 2, 3] }],
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: isTouchDevice ? 'none' : 'mousemove|click',
        axisPointer: { type: 'cross', label: { backgroundColor: '#0F172A' } },
        showContent: false,
        backgroundColor: 'transparent',
        borderWidth: 0,
        padding: 0,
        formatter: () => '',
      },
      grid: [
        { left: '4.5%', right: '2.2%', top: '4%', height: '36%' },
        { left: '4.5%', right: '2.2%', top: '43%', height: '16%' },
        { left: '4.5%', right: '2.2%', top: '62%', height: '16%' },
        { left: '4.5%', right: '2.2%', top: '81%', height: '12.5%' },
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
            margin: 8,
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
          axisLabel: { show: false },
          min: 'dataMin',
          max: 'dataMax',
        },
      ],
      yAxis: [
        makeYAxis(0, (v: number) => v.toFixed(2)),
        makeYAxis(1, (v: number) => compactAmount(v), {
          min: (value: { max?: number; min?: number }) => -amountAxisBound(value),
          max: (value: { max?: number; min?: number }) => amountAxisBound(value),
        }),
        makeYAxis(2, (v: number) => compactAmount(v), {
          min: (value: { max?: number; min?: number }) => -amountAxisBound(value),
          max: (value: { max?: number; min?: number }) => amountAxisBound(value),
        }),
        makeYAxis(3, (v: number) => `${v.toFixed(0)}%`, {
          min: (value: { max?: number; min?: number }) => -percentAxisBound(value),
          max: (value: { max?: number; min?: number }) => percentAxisBound(value),
        }),
        {
          type: 'value',
          gridIndex: 3,
          min: 0,
          max: 120,
          show: false,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1, 2, 3],
          filterMode: 'filter',
          zoomOnMouseWheel: false,
          moveOnMouseWheel: false,
          moveOnMouseMove: false,
          preventDefaultMouseMove: false,
          start: zoomWindow.start,
          end: zoomWindow.end,
        },
        {
          type: 'slider',
          xAxisIndex: [0, 1, 2, 3],
          bottom: 2,
          height: 14,
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
        {
          name: 'L2超大单活跃度',
          type: 'line',
          xAxisIndex: 3,
          yAxisIndex: 4,
          data: superL2ActivityLine,
          showSymbol: false,
          smooth: 0.25,
          connectNulls: false,
          lineStyle: {
            color: COLORS.superL2Buy,
            width: 1.2,
            opacity: 0.95,
          },
          itemStyle: { color: COLORS.superL2Buy },
          z: 7,
        },
        {
          name: 'L2主力活跃度',
          type: 'line',
          xAxisIndex: 3,
          yAxisIndex: 4,
          data: mainL2ActivityLine,
          showSymbol: false,
          smooth: 0.25,
          connectNulls: false,
          lineStyle: {
            color: COLORS.mainL2Buy,
            width: 1.2,
            opacity: 0.95,
          },
          itemStyle: { color: COLORS.mainL2Buy },
          z: 7,
        },
        {
          name: 'L1超大单活跃度',
          type: 'line',
          xAxisIndex: 3,
          yAxisIndex: 4,
          data: superL1ActivityLine,
          showSymbol: false,
          smooth: 0.25,
          connectNulls: false,
          lineStyle: {
            color: COLORS.mainL2Sell,
            width: 1.2,
            opacity: 0.92,
          },
          itemStyle: { color: COLORS.mainL2Sell },
          z: 7,
        },
        {
          name: 'L1主力活跃度',
          type: 'line',
          xAxisIndex: 3,
          yAxisIndex: 4,
          data: mainL1ActivityLine,
          showSymbol: false,
          smooth: 0.25,
          connectNulls: false,
          lineStyle: {
            color: COLORS.mainL1Sell,
            width: 1.2,
            opacity: 0.92,
          },
          itemStyle: { color: COLORS.mainL1Sell },
          z: 7,
        },
      ],
    };
  }, [fusionRows, granularity, isTouchDevice, visibleIndexRange, zoomWindow]);

  const selectedStatusBadges = useMemo(() => {
    if (!selectedRow) return [];
    return [
      selectedRow.isPreviewOnly ? '未结算' : null,
      selectedRow.isPlaceholder ? '缺失占位' : null,
      selectedRow.fallbackUsed ? 'fallback' : null,
      selectedRow.isFinalized ? 'finalized' : 'preview',
    ].filter(Boolean) as string[];
  }, [selectedRow]);

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
                <div>第四图中的细线表示买卖总额占总成交额比例：紫线 = L2 超大单，红线 = L2 主力，深绿线 = L1 超大单，浅绿线 = L1 主力。</div>
                <div>黄色 <span className="font-bold text-amber-300">!</span> 表示该点存在 `quality_info`；若为当日未结算，则外置读数条会提示 “当前仅 L1 实时口径”。</div>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.superL2Buy }} />超大 L2 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.superL1Buy }} />超大 L1 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.mainL2Buy }} />主力 L2 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.mainL1Buy }} />主力 L1 买</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-[2px] w-4 rounded-full" style={{ backgroundColor: COLORS.superL2Buy }} />L2 超大占比线</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-[2px] w-4 rounded-full" style={{ backgroundColor: COLORS.mainL2Buy }} />L2 主力占比线</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-[2px] w-4 rounded-full" style={{ backgroundColor: COLORS.mainL2Sell }} />L1 超大占比线</span>
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-2 py-1"><span className="h-[2px] w-4 rounded-full" style={{ backgroundColor: COLORS.mainL1Sell }} />L1 主力占比线</span>
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
                      <div className="text-slate-400">其余 {issueRows.length - 16} 条请缩放后在外置读数条里查看。</div>
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
                title={`缩小查看更多（当前约 ${getVisibleBarsForPreset(inferNearestPresetIndex(fusionRows.length || 1, zoomWindow))} 点）`}
              >
                <Minus className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleZoomStep('in')}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
                title={`放大查看细节（当前约 ${getVisibleBarsForPreset(inferNearestPresetIndex(fusionRows.length || 1, zoomWindow))} 点）`}
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
            className="w-full rounded-xl border border-slate-800/70 bg-slate-950/35 p-2"
          >
            {selectedRow && (
              <div className="mb-2 grid gap-2 rounded-xl border border-slate-800/80 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-200 lg:grid-cols-[minmax(220px,1.05fr)_minmax(190px,0.95fr)_minmax(250px,1fr)_minmax(250px,1fr)]">
                <div className="min-w-0 rounded-lg border border-slate-800/80 bg-slate-950/55 px-3 py-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-semibold text-white">{selectedRow.datetime}</span>
                    <span className="rounded-full border border-slate-700 bg-slate-900/80 px-2 py-0.5 text-[10px] text-cyan-200">{selectedRow.source}</span>
                    {selectedStatusBadges.map((badge) => (
                      <span
                        key={badge}
                        className={`rounded-full border px-2 py-0.5 text-[10px] ${
                          badge === '未结算'
                            ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                            : badge === '缺失占位'
                              ? 'border-sky-500/30 bg-sky-500/10 text-sky-200'
                              : 'border-slate-700 bg-slate-900/80 text-slate-300'
                        }`}
                      >
                        {badge}
                      </span>
                    ))}
                  </div>
                  <div className="mt-1 whitespace-nowrap text-[10px] text-slate-500">
                    当前窗口 {visibleIndexRange.startIndex + 1}-{visibleIndexRange.endIndex + 1} / {fusionRows.length} 点，默认显示窗口最后一点
                  </div>
                  {selectedRow.qualityInfo && (
                    <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] leading-5 text-amber-100">
                      质量提示：{selectedRow.qualityInfo}
                    </div>
                  )}
                </div>

                <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 px-3 py-2.5">
                  <div className="mb-2 text-[10px] font-semibold tracking-wide text-amber-200">价格 / 元数据</div>
                  <div className="space-y-1.5 text-[11px] leading-5">
                    <div className="grid grid-cols-2 gap-x-4">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="whitespace-nowrap text-slate-500">开盘价</span>
                        <span className="whitespace-nowrap text-right font-mono text-slate-100">{formatPrice(selectedRow.open)}</span>
                      </div>
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="whitespace-nowrap text-slate-500">最高价</span>
                        <span className="whitespace-nowrap text-right font-mono text-red-300">{formatPrice(selectedRow.high)}</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="whitespace-nowrap text-slate-500">最低价</span>
                        <span className="whitespace-nowrap text-right font-mono text-emerald-300">{formatPrice(selectedRow.low)}</span>
                      </div>
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="whitespace-nowrap text-slate-500">收盘价</span>
                        <span className="whitespace-nowrap text-right font-mono text-amber-200">{formatPrice(selectedRow.close)}</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="whitespace-nowrap text-slate-500">成交额</span>
                        <span className="whitespace-nowrap text-right font-mono text-slate-100">{compactAmount(selectedRow.totalAmount)}</span>
                      </div>
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="whitespace-nowrap text-slate-500">涨跌</span>
                        <span
                          className={`whitespace-nowrap text-right font-mono ${
                            (selectedPeriodChangePct ?? 0) > 0
                              ? 'text-red-300'
                              : (selectedPeriodChangePct ?? 0) < 0
                                ? 'text-emerald-300'
                                : 'text-slate-100'
                          }`}
                        >
                          {selectedPeriodChangePct === null ? '--' : `${selectedPeriodChangePct > 0 ? '+' : ''}${compactPercent(selectedPeriodChangePct)}`}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <InfoStripSection
                  title="主力（右柱）"
                  accentClass="text-rose-200"
                  rows={[
                    { label: '买入 L2 / L1', value: `${compactAmount(selectedRow.l2MainBuy)} / ${compactAmount(selectedRow.l1MainBuy)}` },
                    { label: '卖出 L2 / L1', value: `${compactAmount(selectedRow.l2MainSell)} / ${compactAmount(selectedRow.l1MainSell)}` },
                    { label: '净流入 L2 / L1', value: `${compactAmount(toNet(selectedRow.l2MainBuy, selectedRow.l2MainSell))} / ${compactAmount(toNet(selectedRow.l1MainBuy, selectedRow.l1MainSell))}` },
                  ]}
                />

                <InfoStripSection
                  title="超大单（左柱）"
                  accentClass="text-violet-200"
                  rows={[
                    { label: '买入 L2 / L1', value: `${compactAmount(selectedRow.l2SuperBuy)} / ${compactAmount(selectedRow.l1SuperBuy)}` },
                    { label: '卖出 L2 / L1', value: `${compactAmount(selectedRow.l2SuperSell)} / ${compactAmount(selectedRow.l1SuperSell)}` },
                    { label: '净流入 L2 / L1', value: `${compactAmount(toNet(selectedRow.l2SuperBuy, selectedRow.l2SuperSell))} / ${compactAmount(toNet(selectedRow.l1SuperBuy, selectedRow.l1SuperSell))}` },
                  ]}
                />
              </div>
            )}
            <ReactEChartsCore
              ref={chartRef}
              echarts={echarts}
              option={chartOption}
              notMerge
              lazyUpdate
              onEvents={{
                datazoom: handleDataZoom,
                showTip: handleActivePointer,
                updateAxisPointer: handleActivePointer,
                globalout: handlePointerLeave,
              }}
              style={{ width: '100%', height: '76vh', minHeight: 560, maxHeight: 820 }}
            />
            {isTouchDevice && (
              <div className="px-3 pb-1 pt-2 text-[11px] text-slate-500">
                手机端：单指上下滑动优先滚页面；长按图表约 0.4 秒后，再左右拖动查看十字线与顶部读数。
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default HistoryMultiframeFusionView;
