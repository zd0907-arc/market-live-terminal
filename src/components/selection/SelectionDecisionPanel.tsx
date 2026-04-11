import React, { useEffect, useMemo, useState } from 'react';

import { AlertTriangle, CheckCircle2, Clock3, Newspaper, ShieldAlert, TrendingUp } from 'lucide-react';

import QuoteMetaRow from '../common/QuoteMetaRow';
import StockQuoteHeroCard from '../common/StockQuoteHeroCard';
import HistoryView from '../dashboard/HistoryView';
import HistoryMultiframeFusionView from '../dashboard/HistoryMultiframeFusionView';
import * as StockService from '../../services/stockService';
import { fetchSelectionHistoryMultiframe } from '../../services/selectionService';
import { HistoryMultiframeGranularity, SearchResult, SelectionCandidateItem, SelectionProfileData } from '../../types';

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));

const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  if (Math.abs(num) >= 1e8) return `${(num / 1e8).toFixed(2)}亿`;
  if (Math.abs(num) >= 1e4) return `${(num / 1e4).toFixed(0)}万`;
  return num.toFixed(0);
};

const fmtMarketCap = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value)) || Number(value) <= 0) return '--';
  return `${(Number(value) / 1e8).toFixed(2)}亿`;
};

const scoreTone = (score?: number | null) => {
  const value = Number(score || 0);
  if (value >= 75) return 'text-red-300';
  if (value >= 65) return 'text-amber-300';
  return 'text-slate-300';
};

const MetricCard: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone = 'text-slate-100' }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const formatDateInput = (value: Date) => value.toISOString().slice(0, 10);
const shiftDate = (dateText: string, days: number) => {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateText;
  date.setDate(date.getDate() + days);
  return formatDateInput(date);
};

interface Props {
  candidate: SelectionCandidateItem | null;
  profile: SelectionProfileData | null;
  displayName?: string;
}

