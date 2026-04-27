import React, { useEffect, useMemo, useState } from 'react';

import { ExternalLink, FileText, Newspaper, ShieldAlert, TrendingUp } from 'lucide-react';

import HistoryView from '../dashboard/HistoryView';
import HistoryMultiframeFusionView from '../dashboard/HistoryMultiframeFusionView';
import { fetchSelectionHistoryMultiframe, fetchStockEventCoverage, fetchStockEventFeed } from '../../services/selectionService';
import { HistoryMultiframeGranularity, SearchResult, SelectionCandidateItem, SelectionProfileData, StockEventCoverageData, StockEventFeedItem } from '../../types';

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));

const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  if (Math.abs(num) >= 1e8) return `${(num / 1e8).toFixed(2)}亿`;
  if (Math.abs(num) >= 1e4) return `${(num / 1e4).toFixed(0)}万`;
  return num.toFixed(0);
};

const scoreTone = (score?: number | null) => {
  const value = Number(score || 0);
  if (value >= 75) return 'text-red-300';
  if (value >= 65) return 'text-amber-300';
  return 'text-slate-300';
};

const MetricCard: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone = 'text-slate-100' }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2">
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`mt-0.5 text-sm font-semibold ${tone}`}>{value}</div>
  </div>
);

const formatDateInput = (value: Date) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};
const parseDateInput = (value?: string | null) => {
  if (!value) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
};
const diffDays = (start?: string | null, end?: string | null) => {
  const startDate = parseDateInput(start);
  const endDate = parseDateInput(end);
  if (!startDate || !endDate) return null;
  return Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 86400000));
};
const shiftDate = (dateText: string, days: number) => {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateText;
  date.setDate(date.getDate() + days);
  return formatDateInput(date);
};

const maxDateText = (...values: Array<string | null | undefined>) => {
  const valid = values.map((item) => String(item || '').slice(0, 10)).filter(Boolean);
  if (!valid.length) return '';
  return valid.sort()[valid.length - 1];
};

interface Props {
  candidate: SelectionCandidateItem | null;
  profile: SelectionProfileData | null;
  displayName?: string;
  backendStatus: boolean;
  latestTradeDate?: string;
}

type EventGroupKey = 'official' | 'company' | 'media';

const EVENT_GROUP_META: Record<EventGroupKey, { label: string; desc: string }> = {
  official: { label: '官方披露', desc: '财报 / 公告 / 监管 / 再融资' },
  company: { label: '公司交流', desc: '互动问答 / 业绩说明会 / 投资者关系' },
  media: { label: '媒体资讯', desc: '快讯 / 长文 / 解读 / 调研速递' },
};

const classifyEventGroup = (item: StockEventFeedItem): EventGroupKey => {
  const title = String(item.title || '');
  if (
    item.source_type === 'qa' ||
    /投资者关系|说明会|互动|问答|调研|接待/i.test(title)
  ) {
    return 'company';
  }
  if (item.source_type === 'news') return 'media';
  return 'official';
};

const compactTime = (value?: string | null) => (value ? String(value).slice(0, 16) : '--');

const COVERAGE_DAY_OPTIONS = [30, 60, 90, 120, 180] as const;

