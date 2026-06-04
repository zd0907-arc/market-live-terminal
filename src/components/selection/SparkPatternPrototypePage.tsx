import React, { useMemo } from 'react';
import { ArrowLeft, BarChart3, Layers3, Target } from 'lucide-react';

import { Metric, SectionCard } from '../common/ResearchCard';
import {
  PatternPayload,
  PatternSectionBlock,
  pctTone,
  fmtPct,
  summarizeItems,
  usePatternPayload,
} from './SparkPatternResearchShared';

const DATA_URL = '/research/spark_top1_pattern_prototype.json';

const SparkPatternPrototypePage: React.FC = () => {
  const { payload, loading, error } = usePatternPayload(DATA_URL);

  const sections = payload?.sections || [];
  const items = sections.flatMap((section) => section.items || []);
  const { avgRunup, avgCloseReturn } = useMemo(() => summarizeItems(items), [items]);

  if (loading) {
    return <div className="min-h-screen bg-[#0a0f1c] p-6 text-slate-300">正在加载星火形态样式版...</div>;
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
            星火形态样式版
          </div>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            Spark Top1 / Top3 Prototype
          </span>
        </div>
      </div>

      <main className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 md:px-6">
        <SectionCard title="样式目标" icon={<BarChart3 className="h-4 w-4 text-sky-300" />}>
          <div className="grid gap-3 md:grid-cols-5">
            <Metric label="Top1 样本" value={`${payload.meta.top1_stock_count} 只`} />
            <Metric label="Top3 样本" value={`${payload.meta.top3_stock_count} 只`} />
            <Metric label="原始信号" value={`${payload.meta.top1_signal_count + payload.meta.top3_signal_count} 次`} />
            <Metric label="平均22日冲高" value={fmtPct(avgRunup)} tone="text-red-200" />
            <Metric label="平均22日收盘" value={fmtPct(avgCloseReturn)} tone={pctTone(avgCloseReturn)} />
          </div>
          <div className="mt-3 text-sm text-slate-300">
            用于确认星火入选股票的独立形态研究页信息密度、图表结构和卡片节奏。
          </div>
          <div className="mt-3 text-xs text-slate-500">同一股票合并；每个信号按买入日前 40 个交易日 + 买入日起 50 个交易日取窗口，并对多次信号取并集。图中统一标出信号日、次日买入日和 22 日硬退出日。</div>
        </SectionCard>

        {sections.map((section) => <PatternSectionBlock key={section.id} section={section} />)}
      </main>
    </div>
  );
};

export default SparkPatternPrototypePage;
