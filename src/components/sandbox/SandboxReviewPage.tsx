import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { ArrowLeft, RefreshCw } from 'lucide-react';

import { SandboxPoolItem, SandboxReviewBar } from '../../types';
import * as StockService from '../../services/stockService';

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  CandlestickChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

type Granularity = '5m' | '15m' | '30m' | '60m' | '1d';
type GranularityMode = 'auto' | Granularity;
type WindowPreset = '1d' | '3d' | '5d' | '20d' | '60d' | 'all';

const DEFAULT_SYMBOL = 'sh603629';
const DEFAULT_START = '2025-01-01';
const DEFAULT_END = '2026-02-28';
const SANDBOX_MIN_DATE = '2025-01-01';
const SANDBOX_MAX_DATE = '2026-02-28';
const DAY_MS = 24 * 60 * 60 * 1000;
const MAX_VISIBLE_POINTS = 240;

const PRESET_OPTIONS: Array<{ key: WindowPreset; label: string; days: number | null }> = [
  { key: '1d', label: '1日', days: 1 },
  { key: '3d', label: '3日', days: 3 },
  { key: '5d', label: '5日', days: 5 },
  { key: '20d', label: '20日', days: 20 },
  { key: '60d', label: '60日', days: 60 },
  { key: 'all', label: '全部', days: null },
];

const GRANULARITY_OPTIONS: Array<{ key: GranularityMode; label: string }> = [
  { key: 'auto', label: '自动' },
  { key: '5m', label: '5m' },
  { key: '15m', label: '15m' },
  { key: '30m', label: '30m' },
  { key: '60m', label: '60m' },
  { key: '1d', label: '1d' },
];

const GRANULARITY_MINUTES: Record<Exclude<Granularity, '1d'>, number> = {
  '5m': 5,
  '15m': 15,
  '30m': 30,
  '60m': 60,
};

const GRANULARITY_ORDER: Granularity[] = ['5m', '15m', '30m', '60m', '1d'];

const nextGranularity = (value: Granularity): Granularity => {
  const index = GRANULARITY_ORDER.indexOf(value);
  if (index < 0 || index >= GRANULARITY_ORDER.length - 1) return '1d';
  return GRANULARITY_ORDER[index + 1];
};

const parseLocalDateTime = (datetimeText: string): Date => {
  const [datePart, timePart = '00:00:00'] = datetimeText.split(' ');
  const [year, month, day] = datePart.split('-').map((v) => parseInt(v, 10));
  const [hour, minute, second] = timePart.split(':').map((v) => parseInt(v, 10));
  return new Date(year, (month || 1) - 1, day || 1, hour || 0, minute || 0, second || 0, 0);
};

const formatLocalDateTime = (date: Date): string => {
  const pad = (value: number) => `${value}`.padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
};

const normalizeRows = (rows: SandboxReviewBar[]): SandboxReviewBar[] => {
  return [...rows].sort((a, b) => parseLocalDateTime(a.datetime).getTime() - parseLocalDateTime(b.datetime).getTime());
};

type Acc = {
  ts: number;
  symbol: string;
  sourceDate: string;
  firstTs: number;
  lastTs: number;
  open: number;
  high: number;
  low: number;
  close: number;
  total_amount: number;
  l1_main_buy: number;
  l1_main_sell: number;
  l1_super_buy: number;
  l1_super_sell: number;
  l2_main_buy: number;
  l2_main_sell: number;
  l2_super_buy: number;
  l2_super_sell: number;
};

const createAccFromRow = (row: SandboxReviewBar, ts: number): Acc => ({
  ts,
  symbol: row.symbol,
  sourceDate: row.source_date,
  firstTs: ts,
  lastTs: ts,
  open: row.open,
  high: row.high,
  low: row.low,
  close: row.close,
  total_amount: Number.isFinite(row.total_amount) ? row.total_amount : 0,
  l1_main_buy: row.l1_main_buy,
  l1_main_sell: row.l1_main_sell,
  l1_super_buy: row.l1_super_buy,
  l1_super_sell: row.l1_super_sell,
  l2_main_buy: row.l2_main_buy,
  l2_main_sell: row.l2_main_sell,
  l2_super_buy: row.l2_super_buy,
  l2_super_sell: row.l2_super_sell,
});

const mergeRowToAcc = (acc: Acc, row: SandboxReviewBar, ts: number): void => {
  acc.high = Math.max(acc.high, row.high);
  acc.low = Math.min(acc.low, row.low);
  if (ts < acc.firstTs) {
    acc.firstTs = ts;
    acc.open = row.open;
  }
  if (ts >= acc.lastTs) {
    acc.lastTs = ts;
    acc.close = row.close;
    acc.sourceDate = row.source_date;
  }
  acc.total_amount += Number.isFinite(row.total_amount) ? row.total_amount : 0;
  acc.l1_main_buy += row.l1_main_buy;
  acc.l1_main_sell += row.l1_main_sell;
  acc.l1_super_buy += row.l1_super_buy;
  acc.l1_super_sell += row.l1_super_sell;
  acc.l2_main_buy += row.l2_main_buy;
  acc.l2_main_sell += row.l2_main_sell;
  acc.l2_super_buy += row.l2_super_buy;
  acc.l2_super_sell += row.l2_super_sell;
};

const toBar = (acc: Acc, datetime: string, granularity: Granularity): SandboxReviewBar => ({
  symbol: acc.symbol,
  datetime,
  open: acc.open,
  high: acc.high,
  low: acc.low,
  close: acc.close,
  total_amount: acc.total_amount,
  l1_main_buy: acc.l1_main_buy,
  l1_main_sell: acc.l1_main_sell,
  l1_main_net: acc.l1_main_buy - acc.l1_main_sell,
  l1_super_buy: acc.l1_super_buy,
  l1_super_sell: acc.l1_super_sell,
  l1_super_net: acc.l1_super_buy - acc.l1_super_sell,
  l2_main_buy: acc.l2_main_buy,
  l2_main_sell: acc.l2_main_sell,
  l2_main_net: acc.l2_main_buy - acc.l2_main_sell,
  l2_super_buy: acc.l2_super_buy,
  l2_super_sell: acc.l2_super_sell,
  l2_super_net: acc.l2_super_buy - acc.l2_super_sell,
  source_date: datetime.slice(0, 10),
  bucket_granularity: granularity,
});

const aggregateRows = (rows: SandboxReviewBar[], granularity: Granularity): SandboxReviewBar[] => {
  if (granularity === '5m') {
    return rows.map((row) => ({
      ...row,
      total_amount: Number.isFinite(row.total_amount) ? row.total_amount : 0,
      bucket_granularity: '5m',
    }));
  }

  if (granularity === '1d') {
    const buckets = new Map<string, Acc>();
    for (const row of rows) {
      const ts = parseLocalDateTime(row.datetime).getTime();
      const bucketKey = row.source_date || row.datetime.slice(0, 10);
      const prev = buckets.get(bucketKey);
      if (!prev) {
        buckets.set(bucketKey, createAccFromRow(row, ts));
      } else {
        mergeRowToAcc(prev, row, ts);
      }
    }

    return Array.from(buckets.entries())
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .map(([dateKey, acc]) => toBar(acc, `${dateKey} 15:00:00`, '1d'));
  }

  const minutes = GRANULARITY_MINUTES[granularity];
  const bucketMs = minutes * 60 * 1000;
  const buckets = new Map<number, Acc>();

  for (const row of rows) {
    const ts = parseLocalDateTime(row.datetime).getTime();
    const bucketTs = Math.floor(ts / bucketMs) * bucketMs;
    const prev = buckets.get(bucketTs);
    if (!prev) {
      buckets.set(bucketTs, createAccFromRow(row, ts));
    } else {
      mergeRowToAcc(prev, row, ts);
    }
  }

  return Array.from(buckets.values())
    .sort((a, b) => a.ts - b.ts)
    .map((acc) => toBar(acc, formatLocalDateTime(new Date(acc.ts)), granularity));
};