const SelectionDecisionPanel: React.FC<Props> = ({ candidate, profile, displayName, backendStatus, latestTradeDate }) => {
  const [granularity, setGranularity] = useState<HistoryMultiframeGranularity>('1d');
  const [coverageDays, setCoverageDays] = useState<number>(90);
  const [chartStatus, setChartStatus] = useState({
    hasData: false,
    hasFormalL2History: false,
    hasPreviewRows: false,
    rowCount: 0,
    dataOrigin: 'none' as 'local' | 'cloud' | 'none',
  });
  const [eventFeed, setEventFeed] = useState<StockEventFeedItem[]>([]);
  const [eventCoverage, setEventCoverage] = useState<StockEventCoverageData | null>(null);
  const [loadingEvents, setLoadingEvents] = useState(false);

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
      setEventFeed([]);
      setEventCoverage(null);
      return;
    }
    let cancelled = false;
    setLoadingEvents(true);
    Promise.all([
      fetchStockEventFeed(candidate.symbol.toLowerCase(), { limit: 24 }),
      fetchStockEventCoverage(candidate.symbol.toLowerCase(), 365),
    ])
      .then(([feed, coverage]) => {
        if (cancelled) return;
        setEventFeed(feed?.items || []);
        setEventCoverage(coverage);
      })
      .finally(() => {
        if (!cancelled) setLoadingEvents(false);
      });
    return () => {
      cancelled = true;
    };
  }, [candidate]);

  useEffect(() => {
    if (!candidate?.trade_date) return;
    setGranularity('1d');
    setCoverageDays(90);
  }, [candidate?.symbol, candidate?.trade_date]);

  const effectiveEndDate = maxDateText(
    latestTradeDate,
    profile?.latest_available_trade_date,
    profile?.trade_date,
    candidate?.trade_date,
  ) || formatDateInput(new Date());
  const effectiveStartDate = useMemo(() => shiftDate(effectiveEndDate, -coverageDays), [coverageDays, effectiveEndDate]);
  const tradePlanMarkers = useMemo(() => {
    const plan = profile?.trade_plan;
    const markers: Array<{ date?: string | null; type: 'entry' | 'exit'; label: string; note?: string | null; simulated?: boolean }> = [];
    const seen = new Set<string>();
    const pushMarker = (marker: { date?: string | null; type: 'entry' | 'exit'; label: string; note?: string | null; simulated?: boolean }) => {
      if (!marker.date) return;
      const key = `${marker.date}-${marker.label}`;
      if (seen.has(key)) return;
      seen.add(key);
      markers.push(marker);
    };
    pushMarker({
      date: profile?.observe_date || profile?.discovery_date || candidate?.observe_date,
      type: 'entry',
      label: '观察',
      note: '纳入观察池',
    });
    pushMarker({
      date: profile?.launch_start_date,
      type: 'entry',
      label: '启动',
      note: profile?.launch_end_date ? `启动窗口 ${profile.launch_start_date} ~ ${profile.launch_end_date}` : '启动观察',
    });
    pushMarker({
      date: profile?.pullback_confirm_date || profile?.entry_signal_date || candidate?.entry_signal_date || plan?.signal_date,
      type: 'entry',
      label: '确认',
      note: '确认日收盘识别，次日执行',
    });
    pushMarker({
      date: plan?.entry_date || profile?.entry_date || candidate?.entry_date,
      type: 'entry',
      label: '买入',
      note: plan?.entry_price ? `买入价 ${fmtNum(plan.entry_price)}` : '计划买入日',
    });
    pushMarker({
      date: plan?.exit_signal_date || profile?.exit_signal_date || candidate?.exit_signal_date,
      type: 'exit',
      label: '卖出信号',
      note: [
        plan?.exit_reason || null,
        plan?.return_pct != null ? `收益 ${fmtPct(plan.return_pct)}` : null,
      ].filter(Boolean).join(' / '),
      simulated: plan?.exit_is_simulated,
    });
    const exitDate = plan?.exit_date || profile?.exit_date || candidate?.exit_date;
    const exitSignalDate = plan?.exit_signal_date || profile?.exit_signal_date || candidate?.exit_signal_date;
    if (exitDate && exitDate !== exitSignalDate) {
      pushMarker({
        date: exitDate,
        type: 'exit',
        label: '卖出',
        note: [
          plan?.exit_price ? `卖出价 ${fmtNum(plan.exit_price)}` : null,
          plan?.return_pct != null ? `收益 ${fmtPct(plan.return_pct)}` : null,
        ].filter(Boolean).join(' / '),
        simulated: plan?.exit_is_simulated,
      });
    }
    return markers;
  }, [candidate, profile]);
  const tradeSummary = useMemo(() => {
    const plan = profile?.trade_plan;
    if (!plan?.entry_date) return { text: null as string | null, tone: 'neutral' as const };
    const end = plan.exit_signal_date || effectiveEndDate;
    const holdingDays = diffDays(plan.entry_date, end);
    const returnPct = plan.return_pct;
    const daysText = holdingDays === null ? null : `持有${holdingDays}天`;
    const returnText = returnPct == null ? null : `${returnPct > 0 ? '+' : ''}${fmtPct(returnPct)}`;
    const text = [daysText, returnText].filter(Boolean).join(' / ');
    const tone = returnPct == null ? 'neutral' : returnPct >= 0 ? 'positive' : 'negative';
    return { text: text || null, tone };
  }, [effectiveEndDate, profile?.trade_plan]);
  const groupedEventFeed = useMemo(() => {
    const groups: Record<EventGroupKey, StockEventFeedItem[]> = {
      official: [],
      company: [],
      media: [],
    };
    eventFeed.forEach((item) => groups[classifyEventGroup(item)].push(item));
    return groups;
  }, [eventFeed]);

  if (!candidate || !profile || !activeStock) {
    return <div className="py-16 text-center text-sm text-slate-500">请选择左侧候选，右侧会直接加载复盘决策视图。</div>;
  }

  const candidateTypeText = (profile.candidate_types || candidate.candidate_types || []).join(' / ');
  const tradePlan = profile.trade_plan;
  const isStableCallback = profile.strategy_internal_id === 'stable_capital_callback' || candidate.strategy_internal_id === 'stable_capital_callback';
  const isTrendContinuation = profile.strategy_internal_id === 'trend_continuation_callback' || candidate.strategy_internal_id === 'trend_continuation_callback';
  const isProductStrategy = isStableCallback || isTrendContinuation;
  const strategyExplanation = (profile.research?.strategy_explanation as string[] | undefined) || [
    '这不是追涨停策略，而是先发现资金异动。',
    '启动后等待回调承接确认，确认日收盘识别，次日开盘买入。',
    '买入后主要看累计超大单是否从峰值明显撤退。',
    '多个风险信号同时出现时过滤。',
  ];
  const anchorDate = candidate.trade_date || profile.observe_date || profile.discovery_date || profile.entry_signal_date || profile.trade_plan?.signal_date || null;

  return (
    <div className="space-y-3">
      {profile.profile_date_fallback_used && profile.requested_trade_date && profile.requested_trade_date !== profile.trade_date ? (
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
          你当前查看的日期是 {profile.requested_trade_date}，但选股画像最新只算到 {profile.trade_date}，右侧判断先按最近可用画像日展示。
        </div>
      ) : null}

      <section>
        <div>
          <HistoryMultiframeFusionView
            activeStock={activeStock}
            backendStatus={backendStatus}
            granularity={granularity}
            onGranularityChange={setGranularity}
            startDate={effectiveStartDate}
            endDate={effectiveEndDate}
            signalDate={candidate.trade_date}
            signalLabel="信号日"
            defaultAnchorDate={anchorDate}
            tradeMarkers={tradePlanMarkers}
            tradeSummaryText={tradeSummary.text}
            tradeSummaryTone={tradeSummary.tone}
            headerRightSlot={(
              <div className="flex flex-wrap items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/50 p-1">
                {COVERAGE_DAY_OPTIONS.map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => setCoverageDays(days)}
                    className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors ${coverageDays === days ? 'bg-sky-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'}`}
                  >
                    {days}天
                  </button>
                ))}
              </div>
            )}
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
          {granularity === '1d' && !chartStatus.hasData ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/20 p-2">
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

      {isProductStrategy ? (
        <section className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-emerald-100">{isTrendContinuation ? '趋势中继高质量回踩' : '资金流回调稳健'}</div>
              <div className="mt-1 text-xs leading-5 text-emerald-50/80">
                {strategyExplanation.join('；')}
              </div>
            </div>
            <div className="grid min-w-[260px] grid-cols-2 gap-2 text-xs">
              <MetricCard label="买入状态" value={profile.entry_allowed === false ? (isTrendContinuation ? '观察中' : '风险过滤') : '可买入'} tone={profile.entry_allowed === false ? 'text-amber-200' : 'text-emerald-100'} />
              <MetricCard label="风险标签" value={`${profile.risk_count ?? candidate.risk_count ?? 0} 个`} tone={(profile.risk_count ?? candidate.risk_count ?? 0) >= 2 ? 'text-red-200' : 'text-emerald-100'} />
            </div>
          </div>
          <div className="mt-3 grid gap-2 text-xs md:grid-cols-4">
            <MetricCard label="纳入观察" value={profile.observe_date || profile.discovery_date || candidate.observe_date || '--'} />
            <MetricCard label={isTrendContinuation ? '回踩确认' : '回调确认'} value={profile.pullback_confirm_date || profile.entry_signal_date || candidate.entry_signal_date || '--'} />
            <MetricCard label="次日买入" value={profile.trade_plan?.entry_date || profile.entry_date || '--'} />
            <MetricCard label="卖出信号/卖出" value={[profile.trade_plan?.exit_signal_date || profile.exit_signal_date, profile.trade_plan?.exit_date || profile.exit_date].filter(Boolean).join(' / ') || '--'} />
          </div>
        </section>
      ) : null}

      <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
        <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr_1fr]">
          <div className="rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2">
            <div className="text-[11px] text-slate-500">信号链路</div>
            <div className="mt-1 text-sm text-slate-100">
              信号日 {candidate.trade_date || '--'}
              {tradePlan?.entry_date ? ` → 入场 ${tradePlan.entry_date}` : ''}
              {tradePlan?.exit_signal_date ? ` → 出场提示 ${tradePlan.exit_signal_date}` : ''}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {tradePlan?.exit_reason || profile.current_judgement || '当前无交易计划说明'}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2">
            <div className="text-[11px] text-slate-500">候选类型</div>
            <div className="mt-1 text-sm font-semibold text-slate-100">{candidateTypeText || '--'}</div>
            <div className="mt-1 text-xs text-slate-400">
              {profile.intent_profile?.intent_label ? `意图：${profile.intent_profile.intent_label}` : '当前无意图标签'}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2">
            <div className="text-[11px] text-slate-500">入场结论</div>
            <div className={`mt-1 text-sm font-semibold ${profile.entry_allowed === false ? 'text-amber-300' : 'text-emerald-300'}`}>
              {profile.entry_allowed === false ? (isTrendContinuation ? '观察中' : '已拦截') : isProductStrategy ? '可买入' : '允许进场'}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {(profile.entry_block_reasons || []).length > 0 ? profile.entry_block_reasons?.join('；') : isProductStrategy ? '确认日收盘识别，计划次日开盘买入' : '当前未触发入场拦截'}
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-3 xl:grid-cols-[1fr_1fr_1.2fr]">
        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <TrendingUp className="h-4 w-4 text-sky-400" />
            为什么选中它
          </div>
          <div className="mt-2 text-sm leading-6 text-slate-200">
            {isStableCallback
              ? [profile.setup_reason, profile.launch_reason, profile.pullback_reason].filter(Boolean).join('；')
              : profile.breakout_reason_summary || candidate.reason_summary || '当前未生成解释'}
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <MetricCard label="5日净流入" value={fmtAmt(profile.net_inflow_5d)} />
            <MetricCard label="10日正流入占比" value={fmtPct((profile.positive_inflow_ratio_10d || 0) * 100, 1)} />
            <MetricCard label="距前20高点" value={fmtPct(profile.breakout_vs_prev20_high_pct)} />
            <MetricCard label="L2确认强度" value={fmtNum(profile.l2_vs_l1_strength)} />
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldAlert className="h-4 w-4 text-amber-400" />
            出货风险判断
          </div>
          <div className="mt-2 text-sm leading-6 text-slate-200">
            {isStableCallback
              ? ((profile.risk_labels || candidate.risk_labels || []).length > 0 ? (profile.risk_labels || candidate.risk_labels || []).join('；') : '组合风险标签未达到过滤阈值。')
              : profile.distribution_reason_summary || '当前未见明显出货压力'}
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <MetricCard label="出货风险分" value={fmtNum(profile.distribution_score)} tone={scoreTone(profile.distribution_score)} />
            <MetricCard label="20日涨幅" value={fmtPct(profile.return_20d_pct)} />
            <MetricCard label="情绪热比" value={fmtNum(profile.sentiment_heat_ratio)} />
            <MetricCard label="L2事件" value={profile.l2_order_event_available ? '增强可用' : '弱化版'} />
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Newspaper className="h-4 w-4 text-violet-400" />
            事件时间线
          </div>
          <div className="mt-3 max-h-[320px] space-y-2 overflow-auto pr-1">
            {(profile.event_timeline || []).length > 0 ? (
              (profile.event_timeline || []).map((item, idx) => (
                <div key={`${item.kind}-${item.time}-${idx}`} className="rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2">
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

      <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Newspaper className="h-4 w-4 text-fuchsia-400" />
              事件依据 / 信息来源
            </div>
          </div>
          <div className="text-xs text-slate-500">
            {eventCoverage?.coverage_status === 'covered'
              ? `最近覆盖：${eventCoverage?.modules?.filter((item) => item.covered).length || 0} / ${eventCoverage?.modules?.length || 0} 类`
              : '当前无事件覆盖摘要'}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {(eventCoverage?.modules || [
            { module: 'report', label: '财报', covered: false, count: 0 },
            { module: 'announcement', label: '公告', covered: false, count: 0 },
            { module: 'qa', label: '互动问答', covered: false, count: 0 },
            { module: 'news', label: '财经资讯', covered: false, count: 0 },
            { module: 'regulatory', label: '监管', covered: false, count: 0 },
          ]).map((item) => (
            <div key={item.module} className="rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2">
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-slate-500">{item.label}</span>
                <span className="font-semibold text-slate-100">{item.count || 0}</span>
                <span className={item.covered ? 'text-emerald-300' : 'text-slate-500'}>{item.covered ? '已覆盖' : '暂无'}</span>
                <span className="text-slate-600">{compactTime(item.latest_event_time)}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-3 grid gap-3 xl:grid-cols-3">
          {(Object.keys(EVENT_GROUP_META) as EventGroupKey[]).map((groupKey) => {
            const group = EVENT_GROUP_META[groupKey];
            const items = groupedEventFeed[groupKey];
            return (
              <div key={groupKey} className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-white">{group.label}</div>
                  </div>
                  <div className="rounded-lg border border-slate-700 px-2 py-1 text-[11px] text-slate-400">{items.length}</div>
                </div>
                <div className="mt-3 max-h-[360px] space-y-2 overflow-auto pr-1">
                  {loadingEvents ? (
                    <div className="rounded-xl border border-dashed border-slate-800 px-3 py-4 text-sm text-slate-500">正在加载事件依据...</div>
                  ) : items.length > 0 ? (
                    items.map((item) => (
                      <div key={item.event_id} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
                        <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                          <span>{item.source_label || item.source_type_label || item.source || '事件源'}</span>
                          <span>{compactTime(item.published_at)}</span>
                        </div>
                        <div className="mt-1 text-sm font-medium text-slate-100">{item.title || '--'}</div>
                        {item.content && item.content !== item.title ? (
                          <div className="mt-1 line-clamp-2 text-xs text-slate-400">{item.content}</div>
                        ) : null}
                        <div className="mt-2 flex flex-wrap gap-2">
                          {item.raw_url ? (
                            <a
                              href={item.raw_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-[11px] text-slate-200 hover:border-slate-500"
                            >
                              <ExternalLink className="h-3 w-3" />
                              查看原文
                            </a>
                          ) : null}
                          {item.pdf_url ? (
                            <a
                              href={item.pdf_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 rounded-lg border border-cyan-700/60 px-2 py-1 text-[11px] text-cyan-200 hover:border-cyan-500"
                            >
                              <FileText className="h-3 w-3" />
                              查看PDF
                            </a>
                          ) : null}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-800 px-3 py-4 text-sm text-slate-500">当前分组暂无可展示事件。</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
};

export default SelectionDecisionPanel;
