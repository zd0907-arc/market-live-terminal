import React, { useEffect, useMemo, useRef } from 'react';
import { ExternalLink, Eye, Heart, MessageSquare, Repeat2 } from 'lucide-react';
import { SentimentFeedItemV2, SentimentFeedSort } from '../../services/sentimentService';

interface CommentListProps {
    items: SentimentFeedItemV2[];
    loading: boolean;
    sort: SentimentFeedSort;
    onSortChange: (next: SentimentFeedSort) => void;
    emptyMessage?: string;
    focusDayKey?: string | null;
}

const formatDateTime = (value?: string | null) => {
    if (!value) return '--';
    return String(value).slice(5, 16);
};

const formatDayHeader = (dayKey: string) => {
    if (!dayKey) return '--';
    return dayKey.replace(/^(\d{4})-/, '');
};

const metricText = (value?: number | null) => {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return null;
    if (numeric >= 10000) return `${(numeric / 10000).toFixed(1)}万`;
    return `${Math.round(numeric)}`;
};

const CommentList: React.FC<CommentListProps> = ({
    items,
    loading,
    sort,
    onSortChange,
    emptyMessage = '当前窗口暂无原文帖子',
    focusDayKey,
}) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const groupRefs = useRef<Record<string, HTMLDivElement | null>>({});

    const groups = useMemo(() => {
        const bucket = new Map<string, SentimentFeedItemV2[]>();
        items.forEach((item) => {
            const key = item.day_key || String(item.pub_time || '').slice(0, 10) || '未分组';
            const current = bucket.get(key) || [];
            current.push(item);
            bucket.set(key, current);
        });
        return Array.from(bucket.entries()).map(([dayKey, dayItems]) => ({ dayKey, items: dayItems }));
    }, [items]);

    useEffect(() => {
        if (sort === 'hot' && containerRef.current) {
            containerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
            return;
        }
        if (!focusDayKey) return;
        const target = groupRefs.current[focusDayKey];
        const container = containerRef.current;
        if (target && container) {
            const containerRect = container.getBoundingClientRect();
            const targetRect = target.getBoundingClientRect();
            const nextTop = container.scrollTop + (targetRect.top - containerRect.top) - 8;
            container.scrollTo({ top: Math.max(0, nextTop), behavior: 'smooth' });
        }
    }, [focusDayKey, groups, sort]);

    return (
        <div className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-950/45">
            <div className="border-b border-slate-800 px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                    <div>
                        <div className="text-sm font-semibold text-slate-200">最近 50 条原文</div>
                        <div className="text-[11px] text-slate-500">股吧主帖正文优先展示，按图表窗口同步过滤</div>
                    </div>
                    <div className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900/80 p-0.5 text-[11px]">
                        {[
                            ['latest', '最新'],
                            ['hot', '最热'],
                        ].map(([key, label]) => (
                            <button
                                key={key}
                                type="button"
                                onClick={() => onSortChange(key as SentimentFeedSort)}
                                className={`rounded px-2 py-1 transition-colors ${
                                    sort === key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                                }`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div ref={containerRef} className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
                {loading ? (
                    <div className="flex h-full items-center justify-center text-xs text-slate-500">加载中...</div>
                ) : items.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-slate-500">
                        <MessageSquare className="h-6 w-6 opacity-50" />
                        <div className="text-xs leading-5">{emptyMessage}</div>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {groups.map((group, groupIndex) => (
                            <div
                                key={group.dayKey}
                                ref={(node) => {
                                    groupRefs.current[group.dayKey] = node;
                                }}
                                className="space-y-2"
                            >
                                <div
                                    className={`sticky top-0 z-10 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium backdrop-blur ${
                                        (sort === 'hot' && groupIndex === 0) || focusDayKey === group.dayKey
                                            ? 'border-blue-500/40 bg-blue-500/12 text-blue-200'
                                            : 'border-slate-800 bg-slate-950/92 text-slate-400'
                                    }`}
                                >
                                    {formatDayHeader(group.dayKey)}
                                </div>
                                {group.items.map((item, itemIndex) => (
                                    <div
                                        key={item.event_id}
                                        className={`rounded-xl border px-3 py-2.5 text-sm text-slate-200 ${
                                            sort === 'hot' && groupIndex === 0 && itemIndex === 0
                                                ? 'border-amber-500/30 bg-amber-500/5'
                                                : 'border-slate-800 bg-slate-900/40'
                                        }`}
                                    >
                                        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">股吧</span>
                                            {item.author_name ? <span className="text-slate-500">{item.author_name}</span> : null}
                                            <span className="text-slate-500">{formatDateTime(item.pub_time)}</span>
                                            {item.raw_url ? (
                                                <a
                                                    href={item.raw_url}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="inline-flex items-center gap-1 text-blue-300 hover:text-blue-200"
                                                >
                                                    原文 <ExternalLink className="h-3 w-3" />
                                                </a>
                                            ) : null}
                                            {sort === 'hot' && groupIndex === 0 && itemIndex === 0 ? (
                                                <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-300">当前最热</span>
                                            ) : null}
                                        </div>

                                        <div className="whitespace-pre-wrap break-words text-[13px] leading-6 text-slate-100">
                                            {item.content || item.title || '--'}
                                        </div>

                                        <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                                            {metricText(item.view_count) ? (
                                                <span className="inline-flex items-center gap-1">
                                                    <Eye className="h-3 w-3" /> {metricText(item.view_count)}
                                                </span>
                                            ) : null}
                                            {metricText(item.reply_count) ? (
                                                <span className="inline-flex items-center gap-1">
                                                    <MessageSquare className="h-3 w-3" /> {metricText(item.reply_count)}
                                                </span>
                                            ) : null}
                                            {metricText(item.like_count) ? (
                                                <span className="inline-flex items-center gap-1">
                                                    <Heart className="h-3 w-3" /> {metricText(item.like_count)}
                                                </span>
                                            ) : null}
                                            {metricText(item.repost_count) ? (
                                                <span className="inline-flex items-center gap-1">
                                                    <Repeat2 className="h-3 w-3" /> {metricText(item.repost_count)}
                                                </span>
                                            ) : null}
                                            {sort === 'hot' && item.hot_score ? (
                                                <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-300">
                                                    热度 {item.hot_score.toFixed(1)}
                                                </span>
                                            ) : null}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default CommentList;
