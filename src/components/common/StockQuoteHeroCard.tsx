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
  const latestDateText = latestLabel?.replace(/^最新\s*/, '');

  const StatItem = ({ label, value, emphasize = false }: { label: string; value: string; emphasize?: boolean }) => (
    <div className="flex min-w-0 items-baseline gap-1.5">
      <span className="shrink-0 whitespace-nowrap text-slate-500">{label}</span>
      <span className={`min-w-0 whitespace-nowrap tabular-nums ${emphasize ? 'font-semibold text-slate-100' : 'text-slate-300'}`}>{value}</span>
    </div>
  );

  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-2.5 shadow-lg md:p-3">
      <div className={`pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full opacity-20 blur-[80px] ${price >= previousClose ? 'bg-red-500' : 'bg-green-500'}`} />

      <div className="relative z-10 grid gap-2.5 lg:grid-cols-[minmax(220px,0.86fr)_minmax(0,2.85fr)_minmax(112px,0.52fr)] lg:items-center xl:grid-cols-[minmax(235px,0.82fr)_minmax(0,3fr)_minmax(124px,0.52fr)]">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2 overflow-hidden">
            <h1 className="min-w-0 truncate text-lg font-bold tracking-tight text-white md:text-xl">
              {name}
            </h1>
            {symbol ? (
              <span className="shrink-0 rounded border border-slate-800 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] font-normal uppercase text-slate-300 md:text-xs">
                {symbol}
              </span>
            ) : null}
          </div>

          {metaRow ? (
            <div className="mt-1 flex min-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap font-mono text-[9px] leading-4 text-slate-500 md:text-[10px]">
              {metaRow}
            </div>
          ) : null}
        </div>

        <div className="min-w-0 border-t border-slate-800 pt-2 font-mono text-[11px] lg:border-l lg:border-t-0 lg:pl-3 lg:pt-0 xl:pl-4">
          <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(128px,0.95fr)_minmax(190px,1.35fr)_minmax(70px,0.55fr)] xl:grid-cols-[minmax(142px,0.95fr)_minmax(210px,1.35fr)_minmax(76px,0.55fr)]">
            <div className="grid min-w-0 grid-cols-2 gap-x-2.5 gap-y-1">
              <StatItem label="今开" value={open.toFixed(2)} />
              <StatItem label="昨收" value={previousClose.toFixed(2)} />
              <StatItem label="最高" value={high.toFixed(2)} />
              <StatItem label="最低" value={low.toFixed(2)} />
            </div>
            <div className="grid min-w-0 grid-cols-2 gap-x-2.5 gap-y-1">
              <StatItem label="成交量" value={formatAmount(volume)} emphasize />
              <StatItem label="成交额" value={formatAmount(amount)} emphasize />
              <StatItem label="振幅" value={formatPercent(amplitude)} />
              <StatItem label="换手率" value={formatPercent(turnoverRate)} />
            </div>
            <div className="grid min-w-0 grid-cols-1 gap-y-1">
              <StatItem label="总市值" value={marketCapLabel ?? '--'} emphasize />
            </div>
          </div>
        </div>

        <div className="min-w-0 border-t border-slate-800 pt-2 text-left lg:border-l lg:border-t-0 lg:pl-3 lg:pt-0 lg:text-right xl:pl-4">
          <div className={`font-mono text-[31px] font-bold leading-none tracking-tight xl:text-[33px] ${priceColor}`}>
            {price.toFixed(2)}
          </div>
          <div className="mt-0.5 flex items-center gap-2 font-mono text-sm leading-none lg:justify-end">
            <span className={`flex items-center ${priceColor}`}>
              {price >= previousClose ? <ArrowUp className="mr-1 h-3 w-3" /> : <ArrowDown className="mr-1 h-3 w-3" />}
              {delta.toFixed(2)}
            </span>
            <span className={`rounded bg-slate-800/50 px-1.5 py-0.5 ${priceColor}`}>
              {pct.toFixed(2)}%
            </span>
          </div>
          {latestDateText ? (
            <div className="mt-0.5 whitespace-nowrap font-mono text-[10px] leading-none tabular-nums text-slate-500 lg:text-right">
              {latestDateText}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default StockQuoteHeroCard;
