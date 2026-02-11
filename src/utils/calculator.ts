import { TickData, CapitalRatioData } from '../../types';

/**
 * 核心资金计算逻辑
 * 将逐笔交易数据聚合为分钟级的主力资金分布
 * @param ticks 逐笔数据列表
 * @param mainForceThreshold 主力大单阈值 (默认20万，应从配置读取)
 */
export const calculateCapitalFlow = (
    ticks: TickData[], 
    mainForceThreshold: number = 200000
): CapitalRatioData[] => {
    if (ticks.length === 0) return [];

    // 按分钟聚合 buckets: HH:mm -> { mainBuy, mainSell, total }
    const buckets: { [key: string]: { mainBuy: number, mainSell: number, totalAmount: number } } = {};

    ticks.forEach(t => {
        // time format HH:mm:ss -> key HH:mm
        const key = t.time.substring(0, 5);
        if (!buckets[key]) buckets[key] = { mainBuy: 0, mainSell: 0, totalAmount: 0 };

        buckets[key].totalAmount += t.amount;

        // 核心判定逻辑：金额 >= 阈值
        if (t.amount >= mainForceThreshold) {
            if (t.type === 'buy') buckets[key].mainBuy += t.amount;
            if (t.type === 'sell') buckets[key].mainSell += t.amount;
        }
    });

    // 转换为数组并按时间排序
    const sortedKeys = Object.keys(buckets).sort();
    
    const result: CapitalRatioData[] = sortedKeys.map(timeKey => {
        const b = buckets[timeKey];
        const safeTotal = b.totalAmount || 1; // 避免除以0
        
        const mainBuyRatio = (b.mainBuy / safeTotal) * 100;
        const mainSellRatio = (b.mainSell / safeTotal) * 100;
        const mainParticipationRatio = ((b.mainBuy + b.mainSell) / safeTotal) * 100;

        return {
            time: timeKey,
            mainBuyRatio: parseFloat(mainBuyRatio.toFixed(1)),
            mainSellRatio: parseFloat(mainSellRatio.toFixed(1)),
            mainParticipationRatio: parseFloat(mainParticipationRatio.toFixed(1))
        };
    });

    return result;
};
