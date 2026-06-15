import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, X } from 'lucide-react';

type AgenticCompanyResearchEmbedProps = {
  symbol?: string | null;
  companyName?: string | null;
};

const escapeHtml = (value: string) => (
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
);

const frameShell = (title: string, body: string) => `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #020617;
      --panel: #0f172a;
      --panel-2: #111827;
      --border: #1e293b;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --soft: #cbd5e1;
      --cyan: #22d3ee;
      --sky: #38bdf8;
      --emerald: #34d399;
      --amber: #fbbf24;
      --rose: #fb7185;
      --violet: #a78bfa;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    .page { padding: 18px; }
    .top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--cyan);
      font-size: 11px;
      letter-spacing: 0;
      font-weight: 700;
    }
    h1, h2, h3, p { margin: 0; }
    h1 { margin-top: 6px; font-size: 22px; line-height: 1.2; }
    h2 { font-size: 14px; }
    .sub { margin-top: 7px; color: var(--muted); font-size: 13px; max-width: 900px; }
    .badge-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(15,23,42,.72);
      color: var(--soft);
      font-size: 11px;
      white-space: nowrap;
    }
    .status {
      min-width: 116px;
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 9px 10px;
      background: #0b1120;
      text-align: right;
      font-size: 11px;
      color: var(--muted);
    }
    .status strong { display: block; color: var(--amber); font-size: 15px; margin-top: 3px; }
    .grid { display: grid; gap: 12px; }
    .grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .section { margin-top: 14px; }
    .panel {
      border: 1px solid var(--border);
      border-radius: 10px;
      background: rgba(15,23,42,.72);
      padding: 13px;
      min-width: 0;
    }
    .panel h2 { color: #f8fafc; margin-bottom: 9px; }
    .metric-value { font-size: 20px; font-weight: 800; line-height: 1.1; }
    .metric-label { color: var(--muted); font-size: 11px; margin-top: 6px; }
    .metric-note { color: var(--muted); font-size: 11px; margin-top: 5px; }
    .good { color: var(--emerald); }
    .warn { color: var(--amber); }
    .hot { color: var(--rose); }
    .cool { color: var(--sky); }
    .muted { color: var(--muted); }
    .bar-list { display: grid; gap: 8px; }
    .bar-row { display: grid; grid-template-columns: 86px minmax(0, 1fr) 44px; gap: 8px; align-items: center; font-size: 12px; }
    .bar-track { height: 8px; background: #1e293b; border-radius: 999px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: inherit; }
    .mini-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .mini-table th, .mini-table td { padding: 7px 6px; border-bottom: 1px solid #1e293b; text-align: left; vertical-align: top; }
    .mini-table th { color: var(--muted); font-weight: 600; }
    .callout {
      border-left: 3px solid var(--cyan);
      padding: 9px 11px;
      background: rgba(8,47,73,.26);
      color: #dbeafe;
      border-radius: 8px;
      font-size: 12px;
    }
    .timeline { display: grid; grid-template-columns: 116px 1fr; gap: 10px; align-items: start; }
    .time-dot { color: var(--cyan); font-weight: 800; font-size: 12px; }
    .time-body { color: var(--soft); font-size: 12px; padding-bottom: 10px; border-bottom: 1px solid #1e293b; }
    .svg-wrap { width: 100%; overflow: hidden; }
    .compact.page {
      padding: 10px 0 2px;
      background: transparent;
    }
    .compact .top {
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(51,65,85,.74);
    }
    .compact .sub { max-width: 760px; }
    .compact .status {
      border: 0;
      background: transparent;
      padding: 0;
      min-width: 72px;
    }
    .compact-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border-bottom: 1px solid rgba(51,65,85,.72);
    }
    .compact-stat {
      min-width: 0;
      padding: 12px 14px 12px 0;
      border-right: 1px solid rgba(51,65,85,.44);
    }
    .compact-stat:last-child { border-right: 0; }
    .compact-split {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 22px;
      padding: 15px 0;
      border-bottom: 1px solid rgba(51,65,85,.72);
    }
    .compact-block { min-width: 0; }
    .compact-block h2 {
      margin: 0 0 10px;
      color: #f8fafc;
      font-size: 13px;
    }
    .compact-note {
      margin-top: 13px;
      padding: 10px 12px;
      border-left: 3px solid var(--cyan);
      background: rgba(8,47,73,.18);
      color: #dbeafe;
      font-size: 12px;
    }
    svg text { font-family: inherit; }
    @media (max-width: 760px) {
      .page { padding: 12px; }
      .compact.page { padding: 8px 0 2px; }
      .top { display: block; }
      .status { margin-top: 12px; text-align: left; }
      .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
      .compact-stats, .compact-split { grid-template-columns: 1fr; }
      .compact-stat { border-right: 0; border-bottom: 1px solid rgba(51,65,85,.44); }
      .compact-stat:last-child { border-bottom: 0; }
      .bar-row { grid-template-columns: 74px minmax(0,1fr) 38px; }
    }
  </style>
</head>
<body>${body}</body>
</html>`;