const calcRangeByDays = (rows: SandboxReviewBar[], days: number | null): [number, number] => {
  if (!rows.length || days === null) return [0, 100];

  const timestamps = rows.map((row) => parseLocalDateTime(row.datetime).getTime());
  const endTs = timestamps[timestamps.length - 1];
  const startTs = endTs - days * DAY_MS;
  const startIdx = Math.max(0, timestamps.findIndex((ts) => ts >= startTs));
  const denominator = Math.max(1, timestamps.length - 1);
  return [(startIdx / denominator) * 100, 100];
};

const calcVisibleDays = (rows: SandboxReviewBar[], zoomRange: [number, number]): number => {
  if (rows.length <= 1) return 0;

  const denominator = Math.max(1, rows.length - 1);
  const startIdx = Math.floor((zoomRange[0] / 100) * denominator);
  const endIdx = Math.ceil((zoomRange[1] / 100) * denominator);
  const start = parseLocalDateTime(rows[Math.max(0, startIdx)].datetime).getTime();
  const end = parseLocalDateTime(rows[Math.min(rows.length - 1, Math.max(startIdx, endIdx))].datetime).getTime();
  return Math.max(0, (end - start) / DAY_MS);
};

const chooseGranularityByDays = (visibleDays: number): Granularity => {
  if (visibleDays <= 1) return '5m';
  if (visibleDays <= 5) return '15m';
  if (visibleDays <= 20) return '60m';
  return '1d';
};

const estimateVisibleCount = (rows: SandboxReviewBar[], zoomRange: [number, number]): number => {
  if (!rows.length) return 0;
  const ratio = Math.max(0.01, (zoomRange[1] - zoomRange[0]) / 100);
  return Math.max(1, Math.round(rows.length * ratio));
};

const formatFlowValueW = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  return `${(value / 10000).toFixed(2)}w`;
};

const trimTrailingZeros = (valueText: string): string => valueText.replace(/\.0+$|(\.\d*[1-9])0+$/, '$1');

