import React, { useState, useEffect } from 'react';
import { Settings, MessageSquare, Cpu, CheckCircle, XCircle, Shield } from 'lucide-react';
import * as StockService from '../../services/stockService';
import { clearStoredWriteToken, getStoredWriteToken, setStoredWriteToken } from '../../config';

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

    // AI Config (只读)
    const [llmModel, setLlmModel] = useState('');
    const [llmBaseUrl, setLlmBaseUrl] = useState('');
    const [llmKeyConfigured, setLlmKeyConfigured] = useState(false);
    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean, message: string } | null>(null);
    const [adminWriteToken, setAdminWriteToken] = useState('');
    const [adminTokenSaved, setAdminTokenSaved] = useState(false);
    const [adminTokenMessage, setAdminTokenMessage] = useState('');

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
            });

            const existingToken = getStoredWriteToken();
            setAdminWriteToken(existingToken);
            setAdminTokenSaved(Boolean(existingToken));
            setAdminTokenMessage('');
        }
    }, [isOpen]);

    const saveAdminToken = () => {
        const normalized = adminWriteToken.trim();
        if (!normalized) {
            clearStoredWriteToken();
            setAdminTokenSaved(false);
            setAdminTokenMessage('已清除本会话管理员写令牌');
            return;
        }
        setStoredWriteToken(normalized);
        setAdminTokenSaved(true);
        setAdminTokenMessage('管理员写令牌已保存到当前浏览器会话');
    };

    const clearAdminToken = () => {
        setAdminWriteToken('');
        clearStoredWriteToken();
        setAdminTokenSaved(false);
        setAdminTokenMessage('已清除本会话管理员写令牌');
    };

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
        } catch (e: any) {
            setTestResult({ success: false, message: e?.message || '请求失败，请检查后端服务' });
        } finally {
            setIsTesting(false);
        }
    };

    const handleSave = async () => {
        try {
            // 只保存情绪关键词配置，LLM 配置不再通过前端修改
            await StockService.updateAppConfig('sentiment_bull_words', bullWords);
            await StockService.updateAppConfig('sentiment_bear_words', bearWords);
            onSave();
            onClose();
        } catch (e: any) {
            alert(e?.message || '保存配置失败');
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
                                    AI 配置已由服务端环境变量安全管理，无法通过前端修改。如需更换模型或 Key，请联系管理员在服务器端配置。
                                </p>
                            </div>

                            {/* 只读信息卡片 */}
                            <div className="space-y-3">
                                <div>
                                    <label className="block text-xs text-slate-500 mb-1">模型</label>
                                    <div className="w-full bg-slate-800/40 border border-slate-700 rounded px-3 py-2 text-slate-300 text-sm">
                                        {llmModel}
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

                            <div className="pt-3 border-t border-slate-700 space-y-3">
                                <div className="flex items-start gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                                    <Shield className="w-4 h-4 text-amber-300 mt-0.5 flex-shrink-0" />
                                    <p className="text-xs text-slate-300 leading-relaxed">
                                        生产环境默认只读。若需执行星标、保存配置、手动抓取等写操作，请在受信设备输入管理员写令牌。令牌仅保存在当前浏览器会话，关闭标签页后失效。
                                    </p>
                                </div>
                                <div>
                                    <label className="block text-xs text-slate-500 mb-1">管理员写令牌（仅当前会话）</label>
                                    <input
                                        type="password"
                                        value={adminWriteToken}
                                        onChange={e => setAdminWriteToken(e.target.value)}
                                        placeholder="输入 WRITE_API_TOKEN"
                                        className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:border-amber-400 focus:outline-none"
                                    />
                                </div>
                                <div className="flex items-center gap-3">
                                    <button
                                        onClick={saveAdminToken}
                                        className="px-3 py-1.5 text-xs rounded bg-amber-600 hover:bg-amber-500 text-white transition-colors"
                                    >
                                        保存到会话
                                    </button>
                                    <button
                                        onClick={clearAdminToken}
                                        className="px-3 py-1.5 text-xs rounded bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                                    >
                                        清除
                                    </button>
                                    <span className={`text-xs ${adminTokenSaved ? 'text-green-400' : 'text-slate-500'}`}>
                                        {adminTokenSaved ? '当前会话已持有管理员写令牌' : '当前会话未持有管理员写令牌'}
                                    </span>
                                </div>
                                {adminTokenMessage && (
                                    <p className="text-xs text-slate-400">{adminTokenMessage}</p>
                                )}
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
