import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Info, RefreshCw, Rss, Sparkles, Wand2 } from 'lucide-react';
import {
    sentimentService,
    SentimentDailyScore,
    SentimentFeedItemV2,
    SentimentFeedPayloadV2,
    SentimentFeedSort,
    SentimentHeatTrendPointV2,
    SentimentOverviewV2,
    SentimentWindow,
} from '../../services/sentimentService';
import CommentList from './CommentList';
import SentimentTrendChart from './SentimentTrendChart';

interface SentimentDashboardProps {
    symbol: string;
}

const AUTO_RECRAWL_MS = 30 * 60 * 1000;
const autoCrawlDedup = new Map<string, number>();
const TRADING_SLOTS = ['盘前', '09:30', '10:00', '10:30', '11:00', '午间', '13:00', '13:30', '14:00', '14:30', '盘后'];
const SLOT_ORDER = new Map(TRADING_SLOTS.map((slot, index) => [slot, index]));

const formatLargeNumber = (value?: number | null) => {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return '--';
    if (Math.abs(numeric) >= 10000) return `${(numeric / 10000).toFixed(1)}万`;
    return `${Math.round(numeric)}`;
};

const formatMultiplier = (value?: number | null) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '--';
    return `${value.toFixed(2)}x`;
};

const formatScore = (value?: number | null) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '--';
    const rounded = Math.round(value);
    return `${rounded > 0 ? '+' : ''}${rounded}`;
};

const directionTextClass = (label?: string | null) => {
    if (!label) return 'text-slate-400';
    if (label.includes('偏多')) return 'text-red-300';
    if (label.includes('偏空')) return 'text-green-300';
    return 'text-violet-200';
};

const riskTagClass = (label?: string | null) => {
    if (!label) return 'text-slate-400';
    if (label.includes('FOMO') || label.includes('叙事发酵')) return 'text-red-300';
    if (label.includes('恐慌')) return 'text-green-300';
    if (label.includes('分歧')) return 'text-fuchsia-300';
    if (label.includes('观望')) return 'text-amber-300';
    return 'text-violet-300';
};

const getCoverageText = (value?: string) => {
    if (value === 'covered') return '已覆盖';
    if (value === 'no_recent_events') return '当前窗口无新增';
    if (value === 'uncovered') return '暂未覆盖';
    return value || '--';
};

const pickLatestDayKey = (trend: SentimentHeatTrendPointV2[], feedItems: SentimentFeedItemV2[]) => {
    const fromFeed = [...new Set(feedItems.map((item) => item.day_key).filter(Boolean))].sort().pop();
    if (fromFeed) return fromFeed;
    return [...trend]
        .map((item) => item.bucket_date)
        .filter(Boolean)
        .sort()
        .pop() || null;
};

const resolve5dSlot = (clock?: string, dayHasPrice = false) => {
    if (!dayHasPrice) return '休市';
    const hhmm = String(clock || '').slice(0, 5);
    if (!hhmm) return '盘后';
    if (hhmm < '09:30') return '盘前';
    if (hhmm < '10:00') return '09:30';
    if (hhmm < '10:30') return '10:00';
    if (hhmm < '11:00') return '10:30';
    if (hhmm < '11:30') return '11:00';
    if (hhmm < '13:00') return '午间';
    if (hhmm < '13:30') return '13:00';
    if (hhmm < '14:00') return '13:30';
    if (hhmm < '14:30') return '14:00';
    if (hhmm <= '15:00') return '14:30';
    return '盘后';
};

