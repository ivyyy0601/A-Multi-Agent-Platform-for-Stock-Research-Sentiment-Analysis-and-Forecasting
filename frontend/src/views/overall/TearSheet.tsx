import { useState } from 'react';
import axios from 'axios';
import { redditAPI, xAPI, newsAPI } from '../sentiment/api/adanos';

interface Props {
  symbol: string;
  quote: any;
  profile: any;
  metrics: any;
  onClose: () => void;
  analystName?: string;
}

type Source = 'quote' | 'financials' | 'analyst' | 'peers' | 'sentiment' | 'news';
type Phase  = 'configure' | 'collecting' | 'analyzing' | 'done' | 'error';

const SOURCE_META: { key: Source; icon: string; label: string; desc: string }[] = [
  { key: 'quote',      icon: '💰', label: 'Quote',      desc: 'Live price · Market cap · 52W range' },
  { key: 'financials', icon: '📊', label: 'Financials', desc: 'Revenue · Profit · Balance sheet' },
  { key: 'analyst',    icon: '🎯', label: 'Analyst',    desc: 'Analyst ratings · Price targets' },
  { key: 'peers',      icon: '🔄', label: 'Peers',      desc: 'Peer comparison · Valuation benchmarks' },
  { key: 'sentiment',  icon: '💬', label: 'Sentiment',  desc: 'Reddit · X · Social sentiment' },
  { key: 'news',       icon: '📰', label: 'News',       desc: 'Latest news · Event updates' },
];

function fmt(n: any, dec = 2): string {
  if (n == null) return 'N/A';
  const v = parseFloat(n);
  if (isNaN(v)) return 'N/A';
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(1) + 'T';
  if (abs >= 1e9)  return (v / 1e9).toFixed(1)  + 'B';
  if (abs >= 1e6)  return (v / 1e6).toFixed(1)  + 'M';
  if (abs >= 1e3)  return (v / 1e3).toFixed(1)  + 'K';
  return v.toFixed(dec);
}
function fmtPct(n: any): string {
  if (n == null) return 'N/A';
  const v = parseFloat(n);
  if (isNaN(v)) return 'N/A';
  return (Math.abs(v) < 2 ? (v * 100).toFixed(1) : v.toFixed(1)) + '%';
}

