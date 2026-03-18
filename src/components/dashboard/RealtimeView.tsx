import React, { useState, useEffect, useRef } from 'react';
import { TrendingUp, Layers } from 'lucide-react';
import { LineChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Area, ComposedChart } from 'recharts';
import { TickData, SearchResult, CapitalRatioData, CumulativeCapitalData, DashboardSourceMeta } from '../../types';
import * as StockService from '../../services/stockService';
import SentimentTrend from './SentimentTrend';

interface RealtimeViewProps {
    activeStock: SearchResult | null;
    isTradingHours: () => boolean;
    configVersion?: number;
    focusMode?: 'normal' | 'focus';
}

const RealtimeView: React.FC<RealtimeViewProps> = ({ activeStock, configVersion, focusMode = 'normal' }) => {
    // State
    const [displayTicks, setDisplayTicks] = useState<TickData[]>([]);
    const [chartData, setChartData] = useState<CapitalRatioData[]>([]);
    const [cumulativeData, setCumulativeData] = useState<CumulativeCapitalData[]>([]);
    const isFetchingRef = useRef(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [lastUpdated, setLastUpdated] = useState<string>('');
    const [displayDate, setDisplayDate] = useState<string>('');
    const [selectedDate, setSelectedDate] = useState<string>('');
    const [sourceMeta, setSourceMeta] = useState<DashboardSourceMeta>({});
    const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
    const requestSeqRef = useRef(0);

    // Thresholds (Loaded from Backend)
    const [thresholds, setThresholds] = useState({ large: 200000, superLarge: 1000000 });

    // Load Thresholds on Mount
    const loadThresholds = () => {
        StockService.getAppConfig().then(cfg => {
            setThresholds({
                large: parseFloat(cfg.large_threshold) || 500000,
                superLarge: parseFloat(cfg.super_large_threshold) || 1000000
            });
        });
    };

    useEffect(() => {
        loadThresholds();
    }, []);

    // Data Polling
    const [forceRefresh, setForceRefresh] = useState(0);

    // Reset data on stock change or date change
    useEffect(() => {
        setDisplayTicks([]);
        setChartData([]);
        setCumulativeData([]);
        setLastUpdated('');
        setSourceMeta({});
    }, [activeStock, selectedDate]);

    useEffect(() => {
        if (!activeStock) return;

        let isMounted = true;

        const heartbeatMode = focusMode === 'focus' ? 'focus' : 'warm';
        const enableRealtimeTracking = !selectedDate;

        let heartbeatInterval: any = null;
        if (enableRealtimeTracking) {
            // 策略A：前端发送心跳，激活后端注册表的追踪
            StockService.sendHeartbeat(activeStock.symbol, heartbeatMode);
            heartbeatInterval = setInterval(() => {
                if (isMounted) StockService.sendHeartbeat(activeStock.symbol, heartbeatMode);
            }, 10000); // Send heartbeat every 10 seconds
        }

        let intervalId: any = null;

        const fetchData = async () => {
            if (!isMounted || isFetchingRef.current) return;
            const requestSeq = ++requestSeqRef.current;
            isFetchingRef.current = true;
            if (isMounted) setIsLoadingDashboard(true);
            if (chartData.length > 0) setIsRefreshing(true); // Only show breathing text if we already have data
            try {
                // Fetch pre-calculated dashboard data from backend
                const data = await StockService.fetchRealtimeDashboard(activeStock.symbol, selectedDate);

                if (!isMounted || requestSeq !== requestSeqRef.current) {
                    return;
                }

                if (data) {
                    // Update Chart Data (Full Series)
                    const processedChart = (data.chart_data || []).map((d: any) => ({
                        ...d,
                        mainSellAmountPlot: d.mainSellAmount ? -d.mainSellAmount : 0,
                        mainBuyAmount: d.mainBuyAmount || 0,
                        superSellAmountPlot: d.superSellAmount ? -d.superSellAmount : 0,
                        superBuyAmount: d.superBuyAmount || 0,
                        closePrice: d.closePrice || 0
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

                    // Update Ticks Table (Only latest N)
                    if (data.latest_ticks && Array.isArray(data.latest_ticks)) {
                        const ticks = data.latest_ticks.map((t: any) => ({
                            ...t,
                            color: t.type === 'buy' ? 'text-red-500' : (t.type === 'sell' ? 'text-green-500' : 'text-slate-400')
                        }));
                        setDisplayTicks(ticks);
                    }

                    const now = new Date();
                    setLastUpdated(now.toTimeString().split(' ')[0]); // 24-hour format HH:MM:SS
                    if (data.display_date) {
                        setDisplayDate(data.display_date);
                    }
                } else if (selectedDate) {
                    // Historical empty state clears the canvas; realtime polling keeps stale data visible.
                    setChartData([]);
                    setCumulativeData([]);
                    setDisplayTicks([]);
                    setDisplayDate(selectedDate);
                    setSourceMeta({});
                }
            } catch (err) {
                console.warn("Dashboard update failed", err);
            } finally {
                isFetchingRef.current = false;
                if (isMounted) {
                    setIsRefreshing(false);
                    setIsLoadingDashboard(false);
                }
            }
        };

        fetchData();

        if (enableRealtimeTracking) {
            // Quiet refresh: focus=5s, normal=30s.
            const intervalMs = focusMode === 'focus' ? 5000 : 30000;
            intervalId = setInterval(fetchData, intervalMs);
        }

        return () => {
            isMounted = false;
            // 心跳随组件卸载自动停止
            if (heartbeatInterval) clearInterval(heartbeatInterval);
            if (intervalId) clearInterval(intervalId);
        };
    }, [activeStock, forceRefresh, selectedDate, focusMode]);

    // Callback when config is updated
    useEffect(() => {
        if (configVersion) {
            loadThresholds(); // Reload local thresholds for display/logic if needed
            setForceRefresh(prev => prev + 1); // Trigger re-fetch of dashboard data
        }
    }, [configVersion]);

    // Dynamic Gradient Offset Calculation
    const gradientOffset = () => {
        if (cumulativeData.length === 0) return 0;
        const dataMax = Math.max(...cumulativeData.map((i) => i.cumNetInflow));
        const dataMin = Math.min(...cumulativeData.map((i) => i.cumNetInflow));

        if (dataMax <= 0) {
            return 0;
        }
        if (dataMin >= 0) {
            return 1;
        }

        return dataMax / (dataMax - dataMin);
    };

    const off = gradientOffset();

    const getWeekDay = (dateStr: string) => {
        const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        return days[new Date(dateStr).getDay()];
    };

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
        const year = parts.find(p => p.type === 'year')?.value || '1970';
        const month = parts.find(p => p.type === 'month')?.value || '01';
        const day = parts.find(p => p.type === 'day')?.value || '01';
        const hour = parts.find(p => p.type === 'hour')?.value || '00';
        const minute = parts.find(p => p.type === 'minute')?.value || '00';
        return {
            date: `${year}-${month}-${day}`,
            hhmm: `${hour}:${minute}`,
            timeNum: Number(hour) * 100 + Number(minute),
            weekday: new Date(`${year}-${month}-${day}T00:00:00+08:00`).getDay(),
        };
    };

    const getProvisionalMeta = (): DashboardSourceMeta => {
        const now = getChinaNow();
        const isWeekend = now.weekday === 0 || now.weekday === 6;
        const isTradeDay = !isWeekend;

        if (selectedDate) {
            return {
                display_date: selectedDate,
                market_status: isTradeDay ? (now.timeNum > 1500 ? 'post_close' : (now.timeNum >= 1130 && now.timeNum < 1300 ? 'lunch_break' : (now.timeNum >= 915 && now.timeNum <= 1500 ? 'trading' : 'pre_open'))) : 'closed_day',
                market_status_label: isTradeDay ? (now.timeNum > 1500 ? '盘后复盘' : (now.timeNum >= 1130 && now.timeNum < 1300 ? '午间休市' : (now.timeNum >= 915 && now.timeNum <= 1500 ? '盘中交易' : '盘前未开盘'))) : '休盘日',
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
                market_status: 'pre_open',
                market_status_label: '盘前未开盘',
                default_display_scope: 'previous_trade_day',
                default_display_scope_label: '默认展示上一交易日数据',
                view_mode: 'previous_trade_day',
                view_mode_label: '默认展示上一交易日数据',
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

    useEffect(() => {
        if (!activeStock) return;
        const provisional = getProvisionalMeta();
        setDisplayDate(provisional.display_date || '');
        setSourceMeta(prev => ({
            ...provisional,
            source: prev.source,
            bucket_granularity: prev.bucket_granularity,
            is_finalized: prev.is_finalized,
        }));
        setIsLoadingDashboard(true);
    }, [activeStock, selectedDate]);

    const getStatusBadge = () => {
        const effectiveMeta = sourceMeta.market_status ? sourceMeta : getProvisionalMeta();
        const effectiveDisplayDate = displayDate || effectiveMeta.display_date || '';

        if (!effectiveDisplayDate) {
            return {
                className: 'text-[11px] font-bold text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700',
                text: '⚪ 状态检测中...',
            };
        }

        if (effectiveMeta.view_mode === 'manual_date') {
            return {
                className: 'text-[11px] font-bold text-yellow-500 bg-yellow-500/10 px-2 py-0.5 rounded border border-yellow-500/20',
                text: `🟡 手动回溯: ${effectiveDisplayDate} (${getWeekDay(effectiveDisplayDate)})`,
            };
        }

        const marketStatus = effectiveMeta.market_status;
        const marketLabel = effectiveMeta.market_status_label || '状态未知';
        const scopeLabel = effectiveMeta.default_display_scope_label || effectiveMeta.view_mode_label || '';

        if (marketStatus === 'trading') {
            return {
                className: 'text-[11px] font-bold text-green-500 bg-green-500/10 px-2 py-0.5 rounded border border-green-500/20',
                text: `🟢 ${marketLabel} · ${scopeLabel}`,
            };
        }

        if (marketStatus === 'lunch_break') {
            return {
                className: 'text-[11px] font-bold text-orange-400 bg-orange-500/10 px-2 py-0.5 rounded border border-orange-500/20',
                text: `🟠 ${marketLabel} · ${scopeLabel}`,
            };
        }

        if (marketStatus === 'post_close') {
            return {
                className: 'text-[11px] font-bold text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20',
                text: `🔵 ${marketLabel} · ${scopeLabel}`,
            };
        }

        return {
            className: 'text-[11px] font-bold text-slate-300 bg-slate-800 px-2 py-0.5 rounded border border-slate-700',
            text: `⚪ ${marketLabel} · ${scopeLabel}`,
        };
    };

    const getSourceLabel = () => {
        if (sourceMeta.source === 'l2_history') {
            const bucket = sourceMeta.bucket_granularity || '5m';
            return `Source: 正式L2历史 (${bucket})`;
        }
        if (sourceMeta.source === 'history_1m') {
            return 'Source: 历史1m回放';
        }
        if (sourceMeta.source === 'sentiment_snapshots_fallback') {
            return 'Source: 当日快照兜底';
        }
        if (sourceMeta.source === 'realtime_ticks') {
            return sourceMeta.is_finalized ? 'Source: 实时 ticks（已结算）' : 'Source: 实时 ticks';
        }
        return 'Source: 数据源识别中...';
    };

    const statusBadge = getStatusBadge();

    return (
        <div className="space-y-2">
            {/* Top Row: Main Chart (Full Width) */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative">
                <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center">
                        <h3 className="text-base font-bold text-white flex items-center gap-2">
                            <TrendingUp className="w-4 h-4 text-blue-400" />
                            主力动态 (实时)
                            {isRefreshing && (
                                <span className={`text-[10px] font-normal ml-1 animate-pulse ${focusMode === 'focus' ? 'text-red-300' : 'text-sky-300'}`}>
                                    静默刷新中...
                                </span>
                            )}
                            <span className="text-[10px] font-normal text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded ml-2">
                                {getSourceLabel()}
                            </span>
                        </h3>

                        {/* History Date Selector & Back Button */}
                        <div className="flex items-center gap-2 ml-4">
                            <input
                                type="date"
                                value={selectedDate}
                                onChange={(e) => setSelectedDate(e.target.value)}
                                className="bg-slate-800 text-slate-200 border border-slate-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500"
                            />
                            {selectedDate && (
                                <button
                                    onClick={() => setSelectedDate('')}
                                    className="bg-blue-600/20 text-blue-400 hover:bg-blue-600/40 border border-blue-600/30 rounded px-2 py-1 text-xs transition-colors"
                                >
                                    返回今日
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        {/* Status Indicator */}
                        <span className={statusBadge.className}>
                            {statusBadge.text}
                        </span>
                        {/* Last Updated */}
                        <span className="text-[10px] text-slate-500 font-mono">
                            {lastUpdated ? `Updated: ${lastUpdated}` : '正在同步数据...'}
                        </span>
                    </div>
                </div>

                <div className="flex flex-col md:grid md:grid-rows-2 gap-4 md:gap-2 h-[800px] md:h-[500px]">
                    {/* 1. 分时强度图 (Instantaneous) */}
                    <div className="h-full w-full relative">
                        <div className="absolute top-2 left-2 md:left-10 z-10 text-[10px] md:text-xs font-bold text-slate-400 bg-slate-900/80 px-2 rounded">
                            分时博弈强度
                        </div>
                        {chartData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={chartData} syncId="capitalFlow">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                    <XAxis
                                        dataKey="time"
                                        xAxisId="0"
                                        stroke="#64748b"
                                        tick={{ fontSize: 12 }}
                                        ticks={['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00']}
                                        interval="preserveStartEnd"
                                        hide // Hide X Axis for top chart
                                    />
                                    {/* Second XAxis for Super Large Bars to overlap */}
                                    <XAxis
                                        dataKey="time"
                                        xAxisId="1"
                                        hide
                                    />
                                    {/* Left Axis: Amount (Bar) */}
                                    <YAxis
                                        yAxisId="amount"
                                        stroke="#94a3b8"
                                        tick={{ fontSize: 10 }}
                                        tickFormatter={(val) => (Math.abs(val) / 10000).toFixed(0)}
                                    />
                                    {/* Right Axis: Ratio (Line) */}
                                    <YAxis
                                        yAxisId="ratio"
                                        orientation="right"
                                        stroke="#cbd5e1"
                                        tick={{ fontSize: 10 }}
                                        unit="%"
                                        domain={[0, 100]}
                                        hide
                                    />
                                    {/* Hidden Axis: Price */}
                                    <YAxis
                                        yAxisId="price"
                                        orientation="right"
                                        domain={['auto', 'auto']}
                                        hide
                                    />

                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                                        itemStyle={{ fontSize: 12 }}
                                        formatter={(val: number, name: string) => {
                                            if (name.includes('主力') || name.includes('超大单')) {
                                                if (name.includes('占比') || name.includes('参与度')) {
                                                    return [val + '%', name];
                                                }
                                                return [(Math.abs(val) / 10000).toFixed(1) + '万', name];
                                            }
                                            if (name === '股价') return [val.toFixed(2), name];
                                            return [val, name];
                                        }}
                                    />
                                    <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" height={36} />

                                    {/* Bars: Buy (Up) / Sell (Down) */}
                                    {/* Layer 1: Main Force (Background) - Lighter Colors */}
                                    <Bar xAxisId="0" yAxisId="amount" dataKey="mainBuyAmount" name="主力买入" fill="#f87171" barSize={4} fillOpacity={1} />
                                    <Bar xAxisId="0" yAxisId="amount" dataKey="mainSellAmountPlot" name="主力卖出" fill="#4ade80" barSize={4} fillOpacity={1} />

                                    {/* Layer 2: Super Large (Foreground) - Darker/Vivid Colors */}
                                    <Bar xAxisId="1" yAxisId="amount" dataKey="superBuyAmount" name="超大单买入" fill="#9333ea" barSize={4} />
                                    <Bar xAxisId="1" yAxisId="amount" dataKey="superSellAmountPlot" name="超大单卖出" fill="#14532d" barSize={4} />

                                    {/* Lines: Participation & Price */}
                                    <Line yAxisId="ratio" type="monotone" dataKey="mainParticipationRatio" name="主力参与度" stroke="#f8fafc" strokeWidth={1} dot={false} strokeOpacity={0.25} animationDuration={500} />
                                    <Line yAxisId="ratio" type="monotone" dataKey="superParticipationRatio" name="超大单参与度" stroke="#9333ea" strokeWidth={1} dot={false} strokeOpacity={0.25} animationDuration={500} />
                                    <Line yAxisId="price" type="monotone" dataKey="closePrice" name="股价" stroke="#facc15" strokeWidth={1} dot={false} animationDuration={500} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        ) : isLoadingDashboard ? (
                            <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
                                <span>正在获取分时数据...</span>
                                <span className="text-xs text-slate-600">已先判定市场状态，图表数据仍在加载</span>
                            </div>
                        ) : displayDate ? (
                            <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
                                <span>{sourceMeta.view_mode === 'manual_date' ? '当前回溯日期无本地 Tick 数据' : '暂无交易数据'}</span>
                                {sourceMeta.view_mode === 'manual_date' && <span className="text-xs text-slate-600">本地数据库未在此日期保存该股票的明细记录</span>}
                            </div>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                                加载中...
                            </div>
                        )}
                    </div>

                    {/* 2. 累计趋势图 (Cumulative) */}
                    <div className="h-full w-full relative">
                        <div className="absolute top-2 left-2 md:left-10 z-10 text-[10px] md:text-xs font-bold text-slate-400 bg-slate-900/80 px-2 rounded">
                            主力累计资金 (万元)
                        </div>
                        {cumulativeData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={cumulativeData} syncId="capitalFlow">
                                    <defs>
                                        <linearGradient id="splitColor" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset={off} stopColor="#ef4444" stopOpacity={0.3} />
                                            <stop offset={off} stopColor="#22c55e" stopOpacity={0.3} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                    <XAxis
                                        dataKey="time"
                                        stroke="#64748b"
                                        tick={{ fontSize: 12 }}
                                        ticks={['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00']}
                                        interval="preserveStartEnd"
                                    />
                                    {/* Left Axis: Net Inflow */}
                                    <YAxis
                                        yAxisId="net"
                                        stroke="#a78bfa"
                                        tick={{ fontSize: 12 }}
                                        tickFormatter={(val) => (val / 10000).toFixed(0)}
                                        domain={['auto', 'auto']}
                                    />
                                    {/* Right Axis: Total Buy/Sell */}
                                    <YAxis
                                        yAxisId="total"
                                        orientation="right"
                                        stroke="#64748b"
                                        tick={{ fontSize: 12 }}
                                        tickFormatter={(val) => (val / 10000).toFixed(0)}
                                        domain={['auto', 'auto']}
                                        hide // Hide right axis ticks to avoid clutter, just use for scaling
                                    />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                                        itemStyle={{ fontSize: 12 }}
                                        formatter={(val: number, name: string) => {
                                            const v = (val / 10000).toFixed(1) + '万';
                                            return [v, name];
                                        }}
                                    />
                                    <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" height={36} />

                                    {/* Area for Main Net Inflow - Red/Green based on value */}
                                    <Area
                                        yAxisId="net"
                                        type="monotone"
                                        dataKey="cumNetInflow"
                                        name="主力净流入"
                                        stroke="none"
                                        fill="url(#splitColor)"
                                        animationDuration={500}
                                    />

                                    {/* Super Large Net Inflow Line */}
                                    <Line
                                        yAxisId="net"
                                        type="monotone"
                                        dataKey="cumSuperNetInflow"
                                        name="超大单净流入"
                                        stroke="#d946ef"
                                        strokeWidth={2}
                                        dot={false}
                                        strokeDasharray="5 5"
                                        animationDuration={500}
                                    />

                                    {/* Background Reference Lines (Total) */}
                                    {/* Main Force: Solid Lines */}
                                    <Line yAxisId="total" type="monotone" dataKey="cumMainBuy" name="主力买入" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeOpacity={0.8} animationDuration={500} />
                                    <Line yAxisId="total" type="monotone" dataKey="cumMainSell" name="主力卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} strokeOpacity={0.8} animationDuration={500} />

                                    {/* Super Large: Dashed Lines */}
                                    <Line yAxisId="total" type="monotone" dataKey="cumSuperBuy" name="超大单买入" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeDasharray="3 3" strokeOpacity={0.8} animationDuration={500} />
                                    <Line yAxisId="total" type="monotone" dataKey="cumSuperSell" name="超大单卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} strokeDasharray="3 3" strokeOpacity={0.8} animationDuration={500} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                                计算累计趋势中...
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Bottom Row: Sentiment (Full Width Now) */}
            <div className="min-h-[400px] flex">
                <div className="flex-1 min-w-0 bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative flex flex-col">
                    <h3 className="text-base font-bold text-white flex items-center gap-2 mb-2 shrink-0">
                        <TrendingUp className="w-4 h-4 text-purple-400" />
                        资金博弈分析
                    </h3>
                    <div className="flex-1 min-h-[350px]">
                        {activeStock && <SentimentTrend symbol={activeStock.symbol} date={selectedDate} />}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default RealtimeView;
