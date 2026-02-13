import React, { useEffect, useState, useMemo } from 'react';
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, ReferenceDot, Line
} from 'recharts';
import { Info, HelpCircle } from 'lucide-react';

interface Signal {
  type: string;
  signal: string;
  level: string;
  detail: string;
}

interface SentimentPoint {
  timestamp: string; // HH:MM:SS or HH:MM (history)
  cvd: number;
  oib: number;
  price: number;
  signals?: Signal[];
  bid1_vol?: number;
  ask1_vol?: number;
  tick_vol?: number;
}

interface SentimentTrendProps {
  symbol: string;
}

const SentimentTrend: React.FC<SentimentTrendProps> = ({ symbol }) => {
  const [historyData, setHistoryData] = useState<SentimentPoint[]>([]);
  const [liveData, setLiveData] = useState<SentimentPoint | null>(null);

  // 1. Initial Load: History
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/sentiment/history?symbol=${symbol}`);
        const json = await res.json();
        if (json.code === 200) {
           // Ensure signals are parsed
           const parsed = json.data.map((d: any) => ({
               ...d,
               signals: typeof d.signals === 'string' ? JSON.parse(d.signals) : (d.signals || [])
           }));
           setHistoryData(parsed);
        }
      } catch (e) {
        console.error("Fetch history failed", e);
      }
    };
    fetchHistory();
  }, [symbol]);

  // 2. Polling: Realtime (3s)
  useEffect(() => {
    const fetchLive = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/sentiment?symbol=${symbol}`);
        const json = await res.json();
        if (json.code === 200 && json.data) {
            const raw = json.data;
            const livePoint: SentimentPoint = {
                timestamp: raw.timestamp,
                cvd: raw.cvd,
                oib: raw.oib,
                price: raw.price,
                signals: typeof raw.signals === 'string' ? JSON.parse(raw.signals) : (raw.signals || []),
                // Fix: Assign missing fields
                bid1_vol: raw.bid1_vol,
                ask1_vol: raw.ask1_vol,
                tick_vol: raw.tick_vol
            };
            
            setLiveData(prev => {
                // If minute changed, we should probably re-fetch history or commit prev to history
                // For simplicity, we just update liveData. 
                // In a perfect world, we'd append to history locally.
                if (prev && prev.timestamp.substring(0,5) !== livePoint.timestamp.substring(0,5)) {
                    // Minute changed, trigger history refresh
                     fetch(`http://localhost:8000/api/sentiment/history?symbol=${symbol}`)
                        .then(r => r.json())
                        .then(j => {
                            if (j.code === 200) {
                                const parsed = j.data.map((d: any) => ({
                                    ...d,
                                    signals: typeof d.signals === 'string' ? JSON.parse(d.signals) : (d.signals || [])
                                }));
                                setHistoryData(parsed);
                            }
                        });
                }
                return livePoint;
            });
        }
      } catch (e) {
        console.error(e);
      }
    };

    const interval = setInterval(fetchLive, 3000);
    return () => clearInterval(interval);
  }, [symbol]);

  // Merge Data
  const chartData = useMemo(() => {
      // 1. Filter Time
      const filtered = historyData.filter(d => {
          if (d.timestamp < '09:15' || d.timestamp > '15:00') return false;
          if (d.timestamp > '11:30' && d.timestamp < '13:00') return false;
          return true;
      });
      
      // 2. OIB Smart Truncation
      if (filtered.length === 0) return [];
      
      const oibValues = filtered.map(d => Math.abs(d.oib));
      const mean = oibValues.reduce((a, b) => a + b, 0) / oibValues.length;
      const LIMIT = mean * 3; // Threshold: 3x Mean
      
      return filtered.map(d => {
          const isClipped = Math.abs(d.oib) > LIMIT;
          return {
              ...d,
              oib: isClipped ? (d.oib > 0 ? LIMIT : -LIMIT) : d.oib, // Truncate for display
              oib_real: d.oib, // Store real value
              is_clipped: isClipped
          };
      });
  }, [historyData]);

  const formatYAxis = (tick: any) => {
    if (tick === undefined || tick === null) return '';
    if (typeof tick !== 'number') return String(tick);
    if (Math.abs(tick) >= 10000) return `${(tick/10000).toFixed(1)}w`;
    return tick.toString();
  };

  const gradientOffset = () => {
    if (!chartData || chartData.length === 0) return 0;
    const max = Math.max(...chartData.map(i => i.cvd));
    const min = Math.min(...chartData.map(i => i.cvd));
    if (max <= 0) return 0;
    if (min >= 0) return 1;
    if (max === min) return 0; // Prevent NaN
    return max / (max - min);
  };
  
  const off = gradientOffset();

  // Custom Tooltip (V3.0 Design)
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload as SentimentPoint;
      
      // Smart Truncation: Use real value for display if clipped
      const oibVal = point.oib_real !== undefined ? point.oib_real : point.oib;
      
      // Check for V3 signals
      const aggBuy = point.signals?.find(s => s.type === 'AGGRESSIVE_BUY');
      const heavyPressure = point.signals?.find(s => s.type === 'HEAVY_PRESSURE');
      const bullSupport = point.signals?.find(s => s.type === 'BULLISH_SUPPORT');
      
      return (
        <div className="bg-slate-950 border border-slate-700 p-3 rounded-lg shadow-2xl text-xs z-50 max-w-[250px]">
          <div className="text-slate-400 mb-2 border-b border-slate-800 pb-1 flex justify-between">
            <span>{point.timestamp}</span>
            <span className={point.cvd > 0 ? "text-red-400" : "text-green-400"}>
                CVD: {point.cvd.toFixed(0)}
            </span>
          </div>

          {/* V3 Signal Cards */}
          {aggBuy && (
              <div className="mb-3 bg-red-900/20 border-l-2 border-red-500 pl-2 py-1">
                  <div className="flex items-center gap-1 font-bold text-red-400 text-sm mb-1">
                      <span>🔥</span> 主力抢筹
                  </div>
                  <div className="text-slate-300 mb-1">现象：巨额压单被暴力吃掉，价格不跌反涨。</div>
                  <div className="text-yellow-500/80 text-[10px]">⚠️ 风险：若CVD后续走平，警惕假突破。</div>
              </div>
          )}
          
          {heavyPressure && (
              <div className="mb-3 bg-gray-800/50 border-l-2 border-gray-400 pl-2 py-1">
                  <div className="flex items-center gap-1 font-bold text-gray-300 text-sm mb-1">
                      <span>🧱</span> 抛压沉重
                  </div>
                  <div className="text-slate-300 mb-1">现象：上方阻力巨大，买方吃不动。</div>
                  <div className="text-yellow-500/80 text-[10px]">⚠️ 风险：建议观望，若放量突破才可介入。</div>
              </div>
          )}

          {bullSupport && (
              <div className="mb-3 bg-green-900/20 border-l-2 border-green-500 pl-2 py-1">
                  <div className="flex items-center gap-1 font-bold text-green-400 text-sm mb-1">
                      <span>🛡️</span> 主力护盘
                  </div>
                  <div className="text-slate-300 mb-1">现象：下方有隐形托单，砸不下去。</div>
              </div>
          )}

          {/* Fallback for normal data */}
          {!aggBuy && !heavyPressure && !bullSupport && (
              <div className="grid grid-cols-2 gap-2 text-slate-300">
                  <div>价格: <span className="text-yellow-400">{point.price}</span></div>
                  <div>意愿: <span className={oibVal > 0 ? "text-red-400" : "text-green-400"}>{oibVal.toFixed(0)}</span></div>
              </div>
          )}
        </div>
      );
    }
    return null;
  };

  // usePrevious Hook
  const usePrevious = <T,>(value: T): T | undefined => {
      const ref = React.useRef<T>();
      useEffect(() => {
          ref.current = value;
      });
      return ref.current;
  };
  
  const prevPrice = usePrevious(liveData?.price);
  
  // 3. Persistent Direction State (for static background)
  const [lastDirection, setLastDirection] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
      if (liveData?.price && prevPrice) {
          if (liveData.price > prevPrice) setLastDirection('up');
          else if (liveData.price < prevPrice) setLastDirection('down');
      }
  }, [liveData?.price, prevPrice]);
  
  // Calculate Momentum Class
  const momentumClass = useMemo(() => {
      if (!liveData || !prevPrice) return '';
      if (liveData.price > prevPrice) return 'flash-red';
      if (liveData.price < prevPrice) return 'flash-green';
      return '';
  }, [liveData?.price, prevPrice]);

  return (
    <div className="flex h-full w-full gap-1">
        <style>{`
          @keyframes flash-red { 0% { background-color: rgba(239, 68, 68, 0.3); } 100% { background-color: transparent; } }
          @keyframes flash-green { 0% { background-color: rgba(34, 197, 94, 0.3); } 100% { background-color: transparent; } }
          .flash-red { animation: flash-red 1s ease-out; }
          .flash-green { animation: flash-green 1s ease-out; }
          
          @keyframes pulse-red { 0% { opacity: 1; box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); } 70% { opacity: 1; box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); } 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); } }
          @keyframes pulse-green { 0% { opacity: 1; box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); } 70% { opacity: 1; box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); } 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); } }
          .animate-pulse-red { animation: pulse-red 2s infinite; }
          .animate-pulse-green { animation: pulse-green 2s infinite; }
        `}</style>

        {/* Left Column: Charts */}
        <div className="flex-1 flex flex-col min-w-0">
            {/* CVD Chart Container */}
            <div className="flex-1 min-h-0 mb-1 bg-slate-900/50 rounded-lg p-2 border border-slate-800/50 relative">
                <div className="flex justify-between items-center mb-1 px-1">
                    <div className="flex items-center gap-1.5 group relative">
                        <h4 className="text-xs font-bold text-slate-200">实战博弈 (CVD资金流)</h4>
                        <Info className="w-3 h-3 text-slate-500 cursor-help hover:text-blue-400" />
                        <div className="absolute left-0 bottom-full mb-2 w-64 p-3 bg-slate-950 border border-slate-700 rounded-lg shadow-xl text-[11px] leading-relaxed text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                            <div className="font-bold text-white mb-1">V3.0 实战博弈系统</div>
                            <div className="mb-1"><span className="text-red-400">🔥 主力抢筹</span>：大单压不住，暴力上攻。</div>
                            <div className="mb-1"><span className="text-gray-400">🧱 抛压沉重</span>：买不动，阻力大。</div>
                            <div><span className="text-green-400">🛡️ 主力护盘</span>：跌不动，有人托。</div>
                        </div>
                    </div>
                </div>
                
                <ResponsiveContainer width="100%" height="85%">
                    <AreaChart data={chartData} syncId="sentimentId" margin={{top: 5, right: 0, left: -10, bottom: 0}}>
                        <defs>
                            <linearGradient id={`splitColor-${symbol}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset={off} stopColor="#ef4444" stopOpacity={0.4}/>
                                <stop offset={off} stopColor="#22c55e" stopOpacity={0.4}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.1} stroke="#334155" />
                        <XAxis dataKey="timestamp" hide />
                        <YAxis yAxisId="left" tickFormatter={formatYAxis} style={{fontSize: '10px'}} tick={{fill: '#64748b'}} />
                        <YAxis yAxisId="right" orientation="right" domain={['auto', 'auto']} hide />
                        <Tooltip content={<CustomTooltip />} />
                        <ReferenceLine y={0} yAxisId="left" stroke="#475569" strokeDasharray="3 3" />
                        
                        {/* CVD Area (Left Axis) - No Stroke */}
                        <Area yAxisId="left" type="monotone" dataKey="cvd" stroke="none" fill={`url(#splitColor-${symbol})`} isAnimationActive={false} />
                        
                        {/* Price Line (Right Axis) */}
                        <Line yAxisId="right" type="monotone" dataKey="price" stroke="#facc15" strokeWidth={2} dot={false} connectNulls={true} />
                        
                        {/* Render History Signals */}
                        {chartData.map((entry, index) => {
                            const aggBuy = entry.signals?.some(s => s.type === 'AGGRESSIVE_BUY');
                            const heavy = entry.signals?.some(s => s.type === 'HEAVY_PRESSURE');
                            const support = entry.signals?.some(s => s.type === 'BULLISH_SUPPORT');
                            
                            if (aggBuy) return <ReferenceDot yAxisId="left" key={index} x={entry.timestamp} y={entry.cvd} r={4} fill="none" stroke="none" label={{ position: 'top', value: '🔥', fontSize: 16 }} />;
                            if (heavy) return <ReferenceDot yAxisId="left" key={index} x={entry.timestamp} y={entry.cvd} r={4} fill="none" stroke="none" label={{ position: 'top', value: '🧱', fontSize: 16 }} />;
                            if (support) return <ReferenceDot yAxisId="left" key={index} x={entry.timestamp} y={entry.cvd} r={4} fill="none" stroke="none" label={{ position: 'top', value: '🛡️', fontSize: 16 }} />;
                            return null;
                        })}
                    </AreaChart>
                </ResponsiveContainer>
            </div>

            {/* OIB Chart (Simplified for V3) */}
            <div className="flex-1 min-h-0 bg-slate-900/50 rounded-lg p-2 border border-slate-800/50">
                 <div className="flex justify-between items-center mb-1 px-1">
                    <h4 className="text-xs font-bold text-slate-200">潜在意愿 (OIB)</h4>
                </div>
                <ResponsiveContainer width="100%" height="85%">
                    <BarChart data={chartData} syncId="sentimentId" margin={{top: 5, right: 0, left: -10, bottom: 0}}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.1} stroke="#334155" />
                        <XAxis dataKey="timestamp" style={{fontSize: '10px'}} tick={{fill: '#64748b'}} minTickGap={30} />
                        <YAxis tickFormatter={formatYAxis} style={{fontSize: '10px'}} tick={{fill: '#64748b'}} />
                        <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} content={() => null} /> 
                        <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                        <Bar dataKey="oib" isAnimationActive={false}>
                            {chartData.map((entry, index) => (
                                <Cell 
                                    key={`cell-${index}`} 
                                    fill={entry.oib > 0 ? '#ef4444' : '#22c55e'} 
                                    fillOpacity={entry.is_clipped ? 0.6 : 1}
                                    stroke={entry.is_clipped ? (entry.oib > 0 ? '#ef4444' : '#22c55e') : 'none'}
                                    strokeDasharray={entry.is_clipped ? "2 2" : undefined}
                                />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>

        {/* Right Column: Full-height Micro-Stethoscope Panel (60px) */}
        <div className="w-[60px] bg-slate-900/80 rounded-lg border border-slate-700/50 flex flex-col relative overflow-hidden">
             <div className="absolute inset-0 border-2 border-slate-700/30 pointer-events-none" />
             
             {liveData ? (
                <>
                     {/* A. Top Layer (25%): Instant Price & Momentum */}
                     <div className="flex-1 flex flex-col items-center justify-center border-b border-slate-700/30 relative overflow-hidden">
                        {/* Static Background Layer */}
                        <div className={`absolute inset-0 transition-colors duration-500 pointer-events-none 
                            ${lastDirection === 'up' ? 'bg-red-500/10' : ''} 
                            ${lastDirection === 'down' ? 'bg-green-500/10' : ''}
                        `} />
                        
                        {/* Flash Layer */}
                        <div className={`absolute inset-0 pointer-events-none ${momentumClass}`} />

                        <div className="text-[9px] text-slate-500 absolute top-1 z-10">实时</div>
                        <div className="text-yellow-400 font-bold text-sm mt-2 z-10">{liveData.price.toFixed(2)}</div>
                     </div>

                     {/* B. Middle Layer (50%): Bid-Ask Ratio Gauge */}
                     <div className="flex-[2] flex flex-col items-center justify-center border-b border-slate-700/30 py-1 gap-1">
                        {/* Ask Volume (Pressure) */}
                        <div className="text-[8px] text-green-400 leading-none text-center">
                            压:{formatYAxis(liveData.ask1_vol || 0)}
                        </div>
                        
                        {/* Vertical Gauge */}
                        <div className="w-1.5 flex-1 bg-slate-800 rounded-full overflow-hidden relative flex flex-col">
                             {/* Ask (Green) - Top */}
                             <div 
                                className="w-full bg-green-500 transition-all duration-300"
                                style={{ height: `${(liveData.ask1_vol || 0) / ((liveData.bid1_vol || 1) + (liveData.ask1_vol || 1)) * 100}%` }}
                             />
                             {/* Divider Cursor */}
                             <div className="h-[1px] w-full bg-white z-10 shadow-[0_0_2px_rgba(255,255,255,0.8)]" />
                             {/* Bid (Red) - Bottom */}
                             <div 
                                className="w-full bg-red-500 transition-all duration-300 flex-1"
                             />
                        </div>
                        
                        {/* Bid Volume (Support) */}
                        <div className="text-[8px] text-red-400 leading-none text-center">
                            托:{formatYAxis(liveData.bid1_vol || 0)}
                        </div>
                     </div>

                     {/* C. Bottom Layer (25%): Tick Velocity */}
                     <div className="flex-1 flex flex-col items-center justify-center bg-slate-800/20">
                        <div className="text-[9px] text-slate-500 mb-0.5">Tick</div>
                        <div className={`text-xs font-bold flex items-center gap-0.5 ${(liveData.tick_vol || 0) > 1000 ? 'text-yellow-400 animate-pulse' : 'text-slate-200'}`}>
                            {(liveData.tick_vol || 0) > 1000 && <span className="text-[10px]">⚡️</span>}
                            {liveData.tick_vol || 0}
                        </div>
                     </div>
                </>
             ) : (
                <div className="flex items-center justify-center h-full text-slate-600 text-[10px]">等待...</div>
             )}
        </div>
    </div>
  );
};

export default SentimentTrend;
