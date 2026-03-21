import React from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';

interface StockQuoteHeroCardProps {
  name: string;
  symbol?: string;
  price: number;
  previousClose: number;
  open: number;
  high: number;
  low: number;
  volume?: number;
  amount?: number;
  turnoverRate?: number | null;
  latestLabel?: string;
  marketCapLabel?: string;
  metaRow?: React.ReactNode;
}

const getPriceColorClass = (current: number, base: number) => {
  if (current > base) return 'text-red-400';
  if (current < base) return 'text-green-400';
  return 'text-slate-200';
};

const formatAmount = (num?: number) => {
  if (!Number.isFinite(num) || (num || 0) <= 0) return '--';
  if ((num || 0) > 100000000) return ((num || 0) / 100000000).toFixed(2) + '亿';
  if ((num || 0) > 10000) return ((num || 0) / 10000).toFixed(0) + '万';
  return (num || 0).toFixed(0);
};

const formatPercent = (num?: number | null) => {
  if (!Number.isFinite(num)) return '--';
  return `${(num || 0).toFixed(2)}%`;
};

const StockQuoteHeroCard: React.FC<StockQuoteHeroCardProps> = ({
  name,
  symbol,
  price,
  previousClose,
  open,
  high,
  low,
  volume,
  amount,
  turnoverRate,
  latestLabel,
  marketCapLabel,
  metaRow,
}) => {
  const priceColor = getPriceColorClass(price, previousClose);
  const delta = price - previousClose;
  const pct = previousClose > 0 ? (delta / previousClose) * 100 : 0;
  const amplitude = previousClose > 0 ? ((high - low) / previousClose) * 100 : null;

  const StatItem = ({ label, value, emphasize = false }: { label: string; value: string; emphasize?: boolean }) => (
    <div className="flex items-center gap-1.5 md:gap-2 min-w-0">
      <span className="text-slate-500 whitespace-nowrap">{label}</span>
      <span className={`truncate ${emphasize ? 'text-slate-100' : 'text-slate-300'}`}>{value}</span>
    </div>
  );

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-lg relative overflow-hidden">
      <div className={`absolute -top-10 -right-10 w-40 h-40 rounded-full blur-[80px] opacity-20 pointer-events-none ${price >= previousClose ? 'bg-red-500' : 'bg-green-500'}`} />

      <div className="flex justify-between items-start md:items-center relative z-10 gap-3 md:gap-4 flex-col md:flex-row">
        <div className="flex items-start gap-4 md:gap-6 flex-1 min-w-0 w-full">
          <div className="min-w-[180px] md:min-w-[220px] flex-shrink-0">
            <div className="flex items-center gap-2 md:gap-3 min-w-0 flex-wrap">
              <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight truncate">
                {name}
              </h1>
              {symbol ? (
                <span className="text-[10px] md:text-xs font-mono text-slate-300 font-normal bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800 uppercase">
                  {symbol}
                </span>
              ) : null}
            </div>

            {metaRow ? (
              <div className="flex items-center gap-2 md:gap-3 text-[10px] text-slate-500 font-mono mt-2">
                {metaRow}
              </div>
            ) : null}
          </div>

          <div className="flex-1 min-w-0 border-l border-slate-800 pl-4 md:pl-6">
            <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_1.2fr_0.85fr] gap-3 md:gap-4 text-[11px] md:text-xs font-mono">
              <div className="grid grid-cols-1 gap-1.5 min-w-0">
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 min-w-0">
                  <StatItem label="今开" value={open.toFixed(2)} />
                  <StatItem label="昨收" value={previousClose.toFixed(2)} />
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 min-w-0">
                  <StatItem label="最高" value={high.toFixed(2)} />
                  <StatItem label="最低" value={low.toFixed(2)} />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-1.5 min-w-0">
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 min-w-0">
                  <StatItem label="成交量" value={formatAmount(volume)} emphasize />
                  <StatItem label="成交额" value={formatAmount(amount)} emphasize />
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 min-w-0">
                  <StatItem label="振幅" value={formatPercent(amplitude)} />
                  <StatItem label="换手率" value={formatPercent(turnoverRate)} />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-1.5 min-w-0">
                <StatItem label="总市值" value={marketCapLabel ?? '--'} emphasize />
                {latestLabel ? (
                  <StatItem label="最新日期" value={latestLabel.replace(/^最新\s*/, '')} />
                ) : (
                  <div className="h-[18px]" />
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="w-full md:w-auto md:min-w-[180px] text-right pl-0 md:pl-4 shrink-0 md:border-l md:border-slate-800 ml-auto">
          <div className={`text-4xl font-mono font-bold tracking-tight ${priceColor}`}>
            {price.toFixed(2)}
          </div>
          <div className={`text-sm font-mono flex items-center justify-end gap-2 mt-1 ${priceColor}`}>
            <span className="flex items-center">
              {price >= previousClose ? <ArrowUp className="w-3 h-3 mr-1" /> : <ArrowDown className="w-3 h-3 mr-1" />}
              {delta.toFixed(2)}
            </span>
            <span className="bg-slate-800/50 px-1.5 py-0.5 rounded">
              {pct.toFixed(2)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StockQuoteHeroCard;
