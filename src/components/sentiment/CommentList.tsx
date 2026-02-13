import React from 'react';
import { User, MessageSquare, Eye, ThumbsUp, ThumbsDown, Clock } from 'lucide-react';
import { SentimentComment } from '../../services/sentimentService';

interface CommentListProps {
    comments: SentimentComment[];
    loading: boolean;
}

const CommentList: React.FC<CommentListProps> = ({ comments, loading }) => {
    if (loading) {
        return <div className="p-4 text-center text-xs text-slate-500">加载中...</div>;
    }

    if (comments.length === 0) {
        return (
            <div className="h-full flex flex-col items-center justify-center text-slate-500 p-4">
                <MessageSquare className="w-6 h-6 mb-2 opacity-50" />
                <p className="text-xs">暂无评论数据</p>
            </div>
        );
    }

    // 格式化日期：02-12 14:00
    const formatDate = (dateStr: string) => {
        try {
            // dateStr format: YYYY-MM-DD HH:MM
            const parts = dateStr.split(' ');
            if (parts.length < 2) return dateStr;
            const dateParts = parts[0].split('-'); // [YYYY, MM, DD]
            return `${dateParts[1]}-${dateParts[2]} ${parts[1]}`;
        } catch {
            return dateStr;
        }
    };

    return (
        <div className="h-full flex flex-col bg-slate-900/50">
            <div className="p-2 border-b border-slate-800 bg-slate-900/80 flex justify-between items-center sticky top-0 z-10 backdrop-blur-sm">
                <h3 className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                    <MessageSquare className="w-3 h-3 text-blue-400" />
                    实时股吧热评
                </h3>
                <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">Latest 50</span>
            </div>
            
            <div className="flex-1 overflow-y-auto custom-scrollbar p-1 space-y-1">
                {comments.map((comment, index) => {
                    // 根据情绪分设置边框颜色
                    let borderColor = 'border-slate-800';
                    let sentimentIcon = null;
                    
                    if (comment.sentiment_score > 0) {
                        borderColor = 'border-l-2 border-l-red-500/50 border-slate-800/50';
                        sentimentIcon = <ThumbsUp className="w-2.5 h-2.5 text-red-500" />;
                    } else if (comment.sentiment_score < 0) {
                        borderColor = 'border-l-2 border-l-green-500/50 border-slate-800/50';
                        sentimentIcon = <ThumbsDown className="w-2.5 h-2.5 text-green-500" />;
                    }

                    return (
                        <div 
                            key={comment.id} 
                            className={`bg-slate-800/20 p-2 rounded hover:bg-slate-800/40 transition-colors ${borderColor}`}
                        >
                            <div className="flex justify-between items-start mb-1">
                                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                                    <span className="flex items-center gap-1 text-slate-400">
                                        <User className="w-2.5 h-2.5" />
                                        <span className="font-medium truncate max-w-[60px]">股友_{comment.id.slice(-4)}</span>
                                    </span>
                                    <span className="text-slate-600">|</span>
                                    <span className="flex items-center gap-0.5">
                                        {formatDate(comment.pub_time)}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2 text-[10px] text-slate-600">
                                    <span className="flex items-center gap-0.5" title="阅读">
                                        <Eye className="w-2.5 h-2.5" /> {comment.read_count}
                                    </span>
                                    <span className="flex items-center gap-0.5" title="回复">
                                        <MessageSquare className="w-2.5 h-2.5" /> {comment.reply_count}
                                    </span>
                                </div>
                            </div>
                            
                            <div className="text-xs text-slate-300 leading-snug break-words line-clamp-2 hover:line-clamp-none transition-all">
                                {comment.content}
                            </div>
                            
                            {sentimentIcon && (
                                <div className="mt-1 flex justify-end">
                                    <span className={`text-[10px] px-1 py-0 rounded flex items-center gap-1 bg-slate-900/50 ${
                                        comment.sentiment_score > 0 ? 'text-red-400' : 'text-green-400'
                                    }`}>
                                        {sentimentIcon}
                                        {comment.sentiment_score > 0 ? '看多' : '看空'}
                                    </span>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default CommentList;
