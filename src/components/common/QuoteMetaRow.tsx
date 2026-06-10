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
        className={`shrink-0 rounded-full p-0.5 transition-colors md:p-1 ${isWatchlisted ? 'bg-yellow-400/10 text-yellow-400' : 'text-slate-600 hover:bg-slate-800 hover:text-slate-400'}`}
        title={isWatchlisted ? '取消收藏' : '加入自选'}
      >
        <Star className={`h-3.5 w-3.5 ${isWatchlisted ? 'fill-yellow-400' : ''}`} />
      </button>

      {extraActions}

      <RealTimeClock />
      <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap ${backendStatus ? 'text-green-500/80' : 'text-red-500/80'}`}>
        <Server className="h-2.5 w-2.5" />
        {backendStatus ? '服务正常' : '服务断开'}
      </span>
    </>
  );
};

export default QuoteMetaRow;
