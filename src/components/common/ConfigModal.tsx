import React, { useState, useEffect } from 'react';
import { Settings, MessageSquare, Cpu, CheckCircle, XCircle, Shield, Save } from 'lucide-react';
import * as StockService from '../../services/stockService';

interface ConfigModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: () => void;
}

const ConfigModal: React.FC<ConfigModalProps> = ({ isOpen, onClose, onSave }) => {
    const [activeTab, setActiveTab] = useState<'sentiment' | 'ai'>('sentiment');

    // Sentiment Config
    const [bullWords, setBullWords] = useState('');
    const [bearWords, setBearWords] = useState('');

    // AI Config
    const [llmModel, setLlmModel] = useState('');
    const [llmBaseUrl, setLlmBaseUrl] = useState('');
    const [llmKeyConfigured, setLlmKeyConfigured] = useState(false);
    const [llmModelSource, setLlmModelSource] = useState<'app_config' | 'env' | string>('env');
    const [isTesting, setIsTesting] = useState(false);
    const [isSavingAi, setIsSavingAi] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean, message: string } | null>(null);

    useEffect(() => {
        if (isOpen) {
            // 加载情绪关键词配置
            StockService.getAppConfig().then(cfg => {
                if (cfg.sentiment_bull_words) setBullWords(cfg.sentiment_bull_words);
                if (cfg.sentiment_bear_words) setBearWords(cfg.sentiment_bear_words);
            });

            // 加载 LLM 脱敏信息
            StockService.getLLMInfo().then(info => {
                setLlmModel(info.model || '未配置');
                setLlmBaseUrl(info.base_url || '未配置');
                setLlmKeyConfigured(info.key_configured || false);
                setLlmModelSource(info.model_source || 'env');
            });
        }
    }, [isOpen]);

    const handleTestConnection = async () => {
        setIsTesting(true);
        setTestResult(null);
        try {
            const res = await StockService.testLLMConnection();
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
        await StockService.updateAppConfig('sentiment_bull_words', bullWords);
        await StockService.updateAppConfig('sentiment_bear_words', bearWords);
        onSave();
        onClose();
    };

    const handleSaveAiModel = async () => {
        setIsSavingAi(true);
        setTestResult(null);
        try {
            await StockService.updateAppConfig('llm_model', llmModel.trim());
            setLlmModelSource('app_config');
            setTestResult({ success: true, message: '模型名称已保存' });
            onSave();
        } catch (e) {
            setTestResult({ success: false, message: '模型名称保存失败' });
        } finally {
            setIsSavingAi(false);
        }
    };

    if (!isOpen) return null;

    return (
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
                            {/* 安全提示 */}
                            <div className="flex items-start gap-2 p-3 bg-slate-800/60 border border-slate-700 rounded-lg">
                                <Shield className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
                                <p className="text-xs text-slate-400 leading-relaxed">
                                    API Key 与 Base URL 仍由服务端环境变量安全管理；前端只允许修改模型名称，保存后立即作为默认模型生效。
                                </p>
                            </div>

                            {/* 可编辑/只读信息卡片 */}
                            <div className="space-y-3">
                                <div>
                                    <label className="block text-xs text-slate-500 mb-1">模型</label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            value={llmModel}
                                            onChange={e => setLlmModel(e.target.value)}
                                            placeholder="例如 gpt-4.1-mini / gemini-2.5-pro"
                                            className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:border-green-500 focus:outline-none"
                                        />
                                        <button
                                            onClick={handleSaveAiModel}
                                            disabled={isSavingAi || !llmModel.trim()}
                                            className={`inline-flex items-center gap-1 rounded px-3 py-2 text-xs transition-colors ${
                                                isSavingAi || !llmModel.trim()
                                                    ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
                                                    : 'bg-green-600 hover:bg-green-500 text-white'
                                            }`}
                                        >
                                            <Save className="w-3.5 h-3.5" />
                                            {isSavingAi ? '保存中...' : '保存'}
                                        </button>
                                    </div>
                                    <div className="mt-1 text-[11px] text-slate-500">
                                        当前来源：{llmModelSource === 'app_config' ? '前端保存配置' : '服务端环境变量'}
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs text-slate-500 mb-1">API Base URL</label>
                                    <div className="w-full bg-slate-800/40 border border-slate-700 rounded px-3 py-2 text-slate-300 text-sm truncate">
                                        {llmBaseUrl}
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs text-slate-500 mb-1">API Key 状态</label>
                                    <div className="flex items-center gap-2 px-3 py-2">
                                        {llmKeyConfigured ? (
                                            <>
                                                <CheckCircle className="w-4 h-4 text-green-400" />
                                                <span className="text-green-400 text-sm">已配置</span>
                                            </>
                                        ) : (
                                            <>
                                                <XCircle className="w-4 h-4 text-red-400" />
                                                <span className="text-red-400 text-sm">未配置</span>
                                            </>
                                        )}
                                    </div>
                                </div>

                                {/* 测试连接按钮 */}
                                <div className="pt-1 flex items-center gap-3">
                                    <button
                                        onClick={handleTestConnection}
                                        disabled={isTesting || !llmKeyConfigured}
                                        className={`px-3 py-1.5 text-xs rounded transition-colors flex items-center gap-2 ${isTesting || !llmKeyConfigured
                                                ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
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
