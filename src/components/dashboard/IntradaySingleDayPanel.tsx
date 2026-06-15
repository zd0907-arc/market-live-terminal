import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, ComposedChart, ReferenceLine } from 'recharts';

import { TickData, SearchResult, CapitalRatioData, CumulativeCapitalData, DashboardSourceMeta, IntradayFusionData } from '../../types';
import * as StockService from '../../services/stockService';
import { buildIntradaySlots, DEFAULT_INTRADAY_AXIS_TICKS, inferIntradayStepFromTimes } from '../../utils/intradayTimeAxis';
import FundsBattleSection from './FundsBattleSection';

interface IntradaySingleDayPanelProps {
  activeStock: SearchResult | null;
  configVersion?: number;
  focusMode?: 'normal' | 'focus';
  enableRealtime?: boolean;
  selectedDate?: string;
  onSelectedDateChange?: (value: string) => void;
  showDateControls?: boolean;
  showReturnToday?: boolean;
  title?: string;
  chartHeightClassName?: string;
  syncId?: string;
  dateControlSlot?: React.ReactNode;
  previousClose?: number | null;
  quoteDate?: string | null;
}

class PanelErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error('Panel render failed:', error);
  }

  componentDidUpdate(prevProps: { children: React.ReactNode }) {
    if (this.state.hasError && prevProps.children !== this.props.children) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-3 text-sm text-amber-200">
          资金博弈分析模块渲染异常，已自动降级；刷新页面或切换股票后会重试。
        </div>
      );
    }
    return this.props.children;
  }
}

const getChinaNow = () => {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const parts = formatter.formatToParts(now);
  const year = parts.find((p) => p.type === 'year')?.value || '1970';
  const month = parts.find((p) => p.type === 'month')?.value || '01';
  const day = parts.find((p) => p.type === 'day')?.value || '01';
  const hour = parts.find((p) => p.type === 'hour')?.value || '00';
  const minute = parts.find((p) => p.type === 'minute')?.value || '00';
  return {
    date: `${year}-${month}-${day}`,
    hhmm: `${hour}:${minute}`,
    timeNum: Number(hour) * 100 + Number(minute),
    weekday: new Date(`${year}-${month}-${day}T00:00:00+08:00`).getDay(),
  };
};

const shouldPollRealtime = (selectedDate: string) => {
  if (selectedDate) return false;
  const now = getChinaNow();
  const isWeekend = now.weekday === 0 || now.weekday === 6;
  if (isWeekend) return false;
  return now.timeNum >= 915 && now.timeNum <= 1500 && !(now.timeNum >= 1130 && now.timeNum < 1300);
};

type ChartRenderPoint = {
  time: string;
  mainBuyRatio?: number | null;
  mainSellRatio?: number | null;
  mainParticipationRatio?: number | null;
  mainBuyAmount?: number | null;
  mainSellAmount?: number | null;
  mainSellAmountPlot?: number | null;
  superBuyAmount?: number | null;
  superSellAmount?: number | null;
  superSellAmountPlot?: number | null;
  superParticipationRatio?: number | null;
  closePrice?: number | null;
  priceChangePct?: number | null;
};

type CumulativeRenderPoint = {
  time: string;
  cumMainBuy: number | null;
  cumMainSell: number | null;
  cumNetInflow: number | null;
  cumSuperNetInflow: number | null;
  cumSuperBuy: number | null;
  cumSuperSell: number | null;
};

const toFiniteNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const calcPriceChangePct = (price: unknown, previousClose: number | null | undefined) => {
  const close = toFiniteNumber(price);
  const base = toFiniteNumber(previousClose);
  if (close === null || base === null || base <= 0) return null;
  return ((close - base) / base) * 100;
};

