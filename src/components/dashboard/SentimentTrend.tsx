import React, { useEffect, useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid
} from 'recharts';

interface SentimentPoint {
  timestamp: string;
  cvd: number;
  oib: number;
  price: number;
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
            setData(json.data);
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

  return (
    <div className="flex flex-col h-full w-full bg-white dark:bg-gray-800 p-2 rounded shadow">
        {/* CVD Chart */}
        <div className="flex-1 min-h-0 mb-2">
            <div className="flex justify-between items-center mb-1 px-2">
                <h4 className="text-xs font-bold text-gray-700 dark:text-gray-200">实战博弈 (CVD资金流)</h4>
                <div className="text-[10px] text-gray-500">红:多头主导 绿:空头主导</div>
            </div>
            <ResponsiveContainer width="100%" height="90%">
                <AreaChart data={data} syncId="sentimentId" margin={{top: 5, right: 5, left: -20, bottom: 0}}>
                    <defs>
                        <linearGradient id="splitColor" x1="0" y1="0" x2="0" y2="1">
                            <stop offset={off} stopColor="#F6465D" stopOpacity={0.8}/>
                            <stop offset={off} stopColor="#2EBD85" stopOpacity={0.8}/>
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="timestamp" hide />
                    <YAxis tickFormatter={formatYAxis} style={{fontSize: '10px'}} tick={{fill: '#666'}} />
                    <Tooltip 
                        contentStyle={{backgroundColor: 'rgba(255, 255, 255, 0.9)', border: '1px solid #ccc', fontSize: '12px'}}
                        labelStyle={{color: '#333'}}
                        formatter={(value: number) => [value.toLocaleString(), '手数']}
                    />
                    <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />
                    <Area type="monotone" dataKey="cvd" stroke="#888" fill="url(#splitColor)" isAnimationActive={false} />
                </AreaChart>
            </ResponsiveContainer>
        </div>

        {/* OIB Chart */}
        <div className="flex-1 min-h-0">
             <div className="flex justify-between items-center mb-1 px-2">
                <h4 className="text-xs font-bold text-gray-700 dark:text-gray-200">潜在意愿 (OIB委差)</h4>
                <div className="text-[10px] text-gray-500">红:买盘强 绿:卖盘强</div>
            </div>
            <ResponsiveContainer width="100%" height="90%">
                <BarChart data={data} syncId="sentimentId" margin={{top: 5, right: 5, left: -20, bottom: 0}}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="timestamp" style={{fontSize: '10px'}} tick={{fill: '#666'}} minTickGap={30} />
                    <YAxis tickFormatter={formatYAxis} style={{fontSize: '10px'}} tick={{fill: '#666'}} />
                    <Tooltip 
                         contentStyle={{backgroundColor: 'rgba(255, 255, 255, 0.9)', border: '1px solid #ccc', fontSize: '12px'}}
                         cursor={{fill: 'rgba(0,0,0,0.1)'}}
                         formatter={(value: number) => [value.toLocaleString(), '手数']}
                    />
                    <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />
                    <Bar dataKey="oib" isAnimationActive={false}>
                        {
                            data.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.oib > 0 ? '#F6465D' : '#2EBD85'} />
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
