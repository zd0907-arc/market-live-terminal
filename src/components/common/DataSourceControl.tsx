import React from 'react';
import { Layers, Split, CheckCircle2 } from 'lucide-react';

interface DataSourceControlProps {
    mode: 'realtime' | 'history';
    source: string;
    setSource: (source: string) => void;
    compareMode: boolean;
    setCompareMode: (mode: boolean) => void;
    onVerify?: () => void;
}

const DataSourceControl: React.FC<DataSourceControlProps> = ({ mode, source, setSource, compareMode, setCompareMode, onVerify }) => {
    return (
        <div className="flex items-center gap-3 bg-slate-950/50 p-1.5 rounded-lg border border-slate-800/50">
            <div className="flex items-center gap-2 px-2">
                <Layers className="w-4 h-4 text-slate-500" />
                <span className="text-xs text-slate-400">数据源:</span>
                <select 
                    value={source} 
                    onChange={(e) => setSource(e.target.value)}
                    className="bg-transparent text-sm font-medium text-blue-400 focus:outline-none cursor-pointer"
                >
                    {mode === 'realtime' ? (
                        <>
                            <option value="tencent">🟢 腾讯 (Tencent)</option>
                            <option value="eastmoney">🔵 东财 (Eastmoney)</option>
                        </>
                    ) : (
                        <>
                            <option value="sina">🔴 新浪 (Sina)</option>
                            <option value="local">🟣 本地自算 (Local)</option>
                        </>
                    )}
                </select>
            </div>
            
            <div className="w-px h-4 bg-slate-700"></div>
            
            <button 
                onClick={() => setCompareMode(!compareMode)}
                className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${compareMode ? 'bg-blue-500/20 text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}
                title="开启双屏对比"
            >
                <Split className="w-3.5 h-3.5" />
                <span className="text-xs">对比</span>
            </button>
            
            {mode === 'realtime' && onVerify && (
                <button 
                    onClick={onVerify}
                    className="flex items-center gap-1.5 px-2 py-1 text-slate-500 hover:text-green-400 transition-colors"
                    title="多源实时校验"
                >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                </button>
            )}
        </div>
    );
};

export default DataSourceControl;