function buildContext(
  symbol: string,
  sources: Source[],
  quote: any,
  profile: any,
  metrics: any,
  income: any[],
  consensus: any,
  peers: any[],
  news: any[],
  sentiment: any,
) {
  const lines: string[] = [];
  lines.push(`=== ${symbol} Quick Research Data ===`);
  lines.push(`Company: ${profile?.company_name ?? profile?.name ?? symbol}`);
  lines.push(`Sector: ${profile?.sector ?? 'N/A'} | Industry: ${profile?.industry ?? 'N/A'}`);
  if (profile?.description) lines.push(`Description: ${profile.description.slice(0, 400)}`);

  if (sources.includes('quote')) {
    lines.push('\n--- Market Data ---');
    lines.push(`Price: $${parseFloat(quote?.price ?? 0).toFixed(2)}`);
    lines.push(`Change: ${parseFloat(quote?.change_percent ?? 0).toFixed(2)}%`);
    lines.push(`Market Cap: ${fmt(quote?.market_cap ?? metrics?.market_cap)}`);
    lines.push(`52W High: $${parseFloat(quote?.year_high ?? 0).toFixed(2)} | 52W Low: $${parseFloat(quote?.year_low ?? 0).toFixed(2)}`);
    lines.push(`Volume: ${fmt(quote?.volume)} | Avg Volume: ${fmt(quote?.avg_volume)}`);
    lines.push(`Beta: ${parseFloat(metrics?.beta ?? 0).toFixed(2)}`);
    lines.push(`P/E: ${parseFloat(metrics?.pe_ratio ?? metrics?.pe)?.toFixed(1) ?? 'N/A'} | Forward P/E: ${parseFloat(metrics?.forward_pe)?.toFixed(1) ?? 'N/A'}`);
    lines.push(`P/S: ${parseFloat(metrics?.ps_ratio ?? metrics?.price_to_sales)?.toFixed(1) ?? 'N/A'} | P/B: ${parseFloat(metrics?.pb_ratio ?? metrics?.price_to_book)?.toFixed(1) ?? 'N/A'}`);
    lines.push(`EV/EBITDA: ${parseFloat(metrics?.ev_to_ebitda)?.toFixed(1) ?? 'N/A'}`);
    lines.push(`ROE: ${fmtPct(metrics?.roe ?? metrics?.return_on_equity)} | Profit Margin: ${fmtPct(metrics?.net_profit_margin ?? metrics?.profit_margins)}`);
    lines.push(`Debt/Equity: ${parseFloat(metrics?.debt_to_equity)?.toFixed(2) ?? 'N/A'}`);
  }

  if (sources.includes('financials') && income.length > 0) {
    lines.push('\n--- Income Statement (Last 3 Years) ---');
    income.slice(0, 3).forEach((r: any) => {
      const period = (r.period_ending ?? r.date ?? r.period ?? '').slice(0, 10);
      lines.push(`${period}: Revenue=${fmt(r.revenue ?? r.total_revenue)}, GrossProfit=${fmt(r.gross_profit)}, EBITDA=${fmt(r.ebitda)}, NetIncome=${fmt(r.net_income)}, EPS=${parseFloat(r.eps_diluted ?? r.eps)?.toFixed(2) ?? 'N/A'}`);
    });
  }

  if (sources.includes('analyst') && consensus) {
    lines.push('\n--- Analyst Consensus ---');
    lines.push(`Rating: ${consensus.recommendation ?? 'N/A'}`);
    lines.push(`Price Target (Mean): $${parseFloat(consensus.price_target_mean ?? consensus.target_mean_price ?? consensus.price_target)?.toFixed(2) ?? 'N/A'}`);
    lines.push(`Range: $${parseFloat(consensus.price_target_low ?? consensus.target_low_price)?.toFixed(2) ?? 'N/A'} - $${parseFloat(consensus.price_target_high ?? consensus.target_high_price)?.toFixed(2) ?? 'N/A'}`);
    const buy  = (parseInt(consensus.strong_buy ?? 0) + parseInt(consensus.buy ?? 0));
    const hold = parseInt(consensus.hold ?? 0);
    const sell = (parseInt(consensus.sell ?? 0) + parseInt(consensus.strong_sell ?? 0));
    lines.push(`Buy: ${buy} | Hold: ${hold} | Sell: ${sell}`);
  }

  if (sources.includes('peers') && peers.length > 0) {
    lines.push('\n--- Peers Comparison ---');
    peers.forEach((p: any) => {
      lines.push(`${p.symbol}${p.symbol === symbol ? ' (THIS)' : ''}: Price=$${parseFloat(p.price)?.toFixed(2) ?? 'N/A'}, MktCap=${fmt(p.market_cap)}, PE=${parseFloat(p.pe_ratio)?.toFixed(1) ?? 'N/A'}, EV/EBITDA=${parseFloat(p.ev_to_ebitda)?.toFixed(1) ?? 'N/A'}, ROE=${fmtPct(p.roe)}, RevGrowth=${fmtPct(p.revenue_growth)}`);
    });
  }

  if (sources.includes('sentiment')) {
    const platforms = [
      { name: 'Reddit', d: sentiment.reddit },
      { name: 'X/Twitter', d: sentiment.x },
      { name: 'News Sentiment', d: sentiment.newsS },
    ].filter(p => p.d && p.d.found !== false);
    if (platforms.length > 0) {
      lines.push('\n--- Social Sentiment (30 days) ---');
      platforms.forEach(({ name, d }) => {
        lines.push(`${name}: Buzz=${d.buzz_score?.toFixed(1) ?? 'N/A'}, Sentiment=${d.sentiment_score?.toFixed(2) ?? 'N/A'}, Trend=${d.trend ?? 'N/A'}, Bullish=${d.bullish_pct ?? 'N/A'}%, Bearish=${d.bearish_pct ?? 'N/A'}%`);
      });
    }
  }

  if (sources.includes('news') && news.length > 0) {
    lines.push('\n--- Recent News Headlines ---');
    news.slice(0, 8).forEach((n: any) => {
      lines.push(`- ${n.title} (${(n.published_at ?? n.published_date ?? '').slice(0, 10)}, ${n.source ?? n.publisher ?? ''})`);
    });
  }

  return lines.join('\n');
}

