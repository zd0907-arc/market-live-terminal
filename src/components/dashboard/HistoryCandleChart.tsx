import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { HistoryTrendData } from '../../types';

interface HistoryCandleChartProps {
    data: HistoryTrendData[];
    height?: number;
    priceRange?: [number | 'auto', number | 'auto'];
}

const HistoryCandleChart: React.FC<HistoryCandleChartProps> = ({ data, height = 400, priceRange = ['dataMin', 'dataMax'] }) => {

    const option = useMemo(() => {
        if (!data || data.length === 0) return {};

        const dates = data.map(item => item.time.substring(5, 16)); // MM-DD HH:MM

        // K-Line Data: [Open, Close, Low, High]
        // ECharts expects [Open, Close, Lowest, Highest]
        const kLineData = data.map(item => [
            item.open || item.close || 0, // Fallback to close if open is missing
            item.close || 0,
            item.low || item.close || 0,
            item.high || item.close || 0
        ]);

        const netInflowData = data.map(item => item.net_inflow || 0);
        const positiveNetInflowData = data.map(item => (item.net_inflow || 0) > 0 ? item.net_inflow : 0);
        const negativeNetInflowData = data.map(item => (item.net_inflow || 0) <= 0 ? item.net_inflow : 0);
        const superNetData = data.map(item => item.super_net || 0);

        return {
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross',
                    label: {
                        backgroundColor: '#6a7985'
                    }
                },
                backgroundColor: 'rgba(15, 23, 42, 0.9)', // slate-900
                borderColor: '#334155', // slate-700
                textStyle: {
                    color: '#e2e8f0' // slate-200
                },
                formatter: function (params: any) {
                    if (!params || params.length === 0) return '';
                    const dataIndex = params[0].dataIndex;
                    const rawItem = data[dataIndex];

                    let result = `<div style="font-size:12px; font-weight:bold; margin-bottom:4px;">${params[0].axisValue}</div>`;

                    // Main Net Inflow
                    const netColor = (rawItem.net_inflow || 0) >= 0 ? '#ef4444' : '#22c55e';
                    const netVal = ((rawItem.net_inflow || 0) / 10000).toFixed(1) + '万';
                    const netMarker = `<span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${netColor};"></span>`;
                    result += `<div style="display:flex; justify-content:space-between; gap:12px; font-size:11px;">
                        <span>${netMarker}主力净流入</span>
                        <span style="font-family:monospace; color:#fff">${netVal}</span>
                    </div>`;

                    // Super Net
                    const superColor = '#a855f7';
                    const superVal = ((rawItem.super_net || 0) / 10000).toFixed(1) + '万';
                    const superMarker = `<span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${superColor};"></span>`;
                    result += `<div style="display:flex; justify-content:space-between; gap:12px; font-size:11px;">
                        <span>${superMarker}超大单净流入</span>
                        <span style="font-family:monospace; color:#fff">${superVal}</span>
                    </div>`;

                    // Candle
                    const o = rawItem.open || rawItem.close || 0;
                    const c = rawItem.close || 0;
                    const l = rawItem.low || rawItem.close || 0;
                    const h = rawItem.high || rawItem.close || 0;
                    const candleColor = '#fbbf24';
                    const candleVal = `O:${o.toFixed(2)} H:${h.toFixed(2)} L:${l.toFixed(2)} C:${c.toFixed(2)}`;
                    const candleMarker = `<span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${candleColor};"></span>`;
                    result += `<div style="display:flex; justify-content:space-between; gap:12px; font-size:11px;">
                        <span>${candleMarker}股价</span>
                        <span style="font-family:monospace; color:${candleColor}">${candleVal}</span>
                    </div>`;

                    return result;
                }
            },
            color: ['#ef4444', '#a855f7', '#fbbf24'], // Default palette for Legend: Red (Main Area), Purple (Super Net), Yellow (Candle Outline)
            legend: {
                data: [
                    { name: '主力净流入', itemStyle: { color: '#ef4444' } },
                    { name: '超大单净流入', itemStyle: { color: '#a855f7' } },
                    { name: '股价', itemStyle: { color: '#fbbf24' } }
                ],
                textStyle: {
                    color: '#94a3b8' // slate-400
                },
                top: 0
            },
            grid: {
                left: '4%',
                right: '4%',
                bottom: '5%',
                top: '10%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: dates,
                axisLine: { lineStyle: { color: '#334155' } },
                axisLabel: { color: '#64748b', fontSize: 10 },
                boundaryGap: true // Candles need gap
            },
            yAxis: [
                {
                    type: 'value',
                    name: '资金 (万)',
                    position: 'left',
                    scale: true,
                    axisLine: { show: false },
                    axisLabel: {
                        color: '#60a5fa',
                        fontSize: 10,
                        formatter: (val: number) => (val / 10000).toFixed(0)
                    },
                    splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } }
                },
                {
                    type: 'value',
                    name: '价格',
                    position: 'right',
                    scale: true,
                    min: priceRange[0],
                    max: priceRange[1],
                    axisLine: { show: false },
                    axisLabel: {
                        color: '#fbbf24',
                        fontSize: 10,
                        formatter: (val: number) => val.toFixed(2)
                    },
                    splitLine: { show: false }
                }
            ],
            series: [
                {
                    name: '主力净流入', // Positive (Red)
                    type: 'line',
                    data: positiveNetInflowData,
                    smooth: false,
                    showSymbol: false,
                    lineStyle: { opacity: 0 },
                    areaStyle: { opacity: 0.15, color: '#ef4444' },
                    itemStyle: { color: '#ef4444' },
                    z: 1,
                    yAxisIndex: 0 // Left Axis
                },
                {
                    name: '_主力流入负', // Negative (Green)
                    type: 'line',
                    data: negativeNetInflowData,
                    smooth: false,
                    showSymbol: false,
                    lineStyle: { opacity: 0 },
                    areaStyle: { opacity: 0.15, color: '#22c55e' },
                    itemStyle: { color: '#22c55e' },
                    z: 1,
                    yAxisIndex: 0 // Left Axis
                },
                {
                    name: '超大单净流入',
                    type: 'line',
                    data: superNetData,
                    smooth: true,
                    showSymbol: false,
                    lineStyle: {
                        color: '#a855f7', // purple-500
                        width: 2,
                        type: 'solid'
                    },
                    z: 4,
                    yAxisIndex: 0 // Left Axis
                },
                {
                    name: '股价',
                    type: 'candlestick',
                    data: kLineData,
                    yAxisIndex: 1, // Right Axis
                    z: 3,
                    itemStyle: {
                        color: '#ef4444', // Up Color (Red)
                        color0: '#22c55e', // Down Color (Green)
                        borderColor: '#ef4444',
                        borderColor0: '#22c55e'
                    },
                    barMaxWidth: 20
                }
            ]
        };
    }, [data]);

    return (
        <ReactECharts
            option={option}
            style={{ height: height, width: '100%' }}
            theme="dark" // Optional: built-in dark theme often looks good, but we customized colors above
        />
    );
};

export default HistoryCandleChart;
