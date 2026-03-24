import React, { useMemo } from 'react';
import {
    Bar,
    CartesianGrid,
    ComposedChart,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import { SentimentHeatTrendPointV2, SentimentWindow } from '../../services/sentimentService';

interface SentimentTrendChartProps {
    data: SentimentHeatTrendPointV2[];
    window: SentimentWindow;
    selectedDayKey?: string | null;
    onSelectDayKey?: (dayKey: string) => void;
}

const formatPrice = (value?: number | null) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '--';
    return value >= 100 ? value.toFixed(1) : value.toFixed(2);
};

const formatHeatValue = (value?: number | null) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '--';
    if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(1)}万`;
    return value.toFixed(1);
};

const formatRelativeHeat = (value?: number | null) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '--';
    return `${value.toFixed(2)}x`;
};

const formatPlain = (value?: number | null) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '--';
    return `${Math.round(value)}`;
};

const PRICE_COLOR = '#facc15';
const HEAT_COLOR = '#60a5fa';
const RELATIVE_HEAT_COLOR = '#ef4444';
const AI_SENTIMENT_COLOR = '#a855f7';
const AI_CONSENSUS_COLOR = '#d946ef';
const AI_TEMPERATURE_COLOR = '#8b5cf6';

const AiScoreDot: React.FC<any> = ({ cx, cy, payload }) => {
    if (!payload?.ai_has_score || !Number.isFinite(cx) || !Number.isFinite(cy)) return null;
    return (
        <g>
            <circle cx={cx} cy={cy} r={4} fill="#6d28d9" opacity={0.35} />
            <circle cx={cx} cy={cy} r={2.8} fill="#d8b4fe" stroke="#f5d0fe" strokeWidth={1.2} />
        </g>
    );
};

const AiMetricDot: React.FC<any> = ({ cx, cy, payload, stroke }: any) => {
    if (!payload?.ai_has_score || !Number.isFinite(cx) || !Number.isFinite(cy)) return null;
    return <circle cx={cx} cy={cy} r={2.6} fill={stroke} stroke="#0f172a" strokeWidth={1} />;
};

const TooltipContent = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const raw = payload[0]?.payload as SentimentHeatTrendPointV2 | undefined;
    if (!raw) return null;
    return (
        <div
            className="min-w-[260px] rounded-xl border border-slate-700 px-3 py-2 text-[11px] text-slate-200 shadow-2xl"
            style={{ backgroundColor: 'rgba(2, 6, 23, 0.96)' }}
        >
            <div className="mb-2 text-slate-400">{label}</div>
            <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                    <span style={{ color: PRICE_COLOR }}>价格</span>
                    <span className="font-semibold" style={{ color: PRICE_COLOR }}>
                        {raw.has_price_data || raw.price_close !== null ? formatPrice(raw.price_close) : '无价格数据'}
                    </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                    <span style={{ color: AI_SENTIMENT_COLOR }}>AI情绪分</span>
                    <span className="font-semibold" style={{ color: AI_SENTIMENT_COLOR }}>{formatPlain(raw.ai_sentiment_score)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                    <span style={{ color: AI_CONSENSUS_COLOR }}>AI一致性</span>
                    <span className="font-semibold" style={{ color: AI_CONSENSUS_COLOR }}>{formatPlain(raw.ai_consensus_strength)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                    <span style={{ color: AI_TEMPERATURE_COLOR }}>AI温度</span>
                    <span className="font-semibold" style={{ color: AI_TEMPERATURE_COLOR }}>{formatPlain(raw.ai_emotion_temperature)}</span>
                </div>
                {raw.ai_risk_tag ? (
                    <div className="flex items-center justify-between gap-3">
                        <span className="text-slate-400">AI标签</span>
                        <span className="font-semibold text-violet-200">{raw.ai_risk_tag}</span>
                    </div>
                ) : null}
                <div className="flex items-center justify-between gap-3">
                    <span style={{ color: HEAT_COLOR }}>热度</span>
                    <span className="font-semibold" style={{ color: HEAT_COLOR }}>{formatHeatValue(raw.raw_heat)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                    <span style={{ color: RELATIVE_HEAT_COLOR }}>相对热度</span>
                    <span className="font-semibold" style={{ color: RELATIVE_HEAT_COLOR }}>{formatRelativeHeat(raw.relative_heat_index)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                    <span className="text-slate-400">主帖 / 评论</span>
                    <span className="font-semibold text-slate-100">
                        {raw.post_count} / {raw.reply_count_sum}
                    </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                    <span className="text-slate-400">阅读量</span>
                    <span className="font-semibold text-slate-100">{raw.read_count_sum || 0}</span>
                </div>
                {raw.is_live_bucket ? <div className="pt-1 text-[10px] text-blue-300">当前桶仍在累积中，补抓后会继续变化</div> : null}
                {raw.is_gap ? <div className="pt-1 text-[10px] text-slate-500">当前桶无新增帖子，不代表讨论归零</div> : null}
            </div>
        </div>
    );
};

const SentimentTrendChart: React.FC<SentimentTrendChartProps> = ({ data, window, selectedDayKey, onSelectDayKey }) => {
    const points = Array.isArray(data) ? data : [];

    const handleChartClick = (state: any) => {
        const nextDayKey = state?.activePayload?.[0]?.payload?.bucket_date;
        if (nextDayKey && onSelectDayKey) {
            onSelectDayKey(nextDayKey);
        }
    };
    const commonMargin = { top: 8, right: 12, left: 0, bottom: 16 };
    const hasAiSeries = points.some((item) => item.ai_has_score);
    const lowerChartData = useMemo(() => points.map((item) => ({ ...item, selected_heat: item.bucket_date === selectedDayKey ? item.raw_heat : null })), [points, selectedDayKey]);

    return (
        <div className="relative flex h-full min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-950/35 p-3">
            <div className="mb-2 flex items-center justify-between text-[11px] text-slate-400">
                <div>热度主图</div>
                <div>{window === '5d' ? '5日 · 30分钟交易桶 + 盘前/盘后' : `${window === '20d' ? '20' : '60'}日 · 日聚合`}</div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-2">
                <div className="h-[43%] min-h-[160px] overflow-visible rounded-xl bg-slate-950/35 p-2">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={points}
                            syncId="sentiment-heat-price"
                            onClick={handleChartClick}
                            margin={commonMargin}
                        >
                            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} opacity={0.45} />
                            <XAxis dataKey="bucket_label" hide />
                            <YAxis
                                yAxisId="price"
                                tick={{ fontSize: 10, fill: '#64748b' }}
                                axisLine={false}
                                tickLine={false}
                                width={46}
                                domain={['auto', 'auto']}
                                tickFormatter={(value) => formatPrice(Number(value))}
                            />
                            <YAxis yAxisId="aiScore" orientation="right" hide domain={[-100, 100]} />
                            <Tooltip
                                content={<TooltipContent />}
                                cursor={{ stroke: 'rgba(148,163,184,0.35)', strokeWidth: 1 }}
                                wrapperStyle={{ outline: 'none', zIndex: 40, pointerEvents: 'none' }}
                                allowEscapeViewBox={{ x: true, y: true }}
                            />
                            <Line
                                yAxisId="price"
                                type="monotone"
                                dataKey="price_close"
                                stroke={PRICE_COLOR}
                                strokeWidth={2}
                                dot={false}
                                connectNulls={false}
                                activeDot={{ r: 3, fill: PRICE_COLOR }}
                                name="价格"
                            />
                            {hasAiSeries ? (
                                <Line
                                    yAxisId="aiScore"
                                    type="monotone"
                                    dataKey="ai_sentiment_score"
                                    stroke={AI_SENTIMENT_COLOR}
                                    strokeWidth={2.8}
                                    dot={<AiScoreDot />}
                                    connectNulls
                                    activeDot={{ r: 4, fill: '#d8b4fe', stroke: '#f5d0fe', strokeWidth: 1.5 }}
                                    name="AI情绪分"
                                />
                            ) : null}
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                <div className="min-h-[240px] flex-1 overflow-hidden rounded-xl bg-slate-950/35 p-2">
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                            data={lowerChartData}
                            syncId="sentiment-heat-price"
                            onClick={handleChartClick}
                            margin={commonMargin}
                        >
                            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} opacity={0.45} />
                            <XAxis
                                dataKey="bucket_label"
                                tick={{ fontSize: 10, fill: '#64748b' }}
                                axisLine={{ stroke: '#334155' }}
                                tickLine={false}
                                minTickGap={window === '5d' ? 8 : 10}
                                interval="preserveStartEnd"
                            />
                            <YAxis
                                yAxisId="heat"
                                tick={{ fontSize: 10, fill: '#64748b' }}
                                axisLine={false}
                                tickLine={false}
                                width={46}
                                tickFormatter={(value) => formatHeatValue(Number(value))}
                            />
                            <YAxis yAxisId="heatRatio" orientation="right" hide domain={[0, 'auto']} />
                            <YAxis yAxisId="aiMetrics" orientation="right" hide domain={[0, 100]} />
                            <Tooltip cursor={{ fill: 'rgba(148,163,184,0.08)' }} content={() => null} />
                            <Bar
                                yAxisId="heat"
                                dataKey="raw_heat"
                                fill={HEAT_COLOR}
                                radius={[4, 4, 0, 0]}
                                maxBarSize={window === '5d' ? 18 : 26}
                                minPointSize={2}
                                name="热度"
                            />
                            <Line
                                yAxisId="heatRatio"
                                type="monotone"
                                dataKey="relative_heat_index"
                                stroke={RELATIVE_HEAT_COLOR}
                                strokeWidth={2}
                                dot={false}
                                connectNulls={false}
                                activeDot={{ r: 3, fill: RELATIVE_HEAT_COLOR }}
                                name="相对热度"
                            />
                            {hasAiSeries ? (
                                <>
                                    <Line
                                        yAxisId="aiMetrics"
                                        type="monotone"
                                        dataKey="ai_consensus_strength"
                                        stroke={AI_CONSENSUS_COLOR}
                                        strokeWidth={1.8}
                                        strokeOpacity={0.9}
                                        dot={<AiMetricDot stroke={AI_CONSENSUS_COLOR} />}
                                        connectNulls
                                        activeDot={{ r: 3, fill: AI_CONSENSUS_COLOR }}
                                        name="AI一致性"
                                    />
                                    <Line
                                        yAxisId="aiMetrics"
                                        type="monotone"
                                        dataKey="ai_emotion_temperature"
                                        stroke={AI_TEMPERATURE_COLOR}
                                        strokeWidth={1.8}
                                        strokeOpacity={0.82}
                                        dot={<AiMetricDot stroke={AI_TEMPERATURE_COLOR} />}
                                        connectNulls
                                        activeDot={{ r: 3, fill: AI_TEMPERATURE_COLOR }}
                                        name="AI温度"
                                    />
                                </>
                            ) : null}
                            {selectedDayKey ? (
                                <Line
                                    yAxisId="heat"
                                    dataKey="selected_heat"
                                    stroke="transparent"
                                    dot={{ r: 4, fill: '#f8fafc', stroke: '#38bdf8', strokeWidth: 2 }}
                                    activeDot={false}
                                    connectNulls={false}
                                    legendType="none"
                                    isAnimationActive={false}
                                />
                            ) : null}
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};

export default SentimentTrendChart;
