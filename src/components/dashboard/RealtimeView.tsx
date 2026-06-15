import React from 'react';

import { SearchResult } from '../../types';
import IntradaySingleDayPanel from './IntradaySingleDayPanel';

interface RealtimeViewProps {
  activeStock: SearchResult | null;
  isTradingHours: () => boolean;
  configVersion?: number;
  focusMode?: 'normal' | 'focus';
  previousClose?: number | null;
  quoteDate?: string | null;
}

const RealtimeView: React.FC<RealtimeViewProps> = ({ activeStock, configVersion, focusMode = 'normal', previousClose, quoteDate }) => (
  <IntradaySingleDayPanel
    activeStock={activeStock}
    configVersion={configVersion}
    focusMode={focusMode}
    previousClose={previousClose}
    quoteDate={quoteDate}
    enableRealtime
    showDateControls
    showReturnToday
  />
);

export default RealtimeView;