function renderMarkdown(text: string) {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    if (line.startsWith('### ')) return <h3 key={i} className="ts-ai-h3">{line.slice(4)}</h3>;
    if (line.startsWith('## '))  return <h2 key={i} className="ts-ai-h2">{line.slice(3)}</h2>;
    if (line.startsWith('# '))   return <h1 key={i} className="ts-ai-h1">{line.slice(2)}</h1>;
    if (line.startsWith('- ') || line.startsWith('• ')) {
      return <li key={i} className="ts-ai-li">{renderInline(line.slice(2))}</li>;
    }
    if (line.trim() === '') return <div key={i} style={{ height: 10 }} />;
    return <p key={i} className="ts-ai-p">{renderInline(line)}</p>;
  });
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    return part;
  });
}

export default function TearSheet({ symbol, quote, profile, metrics, onClose, analystName }: Props) {
  const [phase,    setPhase]    = useState<Phase>('configure');
  const [sources,  setSources]  = useState<Source[]>(['quote', 'financials', 'analyst', 'peers', 'sentiment', 'news']);
  const [steps,    setSteps]    = useState<Record<Source, 'pending' | 'loading' | 'done' | 'skipped'>>({
    quote: 'pending', financials: 'pending', analyst: 'pending', peers: 'pending', sentiment: 'pending', news: 'pending',
  });
  const [analysis, setAnalysis] = useState('');
  const [error,    setError]    = useState('');
  const [saved,    setSaved]    = useState(false);
  const [saving,   setSaving]   = useState(false);

  async function saveReport() {
    if (!analysis || saving || saved) return;
    setSaving(true);
    try {
      await fetch('/api/library/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          company: profile?.name ?? profile?.company_name ?? null,
          report_type: 'quick',
          analyst: analystName || null,
          content: analysis,
          sources: JSON.stringify(sources),
        }),
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  function toggleSource(s: Source) {
    setSources(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  }

  function markStep(s: Source, st: 'loading' | 'done' | 'skipped') {
    setSteps(prev => ({ ...prev, [s]: st }));
  }

  async function run() {
    if (sources.length === 0) return;
    setPhase('collecting');
    setError('');

    // reset steps
    const init: Record<Source, 'pending' | 'loading' | 'done' | 'skipped'> = {
      quote: 'pending', financials: 'pending', analyst: 'pending',
      peers: 'pending', sentiment: 'pending', news: 'pending',
    };
    SOURCE_META.forEach(m => { init[m.key] = sources.includes(m.key) ? 'pending' : 'skipped'; });
    setSteps(init);

    let income: any[]    = [];
    let consensus: any   = null;
    let peers: any[]     = [];
    let news: any[]      = [];
    let sentiment: any   = {};

    // Collect each selected source sequentially so checklist animates
    if (sources.includes('quote')) {
      // quote/metrics already passed as props — just mark done
      markStep('quote', 'loading');
      await new Promise(r => setTimeout(r, 300));
      markStep('quote', 'done');
    }

    if (sources.includes('financials')) {
      markStep('financials', 'loading');
      const res = await axios.get(`/api/market/stock/${symbol}/income?period=annual`).catch(() => null);
      income = Array.isArray(res?.data) ? res.data.slice(0, 4) : [];
      markStep('financials', 'done');
    }

    if (sources.includes('analyst')) {
      markStep('analyst', 'loading');
      const res = await axios.get(`/api/market/stock/${symbol}/consensus`).catch(() => null);
      consensus = Array.isArray(res?.data) && res.data[0] ? res.data[0] : null;
      markStep('analyst', 'done');
    }

    if (sources.includes('peers')) {
      markStep('peers', 'loading');
      const res = await axios.get(`/api/market/stock/${symbol}/peers`).catch(() => null);
      peers = Array.isArray(res?.data) ? res.data.slice(0, 6) : [];
      markStep('peers', 'done');
    }

    if (sources.includes('sentiment')) {
      markStep('sentiment', 'loading');
      const [reddit, x, newsS] = await Promise.all([
        redditAPI.stock(symbol, 30).catch(() => null),
        xAPI.stock(symbol, 30).catch(() => null),
        newsAPI.stock(symbol, 30).catch(() => null),
      ]);
      sentiment = { reddit, x, newsS };
      markStep('sentiment', 'done');
    }

    if (sources.includes('news')) {
      markStep('news', 'loading');
      const res = await axios.get(`/api/market/stock/${symbol}/news`).catch(() => null);
      news = Array.isArray(res?.data) ? res.data.slice(0, 8) : [];
      markStep('news', 'done');
    }

    // Build context & call AI
    setPhase('analyzing');
    const context = buildContext(symbol, sources, quote, profile, metrics, income, consensus, peers, news, sentiment);

    try {
      const selectedLabels = SOURCE_META.filter(m => sources.includes(m.key)).map(m => m.label).join(', ');
      const res = await axios.post('/api/ai/chat', {
        messages: [{
          role: 'user',
          content: `Please provide a quick investment research analysis for ${symbol} based on the data sources available (${selectedLabels}). Structure your response with these sections:

1. **Executive Summary** — 3-4 sentence investment thesis
2. **Business Overview** — what the company does, competitive positioning
${sources.includes('financials') ? '3. **Financial Analysis** — revenue trends, margins, profitability\n' : ''}${sources.includes('analyst') ? '4. **Valuation & Analyst View** — is the stock cheap/expensive? Upside/downside to targets\n' : ''}${sources.includes('peers') ? '5. **Peer Comparison** — how does it stack up vs competitors?\n' : ''}${sources.includes('sentiment') ? '6. **Sentiment & Market Pulse** — what social signals suggest\n' : ''}${sources.includes('news') ? '7. **Recent Catalysts** — key news driving the stock\n' : ''}8. **Conclusion** — Bull case, Bear case, overall assessment

Be specific, reference the actual numbers. Write for a professional investment audience.`,
        }],
        context,
      });
      setAnalysis(res.data.content);
      setPhase('done');
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Analysis failed');
      setPhase('error');
    }
  }

  const stepIcon = (s: Source) => {
    const st = steps[s];
    if (st === 'done')    return <span className="ts-step-icon done">✓</span>;
    if (st === 'loading') return <span className="ts-step-icon loading"><span className="ts-mini-spinner" /></span>;
    if (st === 'skipped') return <span className="ts-step-icon skipped">—</span>;
    return <span className="ts-step-icon pending">○</span>;
  };

  return (
    <div className="ts-overlay" onClick={e => { if ((e.target as HTMLElement).classList.contains('ts-overlay')) onClose(); }}>
      <div className="ts-modal" style={{ maxWidth: 860 }}>

        {/* Header */}
        <div className="ts-toolbar no-print">
          <div className="ts-toolbar-left">
            <span className="ts-toolbar-title">⚡ Quick Analysis · {symbol}</span>
            {phase === 'collecting' && <span className="ts-toolbar-loading">📥 Collecting data...</span>}
            {phase === 'analyzing'  && <span className="ts-toolbar-loading">🤖 AI analyzing...</span>}
            {phase === 'done'       && <span className="ts-toolbar-done">✓ Analysis complete</span>}
          </div>
          <div className="ts-toolbar-right">
            {(phase === 'done' || phase === 'error') && (
              <button className="ic-regen-btn" style={{ marginRight: 8 }}
                onClick={() => { setPhase('configure'); setAnalysis(''); setError(''); }}>
                ⚙ Reconfigure
              </button>
            )}
            <button className="ts-btn-close" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="ts-ai-body">

          {/* ── Configure ───────────────────────────────── */}
          {phase === 'configure' && (
            <div className="ic-configure">
              <div className="ic-configure-title">Select Data Sources</div>
              <div className="ic-configure-sub">
                Selected data sources will be fetched in real time and sent to AI for comprehensive analysis. More sources = more comprehensive analysis.
              </div>

              <div className="ic-select-grid">
                {SOURCE_META.map(m => {
                  const on = sources.includes(m.key);
                  return (
                    <div
                      key={m.key}
                      className={`ic-select-card ${on ? 'selected' : ''}`}
                      style={on ? { borderColor: '#f59e0b66', background: '#f59e0b0d' } : {}}
                      onClick={() => toggleSource(m.key)}
                    >
                      <div className="ic-select-card-top">
                        <span className="ic-select-icon">{m.icon}</span>
                        <div className="ic-select-check"
                          style={on ? { background: '#f59e0b', borderColor: '#f59e0b' } : {}}>
                          {on && '✓'}
                        </div>
                      </div>
                      <div className="ic-select-name" style={on ? { color: '#f59e0b' } : {}}>{m.label}</div>
                      <div className="ic-select-desc">{m.desc}</div>
                    </div>
                  );
                })}
              </div>

              <div className="ic-configure-footer">
                <span className="ic-configure-count">
                  {sources.length} source(s) selected
                  {sources.length === 0 && <span style={{ color: '#ff4d4d', marginLeft: 8 }}>Select at least one</span>}
                </span>
                <button
                  className="ic-generate-btn"
                  style={{ background: sources.length === 0 ? '#333' : 'linear-gradient(135deg,#f59e0b,#d97706)' }}
                  disabled={sources.length === 0}
                  onClick={run}
                >
                  ⚡ Start Quick Analysis →
                </button>
              </div>
            </div>
          )}

          {/* ── Collecting / Analyzing ──────────────────── */}
          {(phase === 'collecting' || phase === 'analyzing') && (
            <div className="ts-ai-loading">
              <div className="ts-ai-spinner" />
              <div className="ts-ai-loading-title">
                {phase === 'collecting' ? 'Fetching data...' : '🤖 AI analyzing...'}
              </div>
              <div className="ts-ai-loading-steps">
                {SOURCE_META.map(m => {
                  const st = steps[m.key];
                  if (st === 'skipped') return null;
                  return (
                    <div key={m.key} className={`ts-ai-step ${st === 'done' ? 'ts-step-done' : st === 'loading' ? 'ts-step-active' : 'ts-step-pending'}`}>
                      {stepIcon(m.key)} {m.icon} {m.label}
                    </div>
                  );
                })}
                <div className={`ts-ai-step ${phase === 'analyzing' ? 'ts-step-active' : 'ts-step-pending'}`}>
                  {phase === 'analyzing'
                    ? <><span className="ts-step-icon loading"><span className="ts-mini-spinner" /></span> 🤖 Writing analysis...</>
                    : <><span className="ts-step-icon pending">○</span> 🤖 AI Analysis</>
                  }
                </div>
              </div>
            </div>
          )}

          {/* ── Error ───────────────────────────────────── */}
          {phase === 'error' && (
            <div className="ts-ai-error">
              ❌ {error || 'Analysis failed, please retry'}
            </div>
          )}

          {/* ── Done ────────────────────────────────────── */}
          {phase === 'done' && analysis && (
            <>
            <div className="library-save-bar">
              <span style={{ color: '#888', fontSize: 12 }}>Report generated</span>
              <button
                className="library-save-btn"
                onClick={saveReport}
                disabled={saving || saved}
                style={saved ? { background: '#00e67622', color: '#00e676', borderColor: '#00e67644' } : {}}
              >
                {saved ? '✓ Saved to Library' : saving ? 'Saving...' : '💾 Save to Library'}
              </button>
            </div>
            <div className="ts-ai-report">
              <div className="ts-ai-report-header">
                <div>
                  <div className="ts-ai-report-title">{profile?.company_name ?? profile?.name ?? symbol} ({symbol})</div>
                  <div className="ts-ai-report-sub">
                    {profile?.sector} · {profile?.industry} · Generated {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                    <span style={{ marginLeft: 12, color: '#f59e0b', fontSize: 11 }}>
                      ⚡ Quick Analysis · {SOURCE_META.filter(m => sources.includes(m.key)).map(m => m.icon).join(' ')}
                    </span>
                  </div>
                </div>
                <div className="ts-ai-report-price">
                  ${parseFloat(quote?.price ?? 0).toFixed(2)}
                  <span className={parseFloat(quote?.change_percent ?? 0) >= 0 ? 'ts-pos' : 'ts-neg'}>
                    {' '}{parseFloat(quote?.change_percent ?? 0) >= 0 ? '+' : ''}{parseFloat(quote?.change_percent ?? 0).toFixed(2)}%
                  </span>
                </div>
              </div>
              <div className="ts-ai-content">
                {renderMarkdown(analysis)}
              </div>
            </div>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
