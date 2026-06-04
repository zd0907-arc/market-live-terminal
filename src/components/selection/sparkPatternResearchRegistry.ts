export type SparkPatternResearchPageId =
  | 'spark_1_0'
  | 'spark_v2_guarded'
  | 'spark_v2_aggressive';

export type SparkPatternResearchPageConfig = {
  id: SparkPatternResearchPageId;
  href: string;
  title: string;
  description: string;
  modelLabel: string;
  dataUrl: string;
  enabled: boolean;
  windowRuleOverride?: string;
};

export const SPARK_PATTERN_RESEARCH_PAGES: SparkPatternResearchPageConfig[] = [
  {
    id: 'spark_1_0',
    href: '/selection-spark-pattern-research/1-0',
    title: '星火 1.0 形态研究页',
    description: '展示星火 1.0 历史选中股票的完整形态、信号与 22 日窗口表现',
    modelLabel: '星火机会模型 1.0',
    dataUrl: '/research/spark_top1_pattern_prototype.json',
    enabled: true,
    windowRuleOverride: '同一股票合并；每个信号按买入日前 40 个交易日 + 买入日起 50 个交易日取窗口，并对多次信号取并集。图中统一标出信号日、次日买入日和 22 日硬退出日。',
  },
  {
    id: 'spark_v2_guarded',
    href: '/selection-spark-pattern-research/v2-guarded',
    title: '星火 v2 稳健型形态研究页',
    description: '展示尽量少踩坑、优先后续能稳定冲高的那套模型',
    modelLabel: '星火稳健版',
    dataUrl: '/research/spark_v2_guarded_pattern_research.json',
    enabled: true,
    windowRuleOverride: '同一股票合并；每个信号按买入日前 40 个交易日 + 买入日起 50 个交易日取窗口，并对多次信号取并集。图中统一标出信号日、次日买入日和 22 日硬退出日。',
  },
  {
    id: 'spark_v2_aggressive',
    href: '/selection-spark-pattern-research/v2-aggressive',
    title: '星火 v2 进攻型形态研究页',
    description: '展示优先寻找后续冲得更高的强势票的那套模型',
    modelLabel: '星火进攻版',
    dataUrl: '/research/spark_v2_aggressive_pattern_research.json',
    enabled: true,
    windowRuleOverride: '同一股票合并；每个信号按买入日前 40 个交易日 + 买入日起 50 个交易日取窗口，并对多次信号取并集。图中统一标出信号日、次日买入日和 22 日硬退出日。',
  },
];

export const getSparkPatternResearchPage = (pathname: string) => (
  SPARK_PATTERN_RESEARCH_PAGES.find((item) => pathname.startsWith(item.href)) || null
);
