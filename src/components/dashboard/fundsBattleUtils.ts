import { FundsBattleSignalTuning, IntradayFusionBar } from '../../types';

export type BattleTrackKey = 'l1' | 'l2';

export interface SignalMark {
  label: '吃' | '出' | '诱空' | '诱多';
  color: string;
}

export interface BattlePoint {
  timestamp: string;
  cvd: number;
  oib: number;
  oibReal: number;
  price: number;
  signal?: SignalMark;
  isClipped?: boolean;
}

export const DEFAULT_FUNDS_BATTLE_TUNING: FundsBattleSignalTuning = {
  diffThreshold: 2_000_000,
  cancelThreshold: 2_000_000,
  vwapDistanceThreshold: 0.0015,
  volatilityChannelRatio: 0.005,
  volumeResonanceRatio: 1.0,
};

export const FUNDS_BATTLE_TUNING_LIMITS = {
  diffThreshold: { min: 0, max: 10_000_000, step: 500_000 },
  cancelThreshold: { min: 0, max: 10_000_000, step: 500_000 },
  vwapDistanceThreshold: { min: 0, max: 0.02, step: 0.0005 },
  volatilityChannelRatio: { min: 0, max: 0.03, step: 0.001 },
  volumeResonanceRatio: { min: 0.5, max: 3.0, step: 0.05 },
} as const;

export const DEFAULT_FUNDS_BATTLE_TICKS = ['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00'];

export function formatFundsYAxis(tick: number | string | null | undefined) {
  if (tick === undefined || tick === null) return '';
  if (typeof tick !== 'number') return String(tick);
  if (Math.abs(tick) >= 10000) return `${Math.round(tick / 10000)}w`;
  return `${Math.round(tick)}`;
}

export function gradientOffset(points: BattlePoint[]) {
  if (points.length === 0) return 0;
  const max = Math.max(...points.map((i) => i.cvd));
  const min = Math.min(...points.map((i) => i.cvd));
  if (max <= 0) return 0;
  if (min >= 0) return 1;
  if (max === min) return 0;
  return max / (max - min);
}

function hasL2Payload(bar: IntradayFusionBar) {
  return [
    bar.l2_main_buy,
    bar.l2_main_sell,
    bar.l2_super_buy,
    bar.l2_super_sell,
    bar.l2_net_inflow,
    bar.l2_cvd_delta,
    bar.l2_oib_delta,
  ].some((value) => value !== null && value !== undefined);
}

function rollingAverage(values: number[]) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function safeNumber(value: number, fallback: number) {
  return Number.isFinite(value) ? value : fallback;
}

export function sanitizeFundsBattleTuning(input: Partial<FundsBattleSignalTuning>): FundsBattleSignalTuning {
  return {
    diffThreshold: clamp(
      safeNumber(Number(input.diffThreshold ?? DEFAULT_FUNDS_BATTLE_TUNING.diffThreshold), DEFAULT_FUNDS_BATTLE_TUNING.diffThreshold),
      FUNDS_BATTLE_TUNING_LIMITS.diffThreshold.min,
      FUNDS_BATTLE_TUNING_LIMITS.diffThreshold.max
    ),
    cancelThreshold: clamp(
      safeNumber(Number(input.cancelThreshold ?? DEFAULT_FUNDS_BATTLE_TUNING.cancelThreshold), DEFAULT_FUNDS_BATTLE_TUNING.cancelThreshold),
      FUNDS_BATTLE_TUNING_LIMITS.cancelThreshold.min,
      FUNDS_BATTLE_TUNING_LIMITS.cancelThreshold.max
    ),
    vwapDistanceThreshold: clamp(
      safeNumber(Number(input.vwapDistanceThreshold ?? DEFAULT_FUNDS_BATTLE_TUNING.vwapDistanceThreshold), DEFAULT_FUNDS_BATTLE_TUNING.vwapDistanceThreshold),
      FUNDS_BATTLE_TUNING_LIMITS.vwapDistanceThreshold.min,
      FUNDS_BATTLE_TUNING_LIMITS.vwapDistanceThreshold.max
    ),
    volatilityChannelRatio: clamp(
      safeNumber(Number(input.volatilityChannelRatio ?? DEFAULT_FUNDS_BATTLE_TUNING.volatilityChannelRatio), DEFAULT_FUNDS_BATTLE_TUNING.volatilityChannelRatio),
      FUNDS_BATTLE_TUNING_LIMITS.volatilityChannelRatio.min,
      FUNDS_BATTLE_TUNING_LIMITS.volatilityChannelRatio.max
    ),
    volumeResonanceRatio: clamp(
      safeNumber(Number(input.volumeResonanceRatio ?? DEFAULT_FUNDS_BATTLE_TUNING.volumeResonanceRatio), DEFAULT_FUNDS_BATTLE_TUNING.volumeResonanceRatio),
      FUNDS_BATTLE_TUNING_LIMITS.volumeResonanceRatio.min,
      FUNDS_BATTLE_TUNING_LIMITS.volumeResonanceRatio.max
    ),
  };
}

