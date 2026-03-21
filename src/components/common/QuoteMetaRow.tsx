import React from 'react';
import { Server, Star } from 'lucide-react';

import RealTimeClock from './RealTimeClock';

interface QuoteMetaRowProps {
  isWatchlisted: boolean;
  onToggleWatchlist: () => void | Promise<void>;
  backendStatus: boolean;
  extraActions?: React.ReactNode;
}

const QuoteMetaRow: React.FC<QuoteMetaRowProps> = ({
  isWatchlisted,
  onToggleWatchlist,
  backendStatus,
  extraActions,
}) => {
  return (
    <>
      <button
        onClick={onToggleWatchlist}
        className={`p-1 md:p-1.5 rounded-full transition-colors ${isWatchlisted ? 'text-yellow-400 bg-yellow-400/10' : 'text-slate-600 hover:text-slate-400 hover:bg-slate-800'}`}
        title={isWatchlisted ? '取消收藏' : '加入自选'}
      >
        <Star className={`w-3.5 h-3.5 md:w-4 md:h-4 ${isWatchlisted ? 'fill-yellow-400' : ''}`} />
      </button>

      {extraActions}

      <RealTimeClock />
      <span className={`flex items-center gap-1 ${backendStatus ? 'text-green-500/80' : 'text-red-500/80'}`}>
        <Server className="w-2.5 h-2.5 md:w-3 md:h-3" />
        {backendStatus ? '服务: 正常' : '服务: 断开'}
      </span>
    </>
  );
};

export default QuoteMetaRow;