const compactHtml = (name: string, symbol: string) => frameShell(`${name} 简版研究`, `
  <main class="page compact">
    <header class="top">
      <div>
        <div class="eyebrow">Agentic Research · 样式原型</div>
        <h1>${escapeHtml(name)} <span class="muted">${escapeHtml(symbol.toUpperCase())}</span></h1>
        <p class="sub">这块未来由公司研究 Agent 生成。当前先用实益达做样式占位，重点验证：简版卡能同时容纳文字、图表、估值和股价驱动。</p>
        <div class="badge-row">
          <span class="badge">电子制造服务</span>
          <span class="badge">LED/照明应用</span>
          <span class="badge">小盘题材波动</span>
          <span class="badge">数据待正式研究</span>
        </div>
      </div>
      <div class="status">研究状态<strong>DEMO</strong></div>
    </header>

    <section class="compact-stats">
      <div class="compact-stat">
        <div class="metric-value">2025A</div>
        <div class="metric-label">基线年度</div>
        <div class="metric-note">收入、扣非、现金流由正式 Agent run 填充</div>
      </div>
      <div class="compact-stat">
        <div class="metric-value warn">2026Q1</div>
        <div class="metric-label">变化观察点</div>
        <div class="metric-note">看同比、环比和是否可持续</div>
      </div>
      <div class="compact-stat">
        <div class="metric-value cool">PE</div>
        <div class="metric-label">静态 vs Q1年化</div>
        <div class="metric-note">展示估值重算差异，不直接给买卖建议</div>
      </div>
      <div class="compact-stat">
        <div class="metric-value hot">波动</div>
        <div class="metric-label">股价驱动</div>
        <div class="metric-note">题材、业绩、资金三者拆开看</div>
      </div>
    </section>

    <section class="compact-split">
      <div class="compact-block">
        <h2>业务结构示意</h2>
        <div class="bar-list">
          <div class="bar-row"><span>制造服务</span><div class="bar-track"><div class="bar-fill" style="width:58%;background:var(--sky)"></div></div><b>58</b></div>
          <div class="bar-row"><span>LED应用</span><div class="bar-track"><div class="bar-fill" style="width:24%;background:var(--emerald)"></div></div><b>24</b></div>
          <div class="bar-row"><span>品牌/其他</span><div class="bar-track"><div class="bar-fill" style="width:18%;background:var(--violet)"></div></div><b>18</b></div>
        </div>
        <p class="metric-note">正式版会展示收入占比、毛利贡献和同比变化，不固定业务项数量。</p>
      </div>
      <div class="compact-block">
        <h2>股价驱动示意</h2>
        <div class="bar-list">
          <div class="bar-row"><span>题材资金</span><div class="bar-track"><div class="bar-fill" style="width:72%;background:var(--rose)"></div></div><b>高</b></div>
          <div class="bar-row"><span>业绩变化</span><div class="bar-track"><div class="bar-fill" style="width:48%;background:var(--amber)"></div></div><b>中</b></div>
          <div class="bar-row"><span>估值修复</span><div class="bar-track"><div class="bar-fill" style="width:38%;background:var(--cyan)"></div></div><b>中</b></div>
        </div>
        <p class="metric-note">正式版会把 20/60/120 日走势、主题热度和公告节点合并显示。</p>
      </div>
    </section>

    <section class="compact-note">我现在看它，是因为走势有兴趣；下一步要快速知道：它的业务主线、2025 到 2026Q1 的变化、当前估值重算、股价到底在交易什么。</section>
  </main>
`);

