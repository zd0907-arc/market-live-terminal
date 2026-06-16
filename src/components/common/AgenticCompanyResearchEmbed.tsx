import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, RefreshCw, X } from 'lucide-react';

import { fetchAgenticCompanyResearch } from '../../services/selectionService';
import { AgenticCompanyResearchArtifact } from '../../types';
import { lockBodyScroll } from '../../utils/bodyScrollLock';

type AgenticCompanyResearchEmbedProps = {
  symbol?: string | null;
  companyName?: string | null;
  onAvailabilityChange?: (available: boolean) => void;
  showUnavailableState?: boolean;
};

const readinessLabel = (artifact: AgenticCompanyResearchArtifact) => {
  const readiness = artifact.manifest?.promotion_readiness || artifact.manifest?.status || '';
  if (readiness === 'ready_after_ledger') return '可晋级研究';
  if (readiness === 'blocked') return '研究阻塞';
  return '候选研究';
};

const readinessClass = (artifact: AgenticCompanyResearchArtifact) => {
  const readiness = artifact.manifest?.promotion_readiness || artifact.manifest?.status || '';
  if (readiness === 'ready_after_ledger') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100';
  if (readiness === 'blocked') return 'border-rose-500/40 bg-rose-500/10 text-rose-100';
  return 'border-amber-500/40 bg-amber-500/10 text-amber-100';
};

