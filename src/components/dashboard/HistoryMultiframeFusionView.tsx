import React, { useEffect, useMemo, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { CandlestickChart, CustomChart, LineChart, ScatterChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { AlertCircle, Database, RefreshCw } from 'lucide-react';

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
  granularity: '5m' | '30m' | '1h' | '1d';
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

const LOOKBACK_DAYS: Record<'5m' | '30m' | '1h' | '1d', number> = {
  '5m': 10,
  '30m': 20,
  '1h': 40,
  '1d': 240,
};

const LABELS: Record<'5m' | '30m' | '1h' | '1d', string> = {
  '5m': '5分钟',
  '30m': '30分钟',
  '1h': '1小时',
  '1d': '日线',
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

const formatQualityShort = (value: string | null): string => {
  if (!value) return '';
  return value.length > 24 ? `${value.slice(0, 24)}…` : value;
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

  let left = x + 16;
  if (left + contentWidth > viewWidth - 12) {
    left = x - contentWidth - 16;
  }
  left = clamp(left, 12, Math.max(12, viewWidth - contentWidth - 12));

  let top = y - contentHeight / 2;
  if (top + contentHeight > viewHeight - 12) {
    top = viewHeight - contentHeight - 12;
  }
  top = clamp(top, 12, Math.max(12, viewHeight - contentHeight - 12));

  return [left, top];
};

const buildTooltipHtml = (row: FusionRow): string => {
  const renderValueRow = (label: string, l2Value: number | null, l1Value: number | null, colors: [string, string], formatter: (v: number | null) => string) => `
    <div style="display:grid;grid-template-columns:58px minmax(0,1fr) minmax(0,1fr);align-items:start;gap:8px;line-height:1.45;">
      <span style="color:#94A3B8;">${label}</span>
      <span style="display:inline-flex;align-items:flex-start;gap:4px;color:#E2E8F0;min-width:0;white-space:normal;word-break:break-word;">
        <span style="display:inline-block;width:8px;height:8px;background:${colors[0]};border-radius:2px;flex:0 0 auto;margin-top:4px;"></span>
        <span><span style="color:#94A3B8;">L2</span> ${formatter(l2Value)}</span>
      </span>
      <span style="display:inline-flex;align-items:flex-start;gap:4px;color:#E2E8F0;min-width:0;white-space:normal;word-break:break-word;">
        <span style="display:inline-block;width:8px;height:8px;background:${colors[1]};border-radius:2px;flex:0 0 auto;margin-top:4px;"></span>
        <span><span style="color:#94A3B8;">L1</span> ${formatter(l1Value)}</span>
      </span>
    </div>
  `;

  const statusBadges = [
    row.isPreviewOnly ? '<span style="padding:2px 6px;border-radius:999px;background:rgba(245,158,11,.14);border:1px solid rgba(245,158,11,.25);color:#FCD34D;">未结算</span>' : '',
    row.isPlaceholder ? '<span style="padding:2px 6px;border-radius:999px;background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.2);color:#BFDBFE;">缺失占位</span>' : '',
    row.fallbackUsed ? '<span style="padding:2px 6px;border-radius:999px;background:rgba(148,163,184,.12);border:1px solid rgba(148,163,184,.2);color:#CBD5E1;">fallback</span>' : '',
  ].filter(Boolean).join('');

  const notices = [
    row.isPreviewOnly ? '当前仅 L1 实时口径，L2 待盘后覆盖。' : '',
    row.qualityInfo ? `质量提示：${row.qualityInfo}` : '',
  ].filter(Boolean);

  return `
    <div style="width:348px;max-width:348px;color:#E2E8F0;white-space:normal;word-break:break-word;">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px;">
        <div>
          <div style="font-size:15px;font-weight:700;color:#F8FAFC;">${row.datetime}</div>
          <div style="margin-top:4px;font-size:12px;color:#94A3B8;">来源 ${row.source} ｜ finalized ${row.isFinalized ? 'true' : 'false'}</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;">${statusBadges}</div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div style="padding:10px 12px;border-radius:10px;background:rgba(15,23,42,.68);border:1px solid rgba(51,65,85,.85);">
          <div style="font-size:11px;color:#94A3B8;margin-bottom:6px;letter-spacing:.02em;">价格 / 元数据</div>
          <div style="font-size:12px;line-height:1.6;color:#E2E8F0;">O ${formatPrice(row.open)} / H ${formatPrice(row.high)} / L ${formatPrice(row.low)} / C ${formatPrice(row.close)}</div>
          <div style="font-size:12px;line-height:1.6;color:#E2E8F0;">成交额 ${compactAmount(row.totalAmount)}</div>
          <div style="font-size:12px;line-height:1.6;color:#E2E8F0;">日期 ${row.tradeDate}</div>
        </div>
        <div style="padding:10px 12px;border-radius:10px;background:rgba(15,23,42,.68);border:1px solid rgba(51,65,85,.85);">
          <div style="font-size:11px;color:#94A3B8;margin-bottom:6px;letter-spacing:.02em;">图例速读</div>
          <div style="font-size:12px;line-height:1.65;color:#E2E8F0;">左柱=超大单，右柱=主力</div>
          <div style="font-size:12px;line-height:1.65;color:#E2E8F0;">深色=L2 底柱，浅色=L1 芯柱</div>
          <div style="font-size:12px;line-height:1.65;color:#E2E8F0;">上=买入/净流入，下=卖出/净流出</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div style="padding:10px;border-radius:10px;background:rgba(76,29,149,.12);border:1px solid rgba(139,92,246,.24);">
          <div style="font-size:12px;font-weight:700;color:#E9D5FF;margin-bottom:8px;">超大单（左柱）</div>
          ${renderValueRow('买入', row.l2SuperBuy, row.l1SuperBuy, [COLORS.superL2Buy, COLORS.superL1Buy], compactAmount)}
          ${renderValueRow('卖出', row.l2SuperSell, row.l1SuperSell, [COLORS.superL2Sell, COLORS.superL1Sell], compactAmount)}
          ${renderValueRow('净流入', toNet(row.l2SuperBuy, row.l2SuperSell), toNet(row.l1SuperBuy, row.l1SuperSell), [COLORS.superL2Buy, COLORS.superL1Buy], compactAmount)}
          ${renderValueRow('买入力度', toRatio(row.l2SuperBuy, row.totalAmount), toRatio(row.l1SuperBuy, row.totalAmount), [COLORS.superL2Buy, COLORS.superL1Buy], compactPercent)}
          ${renderValueRow('卖出力度', toRatio(row.l2SuperSell, row.totalAmount), toRatio(row.l1SuperSell, row.totalAmount), [COLORS.superL2Sell, COLORS.superL1Sell], compactPercent)}
        </div>
        <div style="padding:10px;border-radius:10px;background:rgba(127,29,29,.12);border:1px solid rgba(248,113,113,.24);">
          <div style="font-size:12px;font-weight:700;color:#FECACA;margin-bottom:8px;">主力（右柱）</div>
          ${renderValueRow('买入', row.l2MainBuy, row.l1MainBuy, [COLORS.mainL2Buy, COLORS.mainL1Buy], compactAmount)}
          ${renderValueRow('卖出', row.l2MainSell, row.l1MainSell, [COLORS.mainL2Sell, COLORS.mainL1Sell], compactAmount)}
          ${renderValueRow('净流入', toNet(row.l2MainBuy, row.l2MainSell), toNet(row.l1MainBuy, row.l1MainSell), [COLORS.mainL2Buy, COLORS.mainL1Buy], compactAmount)}
          ${renderValueRow('买入力度', toRatio(row.l2MainBuy, row.totalAmount), toRatio(row.l1MainBuy, row.totalAmount), [COLORS.mainL2Buy, COLORS.mainL1Buy], compactPercent)}
          ${renderValueRow('卖出力度', toRatio(row.l2MainSell, row.totalAmount), toRatio(row.l1MainSell, row.totalAmount), [COLORS.mainL2Sell, COLORS.mainL1Sell], compactPercent)}
        </div>
      </div>

      ${notices.length ? `<div style="margin-top:12px;padding:10px 12px;border-radius:10px;background:rgba(250,204,21,.08);border:1px solid rgba(250,204,21,.18);font-size:12px;line-height:1.65;color:#FDE68A;">${notices.join('<br/>')}</div>` : ''}
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

const HistoryMultiframeFusionView: React.FC<HistoryMultiframeFusionViewProps> = ({
  activeStock,
  backendStatus,
  granularity,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [rows, setRows] = useState<HistoryMultiframeItem[]>([]);

  useEffect(() => {
    let isMounted = true;
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
        if (!isMounted) return;
        setRows(data);
      } catch (e: any) {
        if (!isMounted) return;
        setError(e?.message || '获取历史多维数据失败');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    load();
    return () => {
      isMounted = false;
    };
  }, [activeStock, granularity, refreshKey]);

  const fusionRows = useMemo(() => buildRows(rows, granularity), [rows, granularity]);
  const hasFormalL2History = fusionRows.some(
    (row) => row.isFinalized && !row.isPlaceholder && [row.l2MainBuy, row.l2MainSell, row.l2SuperBuy, row.l2SuperSell].some((item) => item !== null),
  );
  const hasPreviewRows = fusionRows.some((row) => row.isPreviewOnly);
  const issueCount = fusionRows.filter((row) => !!row.qualityInfo).length;

  const sourceLabel = useMemo(() => {
    if (hasFormalL2History && hasPreviewRows) return 'Source: 正式L2历史 + 今日L1预览';
    if (hasFormalL2History) return 'Source: 正式L2历史';
    if (hasPreviewRows) return 'Source: 今日L1预览';
    if (fusionRows.length) return 'Source: 仅异常占位 / 待补正式L2';
    return 'Source: 暂无可用正式L2历史';
  }, [fusionRows.length, hasFormalL2History, hasPreviewRows]);

  const customLegend = [
    { label: '超大 L2 买', color: COLORS.superL2Buy },
    { label: '超大 L1 买', color: COLORS.superL1Buy },
    { label: '超大 L2 卖', color: COLORS.superL2Sell },
    { label: '超大 L1 卖', color: COLORS.superL1Sell },
    { label: '主力 L2 买', color: COLORS.mainL2Buy },
    { label: '主力 L1 买', color: COLORS.mainL1Buy },
    { label: '主力 L2 卖', color: COLORS.mainL2Sell },
    { label: '主力 L1 卖', color: COLORS.mainL1Sell },
  ];

  const chartOption = useMemo(() => {
    if (!fusionRows.length) return {};

    const category = fusionRows.map((row) => row.label);
    const candleData = fusionRows.map((row) => (
      row.open !== null && row.high !== null && row.low !== null && row.close !== null
        ? [row.open, row.close, row.low, row.high]
        : ['-', '-', '-', '-']
    ));
    const closeLine = fusionRows.map((row) => row.close);
    const qualityMarks = fusionRows.map((row) => (row.qualityInfo ? row.close : null));

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

    return {
      animation: false,
      backgroundColor: 'transparent',
      axisPointer: {
        link: [{ xAxisIndex: [0, 1, 2, 3] }],
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { backgroundColor: '#0F172A' } },
        backgroundColor: 'rgba(15, 23, 42, 0.98)',
        borderColor: '#334155',
        borderWidth: 1,
        padding: 12,
        textStyle: { color: '#E2E8F0', fontSize: 12 },
        extraCssText: 'box-shadow: 0 18px 40px rgba(2,6,23,0.52); border-radius: 14px; white-space: normal; max-width: 360px;',
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
        { left: '6%', right: '4%', top: 24, height: '23%' },
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
          axisLabel: { show: false },
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
            interval: granularity === '5m' ? 'auto' : 0,
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
          zoomOnMouseWheel: true,
          moveOnMouseMove: true,
          moveOnMouseWheel: true,
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
          start: Math.max(0, 100 - Math.min(100, Math.round((60 / Math.max(fusionRows.length, 1)) * 100))),
          end: 100,
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
  }, [fusionRows, granularity]);

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
        <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold text-white">历史多维融合版</h3>
              <span className="text-[10px] font-normal text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
                {LABELS[granularity]}
              </span>
              <span className="text-[10px] font-normal text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
                {sourceLabel}
              </span>
              {hasPreviewRows && (
                <span className="text-[10px] font-medium text-amber-200 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded">
                  今日未结算：仅展示 L1 芯柱
                </span>
              )}
              {issueCount > 0 && (
                <span className="text-[10px] font-medium text-amber-200 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded">
                  质量提示 {issueCount} 个
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              上方价格区，下方三层都按“左超大 / 右主力”双柱展开：深色 L2 做底，浅色 L1 做芯；黄色 ! 表示该点存在质量提示。
            </p>
          </div>

          <button
            onClick={() => setRefreshKey((prev) => prev + 1)}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-slate-700 text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
            title="刷新历史多维数据"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            刷新
          </button>
        </div>

        <div className="mb-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2">
            <span className="text-[11px] font-medium text-slate-300 mr-1">图例</span>
            {customLegend.map((item) => (
              <span
                key={item.label}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-700/80 bg-slate-900/70 px-2 py-1 text-[11px] text-slate-300"
              >
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-start gap-2 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2 text-[11px] text-slate-400 lg:justify-end">
            <span className="rounded-full border border-slate-700/80 px-2 py-1">左柱 = 超大单</span>
            <span className="rounded-full border border-slate-700/80 px-2 py-1">右柱 = 主力</span>
            <span className="rounded-full border border-slate-700/80 px-2 py-1">Hover 同步联动</span>
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/20 px-2 py-1 text-amber-200">
              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-[10px] font-black text-slate-950">!</span>
              {issueCount > 0 ? `${issueCount} 个异常点` : '暂无异常点'}
            </span>
          </div>
        </div>

        {issueCount > 0 && (
          <div className="mb-3 flex flex-wrap gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-100">
            {fusionRows.filter((row) => !!row.qualityInfo).slice(0, 8).map((row) => (
              <span key={row.key} className="rounded-full border border-amber-500/20 bg-slate-950/40 px-2 py-1">
                {row.label.replace('\n', ' ')} · {formatQualityShort(row.qualityInfo)}
              </span>
            ))}
            {issueCount > 8 && <span className="rounded-full border border-amber-500/20 bg-slate-950/40 px-2 py-1">其余 {issueCount - 8} 个请在图上 hover 查看</span>}
          </div>
        )}

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
          <div className="w-full min-h-[980px] rounded-xl border border-slate-800/70 bg-slate-950/35 p-2">
            <ReactEChartsCore
              echarts={echarts}
              option={chartOption}
              notMerge
              lazyUpdate
              style={{ width: '100%', height: 960 }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default HistoryMultiframeFusionView;
