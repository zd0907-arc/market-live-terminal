import React, { useEffect, useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, ReferenceDot
} from 'recharts';
import { Info, HelpCircle } from 'lucide-react';

interface Signal {
  type: string;
  signal: string;
  level: string;
  detail: string;
}

interface SentimentPoint {
  timestamp: string;
  cvd: number;
  oib: number;
  price: number;
  signals?: Signal[];
}

interface SentimentTrendProps {
  symbol: string;
}

const SentimentTrend: React.FC<SentimentTrendProps> = ({ symbol }) => {
  const [data, setData] = useState<SentimentPoint[]>([]);
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Backend API is on port 8000
        const res = await fetch(`http://localhost:8000/api/monitor/history?symbol=${symbol}`);
        const json = await res.json();
        if (json.code === 200) {
            // Filter data to trading hours only (09:30 - 15:00)
            const filteredData = json.data.filter((d: any) => d.timestamp <= '15:00:05').map((d: any) => ({
                ...d,
                signals: d.signals ? JSON.parse(d.signals) : []
            }));
            setData(filteredData);
        }
      } catch (e) {
        console.error(e);
      }
    };
    
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [symbol]);

  const formatYAxis = (tick: number) => {
    if (Math.abs(tick) >= 10000) return `${(tick/10000).toFixed(1)}w`;
    return tick.toString();
  };

  const gradientOffset = () => {
    if (data.length === 0) return 0;
    const max = Math.max(...data.map(i => i.cvd));
    const min = Math.min(...data.map(i => i.cvd));
    if (max <= 0) return 0;
    if (min >= 0) return 1;
    return max / (max - min);
  };
  
  const off = gradientOffset();

  // Custom Tooltip for Chart
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload as SentimentPoint;
      return (
        <div className="bg-slate-900 border border-slate-700 p-2 rounded shadow-xl text-xs z-50">
          <div className="text-slate-400 mb-1">{label}</div>
          {payload.map((p: any) => (
            <div key={p.name} style={{ color: p.color }} className="mb-1">
              {p.name === 'cvd' ? '实战博弈' : '潜在意愿'}: {p.value.toLocaleString()} 手
            </div>
          ))}
          {point.signals && point.signals.length > 0 && (
            <div className="mt-2 pt-2 border-t border-slate-800">
                {point.signals.map((s, idx) => (
                    <div key={idx} className="mb-1">
                        <div className="font-bold text-yellow-400 flex items-center gap-1">
                            {s.signal}
                        </div>
                        <div className="text-slate-300 scale-90 origin-left">{s.detail}</div>
                    </div>
                ))}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full w-full">
        {/* CVD Chart */}
        <div className="flex-1 min-h-0 mb-2 bg-slate-900/50 rounded-lg p-2 border border-slate-800/50 relative">
            <div className="flex justify-between items-center mb-1 px-1">
                <div className="flex items-center gap-1.5 group relative">
                    <h4 className="text-xs font-bold text-slate-200">实战博弈 (CVD资金流)</h4>
                    <Info className="w-3 h-3 text-slate-500 cursor-help hover:text-blue-400" />
                    
                    {/* Tooltip */}
                    <div className="absolute left-0 bottom-full mb-2 w-64 p-3 bg-slate-950 border border-slate-700 rounded-lg shadow-xl text-[11px] leading-relaxed text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                        <div className="font-bold text-white mb-1">CVD (Cumulative Volume Delta)</div>
                        通过计算逐笔成交的主动买入与主动卖出差额的累积值，反映市场资金的实际流向。<br/>
                        <span className="text-red-400">红色上行</span>：多头资金主导买入。<br/>
                        <span className="text-green-400">绿色下行</span>：空头资金主导卖出。
                    </div>
                </div>
                
                {/* Joint Analysis Help */}
                <div className="group relative">
                    <HelpCircle className="w-3 h-3 text-slate-500 cursor-help hover:text-yellow-400" />
                    <div className="absolute right-0 top-4 w-[280px] p-3 bg-slate-950 border border-slate-700 rounded-lg shadow-xl text-[11px] text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                        <div className="font-bold text-white mb-2 text-center border-b border-slate-800 pb-1">联合研判决策矩阵</div>
                        <div className="grid grid-cols-3 gap-1 mb-1 text-slate-500 text-[10px] text-center">
                            <div>实战(CVD)</div>
                            <div>意愿(OIB)</div>
                            <div>结论</div>
                        </div>
                        <div className="grid grid-cols-3 gap-1 mb-1 items-center text-center border-b border-slate-800/50 pb-1">
                            <div className="text-red-400">📈 持续上升</div>
                            <div className="text-green-400">📉 转绿</div>
                            <div className="text-white font-bold">真突破</div>
                        </div>
                        <div className="text-[10px] text-slate-400 mb-2">主力真买且吃光卖单，阻力变小 → <span className="text-red-400">买入</span></div>
                        
                        <div className="grid grid-cols-3 gap-1 mb-1 items-center text-center border-b border-slate-800/50 pb-1">
                            <div className="text-green-400">📉 下降/平</div>
                            <div className="text-red-400">📈 大幅上升</div>
                            <div className="text-white font-bold">假支撑</div>
                        </div>
                        <div className="text-[10px] text-slate-400 mb-2">没人真买但挂单巨大，托单出货 → <span className="text-green-400">快跑</span></div>

                        <div className="grid grid-cols-3 gap-1 mb-1 items-center text-center border-b border-slate-800/50 pb-1">
                            <div className="text-red-400">📈 缓慢上升</div>
                            <div className="text-green-400">📉 巨量绿色</div>
                            <div className="text-white font-bold">吸筹压盘</div>
                        </div>
                        <div className="text-[10px] text-slate-400">暗中吃货但压价，压单消失即起飞 → <span className="text-blue-400">关注</span></div>
                    </div>
                </div>
            </div>
            <ResponsiveContainer width="100%" height="85%">
                <AreaChart data={data} syncId="sentimentId" margin={{top: 5, right: 5, left: -20, bottom: 0}}>
                    <defs>
                        <linearGradient id={`splitColor-${symbol}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset={off} stopColor="#ef4444" stopOpacity={0.4}/>
                            <stop offset={off} stopColor="#22c55e" stopOpacity={0.4}/>
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} stroke="#334155" />
                    <XAxis dataKey="timestamp" hide />
                    <YAxis tickFormatter={formatYAxis} style={{fontSize: '10px'}} tick={{fill: '#64748b'}} />
                    <Tooltip content={<CustomTooltip />} />
                    <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                    <Area type="monotone" dataKey="cvd" stroke="#94a3b8" strokeWidth={1} fill={`url(#splitColor-${symbol})`} isAnimationActive={false} />
                    {/* Render Signals */}
                    {data.map((entry, index) => {
                        if (entry.signals && entry.signals.length > 0) {
                            // Get the most severe signal emoji
                            const emoji = entry.signals[0].type.includes('ICEBERG') ? '🧊' 
                                        : entry.signals[0].type.includes('SPOOFING') ? '👻' 
                                        : '⚠️';
                            
                            return (
                                <ReferenceDot 
                                    key={`signal-${index}`} 
                                    x={entry.timestamp} 
                                    y={entry.cvd} 
                                    r={3} 
                                    fill="#facc15" 
                                    stroke="none"
                                    isFront={true}
                                    label={{ position: 'top', value: emoji, fontSize: 14, fill: '#fff' }}
                                />
                            );
                        }
                        return null;
                    })}
                </AreaChart>
            </ResponsiveContainer>
        </div>

        {/* OIB Chart */}
        <div className="flex-1 min-h-0 bg-slate-900/50 rounded-lg p-2 border border-slate-800/50">
             <div className="flex justify-between items-center mb-1 px-1">
                <div className="flex items-center gap-1.5 group relative">
                    <h4 className="text-xs font-bold text-slate-200">潜在意愿 (OIB委差)</h4>
                    <Info className="w-3 h-3 text-slate-500 cursor-help hover:text-blue-400" />

                    {/* Tooltip */}
                    <div className="absolute left-0 bottom-full mb-2 w-64 p-3 bg-slate-950 border border-slate-700 rounded-lg shadow-xl text-[11px] leading-relaxed text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                        <div className="font-bold text-white mb-1">OIB (Order Imbalance)</div>
                        通过盘口<span className="text-yellow-400">买一至买五</span>与<span className="text-yellow-400">卖一至卖五</span>挂单总量的差额，反映市场潜在的挂单意愿。<br/>
                        <span className="text-red-400">红柱</span>：买盘挂单意愿强。<br/>
                        <span className="text-green-400">绿柱</span>：卖盘挂单意愿强。
                    </div>
                </div>
                <div className="text-[10px] text-slate-500">红:买强 绿:卖强</div>
            </div>
            <ResponsiveContainer width="100%" height="85%">
                <BarChart data={data} syncId="sentimentId" margin={{top: 5, right: 5, left: -20, bottom: 0}}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} stroke="#334155" />
                    <XAxis dataKey="timestamp" style={{fontSize: '10px'}} tick={{fill: '#64748b'}} minTickGap={30} />
                    <YAxis tickFormatter={formatYAxis} style={{fontSize: '10px'}} tick={{fill: '#64748b'}} />
                    <Tooltip content={<CustomTooltip />} cursor={{fill: 'rgba(255,255,255,0.05)'}} />
                    <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                    <Bar dataKey="oib" isAnimationActive={false}>
                        {
                            data.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.oib > 0 ? '#ef4444' : '#22c55e'} />
                            ))
                        }
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    </div>
  );
};

export default SentimentTrend;
