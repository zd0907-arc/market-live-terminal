export type ProbeSignalResearchPageId = 'probe_signal_research';

export type ProbeSignalResearchPageConfig = {
  id: ProbeSignalResearchPageId;
  href: string;
  title: string;
  description: string;
  modelLabel: string;
  dataUrl: string;
  enabled: boolean;
  windowRuleOverride?: string;
};

export const PROBE_SIGNAL_RESEARCH_PAGES: ProbeSignalResearchPageConfig[] = [
  {
    id: 'probe_signal_research',
    href: '/selection-probe-signal-research',
    title: '试盘事件研究页',
    description: '展示试盘观察池与 D3 确认池样本，重点看历史同类、后续冲高和先亏风险。',
    modelLabel: '试盘规则策略',
    dataUrl: '/research/probe_signal_research_payload.json',
    enabled: true,
    windowRuleOverride: '每张图按信号日前 45 个交易日 + 信号日后 45 个交易日取窗口；图中显示日K、成交量、主力净流入和超大单净流入。',
  },
];

export const getProbeSignalResearchPage = (pathname: string) => (
  PROBE_SIGNAL_RESEARCH_PAGES.find((item) => pathname.startsWith(item.href)) || null
);
