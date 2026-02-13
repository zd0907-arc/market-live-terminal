import React from 'react';
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { SentimentTrendPoint } from '../../services/sentimentService';

interface SentimentTrendChartProps {
    data: SentimentTrendPoint[];
}

const SentimentTrendChart: React.FC<SentimentTrendChartProps> = ({ data }) => {
    return (
        <div className="h-full w-full bg-transparent">
            <h3 className="text-slate-200 font-bold text-xs mb-1 ml-1 absolute top-1 left-1 z-10">散户情绪热度趋势 (72H)</h3>
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                    data={data}
                    margin={{
                        top: 25, // Leave space for title
                        right: 5,
                        bottom: 0,
                        left: 0,
                    }}
                >
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" vertical={false} opacity={0.5} />
                    
                    <XAxis 
                        dataKey="time_bucket" 
                        scale="band" 
                        tick={{fontSize: 9, fill: '#64748b'}}
                        tickFormatter={(time) => time.split(' ')[1]} 
                        axisLine={{ stroke: '#334155' }}
                        tickLine={false}
                        interval="preserveStartEnd"
                        minTickGap={30}
                    />
                    
                    <YAxis 
                        yAxisId="left" 
                        // label={{ value: '热度', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} 
                        tick={{ fill: '#64748b', fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        width={25}
                    />
                    
                    <YAxis 
                        yAxisId="right" 
                        orientation="right" 
                        // label={{ value: '多空比', angle: 90, position: 'insideRight', fill: '#64748b', fontSize: 10 }} 
                        tick={{ fill: '#64748b', fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        width={25}
                    />
                    
                    <Tooltip 
                        contentStyle={{ 
                            backgroundColor: '#0f172a', 
                            borderColor: '#1e293b', 
                            color: '#f1f5f9', 
                            borderRadius: '4px', 
                            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
                            fontSize: '11px',
                            padding: '4px 8px'
                        }}
                        itemStyle={{ padding: 0 }}
                        formatter={(value: any, name: any) => {
                            if (name === 'total_heat') return [value, '热度'];
                            if (name === 'bull_bear_ratio') return [value, '多空比'];
                            return [value, name];
                        }}
                        labelFormatter={(label) => `${label}`}
                        labelStyle={{ color: '#94a3b8', marginBottom: '2px' }}
                    />
                    
                    <Legend 
                        verticalAlign="top" 
                        align="right"
                        height={20} 
                        iconSize={8}
                        wrapperStyle={{ top: 0, right: 0, fontSize: '10px', color: '#94a3b8' }}
                    />
                    
                    <Bar yAxisId="left" dataKey="total_heat" barSize={12} fill="#60a5fa" name="情绪热度" radius={[2, 2, 0, 0]} fillOpacity={0.8} />
                    <Line yAxisId="right" type="monotone" dataKey="bull_bear_ratio" stroke="#f59e0b" strokeWidth={1.5} name="多空比" dot={false} activeDot={{ r: 3 }} />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
};

export default SentimentTrendChart;