const compress5dTrend = (rows: SentimentHeatTrendPointV2[]): SentimentHeatTrendPointV2[] => {
    if (!rows.length) return rows;

    const dayHasPrice = new Map<string, boolean>();
    rows.forEach((row) => {
        if (!row.bucket_date) return;
        if ((row.has_price_data || row.price_close !== null) && row.price_close !== undefined) {
            dayHasPrice.set(row.bucket_date, true);
        } else if (!dayHasPrice.has(row.bucket_date)) {
            dayHasPrice.set(row.bucket_date, false);
        }
    });

    type TempRow = SentimentHeatTrendPointV2 & { slotLabel: string; slotIndex: number };
    const grouped = new Map<string, TempRow>();

    rows.forEach((row) => {
        const dayKey = row.bucket_date;
        const slotLabel = resolve5dSlot(row.bucket_clock, Boolean(dayHasPrice.get(dayKey)));
        const slotIndex = slotLabel === '休市' ? 99 : SLOT_ORDER.get(slotLabel) ?? 98;
        const groupKey = `${dayKey}__${slotLabel}`;
        const current = grouped.get(groupKey);
        if (!current) {
            grouped.set(groupKey, {
                ...row,
                time_bucket: `${dayKey} ${slotLabel}`,
                bucket_label: slotLabel === '休市' ? `${dayKey.slice(5)} 休市` : `${dayKey.slice(5)} ${slotLabel}`,
                bucket_clock: slotLabel,
                raw_heat: Number(row.raw_heat || 0),
                post_count: Number(row.post_count || 0),
                reply_count_sum: Number(row.reply_count_sum || 0),
                read_count_sum: Number(row.read_count_sum || 0),
                is_gap: Number(row.raw_heat || 0) <= 0,
                slotLabel,
                slotIndex,
            });
            return;
        }

        current.raw_heat += Number(row.raw_heat || 0);
        current.post_count += Number(row.post_count || 0);
        current.reply_count_sum += Number(row.reply_count_sum || 0);
        current.read_count_sum += Number(row.read_count_sum || 0);
        current.volume_proxy = Number(current.volume_proxy || 0) + Number(row.volume_proxy || 0);
        current.has_price_data = Boolean(current.has_price_data || row.has_price_data);
        current.is_live_bucket = Boolean(current.is_live_bucket || row.is_live_bucket);
        if (row.price_close !== null && row.price_close !== undefined) {
            current.price_close = row.price_close;
            current.price_change_pct = row.price_change_pct;
        }
    });

    const ordered = Array.from(grouped.values()).sort((a, b) => {
        if (a.bucket_date !== b.bucket_date) return a.bucket_date.localeCompare(b.bucket_date);
        return a.slotIndex - b.slotIndex;
    });

    const slotHistory = new Map<string, number[]>();
    return ordered.map((row) => {
        const history = slotHistory.get(row.slotLabel) || [];
        const baselineAvg = history.length ? history.reduce((sum, value) => sum + value, 0) / history.length : 0;
        const rawHeat = Number(row.raw_heat || 0);
        const relative = baselineAvg > 0 && rawHeat > 0 ? Number((rawHeat / baselineAvg).toFixed(2)) : null;
        slotHistory.set(row.slotLabel, [...history.slice(-4), rawHeat]);
        return {
            ...row,
            raw_heat: Number(rawHeat.toFixed(2)),
            relative_heat_index: relative,
            relative_heat_label:
                relative === null ? '基线不足' : relative >= 2.5 ? '显著升温' : relative >= 1.2 ? '偏热' : relative >= 0.8 ? '常态' : relative > 0 ? '偏冷' : '无讨论',
            is_gap: rawHeat <= 0,
        };
    });
};

const mergeDailyScoresIntoTrend = (rows: SentimentHeatTrendPointV2[], scores: SentimentDailyScore[]) => {
    if (!rows.length) return rows;
    const scoreMap = new Map(scores.filter((item) => item.has_score).map((item) => [item.trade_date, item]));
    const lastIndexByDate = new Map<string, number>();
    rows.forEach((row, index) => lastIndexByDate.set(row.bucket_date, index));

    return rows.map((row, index) => {
        const score = scoreMap.get(row.bucket_date);
        return {
            ...row,
            ai_sentiment_score: score?.sentiment_score ?? null,
            ai_consensus_strength: score?.consensus_strength ?? null,
            ai_emotion_temperature: score?.emotion_temperature ?? null,
            ai_risk_tag: score?.risk_tag ?? null,
            ai_has_score: Boolean(score?.has_score),
            ai_tag_visible: Boolean(score?.risk_tag && lastIndexByDate.get(row.bucket_date) === index),
        };
    });
};

