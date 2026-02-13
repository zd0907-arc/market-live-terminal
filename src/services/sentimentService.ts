import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000/api';

export interface SentimentDashboardData {
    score: number;
    status: string;
    bull_bear_ratio: number;
    summary: string;
    risk_warning: string;
    details: {
        bull_count: number;
        bear_count: number;
        total_count: number;
    };
}

export interface SentimentTrendPoint {
    time_bucket: string;
    total_heat: number;
    post_count: number;
    bull_vol: number;
    bear_vol: number;
    bull_bear_ratio: number;
}

export interface SentimentComment {
    id: string;
    content: string;
    pub_time: string;
    read_count: number;
    reply_count: number;
    sentiment_score: number;
    heat_score: number;
}

export interface SentimentSummary {
    id: number;
    content: string;
    created_at: string;
    model: string;
}

export const sentimentService = {
    // 触发抓取
    crawl: async (symbol: string) => {
        const response = await axios.post(`${API_BASE_URL}/sentiment/crawl/${symbol}`);
        return response.data;
    },

    // 获取仪表盘数据
    getDashboard: async (symbol: string): Promise<SentimentDashboardData> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/dashboard/${symbol}`);
        return response.data;
    },

    // 获取趋势数据 (支持 interval 参数)
    getTrend: async (symbol: string, interval: '72h' | '14d' = '72h'): Promise<SentimentTrendPoint[]> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/trend/${symbol}?interval=${interval}`);
        return response.data;
    },

    // 获取真实评论列表
    getComments: async (symbol: string): Promise<SentimentComment[]> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/comments/${symbol}`);
        return response.data;
    },

    // 生成 AI 摘要
    generateSummary: async (symbol: string) => {
        const response = await axios.post(`${API_BASE_URL}/sentiment/summary/${symbol}`, {}, { timeout: 120000 });
        return response.data;
    },

    // 获取 AI 摘要历史
    getSummaryHistory: async (symbol: string): Promise<SentimentSummary[]> => {
        const response = await axios.get(`${API_BASE_URL}/sentiment/summary/history/${symbol}`);
        return response.data;
    }
};
