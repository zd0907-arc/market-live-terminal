const TRADING_SESSIONS = [
  [9 * 60 + 30, 11 * 60 + 30],
  [13 * 60, 15 * 60],
] as const;

export const DEFAULT_INTRADAY_AXIS_TICKS = ['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00'];
export const COMPACT_INTRADAY_AXIS_TICKS = ['09:30', '10:30', '11:30', '13:00', '14:00', '15:00'];

const formatMinuteLabel = (minutes: number) => {
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
};

const timeLabelToMinutes = (time: string) => {
  const match = /^(\d{2}):(\d{2})$/.exec(time);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  return hour * 60 + minute;
};

const parseGranularityMinutes = (granularity?: string | null) => {
  const match = /^(\d+)\s*m$/i.exec(String(granularity || '').trim());
  if (!match) return null;
  const minutes = Number(match[1]);
  return Number.isFinite(minutes) && minutes > 0 ? minutes : null;
};

export const buildIntradaySlots = (stepMinutes: number) => {
  const step = Math.max(1, Math.min(60, Math.round(stepMinutes)));
  const slots: string[] = [];
  TRADING_SESSIONS.forEach(([start, end]) => {
    for (let minute = start; minute <= end; minute += step) {
      slots.push(formatMinuteLabel(minute));
    }
  });
  return slots;
};

export const inferIntradayStepFromTimes = (times: string[], granularity?: string | null) => {
  const parsed = parseGranularityMinutes(granularity);
  if (parsed) return parsed;

  const minutes = times
    .map(timeLabelToMinutes)
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b);
  const deltas = minutes
    .slice(1)
    .map((minute, index) => minute - minutes[index])
    .filter((delta) => delta > 0 && delta <= 60);

  return deltas.length ? Math.max(1, Math.min(60, Math.min(...deltas))) : 5;
};
