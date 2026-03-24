import axios from 'axios';
import { API_BASE_URL } from '../config';

export type SentimentWindow = '5d' | '20d' | '60d';
export type SentimentFeedSort = 'latest' | 'hot';

export interface SentimentDailyScore {
    symbol: string;
    trade_date: string;
    sample_count: number;
    sentiment_score: number | null;
    direction_label: '偏多' | '偏空' | '分歧' | '中性' | string | null;
    consensus_strength: number | null;
    emotion_temperature: number | null;
    risk_tag: string | null;
    summary_text: string | null;
    model_used?: string | null;
    created_at?: string | null;
    has_score?: boolean;
}

export interface SentimentOverviewV2 {
    symbol: string;
    window: SentimentWindow;
    window_label: string;
    window_start: string | null;
    window_end: string | null;
    trade_dates: string[];
    current_stock_heat: number;
    post_count: number;
    reply_count_sum: number;
    read_count_sum: number;
    relative_heat_index: number | null;
    relative_heat_label: string;
    coverage_status: 'covered' | 'no_recent_events' | 'uncovered' | string;
    metric_explanations: Record<string, string>;
    daily_score?: SentimentDailyScore | null;
}

export interface SentimentHeatTrendPointV2 {
    time_bucket: string;
    bucket_label: string;
    bucket_date: string;
    bucket_clock?: string;
    raw_heat: number;
    post_count: number;
    reply_count_sum: number;
    read_count_sum: number;
    relative_heat_index: number | null;
    relative_heat_label: string;
    is_gap: boolean;
    is_live_bucket?: boolean;
    price_close?: number | null;
    price_change_pct?: number | null;
    volume_proxy?: number | null;
    has_price_data?: boolean;
    ai_sentiment_score?: number | null;
    ai_consensus_strength?: number | null;
    ai_emotion_temperature?: number | null;
    ai_risk_tag?: string | null;
    ai_has_score?: boolean;
    ai_tag_visible?: boolean;
}

export interface SentimentFeedItemV2 {
    event_id: string;
    title?: string;
    content: string;
    day_key: string;
    author_name?: string | null;
    pub_time: string;
    crawl_time?: string | null;
    view_count: number;
    reply_count: number;
    like_count: number;
    repost_count: number;
    raw_url?: string | null;
    source_event_id?: string | null;
    hot_score?: number;
}

export interface SentimentFeedPayloadV2 {
    items: SentimentFeedItemV2[];
    coverage_status: 'covered' | 'no_recent_events' | 'uncovered' | string;
    window_start?: string | null;
    window_end?: string | null;
}

export const sentimentService = {
    crawl: async (symbol: string) => {
        const response = await axios.post(`${API_BASE_URL}/sentiment/crawl/${symbol}`);
        return response.data;
    },

    getOverviewV2: async (symbol: string, window: SentimentWindow = '5d'): Promise<SentimentOverviewV2> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/overview/${symbol}?window=${window}`);
        return response.data;
    },

    getHeatTrendV2: async (symbol: string, window: SentimentWindow = '5d'): Promise<SentimentHeatTrendPointV2[]> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/heat_trend/${symbol}?window=${window}`);
        return Array.isArray(response.data) ? response.data : [];
    },

    getDailyScoresV2: async (symbol: string, window: SentimentWindow = '20d'): Promise<SentimentDailyScore[]> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/daily_scores/${symbol}?window=${window}`);
        return Array.isArray(response.data) ? response.data : [];
    },

    getFeedV2: async (
        symbol: string,
        window: SentimentWindow = '5d',
        sort: SentimentFeedSort = 'latest',
        limit = 50
    ): Promise<SentimentFeedPayloadV2> => {
        const response = await axios.get(
            `${API_BASE_URL}/sentiment/feed/${symbol}?window=${window}&sort=${sort}&limit=${limit}`
        );
        return response.data;
    },

    generateDailyScore: async (symbol: string, tradeDate: string) => {
        const response = await axios.post(
            `${API_BASE_URL}/sentiment/internal/sentiment/score_daily/${symbol}?trade_date=${tradeDate}`
        );
        return response.data;
    },
};