const buildPctDomain = (values: Array<number | null | undefined>) => {
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

const fillContinuousFieldsBetweenKnown = <T extends Record<string, unknown>>(rows: T[], fields: string[]): T[] => {
  const next = rows.map((row) => ({ ...row }));
  fields.forEach((field) => {
    const validIndexes = next
      .map((row, index) => (toFiniteNumber(row[field]) !== null ? index : -1))
      .filter((index) => index >= 0);
    const firstValidIndex = validIndexes[0] ?? -1;
    const lastValidIndex = validIndexes[validIndexes.length - 1] ?? -1;
    if (firstValidIndex < 0 || lastValidIndex <= firstValidIndex) return;

    let lastValue = next[firstValidIndex][field];
    for (let index = firstValidIndex + 1; index < lastValidIndex; index += 1) {
      if (toFiniteNumber(next[index][field]) !== null) {
        lastValue = next[index][field];
      } else {
        next[index][field] = lastValue;
      }
    }
  });
  return next as T[];
};

const alignChartDataToTradingDay = (
  rows: CapitalRatioData[],
  granularity?: string | null,
  previousClose?: number | null,
): ChartRenderPoint[] => {
  if (!rows.length) return [];
  const slots = buildIntradaySlots(inferIntradayStepFromTimes(rows.map((row) => row.time), granularity));
  const byTime = new Map(rows.map((row) => [row.time, row]));
  const aligned = slots.map((time) => {
    const row = byTime.get(time);
    if (row) {
      return {
        ...row,
        closePrice: toFiniteNumber(row.closePrice),
        priceChangePct: calcPriceChangePct(row.closePrice, previousClose),
      };
    }
    return {
      time,
      mainBuyRatio: null,
      mainSellRatio: null,
      mainParticipationRatio: null,
      mainBuyAmount: null,
      mainSellAmount: null,
      mainSellAmountPlot: null,
      superBuyAmount: null,
      superSellAmount: null,
      superSellAmountPlot: null,
      superParticipationRatio: null,
      closePrice: null,
      priceChangePct: null,
    };
  });
  return fillContinuousFieldsBetweenKnown(aligned, ['closePrice', 'priceChangePct']);
};

const alignCumulativeDataToTradingDay = (rows: CumulativeCapitalData[], granularity?: string | null): CumulativeRenderPoint[] => {
  if (!rows.length) return [];
  const slots = buildIntradaySlots(inferIntradayStepFromTimes(rows.map((row) => row.time), granularity));
  const byTime = new Map(rows.map((row) => [row.time, row]));
  const aligned = slots.map((time) => byTime.get(time) || {
    time,
    cumMainBuy: null,
    cumMainSell: null,
    cumNetInflow: null,
    cumSuperNetInflow: null,
    cumSuperBuy: null,
    cumSuperSell: null,
  });
  return fillContinuousFieldsBetweenKnown(aligned, [
    'cumMainBuy',
    'cumMainSell',
    'cumNetInflow',
    'cumSuperNetInflow',
    'cumSuperBuy',
    'cumSuperSell',
  ]);
};

const getProvisionalMeta = (selectedDate: string): DashboardSourceMeta => {
  const now = getChinaNow();
  const isWeekend = now.weekday === 0 || now.weekday === 6;
  const isTradeDay = !isWeekend;

  if (selectedDate) {
    const provisionalStatus = isTradeDay
      ? (now.timeNum >= 915 && now.timeNum <= 1500
        ? (now.timeNum >= 1130 && now.timeNum < 1300 ? 'lunch_break' : 'trading')
        : 'post_close')
      : 'closed_day';
    const provisionalStatusLabel = isTradeDay
      ? (now.timeNum >= 915 && now.timeNum <= 1500
        ? (now.timeNum >= 1130 && now.timeNum < 1300 ? '午间休市' : '盘中交易')
        : '盘后复盘')
      : '休盘日';
    return {
      display_date: selectedDate,
      market_status: provisionalStatus,
      market_status_label: provisionalStatusLabel,
      view_mode: 'manual_date',
      view_mode_label: '手动查看指定日期数据',
      default_display_scope_label: '手动查看指定日期数据',
    };
  }

  if (!isTradeDay) {
    return {
      display_date: now.date,
      natural_today: now.date,
      market_status: 'closed_day',
      market_status_label: '休盘日',
      default_display_scope: 'previous_trade_day',
      default_display_scope_label: '默认展示上一交易日数据',
      view_mode: 'previous_trade_day',
      view_mode_label: '默认展示上一交易日数据',
    };
  }

  if (now.timeNum < 915) {
    return {
      display_date: now.date,
      natural_today: now.date,
      market_status: 'post_close',
      market_status_label: '盘后复盘',
      default_display_scope: 'previous_trade_day',
      default_display_scope_label: '默认展示上一交易日复盘数据',
      view_mode: 'previous_trade_day',
      view_mode_label: '默认展示上一交易日复盘数据',
    };
  }

  if (now.timeNum >= 915 && now.timeNum < 1130) {
    return {
      display_date: now.date,
      natural_today: now.date,
      market_status: 'trading',
      market_status_label: '盘中交易',
      default_display_scope: 'today',
      default_display_scope_label: '默认展示今日实时数据',
      view_mode: 'today_realtime',
      view_mode_label: '默认展示今日实时数据',
    };
  }

  if (now.timeNum >= 1130 && now.timeNum < 1300) {
    return {
      display_date: now.date,
      natural_today: now.date,
      market_status: 'lunch_break',
      market_status_label: '午间休市',
      default_display_scope: 'today',
      default_display_scope_label: '默认展示今日已采集数据',
      view_mode: 'today_midday_review',
      view_mode_label: '默认展示今日已采集数据',
    };
  }

  if (now.timeNum >= 1300 && now.timeNum <= 1500) {
    return {
      display_date: now.date,
      natural_today: now.date,
      market_status: 'trading',
      market_status_label: '盘中交易',
      default_display_scope: 'today',
      default_display_scope_label: '默认展示今日实时数据',
      view_mode: 'today_realtime',
      view_mode_label: '默认展示今日实时数据',
    };
  }

  return {
    display_date: now.date,
    natural_today: now.date,
    market_status: 'post_close',
    market_status_label: '盘后复盘',
    default_display_scope: 'today',
    default_display_scope_label: '默认展示今日收盘后数据',
    view_mode: 'today_postclose_review',
    view_mode_label: '默认展示今日收盘后数据',
  };
};

const IntradaySingleDayPanel: React.FC<IntradaySingleDayPanelProps> = ({
  activeStock,
  configVersion,
  focusMode = 'normal',
  enableRealtime = true,
  selectedDate,
  onSelectedDateChange,
  showDateControls = true,
  showReturnToday = true,
  title,
  chartHeightClassName = 'h-[800px] md:h-[500px]',
  syncId = 'capitalFlow',
  dateControlSlot,
  previousClose,
  quoteDate,
}) => {
  const controlledDate = selectedDate !== undefined;
  const [internalSelectedDate, setInternalSelectedDate] = useState('');
  const selectedDateValue = controlledDate ? selectedDate || '' : internalSelectedDate;
  const setSelectedDateValue = useCallback((value: string) => {
    if (controlledDate) {
      onSelectedDateChange?.(value);
      return;
    }
    setInternalSelectedDate(value);
  }, [controlledDate, onSelectedDateChange]);

  const [displayTicks, setDisplayTicks] = useState<TickData[]>([]);
  const [chartData, setChartData] = useState<CapitalRatioData[]>([]);
  const [cumulativeData, setCumulativeData] = useState<CumulativeCapitalData[]>([]);
  const isFetchingRef = useRef(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [displayDate, setDisplayDate] = useState('');
  const [sourceMeta, setSourceMeta] = useState<DashboardSourceMeta>({});
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [fusionData, setFusionData] = useState<IntradayFusionData | null>(null);
  const [isLoadingFusion, setIsLoadingFusion] = useState(false);
  const [forceRefresh, setForceRefresh] = useState(0);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (!controlledDate) setInternalSelectedDate('');
  }, [activeStock?.symbol, controlledDate]);

  useEffect(() => {
    setDisplayTicks([]);
    setChartData([]);
    setCumulativeData([]);
    setSourceMeta({});
    setFusionData(null);
  }, [activeStock, selectedDateValue]);

  useEffect(() => {
    if (!activeStock) return;

    let isMounted = true;
    const heartbeatMode = focusMode === 'focus' ? 'focus' : 'warm';
    const enableRealtimeTracking = enableRealtime && !selectedDateValue && shouldPollRealtime(selectedDateValue);
    let heartbeatInterval: ReturnType<typeof setInterval> | null = null;

    if (enableRealtimeTracking) {
      StockService.sendHeartbeat(activeStock.symbol, heartbeatMode);
      heartbeatInterval = setInterval(() => {
        if (isMounted) StockService.sendHeartbeat(activeStock.symbol, heartbeatMode);
      }, 10000);
    }

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const fetchData = async () => {
      if (!isMounted || isFetchingRef.current) return;
      const requestSeq = ++requestSeqRef.current;
      isFetchingRef.current = true;
      if (isMounted) setIsLoadingDashboard(true);
      if (chartData.length > 0) setIsRefreshing(true);
      try {
        const data = await StockService.fetchRealtimeDashboard(activeStock.symbol, selectedDateValue);

        if (!isMounted || requestSeq !== requestSeqRef.current) return;

        if (data) {
          const processedChart = (data.chart_data || []).map((d: any) => ({
            ...d,
            mainSellAmountPlot: d.mainSellAmount ? -d.mainSellAmount : 0,
            mainBuyAmount: d.mainBuyAmount || 0,
            superSellAmountPlot: d.superSellAmount ? -d.superSellAmount : 0,
            superBuyAmount: d.superBuyAmount || 0,
            closePrice: toFiniteNumber(d.closePrice),
          }));
          setChartData(processedChart);
          setCumulativeData(data.cumulative_data || []);
          setSourceMeta({
            natural_today: data.natural_today,
            source: data.source,
            is_finalized: data.is_finalized,
            bucket_granularity: data.bucket_granularity,
            display_date: data.display_date,
            market_status: data.market_status,
            market_status_label: data.market_status_label,
            default_display_date: data.default_display_date,
            default_display_scope: data.default_display_scope,
            default_display_scope_label: data.default_display_scope_label,
            view_mode: data.view_mode,
            view_mode_label: data.view_mode_label,
            is_realtime_session: data.is_realtime_session,
          });

          if (data.latest_ticks && Array.isArray(data.latest_ticks)) {
            const ticks = data.latest_ticks.map((t: any) => ({
              ...t,
              color: t.type === 'buy' ? 'text-red-500' : (t.type === 'sell' ? 'text-green-500' : 'text-slate-400'),
            }));
            setDisplayTicks(ticks);
          }

          if (data.display_date) setDisplayDate(data.display_date);
          if (
            !controlledDate
            && !selectedDateValue
            && data.default_display_scope === 'previous_trade_day'
            && data.default_display_date
          ) {
            setSelectedDateValue(data.default_display_date);
          }
          if (intervalId && data.market_status !== 'trading') {
            clearInterval(intervalId);
            intervalId = null;
          }
        } else if (selectedDateValue) {
          setChartData([]);
          setCumulativeData([]);
          setDisplayTicks([]);
          setDisplayDate(selectedDateValue);
          setSourceMeta({});
        }
      } catch (err) {
        console.warn('Dashboard update failed', err);
      } finally {
        isFetchingRef.current = false;
        if (isMounted) {
          setIsRefreshing(false);
          setIsLoadingDashboard(false);
        }
      }
    };

    fetchData();

    if (enableRealtimeTracking && shouldPollRealtime(selectedDateValue)) {
      const intervalMs = focusMode === 'focus' ? 5000 : 30000;
      intervalId = setInterval(fetchData, intervalMs);
    }

    return () => {
      isMounted = false;
      isFetchingRef.current = false;
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      if (intervalId) clearInterval(intervalId);
    };
  }, [activeStock, forceRefresh, selectedDateValue, focusMode, enableRealtime, controlledDate, setSelectedDateValue]);

  useEffect(() => {
    if (!activeStock) return;

    let isMounted = true;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const fetchFusion = async () => {
      if (!isMounted) return;
      setIsLoadingFusion(true);
      try {
        const data = await StockService.fetchIntradayFusion(activeStock.symbol, selectedDateValue);
        if (!isMounted) return;
        setFusionData(data);
      } catch (err) {
        console.warn('Intraday fusion update failed', err);
      } finally {
        if (isMounted) setIsLoadingFusion(false);
      }
    };

    fetchFusion();

    if (enableRealtime && !selectedDateValue && shouldPollRealtime(selectedDateValue)) {
      const intervalMs = focusMode === 'focus' ? 5000 : 30000;
      intervalId = setInterval(fetchFusion, intervalMs);
    }

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [activeStock, selectedDateValue, focusMode, enableRealtime]);

  useEffect(() => {
    if (configVersion) setForceRefresh((prev) => prev + 1);
  }, [configVersion]);

  useEffect(() => {
    if (!activeStock) return;
    const provisional = getProvisionalMeta(selectedDateValue);
    setDisplayDate(provisional.display_date || '');
    setSourceMeta((prev) => ({
      ...provisional,
      source: prev.source,
      bucket_granularity: prev.bucket_granularity,
      is_finalized: prev.is_finalized,
    }));
    setIsLoadingDashboard(true);
  }, [activeStock, selectedDateValue]);

  const gradientOffset = () => {
    if (cumulativeData.length === 0) return 0;
    const dataMax = Math.max(...cumulativeData.map((i) => i.cumNetInflow));
    const dataMin = Math.min(...cumulativeData.map((i) => i.cumNetInflow));

    if (dataMax <= 0) return 0;
    if (dataMin >= 0) return 1;
    return dataMax / (dataMax - dataMin);
  };

  const getStatusBadge = () => {
    const effectiveMeta = sourceMeta.market_status ? sourceMeta : getProvisionalMeta(selectedDateValue);
    const effectiveDisplayDate = displayDate || effectiveMeta.display_date || '';

    if (!effectiveDisplayDate) {
      return {
        className: 'text-[10px] font-medium text-slate-500 bg-slate-800/60 px-1.5 py-0.5 rounded border border-slate-700/60',
        text: '检测中',
      };
    }

    if (effectiveMeta.view_mode === 'manual_date') {
      return {
        className: 'text-[10px] font-medium text-yellow-400 bg-yellow-500/10 px-1.5 py-0.5 rounded border border-yellow-500/20',
        text: '回溯',
      };
    }

    const marketStatus = effectiveMeta.market_status;
    const marketLabel = effectiveMeta.market_status_label || '状态未知';

    if (marketStatus === 'trading') {
      return {
        className: 'text-[10px] font-medium text-green-400 bg-green-500/10 px-1.5 py-0.5 rounded border border-green-500/20',
        text: marketLabel,
      };
    }

    if (marketStatus === 'lunch_break') {
      return {
        className: 'text-[10px] font-medium text-orange-400 bg-orange-500/10 px-1.5 py-0.5 rounded border border-orange-500/20',
        text: marketLabel,
      };
    }

    if (marketStatus === 'post_close') {
      return {
        className: 'text-[10px] font-medium text-sky-400 bg-sky-500/10 px-1.5 py-0.5 rounded border border-sky-500/20',
        text: marketLabel,
      };
    }

    return {
      className: 'text-[10px] font-medium text-slate-300 bg-slate-800/70 px-1.5 py-0.5 rounded border border-slate-700/60',
      text: marketLabel,
    };
  };

  const getUpdateText = () => {
    const hasLoadedData = chartData.length > 0 || cumulativeData.length > 0 || displayTicks.length > 0;
    if (isLoadingDashboard) return hasLoadedData ? '刷新中' : '加载中';
    return '';
  };

  const priceReference = useMemo(() => {
    const base = toFiniteNumber(previousClose);
    if (base === null || base <= 0) return null;
    if (displayDate && quoteDate && displayDate !== quoteDate) return null;
    return base;
  }, [displayDate, previousClose, quoteDate]);
  const chartTimelineData = useMemo(
    () => alignChartDataToTradingDay(chartData, sourceMeta.bucket_granularity, priceReference),
    [chartData, priceReference, sourceMeta.bucket_granularity],
  );
  const pricePctDomain = useMemo(
    () => buildPctDomain(chartTimelineData.map((row) => row.priceChangePct)),
    [chartTimelineData],
  );
  const cumulativeTimelineData = useMemo(
    () => alignCumulativeDataToTradingDay(cumulativeData, sourceMeta.bucket_granularity),
    [cumulativeData, sourceMeta.bucket_granularity],
  );

  if (!activeStock) {
    return <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-6 text-center text-sm text-slate-500">请选择股票查看单日走势。</div>;
  }

  const statusBadge = getStatusBadge();
  const updateText = getUpdateText();
  const off = gradientOffset();
  const defaultDateControls = showDateControls ? (
    <div className="flex items-center gap-2">
      <input
        type="date"
        value={selectedDateValue}
        onChange={(e) => setSelectedDateValue(e.target.value)}
        className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:border-blue-500"
      />
      {showReturnToday && selectedDateValue ? (
        <button
          type="button"
          onClick={() => setSelectedDateValue('')}
          className="rounded border border-blue-600/30 bg-blue-600/20 px-2 py-1 text-xs text-blue-400 transition-colors hover:bg-blue-600/40"
        >
          返回今日
        </button>
      ) : null}
    </div>
  ) : null;

  return (
    <div className="space-y-2">
      <div className="relative rounded-lg bg-slate-900/80 p-2 shadow-lg">
        <div className="mb-1.5 flex flex-nowrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-nowrap items-center gap-1.5">
            <h3 className="flex min-w-0 items-center gap-1.5 text-sm font-bold text-white">
              <TrendingUp className="h-3.5 w-3.5 shrink-0 text-blue-400" />
              <span className="truncate">{title || (enableRealtime ? '主力动态 (实时)' : '主力动态（单日）')}</span>
              {isRefreshing ? (
                <span className={`text-[9px] font-normal ${focusMode === 'focus' ? 'text-red-300' : 'text-sky-300'} animate-pulse`}>
                  刷新
                </span>
              ) : null}
            </h3>
            {dateControlSlot !== undefined ? dateControlSlot : defaultDateControls}
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <span className={statusBadge.className}>{statusBadge.text}</span>
            {updateText ? <span className="text-[10px] text-slate-500">{updateText}</span> : null}
          </div>
        </div>

        <div className="w-full">
          <div className={`flex flex-col gap-2 md:grid md:grid-rows-2 md:gap-1.5 ${chartHeightClassName}`}>
            <div className="relative h-full w-full">
              <div className="absolute left-10 top-1 z-10 bg-slate-900/70 px-1 text-[9px] font-semibold text-slate-500">
                分时博弈强度
              </div>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartTimelineData} syncId={syncId} margin={{ top: 8, right: 2, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="time"
                      xAxisId="0"
                      stroke="#64748b"
                      tick={{ fontSize: 9 }}
                      ticks={DEFAULT_INTRADAY_AXIS_TICKS}
                      interval="preserveStartEnd"
                      hide
                    />
                    <XAxis dataKey="time" xAxisId="1" hide />
                    <YAxis yAxisId="amount" width={34} stroke="#94a3b8" tick={{ fontSize: 9 }} tickFormatter={(val) => (Math.abs(val) / 10000).toFixed(0)} />
                    <YAxis yAxisId="ratio" orientation="right" stroke="#cbd5e1" tick={{ fontSize: 10 }} unit="%" domain={[0, 100]} hide />
                    <YAxis
                      yAxisId="price"
                      orientation="right"
                      width={34}
                      domain={pricePctDomain}
                      stroke="#facc15"
                      tick={{ fontSize: 9 }}
                      tickFormatter={(val) => `${Number(val).toFixed(1)}%`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                      itemStyle={{ fontSize: 10 }}
                      formatter={(val: number | null | undefined, name: string, item: any) => {
                        if (val === null || val === undefined || Number.isNaN(Number(val))) return ['--', name];
                        const num = Number(val);
                        if (name.includes('主力') || name.includes('超大单')) {
                          if (name.includes('占比') || name.includes('参与度')) return [num + '%', name];
                          return [(Math.abs(num) / 10000).toFixed(1) + '万', name];
                        }
                        if (name === '股价') {
                          const price = toFiniteNumber(item?.payload?.closePrice);
                          return [`${num.toFixed(2)}%${price !== null ? ` / ${price.toFixed(2)}` : ''}`, name];
                        }
                        return [num, name];
                      }}
                    />
                    <Bar xAxisId="0" yAxisId="amount" dataKey="mainBuyAmount" name="主力买入" fill="#f87171" barSize={4} fillOpacity={1} />
                    <Bar xAxisId="0" yAxisId="amount" dataKey="mainSellAmountPlot" name="主力卖出" fill="#4ade80" barSize={4} fillOpacity={1} />
                    <Bar xAxisId="1" yAxisId="amount" dataKey="superBuyAmount" name="超大单买入" fill="#9333ea" barSize={4} />
                    <Bar xAxisId="1" yAxisId="amount" dataKey="superSellAmountPlot" name="超大单卖出" fill="#14532d" barSize={4} />
                    <Line yAxisId="ratio" type="monotone" dataKey="mainParticipationRatio" name="主力参与度" stroke="#f8fafc" strokeWidth={1} dot={false} connectNulls strokeOpacity={0.25} animationDuration={500} />
                    <Line yAxisId="ratio" type="monotone" dataKey="superParticipationRatio" name="超大单参与度" stroke="#9333ea" strokeWidth={1} dot={false} connectNulls strokeOpacity={0.25} animationDuration={500} />
                    <ReferenceLine yAxisId="price" y={0} stroke="#facc15" strokeOpacity={0.35} strokeDasharray="3 3" />
                    <Line yAxisId="price" type="monotone" dataKey="priceChangePct" name="股价" stroke="#facc15" strokeWidth={1.4} dot={false} connectNulls animationDuration={500} />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : isLoadingDashboard ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-slate-500">
                  <span>正在获取分时数据...</span>
                  <span className="text-xs text-slate-600">已先判定市场状态，图表数据仍在加载</span>
                </div>
              ) : displayDate ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-slate-500">
                  <span>{sourceMeta.view_mode === 'manual_date' ? '当前回溯日期无本地 Tick 数据' : '暂无交易数据'}</span>
                  {sourceMeta.view_mode === 'manual_date' ? <span className="text-xs text-slate-600">本地数据库未在此日期保存该股票的明细记录</span> : null}
                </div>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">加载中...</div>
              )}
            </div>

            <div className="relative h-full w-full">
              <div className="absolute left-10 top-1 z-10 bg-slate-900/70 px-1 text-[9px] font-semibold text-slate-500">
                主力累计资金 (万元)
              </div>
              {cumulativeData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={cumulativeTimelineData} syncId={syncId} margin={{ top: 8, right: 2, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id={`${syncId}-splitColor`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset={off} stopColor="#ef4444" stopOpacity={0.3} />
                        <stop offset={off} stopColor="#22c55e" stopOpacity={0.3} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="time"
                      stroke="#64748b"
                      tick={{ fontSize: 9 }}
                      ticks={DEFAULT_INTRADAY_AXIS_TICKS}
                      interval="preserveStartEnd"
                    />
                    <YAxis yAxisId="net" width={34} stroke="#a78bfa" tick={{ fontSize: 9 }} tickFormatter={(val) => (val / 10000).toFixed(0)} domain={['auto', 'auto']} />
                    <YAxis yAxisId="total" orientation="right" stroke="#64748b" tick={{ fontSize: 12 }} tickFormatter={(val) => (val / 10000).toFixed(0)} domain={['auto', 'auto']} hide />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                      itemStyle={{ fontSize: 10 }}
                      formatter={(val: number | null | undefined, name: string) => {
                        if (val === null || val === undefined || Number.isNaN(Number(val))) return ['--', name];
                        const v = (Number(val) / 10000).toFixed(1) + '万';
                        return [v, name];
                      }}
                    />
                    <Area yAxisId="net" type="monotone" dataKey="cumNetInflow" name="主力净流入" stroke="none" fill={`url(#${syncId}-splitColor)`} connectNulls animationDuration={500} />
                    <Line yAxisId="net" type="monotone" dataKey="cumSuperNetInflow" name="超大单净流入" stroke="#d946ef" strokeWidth={2} dot={false} connectNulls strokeDasharray="5 5" animationDuration={500} />
                    <Line yAxisId="total" type="monotone" dataKey="cumMainBuy" name="主力买入" stroke="#ef4444" strokeWidth={1.5} dot={false} connectNulls strokeOpacity={0.8} animationDuration={500} />
                    <Line yAxisId="total" type="monotone" dataKey="cumMainSell" name="主力卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} connectNulls strokeOpacity={0.8} animationDuration={500} />
                    <Line yAxisId="total" type="monotone" dataKey="cumSuperBuy" name="超大单买入" stroke="#ef4444" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="3 3" strokeOpacity={0.8} animationDuration={500} />
                    <Line yAxisId="total" type="monotone" dataKey="cumSuperSell" name="超大单卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} connectNulls strokeDasharray="3 3" strokeOpacity={0.8} animationDuration={500} />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">计算累计趋势中...</div>
              )}
            </div>
          </div>
        </div>
      </div>

      <PanelErrorBoundary>
        <FundsBattleSection data={fusionData} isLoading={isLoadingFusion} />
      </PanelErrorBoundary>
    </div>
  );
};

export default IntradaySingleDayPanel;
