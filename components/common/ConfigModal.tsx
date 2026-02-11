import React, { useState, useEffect } from 'react';
import { Settings } from 'lucide-react';
import * as StockService from '../../services/stockService';

interface ConfigModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: () => void;
}

const ConfigModal: React.FC<ConfigModalProps> = ({ isOpen, onClose, onSave }) => {
    const [superThreshold, setSuperThreshold] = useState('1000000');
    const [largeThreshold, setLargeThreshold] = useState('200000');

    useEffect(() => {
        if(isOpen) {
            StockService.getAppConfig().then(cfg => {
                if(cfg.super_large_threshold) setSuperThreshold(cfg.super_large_threshold);
                if(cfg.large_threshold) setLargeThreshold(cfg.large_threshold);
            });
        }
    }, [isOpen]);

    const handleSave = async () => {
        await StockService.updateAppConfig('super_large_threshold', superThreshold);
        await StockService.updateAppConfig('large_threshold', largeThreshold);
        onSave();
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[100]">
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-96 shadow-2xl">
                <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                    <Settings className="w-5 h-5 text-blue-400" />
                    本地主力判定规则
                </h3>
                <div className="space-y-4">
                    <div>
                        <label className="block text-xs text-slate-400 mb-1">超大单阈值 (元)</label>
                        <input 
                            type="number" 
                            value={superThreshold}
                            onChange={e => setSuperThreshold(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white font-mono"
                        />
                    </div>
                    <div>
                        <label className="block text-xs text-slate-400 mb-1">大单阈值 (元)</label>
                        <input 
                            type="number" 
                            value={largeThreshold}
                            onChange={e => setLargeThreshold(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white font-mono"
                        />
                    </div>
                </div>
                <div className="flex justify-end gap-3 mt-6">
                    <button onClick={onClose} className="px-4 py-2 text-slate-400 hover:text-white transition-colors">取消</button>
                    <button onClick={handleSave} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">保存规则</button>
                </div>
            </div>
        </div>
    );
};

export default ConfigModal;