const fullHtml = (name: string, symbol: string) => frameShell(`${name} 完整研究`, `
  <main class="page">
    <header class="top">
      <div>
        <div class="eyebrow">Agentic Research Full Page · 样式原型</div>
        <h1>${escapeHtml(name)} <span class="muted">${escapeHtml(symbol.toUpperCase())}</span> 公司研究页</h1>
        <p class="sub">完整页展示研究 Agent 的可视化产物：业务层级、2025/2026Q1 变化、估值重算、股价驱动、风险反证和证据来源。当前数据为样式占位，不作为正式研究结论。</p>
      </div>
      <div class="status">页面状态<strong>FULL DEMO</strong></div>
    </header>

    <section class="section grid grid-4">
      <div class="panel"><div class="metric-value">7.2亿</div><div class="metric-label">2025A 收入示意</div><div class="metric-note">正式版接年报字段</div></div>
      <div class="panel"><div class="metric-value good">+38%</div><div class="metric-label">2026Q1 收入同比示意</div><div class="metric-note">看增速是否持续</div></div>
      <div class="panel"><div class="metric-value warn">72x</div><div class="metric-label">静态 PE 示意</div><div class="metric-note">按 2025 利润</div></div>
      <div class="panel"><div class="metric-value cool">36x</div><div class="metric-label">Q1年化 PE 示意</div><div class="metric-note">只作重算口径</div></div>
    </section>

    <section class="section grid grid-2">
      <div class="panel">
        <h2>1. 公司做什么：业务层级图</h2>
        <div class="svg-wrap">
          <svg viewBox="0 0 680 260" width="100%" height="260" role="img" aria-label="业务层级示意">
            <rect x="20" y="26" width="160" height="52" rx="8" fill="#082f49" stroke="#0ea5e9"/>
            <text x="100" y="56" text-anchor="middle" fill="#e0f2fe" font-size="14" font-weight="700">实益达</text>
            <path d="M180 52 L260 52" stroke="#475569" stroke-width="2"/>
            <rect x="260" y="18" width="150" height="40" rx="8" fill="#111827" stroke="#334155"/>
            <text x="335" y="43" text-anchor="middle" fill="#cbd5e1" font-size="12">电子制造服务</text>
            <rect x="260" y="78" width="150" height="40" rx="8" fill="#111827" stroke="#334155"/>
            <text x="335" y="103" text-anchor="middle" fill="#cbd5e1" font-size="12">LED/照明应用</text>
            <rect x="260" y="138" width="150" height="40" rx="8" fill="#111827" stroke="#334155"/>
            <text x="335" y="163" text-anchor="middle" fill="#cbd5e1" font-size="12">品牌客户/其他</text>
            <path d="M410 38 L482 38" stroke="#475569" stroke-width="2"/>
            <path d="M410 98 L482 98" stroke="#475569" stroke-width="2"/>
            <path d="M410 158 L482 158" stroke="#475569" stroke-width="2"/>
            <rect x="482" y="18" width="170" height="40" rx="8" fill="#0f172a" stroke="#334155"/>
            <text x="567" y="43" text-anchor="middle" fill="#94a3b8" font-size="12">收入/毛利拆分</text>
            <rect x="482" y="78" width="170" height="40" rx="8" fill="#0f172a" stroke="#334155"/>
            <text x="567" y="103" text-anchor="middle" fill="#94a3b8" font-size="12">订单/客户验证</text>
            <rect x="482" y="138" width="170" height="40" rx="8" fill="#0f172a" stroke="#334155"/>
            <text x="567" y="163" text-anchor="middle" fill="#94a3b8" font-size="12">费用/现金流验证</text>
            <text x="20" y="230" fill="#94a3b8" font-size="12">正式版会由财报 Agent 自动识别业务层级，避免把收入项、利润项和概念项混在一起。</text>
          </svg>
        </div>
      </div>

      <div class="panel">
        <h2>2. 2025 到 2026Q1：变化率优先</h2>
        <table class="mini-table">
          <thead><tr><th>指标</th><th>2025A</th><th>2026Q1</th><th>判断</th></tr></thead>
          <tbody>
            <tr><td>收入</td><td>7.2亿</td><td>2.4亿 / +38%</td><td>示意：先看增长是否来自主业</td></tr>
            <tr><td>扣非</td><td>0.18亿</td><td>0.09亿 / +120%</td><td>示意：弹性强但要看持续性</td></tr>
            <tr><td>CFO</td><td>0.31亿</td><td>-0.05亿</td><td>示意：利润和现金流要分开</td></tr>
            <tr><td>存货</td><td>1.6亿</td><td>1.9亿</td><td>示意：电子制造需盯库存周转</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section grid grid-2">
      <div class="panel">
        <h2>3. 收入/毛利结构</h2>
        <div class="svg-wrap">
          <svg viewBox="0 0 680 250" width="100%" height="250" role="img" aria-label="收入毛利结构示意">
            <text x="18" y="28" fill="#94a3b8" font-size="12">收入占比</text>
            <rect x="90" y="16" width="530" height="22" rx="6" fill="#1e293b"/>
            <rect x="90" y="16" width="307" height="22" rx="6" fill="#38bdf8"/>
            <rect x="397" y="16" width="127" height="22" fill="#34d399"/>
            <rect x="524" y="16" width="96" height="22" rx="6" fill="#a78bfa"/>
            <text x="18" y="76" fill="#94a3b8" font-size="12">毛利贡献</text>
            <rect x="90" y="64" width="530" height="22" rx="6" fill="#1e293b"/>
            <rect x="90" y="64" width="250" height="22" rx="6" fill="#38bdf8"/>
            <rect x="340" y="64" width="180" height="22" fill="#34d399"/>
            <rect x="520" y="64" width="100" height="22" rx="6" fill="#a78bfa"/>
            <g font-size="12" fill="#cbd5e1">
              <circle cx="105" cy="128" r="5" fill="#38bdf8"/><text x="118" y="132">制造服务</text>
              <circle cx="230" cy="128" r="5" fill="#34d399"/><text x="243" y="132">LED/照明应用</text>
              <circle cx="382" cy="128" r="5" fill="#a78bfa"/><text x="395" y="132">品牌/其他</text>
            </g>
            <text x="18" y="192" fill="#94a3b8" font-size="12">正式版：收入和毛利不只放表格，要用结构条先让你看懂“钱和利润是不是同一件事”。</text>
          </svg>
        </div>
      </div>

      <div class="panel">
        <h2>4. 估值重算</h2>
        <div class="grid grid-3">
          <div class="panel"><div class="metric-value warn">72x</div><div class="metric-label">静态 PE</div></div>
          <div class="panel"><div class="metric-value cool">36x</div><div class="metric-label">Q1扣非年化 PE</div></div>
          <div class="panel"><div class="metric-value">中高</div><div class="metric-label">行业位置示意</div></div>
        </div>
        <div class="callout" style="margin-top:12px;">完整页不只给 PE，还要解释：为什么静态 PE 和 Q1 年化 PE 差这么多；Q1 能不能外推；同业中位数在哪里；市场到底在给业绩还是题材估值。</div>
      </div>
    </section>

    <section class="section grid grid-2">
      <div class="panel">
        <h2>5. 股价过去在交易什么</h2>
        <div class="bar-list">
          <div class="bar-row"><span>题材资金</span><div class="bar-track"><div class="bar-fill" style="width:72%;background:var(--rose)"></div></div><b>高</b></div>
          <div class="bar-row"><span>业绩改善</span><div class="bar-track"><div class="bar-fill" style="width:55%;background:var(--amber)"></div></div><b>中</b></div>
          <div class="bar-row"><span>估值重算</span><div class="bar-track"><div class="bar-fill" style="width:42%;background:var(--cyan)"></div></div><b>中</b></div>
          <div class="bar-row"><span>行业景气</span><div class="bar-track"><div class="bar-fill" style="width:36%;background:var(--emerald)"></div></div><b>弱</b></div>
        </div>
      </div>
      <div class="panel">
        <h2>6. 关键事件时间线</h2>
        <div class="timeline"><div class="time-dot">2025A</div><div class="time-body">建立收入、扣非、现金流基线；识别业务和利润主线。</div></div>
        <div class="timeline"><div class="time-dot">2026Q1</div><div class="time-body">检查收入和扣非变化率，判断增长是否来自主业，是否伴随现金流压力。</div></div>
        <div class="timeline"><div class="time-dot">06-11</div><div class="time-body">叠加选股信号、走势、成交和主题热度，判断是否值得打开完整研究。</div></div>
      </div>
    </section>

    <section class="section grid grid-2">
      <div class="panel">
        <h2>7. 现在最该盯</h2>
        <table class="mini-table">
          <tbody>
            <tr><td>Q2扣非</td><td>验证 Q1 增长能否延续</td></tr>
            <tr><td>经营现金流</td><td>验证利润是不是变成现金</td></tr>
            <tr><td>存货周转</td><td>电子制造链容易被库存拖累</td></tr>
            <tr><td>主题热度</td><td>判断短线资金是否仍在交易</td></tr>
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>8. 证据状态</h2>
        <div class="callout">正式版会显示：哪些结论来自 03 财报 Agent、06 股价驱动 Agent、09 财务质量 Agent、07 对账 Agent；哪些字段能入库，哪些只是临时研究判断。</div>
      </div>
    </section>
  </main>
`);

