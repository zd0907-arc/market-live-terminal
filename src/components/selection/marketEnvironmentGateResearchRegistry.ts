export type MarketEnvironmentGateResearchPageConfig = {
  id: 'market_environment_gate';
  href: string;
  title: string;
  description: string;
  modelLabel: string;
  dataUrl: string;
  enabled: boolean;
};

export const MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE: MarketEnvironmentGateResearchPageConfig = {
  id: 'market_environment_gate',
  href: '/selection-market-environment-gate-research',
  title: '市场环境门控研究页',
  description: '展示市场水位如何影响四个候选来源，以及被拦截候选后续 5/10 日表现。',
  modelLabel: '市场环境覆盖层',
  dataUrl: '/research/market_environment_gate_research_payload.json',
  enabled: true,
};

export const getMarketEnvironmentGateResearchPage = (pathname: string) => (
  pathname.startsWith(MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE.href)
    ? MARKET_ENVIRONMENT_GATE_RESEARCH_PAGE
    : null
);
