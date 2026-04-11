import React from 'react';
import { Activity, Search, X } from 'lucide-react';

import { SearchResult } from '../../types';
import { APP_VERSION } from '../../version';

interface MarketTopHeaderProps {
  routeHref: string;
  routeLabel: string;
  routeTitle: string;
  secondaryRouteHref?: string;
  secondaryRouteLabel?: string;
  secondaryRouteTitle?: string;
  searchValue: string;
  isSearchFocused: boolean;
  searchResults: SearchResult[];
  searchHistory: SearchResult[];
  searchContainerRef?: React.RefObject<HTMLDivElement | null>;
  onSearchChange: (value: string) => void;
  onSearchFocus: () => void;
  onSearchBlur: () => void;
  onSearchKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => void | Promise<void>;
  onClearSearch: () => void;
  onSelectSearchResult: (result: SearchResult) => void | Promise<void>;
  onSelectHistory: (result: SearchResult) => void | Promise<void>;
  rightSlot?: React.ReactNode;
}

const MarketTopHeader: React.FC<MarketTopHeaderProps> = ({
  routeHref,
  routeLabel,
  routeTitle,
  secondaryRouteHref,
  secondaryRouteLabel,
  secondaryRouteTitle,
  searchValue,
  isSearchFocused,
  searchResults,
  searchHistory,
  searchContainerRef,
  onSearchChange,
  onSearchFocus,
  onSearchBlur,
  onSearchKeyDown,
  onClearSearch,
  onSelectSearchResult,
  onSelectHistory,
  rightSlot,
}) => {
  return (
    <header className="sticky top-0 z-50 bg-[#0f1623]/95 backdrop-blur border-b border-slate-800 shadow-md transition-all duration-300">
      <div className="max-w-[1600px] mx-auto p-3 md:p-4 flex flex-col md:flex-row items-center justify-between gap-3 md:gap-4">
        <div className="w-full flex items-center justify-between gap-3 md:gap-4">
          <div className="flex items-center gap-2 font-bold text-lg text-red-500 shrink-0">
            <Activity className="w-6 h-6" />
            <span className="hidden sm:inline">ZhangData</span>
            <span className="text-[10px] md:text-xs text-slate-500 bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded font-mono">
              v{APP_VERSION}
            </span>
            <a
              href={routeHref}
              className="text-[10px] md:text-xs text-cyan-300 bg-cyan-900/30 border border-cyan-700/50 px-1.5 py-0.5 rounded hover:bg-cyan-800/40 transition-colors"
              title={routeTitle}
            >
              {routeLabel}
            </a>
            {secondaryRouteHref && secondaryRouteLabel ? (
              <a
                href={secondaryRouteHref}
                className="text-[10px] md:text-xs text-emerald-300 bg-emerald-900/30 border border-emerald-700/50 px-1.5 py-0.5 rounded hover:bg-emerald-800/40 transition-colors"
                title={secondaryRouteTitle || secondaryRouteLabel}
              >
                {secondaryRouteLabel}
              </a>
            ) : null}
          </div>

          <div className="relative flex-1 max-w-3xl flex items-center gap-2 md:gap-4" ref={searchContainerRef}>
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 text-slate-400 w-4 h-4 md:w-5 md:h-5" />
              <input
                type="text"
                placeholder="代码(600519) 或 简称(茅台)"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-9 py-1.5 md:pl-10 md:pr-10 md:py-2 text-sm md:text-base text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                value={searchValue}
                onChange={(e) => onSearchChange(e.target.value)}
                onFocus={onSearchFocus}
                onBlur={onSearchBlur}
                onKeyDown={onSearchKeyDown}
              />
              {searchValue && (
                <button
                  onClick={onClearSearch}
                  className="absolute right-3 top-2 text-slate-500 hover:text-slate-300"
                  aria-label="清空搜索"
                >
                  <X className="h-4 w-4" />
                </button>
              )}

              {isSearchFocused && !searchValue && searchHistory.length > 0 && (
                <div className="absolute top-full left-0 mt-2 w-full md:w-96 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-80 overflow-y-auto z-50">
                  <div className="px-3 py-2 text-[10px] md:text-xs text-slate-500 bg-slate-900/50 border-b border-slate-700 flex justify-between items-center">
                    <span>最近访问</span>
                    <span className="bg-slate-700 px-1.5 py-0.5 rounded text-slate-300">History</span>
                  </div>
                  {searchHistory.map((res) => (
                    <button
                      key={res.symbol}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => onSelectHistory(res)}
                      className="w-full text-left px-3 py-2 md:px-4 md:py-2 hover:bg-slate-700 flex justify-between items-center group transition-colors border-b border-slate-800/50 last:border-0"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-300 text-sm md:text-base">{res.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500 font-mono">{res.code}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {searchResults.length > 0 && (
                <div className="absolute top-full left-0 mt-2 w-full md:w-96 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-60 overflow-y-auto z-50">
                  {searchResults.map((res) => (
                    <button
                      key={res.symbol}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => onSelectSearchResult(res)}
                      className="w-full text-left px-3 py-2 md:px-4 md:py-3 hover:bg-slate-700 flex justify-between items-center group transition-colors"
                    >
                      <div>
                        <span className="font-bold text-white text-sm md:text-base">{res.name}</span>
                        <span className="ml-2 text-[10px] md:text-xs text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded">{res.code}</span>
                      </div>
                      <span className="text-[10px] md:text-xs text-slate-500 group-hover:text-blue-400 uppercase">{res.market}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="hidden md:flex items-center gap-4 w-48 justify-end">
            {rightSlot}
          </div>
        </div>
      </div>
    </header>
  );
};

export default MarketTopHeader;
