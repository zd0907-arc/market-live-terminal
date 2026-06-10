import React from 'react';

import { SearchResult } from '../../types';
import IntradaySingleDayPanel from './IntradaySingleDayPanel';

interface RealtimeViewProps {
  activeStock: SearchResult | null;
  isTradingHours: () => boolean;
  configVersion?: number;
  focusMode?: 'normal' | 'focus';
}

const RealtimeView: React.FC<RealtimeViewProps> = ({ activeStock, configVersion, focusMode = 'normal' }) => (
  <IntradaySingleDayPanel
    activeStock={activeStock}
    configVersion={configVersion}
    focusMode={focusMode}
    enableRealtime
    showDateControls
    showReturnToday
  />
);

export default RealtimeView;
