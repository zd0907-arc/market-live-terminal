export interface StockBase {
  code: string;      // e.g., "600519"
  symbol: string;    // e.g., "sh600519"
  name: string;      // e.g., "贵州茅台"
}

export interface RealTimeQuote extends StockBase {
  price: number;
  lastClose: number;
  open: number;
  high: number;
  low: number;
  volume: number;    // 成交量（股）
  amount: number;    // 成交额（元）
  time: string;
  date: string;
  // 买卖五档
  bids: { price: number; volume: number }[];
  asks: { price: number; volume: number }[];
}

export interface TickData {
  time: string;      // HH:mm:ss
  price: number;     // 成交价
  volume: number;    // 成交量（手）
  amount: number;    // 成交额（元）
  type: 'buy' | 'sell' | 'neutral'; // 主卖/主买/中性
  color: string;     // UI辅助颜色
}

export interface SearchResult {
  name: string;
  code: string;
  symbol: string; // 完整带前缀代码
  market: string; // sh or sz
}

export interface CapitalFlowTrend {
  time: string;           // HH:mm
  mainNetInflow: number;  // 主力净流入 (大单+超大单)
  superNetInflow: number; // 超大单净流入
  mainCumInflow: number;  // 主力累计
  superCumInflow: number; // 超大单累计
}

export interface CapitalRatioData {
  time: string;           // HH:mm
  mainBuyRatio: number;   // 主力买入占比 %
  mainSellRatio: number;  // 主力卖出占比 %
  mainParticipationRatio: number; // 主力参与度 (买+卖)/总 %
}

// 新增：历史分析数据结构
export interface HistoryAnalysisData {
  date: string;
  close: number;
  pct_change: number;
  total_amount: number;
  main_buy_amount: number;
  main_sell_amount: number;
  net_inflow: number;
  // 以下为前端计算字段
  buyRatio?: number;
  sellRatio?: number;
  activityRatio?: number;
}