import React, { useState } from 'react';
import { Settings } from 'lucide-react';
import ConfigModal from '../common/ConfigModal';

interface ThresholdConfigProps {
    onConfigUpdate: () => void;
    onWatchlistChanged?: () => void;
}

const ThresholdConfig: React.FC<ThresholdConfigProps> = ({ onConfigUpdate, onWatchlistChanged }) => {
    const [isOpen, setIsOpen] = useState(false);

    const handleSave = () => {
        onConfigUpdate();
        // ConfigModal handles the closing via onClose, but here we might want to refresh something
    };

    return (
        <div className="relative">
            <button 
                onClick={() => setIsOpen(!isOpen)}
                className="flex h-9 items-center gap-2 rounded-lg bg-slate-800 px-3 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
                title="系统配置"
            >
                <Settings className="h-4 w-4" />
                <span className="text-xs font-medium hidden md:inline">配置</span>
            </button>

            <ConfigModal 
                isOpen={isOpen} 
                onClose={() => setIsOpen(false)} 
                onSave={handleSave} 
                onWatchlistChanged={onWatchlistChanged}
            />
        </div>
    );
};

export default ThresholdConfig;
