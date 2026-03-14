import React, { useEffect, useMemo, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { AlertCircle, Database, RefreshCw } from 'lucide-react';

import { HistoryMultiframeGranularity, HistoryMultiframeItem, SearchResult } from '../../types';
import * as StockService from '../../services/stockService';

echarts.use([
  BarChart,
  CandlestickChart,
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
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
  open: number;
  high: number;
  low: number;
  close: number;
  totalAmount: number;
  source: string;
  isFinalized: boolean;
  previewLevel: string | null;
  fallbackUsed: boolean;
  isPreviewOnly: boolean;
  l1MainBuy: number | null;
  l1MainSell: number | null;
  l1SuperBuy: number | null;
  l1SuperSell: number | null;
  l2MainBuy: number | null;
  l2MainSell: number | null;
  l2SuperBuy: number | null;
  l2SuperSell: number | null;
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
};

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
    const hasUsableL2 = isFinalized
      && [row.l2_main_buy, row.l2_main_sell, row.l2_super_buy, row.l2_super_sell].some((item) => toFiniteNumber(item) !== null);

    if (!hasUsableL2 && !isPreviewOnly) {
      return null;
    }

    return {
      key: row.datetime,
      label: buildLabel(row, granularity),
      datetime: row.datetime,
      tradeDate: row.trade_date,
      open: Number(row.open || 0),
      high: Number(row.high || 0),
      low: Number(row.low || 0),
      close: Number(row.close || 0),
      totalAmount: Number(row.total_amount || 0),
      source,
      isFinalized,
      previewLevel,
      fallbackUsed: row.fallback_used === true,
      isPreviewOnly,
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
  const hasFormalL2History = fusionRows.some((row) => row.isFinalized);
  const hasPreviewRows = fusionRows.some((row) => row.isPreviewOnly);

  const sourceLabel = useMemo(() => {
    if (hasFormalL2History && hasPreviewRows) return 'Source: 正式L2历史 + 今日L1预览';
    if (hasFormalL2History) return 'Source: 正式L2历史';
    if (hasPreviewRows) return 'Source: 今日L1预览';
    return 'Source: 暂无可用正式L2历史';
  }, [hasFormalL2History, hasPreviewRows]);

  const chartOption = useMemo(() => {
    if (!fusionRows.length) return {};

    const category = fusionRows.map((row) => row.label);
    const candleData = fusionRows.map((row) => [row.open, row.close, row.low, row.high]);
    const closeLine = fusionRows.map((row) => row.close);
    const superL2Buy = fusionRows.map((row) => row.l2SuperBuy);
    const superL1Buy = fusionRows.map((row) => row.l1SuperBuy);
    const superL2Sell = fusionRows.map((row) => (row.l2SuperSell === null ? null : -row.l2SuperSell));
    const superL1Sell = fusionRows.map((row) => (row.l1SuperSell === null ? null : -row.l1SuperSell));
    const mainL2Buy = fusionRows.map((row) => row.l2MainBuy);
    const mainL1Buy = fusionRows.map((row) => row.l1MainBuy);
    const mainL2Sell = fusionRows.map((row) => (row.l2MainSell === null ? null : -row.l2MainSell));
    const mainL1Sell = fusionRows.map((row) => (row.l1MainSell === null ? null : -row.l1MainSell));

    const amountAxisBound = (value: { max?: number; min?: number }) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      return maxAbs === 0 ? 1 : maxAbs;
    };

    return {
      animation: false,
      backgroundColor: 'transparent',
      legend: {
        top: 4,
        type: 'scroll',
        textStyle: { color: '#94A3B8', fontSize: 11 },
      },
      axisPointer: {
        link: [{ xAxisIndex: [0, 1] }],
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: '#334155',
        borderWidth: 1,
        textStyle: { color: '#E2E8F0', fontSize: 12 },
        extraCssText: 'box-shadow: 0 10px 24px rgba(2,6,23,0.45);',
        formatter: (params: any) => {
          const items = Array.isArray(params) ? params : [params];
          if (!items.length) return '';
          const idx = Number(items[0]?.dataIndex ?? 0);
          const row = fusionRows[idx];
          if (!row) return '';

          const marker = (color: string) =>
            `<span style="display:inline-block;margin-right:6px;border-radius:50%;width:8px;height:8px;background:${color};"></span>`;

          const meta = [
            `<div style="font-weight:700;color:#F8FAFC;margin-bottom:6px;">${row.datetime}</div>`,
            `<div style="color:#CBD5E1;">O ${row.open.toFixed(2)} / H ${row.high.toFixed(2)} / L ${row.low.toFixed(2)} / C ${row.close.toFixed(2)}</div>`,
            `<div style="color:#CBD5E1;">来源: ${row.source} ｜ finalized: ${row.isFinalized ? 'true' : 'false'} ｜ fallback: ${row.fallbackUsed ? 'true' : 'false'}</div>`,
            `<div style="color:#CBD5E1;">成交额: ${compactAmount(row.totalAmount)}</div>`,
            row.isPreviewOnly ? `<div style="margin-top:4px;color:#FBBF24;">未结算 / 当前仅 ${row.previewLevel || 'L1'} 实时口径，L2 待盘后覆盖</div>` : '',
          ].filter(Boolean);

          return [
            ...meta,
            `<div style="margin-top:8px;color:#E9D5FF;font-weight:600;">超大单（左柱）</div>`,
            `<div>${marker(COLORS.superL2Buy)}L2买入: ${compactAmount(row.l2SuperBuy)}</div>`,
            `<div>${marker(COLORS.superL1Buy)}L1买入: ${compactAmount(row.l1SuperBuy)}</div>`,
            `<div>${marker(COLORS.superL2Sell)}L2卖出: ${compactAmount(row.l2SuperSell)}</div>`,
            `<div>${marker(COLORS.superL1Sell)}L1卖出: ${compactAmount(row.l1SuperSell)}</div>`,
            `<div style="margin-top:8px;color:#FECACA;font-weight:600;">主力（右柱）</div>`,
            `<div>${marker(COLORS.mainL2Buy)}L2买入: ${compactAmount(row.l2MainBuy)}</div>`,
            `<div>${marker(COLORS.mainL1Buy)}L1买入: ${compactAmount(row.l1MainBuy)}</div>`,
            `<div>${marker(COLORS.mainL2Sell)}L2卖出: ${compactAmount(row.l2MainSell)}</div>`,
            `<div>${marker(COLORS.mainL1Sell)}L1卖出: ${compactAmount(row.l1MainSell)}</div>`,
          ].join('<br/>');
        },
      },
      grid: [
        { left: '6%', right: '4%', top: 40, height: '32%' },
        { left: '6%', right: '4%', top: '48%', height: '36%' },
      ],
      xAxis: [
        {
          type: 'category',
          data: category,
          boundaryGap: true,
          axisLine: { lineStyle: { color: COLORS.border } },
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
          nameTextStyle: { color: COLORS.closeLine, fontSize: 11 },
          axisLabel: { color: COLORS.closeLine, fontSize: 10, formatter: (v: number) => v.toFixed(2) },
          splitLine: { lineStyle: { color: COLORS.border, type: 'dashed' } },
        },
        {
          type: 'value',
          gridIndex: 1,
          scale: true,
          name: '资金绝对值',
          nameTextStyle: { color: '#CBD5E1', fontSize: 11 },
          min: (value: { max?: number; min?: number }) => -amountAxisBound(value),
          max: (value: { max?: number; min?: number }) => amountAxisBound(value),
          axisLabel: { color: '#CBD5E1', fontSize: 10, formatter: (v: number) => compactAmount(v) },
          splitLine: { lineStyle: { color: COLORS.border, type: 'dashed' } },
          axisLine: { show: true, lineStyle: { color: '#475569' } },
        },
      ],
      dataZoom: [
        {
          type: 'slider',
          xAxisIndex: [0, 1],
          bottom: 6,
          height: 18,
          showDetail: false,
          brushSelect: false,
          filterMode: 'filter',
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
          name: '超大L2买',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: superL2Buy,
          barWidth: 11,
          barCategoryGap: '42%',
          itemStyle: { color: COLORS.superL2Buy, borderRadius: 0 },
          markLine: { silent: true, symbol: ['none', 'none'], lineStyle: { color: '#475569', width: 1 }, data: [{ yAxis: 0 }] },
          z: 2,
        },
        {
          name: '超大L1买',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: superL1Buy,
          barWidth: 11,
          barGap: '-100%',
          itemStyle: { color: COLORS.superL1Buy, borderRadius: 0 },
          z: 3,
        },
        {
          name: '超大L2卖',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: superL2Sell,
          barWidth: 11,
          barGap: '-100%',
          itemStyle: { color: COLORS.superL2Sell, borderRadius: 0 },
          z: 2,
        },
        {
          name: '超大L1卖',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: superL1Sell,
          barWidth: 11,
          barGap: '-100%',
          itemStyle: { color: COLORS.superL1Sell, borderRadius: 0 },
          z: 3,
        },
        {
          name: '主力L2买',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: mainL2Buy,
          barWidth: 11,
          barGap: '55%',
          itemStyle: { color: COLORS.mainL2Buy, borderRadius: 0 },
          z: 2,
        },
        {
          name: '主力L1买',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: mainL1Buy,
          barWidth: 11,
          barGap: '-100%',
          itemStyle: { color: COLORS.mainL1Buy, borderRadius: 0 },
          z: 3,
        },
        {
          name: '主力L2卖',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: mainL2Sell,
          barWidth: 11,
          barGap: '-100%',
          itemStyle: { color: COLORS.mainL2Sell, borderRadius: 0 },
          z: 2,
        },
        {
          name: '主力L1卖',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: mainL1Sell,
          barWidth: 11,
          barGap: '-100%',
          itemStyle: { color: COLORS.mainL1Sell, borderRadius: 0 },
          z: 3,
        },
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
            </div>
            <p className="text-xs text-slate-400 mt-1">
              上方价格区，下方左超大/右主力双柱；深色 L2 做底，浅色 L1 做芯。
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
        ) : !hasFormalL2History ? (
          <div className="min-h-[420px] flex flex-col items-center justify-center text-center bg-slate-950/30 rounded-lg border border-slate-800/50 px-6">
            <Database className="w-14 h-14 mb-4 text-slate-700" />
            <h4 className="text-slate-200 font-semibold mb-2">暂无可用正式 L2 {LABELS[granularity]}历史</h4>
            <p className="text-sm text-slate-500 max-w-xl leading-6">
              新版历史多维只消费正式 L2 历史底座，并在今天未结算时追加 L1 preview。
              当前股票若尚未完成盘后 L2 回补，请先切回旧版查看原有图表，或等待该股票对应交易日的正式 L2 数据入库。
            </p>
          </div>
        ) : (
          <div className="w-full min-h-[620px]">
            <ReactEChartsCore
              echarts={echarts}
              option={chartOption}
              notMerge
              lazyUpdate
              style={{ width: '100%', height: 620 }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default HistoryMultiframeFusionView;