const SelectionDecisionPanel: React.FC<Props> = ({ candidate, profile, displayName }) => {
  const [quote, setQuote] = useState<any | null>(null);
  const [turnoverRate, setTurnoverRate] = useState<number | null>(null);
  const [backendStatus, setBackendStatus] = useState(false);
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [granularity, setGranularity] = useState<HistoryMultiframeGranularity>('1d');
  const [windowMode, setWindowMode] = useState<'40d' | '90d' | 'to_now' | 'custom'>('90d');
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');
  const [chartStatus, setChartStatus] = useState({
    hasData: false,
    hasFormalL2History: false,
    hasPreviewRows: false,
    rowCount: 0,
    dataOrigin: 'none' as 'local' | 'cloud' | 'none',
  });

  const activeStock = useMemo<SearchResult | null>(() => {
    if (!candidate) return null;
    const symbol = candidate.symbol.toLowerCase();
    return {
      symbol,
      code: symbol.slice(2),
      market: symbol.slice(0, 2),
      name: (displayName || candidate.name || symbol).trim(),
    };
  }, [candidate, displayName]);

  useEffect(() => {
    if (!candidate) {
      setQuote(null);
      setTurnoverRate(null);
      setIsWatchlisted(false);
      return;
    }
    const symbol = candidate.symbol.toLowerCase();
    let cancelled = false;
    StockService.fetchQuote(symbol).then((res) => {
      if (!cancelled) setQuote(res);
    }).catch(() => {
      if (!cancelled) setQuote(null);
    });
    StockService.fetchSentimentData(symbol).then((data) => {
      if (!cancelled) {
        const value = Number(data?.turnover_rate);
        setTurnoverRate(Number.isFinite(value) ? value : null);
      }
    }).catch(() => {
      if (!cancelled) setTurnoverRate(null);
    });
    StockService.getWatchlist().then((items) => {
      if (!cancelled) setIsWatchlisted(Boolean(items.find((item) => item.symbol === symbol)));
    }).catch(() => {
      if (!cancelled) setIsWatchlisted(false);
    });
    StockService.checkBackendHealth().then((ok) => {
      if (!cancelled) setBackendStatus(ok);
    }).catch(() => {
      if (!cancelled) setBackendStatus(false);
    });
    return () => {
      cancelled = true;
    };
  }, [candidate]);

  useEffect(() => {
    if (!candidate?.trade_date) return;
    const signalDate = candidate.trade_date;
    const today = formatDateInput(new Date());
    setGranularity('1d');
    setWindowMode('90d');
    setWindowStart(shiftDate(signalDate, -20));
    setWindowEnd(shiftDate(signalDate, 90) > today ? today : shiftDate(signalDate, 90));
  }, [candidate?.symbol, candidate?.trade_date]);

  const handleToggleWatchlist = async () => {
    if (!candidate) return;
    const symbol = candidate.symbol.toLowerCase();
    const resolvedName = (displayName || candidate.name || symbol).trim();
    if (isWatchlisted) {
      await StockService.removeFromWatchlist(symbol);
      setIsWatchlisted(false);
      return;
    }
    await StockService.addToWatchlist(symbol, resolvedName);
    setIsWatchlisted(true);
  };

  const applyWindowPreset = (mode: '40d' | '90d' | 'to_now') => {
    if (!candidate?.trade_date) return;
    const signalDate = candidate.trade_date;
    const today = formatDateInput(new Date());
    const nextStart = shiftDate(signalDate, -20);
    const nextEnd = mode === '40d'
      ? shiftDate(signalDate, 40)
      : mode === '90d'
        ? shiftDate(signalDate, 90)
        : today;
    setWindowMode(mode);
    setWindowStart(nextStart);
    setWindowEnd(nextEnd > today ? today : nextEnd);
  };

  if (!candidate || !profile || !activeStock) {
    return <div className="py-16 text-center text-sm text-slate-500">请选择左侧候选，右侧会直接加载复盘决策视图。</div>;
  }

  const heroPrice = Number(quote?.price ?? profile.close ?? 0);
  const previousClose = Number(quote?.lastClose ?? profile.prev_close ?? profile.close ?? 0);
  const open = Number(quote?.open ?? profile.close ?? 0);
  const high = Number(quote?.high ?? profile.close ?? 0);
  const low = Number(quote?.low ?? profile.close ?? 0);
  const heroName = (quote?.name || displayName || profile.name || candidate.name || candidate.symbol).trim();
  const effectiveStartDate = useMemo(() => {
    if (!windowStart || !windowEnd) return undefined;
    if (granularity === '1d') return windowStart;
    const maxLookback = granularity === '1h' ? 60 : 30;
    const clippedStart = shiftDate(windowEnd, -maxLookback);
    return clippedStart > windowStart ? clippedStart : windowStart;
  }, [granularity, windowEnd, windowStart]);
  const effectiveEndDate = windowEnd || undefined;
  const intradayWindowClipped = granularity !== '1d' && !!windowStart && !!effectiveStartDate && effectiveStartDate !== windowStart;

  return (
    <div className="space-y-4">
      <StockQuoteHeroCard
        name={heroName}
        symbol={candidate.symbol}
        price={heroPrice}
        previousClose={previousClose}
        open={open}
        high={high}
        low={low}
        volume={quote?.volume}
        amount={quote?.amount}
        turnoverRate={turnoverRate}
        latestLabel={`最新 ${candidate.trade_date}`}
        marketCapLabel={fmtMarketCap(profile.market_cap)}
        metaRow={(
          <QuoteMetaRow
            isWatchlisted={isWatchlisted}
            onToggleWatchlist={handleToggleWatchlist}
            backendStatus={backendStatus}
          />
        )}
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          当前综合判断
        </div>
        {profile.profile_date_fallback_used && profile.requested_trade_date && profile.requested_trade_date !== profile.trade_date ? (
          <div className="mt-3 rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
            你当前查看的日期是 {profile.requested_trade_date}，但选股画像最新只算到 {profile.trade_date}，右侧判断先按最近可用画像日展示；下方图表仍按你选的时间窗看真实历史。
          </div>
        ) : null}
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="当前阶段" value={profile.current_judgement || '--'} tone="text-cyan-300" />
          <MetricCard label="启动确认分" value={fmtNum(profile.breakout_score)} tone={scoreTone(profile.breakout_score)} />
          <MetricCard label="吸筹前置分" value={fmtNum(profile.stealth_score)} tone={scoreTone(profile.stealth_score)} />
          <MetricCard label="出货风险级别" value={profile.distribution_risk_level || '--'} tone={profile.distribution_risk_level === '高' ? 'text-red-300' : profile.distribution_risk_level === '中' ? 'text-amber-300' : 'text-emerald-300'} />
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Clock3 className="h-4 w-4 text-amber-400" />
              复盘决策视图
            </div>
            <div className="inline-flex gap-2">
              {[
                { value: '5m', label: '5分' },
                { value: '30m', label: '30分' },
                { value: '1h', label: '1小时' },
                { value: '1d', label: '日线' },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setGranularity(item.value as HistoryMultiframeGranularity)}
                  className={`rounded-lg px-2.5 py-1 text-xs ${granularity === item.value ? 'bg-slate-200 text-slate-900' : 'border border-slate-700 text-slate-300'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
              <div className="text-[11px] text-slate-500">观察窗口</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {[
                  { key: '40d', label: '信号后40天' },
                  { key: '90d', label: '信号后90天' },
                  { key: 'to_now', label: '看到现在' },
                ].map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => applyWindowPreset(item.key as '40d' | '90d' | 'to_now')}
                    className={`rounded-lg px-2.5 py-1 text-xs ${windowMode === item.key ? 'bg-sky-200 text-slate-900' : 'border border-slate-700 text-slate-300'}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-xs text-slate-400">
                开始日期
                <input
                  type="date"
                  value={windowStart}
                  onChange={(e) => {
                    setWindowMode('custom');
                    setWindowStart(e.target.value);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </label>
              <label className="text-xs text-slate-400">
                结束日期
                <input
                  type="date"
                  value={windowEnd}
                  onChange={(e) => {
                    setWindowMode('custom');
                    setWindowEnd(e.target.value);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </label>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/30 p-2">
          <HistoryMultiframeFusionView
            activeStock={activeStock}
            backendStatus={backendStatus}
            granularity={granularity}
            onGranularityChange={setGranularity}
            startDate={effectiveStartDate}
            endDate={effectiveEndDate}
            fetchRows={({ symbol, granularity: nextGranularity, days, startDate, endDate, includeTodayPreview }) =>
              fetchSelectionHistoryMultiframe(symbol, {
                granularity: nextGranularity,
                days,
                startDate,
                endDate,
                includeTodayPreview,
              })
            }
            onDataStatusChange={setChartStatus}
          />
        </div>

        <div className="mt-3 space-y-2">
          <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              当前默认按“信号日前后窗口”看，不再直接把一年多历史全堆上去。日线优先用于看波段结构；分钟级若窗口过长，会自动收敛到更近的局部窗口。
            </div>
          </div>
          {intradayWindowClipped ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
              当前是分钟级图，为保证可读性，已自动聚焦到结束日前最近一段窗口；若想看更长周期，请切回日线。
            </div>
          ) : null}
          {chartStatus.dataOrigin === 'cloud' ? (
            <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
              当前右侧数据已自动走云端只读回退，所以即使你本地没补齐，这只票也能先直接看生产端的历史多维结果。
            </div>
          ) : null}
          {granularity === '1d' && !chartStatus.hasData ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/20 p-2">
              <div className="mb-2 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-xs text-slate-400">
                这只票当前还没有正式 L2 日线底座，先给你补一个日级资金流 fallback 视图，至少能看价格、净流入和日级资金变化。
              </div>
              <HistoryView
                activeStock={activeStock}
                backendStatus={backendStatus}
                forceViewMode="daily"
                initialHistorySource="local"
              />
            </div>
          ) : null}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr_1.2fr]">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <TrendingUp className="h-4 w-4 text-sky-400" />
            为什么选中它
          </div>
          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-200">
            {profile.breakout_reason_summary || candidate.reason_summary || '当前未生成解释'}
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <MetricCard label="5日净流入" value={fmtAmt(profile.net_inflow_5d)} />
            <MetricCard label="10日正流入占比" value={fmtPct((profile.positive_inflow_ratio_10d || 0) * 100, 1)} />
            <MetricCard label="距前20高点" value={fmtPct(profile.breakout_vs_prev20_high_pct)} />
            <MetricCard label="L2确认强度" value={fmtNum(profile.l2_vs_l1_strength)} />
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldAlert className="h-4 w-4 text-amber-400" />
            出货风险判断
          </div>
          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-200">
            {profile.distribution_reason_summary || '当前未见明显出货压力'}
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <MetricCard label="出货风险分" value={fmtNum(profile.distribution_score)} tone={scoreTone(profile.distribution_score)} />
            <MetricCard label="20日涨幅" value={fmtPct(profile.return_20d_pct)} />
            <MetricCard label="情绪热比" value={fmtNum(profile.sentiment_heat_ratio)} />
            <MetricCard label="L2事件" value={profile.l2_order_event_available ? '增强可用' : '弱化版'} />
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Newspaper className="h-4 w-4 text-violet-400" />
            事件时间线
          </div>
          <div className="mt-3 max-h-[360px] space-y-2 overflow-auto pr-1">
            {(profile.event_timeline || []).length > 0 ? (
              (profile.event_timeline || []).map((item, idx) => (
                <div key={`${item.kind}-${item.time}-${idx}`} className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                    <span>{item.kind === 'daily_score' ? '情绪日评分' : `${item.source || '事件源'} / ${item.event_type || '事件'}`}</span>
                    <span>{item.time || '--'}</span>
                  </div>
                  <div className="mt-1 text-sm text-slate-200">
                    {item.kind === 'daily_score'
                      ? `${item.direction_label || '情绪'} / ${item.risk_tag || '无标签'} / 分数 ${fmtNum(item.sentiment_score)}`
                      : item.content || '--'}
                  </div>
                  {item.summary_text ? <div className="mt-1 text-xs text-slate-400">{item.summary_text}</div> : null}
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-slate-800 p-4 text-sm text-slate-500">当前无可展示事件。</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default SelectionDecisionPanel;
