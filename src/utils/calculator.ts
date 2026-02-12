import { TickData, CapitalRatioData, CumulativeCapitalData } from '@/types';

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

/**
 * 累计主力资金趋势计算
 * @param ticks 逐笔数据列表
 * @param mainForceThreshold 主力大单阈值
 * @param superLargeThreshold 超大单阈值
 */
export const calculateCumulativeCapitalFlow = (
    ticks: TickData[], 
    mainForceThreshold: number = 200000,
    superLargeThreshold: number = 1000000
): CumulativeCapitalData[] => {
    if (ticks.length === 0) return [];

    // 1. 确保按时间排序
    const sortedTicks = [...ticks].sort((a, b) => a.time.localeCompare(b.time));

    // 2. 按分钟聚合增量
    const buckets: { 
        [key: string]: { 
            mainBuy: number, mainSell: number,
            superBuy: number, superSell: number 
        } 
    } = {};
    
    sortedTicks.forEach(t => {
        const key = t.time.substring(0, 5); // HH:mm
        if (!buckets[key]) buckets[key] = { mainBuy: 0, mainSell: 0, superBuy: 0, superSell: 0 };

        // 主力判定 (>20万)
        if (t.amount >= mainForceThreshold) {
            if (t.type === 'buy') buckets[key].mainBuy += t.amount;
            if (t.type === 'sell') buckets[key].mainSell += t.amount;
        }

        // 超大单判定 (>100万)
        if (t.amount >= superLargeThreshold) {
            if (t.type === 'buy') buckets[key].superBuy += t.amount;
            if (t.type === 'sell') buckets[key].superSell += t.amount;
        }
    });

    // 3. 计算累计值
    const sortedKeys = Object.keys(buckets).sort();
    const result: CumulativeCapitalData[] = [];
    
    let runningMainBuy = 0;
    let runningMainSell = 0;
    let runningSuperBuy = 0;
    let runningSuperSell = 0;

    sortedKeys.forEach(timeKey => {
        const b = buckets[timeKey];
        runningMainBuy += b.mainBuy;
        runningMainSell += b.mainSell;
        
        runningSuperBuy += b.superBuy;
        runningSuperSell += b.superSell;

        result.push({
            time: timeKey,
            cumMainBuy: runningMainBuy,
            cumMainSell: runningMainSell,
            cumNetInflow: runningMainBuy - runningMainSell,
            
            cumSuperBuy: runningSuperBuy,
            cumSuperSell: runningSuperSell,
            cumSuperNetInflow: runningSuperBuy - runningSuperSell
        });
    });

    return result;
};
