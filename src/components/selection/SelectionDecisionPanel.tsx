import React, { useEffect, useMemo, useRef, useState } from 'react';

import { ExternalLink, FileText, Newspaper, ShieldAlert, Sparkles, TrendingUp } from 'lucide-react';

import HistoryView from '../dashboard/HistoryView';
import HistoryMultiframeFusionView from '../dashboard/HistoryMultiframeFusionView';
import { fetchSelectionHistoryMultiframe, fetchSelectionResearchContext, prepareSelectionResearchContext } from '../../services/selectionService';
import {
  HistoryMultiframeGranularity,
  SearchResult,
  SelectionCandidateItem,
  SelectionEventInterpretation,
  SelectionProfileData,
  SelectionResearchContextData,
  SelectionStrategy,
  StockEventCoverageData,
  StockEventFeedItem,
} from '../../types';

const fmtPct = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : `${Number(value).toFixed(digits)}%`);
const fmtNum = (value?: number | null, digits = 2) => (value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(digits));

const fmtAmt = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  if (Math.abs(num) >= 1e8) return `${(num / 1e8).toFixed(2)}亿`;
  if (Math.abs(num) >= 1e4) return `${(num / 1e4).toFixed(0)}万`;
  return num.toFixed(0);
};

const fmtSignedPct = (value?: number | null, digits = 2) => {
  if (value == null || Number.isNaN(Number(value))) return '--';
  const num = Number(value);
  return `${num > 0 ? '+' : ''}${num.toFixed(digits)}%`;
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

type StrategyInsight = React.ComponentProps<typeof HistoryMultiframeFusionView>['strategyInsight'];

const normalizeStrategy = (value?: string | null): SelectionStrategy => {
  const text = String(value || '').trim();
  if (['stable_capital_callback', 'trend_continuation_callback', 'stealth', 'breakout', 'distribution', 'v2'].includes(text)) {
    return text as SelectionStrategy;
  }
  return 'stable_capital_callback';
};

const statusTone = (value?: string) => {
  if (['强', 'confirmed', '资金+逻辑一致', '可继续研究'].includes(String(value || ''))) return 'text-emerald-200 border-emerald-500/30 bg-emerald-500/10';
  if (['中', 'logic_only', 'funds_only', '等资金确认', '按资金策略，提示一日游风险'].includes(String(value || ''))) return 'text-amber-200 border-amber-500/30 bg-amber-500/10';
  if (['conflict', '资金冲突'].includes(String(value || ''))) return 'text-red-200 border-red-500/30 bg-red-500/10';
  return 'text-slate-300 border-slate-700 bg-slate-900/60';
};

const TinyBadge: React.FC<{ children: React.ReactNode; tone?: string }> = ({ children, tone = 'text-slate-300 border-slate-700 bg-slate-900/60' }) => (
  <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${tone}`}>
    {children}
  </span>
);

const levelText = (metric: string, value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return '暂无';
  const num = Number(value);
  if (metric === 'active_buy_strength') {
    if (num > 5) return '很强';
    if (num > 2) return '强';
    if (num > 0) return '达标';
    return '不达标';
  }
  if (metric === 'net_ratio_pct') {
    if (num > 6) return '很强';
    if (num > 3) return '强';
    if (num >= 0) return '达标';
    return '不达标';
  }
  if (metric === 'score') {
    if (num >= 75) return '很强';
    if (num >= 60) return '较强';
    if (num >= 45) return '可观察';
    return '偏弱';
  }
  return '';
};

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
  const [researchContext, setResearchContext] = useState<SelectionResearchContextData | null>(null);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [preparingContext, setPreparingContext] = useState(false);
  const [prepareMessage, setPrepareMessage] = useState<string | null>(null);
  const autoPrepareKeys = useRef<Set<string>>(new Set());

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
      setResearchContext(null);
      setPrepareMessage(null);
      return;
    }
    let cancelled = false;
    setLoadingEvents(true);
    const strategy = normalizeStrategy(profile?.strategy_internal_id || candidate.strategy_internal_id);
    const contextDate = candidate.trade_date || profile?.requested_trade_date || profile?.trade_date;
    fetchSelectionResearchContext(candidate.symbol.toLowerCase(), contextDate, strategy, {
      eventLimit: 24,
      eventDays: 365,
      seriesDays: 60,
    })
      .then((context) => {
        if (cancelled) return;
        setResearchContext(context);
        setEventFeed(context?.stock_event_feed?.items || []);
        setEventCoverage(context?.stock_event_coverage || null);
      })
      .finally(() => {
        if (!cancelled) setLoadingEvents(false);
      });
    return () => {
      cancelled = true;
    };
  }, [candidate?.symbol, candidate?.trade_date, candidate?.strategy_internal_id, profile?.strategy_internal_id, profile?.trade_date, profile?.requested_trade_date]);

  useEffect(() => {
    if (!candidate || !profile || loadingEvents || preparingContext) return;
    const status = researchContext?.stock_event_coverage?.coverage_status || '';
    const hasLlmBrief = researchContext?.decision_brief?.source === 'llm_decision_brief_v1';
    const shouldPrepare = !researchContext || !hasLlmBrief || ['db_table_empty', 'symbol_not_hydrated_or_no_events', 'no_recent_events', 'no_events_in_window', 'table_missing'].includes(status);
    if (!shouldPrepare) return;
    const key = `${candidate.symbol}-${candidate.trade_date}-${profile.strategy_internal_id || candidate.strategy_internal_id || ''}`;
    if (autoPrepareKeys.current.has(key)) return;
    autoPrepareKeys.current.add(key);

    let cancelled = false;
    const strategy = normalizeStrategy(profile?.strategy_internal_id || candidate.strategy_internal_id);
    const contextDate = candidate.trade_date || profile?.requested_trade_date || profile?.trade_date;
    setPreparingContext(true);
    setPrepareMessage('正在补拉公司概况、财务快照和事件源，并调用 LLM 生成公司概况/决策解释...');
    prepareSelectionResearchContext(candidate.symbol.toLowerCase(), contextDate, strategy, {
      useLlm: true,
      eventLimit: 50,
      newsDays: 45,
      seriesDays: 60,
    }).then((result) => {
      if (cancelled) return;
      if (result?.context) {
        setResearchContext(result.context);
        setEventFeed(result.context.stock_event_feed?.items || []);
        setEventCoverage(result.context.stock_event_coverage || null);
        const hydrateStage = result.stages?.find((item) => item.step === 'hydrate_events');
        const companyStage = result.stages?.find((item) => item.step === 'fetch_company_profile');
        const financialStage = result.stages?.find((item) => item.step === 'fetch_financial_snapshot');
        const briefStage = result.stages?.find((item) => item.step === 'generate_decision_brief');
        setPrepareMessage([
          hydrateStage?.status === 'ok' ? `事件源自动补拉完成，新增/更新 ${hydrateStage.upserted_count || 0} 条` : hydrateStage?.message,
          companyStage?.status === 'ok' ? '公司概况已补齐' : companyStage?.message,
          financialStage?.status === 'ok' ? `财务快照已补齐${financialStage.latest_period ? `（${financialStage.latest_period}）` : ''}` : financialStage?.message,
          briefStage?.status === 'ok' ? 'LLM研究摘要已生成' : briefStage?.message ? `LLM摘要未生成：${briefStage.message}` : null,
        ].filter(Boolean).join('；') || '自动补拉完成。');
      }
    }).finally(() => {
      if (!cancelled) setPreparingContext(false);
    });
    return () => {
      cancelled = true;
    };
  }, [candidate, profile, loadingEvents, preparingContext, researchContext]);

  const handlePrepareContext = async () => {
    if (!candidate) return;
    const strategy = normalizeStrategy(profile?.strategy_internal_id || candidate.strategy_internal_id);
    const contextDate = candidate.trade_date || profile?.requested_trade_date || profile?.trade_date;
    setPreparingContext(true);
    setPrepareMessage('正在补拉公告/问答/新闻，并生成公司概况和决策解释，可能需要几十秒...');
    const result = await prepareSelectionResearchContext(candidate.symbol.toLowerCase(), contextDate, strategy, {
      useLlm: true,
      eventLimit: 50,
      newsDays: 45,
      seriesDays: 60,
    });
    if (result?.context) {
      setResearchContext(result.context);
      setEventFeed(result.context.stock_event_feed?.items || []);
      setEventCoverage(result.context.stock_event_coverage || null);
      const hydrateStage = result.stages?.find((item) => item.step === 'hydrate_events');
      const companyStage = result.stages?.find((item) => item.step === 'fetch_company_profile');
      const financialStage = result.stages?.find((item) => item.step === 'fetch_financial_snapshot');
      const llmStage = result.stages?.find((item) => item.step === 'generate_decision_brief');
      const parts = [
        hydrateStage?.status === 'ok' ? `事件补拉完成，新增/更新 ${hydrateStage.upserted_count || 0} 条` : hydrateStage?.message,
        companyStage?.status === 'ok' ? '公司介绍已获取' : companyStage?.message ? `公司介绍缺失：${companyStage.message}` : null,
        financialStage?.status === 'ok' ? `财务快照已获取${financialStage.latest_period ? `（${financialStage.latest_period}）` : ''}` : financialStage?.message ? `财务快照缺失：${financialStage.message}` : null,
        llmStage?.status === 'ok' ? '公司概况/决策解释已生成' : llmStage?.message ? `LLM摘要未生成：${llmStage.message}` : null,
      ].filter(Boolean);
      setPrepareMessage(parts.join('；') || '研究上下文已刷新。');
    } else {
      setPrepareMessage('准备失败：后端未返回有效上下文。');
    }
    setPreparingContext(false);
  };

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
    const observeDate = profile?.observe_date || profile?.discovery_date || candidate?.observe_date;
    const launchStartDate = profile?.launch_start_date;
    pushMarker({
      date: observeDate,
      type: 'entry',
      label: observeDate && launchStartDate && observeDate === launchStartDate ? '观察/启动' : '观察',
      note: observeDate && launchStartDate && observeDate === launchStartDate ? '纳入观察池，趋势启动观察' : '纳入观察池',
    });
    if (launchStartDate && launchStartDate !== observeDate) {
      pushMarker({
        date: launchStartDate,
        type: 'entry',
        label: '启动',
        note: profile?.launch_end_date ? `启动窗口 ${profile.launch_start_date} ~ ${profile.launch_end_date}` : '启动观察',
      });
    }
    pushMarker({
      date: profile?.pullback_confirm_date || profile?.entry_signal_date || candidate?.entry_signal_date || plan?.signal_date,
      type: 'entry',
      label: '买入确认',
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
  const eventInterpretation = researchContext?.event_interpretation as SelectionEventInterpretation | undefined;
  const decisionBrief = researchContext?.decision_brief;
  const companyOverviewText = decisionBrief?.company_overview
    || [
      researchContext?.company_profile?.company_name || researchContext?.name || candidate.name || candidate.symbol,
      researchContext?.company_profile?.main_business ? `主营：${researchContext.company_profile.main_business}` : null,
      researchContext?.financial_snapshot?.summary_text ? `财务快照：${researchContext.financial_snapshot.summary_text}` : null,
      eventFeed.length ? `近期事件：${eventFeed.slice(0, 3).map((item) => item.title).filter(Boolean).join('；')}` : null,
    ].filter(Boolean).join('。')
    || '公司概况还没生成，点击“刷新研究摘要”补拉公告、财务和LLM解释。';
  const decisionExplanationText = decisionBrief?.decision_explanation
    || [
      profile.current_judgement ? `当前判断：${profile.current_judgement}` : null,
      profile.breakout_reason_summary || [profile.setup_reason, profile.launch_reason, profile.pullback_reason].filter(Boolean).join('；'),
      eventInterpretation?.reasoning ? `事件/资金解释：${eventInterpretation.reasoning}` : null,
    ].filter(Boolean).join('。')
    || '决策解释还没生成，点击“刷新研究摘要”后会把事件催化、趋势回踩和资金确认合成一段人话。';
  const auditFlags = researchContext?.source_audit?.audit_flags || [];
  const contextCoverageStatus = researchContext?.stock_event_coverage?.coverage_status || eventCoverage?.coverage_status;
  const anchorDate = candidate.trade_date || profile.observe_date || profile.discovery_date || profile.entry_signal_date || profile.trade_plan?.signal_date || null;
  const strategyInsight = useMemo<StrategyInsight>(() => {
    const intent = profile.intent_profile || {};
    const entrySignalDate = profile.pullback_confirm_date || profile.entry_signal_date || candidate.entry_signal_date || profile.trade_plan?.signal_date;
    const observeDate = profile.observe_date || profile.discovery_date || candidate.observe_date;
    const entryDate = profile.trade_plan?.entry_date || profile.entry_date || candidate.entry_date;
    const exitSignalDate = profile.trade_plan?.exit_signal_date || profile.exit_signal_date || candidate.exit_signal_date;
    const exitDate = profile.trade_plan?.exit_date || profile.exit_date || candidate.exit_date;

    if (isTrendContinuation) {
      const activeStrength = Number(intent.confirm_active_buy_strength ?? candidate.confirm_active_buy_strength);
      const mainNetRatioPct = Number(intent.confirm_main_net_ratio ?? candidate.confirm_main_net_ratio) * 100;
      const trendScore = Number(intent.trend_score ?? candidate.breakout_score);
      const fundScore = Number(intent.fund_score ?? candidate.stealth_score);
      const repairScore = Number(intent.repair_score ?? candidate.distribution_score);
      const isBuy = profile.entry_allowed !== false;
      return {
        title: isBuy ? '买入确认' : '观察中',
        subtitle: isBuy
          ? `${observeDate || '--'}观察/启动 → ${entrySignalDate || '--'}买入确认`
          : `${observeDate || candidate.trade_date || '--'}进入观察池，等待回踩确认`,
        tone: isBuy ? 'positive' : 'watch',
        sections: [
          {
            title: '信号链路',
            rows: [
              { label: '观察/启动', value: observeDate || '--', desc: '趋势中继先进入观察池，不直接买；后续等待回踩和承接确认。' },
              { label: '买入确认', value: entrySignalDate || '--', desc: '确认日收盘识别，满足买点后计划下一个可交易日执行。' },
              { label: '计划买入', value: entryDate || '待次日', desc: '回测里用次日开盘价；最新信号如果未来数据不足，暂不强行补价格。' },
              { label: '卖出信号/卖出', value: [exitSignalDate, exitDate].filter(Boolean).join(' / ') || '待跟踪', desc: '买入后主要盯累计超大单是否真实撤退。' },
            ],
          },
          {
            title: '买入确认依据',
            rows: [
              {
                label: '主动买入强度',
                value: Number.isFinite(activeStrength) ? `${activeStrength.toFixed(2)}｜${levelText('active_buy_strength', activeStrength)}` : '--',
                desc: '算法：确认日主动买入净额 / 当日成交额 ×100。含义：当天是否有真实主动资金往上买。阈值：>0 达标，>2 强，>5 很强；<=0 不确认买点。',
              },
              {
                label: '主力净流入比例',
                value: Number.isFinite(mainNetRatioPct) ? `${mainNetRatioPct.toFixed(2)}%｜${levelText('net_ratio_pct', mainNetRatioPct)}` : '--',
                desc: '算法：确认日 L2 主力净流入 / 当日成交额。含义：主力资金是否真实留入。阈值：>=0 达标，>3% 强，>6% 很强。',
              },
              {
                label: '趋势分',
                value: Number.isFinite(trendScore) ? `${trendScore.toFixed(2)}｜${levelText('score', trendScore)}` : '--',
                desc: '综合近20日涨幅、相对高点位置、趋势延续状态。不是越高越追涨，主要用于判断是否已经进入趋势中继区间。',
              },
              {
                label: '资金留场分',
                value: Number.isFinite(fundScore) ? `${fundScore.toFixed(2)}｜${levelText('score', fundScore)}` : '--',
                desc: '综合前期超大单/主力净流入和正流入天数。含义：趋势起来后资金有没有明显跑掉。',
              },
              {
                label: '修复/承接分',
                value: Number.isFinite(repairScore) ? `${repairScore.toFixed(2)}｜${levelText('score', repairScore)}` : '--',
                desc: '观察回踩后是否重新承接。分数越高，说明回踩后价格和资金修复越好。',
              },
            ],
          },
          {
            title: '退出逻辑',
            rows: [
              { label: '核心规则', value: '累计超大单', desc: '累计超大单增速下降不是风险；累计值真实下降、并从峰值明显回撤，才是风险。' },
              { label: '当前说明', value: profile.exit_plan_summary || '待跟踪', desc: '卖出信号通常是收盘后识别，下一交易日执行。' },
            ],
          },
        ],
      };
    }

    if (isStableCallback) {
      const setupScore = Number(intent.setup_score ?? profile.stealth_score);
      const launchReturn = Number(intent.launch3_return_pct ?? profile.breakout_score);
      const supportSpread = Number(intent.pullback_support_spread_avg);
      const riskCount = Number(profile.risk_count ?? candidate.risk_count ?? 0);
      const isBuy = profile.entry_allowed !== false;
      return {
        title: isBuy ? '可买入' : '风险拦截',
        subtitle: `${profile.discovery_date || '--'}观察 → ${entrySignalDate || '--'}回调承接确认`,
        tone: isBuy ? 'positive' : 'watch',
        sections: [
          {
            title: '信号链路',
            rows: [
              { label: '纳入观察', value: profile.discovery_date || '--', desc: '先发现资金异动和启动迹象，不追当天暴涨。' },
              { label: '买入确认', value: entrySignalDate || '--', desc: '启动后出现回调承接，确认日收盘识别，计划次日买入。' },
              { label: '计划买入', value: entryDate || '--', desc: '回测里用次日开盘价。' },
              { label: '卖出信号/卖出', value: [exitSignalDate, exitDate].filter(Boolean).join(' / ') || '待跟踪', desc: '买入后盯累计超大单和组合风险。' },
            ],
          },
          {
            title: '买入确认依据',
            rows: [
              {
                label: '前置资金分',
                value: Number.isFinite(setupScore) ? `${setupScore.toFixed(2)}｜${levelText('score', setupScore)}` : '--',
                desc: '综合启动前资金异动、资金持续性和价格结构。含义：前面是否有资金提前进入。',
              },
              {
                label: '启动3日涨幅',
                value: Number.isFinite(launchReturn) ? fmtSignedPct(launchReturn) : '--',
                desc: '算法：启动窗口内股价涨幅。含义：是否真的完成启动，而不是弱反弹。',
              },
              {
                label: '回调承接强度',
                value: Number.isFinite(supportSpread) ? supportSpread.toFixed(4) : '--',
                desc: '算法：回调期盘口支撑与上方压力的相对差。大于0代表支撑强于卖压；越高说明回调承接越好。',
              },
              {
                label: '组合风险数',
                value: `${riskCount} 个`,
                desc: '组合风险包含撤买单异常、盘口/成交背离、弱启动弱承接等。单个风险不一定拦截，多个风险同时出现才更危险。',
              },
            ],
          },
        ],
      };
    }

    return null;
  }, [candidate, isStableCallback, isTrendContinuation, profile]);

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
            strategyInsight={strategyInsight}
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

      <section className="grid gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-violet-500/20 bg-violet-500/10 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Sparkles className="h-4 w-4 text-violet-300" />
              公司概况
              {researchContext?.as_of_cutoff ? <span className="text-[11px] font-normal text-slate-500">截至 {researchContext.as_of_cutoff}</span> : null}
            </div>
            <button
              type="button"
              onClick={handlePrepareContext}
              disabled={preparingContext || loadingEvents}
              className="rounded-lg border border-violet-500/40 bg-violet-500/15 px-2.5 py-1 text-[11px] font-semibold text-violet-100 hover:border-violet-300 disabled:cursor-wait disabled:opacity-60"
            >
              {preparingContext ? '生成中...' : '刷新研究摘要'}
            </button>
          </div>
          <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-100">
            {companyOverviewText}
          </div>
          {prepareMessage ? (
            <div className={`mt-3 rounded-lg border px-2 py-1.5 text-xs ${prepareMessage.includes('失败') || prepareMessage.includes('未生成') ? 'border-amber-500/30 bg-amber-500/10 text-amber-100' : 'border-violet-500/30 bg-violet-500/10 text-violet-100'}`}>
              {prepareMessage}
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <TrendingUp className="h-4 w-4 text-emerald-300" />
              决策解释
            </div>
            <div className="flex flex-wrap gap-1.5">
              <TinyBadge tone={profile.entry_allowed === false ? statusTone('logic_only') : statusTone('confirmed')}>
                {profile.entry_allowed === false ? '观察/拦截' : '可买入'}
              </TinyBadge>
              <TinyBadge>{decisionBrief?.source === 'llm_decision_brief_v1' ? 'LLM摘要' : '规则兜底'}</TinyBadge>
              <TinyBadge tone={contextCoverageStatus === 'covered' ? statusTone('confirmed') : statusTone('unknown')}>{contextCoverageStatus || 'unknown'}</TinyBadge>
            </div>
          </div>
          <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-100">
            {decisionExplanationText}
          </div>
        </div>
      </section>

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
