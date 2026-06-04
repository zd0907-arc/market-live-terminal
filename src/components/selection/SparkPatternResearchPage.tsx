import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, Target } from 'lucide-react';

import { Metric, SectionCard } from '../common/ResearchCard';
import {
  PatternCard,
  pctTone,
  fmtPct,
  summarizeItems,
  usePatternPayload,
} from './SparkPatternResearchShared';
import { getSparkPatternResearchPage, SPARK_PATTERN_RESEARCH_PAGES } from './sparkPatternResearchRegistry';

const SparkPatternResearchPage: React.FC = () => {
  const page = getSparkPatternResearchPage(typeof window === 'undefined' ? '' : window.location.pathname);
  const [activeSectionId, setActiveSectionId] = useState('');
  const { payload, loading, error } = usePatternPayload(page?.dataUrl || '');

  useEffect(() => {
    if (!payload?.sections?.length) return;
    setActiveSectionId((prev) => (payload.sections.some((section) => section.id === prev) ? prev : payload.sections[0].id));
  }, [payload]);

  const sections = payload?.sections || [];
  const activeSection = sections.find((section) => section.id === activeSectionId) || sections[0] || null;
  const activeItems = activeSection?.items || [];
  const { avgRunup, avgCloseReturn } = useMemo(() => summarizeItems(activeItems), [activeItems]);

  if (!page) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-red-200">未识别的星火形态研究页路由。</div>;
  }

  if (loading) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-slate-300">正在加载{page.title}...</div>;
  }

  if (error || !payload) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-red-200">读取失败：{error || '无数据'}</div>;
  }

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-slate-200">
      <div className="sticky top-0 z-40 border-b border-slate-800 bg-[#0f1623]/95 shadow-md backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-2 px-4 py-3 md:px-6">
          <a href="/selection-research" className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-slate-500">
            <ArrowLeft className="h-3.5 w-3.5" />
            返回选股研究
          </a>
          <div className="flex items-center gap-2 text-base font-bold text-white">
            <Target className="h-5 w-5 text-sky-300" />
            {page.title}
          </div>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            {page.modelLabel}
          </span>
        </div>
        <div className="mx-auto max-w-[1800px] px-4 pb-3 md:px-6">
          <div className="inline-flex max-w-full flex-wrap gap-2 rounded-xl border border-slate-800 bg-slate-950 px-2 py-2">
            {SPARK_PATTERN_RESEARCH_PAGES.filter((item) => item.enabled).map((item) => {
              const active = item.id === page.id;
              return (
                <a
                  key={item.id}
                  href={item.href}
                  className={`rounded-lg px-3 py-2 text-sm transition ${
                    active
                      ? 'bg-sky-500/15 text-sky-100 ring-1 ring-sky-500/40'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`}
                >
                  <div className="font-medium">{item.title.replace('形态研究页', '')}</div>
                  <div className="mt-1 text-[11px] leading-4 text-slate-500">{item.modelLabel}</div>
                </a>
              );
            })}
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        <SectionCard title="页面说明" icon={<BarChart3 className="h-4 w-4 text-sky-300" />}>
          <div className="grid gap-3 md:grid-cols-5">
            <Metric label="当前档位" value={activeSection?.title || '--'} />
            <Metric label="当前合并股票" value={`${activeSection?.stock_count || 0} 只`} />
            <Metric label="当前原始信号" value={`${activeSection?.source_signal_count || 0} 次`} />
            <Metric label="平均22日冲高" value={fmtPct(avgRunup)} tone="text-red-200" />
            <Metric label="平均22日收盘" value={fmtPct(avgCloseReturn)} tone={pctTone(avgCloseReturn)} />
          </div>
          <div className="mt-3 inline-flex rounded-lg border border-slate-800 bg-slate-950/60 p-1">
            {sections.map((section) => {
              const active = section.id === activeSection?.id;
              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSectionId(section.id)}
                  className={`rounded-md px-3 py-2 text-left text-sm transition ${active ? 'bg-sky-500/15 text-sky-100' : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'}`}
                >
                  <div className="font-medium">{section.title}</div>
                  <div className="text-[11px] text-slate-500">{section.stock_count} 只 / {section.source_signal_count} 次</div>
                </button>
              );
            })}
          </div>
          <div className="mt-3 text-sm text-slate-300">{page.description}</div>
          <div className="mt-2 text-xs text-slate-500">{activeSection?.description}</div>
          <div className="mt-3 text-xs text-slate-500">{page.windowRuleOverride || payload.meta.window_rule}</div>
          {payload.meta.source ? <div className="mt-1 text-[11px] text-slate-600">来源：{payload.meta.source}</div> : null}
        </SectionCard>

        {activeSection ? (
          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2">
              <div>
                <div className="text-sm font-semibold text-white">{activeSection.title}</div>
                <div className="mt-1 text-xs text-slate-500">{activeSection.description}</div>
              </div>
              <div className="text-xs text-slate-400">
                合并后 {activeSection.stock_count} 只 · 原始信号 {activeSection.source_signal_count} 次
              </div>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              {activeSection.items.map((item) => <PatternCard key={item.id} item={item} />)}
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
};

export default SparkPatternResearchPage;