export function buildBattleSeries(
  bars: IntradayFusionBar[],
  track: BattleTrackKey,
  tuning: FundsBattleSignalTuning = DEFAULT_FUNDS_BATTLE_TUNING,
  options?: {
    enableSignals?: boolean;
  }
): { points: BattlePoint[]; lacksOrderEventFactors: boolean } {
  const rawPoints: BattlePoint[] = [];
  let cumulativeCvd = 0;
  let cumulativeAmount = 0;
  let cumulativeVolume = 0;
  const recentAmounts: number[] = [];
  let lacksOrderEventFactors = true;
  const enableSignals = options?.enableSignals ?? true;

  for (const bar of bars) {
    const hasL2 = hasL2Payload(bar);
    if (track === 'l2' && !hasL2) continue;

    const totalAmount = Number(bar.total_amount ?? 0);
    const totalVolume = Number(bar.total_volume ?? 0);
    const close = Number(bar.close ?? 0);
    cumulativeAmount += totalAmount;
    cumulativeVolume += totalVolume;
    const vwap = cumulativeVolume > 0 ? cumulativeAmount / cumulativeVolume : close;

    recentAmounts.push(totalAmount);
    if (recentAmounts.length > 5) recentAmounts.shift();
    const avgAmount = rollingAverage(recentAmounts);
    const volumeResonance = avgAmount > 0 ? totalAmount >= avgAmount * tuning.volumeResonanceRatio : false;

    const l1Net = Number(bar.l1_net_inflow ?? 0);
    const l2Net =
      bar.l2_net_inflow !== null && bar.l2_net_inflow !== undefined
        ? Number(bar.l2_net_inflow)
        : Number(bar.l2_main_buy ?? 0) +
          Number(bar.l2_super_buy ?? 0) -
          Number(bar.l2_main_sell ?? 0) -
          Number(bar.l2_super_sell ?? 0);

    const cvdDelta = track === 'l2' ? Number(bar.l2_cvd_delta ?? l2Net) : l1Net;
    const oibReal = track === 'l2' ? Number(bar.l2_oib_delta ?? l2Net) : l1Net;
    cumulativeCvd += cvdDelta;

    const belowVwap = close <= vwap * (1 - tuning.vwapDistanceThreshold);
    const aboveVwap = close >= vwap * (1 + tuning.vwapDistanceThreshold);
    const lowZone = close <= vwap * (1 - tuning.volatilityChannelRatio);
    const highZone = close >= vwap * (1 + tuning.volatilityChannelRatio);

    const cancelBuy = Number(bar.cancel_buy_amount ?? 0);
    const cancelSell = Number(bar.cancel_sell_amount ?? 0);
    if (cancelBuy > 0 || cancelSell > 0 || bar.l2_cvd_delta !== null || bar.l2_oib_delta !== null) {
      lacksOrderEventFactors = false;
    }

    let signal: SignalMark | undefined;
    if (enableSignals) {
      if (track === 'l1' && !hasL2) {
        if (l1Net > tuning.diffThreshold && belowVwap && volumeResonance) {
          signal = { label: '吃', color: '#ef4444' };
        } else if (-l1Net > tuning.diffThreshold && aboveVwap && volumeResonance) {
          signal = { label: '出', color: '#22c55e' };
        }
      } else {
        const diffBuy = l2Net - l1Net;
        const diffSell = l1Net - l2Net;
        if (diffBuy > tuning.diffThreshold && belowVwap && volumeResonance) {
          signal = { label: '吃', color: '#ef4444' };
        } else if (cancelSell > tuning.cancelThreshold && (belowVwap || lowZone) && volumeResonance) {
          signal = { label: '诱空', color: '#ef4444' };
        } else if (diffSell > tuning.diffThreshold && aboveVwap && volumeResonance) {
          signal = { label: '出', color: '#22c55e' };
        } else if (cancelBuy > tuning.cancelThreshold && (aboveVwap || highZone) && volumeResonance) {
          signal = { label: '诱多', color: '#22c55e' };
        }
      }
    }

    rawPoints.push({
      timestamp: bar.datetime.slice(11, 16),
      cvd: cumulativeCvd,
      oib: oibReal,
      oibReal,
      price: close,
      signal,
    });
  }

  if (rawPoints.length === 0) {
    return { points: [], lacksOrderEventFactors };
  }

  const absValues = rawPoints.map((point) => Math.abs(point.oibReal));
  const mean = absValues.reduce((sum, value) => sum + value, 0) / absValues.length;
  const limit = mean > 0 ? mean * 3 : 0;

  return {
    points: rawPoints.map((point) => {
      const isClipped = limit > 0 && Math.abs(point.oibReal) > limit;
      return {
        ...point,
        oib: isClipped ? (point.oibReal > 0 ? limit : -limit) : point.oibReal,
        isClipped,
      };
    }),
    lacksOrderEventFactors,
  };
}

export function countSignals(points: BattlePoint[]) {
  return points.reduce((count, point) => count + (point.signal ? 1 : 0), 0);
}

export function hasFullOrderEventFactors(points: BattlePoint[], lacksOrderEventFactors: boolean) {
  return points.length > 0 && !lacksOrderEventFactors;
}
