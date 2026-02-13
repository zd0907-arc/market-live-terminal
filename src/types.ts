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
  mainBuyAmount?: number; // 主力买入金额 (元)
  mainSellAmount?: number; // 主力卖出金额 (元)
  superBuyAmount?: number; // 超大单买入金额 (元)
  superSellAmount?: number; // 超大单卖出金额 (元)
  superParticipationRatio?: number; // 超大单参与度 %
  closePrice?: number;    // 收盘价
}

export interface CumulativeCapitalData {
  time: string;           // HH:mm
  cumMainBuy: number;     // 累计主力买入 (元)
  cumMainSell: number;    // 累计主力卖出 (元)
  cumNetInflow: number;   // 累计净流入 (元)
  
  // 超大单数据
  cumSuperNetInflow: number; // 累计超大单净流入
  cumSuperBuy: number;
  cumSuperSell: number;
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
  super_large_ratio?: number;
}

export interface HistoryTrendData {
  time: string; // "YYYY-MM-DD HH:MM:SS"
  net_inflow: number;
  main_buy: number;
  main_sell: number;
  super_net: number;
  super_buy: number;
  super_sell: number;
}

export interface SentimentData {
  symbol: string;
  name: string;
  price: number;
  last_close: number;
  volume: number;
  outer_disk: number; // Active Buy
  inner_disk: number; // Active Sell
  buy_queue_vol: number; // Total Buy 1-5
  sell_queue_vol: number; // Total Sell 1-5
  turnover_rate: number;
  timestamp: string;
}