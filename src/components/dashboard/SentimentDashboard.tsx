import React, { useEffect, useState } from 'react';
import { Gauge, ArrowUp, ArrowDown, Activity } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import { SentimentData } from '../../types';
import * as StockService from '../../services/stockService';

interface SentimentDashboardProps {
    symbol: string;
    refreshInterval: number;
}

const SentimentDashboard: React.FC<SentimentDashboardProps> = ({ symbol, refreshInterval }) => {
    const [data, setData] = useState<SentimentData | null>(null);
    const [loading, setLoading] = useState(false);

    const fetchData = async () => {
        try {
            const res = await StockService.fetchSentimentData(symbol);
            if (res) setData(res);
        } catch (e) {
            console.error("Sentiment fetch error", e);
        }
    };

    useEffect(() => {
        setLoading(true);
        fetchData().finally(() => setLoading(false));
        
        const id = setInterval(fetchData, refreshInterval > 0 ? refreshInterval : 5000);
        return () => clearInterval(id);
    }, [symbol, refreshInterval]);

    if (!data) return (
        <div className="h-full flex flex-col items-center justify-center text-slate-600 bg-slate-900 border border-slate-800 rounded-xl">
            <Activity className="w-8 h-8 mb-2 opacity-50" />
            <span className="text-xs">等待情绪数据...</span>
        </div>
    );

    // Calculations
    const totalActive = data.outer_disk + data.inner_disk;
    const activeBuyRatio = (data.outer_disk / totalActive) * 100;
    const activeSellRatio = (data.inner_disk / totalActive) * 100;
    const netActiveBuy = data.outer_disk - data.inner_disk;
    
    const totalQueue = data.buy_queue_vol + data.sell_queue_vol;
    const buyQueueRatio = (data.buy_queue_vol / totalQueue) * 100;
    
    // Sentiment Label
    let sentimentLabel = "多空平衡";
    let sentimentColor = "text-yellow-400";
    if (activeBuyRatio > 60) { sentimentLabel = "多头主导"; sentimentColor = "text-red-500"; }
    if (activeBuyRatio < 40) { sentimentLabel = "空头占优"; sentimentColor = "text-green-500"; }
    if (activeBuyRatio > 75) { sentimentLabel = "极强吸筹"; sentimentColor = "text-purple-400"; }
    
    const pieData = [
        { name: '主动买(外盘)', value: data.outer_disk, color: '#ef4444' },
        { name: '主动卖(内盘)', value: data.inner_disk, color: '#22c55e' },
    ];

    const barData = [
        { name: '买盘', value: data.buy_queue_vol, fill: '#ef4444' },
        { name: '卖盘', value: data.sell_queue_vol, fill: '#22c55e' },
    ];

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg h-full flex flex-col">
            <div className="flex justify-between items-center mb-4 pb-2 border-b border-slate-800">
                <h3 className="font-bold text-slate-200 flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-blue-400" />
                    多空情绪 (Tencent)
                </h3>
                <div className={`text-xs font-bold px-2 py-0.5 rounded bg-slate-800 ${sentimentColor}`}>
                    {sentimentLabel}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 flex-1">
                {/* Left: Active Trade (Outer vs Inner) */}
                <div className="flex flex-col items-center justify-center relative">
                    <div className="text-xs text-slate-400 mb-1">实战博弈 (成交)</div>
                    <div className="h-[120px] w-full relative">
                        <ResponsiveContainer>
                            <PieChart>
                                <Pie 
                                    data={pieData} 
                                    innerRadius={35} 
                                    outerRadius={50} 
                                    paddingAngle={5} 
                                    dataKey="value"
                                    stroke="none"
                                >
                                    {pieData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip 
                                    contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px'}}
                                    formatter={(val: number) => val.toLocaleString()}
                                />
                            </PieChart>
                        </ResponsiveContainer>
                        {/* Center Text */}
                        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                            <span className={`text-xs font-bold ${netActiveBuy > 0 ? 'text-red-500' : 'text-green-500'}`}>
                                {netActiveBuy > 0 ? '+' : ''}{(netActiveBuy/10000).toFixed(1)}万
                            </span>
                            <span className="text-[10px] text-slate-500">净主动</span>
                        </div>
                    </div>
                    <div className="w-full flex justify-between text-[10px] px-2">
                        <span className="text-red-400">{activeBuyRatio.toFixed(0)}%</span>
                        <span className="text-green-400">{activeSellRatio.toFixed(0)}%</span>
                    </div>
                </div>

                {/* Right: Passive Queue (Buy 1-5 vs Sell 1-5) */}
                <div className="flex flex-col items-center justify-center">
                    <div className="text-xs text-slate-400 mb-1">潜在意愿 (挂单)</div>
                    <div className="h-[120px] w-full">
                        <ResponsiveContainer>
                            <BarChart data={barData} layout="vertical" barSize={20}>
                                <XAxis type="number" hide />
                                <YAxis type="category" dataKey="name" tick={{fontSize: 10, fill: '#64748b'}} width={30} />
                                <Tooltip cursor={{fill: 'transparent'}} contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px'}} />
                                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                    {barData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.fill} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1">
                        委比: <span className={buyQueueRatio > 50 ? 'text-red-400' : 'text-green-400'}>
                            {((data.buy_queue_vol - data.sell_queue_vol) / totalQueue * 100).toFixed(1)}%
                        </span>
                    </div>
                </div>
            </div>
            
            <div className="mt-auto pt-3 border-t border-slate-800 flex justify-between text-[10px] text-slate-500">
                <span>换手率: {data.turnover_rate}%</span>
                <span>更新: {data.timestamp}</span>
            </div>
        </div>
    );
};

export default SentimentDashboard;