const AgenticCompanyResearchEmbed: React.FC<AgenticCompanyResearchEmbedProps> = ({
  symbol,
  companyName,
  onAvailabilityChange,
  showUnavailableState = false,
}) => {
  const [artifact, setArtifact] = useState<AgenticCompanyResearchArtifact | null>(null);
  const [loading, setLoading] = useState(false);
  const [fullOpen, setFullOpen] = useState(false);
  const [compactHeight, setCompactHeight] = useState(520);
  const compactFrameRef = useRef<HTMLIFrameElement | null>(null);
  const normalizedSymbol = String(symbol || '').trim().toLowerCase();

  const displayName = (
    artifact?.manifest?.company_name
    || companyName
    || artifact?.data?.identity?.company_name
    || normalizedSymbol
  );
  const compactDoc = artifact?.compact_html || '';
  const fullDoc = artifact?.full_html || '';
  const title = artifact?.manifest?.compact?.title || `${displayName} 公司研究摘要`;
  const fullTitle = artifact?.manifest?.full?.title || `${displayName} 完整公司研究`;
  const generatedAt = artifact?.manifest?.generated_at || '';
  const asOfDate = artifact?.manifest?.as_of_date || '';
  const dataGaps = artifact?.manifest?.data_gaps || [];

  const resizeCompactFrame = useCallback(() => {
    const frame = compactFrameRef.current;
    const doc = frame?.contentDocument;
    const body = doc?.body;
    const root = doc?.documentElement;
    if (!body || !root) return;
    const nextHeight = Math.ceil(Math.max(body.scrollHeight, root.scrollHeight, body.offsetHeight, root.offsetHeight));
    if (Number.isFinite(nextHeight) && nextHeight > 0) {
      const minHeight = artifact?.manifest?.compact?.height?.min_px || 360;
      const maxHeight = artifact?.manifest?.compact?.height?.max_px || 900;
      setCompactHeight(Math.min(maxHeight, Math.max(minHeight, nextHeight + 2)));
    }
  }, [artifact?.manifest?.compact?.height?.max_px, artifact?.manifest?.compact?.height?.min_px]);

  useEffect(() => {
    if (!normalizedSymbol) {
      setArtifact(null);
      onAvailabilityChange?.(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setArtifact(null);
    setFullOpen(false);
    setCompactHeight(520);
    fetchAgenticCompanyResearch(normalizedSymbol)
      .then((payload) => {
        if (cancelled) return;
        const available = Boolean(payload?.available && payload.compact_html && payload.full_html);
        setCompactHeight(payload?.manifest?.compact?.height?.preferred_px || 520);
        setArtifact(available ? payload : null);
        onAvailabilityChange?.(available);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [normalizedSymbol, onAvailabilityChange]);

  useEffect(() => {
    if (!fullOpen) return;
    return lockBodyScroll();
  }, [fullOpen]);

  useEffect(() => {
    resizeCompactFrame();
    window.addEventListener('resize', resizeCompactFrame);
    return () => window.removeEventListener('resize', resizeCompactFrame);
  }, [compactDoc, resizeCompactFrame]);

  const metaText = useMemo(() => {
    const parts = [
      artifact?.run_id ? `run ${artifact.run_id}` : null,
      asOfDate ? `截至 ${asOfDate}` : null,
      generatedAt ? `生成 ${generatedAt.slice(0, 16)}` : null,
    ].filter(Boolean);
    return parts.join(' · ');
  }, [artifact?.run_id, asOfDate, generatedAt]);

  if (!artifact || !compactDoc || !fullDoc) {
    if (loading) return (
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-500">
        Agentic 公司研究读取中...
      </section>
    );
    if (showUnavailableState) {
      return (
        <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/55 p-4">
          <div className="text-sm font-semibold text-slate-100">暂无 Agentic 公司研究</div>
          <div className="mt-2 text-xs leading-5 text-slate-400">
            当前股票还没有 `research_ui_manifest.json` 对应的 compact/full 页面产物。左侧仍可查看盯盘行情和历史资金图；等 10+1 Agent 研究完成后，这里会自动变成公司研究入口。
          </div>
          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2 text-[11px] text-slate-500">
            需要的产物：`final_report.md`、`close_pack.md`、`ui/compact.html`、`ui/full.html`、`ui/research_ui_manifest.json`、`ui/data.json`
          </div>
        </section>
      );
    }
    return null;
  }

  return (
    <section className="rounded-xl border border-cyan-500/20 bg-slate-900/70 p-3">
      <div className="mb-2 flex min-w-0 items-center justify-between gap-2 border-b border-slate-800 pb-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-bold text-white">公司研究摘要</div>
            <span className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${readinessClass(artifact)}`}>
              {readinessLabel(artifact)}
            </span>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">{metaText || title}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => normalizedSymbol && fetchAgenticCompanyResearch(normalizedSymbol).then((payload) => {
              const available = Boolean(payload?.available && payload.compact_html && payload.full_html);
              setArtifact(available ? payload : artifact);
              onAvailabilityChange?.(available);
            })}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white"
            aria-label="重新读取公司研究"
            title="重新读取公司研究"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setFullOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-600/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs font-medium text-cyan-100 hover:bg-cyan-500/20"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            打开完整研究
          </button>
        </div>
      </div>

      <iframe
        ref={compactFrameRef}
        title={title}
        sandbox="allow-same-origin"
        srcDoc={compactDoc}
        scrolling="no"
        onLoad={resizeCompactFrame}
        className="block w-full border-0 bg-transparent"
        style={{ height: compactHeight }}
      />

      {dataGaps.length > 0 ? (
        <div className="mt-2 text-[11px] leading-5 text-amber-200/80">
          数据缺口：{dataGaps.slice(0, 3).join('；')}
        </div>
      ) : null}

      {fullOpen ? (
        <div className="fixed inset-0 z-[220] bg-slate-950/85 p-3 backdrop-blur-sm md:p-6">
          <div className="mx-auto flex h-full max-w-7xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-950 shadow-2xl">
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-white">{fullTitle}</div>
                <div className="text-[11px] text-slate-500">{metaText || `${displayName} Agentic 公司研究`}</div>
              </div>
              <button
                type="button"
                onClick={() => setFullOpen(false)}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white"
                aria-label="关闭完整研究"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <iframe
              title={fullTitle}
              sandbox=""
              srcDoc={fullDoc}
              className="min-h-0 flex-1 border-0 bg-slate-950"
            />
          </div>
        </div>
      ) : null}
    </section>
  );
};

export default AgenticCompanyResearchEmbed;
