import React, { useState } from 'react';
import { Settings } from 'lucide-react';
import ConfigModal from '../common/ConfigModal';

interface ThresholdConfigProps {
    onConfigUpdate: () => void;
}

const ThresholdConfig: React.FC<ThresholdConfigProps> = ({ onConfigUpdate }) => {
    const [isOpen, setIsOpen] = useState(false);

    const handleSave = () => {
        onConfigUpdate();
        // ConfigModal handles the closing via onClose, but here we might want to refresh something
    };

    return (
        <div className="relative">
            <button 
                onClick={() => setIsOpen(!isOpen)}
                className="p-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors flex items-center gap-2"
                title="系统配置"
            >
                <Settings className="w-5 h-5" />
                <span className="text-xs font-medium hidden md:inline">配置</span>
            </button>

            <ConfigModal 
                isOpen={isOpen} 
                onClose={() => setIsOpen(false)} 
                onSave={handleSave} 
            />
        </div>
    );
};

export default ThresholdConfig;
