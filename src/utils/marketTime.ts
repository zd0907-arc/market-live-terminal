export const isCurrentCnTradingSession = (now: Date = new Date()): boolean => {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const hours = now.getHours();
  const minutes = now.getMinutes();
  const time = hours * 100 + minutes;
  return (time >= 930 && time <= 1130) || (time >= 1300 && time <= 1500);
};
