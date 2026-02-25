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

const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        const bull = payload.find((p: any) => p.dataKey === 'bull_vol')?.value || 0;
        const bear = payload.find((p: any) => p.dataKey === 'bear_vol')?.value || 0;
        const heat = payload.find((p: any) => p.dataKey === 'total_heat')?.value || 0;
        const total = bull + bear;

        return (
            <div className="bg-slate-900 border border-slate-700 p-2 rounded shadow-lg text-[11px] min-w-[120px]">
                <div className="text-slate-400 mb-2">{label}</div>
                <div className="flex justify-between items-center mb-1">
                    <span className="text-red-500 flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500"></span>看多评论:</span>
                    <span className="font-bold text-slate-200">{bull} 条</span>
                </div>
                <div className="flex justify-between items-center mb-1">
                    <span className="text-green-500 flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500"></span>看空评论:</span>
                    <span className="font-bold text-slate-200">{bear} 条</span>
                </div>
                <div className="flex justify-between items-center mt-2 pt-1 border-t border-slate-700">
                    <span className="text-slate-300">总发帖量:</span>
                    <span className="font-bold text-white">{total} 条</span>
                </div>
                <div className="flex justify-between items-center mt-1">
                    <span className="text-yellow-500">综合热度:</span>
                    <span className="font-bold text-yellow-500">{typeof heat === 'number' ? heat.toFixed(0) : heat}</span>
                </div>
            </div>
        );
    }
    return null;
};

const SentimentTrendChart: React.FC<SentimentTrendChartProps> = ({ data }) => {
    return (
        <div className="h-full w-full bg-transparent">
            <h3 className="text-slate-200 font-bold text-xs mb-1 ml-1 absolute top-1 left-1 z-10">散户情绪与发帖趋势 (72H)</h3>
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
                        tick={{ fontSize: 9, fill: '#64748b' }}
                        tickFormatter={(time) => time.split(' ')[1]}
                        axisLine={{ stroke: '#334155' }}
                        tickLine={false}
                        interval="preserveStartEnd"
                        minTickGap={30}
                    />

                    <YAxis
                        yAxisId="left"
                        tick={{ fill: '#64748b', fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        width={25}
                    />

                    <YAxis
                        yAxisId="right"
                        orientation="right"
                        tick={{ fill: '#64748b', fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                        width={25}
                    />

                    <Tooltip
                        content={<CustomTooltip />}
                        cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                    />

                    <Legend
                        verticalAlign="top"
                        align="right"
                        height={20}
                        iconSize={8}
                        wrapperStyle={{ top: 0, right: 0, fontSize: '10px', color: '#94a3b8' }}
                    />

                    {/* Make Bear Vol green and at the bottom, Bull Vol red and at the top of the stack */}
                    <Bar yAxisId="left" dataKey="bear_vol" stackId="a" fill="#22c55e" name="看空评论" barSize={12} />
                    <Bar yAxisId="left" dataKey="bull_vol" stackId="a" fill="#ef4444" name="看多评论" barSize={12} radius={[2, 2, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="total_heat" stroke="#eab308" strokeWidth={1.5} name="综合热度" dot={false} activeDot={{ r: 3 }} />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
};

export default SentimentTrendChart;
