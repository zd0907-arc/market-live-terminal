import React, { useState, useEffect } from 'react';
import { AlertCircle, RefreshCw, Database, Settings, Info } from 'lucide-react';
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine, Cell, Area } from 'recharts';
import { SearchResult, HistoryAnalysisData, HistoryTrendData } from '../../types';
import * as StockService from '../../services/stockService';
import DataSourceControl from '../common/DataSourceControl';
import ConfigModal from '../common/ConfigModal';

interface HistoryViewProps {
    activeStock: SearchResult | null;
    backendStatus: boolean;
    configVersion?: number;
}

const HistoryView: React.FC<HistoryViewProps> = ({ activeStock, backendStatus, configVersion }) => {
    // History State
    const [historySource, setHistorySource] = useState('sina');
    const [historyCompareMode, setHistoryCompareMode] = useState(false);
    const [historyCompareSource, setHistoryCompareSource] = useState('local');
    const [historyCompareData, setHistoryCompareData] = useState<HistoryAnalysisData[]>([]);
    
    // Intraday Trend State (New)
    const [viewMode, setViewMode] = useState<'daily' | 'intraday'>('daily');
    const [trendDays, setTrendDays] = useState(5);
    const [trendData, setTrendData] = useState<HistoryTrendData[]>([]);

    // Data
    const [historyData, setHistoryData] = useState<HistoryAnalysisData[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyError, setHistoryError] = useState('');

    // Config
    const [showConfig, setShowConfig] = useState(false);

    const loadHistoryData = async (symbol: string, source: 'sina' | 'local' = 'sina') => {
        setHistoryLoading(true);
        setHistoryError('');
        try {
            const data = await StockService.fetchHistoryAnalysis(symbol, source);
            if (source === 'sina') {
                setHistoryData(data);
            } else {
                setHistoryCompareData(data);
            }
        } catch (e: any) {
            setHistoryError(e.message || '获取历史数据失败');
        } finally {
            setHistoryLoading(false);
        }
    };

    // Load Intraday Trend
    useEffect(() => {
        if (activeStock && viewMode === 'intraday') {
            setHistoryLoading(true);
            StockService.fetchHistoryTrend(activeStock.symbol, trendDays)
                .then(data => {
                    setTrendData(data);
                    setHistoryLoading(false);
                })
                .catch(err => {
                    setHistoryError(err.message);
                    setHistoryLoading(false);
                });
        }
    }, [activeStock, viewMode, trendDays, configVersion]);

    // Initial Load & Source Change (Daily Mode)
    useEffect(() => {
        if (activeStock && viewMode === 'daily') {
            loadHistoryData(activeStock.symbol, historySource as any);
        }
    }, [historySource, activeStock, viewMode, configVersion]);

    // Compare Source Change
    useEffect(() => {
        if (activeStock && historyCompareMode && viewMode === 'daily') {
            loadHistoryData(activeStock.symbol, historyCompareSource as any);
        }
    }, [historyCompareSource, historyCompareMode, activeStock, viewMode, configVersion]);

    const gradientOffset = () => {
      if (trendData.length === 0) return 0;
      const dataMax = Math.max(...trendData.map((i) => i.net_inflow));
      const dataMin = Math.min(...trendData.map((i) => i.net_inflow));
      if (dataMax <= 0) return 0;
      if (dataMin >= 0) return 1;
      return dataMax / (dataMax - dataMin);
    };
    const off = gradientOffset();

    if (!activeStock) return null;

    return (
        <div className="space-y-2">
            <ConfigModal 
                isOpen={showConfig} 
                onClose={() => setShowConfig(false)} 
                onSave={() => {
                    if(historySource === 'local') loadHistoryData(activeStock.symbol, 'local');
                    if(historyCompareMode && historyCompareSource === 'local') loadHistoryData(activeStock.symbol, 'local');
                }} 
            />

            {/* Config Button Area */}
            <div className="flex justify-between items-center mb-1">
                {/* View Mode Toggle */}
                <div className="flex bg-slate-900 rounded-lg p-1 border border-slate-800">
                    <button
                        onClick={() => setViewMode('daily')}
                        className={`px-3 py-1.5 rounded-md text-xs transition-colors ${viewMode === 'daily' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                    >
                        日线统计
                    </button>
                    <button
                        onClick={() => setViewMode('intraday')}
                        className={`px-3 py-1.5 rounded-md text-xs transition-colors ${viewMode === 'intraday' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                    >
                        30分钟趋势
                    </button>
                </div>

                <div className="flex gap-2">
                    {(historySource === 'local' || (historyCompareMode && historyCompareSource === 'local')) && viewMode === 'daily' && (
                        <button 
                            onClick={() => setShowConfig(true)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-slate-400 hover:text-white hover:border-slate-600 transition-colors text-xs"
                        >
                            <Settings className="w-3.5 h-3.5" /> 规则设置
                        </button>
                    )}
                    
                    {viewMode === 'daily' && (
                        <DataSourceControl 
                            mode="history"
                            source={historySource}
                            setSource={setHistorySource}
                            compareMode={historyCompareMode}
                            setCompareMode={setHistoryCompareMode}
                        />
                    )}
                </div>
            </div>

            {/* Backend Status Warning */}
            {!backendStatus && (
                <div className="bg-red-950/30 border border-red-900/50 p-2 rounded-lg flex items-center gap-3 text-red-300 text-xs">
                    <AlertCircle className="w-4 h-4" />
                    <span>
                        本地 Python 服务未连接 (端口 8000)。请在终端运行：
                        <code className="bg-black/30 px-2 py-0.5 rounded ml-2 text-red-200 font-mono">python -m backend.app.main</code>
                    </span>
                </div>
            )}

            {historyError && (
                <div className="bg-red-900/20 border border-red-800 p-3 rounded-lg flex items-center gap-3 text-red-200 text-xs">
                    <AlertCircle className="w-4 h-4" />
                    <span>{historyError}</span>
                </div>
            )}

            {historyLoading && (
                <div className="py-20 text-center text-blue-400 flex flex-col items-center">
                    <RefreshCw className="w-8 h-8 animate-spin mb-4" />
                    <p>正在从本地引擎加载历史资金数据...</p>
                </div>
            )}

            {!historyLoading && !historyError && (
                <>
                    {/* Intraday Trend Chart */}
                    {viewMode === 'intraday' && trendData.length > 0 && (
                        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative">
                             <div className="mb-2 flex justify-between items-center">
                                <h3 className="text-base font-bold text-white flex items-center gap-2">
                                    <span className="text-purple-500">🟣 30分钟资金趋势</span>
                                    <span className="text-[10px] font-normal text-slate-500 bg-slate-800 px-2 py-0.5 rounded ml-2">
                                        Source: Local DB (30m Bars)
                                    </span>
                                </h3>
                                <div className="flex gap-2">
                                    {[5, 10, 20].map(d => (
                                        <button
                                            key={d}
                                            onClick={() => setTrendDays(d)}
                                            className={`px-2 py-0.5 text-[10px] rounded border transition-colors ${trendDays === d ? 'bg-purple-900/50 border-purple-500 text-purple-200' : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-600'}`}
                                        >
                                            {d}日
                                        </button>
                                    ))}
                                </div>
                            </div>
                            
                            <div className="h-[400px]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={trendData}>
                                        <defs>
                                            <linearGradient id="trendSplitColor" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset={off} stopColor="#ef4444" stopOpacity={0.3}/>
                                                <stop offset={off} stopColor="#22c55e" stopOpacity={0.3}/>
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                        <XAxis 
                                            dataKey="time" 
                                            stroke="#64748b" 
                                            tick={{fontSize: 10}} 
                                            tickFormatter={(val) => val.substring(5, 16)} // MM-DD HH:MM
                                            minTickGap={30}
                                        />
                                        <YAxis yAxisId="net" stroke="#a78bfa" tick={{fontSize: 10}} tickFormatter={(val) => (val/10000).toFixed(0)} />
                                        <YAxis yAxisId="total" orientation="right" stroke="#64748b" tick={{fontSize: 10}} tickFormatter={(val) => (val/10000).toFixed(0)} hide />
                                        <Tooltip 
                                            contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                            formatter={(val: number) => (val/10000).toFixed(1) + '万'}
                                            labelFormatter={(label) => label}
                                        />
                                        <Legend wrapperStyle={{fontSize: 12}} verticalAlign="top" height={36}/>
                                        
                                        <Area yAxisId="net" type="monotone" dataKey="net_inflow" name="主力净流入" stroke="none" fill="url(#trendSplitColor)" />
                                        <Line yAxisId="net" type="monotone" dataKey="super_net" name="超大单净流入" stroke="#d946ef" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                                        
                                        <Line yAxisId="total" type="monotone" dataKey="main_buy" name="主力买入" stroke="#ef4444" strokeWidth={1} dot={false} strokeOpacity={0.5} />
                                        <Line yAxisId="total" type="monotone" dataKey="main_sell" name="主力卖出" stroke="#22c55e" strokeWidth={1} dot={false} strokeOpacity={0.5} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    )}

                    {viewMode === 'daily' && historyData.length > 0 && (
                        <div className={`grid ${historyCompareMode ? 'grid-cols-2' : 'grid-cols-1'} gap-2`}>
                            {/* Left Side (Main) */}
                            <div className="space-y-2">
                                {/* 1. Main Net Inflow */}
                                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative">
                                    <div className="mb-2 flex justify-between items-center">
                                        <h3 className="text-base font-bold text-white flex items-center gap-2">
                                            主力净流入
                                        </h3>
                                    </div>
                                    <div className="h-[300px]">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <ComposedChart data={historyData} syncId="historyGraph">
                                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                                <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 10}} />
                                                <YAxis yAxisId="left" stroke="#64748b" tick={{fontSize: 10}} tickFormatter={(val) => (val/100000000).toFixed(0)} />
                                                <YAxis yAxisId="right" orientation="right" stroke="#fbbf24" tick={{fontSize: 10}} domain={['auto', 'auto']} />
                                                
                                                <Tooltip 
                                                    position={{ y: 0 }}
                                                    contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                                    formatter={(val: number, name: string) => {
                                                        if (name === '收盘价') return val.toFixed(2);
                                                        return (val/100000000).toFixed(2) + '亿';
                                                    }} 
                                                />
                                                <Legend wrapperStyle={{fontSize: 12}} />
                                                <ReferenceLine y={0} yAxisId="left" stroke="#334155" />
                                                <Bar yAxisId="left" dataKey="net_inflow" name="主力净流入" fill="#60a5fa">
                                                    {historyData.map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={entry.net_inflow > 0 ? '#ef4444' : '#22c55e'} />
                                                    ))}
                                                </Bar>
                                                <Line yAxisId="right" type="monotone" dataKey="close" name="收盘价" stroke="#fbbf24" strokeWidth={2} dot={false} />
                                            </ComposedChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>

                                {/* 2. Buying/Selling Power */}
                                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg">
                                    <div className="mb-2 flex items-center gap-2">
                                        <h3 className="text-base font-bold text-white">买卖力度分离监控</h3>
                                        <div className="group relative">
                                            <Info className="w-3.5 h-3.5 text-slate-500 cursor-help hover:text-blue-400" />
                                            <div className="absolute left-0 bottom-full mb-2 w-64 p-3 bg-slate-800 border border-slate-700 rounded-lg shadow-xl text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                                                分析：当买入额（红）持续高于卖出额（绿）时，即便股价不涨，也可能是吸筹信号。<br/>
                                                <span className="text-yellow-400">主力交易占比</span>：反映主力资金在当天的统治力，占比越高说明散户越少。
                                            </div>
                                        </div>
                                    </div>
                                    <div className="h-[300px]">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <ComposedChart data={historyData} syncId="historyGraph">
                                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                                <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 10}} />
                                                <YAxis yAxisId="left" stroke="#64748b" tick={{fontSize: 10}} unit="%" domain={[0, 100]} />
                                                <YAxis yAxisId="right" orientation="right" stroke="#fbbf24" tick={{fontSize: 10}} unit="%" domain={[0, 100]} />
                                                <Tooltip 
                                                    position={{ y: 0 }}
                                                    contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                                    formatter={(val: number, name: string, props: any) => {
                                                        if (name === '主力交易占比') return val.toFixed(1) + '%';
                                                        if (name === '超大单占比') return val.toFixed(1) + '%';
                                                        let amount = 0;
                                                        if (name === '主力买入占比') amount = props.payload.main_buy_amount;
                                                        if (name === '主力卖出占比') amount = props.payload.main_sell_amount;
                                                        return `${val.toFixed(1)}% (${(amount/100000000).toFixed(2)}亿)`;
                                                    }} 
                                                />
                                                <Legend wrapperStyle={{fontSize: 12}} />
                                                <Area yAxisId="left" type="monotone" dataKey="buyRatio" name="主力买入占比" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.1} />
                                                <Area yAxisId="left" type="monotone" dataKey="sellRatio" name="主力卖出占比" stackId="2" stroke="#22c55e" fill="#22c55e" fillOpacity={0.1} />
                                                <Line yAxisId="right" type="monotone" dataKey="activityRatio" name="主力交易占比" stroke="#fbbf24" strokeWidth={2} dot={false} />
                                                <Line yAxisId="right" type="monotone" dataKey="super_large_ratio" name="超大单占比" stroke="#a855f7" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                                            </ComposedChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            </div>

                            {/* Right Side (Compare) */}
                            {historyCompareMode && (
                                <div className="space-y-2 border-l border-slate-800 pl-2 border-dashed relative">
                                    <div className="absolute top-0 right-0 z-20">
                                        <div className="flex items-center gap-3 bg-slate-950/50 p-1 rounded-lg border border-slate-800/50">
                                             <span className="text-[10px] text-slate-400">对比源:</span>
                                             <select 
                                                value={historyCompareSource} 
                                                onChange={(e) => setHistoryCompareSource(e.target.value)}
                                                className="bg-transparent text-xs font-medium text-blue-400 focus:outline-none cursor-pointer"
                                             >
                                                <option value="sina">🔴 新浪 (Sina)</option>
                                                <option value="local">🟣 本地自算 (Local)</option>
                                             </select>
                                        </div>
                                    </div>

                                    {/* Compare 1 */}
                                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg opacity-90 mt-8 relative">
                                        <div className="mb-2">
                                            <h3 className="text-base font-bold text-slate-300 flex items-center gap-2">
                                                {historyCompareSource === 'sina' ? <span className="text-red-500">🔴 新浪数据</span> : <span className="text-purple-500">🟣 本地自算</span>}
                                                主力净流入
                                            </h3>
                                        </div>
                                        <div className="h-[300px]">
                                            {historyCompareSource === 'local' && historyCompareData.length === 0 ? (
                                                <div className="h-full flex flex-col items-center justify-center text-slate-500">
                                                    <Database className="w-12 h-12 mb-4 opacity-20" />
                                                    <p>暂无本地数据</p>
                                                    <p className="text-xs mt-2 opacity-60">请先加关注并等待收盘计算</p>
                                                </div>
                                            ) : (
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <ComposedChart data={historyCompareData} syncId="historyGraph">
                                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                                        <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 10}} />
                                                        <YAxis stroke="#64748b" tick={{fontSize: 10}} tickFormatter={(val) => (val/100000000).toFixed(0)} />
                                                        <Tooltip 
                                                            position={{ y: 0 }}
                                                            contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                                            formatter={(val: number) => (val/100000000).toFixed(2) + '亿'} 
                                                        />
                                                        <Legend wrapperStyle={{fontSize: 12}} />
                                                        <ReferenceLine y={0} stroke="#334155" />
                                                        <Bar dataKey="net_inflow" name="主力净流入" fill="#60a5fa">
                                                            {historyCompareData.map((entry, index) => (
                                                                <Cell key={`cell-${index}`} fill={entry.net_inflow > 0 ? '#ef4444' : '#22c55e'} />
                                                            ))}
                                                        </Bar>
                                                    </ComposedChart>
                                                </ResponsiveContainer>
                                            )}
                                        </div>
                                    </div>

                                    {/* Compare 2 */}
                                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg opacity-90">
                                        <div className="mb-2">
                                            <h3 className="text-base font-bold text-slate-300">买卖力度分离监控</h3>
                                        </div>
                                        <div className="h-[300px]">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <ComposedChart data={historyCompareData} syncId="historyGraph">
                                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                                    <XAxis dataKey="date" stroke="#64748b" tick={{fontSize: 10}} />
                                                    <YAxis yAxisId="left" stroke="#64748b" tick={{fontSize: 10}} unit="%" domain={[0, 100]} />
                                                    <YAxis yAxisId="right" orientation="right" stroke="#fbbf24" tick={{fontSize: 10}} unit="%" domain={[0, 100]} />
                                                    <Tooltip 
                                                        position={{ y: 0 }}
                                                        contentStyle={{backgroundColor: '#0f172a', borderColor: '#334155'}} 
                                                        formatter={(val: number, name: string, props: any) => {
                                                            if (name === '主力交易占比') return val.toFixed(1) + '%';
                                                            let amount = 0;
                                                            if (name === '主力买入占比') amount = props.payload.main_buy_amount;
                                                            if (name === '主力卖出占比') amount = props.payload.main_sell_amount;
                                                            return `${val.toFixed(1)}% (${(amount/100000000).toFixed(2)}亿)`;
                                                        }} 
                                                    />
                                                    <Legend wrapperStyle={{fontSize: 12}} />
                                                    <Area yAxisId="left" type="monotone" dataKey="buyRatio" name="主力买入占比" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.1} />
                                                    <Area yAxisId="left" type="monotone" dataKey="sellRatio" name="主力卖出占比" stackId="2" stroke="#22c55e" fill="#22c55e" fillOpacity={0.1} />
                                                    <Line yAxisId="right" type="monotone" dataKey="activityRatio" name="主力交易占比" stroke="#fbbf24" strokeWidth={2} dot={false} />
                                                </ComposedChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default HistoryView;
