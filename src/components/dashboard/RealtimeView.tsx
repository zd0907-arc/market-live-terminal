import React, { useState, useEffect, useRef } from 'react';
import { TrendingUp, Layers, Activity, RefreshCw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { RealTimeQuote, TickData, SearchResult, CapitalRatioData } from '../../types';
import * as StockService from '../../services/stockService';
import { calculateCapitalFlow } from '@/utils/calculator';
import SentimentTrend from './SentimentTrend';

interface RealtimeViewProps {
    activeStock: SearchResult | null;
    quote: RealTimeQuote | null;
    isTradingHours: () => boolean;
}

const RealtimeView: React.FC<RealtimeViewProps> = ({ activeStock, quote, isTradingHours }) => {
    // State
    // Removed DataSourceControl state, force Sina logic internally

    // Data
    const allTicksRef = useRef<TickData[]>([]);
    const [displayTicks, setDisplayTicks] = useState<TickData[]>([]); 
    const [chartData, setChartData] = useState<CapitalRatioData[]>([]);
    const isFetchingRef = useRef(false);
    const [lastUpdated, setLastUpdated] = useState<string>('');

    // Thresholds (Loaded from Backend)
    const [thresholds, setThresholds] = useState({ large: 200000, superLarge: 1000000 });

    // Refresh Control
    const [refreshInterval, setRefreshInterval] = useState<number>(300000); // Default 5min
    const [isRefreshing, setIsRefreshing] = useState(true);
    const [manualRefreshTrigger, setManualRefreshTrigger] = useState(0);

    // Load Thresholds on Mount
    useEffect(() => {
        StockService.getAppConfig().then(cfg => {
            setThresholds({
                large: parseFloat(cfg.large_threshold) || 200000,
                superLarge: parseFloat(cfg.super_large_threshold) || 1000000
            });
        });
    }, []);

    // 核心计算逻辑：使用 Utility Function
    const recalcChartData = () => {
        const result = calculateCapitalFlow(allTicksRef.current, thresholds.large);
        setChartData(result);
    };

    // 逐笔成交数据处理
    const processNewTicks = (newTicks: TickData[]) => {
        if (newTicks.length === 0) return;
        
        // 由于后端现在返回全量数据，前端直接覆盖即可，无需复杂的增量合并逻辑
        // 但为了保持平滑，我们可以只在数据长度变化或有新数据时更新
        // 这里简单处理：全量替换。因为本地数据库读取很快，前端React Diff也会高效处理
        
        // 简单去重/覆盖逻辑：
        // 实际上后端 /api/ticks_full 返回的是当天截止目前的全部数据
        // 我们直接替换 allTicksRef 即可
        
        allTicksRef.current = newTicks;
        
        // 更新 UI
        const uiList = [...newTicks].slice(0, 100); // 已经是倒序的 (Time DESC)
        setDisplayTicks(uiList);
        recalcChartData();
        
        // 更新时间
        const now = new Date();
        setLastUpdated(now.toLocaleTimeString());
    };

    // Data Polling
    useEffect(() => {
        if (!activeStock) return;
        
        // Reset data on stock change
        allTicksRef.current = [];
        setDisplayTicks([]);
        setChartData([]);
        setLastUpdated('');

        let isMounted = true;
        let intervalId: any = null;

        const fetchData = async () => {
            if (!isMounted || isFetchingRef.current) return;
            isFetchingRef.current = true;
            try {
                // Only fetch ticks here, quote is fetched by parent
                const ticksPromise = StockService.fetchTicks(activeStock.symbol);
                const t = await ticksPromise;
                if (isMounted && t && t.length > 0) {
                     processNewTicks(t);
                }
            } catch (tickErr) {
                console.warn("Ticks update failed", tickErr);
            } finally {
                isFetchingRef.current = false;
            }
        };

        fetchData();
        
        // 轮询频率：10秒查一次本地库 (非常轻量)
        intervalId = setInterval(fetchData, 10000);

        return () => {
            isMounted = false;
            if (intervalId) clearInterval(intervalId);
        };
    }, [activeStock]); // 移除 refreshInterval 依赖，固定轮询本地库

    if (!quote) return null;

    return (
        <div className="space-y-6">
            {/* Top Row: Main Chart (Full Width) */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg relative">
                <div className="flex items-center justify-between mb-6">
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <TrendingUp className="w-5 h-5 text-blue-400" />
                        主力动态 (实时)
                        <span className="text-xs font-normal text-slate-500 bg-slate-800 px-2 py-0.5 rounded ml-2">
                            Source: Sina (AkShare)
                        </span>
                    </h3>
                    
                    <div className="flex items-center gap-4">
                        {/* Last Updated */}
                        <span className="text-xs text-slate-500 font-mono">
                            {lastUpdated ? `Updated: ${lastUpdated} (${displayTicks.length} ticks)` : '正在后台同步数据 (约需1-3分钟)...'}
                        </span>

                        <div className="text-xs text-slate-500 flex items-center gap-2">
                            <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-red-500 mr-1"></span>主买</span>
                            <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-green-500 mr-1"></span>主卖</span>
                            <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-yellow-400 mr-1"></span>参与度</span>
                        </div>
                    </div>
                </div>
                
                <div className="h-[300px] w-full">
                    {chartData.length > 1 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={chartData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis 
                                    dataKey="time" 
                                    stroke="#64748b" 
                                    tick={{fontSize: 12}} 
                                    ticks={['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00']}
                                    interval="preserveStartEnd"
                                />
                                <YAxis stroke="#64748b" tick={{fontSize: 12}} unit="%" domain={[0, 'auto']} />
                                <Tooltip 
                                    contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                    itemStyle={{fontSize: 12}}
                                />
                                <Legend wrapperStyle={{fontSize: 12}} />
                                <Line type="monotone" dataKey="mainBuyRatio" name="买入占比" stroke="#ef4444" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="mainSellRatio" name="卖出占比" stroke="#22c55e" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="mainParticipationRatio" name="参与度" stroke="#eab308" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                            等待更多交易数据生成图表...
                        </div>
                    )}
                </div>
            </div>

            {/* Bottom Row: Sentiment (Left) + Ticks (Right) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[400px]">
                {/* Left: Tencent Sentiment */}
                <div className="h-full">
                    {activeStock && <SentimentTrend symbol={activeStock.symbol} />}
                </div>

                {/* Right: Level-1 Ticks */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg h-full flex flex-col">
                    <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                        <h3 className="font-bold text-slate-200 flex items-center gap-2">
                            <Layers className="w-4 h-4 text-blue-400" />
                            Level-1 逐笔
                        </h3>
                        <span className="text-xs text-slate-500 animate-pulse flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Live
                        </span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-0">
                        <table className="w-full text-xs">
                            <thead className="bg-slate-950 sticky top-0 text-slate-500">
                                <tr>
                                    <th className="px-3 py-2 text-left font-medium">时间</th>
                                    <th className="px-3 py-2 text-right font-medium">价格</th>
                                    <th className="px-3 py-2 text-right font-medium">量(手)</th>
                                    <th className="px-3 py-2 text-right font-medium">额(万)</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/50">
                                {displayTicks.map((t, idx) => (
                                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                                        <td className="px-3 py-1.5 text-slate-400 font-mono">{t.time}</td>
                                        <td className={`px-3 py-1.5 text-right font-mono font-medium ${t.color}`}>
                                            {t.price.toFixed(2)}
                                        </td>
                                        <td className="px-3 py-1.5 text-right text-slate-300 font-mono">
                                            {t.volume}
                                        </td>
                                        <td className="px-3 py-1.5 text-right text-slate-500 font-mono">
                                            {(t.amount / 10000).toFixed(1)}
                                            {t.amount > thresholds.superLarge && <span className="ml-1 text-purple-400 font-bold">*</span>}
                                        </td>
                                    </tr>
                                ))}
                                {displayTicks.length === 0 && (
                                    <tr><td colSpan={4} className="text-center py-10 text-slate-600">等待逐笔数据...</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default RealtimeView;
