import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { FundsBattleSignalTuning, IntradayFusionData } from '../../types';
import FundsBattleL1Panel from './FundsBattleL1Panel';
import FundsBattleL2Panel from './FundsBattleL2Panel';
import {
  buildBattleSeries,
  countSignals,
  DEFAULT_FUNDS_BATTLE_TUNING,
  FUNDS_BATTLE_TUNING_LIMITS,
  hasFullOrderEventFactors,
  sanitizeFundsBattleTuning,
} from './fundsBattleUtils';

interface FundsBattleSectionProps {
  data: IntradayFusionData | null;
  isLoading?: boolean;
}

const FUNDS_BATTLE_TUNING_STORAGE_PREFIX = 'funds_battle_tuning_v1:';

function formatThreshold(value: number) {
  return `${(value / 10000).toFixed(0)}万`;
}

function formatRatio(value: number, digits = 3) {
  return value.toFixed(digits);
}

const StatRow: React.FC<{ label: string; value: string; tone?: 'default' | 'warning' }> = ({ label, value, tone = 'default' }) => (
  <div className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/50 px-2 py-1.5 text-xs">
    <span className="text-slate-400">{label}</span>
    <span className={tone === 'warning' ? 'font-semibold text-amber-300' : 'font-semibold text-slate-200'}>{value}</span>
  </div>
);

const HelpBadge: React.FC<{ title: string; body: string }> = ({ title, body }) => (
  <span className="group relative inline-flex items-center">
    <span className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-600 bg-slate-800 text-[10px] font-bold text-slate-300">
      !
    </span>
    <span className="pointer-events-none absolute left-0 top-full z-20 mt-2 hidden w-64 rounded-lg border border-slate-700 bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-300 shadow-xl group-hover:block">
      <span className="mb-1 block font-bold text-white">{title}</span>
      {body}
    </span>
  </span>
);

const SliderControl: React.FC<{
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (next: number) => void;
  display: string;
  helpTitle: string;
  helpBody: string;
}> = ({ label, value, min, max, step, onChange, display, helpTitle, helpBody }) => (
  <label className="block rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
    <div className="mb-1 flex items-center justify-between">
      <span className="inline-flex items-center gap-1 text-xs text-slate-300">
        {label}
        <HelpBadge title={helpTitle} body={helpBody} />
      </span>
      <span className="text-[11px] font-semibold text-sky-300">{display}</span>
    </div>
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full accent-sky-400"
    />
  </label>
);

const NumberControl: React.FC<{
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (next: number) => void;
  helpTitle: string;
  helpBody: string;
}> = ({ label, value, min, max, step, onChange, helpTitle, helpBody }) => (
  <label className="block rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
    <div className="mb-1 flex items-center justify-between">
      <span className="inline-flex items-center gap-1 text-xs text-slate-300">
        {label}
        <HelpBadge title={helpTitle} body={helpBody} />
      </span>
      <span className="text-[11px] text-slate-500">{formatThreshold(value)}</span>
    </div>
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 outline-none focus:border-sky-500"
    />
  </label>
);

