import React, { useState, useEffect, useRef } from 'react';
import { TrendingUp, Layers } from 'lucide-react';
import { LineChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Area, ComposedChart } from 'recharts';
import { RealTimeQuote, TickData, SearchResult, CapitalRatioData, CumulativeCapitalData } from '../../types';
import * as StockService from '../../services/stockService';
import SentimentTrend from './SentimentTrend';

interface RealtimeViewProps {
    activeStock: SearchResult | null;
    quote: RealTimeQuote | null;
    isTradingHours: () => boolean;
    configVersion?: number;
}

const RealtimeView: React.FC<RealtimeViewProps> = ({ activeStock, quote, configVersion }) => {
    // State
    const [displayTicks, setDisplayTicks] = useState<TickData[]>([]); 
    const [chartData, setChartData] = useState<CapitalRatioData[]>([]);
    const [cumulativeData, setCumulativeData] = useState<CumulativeCapitalData[]>([]);
    const isFetchingRef = useRef(false);
    const [lastUpdated, setLastUpdated] = useState<string>('');

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

    useEffect(() => {
        if (!activeStock) return;
        
        // Reset data on stock change
        setDisplayTicks([]);
        setChartData([]);
        setCumulativeData([]);
        setLastUpdated('');

        let isMounted = true;
        let intervalId: any = null;

        const fetchData = async () => {
            if (!isMounted || isFetchingRef.current) return;
            isFetchingRef.current = true;
            try {
                // Fetch pre-calculated dashboard data from backend
                const data = await StockService.fetchRealtimeDashboard(activeStock.symbol);
                
                if (isMounted && data) {
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
                    
                    // Update Ticks Table (Only latest N)
                    if (data.latest_ticks && Array.isArray(data.latest_ticks)) {
                         const ticks = data.latest_ticks.map((t: any) => ({
                            ...t,
                            color: t.type === 'buy' ? 'text-red-500' : (t.type === 'sell' ? 'text-green-500' : 'text-slate-400')
                         }));
                         setDisplayTicks(ticks);
                    }
                    
                    const now = new Date();
                    setLastUpdated(now.toLocaleTimeString());
                }
            } catch (err) {
                console.warn("Dashboard update failed", err);
            } finally {
                isFetchingRef.current = false;
            }
        };

        fetchData();
        
        // Polling every 5 seconds (Lightweight now)
        intervalId = setInterval(fetchData, 5000);

        return () => {
            isMounted = false;
            if (intervalId) clearInterval(intervalId);
        };
    }, [activeStock, forceRefresh]); 
    
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
    
    if (!quote) return null;

    return (
        <div className="space-y-2">
            {/* Top Row: Main Chart (Full Width) */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative">
                <div className="flex items-center justify-between mb-2">
                    <h3 className="text-base font-bold text-white flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-blue-400" />
                        主力动态 (实时)
                        <span className="text-[10px] font-normal text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded ml-2">
                            Source: Local DB
                        </span>
                    </h3>
                    
                    <div className="flex items-center gap-4">
                        {/* Last Updated */}
                        <span className="text-[10px] text-slate-500 font-mono">
                            {lastUpdated ? `Updated: ${lastUpdated}` : '正在同步数据...'}
                        </span>
                    </div>
                </div>
                
                <div className="grid grid-rows-2 gap-2 h-[500px]">
                    {/* 1. 分时强度图 (Instantaneous) */}
                    <div className="h-full w-full relative">
                        <div className="absolute top-2 left-10 z-10 text-xs font-bold text-slate-400 bg-slate-900/80 px-2 rounded">
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
                                        tick={{fontSize: 12}} 
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
                                        tick={{fontSize: 10}} 
                                        tickFormatter={(val) => (Math.abs(val) / 10000).toFixed(0)}
                                    />
                                    {/* Right Axis: Ratio (Line) */}
                                    <YAxis 
                                        yAxisId="ratio"
                                        orientation="right"
                                        stroke="#cbd5e1" 
                                        tick={{fontSize: 10}} 
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
                                        contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                        itemStyle={{fontSize: 12}}
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
                                    <Legend wrapperStyle={{fontSize: 12}} verticalAlign="top" height={36}/>
                                    
                                    {/* Bars: Buy (Up) / Sell (Down) */}
                                    {/* Layer 1: Main Force (Background) - Lighter Colors */}
                                    <Bar xAxisId="0" yAxisId="amount" dataKey="mainBuyAmount" name="主力买入" fill="#f87171" barSize={4} fillOpacity={1} />
                                    <Bar xAxisId="0" yAxisId="amount" dataKey="mainSellAmountPlot" name="主力卖出" fill="#4ade80" barSize={4} fillOpacity={1} />
                                    
                                    {/* Layer 2: Super Large (Foreground) - Darker/Vivid Colors */}
                                    <Bar xAxisId="1" yAxisId="amount" dataKey="superBuyAmount" name="超大单买入" fill="#9333ea" barSize={4} />
                                    <Bar xAxisId="1" yAxisId="amount" dataKey="superSellAmountPlot" name="超大单卖出" fill="#14532d" barSize={4} />
                                    
                                    {/* Lines: Participation & Price */}
                                    <Line yAxisId="ratio" type="monotone" dataKey="mainParticipationRatio" name="主力参与度" stroke="#f8fafc" strokeWidth={1} dot={false} strokeOpacity={0.25} animationDuration={500}/>
                                    <Line yAxisId="ratio" type="monotone" dataKey="superParticipationRatio" name="超大单参与度" stroke="#9333ea" strokeWidth={1} dot={false} strokeOpacity={0.25} animationDuration={500}/>
                                    <Line yAxisId="price" type="monotone" dataKey="closePrice" name="股价" stroke="#facc15" strokeWidth={1} dot={false} animationDuration={500}/>
                                </ComposedChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                                等待数据...
                            </div>
                        )}
                    </div>

                    {/* 2. 累计趋势图 (Cumulative) */}
                    <div className="h-full w-full relative">
                        <div className="absolute top-2 left-10 z-10 text-xs font-bold text-slate-400 bg-slate-900/80 px-2 rounded">
                            主力累计资金 (万元)
                        </div>
                        {cumulativeData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={cumulativeData} syncId="capitalFlow">
                                    <defs>
                                        <linearGradient id="splitColor" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset={off} stopColor="#ef4444" stopOpacity={0.3}/>
                                            <stop offset={off} stopColor="#22c55e" stopOpacity={0.3}/>
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                    <XAxis 
                                        dataKey="time" 
                                        stroke="#64748b" 
                                        tick={{fontSize: 12}} 
                                        ticks={['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00']}
                                        interval="preserveStartEnd"
                                    />
                                    {/* Left Axis: Net Inflow */}
                                    <YAxis 
                                        yAxisId="net"
                                        stroke="#a78bfa" 
                                        tick={{fontSize: 12}} 
                                        tickFormatter={(val) => (val / 10000).toFixed(0)}
                                        domain={['auto', 'auto']}
                                    />
                                    {/* Right Axis: Total Buy/Sell */}
                                    <YAxis 
                                        yAxisId="total"
                                        orientation="right"
                                        stroke="#64748b" 
                                        tick={{fontSize: 12}} 
                                        tickFormatter={(val) => (val / 10000).toFixed(0)}
                                        domain={['auto', 'auto']}
                                        hide // Hide right axis ticks to avoid clutter, just use for scaling
                                    />
                                    <Tooltip 
                                        contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                        itemStyle={{fontSize: 12}}
                                        formatter={(val: number, name: string) => {
                                            const v = (val / 10000).toFixed(1) + '万';
                                            return [v, name];
                                        }}
                                    />
                                    <Legend wrapperStyle={{fontSize: 12}} verticalAlign="top" height={36}/>
                                    
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
                                    <Line yAxisId="total" type="monotone" dataKey="cumMainBuy" name="主力买入" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeOpacity={0.8} animationDuration={500}/>
                                    <Line yAxisId="total" type="monotone" dataKey="cumMainSell" name="主力卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} strokeOpacity={0.8} animationDuration={500}/>
                                    
                                    {/* Super Large: Dashed Lines */}
                                    <Line yAxisId="total" type="monotone" dataKey="cumSuperBuy" name="超大单买入" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeDasharray="3 3" strokeOpacity={0.8} animationDuration={500}/>
                                    <Line yAxisId="total" type="monotone" dataKey="cumSuperSell" name="超大单卖出" stroke="#22c55e" strokeWidth={1.5} dot={false} strokeDasharray="3 3" strokeOpacity={0.8} animationDuration={500}/>
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

            {/* Bottom Row: Sentiment (Left) + Ticks (Right) */}
            <div className="flex gap-2 h-[400px]">
                {/* Left: Sentiment Analysis */}
                <div className="flex-1 min-w-0 bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative flex flex-col">
                     <h3 className="text-base font-bold text-white flex items-center gap-2 mb-2 shrink-0">
                        <TrendingUp className="w-4 h-4 text-purple-400" />
                        资金博弈分析
                    </h3>
                    <div className="flex-1 min-h-0">
                         {activeStock && <SentimentTrend symbol={activeStock.symbol} />}
                    </div>
                </div>

                {/* Right: Level-1 Ticks */}
                <div className="w-[320px] shrink-0 bg-slate-900 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg h-full flex flex-col">
                    <div className="p-2 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center shrink-0">
                        <h3 className="font-bold text-slate-200 flex items-center gap-2 text-sm">
                            <Layers className="w-3.5 h-3.5 text-blue-400" />
                            逐笔成交
                        </h3>
                        <span className="text-[10px] text-slate-500 animate-pulse flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Live
                        </span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-0">
                        <table className="w-full text-xs table-fixed">
                            <thead className="bg-slate-950 sticky top-0 text-slate-500">
                                <tr>
                                    <th className="px-2 py-1.5 text-left font-medium w-16">时间</th>
                                    <th className="px-2 py-1.5 text-right font-medium">价格</th>
                                    <th className="px-2 py-1.5 text-right font-medium">量</th>
                                    <th className="px-2 py-1.5 text-right font-medium">额</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/50">
                                {displayTicks.map((t, idx) => (
                                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                                        <td className="px-2 py-1 text-slate-400 font-mono truncate">{t.time}</td>
                                        <td className={`px-2 py-1 text-right font-mono font-medium truncate ${t.color}`}>
                                            {t.price.toFixed(2)}
                                        </td>
                                        <td className="px-2 py-1 text-right text-slate-300 font-mono truncate">
                                            {t.volume}
                                        </td>
                                        <td className="px-2 py-1 text-right text-slate-500 font-mono truncate">
                                            {(t.amount / 10000).toFixed(0)}
                                            {t.amount > thresholds.superLarge && <span className="ml-0.5 text-purple-400 font-bold">*</span>}
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