const isDemoTarget = (symbol?: string | null, name?: string | null) => {
  const normalizedSymbol = String(symbol || '').toLowerCase();
  const normalizedName = String(name || '');
  return normalizedSymbol === 'sz002137' || normalizedSymbol === '002137' || normalizedName.includes('实益达');
};

const AgenticCompanyResearchEmbed: React.FC<AgenticCompanyResearchEmbedProps> = ({ symbol, companyName }) => {
  const [fullOpen, setFullOpen] = useState(false);
  const [compactHeight, setCompactHeight] = useState(520);
  const compactFrameRef = useRef<HTMLIFrameElement | null>(null);
  const normalizedSymbol = String(symbol || '').toLowerCase();
  const normalizedName = companyName?.trim() || '';
  const displayName = normalizedSymbol === 'sz002137' && (!normalizedName || normalizedName.toLowerCase() === normalizedSymbol)
    ? '实益达'
    : normalizedName || '实益达';
  const displaySymbol = symbol?.trim() || 'sz002137';
  const compactDoc = useMemo(() => compactHtml(displayName, displaySymbol), [displayName, displaySymbol]);
  const fullDoc = useMemo(() => fullHtml(displayName, displaySymbol), [displayName, displaySymbol]);
  const resizeCompactFrame = useCallback(() => {
    const frame = compactFrameRef.current;
    const doc = frame?.contentDocument;
    const body = doc?.body;
    const root = doc?.documentElement;
    if (!body || !root) return;
    const nextHeight = Math.ceil(Math.max(body.scrollHeight, root.scrollHeight, body.offsetHeight, root.offsetHeight));
    if (Number.isFinite(nextHeight) && nextHeight > 0) {
      setCompactHeight(nextHeight + 2);
    }
  }, []);

  useEffect(() => {
    resizeCompactFrame();
    window.addEventListener('resize', resizeCompactFrame);
    return () => window.removeEventListener('resize', resizeCompactFrame);
  }, [compactDoc, resizeCompactFrame]);

  if (!isDemoTarget(symbol, companyName)) return null;

  return (
    <section className="pt-1">
      <div className="mb-2 flex min-w-0 items-center justify-between gap-2 border-b border-slate-800 pb-2">
        <div className="min-w-0">
          <div className="text-sm font-bold text-white">公司研究摘要</div>
          <div className="mt-0.5 text-[11px] text-slate-500">样式原型：未来由 Agent 研究结果生成 HTML</div>
        </div>
        <button
          type="button"
          onClick={() => setFullOpen(true)}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-cyan-600/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs font-medium text-cyan-100 hover:bg-cyan-500/20"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          打开完整研究
        </button>
      </div>
      <iframe
        ref={compactFrameRef}
        title={`${displayName} 公司研究摘要`}
        sandbox="allow-same-origin"
        srcDoc={compactDoc}
        scrolling="no"
        onLoad={resizeCompactFrame}
        className="block w-full border-0 bg-transparent"
        style={{ height: compactHeight }}
      />

      {fullOpen ? (
        <div className="fixed inset-0 z-[220] bg-slate-950/85 p-3 backdrop-blur-sm md:p-6">
          <div className="mx-auto flex h-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 shadow-2xl">
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-white">{displayName} 完整公司研究</div>
                <div className="text-[11px] text-slate-500">HTML 页面原型 · 后续接 Agent run 产物</div>
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
              title={`${displayName} 完整公司研究`}
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
