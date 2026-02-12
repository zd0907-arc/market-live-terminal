import React, { useState, useEffect } from 'react';
import { Settings, Save, X } from 'lucide-react';
import * as StockService from '../../services/stockService';

interface ThresholdConfigProps {
    onConfigUpdate: () => void;
}

const ThresholdConfig: React.FC<ThresholdConfigProps> = ({ onConfigUpdate }) => {
    const [isOpen, setIsOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [config, setConfig] = useState({
        large_threshold: '500000',
        super_large_threshold: '1000000'
    });

    useEffect(() => {
        if (isOpen) {
            loadConfig();
        }
    }, [isOpen]);

    const loadConfig = async () => {
        setLoading(true);
        try {
            const data = await StockService.getAppConfig();
            setConfig({
                large_threshold: data.large_threshold || '500000',
                super_large_threshold: data.super_large_threshold || '1000000'
            });
        } catch (e) {
            console.error("Failed to load config", e);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setLoading(true);
        try {
            await StockService.updateAppConfig('large_threshold', config.large_threshold);
            await StockService.updateAppConfig('super_large_threshold', config.super_large_threshold);
            setIsOpen(false);
            onConfigUpdate(); // Trigger refresh in parent
        } catch (e) {
            console.error("Failed to save config", e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="relative">
            <button 
                onClick={() => setIsOpen(!isOpen)}
                className="p-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors"
                title="资金阈值设置"
            >
                <Settings className="w-5 h-5" />
            </button>

            {isOpen && (
                <div className="absolute right-0 top-12 z-50 w-72 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-4 animate-in fade-in zoom-in-95 duration-200">
                    <div className="flex justify-between items-center mb-4 pb-2 border-b border-slate-800">
                        <h4 className="text-sm font-bold text-white flex items-center gap-2">
                            <Settings className="w-4 h-4 text-blue-400" />
                            资金阈值配置
                        </h4>
                        <button onClick={() => setIsOpen(false)} className="text-slate-500 hover:text-white">
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">主力大单阈值 (元)</label>
                            <input 
                                type="number" 
                                value={config.large_threshold}
                                onChange={(e) => setConfig({...config, large_threshold: e.target.value})}
                                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-mono"
                            />
                            <p className="text-[10px] text-slate-600 mt-1">默认: 500,000 (50万)</p>
                        </div>

                        <div>
                            <label className="block text-xs text-slate-400 mb-1">超大单阈值 (元)</label>
                            <input 
                                type="number" 
                                value={config.super_large_threshold}
                                onChange={(e) => setConfig({...config, super_large_threshold: e.target.value})}
                                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-mono"
                            />
                            <p className="text-[10px] text-slate-600 mt-1">默认: 1,000,000 (100万)</p>
                        </div>

                        <button 
                            onClick={handleSave}
                            disabled={loading}
                            className="w-full bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2 rounded flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {loading ? (
                                <span className="animate-spin w-4 h-4 border-2 border-white/20 border-t-white rounded-full"></span>
                            ) : (
                                <>
                                    <Save className="w-4 h-4" />
                                    保存并刷新
                                </>
                            )}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ThresholdConfig;