export const FundsBattleSection: React.FC<FundsBattleSectionProps> = ({ data, isLoading = false }) => {
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [tuning, setTuning] = useState<FundsBattleSignalTuning>(DEFAULT_FUNDS_BATTLE_TUNING);
  const symbol = data?.symbol || '';

  useEffect(() => {
    if (!symbol || typeof window === 'undefined') {
      setTuning(DEFAULT_FUNDS_BATTLE_TUNING);
      return;
    }
    try {
      const saved = window.localStorage.getItem(`${FUNDS_BATTLE_TUNING_STORAGE_PREFIX}${symbol}`);
      if (!saved) {
        setTuning(DEFAULT_FUNDS_BATTLE_TUNING);
        return;
      }
      const parsed = JSON.parse(saved) as Partial<FundsBattleSignalTuning>;
      setTuning(sanitizeFundsBattleTuning(parsed));
    } catch (error) {
      console.warn('Failed to load funds battle tuning from localStorage', error);
      setTuning(DEFAULT_FUNDS_BATTLE_TUNING);
    }
  }, [symbol]);

  const canUseL2Signals = Boolean(data?.is_l2_finalized && data?.source !== 'history_l1_fallback');

  const l1Result = useMemo(
    () =>
      buildBattleSeries(data?.bars ?? [], 'l1', tuning, {
        enableSignals: canUseL2Signals,
      }),
    [data?.bars, tuning, canUseL2Signals]
  );

  const l2Result = useMemo(
    () =>
      buildBattleSeries(data?.bars ?? [], 'l2', tuning, {
        enableSignals: canUseL2Signals,
      }),
    [data?.bars, tuning, canUseL2Signals]
  );

  const l1SignalCount = useMemo(() => countSignals(l1Result.points), [l1Result.points]);
  const l2SignalCount = useMemo(() => countSignals(l2Result.points), [l2Result.points]);
  const orderEventComplete = hasFullOrderEventFactors(l2Result.points, l2Result.lacksOrderEventFactors);
  const factorStatus = !canUseL2Signals ? '未就绪' : orderEventComplete ? '完整' : '不完整';
  const lacksVolumeForVwap = useMemo(
    () => (data?.bars ?? []).length > 0 && (data?.bars ?? []).every((bar) => !bar.total_volume || Number(bar.total_volume) <= 0),
    [data?.bars]
  );

  const patchTuning = (patch: Partial<FundsBattleSignalTuning>) => {
    setTuning((prev) => {
      const next = sanitizeFundsBattleTuning({ ...prev, ...patch });
      if (symbol && typeof window !== 'undefined') {
        try {
          window.localStorage.setItem(`${FUNDS_BATTLE_TUNING_STORAGE_PREFIX}${symbol}`, JSON.stringify(next));
        } catch (error) {
          console.warn('Failed to persist funds battle tuning to localStorage', error);
        }
      }
      return next;
    });
  };

  const restoreDefaults = () => {
    setTuning(DEFAULT_FUNDS_BATTLE_TUNING);
    if (symbol && typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(`${FUNDS_BATTLE_TUNING_STORAGE_PREFIX}${symbol}`);
      } catch (error) {
        console.warn('Failed to clear funds battle tuning from localStorage', error);
      }
    }
  };

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-slate-800 bg-slate-950/40">
        <button
          type="button"
          onClick={() => setIsAdvancedOpen((prev) => !prev)}
          className="flex w-full items-center justify-between px-3 py-2 text-left"
        >
          <div>
            <div className="text-sm font-semibold text-slate-100">高级设置：资金博弈信号调参</div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              当前股票参数会保存在本地浏览器；切换股票时自动加载各自参数，不请求后端。
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300">
              L1 {l1SignalCount} / L2 {l2SignalCount}
            </span>
            {isAdvancedOpen ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
          </div>
        </button>

        {isAdvancedOpen && (
          <div className="border-t border-slate-800 px-3 pb-3 pt-2">
            <div className="mb-3 grid grid-cols-1 gap-2 lg:grid-cols-3">
              <StatRow label="L1 当前标签数" value={`${l1SignalCount}`} />
              <StatRow label="L2 当前标签数" value={`${l2SignalCount}`} />
              <StatRow
                label="撤单因子状态"
                value={factorStatus}
                tone={factorStatus === '完整' ? 'default' : 'warning'}
              />
            </div>

            {!canUseL2Signals ? (
              <div className="mb-3 rounded border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
                当前模式暂无 finalized L2，调参面板已就绪，但标签只会在盘后/历史双轨模式下正式生效。
              </div>
            ) : !orderEventComplete && (
              <div className="mb-3 rounded border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                撤单因子不完整，当前主要观察差值类信号；`诱空 / 诱多` 可能偏少或不出现。
              </div>
            )}

            {lacksVolumeForVwap && (
              <div className="mb-3 rounded border border-sky-500/20 bg-sky-500/10 px-3 py-2 text-xs text-sky-200">
                当前这批旧 finalized 样本缺少 `total_volume`，VWAP 会退化为收盘价，默认会把“水上/水下”过滤卡得很死。
                若你只是想先把信号调出来看，优先把 <span className="font-semibold">VWAP 偏离阈值调到 0</span>，再视情况把
                <span className="font-semibold"> 吃/出 差值阈值</span> 下调到 `100万` 或更低。
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <NumberControl
                label="吃/出 差值阈值"
                value={tuning.diffThreshold}
                min={FUNDS_BATTLE_TUNING_LIMITS.diffThreshold.min}
                max={FUNDS_BATTLE_TUNING_LIMITS.diffThreshold.max}
                step={FUNDS_BATTLE_TUNING_LIMITS.diffThreshold.step}
                onChange={(next) => patchTuning({ diffThreshold: next })}
                helpTitle="吃 / 出 差值阈值"
                helpBody="控制 L2 净流入与 L1 净流入之间要拉开多大差距才算有隐藏动机。调小它，差值类信号会明显变多；对老样本最值得先调这个。"
              />
              <NumberControl
                label="诱空/诱多 撤单阈值"
                value={tuning.cancelThreshold}
                min={FUNDS_BATTLE_TUNING_LIMITS.cancelThreshold.min}
                max={FUNDS_BATTLE_TUNING_LIMITS.cancelThreshold.max}
                step={FUNDS_BATTLE_TUNING_LIMITS.cancelThreshold.step}
                onChange={(next) => patchTuning({ cancelThreshold: next })}
                helpTitle="诱空 / 诱多 撤单阈值"
                helpBody="控制撤单金额要多大才标记成 诱空/诱多。当前粤桂 2026-03-18 这类旧样本撤单因子并不完整，所以调这个通常不会立刻看到明显变化。"
              />
              <SliderControl
                label="VWAP 偏离阈值"
                value={tuning.vwapDistanceThreshold}
                min={FUNDS_BATTLE_TUNING_LIMITS.vwapDistanceThreshold.min}
                max={FUNDS_BATTLE_TUNING_LIMITS.vwapDistanceThreshold.max}
                step={FUNDS_BATTLE_TUNING_LIMITS.vwapDistanceThreshold.step}
                onChange={(next) => patchTuning({ vwapDistanceThreshold: next })}
                display={formatRatio(tuning.vwapDistanceThreshold, 4)}
                helpTitle="VWAP 偏离阈值"
                helpBody="要求价格必须离 VWAP 多远，才算真正处于‘水上/水下’。调得越大越严格，调到 0 最宽松。像粤桂 2026-03-18 这种 total_volume 缺失的老样本，想先看到信号就优先把它调到 0。"
              />
              <SliderControl
                label="高低位通道阈值"
                value={tuning.volatilityChannelRatio}
                min={FUNDS_BATTLE_TUNING_LIMITS.volatilityChannelRatio.min}
                max={FUNDS_BATTLE_TUNING_LIMITS.volatilityChannelRatio.max}
                step={FUNDS_BATTLE_TUNING_LIMITS.volatilityChannelRatio.step}
                onChange={(next) => patchTuning({ volatilityChannelRatio: next })}
                display={formatRatio(tuning.volatilityChannelRatio, 4)}
                helpTitle="高低位通道阈值"
                helpBody="给 ‘低位/高位’ 再加一层空间过滤，主要影响诱空/诱多。调小它更容易认为当前价格处于极端位置；调大它更保守。"
              />
              <SliderControl
                label="成交量共振阈值"
                value={tuning.volumeResonanceRatio}
                min={FUNDS_BATTLE_TUNING_LIMITS.volumeResonanceRatio.min}
                max={FUNDS_BATTLE_TUNING_LIMITS.volumeResonanceRatio.max}
                step={FUNDS_BATTLE_TUNING_LIMITS.volumeResonanceRatio.step}
                onChange={(next) => patchTuning({ volumeResonanceRatio: next })}
                display={formatRatio(tuning.volumeResonanceRatio, 2)}
                helpTitle="成交量共振阈值"
                helpBody="要求当前 5m 成交额至少达到最近 5 根平均水平的多少倍。调低它，信号更容易出现；调高它，只保留放量时刻。"
              />
            </div>

            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={restoreDefaults}
                className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-slate-500"
              >
                恢复默认
              </button>
              <button
                type="button"
                onClick={() => setIsAdvancedOpen(false)}
                className="rounded border border-sky-600/30 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300 transition hover:bg-sky-500/20"
              >
                收起
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="min-h-[360px]">
        <FundsBattleL1Panel data={data} isLoading={isLoading} tuning={tuning} />
      </div>
      <div className="min-h-[360px]">
        <FundsBattleL2Panel data={data} isLoading={isLoading} tuning={tuning} />
      </div>
    </div>
  );
};

export default FundsBattleSection;
