import React, { useEffect, useState } from 'react';
import { ArrowLeft, BrainCircuit, FileText, LineChart, RefreshCw } from 'lucide-react';

import MarketTopHeader from '../common/MarketTopHeader';
import { APP_VERSION } from '../../version';
import { fetchSelectionPpoBacktestReport } from '../../services/selectionService';
import { PpoBacktestReport } from '../../types';

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className="mt-1 text-sm font-semibold text-slate-100">{value}</div>
  </div>
);

const ModelTrainingPage: React.FC = () => {
  const [report, setReport] = useState<PpoBacktestReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchSelectionPpoBacktestReport()
      .then((payload) => {
        if (!cancelled) setReport(payload);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const summary = report?.summary || {};

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <MarketTopHeader
        routeHref="/"
        routeLabel="回到首页"
        routeTitle="返回首页"
        searchValue=""
        isSearchFocused={false}
        searchResults={[]}
        searchHistory={[]}
        onSearchChange={() => {}}
        onSearchFocus={() => {}}
        onSearchBlur={() => {}}
        onSearchKeyDown={() => {}}
        onClearSearch={() => {}}
        onSelectSearchResult={() => {}}
        onSelectHistory={() => {}}
        rightSlot={null}
      />
      <main className="mx-auto max-w-[1280px] space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <a
            href="/"
            className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回主页面
          </a>
          <div className="flex items-center gap-2 text-lg font-bold text-white">
            <BrainCircuit className="h-5 w-5 text-fuchsia-300" />
            模型训练
          </div>
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
            v{APP_VERSION}
          </span>
        </div>

        <section className="rounded-xl border border-slate-800 bg-slate-900/75">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <FileText className="h-4 w-4 text-fuchsia-300" />
              训练任务清单
            </div>
            {loading ? <span className="inline-flex items-center gap-1 text-xs text-slate-500"><RefreshCw className="h-3.5 w-3.5 animate-spin" />加载中</span> : null}
          </div>
          <div className="divide-y divide-slate-800">
            <a href="/model-training/ppo-backtest" className="block px-4 py-4 transition hover:bg-slate-950/35">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <LineChart className="h-4 w-4 text-fuchsia-300" />
                    <span className="text-sm font-semibold text-white">PPO 回测复盘</span>
                    <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-500">历史训练产物</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {report?.range?.start_date || '--'} ~ {report?.range?.end_date || '--'}
                  </div>
                </div>
                <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-3">
                  <Metric label="总收益" value={fmtPct(summary.total_return_pct)} />
                  <Metric label="最大回撤" value={fmtPct(summary.max_drawdown_pct)} />
                  <Metric label="交易数" value={String(summary.trade_count || 0)} />
                </div>
              </div>
            </a>
          </div>
        </section>
      </main>
    </div>
  );
};

export default ModelTrainingPage;
