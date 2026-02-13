import React, { useState, useEffect } from 'react';
import { Settings, Database, MessageSquare, Cpu } from 'lucide-react';
import * as StockService from '../../services/stockService';

interface ConfigModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: () => void;
}

const ConfigModal: React.FC<ConfigModalProps> = ({ isOpen, onClose, onSave }) => {
    const [activeTab, setActiveTab] = useState<'market' | 'sentiment' | 'ai'>('market');
    
    // Market Config
    const [superThreshold, setSuperThreshold] = useState('1000000');
    const [largeThreshold, setLargeThreshold] = useState('200000');
    
    // Sentiment Config
    const [bullWords, setBullWords] = useState('');
    const [bearWords, setBearWords] = useState('');
    
    // AI Config
    const [llmBaseUrl, setLlmBaseUrl] = useState('https://api.openai.com/v1');
    const [llmApiKey, setLlmApiKey] = useState('');
    const [llmModel, setLlmModel] = useState('gpt-3.5-turbo');
    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<{success: boolean, message: string} | null>(null);

    useEffect(() => {
        if(isOpen) {
            StockService.getAppConfig().then(cfg => {
                if(cfg.super_large_threshold) setSuperThreshold(cfg.super_large_threshold);
                if(cfg.large_threshold) setLargeThreshold(cfg.large_threshold);
                
                if(cfg.sentiment_bull_words) setBullWords(cfg.sentiment_bull_words);
                if(cfg.sentiment_bear_words) setBearWords(cfg.sentiment_bear_words);
                
                if(cfg.llm_base_url) setLlmBaseUrl(cfg.llm_base_url);
                if(cfg.llm_api_key) setLlmApiKey(cfg.llm_api_key);
                if(cfg.llm_model) setLlmModel(cfg.llm_model);
            });
        }
    }, [isOpen]);

    const handleTestConnection = async () => {
        setIsTesting(true);
        setTestResult(null);
        try {
            const res = await StockService.testLLMConnection({
                base_url: llmBaseUrl,
                api_key: llmApiKey,
                model: llmModel
            });
            
            if (res.code === 200) {
                setTestResult({ success: true, message: '连接成功' });
            } else {
                setTestResult({ success: false, message: res.message || '连接失败' });
            }
        } catch (e) {
             setTestResult({ success: false, message: '请求失败，请检查后端服务' });
        } finally {
            setIsTesting(false);
        }
    };

    const handleSave = async () => {
        // Market
        await StockService.updateAppConfig('super_large_threshold', superThreshold);
        await StockService.updateAppConfig('large_threshold', largeThreshold);
        
        // Sentiment
        await StockService.updateAppConfig('sentiment_bull_words', bullWords);
        await StockService.updateAppConfig('sentiment_bear_words', bearWords);
        
        // AI
        await StockService.updateAppConfig('llm_base_url', llmBaseUrl);
        await StockService.updateAppConfig('llm_api_key', llmApiKey);
        await StockService.updateAppConfig('llm_model', llmModel);
        
        onSave();
        onClose();
    };

    if (!isOpen) return null;

    return (
        // 使用 absolute 而不是 fixed，这样它会相对于父元素（Header）定位，而不是视口
        // 同时保留 z-[100] 确保覆盖其他元素
        <div className="absolute top-12 right-0 z-[100] w-[500px]">
            <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl flex flex-col animate-in fade-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="p-4 border-b border-slate-700 flex items-center gap-2">
                    <Settings className="w-5 h-5 text-blue-400" />
                    <h3 className="text-lg font-bold text-white">系统配置</h3>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-slate-700">
                    <button 
                        onClick={() => setActiveTab('market')}
                        className={`flex-1 py-3 text-sm font-medium transition-colors border-b-2 ${activeTab === 'market' ? 'border-blue-500 text-blue-400 bg-slate-800/50' : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'}`}
                    >
                        <div className="flex items-center justify-center gap-2">
                            <Database className="w-4 h-4" /> 主力判定
                        </div>
                    </button>
                    <button 
                        onClick={() => setActiveTab('sentiment')}
                        className={`flex-1 py-3 text-sm font-medium transition-colors border-b-2 ${activeTab === 'sentiment' ? 'border-purple-500 text-purple-400 bg-slate-800/50' : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'}`}
                    >
                        <div className="flex items-center justify-center gap-2">
                            <MessageSquare className="w-4 h-4" /> 情绪词库
                        </div>
                    </button>
                    <button 
                        onClick={() => setActiveTab('ai')}
                        className={`flex-1 py-3 text-sm font-medium transition-colors border-b-2 ${activeTab === 'ai' ? 'border-green-500 text-green-400 bg-slate-800/50' : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'}`}
                    >
                        <div className="flex items-center justify-center gap-2">
                            <Cpu className="w-4 h-4" /> AI 设置
                        </div>
                    </button>
                </div>

                {/* Content */}
                <div className="p-6 space-y-4 overflow-y-auto">
                    {activeTab === 'market' && (
                        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                            <div>
                                <label className="block text-xs text-slate-400 mb-1">超大单阈值 (元)</label>
                                <input 
                                    type="number" 
                                    value={superThreshold}
                                    onChange={e => setSuperThreshold(e.target.value)}
                                    className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white font-mono focus:border-blue-500 focus:outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-slate-400 mb-1">大单阈值 (元)</label>
                                <input 
                                    type="number" 
                                    value={largeThreshold}
                                    onChange={e => setLargeThreshold(e.target.value)}
                                    className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white font-mono focus:border-blue-500 focus:outline-none"
                                />
                            </div>
                        </div>
                    )}

                    {activeTab === 'sentiment' && (
                        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                            <div>
                                <label className="block text-xs text-red-400 mb-1">多头关键词 (逗号分隔)</label>
                                <textarea 
                                    value={bullWords}
                                    onChange={e => setBullWords(e.target.value)}
                                    placeholder="涨停, 连板, 龙头..."
                                    className="w-full h-24 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-xs leading-relaxed focus:border-purple-500 focus:outline-none resize-none"
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-green-400 mb-1">空头关键词 (逗号分隔)</label>
                                <textarea 
                                    value={bearWords}
                                    onChange={e => setBearWords(e.target.value)}
                                    placeholder="跌停, 核按钮, 割肉..."
                                    className="w-full h-24 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-xs leading-relaxed focus:border-purple-500 focus:outline-none resize-none"
                                />
                            </div>
                        </div>
                    )}

                    {activeTab === 'ai' && (
                        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                            <div>
                                <label className="block text-xs text-slate-400 mb-1">API Base URL</label>
                                <input 
                                    type="text" 
                                    value={llmBaseUrl}
                                    onChange={e => setLlmBaseUrl(e.target.value)}
                                    placeholder="https://api.openai.com/v1"
                                    className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:border-green-500 focus:outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-slate-400 mb-1">API Key</label>
                                <input 
                                    type="password" 
                                    value={llmApiKey}
                                    onChange={e => setLlmApiKey(e.target.value)}
                                    placeholder="sk-..."
                                    className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:border-green-500 focus:outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-slate-400 mb-1">Model Name</label>
                                <input 
                                    type="text" 
                                    value={llmModel}
                                    onChange={e => setLlmModel(e.target.value)}
                                    placeholder="gpt-3.5-turbo"
                                    className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:border-green-500 focus:outline-none"
                                />
                                <div className="pt-2 flex items-center gap-3">
                                    <button
                                        onClick={handleTestConnection}
                                        disabled={isTesting}
                                        className={`px-3 py-1.5 text-xs rounded transition-colors flex items-center gap-2 ${
                                            isTesting 
                                            ? 'bg-slate-700 text-slate-400 cursor-not-allowed' 
                                            : 'bg-slate-700 hover:bg-slate-600 text-white'
                                        }`}
                                    >
                                        {isTesting ? '测试中...' : '测试连接'}
                                    </button>
                                    
                                    {testResult && (
                                        <span className={`text-xs ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                                            {testResult.message}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-slate-700 flex justify-end gap-3 bg-slate-900/50">
                    <button onClick={onClose} className="px-4 py-2 text-slate-400 hover:text-white transition-colors text-sm">取消</button>
                    <button onClick={handleSave} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors text-sm font-medium">
                        保存配置
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfigModal;