const InfoBubble: React.FC<{ text: string }> = ({ text }) => (
    <div className="group relative inline-flex">
        <span className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-700 text-[10px] text-slate-300">
            <Info className="h-3 w-3" />
        </span>
        <div
            className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 w-52 -translate-x-1/2 rounded-lg border border-slate-700 px-2.5 py-2 text-[11px] leading-5 text-slate-200 opacity-0 shadow-xl transition-none group-hover:opacity-100"
            style={{ backgroundColor: 'rgba(2, 6, 23, 0.98)' }}
        >
            {text}
        </div>
    </div>
);

const SentimentDashboard: React.FC<SentimentDashboardProps> = ({ symbol }) => {
    const [loading, setLoading] = useState(false);
    const [crawling, setCrawling] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [timeWindow, setTimeWindow] = useState<SentimentWindow>('20d');
    const [sort, setSort] = useState<SentimentFeedSort>('latest');
    const [overview, setOverview] = useState<SentimentOverviewV2 | null>(null);
    const [trend, setTrend] = useState<SentimentHeatTrendPointV2[]>([]);
    const [dailyScores, setDailyScores] = useState<SentimentDailyScore[]>([]);
    const [feed, setFeed] = useState<SentimentFeedPayloadV2 | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [actionMessage, setActionMessage] = useState<string | null>(null);
    const [selectedDayKey, setSelectedDayKey] = useState<string | null>(null);
    const crawlingRef = useRef(false);

    const fetchAll = useCallback(
        async (options?: { silent?: boolean }) => {
            if (!symbol) return;
            const silent = Boolean(options?.silent);
            if (!silent) setLoading(true);
            setError(null);
            try {
                const [overviewPayload, trendPayload, feedPayload, dailyScorePayload] = await Promise.all([
                    sentimentService.getOverviewV2(symbol, timeWindow),
                    sentimentService.getHeatTrendV2(symbol, timeWindow),
                    sentimentService.getFeedV2(symbol, timeWindow, sort, 50),
                    sentimentService.getDailyScoresV2(symbol, timeWindow === '5d' ? '20d' : timeWindow),
                ]);
                setOverview(overviewPayload);
                setTrend(trendPayload);
                setFeed(feedPayload);
                setDailyScores(dailyScorePayload);
                setSelectedDayKey((current) => {
                    if (current && feedPayload.items.some((item) => item.day_key === current)) return current;
                    return pickLatestDayKey(trendPayload, feedPayload.items);
                });
            } catch (err) {
                console.error('sentiment v3 fetch failed', err);
                setError('散户一致性观察加载失败');
                setOverview(null);
                setTrend([]);
                setDailyScores([]);
                setFeed(null);
            } finally {
                if (!silent) setLoading(false);
            }
        },
        [sort, symbol, timeWindow]
    );

    const runAutoCrawl = useCallback(
        async (reason: 'open' | 'stay' | 'manual') => {
            if (!symbol || crawlingRef.current) return;
            const dedupKey = `${symbol}:${reason}`;
            const now = Date.now();
            const lastRun = autoCrawlDedup.get(dedupKey) || 0;
            if (reason !== 'stay' && now - lastRun < 8000) return;
            autoCrawlDedup.set(dedupKey, now);
            crawlingRef.current = true;
            setCrawling(true);
            try {
                await sentimentService.crawl(symbol);
                await fetchAll({ silent: true });
            } catch (err) {
                console.error(`sentiment crawl failed [${reason}]`, err);
            } finally {
                crawlingRef.current = false;
                setCrawling(false);
            }
        },
        [fetchAll, symbol]
    );

    const handleGenerateSummary = useCallback(async () => {
        const tradeDate = overview?.trade_dates?.[overview.trade_dates.length - 1];
        if (!symbol || !tradeDate) {
            setActionMessage('当前没有可总结的交易日。');
            return;
        }
        setGenerating(true);
        setActionMessage(null);
        try {
            const result = await sentimentService.generateDailyScore(symbol, tradeDate);
            if (result?.code === 200) {
                const payload = result.data || {};
                if (payload.status === 'generated') {
                    setActionMessage(`已生成 ${tradeDate} 的 AI 日评：${payload.direction_label || ''} ${payload.sentiment_score ?? ''}`.trim());
                } else {
                    setActionMessage(`已执行总结：${payload.reason || result.message || '完成'}`);
                }
                await fetchAll({ silent: true });
            } else {
                setActionMessage(result?.message || '立即总结失败');
            }
        } catch (err: any) {
            console.error('generate daily score failed', err);
            setActionMessage(err?.response?.data?.message || err?.message || '立即总结失败');
        } finally {
            setGenerating(false);
        }
    }, [fetchAll, overview?.trade_dates, symbol]);

    useEffect(() => {
        setSort('latest');
        setActionMessage(null);
    }, [symbol]);

    useEffect(() => {
        fetchAll();
    }, [fetchAll]);

    useEffect(() => {
        if (!symbol) return;
        runAutoCrawl('open');
    }, [runAutoCrawl, symbol]);

    useEffect(() => {
        if (!symbol) return;
        const timer = window.setInterval(() => {
            runAutoCrawl('stay');
        }, AUTO_RECRAWL_MS);
        return () => window.clearInterval(timer);
    }, [runAutoCrawl, symbol]);

    const feedItems: SentimentFeedItemV2[] = feed?.items || [];
    const displayTrend = useMemo(() => {
        const baseRows = timeWindow === '5d' ? compress5dTrend(trend) : trend;
        return mergeDailyScoresIntoTrend(baseRows, dailyScores);
    }, [dailyScores, timeWindow, trend]);

    useEffect(() => {
        if (!feedItems.length) return;
        if (sort === 'hot') {
            setSelectedDayKey(feedItems[0].day_key || null);
        }
    }, [feedItems, sort]);

    const observationTips = useMemo(() => {
        const validRows = displayTrend.filter((item) => item.has_price_data);
        if (validRows.length < 2) {
            return ['样本较少，先观察热度是否持续放大，再判断是否形成拥挤交易。'];
        }
        const latest = validRows[validRows.length - 1];
        const prev = validRows[validRows.length - 2];
        const priorMaxPrice = Math.max(...validRows.slice(0, -1).map((item) => Number(item.price_close || 0)), 0);
        const priorMaxHeat = Math.max(...validRows.slice(0, -1).map((item) => Number(item.relative_heat_index || 0)), 0);
        const result: string[] = [];

        if ((latest.relative_heat_index || 0) >= 2 && (latest.price_change_pct || 0) < 0) {
            result.push('讨论升温但价格走弱，留意情绪先行与资金承接是否错位。');
        }
        if ((latest.price_close || 0) >= priorMaxPrice && priorMaxPrice > 0 && (latest.relative_heat_index || 0) < Math.max(1.0, priorMaxHeat * 0.75)) {
            result.push('价格创新高但讨论未同步放大，说明跟风热度暂未全面扩散。');
        }
        if ((latest.price_change_pct || 0) < 0 && (latest.relative_heat_index || 0) <= (prev.relative_heat_index || 0)) {
            result.push('价格继续走弱，但讨论未继续放大，抛压情绪可能边际钝化。');
        }
        if ((latest.raw_heat || 0) >= Math.max(40, (prev.raw_heat || 0) * 1.8)) {
            result.push('热度突然放大，关注是否进入散户拥挤阶段。');
        }
        return result.length ? result.slice(0, 3) : ['热度与价格暂未出现明显背离，优先观察是否持续放量讨论。'];
    }, [displayTrend]);

    const metricMeta = useMemo(() => {
        const explanations = overview?.metric_explanations || {};
        return [
            {
                key: 'current_stock_heat',
                label: '当前股票热度',
                value: formatLargeNumber(overview?.current_stock_heat),
                subtext: overview ? `主帖 ${overview.post_count} · 评论 ${overview.reply_count_sum}` : '--',
                accent: 'text-blue-300',
                explain: explanations.current_stock_heat || '当前窗口内累计热度。',
            },
            {
                key: 'relative_heat_index',
                label: '相对热度',
                value: formatMultiplier(overview?.relative_heat_index),
                subtext: overview?.relative_heat_label || '--',
                accent: 'text-amber-300',
                explain: explanations.relative_heat_index || '相对过去 5 个交易日自身基线的放大量。',
            },
            {
                key: 'sentiment_score',
                label: '情绪得分',
                value: formatScore(overview?.daily_score?.sentiment_score),
                subtext: overview?.daily_score?.direction_label || '仅星标股夜间生成',
                accent:
                    (overview?.daily_score?.sentiment_score || 0) > 0
                        ? 'text-red-300'
                        : (overview?.daily_score?.sentiment_score || 0) < 0
                        ? 'text-green-300'
                        : 'text-violet-200',
                explain: explanations.sentiment_score || 'LLM 对当日高价值样本给出的 -100 到 100 综合分。',
            },
            {
                key: 'consensus_strength',
                label: '一致性',
                value: overview?.daily_score?.consensus_strength !== undefined && overview?.daily_score?.consensus_strength !== null ? `${overview.daily_score.consensus_strength}` : '--',
                subtext: '越高越一边倒',
                accent: 'text-fuchsia-300',
                explain: explanations.consensus_strength || '散户观点是否集中。',
            },
            {
                key: 'emotion_temperature',
                label: '情绪温度',
                value: overview?.daily_score?.emotion_temperature !== undefined && overview?.daily_score?.emotion_temperature !== null ? `${overview.daily_score.emotion_temperature}` : '--',
                subtext: '越高越亢奋/恐慌',
                accent: 'text-purple-300',
                explain: explanations.emotion_temperature || '情绪强度。',
            },
            {
                key: 'risk_tag',
                label: '风险标签',
                value: overview?.daily_score?.risk_tag || getCoverageText(overview?.coverage_status),
                subtext: overview?.daily_score?.sample_count ? `样本 ${overview.daily_score.sample_count} 条` : getCoverageText(overview?.coverage_status),
                accent: 'text-violet-300',
                explain: explanations.risk_tag || '对当前散户状态的交易化解释。',
            },
        ];
    }, [overview]);

    const aiLogs = useMemo(
        () => dailyScores.filter((item) => item.has_score).slice().reverse(),
        [dailyScores]
    );

    return (
        <section className="mt-6 h-[72vh] min-h-[620px] rounded-2xl border border-slate-800 bg-slate-900/45 p-4 shadow-[0_18px_60px_rgba(2,6,23,0.32)]">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                    <div className="flex items-center gap-2">
                        <Rss className="h-4 w-4 text-amber-300" />
                        <h2 className="text-base font-semibold text-slate-100">散户一致性观察</h2>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">先看讨论热度，再看相对热度，最后叠加 AI 日评因子与风险标签。</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-1 rounded-xl border border-slate-700 bg-slate-950/60 p-1">
                        {[
                            ['5d', '5D'],
                            ['20d', '20D'],
                            ['60d', '60D'],
                        ].map(([key, label]) => (
                            <button
                                key={key}
                                type="button"
                                onClick={() => setTimeWindow(key as SentimentWindow)}
                                className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
                                    timeWindow === key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                                }`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <button
                        type="button"
                        onClick={() => fetchAll()}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                        刷新
                    </button>
                    <button
                        type="button"
                        onClick={() => runAutoCrawl('manual')}
                        disabled={crawling}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-xs text-blue-200 transition hover:border-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 ${crawling ? 'animate-spin' : ''}`} />
                        立即补抓
                    </button>
                </div>
            </div>

            {error ? (
                <div className="flex h-[calc(100%-52px)] items-center justify-center rounded-xl border border-red-500/20 bg-red-500/5 text-sm text-red-200">
                    {error}
                </div>
            ) : (
                <div className="grid h-[calc(100%-52px)] min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2.2fr)_280px_minmax(360px,1.08fr)]">
                    <div className="flex min-h-0 flex-col gap-3">
                        <div className="grid grid-cols-2 gap-2 rounded-2xl border border-slate-800 bg-slate-950/35 p-3 md:grid-cols-3 xl:grid-cols-6">
                            {metricMeta.map((item) => (
                                <div key={item.key} className="rounded-xl border border-slate-800/80 bg-slate-900/35 px-3 py-2.5">
                                    <div className="flex items-center gap-1 text-[11px] text-slate-500">
                                        <span>{item.label}</span>
                                        <InfoBubble text={item.explain} />
                                    </div>
                                    <div className={`mt-1.5 text-lg font-semibold ${item.accent}`}>{item.value}</div>
                                    <div className="mt-1 text-[10px] leading-4 text-slate-500">{item.subtext}</div>
                                </div>
                            ))}
                        </div>

                        <div className="min-h-0 flex-1">
                            <SentimentTrendChart
                                data={displayTrend}
                                window={timeWindow}
                                selectedDayKey={selectedDayKey}
                                onSelectDayKey={setSelectedDayKey}
                            />
                        </div>
                    </div>

                    <div className="flex min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-950/35 p-3">
                        <div className="mb-2 flex items-center justify-between gap-2 text-sm font-semibold text-slate-200">
                            <div className="flex items-center gap-2">
                                <Sparkles className="h-4 w-4 text-violet-300" />
                                AI 日评日志
                            </div>
                            <button
                                type="button"
                                onClick={handleGenerateSummary}
                                disabled={generating || !overview?.trade_dates?.length}
                                className="inline-flex items-center gap-1 rounded-lg border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-[11px] text-violet-200 transition hover:border-violet-400 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                <Wand2 className={`h-3 w-3 ${generating ? 'animate-pulse' : ''}`} />
                                立即总结当前情况
                            </button>
                        </div>
                        <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-2.5 text-[12px] leading-5 text-slate-300">
                            {overview?.daily_score?.summary_text || '当前暂无日级 LLM 解读。系统仅对星标股在盘后与夜间生成缓存结果。'}
                        </div>
                        {actionMessage ? (
                            <div className="mt-2 rounded-lg border border-violet-500/20 bg-violet-500/5 px-3 py-2 text-[11px] text-violet-200">
                                {actionMessage}
                            </div>
                        ) : null}
                        <div className="mt-3 space-y-2 text-[12px] leading-5 text-slate-300">
                            {observationTips.map((tip, index) => (
                                <div key={`${tip}-${index}`} className="rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-2">
                                    {tip}
                                </div>
                            ))}
                        </div>
                        <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/30 p-2">
                            {aiLogs.length ? (
                                <div className="space-y-2">
                                    {aiLogs.map((item) => (
                                        <div key={item.trade_date} className="rounded-lg border border-slate-800 bg-slate-950/55 px-2.5 py-2 text-[11px] text-slate-200">
                                            <div className="flex items-center justify-between gap-2 text-slate-400">
                                                <span>{item.trade_date}</span>
                                                <span className="text-violet-300">{formatScore(item.sentiment_score)}</span>
                                            </div>
                                            <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-slate-400">
                                                <span className={directionTextClass(item.direction_label)}>方向 {item.direction_label || '--'}</span>
                                                <span className="text-fuchsia-300">一致性 {item.consensus_strength ?? '--'}</span>
                                                <span className="text-purple-300">温度 {item.emotion_temperature ?? '--'}</span>
                                                <span className={riskTagClass(item.risk_tag)}>{item.risk_tag || '--'}</span>
                                            </div>
                                            <div className="mt-1.5 leading-5 text-slate-300">{item.summary_text || '暂无摘要'}</div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="flex h-full items-center justify-center text-[11px] text-slate-500">当前窗口暂无 AI 日评日志</div>
                            )}
                        </div>
                    </div>

                    <div className="min-h-0">
                        <CommentList
                            items={feedItems}
                            loading={loading}
                            sort={sort}
                            onSortChange={setSort}
                            focusDayKey={selectedDayKey}
                            emptyMessage={overview?.coverage_status === 'uncovered' ? '该股票暂未进入股吧抓取覆盖' : '当前窗口暂无可展示原文'}
                        />
                    </div>
                </div>
            )}

            {!error && overview?.coverage_status !== 'covered' ? (
                <div className="mt-3 flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
                    <AlertCircle className="h-4 w-4" />
                    <span>{getCoverageText(overview?.coverage_status)}，如刚加入星标或首次查看，等自动补抓完成后会逐步补齐。</span>
                </div>
            ) : null}
        </section>
    );
};

export default SentimentDashboard;
