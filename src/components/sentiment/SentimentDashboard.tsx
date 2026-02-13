import React, { useState, useEffect } from 'react';
import { RefreshCw, MessageCircle, AlertTriangle, TrendingUp, TrendingDown, HelpCircle, Sparkles, History, Clock } from 'lucide-react';
import { sentimentService, SentimentDashboardData, SentimentTrendPoint, SentimentComment, SentimentSummary } from '../../services/sentimentService';
import SentimentTrendChart from './SentimentTrendChart';
import CommentList from './CommentList';

interface SentimentDashboardProps {
    symbol: string;
}

const SentimentDashboard: React.FC<SentimentDashboardProps> = ({ symbol }) => {
    const [loading, setLoading] = useState(false);
    const [crawling, setCrawling] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [data, setData] = useState<SentimentDashboardData | null>(null);
    const [trendData, setTrendData] = useState<SentimentTrendPoint[]>([]);
    const [comments, setComments] = useState<SentimentComment[]>([]);
    const [summaries, setSummaries] = useState<SentimentSummary[]>([]);
    const [trendInterval, setTrendInterval] = useState<'72h' | '14d'>('72h');
    const [showHistory, setShowHistory] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<string | null>(null);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        
        try {
            // 使用 Promise.allSettled 或分步处理以增强容错性
            const dashboardPromise = sentimentService.getDashboard(symbol).catch(e => {
                console.error("Dashboard fetch failed:", e);
                return null;
            });
            const trendPromise = sentimentService.getTrend(symbol, trendInterval).catch(e => {
                console.error("Trend fetch failed:", e);
                return [];
            });
            const commentsPromise = sentimentService.getComments(symbol).catch(e => {
                console.error("Comments fetch failed:", e);
                return [];
            });
            const summaryPromise = sentimentService.getSummaryHistory(symbol).catch(e => {
                console.error("Summary fetch failed:", e);
                return [];
            });

            const [dashboardData, trend, commentList, summaryList] = await Promise.all([
                dashboardPromise,
                trendPromise,
                commentsPromise,
                summaryPromise
            ]);

            if (dashboardData) {
                setData(dashboardData);
            } else {
                // 如果核心 dashboard 数据失败，才设置全局错误
                // 但如果只是因为没数据（返回的是默认空结构），那是正常的
                // 这里 dashboardData 是 null 说明网络请求挂了
                setError("Failed to load core metrics. Backend may be busy.");
            }
            
            setTrendData(trend);
            setComments(commentList);
            setSummaries(summaryList);
            setLastUpdated(new Date().toLocaleTimeString());
            
        } catch (err) {
            console.error("Critical error in fetchData:", err);
            setError("Failed to load sentiment data");
        } finally {
            setLoading(false);
        }
    };

    // Separate effect for trend switch to avoid reloading everything
    useEffect(() => {
        if (symbol) {
            sentimentService.getTrend(symbol, trendInterval).then(setTrendData);
        }
    }, [trendInterval]);

    useEffect(() => {
        if (symbol) {
            fetchData();
        }
    }, [symbol]);

    const handleCrawl = async () => {
        setCrawling(true);
        try {
            // 同步等待后端完成抓取 (可能是深度抓取或增量抓取)
            await sentimentService.crawl(symbol);
            // 抓取完成后立即刷新数据
            await fetchData();
        } catch (err) {
            console.error(err);
            alert("抓取请求超时或失败，后台可能仍在运行深度抓取，请稍后手动刷新。");
        } finally {
            setCrawling(false);
        }
    };

    const handleGenerateSummary = async () => {
        setGenerating(true);
        try {
            const res = await sentimentService.generateSummary(symbol);
            if (res.code !== 200) {
                throw new Error(res.message || "生成失败");
            }
            const history = await sentimentService.getSummaryHistory(symbol);
            setSummaries(history);
        } catch (err: any) {
            console.error(err);
            // 尝试提取后端返回的具体错误信息
            let msg = err.response?.data?.message || err.message || "未知错误";
            // 针对 Network Error 给出更友好的提示
            if (msg === "Network Error") {
                msg = "后端服务未响应或请求超时 (可能是模型生成时间过长)，请检查后台服务是否运行或稍后重试。";
            }
            alert(`生成摘要失败: ${msg}`);
        } finally {
            setGenerating(false);
        }
    };

    if (!data && loading) return (
        <div className="bg-slate-900 rounded-lg shadow-sm border border-slate-800 p-4 mt-4 mb-4 flex justify-center items-center min-h-[200px]">
            <div className="flex flex-col items-center gap-2 text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin" />
                <span className="text-sm">正在加载情绪数据...</span>
            </div>
        </div>
    );
    
    if (!data) return (
        <div className="bg-slate-900 rounded-lg shadow-sm border border-slate-800 p-4 mt-4 mb-4 flex flex-col justify-center items-center min-h-[200px] text-slate-500">
             <MessageCircle className="w-8 h-8 mb-2 opacity-50" />
             <p className="text-sm">暂无该股票的情绪数据</p>
             <button 
                onClick={handleCrawl}
                disabled={crawling}
                className="mt-3 px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm transition-colors flex items-center gap-2"
             >
                 <RefreshCw className={`w-4 h-4 ${crawling ? 'animate-spin' : ''}`} />
                 {crawling ? '正在抓取...' : '立即抓取'}
             </button>
        </div>
    );

    // 颜色逻辑
    const scoreColor = data.score > 0 ? 'text-red-500' : (data.score < 0 ? 'text-green-500' : 'text-slate-500');
    const ratioColor = data.bull_bear_ratio > 1 ? 'text-red-500' : (data.bull_bear_ratio < 1 ? 'text-green-500' : 'text-slate-500');
    
    // 最新摘要
    const latestSummary = summaries.length > 0 ? summaries[0] : null;

    return (
        <div className="bg-slate-900 rounded-lg shadow-sm border border-slate-800 p-3 mt-4 mb-4">
            {/* Header */}
            <div className="flex justify-between items-center mb-3">
                <div className="flex items-center gap-2">
                    <MessageCircle className="w-4 h-4 text-purple-400" />
                    <h2 className="text-base font-bold text-slate-100">散户情绪监测</h2>
                    <span className="text-[10px] text-slate-500 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">Source: Eastmoney Guba</span>
                    {lastUpdated && <span className="text-[10px] text-slate-500">Updated: {lastUpdated}</span>}
                </div>
                <button 
                    onClick={handleCrawl} 
                    disabled={crawling}
                    className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
                        crawling 
                        ? 'bg-slate-800 text-slate-500 cursor-not-allowed' 
                        : 'bg-purple-900/30 text-purple-300 hover:bg-purple-900/50 border border-purple-800/50'
                    }`}
                >
                    <RefreshCw className={`w-3 h-3 ${crawling ? 'animate-spin' : ''}`} />
                    {crawling ? '抓取中...' : '立即抓取'}
                </button>
            </div>

            {/* Main Layout: Left (Metrics + Chart) | Right (Comments) */}
            <div className="flex flex-col lg:flex-row gap-3 h-[450px]">
                
                {/* Left Column: 2/3 Width */}
                <div className="lg:w-2/3 flex flex-col gap-3 min-h-0">
                    {/* Top Metrics Row */}
                    <div className="flex gap-3 h-32 shrink-0">
                        {/* Metrics Group (Left) */}
                        <div className="w-[120px] flex flex-col gap-2 shrink-0">
                            {/* Score Card */}
                            <div className="flex-1 bg-slate-800/50 px-2 rounded-lg border border-slate-700/50 flex flex-col justify-center items-center relative overflow-hidden group">
                                <div className="absolute top-0 right-0 p-1 opacity-10">
                                    {data.score > 0 ? <TrendingUp className="w-8 h-8 text-red-500" /> : <TrendingDown className="w-8 h-8 text-green-500" />}
                                </div>
                                <div className="flex items-center gap-1 z-10">
                                    <span className="text-[10px] text-slate-400">情绪得分</span>
                                    <div className="relative group/tooltip">
                                        <HelpCircle className="w-2.5 h-2.5 text-slate-600 cursor-help" />
                                        {/* Fixed Tooltip using z-index and fixed positioning context via portal-like behavior or just high z-index */}
                                        <div className="fixed ml-4 -mt-8 w-48 bg-slate-900 border border-slate-700 p-2 rounded shadow-xl text-[10px] text-slate-300 hidden group-hover/tooltip:block z-[9999]">
                                            基于关键词匹配算法：(多头词数 - 空头词数 * 1.2)，归一化到 -10~10 区间。
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-baseline gap-1 mt-0.5">
                                    <span className={`text-2xl font-bold z-10 ${scoreColor} leading-none`}>{data.score}</span>
                                </div>
                            </div>

                            {/* Ratio Card */}
                            <div className="flex-1 bg-slate-800/50 px-2 rounded-lg border border-slate-700/50 flex flex-col justify-center items-center group">
                                <div className="flex items-center gap-1">
                                    <span className="text-[10px] text-slate-400">多空词频比</span>
                                    <div className="relative group/tooltip">
                                        <HelpCircle className="w-2.5 h-2.5 text-slate-600 cursor-help" />
                                        <div className="fixed ml-4 -mt-8 w-48 bg-slate-900 border border-slate-700 p-2 rounded shadow-xl text-[10px] text-slate-300 hidden group-hover/tooltip:block z-[9999]">
                                            多头关键词总数 / (空头关键词总数 + 1)。{'>'}2.0 为显著看多，{'<'}0.5 为显著看空。
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-baseline gap-1 mt-0.5">
                                    <span className={`text-2xl font-bold ${ratioColor} leading-none`}>{data.bull_bear_ratio}</span>
                                </div>
                            </div>
                        </div>

                        {/* AI Summary (Right) */}
                        <div className="flex-1 bg-slate-800/50 p-3 rounded-lg border border-slate-700/50 flex flex-col relative overflow-hidden">
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-slate-200 flex items-center gap-1">
                                        <Sparkles className="w-3 h-3 text-yellow-400" />
                                        AI 舆情摘要
                                    </span>
                                    {data.risk_warning && (
                                        <span className="text-[10px] text-orange-400 bg-orange-900/20 px-1.5 py-0.5 rounded border border-orange-900/30 flex items-center gap-1">
                                            <AlertTriangle className="w-3 h-3" />
                                            {data.risk_warning}
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-2">
                                    <button 
                                        onClick={() => setShowHistory(!showHistory)}
                                        className="text-slate-500 hover:text-slate-300 transition-colors"
                                        title="历史摘要"
                                    >
                                        <History className="w-3.5 h-3.5" />
                                    </button>
                                    <button 
                                        onClick={handleGenerateSummary}
                                        disabled={generating}
                                        className="flex items-center gap-1 bg-blue-600 hover:bg-blue-500 text-white px-2 py-0.5 rounded text-[10px] transition-colors disabled:opacity-50"
                                    >
                                        {generating ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                                        {generating ? 'AI 思考中...' : (latestSummary ? '重新生成' : 'AI 总结')}
                                    </button>
                                </div>
                            </div>
                            
                            {/* Content Area */}
                            <div className="flex-1 overflow-y-auto custom-scrollbar relative">
                                {showHistory ? (
                                    <div className="space-y-3 p-1">
                                        {summaries.map(s => (
                                            <div key={s.id} className="border-b border-slate-700/50 pb-2 last:border-0">
                                                <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-1">
                                                    <Clock className="w-3 h-3" />
                                                    {s.created_at}
                                                    <span className="bg-slate-800 px-1 rounded text-slate-600">{s.model}</span>
                                                </div>
                                                <p className="text-xs text-slate-400 leading-relaxed">{s.content}</p>
                                            </div>
                                        ))}
                                        {summaries.length === 0 && <p className="text-xs text-slate-500 text-center mt-4">暂无历史记录</p>}
                                    </div>
                                ) : (
                                    <div className="h-full">
                                        {latestSummary ? (
                                            <div className="animate-in fade-in duration-300">
                                                <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                                                    {latestSummary.content}
                                                </p>
                                                <div className="mt-2 text-[10px] text-slate-600 flex items-center gap-1">
                                                    <span>Generated by {latestSummary.model} at {latestSummary.created_at}</span>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-2">
                                                <Sparkles className="w-6 h-6 opacity-20" />
                                                <p className="text-xs">暂无 AI 摘要，点击右上角按钮生成</p>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Trend Chart (Smaller) */}
                    <div className="flex-1 bg-slate-800/50 rounded-lg p-1 min-h-0 border border-slate-700/50 overflow-hidden relative flex flex-col">
                        <div className="absolute top-2 right-2 z-10 flex bg-slate-900 rounded border border-slate-700 p-0.5">
                            <button 
                                onClick={() => setTrendInterval('72h')}
                                className={`px-2 py-0.5 text-[10px] rounded transition-colors ${trendInterval === '72h' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                            >
                                72H
                            </button>
                            <button 
                                onClick={() => setTrendInterval('14d')}
                                className={`px-2 py-0.5 text-[10px] rounded transition-colors ${trendInterval === '14d' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                            >
                                14天
                            </button>
                        </div>
                        <SentimentTrendChart data={trendData} />
                    </div>
                </div>

                {/* Right Column: 1/3 Width (Scrollable Comments) */}
                <div className="lg:w-1/3 h-full min-h-0 bg-slate-800/30 rounded-lg border border-slate-800/50 overflow-hidden">
                    <CommentList comments={comments} loading={loading && comments.length === 0} />
                </div>
            </div>
        </div>
    );
};

export default SentimentDashboard;