const formatAmountCompact = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${sign}${trimTrailingZeros((abs / 100000000).toFixed(2))}亿`;
  if (abs >= 10000) return `${sign}${trimTrailingZeros((abs / 10000).toFixed(2))}万`;
  return `${sign}${trimTrailingZeros(abs.toFixed(0))}`;
};

const formatPercentValue = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  return `${value.toFixed(2)}%`;
};

const formatPercentAxis = (value: number): string => {
  if (!Number.isFinite(value)) return '--';
  return `${Math.round(value)}%`;
};

const isDateInSandboxWindow = (startDate: string, endDate: string): boolean =>
  startDate >= SANDBOX_MIN_DATE && endDate <= SANDBOX_MAX_DATE && endDate >= startDate;

const formatMarketCapYi = (marketCap: number): string => {
  if (!Number.isFinite(marketCap) || marketCap <= 0) return '--';
  return `${trimTrailingZeros((marketCap / 100000000).toFixed(2))}亿`;
};

const calcRatioPercent = (numerator: number, denominator: number): number | null => {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return null;
  return (numerator / denominator) * 100;
};

const splitSignedSeries = (values: number[]): { positive: number[]; negative: number[] } => ({
  // Use zero fill instead of null to keep area charts continuously visible.
  positive: values.map((value) => (value > 0 ? value : 0)),
  negative: values.map((value) => (value < 0 ? value : 0)),
});

const splitSignedSeriesNullable = (
  values: Array<number | null>
): { positive: Array<number | null>; negative: Array<number | null> } => ({
  positive: values.map((value) => (value === null ? null : value > 0 ? value : 0)),
  negative: values.map((value) => (value === null ? null : value < 0 ? value : 0)),
});

const SandboxReviewPage: React.FC = () => {
  const [poolItems, setPoolItems] = useState<SandboxPoolItem[]>([]);
  const [poolTotal, setPoolTotal] = useState(0);
  const [poolAsOfDate, setPoolAsOfDate] = useState('');
  const [symbolInput, setSymbolInput] = useState(DEFAULT_SYMBOL);
  const [startDateInput, setStartDateInput] = useState(DEFAULT_START);
  const [endDateInput, setEndDateInput] = useState(DEFAULT_END);
  const [querySymbol, setQuerySymbol] = useState(DEFAULT_SYMBOL);
  const [queryStartDate, setQueryStartDate] = useState(DEFAULT_START);
  const [queryEndDate, setQueryEndDate] = useState(DEFAULT_END);
  const [rawData, setRawData] = useState<SandboxReviewBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [emptyMessage, setEmptyMessage] = useState('');
  const [activePreset, setActivePreset] = useState<WindowPreset>('20d');
  const [zoomRange, setZoomRange] = useState<[number, number]>([0, 100]);
  const [granularityMode, setGranularityMode] = useState<GranularityMode>('auto');
  const [anchorModeEnabled, setAnchorModeEnabled] = useState(false);
  const [anchorTs, setAnchorTs] = useState<number | null>(null);

  const fetchData = useCallback(async (symbol: string, startDate: string, endDate: string) => {
    setLoading(true);
    setError('');
    setEmptyMessage('');
    try {
      const rows = await StockService.fetchSandboxReviewData(symbol, startDate, endDate, '5m');
      if (!rows.length) {
        setRawData([]);
        setActivePreset('20d');
        setZoomRange([0, 100]);
        setEmptyMessage(`接口返回空数据：${symbol} ${startDate} ~ ${endDate}`);
        return;
      }

      const sortedRows = normalizeRows(rows);
      setRawData(sortedRows);
      setActivePreset('20d');
      setZoomRange(calcRangeByDays(sortedRows, 20));
      setQuerySymbol(symbol);
      setQueryStartDate(startDate);
      setQueryEndDate(endDate);
    } catch (err: any) {
      setRawData([]);
      setError(err?.message || '查询失败，请检查 sandbox API 与 sandbox_review.db。');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      try {
        const pool = await StockService.fetchSandboxReviewPool('', 3000);
        setPoolItems(pool.items);
        setPoolTotal(pool.total);
        setPoolAsOfDate(pool.as_of_date || '');
        if (pool.items.length > 0) {
          const picked = pool.items.find((item) => item.symbol === DEFAULT_SYMBOL) || pool.items[0];
          setSymbolInput(picked.symbol);
          await fetchData(picked.symbol, startDateInput, endDateInput);
          return;
        }
        setError('股票池为空，请先执行 pool build + backfill。');
      } catch (e: any) {
        setError(e?.message || '股票池加载失败，请检查 /api/sandbox/pool');
      }
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const aggregatedByGranularity = useMemo(() => {
    const sortedRaw = normalizeRows(rawData);
    return {
      '5m': aggregateRows(sortedRaw, '5m'),
      '15m': aggregateRows(sortedRaw, '15m'),
      '30m': aggregateRows(sortedRaw, '30m'),
      '60m': aggregateRows(sortedRaw, '60m'),
      '1d': aggregateRows(sortedRaw, '1d'),
    } as Record<Granularity, SandboxReviewBar[]>;
  }, [rawData]);

  const viewState = useMemo(() => {
    const baseRows = aggregatedByGranularity['5m'];
    const visibleDays = calcVisibleDays(baseRows, zoomRange);
    let granularity: Granularity = granularityMode === 'auto' ? chooseGranularityByDays(visibleDays) : granularityMode;

    while (
      granularityMode === 'auto' &&
      granularity !== '1d' &&
      estimateVisibleCount(aggregatedByGranularity[granularity], zoomRange) > MAX_VISIBLE_POINTS
    ) {
      granularity = nextGranularity(granularity);
    }

    return {
      bars: aggregatedByGranularity[granularity],
      granularity,
      visibleDays,
      visibleCount: estimateVisibleCount(aggregatedByGranularity[granularity], zoomRange),
    };
  }, [aggregatedByGranularity, granularityMode, zoomRange]);

  const correlationData = useMemo(() => {
    const rows = aggregatedByGranularity['5m'];
    if (!rows.length) {
      return {
        points: [] as Array<{
          datetime: string;
          priceReturn: number;
          nextPriceReturn: number | null;
          l1Net: number;
          l2Net: number;
          l1ActivityRatio: number;
          l2ActivityRatio: number;
        }>,
      };
    }

    const points = rows.map((row, index) => {
      const open = row.open;
      const close = row.close;
      const totalAmount = Number(row.total_amount) || 0;
      const priceReturn = open > 0 ? ((close - open) / open) * 100 : NaN;
      const nextRow = rows[index + 1];
      const nextPriceReturn =
        nextRow && nextRow.open > 0 ? ((nextRow.close - nextRow.open) / nextRow.open) * 100 : null;

      const l1Abs = row.l1_main_buy + row.l1_main_sell;
      const l2Abs = row.l2_main_buy + row.l2_main_sell;

      return {
        datetime: row.datetime,
        priceReturn,
        nextPriceReturn,
        l1Net: row.l1_main_net,
        l2Net: row.l2_main_net,
        l1ActivityRatio: totalAmount > 0 ? (l1Abs / totalAmount) * 100 : NaN,
        l2ActivityRatio: totalAmount > 0 ? (l2Abs / totalAmount) * 100 : NaN,
      };
    });

    return { points };
  }, [aggregatedByGranularity]);

  const correlationStats = useMemo(() => {
    const points = correlationData.points.filter(
      (p) =>
        Number.isFinite(p.priceReturn) &&
        Number.isFinite(p.l1Net) &&
        Number.isFinite(p.l2Net) &&
        Number.isFinite(p.l1ActivityRatio) &&
        Number.isFinite(p.l2ActivityRatio)
    );

    const pearson = (x: number[], y: number[]): number | null => {
      if (x.length < 2 || y.length < 2 || x.length !== y.length) return null;
      const mx = x.reduce((a, b) => a + b, 0) / x.length;
      const my = y.reduce((a, b) => a + b, 0) / y.length;
      let cov = 0;
      let vx = 0;
      let vy = 0;
      for (let i = 0; i < x.length; i += 1) {
        const dx = x[i] - mx;
        const dy = y[i] - my;
        cov += dx * dy;
        vx += dx * dx;
        vy += dy * dy;
      }
      if (vx <= 0 || vy <= 0) return null;
      return cov / Math.sqrt(vx * vy);
    };

    const concurrent = points;
    const leadLag = points.filter((p) => Number.isFinite(p.nextPriceReturn));
    const highActivity = leadLag.filter((p) => (p.l2ActivityRatio || 0) > 30);

    const l1Concurrent = pearson(
      concurrent.map((p) => p.l1Net),
      concurrent.map((p) => p.priceReturn)
    );
    const l2Concurrent = pearson(
      concurrent.map((p) => p.l2Net),
      concurrent.map((p) => p.priceReturn)
    );

    const l1Lead = pearson(
      leadLag.map((p) => p.l1Net),
      leadLag.map((p) => p.nextPriceReturn as number)
    );
    const l2Lead = pearson(
      leadLag.map((p) => p.l2Net),
      leadLag.map((p) => p.nextPriceReturn as number)
    );

    const l2Conditional = pearson(
      highActivity.map((p) => p.l2Net),
      highActivity.map((p) => p.nextPriceReturn as number)
    );

    return {
      concurrentCount: concurrent.length,
      leadCount: leadLag.length,
      highActivityCount: highActivity.length,
      highActivityRatio: leadLag.length ? (highActivity.length / leadLag.length) * 100 : 0,
      l1Concurrent,
      l2Concurrent,
      l1Lead,
      l2Lead,
      l2Conditional,
    };
  }, [correlationData]);

  const scatterData = useMemo(() => {
    const points = correlationData.points.filter((p) => Number.isFinite(p.priceReturn));
    const buildScatter = (netKey: 'l1Net' | 'l2Net', ratioKey: 'l1ActivityRatio' | 'l2ActivityRatio') =>
      points.map((p) => ({
        value: [p[netKey], p.priceReturn, p[ratioKey], p.datetime],
      }));
    return {
      l1: buildScatter('l1Net', 'l1ActivityRatio'),
      l2: buildScatter('l2Net', 'l2ActivityRatio'),
    };
  }, [correlationData]);

  const makeScatterOption = useCallback(
    (title: string, data: Array<{ value: [number, number, number, string] }>) => ({
      animation: false,
      title: {
        text: title,
        left: 'center',
        top: 6,
        textStyle: { color: '#cbd5e1', fontSize: 12, fontWeight: 'normal' },
      },
      grid: { left: '8%', right: '5%', top: 36, bottom: 36 },
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: '#334155',
        borderWidth: 1,
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        formatter: (params: any) => {
          const value = params?.value || [];
          const net = Number(value[0] || 0);
          const ret = Number(value[1] || 0);
          const ratio = Number(value[2] || 0);
          const dt = value[3] || '--';
          return [
            `${dt}`,
            `净流入: ${formatFlowValueW(net)}`,
            `涨跌幅: ${ret.toFixed(3)}%`,
            `活跃度: ${ratio.toFixed(2)}%`,
          ].join('<br/>');
        },
      },
      xAxis: {
        type: 'value',
        axisLabel: {
          color: '#94a3b8',
          formatter: (v: number) => formatFlowValueW(v),
        },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8', formatter: (v: number) => formatPercentAxis(v) },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      series: [
        {
          type: 'scatter',
          data,
          symbolSize: (val: any) => {
            const ratio = Number(val?.[2] || 0);
            return Math.max(6, Math.min(20, 6 + ratio * 0.4));
          },
          itemStyle: {
            color: (params: any) => {
              const ratio = Number(params?.value?.[2] || 0);
              if (ratio >= 50) return '#ef4444';
              if (ratio >= 30) return '#f97316';
              if (ratio >= 15) return '#f59e0b';
              return '#94a3b8';
            },
            opacity: 0.8,
          },
        },
      ],
    }),
    []
  );

  const scatterOptionL1 = useMemo(
    () => makeScatterOption('L1净流入 vs 5分钟涨跌幅', scatterData.l1),
    [makeScatterOption, scatterData.l1]
  );
  const scatterOptionL2 = useMemo(
    () => makeScatterOption('L2净流入 vs 5分钟涨跌幅', scatterData.l2),
    [makeScatterOption, scatterData.l2]
  );

  const rawRangeText = useMemo(() => {
    if (!rawData.length) return '--';
    return `${rawData[0].datetime} ~ ${rawData[rawData.length - 1].datetime}`;
  }, [rawData]);

  const activePoolItem = useMemo(
    () => poolItems.find((item) => item.symbol === querySymbol) || null,
    [poolItems, querySymbol]
  );

  const handleExecuteQuery = useCallback(async () => {
    const symbol = symbolInput.trim().toLowerCase();
    if (!symbol) {
      setError('请先输入股票代码');
      return;
    }
    if (!isDateInSandboxWindow(startDateInput, endDateInput)) {
      setError(`日期范围仅支持 ${SANDBOX_MIN_DATE} ~ ${SANDBOX_MAX_DATE}`);
      return;
    }
    setAnchorTs(null);
    await fetchData(symbol, startDateInput, endDateInput);
  }, [symbolInput, startDateInput, endDateInput]);

  const handleSelectPreset = (preset: WindowPreset, days: number | null) => {
    setActivePreset(preset);
    setZoomRange(calcRangeByDays(aggregatedByGranularity['5m'], days));
  };

  const handleDataZoom = useCallback((event: any) => {
    const payload = event?.batch?.[0] ?? event;
    const nextStart = typeof payload?.start === 'number' ? payload.start : zoomRange[0];
    const nextEnd = typeof payload?.end === 'number' ? payload.end : zoomRange[1];
    const normalized: [number, number] = [
      Math.max(0, Math.min(100, nextStart)),
      Math.max(0, Math.min(100, nextEnd)),
    ];

    if (Math.abs(normalized[0] - zoomRange[0]) > 0.01 || Math.abs(normalized[1] - zoomRange[1]) > 0.01) {
      setZoomRange(normalized);
    }
  }, [zoomRange]);

  const handleChartClick = useCallback((event: any) => {
    if (!anchorModeEnabled) return;
    if (event?.seriesType !== 'candlestick') return;
    const dataIndex = typeof event?.dataIndex === 'number' ? event.dataIndex : -1;
    if (dataIndex < 0 || dataIndex >= viewState.bars.length) return;
    const row = viewState.bars[dataIndex];
    if (!row?.datetime) return;
    setAnchorTs(parseLocalDateTime(row.datetime).getTime());
  }, [anchorModeEnabled, viewState.bars]);

  const option = useMemo(() => {
    const data = viewState.bars;
    if (!data.length) {
      return {};
    }

    const category = data.map((row) => (
      viewState.granularity === '1d' ? row.datetime.substring(5, 10) : row.datetime.substring(5, 16)
    ));
    const candles = data.map((row) => [row.open, row.close, row.low, row.high]);

    const l1MainBuy = data.map((row) => row.l1_main_buy);
    const l1MainSell = data.map((row) => -row.l1_main_sell);
    const l1SuperBuy = data.map((row) => row.l1_super_buy);
    const l1SuperSell = data.map((row) => -row.l1_super_sell);
    const l1MainNet = data.map((row) => row.l1_main_net);
    const l1SuperNet = data.map((row) => row.l1_super_net);

    const l2MainBuy = data.map((row) => row.l2_main_buy);
    const l2MainSell = data.map((row) => -row.l2_main_sell);
    const l2SuperBuy = data.map((row) => row.l2_super_buy);
    const l2SuperSell = data.map((row) => -row.l2_super_sell);
    const l2MainNet = data.map((row) => row.l2_main_net);
    const l2SuperNet = data.map((row) => row.l2_super_net);
    const resolvedTotalAmount = data.map((row) => {
      if (row.total_amount > 0) return row.total_amount;
      // Fallback for old/abnormal rows missing total_amount to avoid empty charts.
      return Math.max(
        0,
        row.l1_main_buy + row.l1_main_sell + row.l1_super_buy + row.l1_super_sell,
        row.l2_main_buy + row.l2_main_sell + row.l2_super_buy + row.l2_super_sell
      );
    });
    const l1MainActivity = data.map((row, idx) => calcRatioPercent(row.l1_main_buy + row.l1_main_sell, resolvedTotalAmount[idx]));
    const l2MainActivity = data.map((row, idx) => calcRatioPercent(row.l2_main_buy + row.l2_main_sell, resolvedTotalAmount[idx]));
    const l1SuperActivity = data.map((row, idx) => calcRatioPercent(row.l1_super_buy + row.l1_super_sell, resolvedTotalAmount[idx]));
    const l2SuperActivity = data.map((row, idx) => calcRatioPercent(row.l2_super_buy + row.l2_super_sell, resolvedTotalAmount[idx]));
    const l1NetRatio = data.map((row, idx) => calcRatioPercent(row.l1_main_net + row.l1_super_net, resolvedTotalAmount[idx]));
    const l2NetRatio = data.map((row, idx) => calcRatioPercent(row.l2_main_net + row.l2_super_net, resolvedTotalAmount[idx]));

    const l1MainNetSplit = splitSignedSeries(l1MainNet);
    const l2MainNetSplit = splitSignedSeries(l2MainNet);
    const l1SuperNetSplit = splitSignedSeries(l1SuperNet);
    const l2SuperNetSplit = splitSignedSeries(l2SuperNet);

    const timestamps = data.map((row) => parseLocalDateTime(row.datetime).getTime());
    const anchorIndex = anchorModeEnabled && anchorTs !== null ? timestamps.findIndex((ts) => ts >= anchorTs) : -1;
    const anchorCategory = anchorIndex >= 0 ? category[anchorIndex] : null;

    const buildCumulative = (series: number[]): Array<number | null> => {
      let cumulative = 0;
      return series.map((value, idx) => {
        if (anchorIndex < 0 || idx < anchorIndex) return null;
        cumulative += Number.isFinite(value) ? value : 0;
        return cumulative;
      });
    };

    const l1MainCum = buildCumulative(l1MainNet);
    const l2MainCum = buildCumulative(l2MainNet);
    const l1SuperCum = buildCumulative(l1SuperNet);
    const l2SuperCum = buildCumulative(l2SuperNet);

    const l1MainCumSplit = splitSignedSeriesNullable(l1MainCum);
    const l2MainCumSplit = splitSignedSeriesNullable(l2MainCum);
    const l1SuperCumSplit = splitSignedSeriesNullable(l1SuperCum);
    const l2SuperCumSplit = splitSignedSeriesNullable(l2SuperCum);

    const anchorMarkLine = anchorCategory
      ? {
          silent: true,
          symbol: ['none', 'none'],
          lineStyle: { color: '#f59e0b', width: 1, type: 'dashed' },
          label: { show: false },
          data: [{ xAxis: anchorCategory }],
        }
      : undefined;

    const symmetricMin = (value: any) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      return maxAbs === 0 ? -1 : -maxAbs;
    };
    const symmetricMax = (value: any) => {
      const maxAbs = Math.max(Math.abs(value.max ?? 0), Math.abs(value.min ?? 0));
      return maxAbs === 0 ? 1 : maxAbs;
    };

    return {
      animation: false,
      backgroundColor: 'transparent',
      legend: {
        type: 'scroll',
        top: 0,
        textStyle: { color: '#94a3b8' },
        data: [
          'K线',
          'L2主力买',
          'L1主力买',
          'L2主力卖',
          'L1主力卖',
          'L2主力活跃度',
          'L1主力活跃度',
          'L2超大买',
          'L1超大买',
          'L2超大卖',
          'L1超大卖',
          'L2超大活跃度',
          'L1超大活跃度',
          'L2主力净',
          'L1主力净',
          'L2超大净',
          'L1超大净',
          'L2净流比',
          'L1净流比',
          'L2主力累计净',
          'L1主力累计净',
          'L2超大累计净',
          'L1超大累计净',
        ],
      },
      title: [
        { text: '股价K线', left: '6.2%', top: 20, textStyle: { color: '#fbbf24', fontSize: 11, fontWeight: 'normal' } },
        { text: '主力绝对资金 + 活跃度', left: '6.2%', top: '20%', textStyle: { color: '#fca5a5', fontSize: 11, fontWeight: 'normal' } },
        { text: '超大绝对资金 + 活跃度', left: '6.2%', top: '29%', textStyle: { color: '#fdba74', fontSize: 11, fontWeight: 'normal' } },
        { text: '主力净流入对比', left: '6.2%', top: '38%', textStyle: { color: '#c4b5fd', fontSize: 11, fontWeight: 'normal' } },
        { text: '超大净流入对比', left: '6.2%', top: '47%', textStyle: { color: '#a78bfa', fontSize: 11, fontWeight: 'normal' } },
        { text: '净流比对比', left: '6.2%', top: '56%', textStyle: { color: '#fca5a5', fontSize: 11, fontWeight: 'normal' } },
        { text: '主力累计净流入（L2，锚点起算）', left: '6.2%', top: '64%', textStyle: { color: '#c4b5fd', fontSize: 11, fontWeight: 'normal' } },
        { text: '主力累计净流入（L1，锚点起算）', left: '6.2%', top: '71%', textStyle: { color: '#fca5a5', fontSize: 11, fontWeight: 'normal' } },
        { text: '超大累计净流入（L2，锚点起算）', left: '6.2%', top: '78%', textStyle: { color: '#a78bfa', fontSize: 11, fontWeight: 'normal' } },
        { text: '超大累计净流入（L1，锚点起算）', left: '6.2%', top: '85%', textStyle: { color: '#fca5a5', fontSize: 11, fontWeight: 'normal' } },
      ],
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: '#334155',
        borderWidth: 1,
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        extraCssText: 'box-shadow: 0 10px 24px rgba(2,6,23,0.45);',
        axisPointer: {
          type: 'cross',
        },
        formatter: (params: any) => {
          const items = Array.isArray(params) ? params : [params];
          if (!items.length) return '';
          const idx = Number(items[0]?.dataIndex ?? 0);
          const axisLabel = items[0]?.axisValueLabel || items[0]?.name || '--';
          const row = data[idx];
          if (!row) return `${axisLabel}`;

          const marker = (color: string) =>
            `<span style="display:inline-block;margin-right:6px;border-radius:50%;width:8px;height:8px;background:${color};"></span>`;

          const section = (title: string, lines: string[]) =>
            [`<div style="margin-top:6px;color:#cbd5e1;font-weight:600;">${title}</div>`, ...lines].join('<br/>');

          const blocks: string[] = [
            `<div style="font-weight:700;color:#f8fafc;">${axisLabel}</div>`,
            section('股价K线', [
              `${marker('#fbbf24')}开: ${row.open.toFixed(2)}  高: ${row.high.toFixed(2)}  低: ${row.low.toFixed(2)}  收: ${row.close.toFixed(2)}`,
            ]),
            section('主力绝对资金 + 活跃度', [
              `${marker('#D32F2F')}L2主力买: ${formatAmountCompact(row.l2_main_buy)}`,
              `${marker('#388E3C')}L2主力卖: ${formatAmountCompact(row.l2_main_sell)}`,
              `${marker('#F4B7C0')}L1主力买: ${formatAmountCompact(row.l1_main_buy)}`,
              `${marker('#B7DDB8')}L1主力卖: ${formatAmountCompact(row.l1_main_sell)}`,
              `${marker('#991B1B')}L2主力活跃度: ${formatPercentValue(l2MainActivity[idx] ?? NaN)}`,
              `${marker('#FCA5A5')}L1主力活跃度: ${formatPercentValue(l1MainActivity[idx] ?? NaN)}`,
            ]),
            section('超大绝对资金 + 活跃度', [
              `${marker('#D32F2F')}L2超大买: ${formatAmountCompact(row.l2_super_buy)}`,
              `${marker('#388E3C')}L2超大卖: ${formatAmountCompact(row.l2_super_sell)}`,
              `${marker('#F4B7C0')}L1超大买: ${formatAmountCompact(row.l1_super_buy)}`,
              `${marker('#B7DDB8')}L1超大卖: ${formatAmountCompact(row.l1_super_sell)}`,
              `${marker('#991B1B')}L2超大活跃度: ${formatPercentValue(l2SuperActivity[idx] ?? NaN)}`,
              `${marker('#FCA5A5')}L1超大活跃度: ${formatPercentValue(l1SuperActivity[idx] ?? NaN)}`,
            ]),
            section('主力净流入对比', [
              `${marker('#6D28D9')}L2主力净: ${formatAmountCompact(row.l2_main_net)}`,
              `${marker('#DC2626')}L1主力净: ${formatAmountCompact(row.l1_main_net)}`,
            ]),
            section('超大净流入对比', [
              `${marker('#6D28D9')}L2超大净: ${formatAmountCompact(row.l2_super_net)}`,
              `${marker('#DC2626')}L1超大净: ${formatAmountCompact(row.l1_super_net)}`,
            ]),
            section('净流比对比', [
              `${marker('#6D28D9')}L2净流比: ${formatPercentValue(l2NetRatio[idx] ?? NaN)}`,
              `${marker('#DC2626')}L1净流比: ${formatPercentValue(l1NetRatio[idx] ?? NaN)}`,
            ]),
            section('主力累计净流入（L2，锚点起算）', [
              `${marker('#6D28D9')}L2主力累计净: ${l2MainCum[idx] === null ? '--' : formatAmountCompact(l2MainCum[idx] ?? NaN)}`,
            ]),
            section('主力累计净流入（L1，锚点起算）', [
              `${marker('#DC2626')}L1主力累计净: ${l1MainCum[idx] === null ? '--' : formatAmountCompact(l1MainCum[idx] ?? NaN)}`,
            ]),
            section('超大累计净流入（L2，锚点起算）', [
              `${marker('#6D28D9')}L2超大累计净: ${l2SuperCum[idx] === null ? '--' : formatAmountCompact(l2SuperCum[idx] ?? NaN)}`,
            ]),
            section('超大累计净流入（L1，锚点起算）', [
              `${marker('#DC2626')}L1超大累计净: ${l1SuperCum[idx] === null ? '--' : formatAmountCompact(l1SuperCum[idx] ?? NaN)}`,
            ]),
          ];

          return blocks.join('<br/>');
        },
      },
      axisPointer: {
        link: [{ xAxisIndex: 'all' }],
      },
      grid: [
        { left: '6%', right: '4%', top: 40, height: '15%' },
        { left: '6%', right: '4%', top: '20%', height: '6.5%' },
        { left: '6%', right: '4%', top: '27.5%', height: '6.5%' },
        { left: '6%', right: '4%', top: '35%', height: '6.5%' },
        { left: '6%', right: '4%', top: '42.5%', height: '6.5%' },
        { left: '6%', right: '4%', top: '50%', height: '6.5%' },
        { left: '6%', right: '4%', top: '57.5%', height: '6.5%' },
        { left: '6%', right: '4%', top: '65%', height: '6.5%' },
        { left: '6%', right: '4%', top: '72.5%', height: '6.5%' },
        { left: '6%', right: '4%', top: '80%', height: '6.5%' },
      ],
      xAxis: [
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 1, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 2, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 3, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 4, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 5, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 6, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 7, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { show: false }, gridIndex: 8, min: 'dataMin', max: 'dataMax' },
        { type: 'category', data: category, boundaryGap: true, axisLabel: { color: '#64748b', fontSize: 10 }, gridIndex: 9, min: 'dataMin', max: 'dataMax' },
      ],
      yAxis: [
        {
          type: 'value',
          scale: true,
          name: '价格',
          nameLocation: 'middle',
          nameGap: 44,
          nameTextStyle: { color: '#fbbf24', fontSize: 11 },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#fbbf24' },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 1,
          name: '主力绝对资金(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#fca5a5', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#fca5a5', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 1,
          position: 'right',
          show: false,
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 2,
          name: '超大绝对资金(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#fdba74', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#fdba74', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 2,
          position: 'right',
          show: false,
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 3,
          name: '主力净流入(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#93c5fd', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#93c5fd', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 4,
          name: '超大净流入(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#a78bfa', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#a78bfa', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 5,
          name: '净流比(%)',
          nameLocation: 'middle',
          nameGap: 44,
          nameTextStyle: { color: '#fca5a5', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#fca5a5', formatter: (v: number) => formatPercentAxis(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 6,
          name: '主力累计净流入L2(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#c4b5fd', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#c4b5fd', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 7,
          name: '主力累计净流入L1(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#fca5a5', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#fca5a5', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 8,
          name: '超大累计净流入L2(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#a78bfa', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#a78bfa', formatter: (v: number) => formatAmountCompact(v) },
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 9,
          name: '超大累计净流入L1(w)',
          nameLocation: 'middle',
          nameGap: 50,
          nameTextStyle: { color: '#fca5a5', fontSize: 11 },
          min: symmetricMin,
          max: symmetricMax,
          axisLine: { show: true, lineStyle: { color: '#111827', width: 1.2 } },
          splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          axisLabel: { color: '#fca5a5', formatter: (v: number) => formatAmountCompact(v) },
        },
      ],
      dataZoom: [
        {
          type: 'slider',
          xAxisIndex: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
          start: zoomRange[0],
          end: zoomRange[1],
          realtime: true,
          bottom: 2,
          height: 18,
          showDetail: false,
          brushSelect: false,
          zoomLock: false,
          filterMode: 'filter',
          handleSize: '120%',
        },
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: candles,
          itemStyle: {
            color: '#ef4444',
            color0: '#22c55e',
            borderColor: '#ef4444',
            borderColor0: '#22c55e',
          },
          markLine: anchorMarkLine,
        },
        { name: 'L2主力买', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: l2MainBuy, itemStyle: { color: '#D32F2F' }, z: 2, markLine: anchorMarkLine },
        { name: 'L1主力买', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: l1MainBuy, itemStyle: { color: '#F4B7C0' }, barGap: '-100%', z: 3 },
        { name: 'L2主力卖', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: l2MainSell, itemStyle: { color: '#388E3C' }, z: 2 },
        { name: 'L1主力卖', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: l1MainSell, itemStyle: { color: '#B7DDB8' }, barGap: '-100%', z: 3 },
        { name: 'L2主力活跃度', type: 'line', xAxisIndex: 1, yAxisIndex: 2, data: l2MainActivity, showSymbol: false, lineStyle: { color: '#991B1B', width: 1.5 }, itemStyle: { color: '#991B1B' }, z: 5 },
        { name: 'L1主力活跃度', type: 'line', xAxisIndex: 1, yAxisIndex: 2, data: l1MainActivity, showSymbol: false, lineStyle: { color: '#FCA5A5', width: 1.5 }, itemStyle: { color: '#FCA5A5' }, z: 5 },

        { name: 'L2超大买', type: 'bar', xAxisIndex: 2, yAxisIndex: 3, data: l2SuperBuy, itemStyle: { color: '#D32F2F' }, z: 2, markLine: anchorMarkLine },
        { name: 'L1超大买', type: 'bar', xAxisIndex: 2, yAxisIndex: 3, data: l1SuperBuy, itemStyle: { color: '#F4B7C0' }, barGap: '-100%', z: 3 },
        { name: 'L2超大卖', type: 'bar', xAxisIndex: 2, yAxisIndex: 3, data: l2SuperSell, itemStyle: { color: '#388E3C' }, z: 2 },
        { name: 'L1超大卖', type: 'bar', xAxisIndex: 2, yAxisIndex: 3, data: l1SuperSell, itemStyle: { color: '#B7DDB8' }, barGap: '-100%', z: 3 },
        { name: 'L2超大活跃度', type: 'line', xAxisIndex: 2, yAxisIndex: 4, data: l2SuperActivity, showSymbol: false, lineStyle: { color: '#991B1B', width: 1.5 }, itemStyle: { color: '#991B1B' }, z: 5 },
        { name: 'L1超大活跃度', type: 'line', xAxisIndex: 2, yAxisIndex: 4, data: l1SuperActivity, showSymbol: false, lineStyle: { color: '#FCA5A5', width: 1.5 }, itemStyle: { color: '#FCA5A5' }, z: 5 },

        { name: 'L2主力净', type: 'line', xAxisIndex: 3, yAxisIndex: 5, data: l2MainNetSplit.positive, showSymbol: false, lineStyle: { color: '#6D28D9', width: 1.2 }, areaStyle: { color: 'rgba(109,40,217,0.25)' }, z: 2, markLine: anchorMarkLine },
        { name: 'L2主力净', type: 'line', xAxisIndex: 3, yAxisIndex: 5, data: l2MainNetSplit.negative, showSymbol: false, lineStyle: { color: '#B45309', width: 1.2 }, areaStyle: { color: 'rgba(180,83,9,0.25)' }, z: 2 },
        { name: 'L1主力净', type: 'line', xAxisIndex: 3, yAxisIndex: 5, data: l1MainNetSplit.positive, showSymbol: false, lineStyle: { color: '#DC2626', width: 1.2 }, areaStyle: { color: 'rgba(220,38,38,0.18)' }, z: 3 },
        { name: 'L1主力净', type: 'line', xAxisIndex: 3, yAxisIndex: 5, data: l1MainNetSplit.negative, showSymbol: false, lineStyle: { color: '#16A34A', width: 1.2 }, areaStyle: { color: 'rgba(22,163,74,0.18)' }, z: 3 },

        { name: 'L2超大净', type: 'line', xAxisIndex: 4, yAxisIndex: 6, data: l2SuperNetSplit.positive, showSymbol: false, lineStyle: { color: '#6D28D9', width: 1.2 }, areaStyle: { color: 'rgba(109,40,217,0.25)' }, z: 2, markLine: anchorMarkLine },
        { name: 'L2超大净', type: 'line', xAxisIndex: 4, yAxisIndex: 6, data: l2SuperNetSplit.negative, showSymbol: false, lineStyle: { color: '#B45309', width: 1.2 }, areaStyle: { color: 'rgba(180,83,9,0.25)' }, z: 2 },
        { name: 'L1超大净', type: 'line', xAxisIndex: 4, yAxisIndex: 6, data: l1SuperNetSplit.positive, showSymbol: false, lineStyle: { color: '#DC2626', width: 1.2 }, areaStyle: { color: 'rgba(220,38,38,0.18)' }, z: 3 },
        { name: 'L1超大净', type: 'line', xAxisIndex: 4, yAxisIndex: 6, data: l1SuperNetSplit.negative, showSymbol: false, lineStyle: { color: '#16A34A', width: 1.2 }, areaStyle: { color: 'rgba(22,163,74,0.18)' }, z: 3 },

        { name: 'L2净流比', type: 'line', xAxisIndex: 5, yAxisIndex: 7, data: l2NetRatio, showSymbol: false, lineStyle: { color: '#6D28D9', width: 1.7 }, itemStyle: { color: '#6D28D9' }, z: 4, markLine: anchorMarkLine },
        { name: 'L1净流比', type: 'line', xAxisIndex: 5, yAxisIndex: 7, data: l1NetRatio, showSymbol: false, lineStyle: { color: '#DC2626', width: 1.6 }, itemStyle: { color: '#DC2626' }, z: 4 },

        { name: 'L2主力累计净', type: 'line', xAxisIndex: 6, yAxisIndex: 8, data: l2MainCum, showSymbol: false, lineStyle: { color: '#6D28D9', width: 1.3 }, z: 4, markLine: anchorMarkLine },
        { name: '_L2主力累计净正', type: 'line', xAxisIndex: 6, yAxisIndex: 8, data: l2MainCumSplit.positive, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(109,40,217,0.25)' }, emphasis: { disabled: true }, z: 2 },
        { name: '_L2主力累计净负', type: 'line', xAxisIndex: 6, yAxisIndex: 8, data: l2MainCumSplit.negative, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(180,83,9,0.25)' }, emphasis: { disabled: true }, z: 2 },

        { name: 'L1主力累计净', type: 'line', xAxisIndex: 7, yAxisIndex: 9, data: l1MainCum, showSymbol: false, lineStyle: { color: '#DC2626', width: 1.3 }, z: 4, markLine: anchorMarkLine },
        { name: '_L1主力累计净正', type: 'line', xAxisIndex: 7, yAxisIndex: 9, data: l1MainCumSplit.positive, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(220,38,38,0.18)' }, emphasis: { disabled: true }, z: 2 },
        { name: '_L1主力累计净负', type: 'line', xAxisIndex: 7, yAxisIndex: 9, data: l1MainCumSplit.negative, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(22,163,74,0.18)' }, emphasis: { disabled: true }, z: 2 },

        { name: 'L2超大累计净', type: 'line', xAxisIndex: 8, yAxisIndex: 10, data: l2SuperCum, showSymbol: false, lineStyle: { color: '#6D28D9', width: 1.3 }, z: 4, markLine: anchorMarkLine },
        { name: '_L2超大累计净正', type: 'line', xAxisIndex: 8, yAxisIndex: 10, data: l2SuperCumSplit.positive, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(109,40,217,0.25)' }, emphasis: { disabled: true }, z: 2 },
        { name: '_L2超大累计净负', type: 'line', xAxisIndex: 8, yAxisIndex: 10, data: l2SuperCumSplit.negative, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(180,83,9,0.25)' }, emphasis: { disabled: true }, z: 2 },

        { name: 'L1超大累计净', type: 'line', xAxisIndex: 9, yAxisIndex: 11, data: l1SuperCum, showSymbol: false, lineStyle: { color: '#DC2626', width: 1.3 }, z: 4, markLine: anchorMarkLine },
        { name: '_L1超大累计净正', type: 'line', xAxisIndex: 9, yAxisIndex: 11, data: l1SuperCumSplit.positive, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(220,38,38,0.18)' }, emphasis: { disabled: true }, z: 2 },
        { name: '_L1超大累计净负', type: 'line', xAxisIndex: 9, yAxisIndex: 11, data: l1SuperCumSplit.negative, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0, width: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: 'rgba(22,163,74,0.18)' }, emphasis: { disabled: true }, z: 2 },
      ],
      graphic:
        !anchorModeEnabled || anchorIndex < 0
          ? [
              {
                type: 'text',
                left: '50%',
                top: '68%',
                z: 100,
                style: {
                  text: '请先开启锚点累计模式并点选K线',
                  fill: '#64748b',
                  font: '12px sans-serif',
                  textAlign: 'center',
                },
              },
              {
                type: 'text',
                left: '50%',
                top: '75%',
                z: 100,
                style: {
                  text: '请先开启锚点累计模式并点选K线',
                  fill: '#64748b',
                  font: '12px sans-serif',
                  textAlign: 'center',
                },
              },
              {
                type: 'text',
                left: '50%',
                top: '82%',
                z: 100,
                style: {
                  text: '请先开启锚点累计模式并点选K线',
                  fill: '#64748b',
                  font: '12px sans-serif',
                  textAlign: 'center',
                },
              },
              {
                type: 'text',
                left: '50%',
                top: '89%',
                z: 100,
                style: {
                  text: '请先开启锚点累计模式并点选K线',
                  fill: '#64748b',
                  font: '12px sans-serif',
                  textAlign: 'center',
                },
              },
            ]
          : [],
    };
  }, [viewState, zoomRange, anchorModeEnabled, anchorTs]);

  const anchorText = useMemo(() => {
    if (anchorTs === null) return '未设置';
    return formatLocalDateTime(new Date(anchorTs));
  }, [anchorTs]);

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200 p-4 md:p-6">
      <div className="max-w-[1600px] mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <a href="/" className="inline-flex items-center gap-2 text-slate-300 hover:text-white text-sm">
            <ArrowLeft className="w-4 h-4" />
            返回首页
          </a>
          <div className="text-xs text-slate-400">沙盒 / L2 复盘</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 md:p-4 flex flex-wrap items-end gap-3">
          <div className="w-full grid grid-cols-1 md:grid-cols-5 gap-3 text-sm">
            <label className="flex flex-col gap-1">
              <span className="text-slate-400 text-xs">股票代码（股票池内）</span>
              <input
                list="sandbox-pool-options"
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-100"
                placeholder="如 sh603629"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-400 text-xs">开始日期</span>
              <input
                type="date"
                min={SANDBOX_MIN_DATE}
                max={SANDBOX_MAX_DATE}
                value={startDateInput}
                onChange={(e) => setStartDateInput(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-100"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-400 text-xs">结束日期</span>
              <input
                type="date"
                min={SANDBOX_MIN_DATE}
                max={SANDBOX_MAX_DATE}
                value={endDateInput}
                onChange={(e) => setEndDateInput(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-100"
              />
            </label>
            <div className="flex flex-col gap-1">
              <span className="text-slate-400 text-xs">股票池</span>
              <div className="px-2 py-1 bg-slate-950 border border-slate-700 rounded text-slate-200">
                {poolTotal > 0 ? `${poolTotal} 只` : '--'}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-slate-400 text-xs">操作</span>
              <button
                onClick={handleExecuteQuery}
                disabled={loading}
                className={`px-3 py-1 rounded border ${
                  loading
                    ? 'bg-slate-800 border-slate-700 text-slate-500 cursor-not-allowed'
                    : 'bg-cyan-700/30 border-cyan-500 text-cyan-200 hover:bg-cyan-700/40'
                }`}
              >
                执行查询
              </button>
            </div>
          </div>
          <datalist id="sandbox-pool-options">
            {poolItems.map((item) => (
              <option key={item.symbol} value={item.symbol}>
                {item.name}
              </option>
            ))}
          </datalist>
          <div className="w-full flex flex-wrap items-center gap-3 text-sm">
            <span className="text-slate-300">Sandbox 复盘：</span>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-slate-200">
              股票 {querySymbol} {activePoolItem ? `(${activePoolItem.name})` : ''}
            </span>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-slate-200">
              区间 {queryStartDate} ~ {queryEndDate}
            </span>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-cyan-300">数据源 sandbox API</span>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-emerald-300">当前粒度 {viewState.granularity}</span>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-violet-300">当前窗口约 {viewState.visibleDays.toFixed(1)} 天 / {viewState.visibleCount} 点</span>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-amber-300">接口返回 {rawData.length} 条</span>
            {poolAsOfDate && (
              <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-slate-300">
                池子快照 {poolAsOfDate}
              </span>
            )}
            {activePoolItem && (
              <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-slate-300">
                市值 {formatMarketCapYi(activePoolItem.market_cap)}
              </span>
            )}
            {loading && (
              <span className="inline-flex items-center gap-1 text-slate-400">
                <RefreshCw className="w-3 h-3 animate-spin" />
                数据加载中
              </span>
            )}
          </div>
          <div className="w-full text-xs text-slate-500">
            数据范围：{rawRangeText}（查询窗口仅支持 {SANDBOX_MIN_DATE} ~ {SANDBOX_MAX_DATE}）
          </div>
          <div className="w-full flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-400">窗口快捷：</span>
            {PRESET_OPTIONS.map((preset) => (
              <button
                key={preset.key}
                onClick={() => handleSelectPreset(preset.key, preset.days)}
                className={`px-2 py-1 rounded border ${activePreset === preset.key ? 'bg-cyan-700/40 border-cyan-500 text-cyan-200' : 'bg-slate-950 border-slate-700 text-slate-300'}`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="w-full flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-400">粒度切换：</span>
            {GRANULARITY_OPTIONS.map((option) => (
              <button
                key={option.key}
                onClick={() => setGranularityMode(option.key)}
                className={`px-2 py-1 rounded border ${granularityMode === option.key ? 'bg-violet-700/40 border-violet-500 text-violet-200' : 'bg-slate-950 border-slate-700 text-slate-300'}`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="w-full text-xs text-slate-500">
            自动规则：1日=5m，3/5日=15m，20日=60m，60日/全部=1d；拖动滑块时仅“自动”模式会动态换粒度。
          </div>
          <div className="w-full flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-400">锚点累计：</span>
            <button
              onClick={() => setAnchorModeEnabled((prev) => !prev)}
              className={`px-2 py-1 rounded border ${anchorModeEnabled ? 'bg-amber-700/40 border-amber-500 text-amber-200' : 'bg-slate-950 border-slate-700 text-slate-300'}`}
            >
              {anchorModeEnabled ? '已开启（点K线设锚点）' : '未开启'}
            </button>
            <button
              onClick={() => setAnchorTs(null)}
              disabled={anchorTs === null}
              className={`px-2 py-1 rounded border ${anchorTs === null ? 'bg-slate-900 border-slate-800 text-slate-600 cursor-not-allowed' : 'bg-slate-950 border-slate-700 text-slate-300'}`}
            >
              清除锚点
            </button>
            <span className="px-2 py-1 rounded bg-slate-950 border border-slate-700 text-slate-300">
              当前锚点 {anchorText}
            </span>
          </div>
        </div>

        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}

        {!error && emptyMessage && (
          <div className="bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300">
            {emptyMessage}
          </div>
        )}

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-2">
          {!error && viewState.bars.length > 0 ? (
            <ReactEChartsCore
              echarts={echarts}
              option={option}
              style={{ width: '100%', height: '276vh' }}
              onEvents={{ datazoom: handleDataZoom, click: handleChartClick }}
            />
          ) : (
            <div className="h-[70vh] flex items-center justify-center text-slate-500 text-sm">
              {error || emptyMessage || '暂无可视化数据。'}
            </div>
          )}
        </div>

        {!error && correlationData.points.length > 0 && (
          <>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 md:p-4">
              <div className="text-sm text-slate-200 mb-3">相关性统计结论（5分钟口径，活跃阈值30%）</div>
              {correlationStats.concurrentCount === 0 && (
                <div className="text-xs text-amber-300 mb-3">
                  当前样本不足。请先重跑含 total_amount 的 sandbox ETL（1-2月真实逐笔），再查看相关性统计。
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="text-slate-400 mb-1">同期解释力（净流入 vs 当期涨跌幅）</div>
                  <div className="text-slate-100">L1: {correlationStats.l1Concurrent?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-100">L2: {correlationStats.l2Concurrent?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-500 mt-1">样本: {correlationStats.concurrentCount}</div>
                </div>
                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="text-slate-400 mb-1">未来预测力（净流入 vs 下一根涨跌幅）</div>
                  <div className="text-slate-100">L1: {correlationStats.l1Lead?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-100">L2: {correlationStats.l2Lead?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-500 mt-1">样本: {correlationStats.leadCount}</div>
                </div>
                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="text-slate-400 mb-1">高活跃过滤（L2活跃度&gt;30%）</div>
                  <div className="text-slate-100">相关系数: {correlationStats.l2Conditional?.toFixed(4) ?? '--'}</div>
                  <div className="text-slate-500 mt-1">
                    样本: {correlationStats.highActivityCount} / {correlationStats.leadCount} ({correlationStats.highActivityRatio.toFixed(1)}%)
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <ReactEChartsCore
                  echarts={echarts}
                  option={scatterOptionL1}
                  style={{ width: '100%', height: '320px' }}
                />
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <ReactEChartsCore
                  echarts={echarts}
                  option={scatterOptionL2}
                  style={{ width: '100%', height: '320px' }}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default SandboxReviewPage;
