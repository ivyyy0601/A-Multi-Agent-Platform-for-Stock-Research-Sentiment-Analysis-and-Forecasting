import { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import { redditAPI, xAPI, newsAPI } from '../sentiment/api/adanos';

// ── Markdown renderer ─────────────────────────────────────────────────
function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('*')  && part.endsWith('*'))  return <em key={i}>{part.slice(1, -1)}</em>;
    if (part.startsWith('`')  && part.endsWith('`'))  return <code key={i} className="ai-inline-code">{part.slice(1, -1)}</code>;
    return part;
  });
}

function parseTable(lines: string[]): React.ReactNode {
  const rows = lines.map(l => l.split('|').map(c => c.trim()).filter(Boolean));
  const [head, , ...body] = rows;
  return (
    <div className="ai-table-wrap">
      <table className="ai-table">
        <thead>
          <tr>{head?.map((c, i) => <th key={i}>{renderInline(c)}</th>)}</tr>
        </thead>
        <tbody>
          {body.map((row, i) => (
            <tr key={i}>{row.map((c, j) => <td key={j}>{renderInline(c)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split('\n');
  const result: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Table block
    if (line.trim().startsWith('|') && lines[i + 1]?.trim().startsWith('|')) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      result.push(<div key={i}>{parseTable(tableLines)}</div>);
      continue;
    }

    // HR
    if (/^---+$/.test(line.trim())) {
      result.push(<hr key={i} className="ai-hr" />);
      i++; continue;
    }

    // Headers
    if (line.startsWith('### ')) { result.push(<div key={i} className="ai-md-h3">{renderInline(line.slice(4))}</div>); i++; continue; }
    if (line.startsWith('## '))  { result.push(<div key={i} className="ai-md-h2">{renderInline(line.slice(3))}</div>); i++; continue; }
    if (line.startsWith('# '))   { result.push(<div key={i} className="ai-md-h1">{renderInline(line.slice(2))}</div>); i++; continue; }

    // Bullet list
    if (line.startsWith('- ') || line.startsWith('• ')) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('• '))) {
        items.push(<li key={i}>{renderInline(lines[i].slice(2))}</li>);
        i++;
      }
      result.push(<ul key={i} className="ai-md-ul">{items}</ul>);
      continue;
    }

    // Arrow list (→)
    if (line.startsWith('→ ')) {
      result.push(<div key={i} className="ai-md-arrow">{renderInline(line.slice(2))}</div>);
      i++; continue;
    }

    // Empty line
    if (line.trim() === '') { result.push(<div key={i} className="ai-md-gap" />); i++; continue; }

    // Paragraph
    result.push(<p key={i} className="ai-md-p">{renderInline(line)}</p>);
    i++;
  }

  return <>{result}</>;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  attachedFiles?: UploadedFile[];
}

interface UploadedFile {
  id: string;
  name: string;
  type: string;
  data: string;   // base64
  preview?: string;
  size: number;
}

interface DataSource {
  id: string;
  label: string;
  icon: string;
  fetch: () => Promise<string>;
}

interface Props {
  tab: string;
  symbol: string;
  chartCapture?: React.MutableRefObject<(() => Promise<string>) | null>;
}

// ── helpers ──────────────────────────────────────────────────────────
function fmt(n: any): string {
  if (n == null) return 'N/A';
  const v = parseFloat(n);
  if (isNaN(v)) return 'N/A';
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(1) + 'T';
  if (abs >= 1e9)  return (v / 1e9).toFixed(1)  + 'B';
  if (abs >= 1e6)  return (v / 1e6).toFixed(1)  + 'M';
  if (abs >= 1e3)  return (v / 1e3).toFixed(1)  + 'K';
  return v.toFixed(2);
}
function fmtPct(n: any): string {
  if (n == null) return 'N/A';
  const v = parseFloat(n);
  if (isNaN(v)) return 'N/A';
  return (Math.abs(v) < 2 ? (v * 100).toFixed(1) : v.toFixed(1)) + '%';
}

function buildDataSources(tab: string, symbol: string): DataSource[] {
  if (tab === 'fundamentals') {
    return [
      {
        id: 'quote', label: 'Quote', icon: '💰',
        fetch: async () => {
          const r = await axios.get(`/api/market/stock/${symbol}/quote`).catch(() => null);
          const q = Array.isArray(r?.data) ? r.data[0] : r?.data;
          if (!q) return '';
          return `[Quote] ${symbol}: Price=$${parseFloat(q.price ?? 0).toFixed(2)}, Change=${parseFloat(q.change_percent ?? 0).toFixed(2)}%, MarketCap=${fmt(q.market_cap)}, 52W=$${q.year_low}–$${q.year_high}, Beta=${q.beta}`;
        },
      },
      {
        id: 'financials', label: 'Financials', icon: '📊',
        fetch: async () => {
          const [inc, bal] = await Promise.all([
            axios.get(`/api/market/stock/${symbol}/income?period=annual`).catch(() => null),
            axios.get(`/api/market/stock/${symbol}/balance?period=annual`).catch(() => null),
          ]);
          const income  = Array.isArray(inc?.data) ? inc.data.slice(0, 3) : [];
          const balance = Array.isArray(bal?.data) ? bal.data[0] : null;
          const lines = ['[Financials]'];
          income.forEach((r: any) => {
            lines.push(`${(r.period_ending ?? r.date ?? '').slice(0, 7)}: Rev=${fmt(r.revenue ?? r.total_revenue)}, GrossProfit=${fmt(r.gross_profit)}, EBITDA=${fmt(r.ebitda)}, NetIncome=${fmt(r.net_income)}, EPS=${parseFloat(r.eps_diluted ?? r.eps)?.toFixed(2) ?? 'N/A'}`);
          });
          if (balance) lines.push(`Balance: TotalAssets=${fmt(balance.total_assets)}, TotalDebt=${fmt(balance.total_debt)}, Cash=${fmt(balance.cash_and_equivalents)}`);
          return lines.join('\n');
        },
      },
      {
        id: 'metrics', label: 'Valuation', icon: '📐',
        fetch: async () => {
          const r = await axios.get(`/api/market/stock/${symbol}/metrics`).catch(() => null);
          const m = Array.isArray(r?.data) ? r.data[0] : r?.data;
          if (!m) return '';
          return `[Valuation] PE=${parseFloat(m.pe_ratio ?? m.pe)?.toFixed(1)??'N/A'}, FwdPE=${parseFloat(m.forward_pe)?.toFixed(1)??'N/A'}, PS=${parseFloat(m.ps_ratio ?? m.price_to_sales)?.toFixed(1)??'N/A'}, PB=${parseFloat(m.pb_ratio ?? m.price_to_book)?.toFixed(1)??'N/A'}, EV/EBITDA=${parseFloat(m.ev_to_ebitda)?.toFixed(1)??'N/A'}, ROE=${fmtPct(m.roe ?? m.return_on_equity)}, ROA=${fmtPct(m.roa ?? m.return_on_assets)}, ProfitMargin=${fmtPct(m.net_profit_margin ?? m.profit_margins)}, D/E=${parseFloat(m.debt_to_equity)?.toFixed(2)??'N/A'}`;
        },
      },
      {
        id: 'analyst', label: 'Analyst', icon: '🎯',
        fetch: async () => {
          const r = await axios.get(`/api/market/stock/${symbol}/consensus`).catch(() => null);
          const c = Array.isArray(r?.data) && r.data[0] ? r.data[0] : null;
          if (!c) return '[Analyst] No data';
          const buy  = parseInt(c.strong_buy ?? 0) + parseInt(c.buy ?? 0);
          const hold = parseInt(c.hold ?? 0);
          const sell = parseInt(c.sell ?? 0) + parseInt(c.strong_sell ?? 0);
          return `[Analyst] Rating=${c.recommendation}, Target=$${parseFloat(c.price_target_mean ?? c.target_mean_price ?? c.price_target)?.toFixed(2)}, Range=$${parseFloat(c.price_target_low ?? c.target_low_price)?.toFixed(2)}–$${parseFloat(c.price_target_high ?? c.target_high_price)?.toFixed(2)}, Buy=${buy}, Hold=${hold}, Sell=${sell}`;
        },
      },
      {
        id: 'peers', label: 'Peers', icon: '🔄',
        fetch: async () => {
          const r = await axios.get(`/api/market/stock/${symbol}/peers`).catch(() => null);
          const peers = Array.isArray(r?.data) ? r.data.slice(0, 6) : [];
          if (!peers.length) return '[Peers] No data';
          return '[Peers]\n' + peers.map((p: any) =>
            `${p.symbol}${p.symbol === symbol ? '(THIS)' : ''}: Price=$${parseFloat(p.price)?.toFixed(2)}, MktCap=${fmt(p.market_cap)}, PE=${parseFloat(p.pe_ratio)?.toFixed(1)??'N/A'}, FwdPE=${parseFloat(p.forward_pe)?.toFixed(1)??'N/A'}, ROE=${fmtPct(p.roe)}, RevGrowth=${fmtPct(p.revenue_growth)}`
          ).join('\n');
        },
      },
      {
        id: 'sentiment', label: 'Sentiment', icon: '💬',
        fetch: async () => {
          const [reddit, x, news] = await Promise.all([
            redditAPI.stock(symbol, 30).catch(() => null),
            xAPI.stock(symbol, 30).catch(() => null),
            newsAPI.stock(symbol, 30).catch(() => null),
          ]);
          const lines = ['[Social Sentiment 30d]'];
          if (reddit && reddit.found !== false) lines.push(`Reddit: buzz=${reddit.buzz_score?.toFixed(1)}, sentiment=${reddit.sentiment_score?.toFixed(2)}, trend=${reddit.trend}, bullish=${reddit.bullish_pct}%, bearish=${reddit.bearish_pct}%`);
          if (x && x.found !== false)      lines.push(`X: buzz=${x.buzz_score?.toFixed(1)}, sentiment=${x.sentiment_score?.toFixed(2)}, trend=${x.trend}`);
          if (news && news.found !== false) lines.push(`News: buzz=${news.buzz_score?.toFixed(1)}, sentiment=${news.sentiment_score?.toFixed(2)}, trend=${news.trend}`);
          return lines.join('\n');
        },
      },
      {
        id: 'news', label: 'News', icon: '📰',
        fetch: async () => {
          const r = await axios.get(`/api/market/stock/${symbol}/news`).catch(() => null);
          const news = Array.isArray(r?.data) ? r.data.slice(0, 6) : [];
          if (!news.length) return '[News] No recent news';
          return '[Recent News]\n' + news.map((n: any) =>
            `- ${n.title} (${(n.published_at ?? n.published_date ?? '').slice(0, 10)}, ${n.source ?? n.publisher ?? ''})`
          ).join('\n');
        },
      },
    ];
  }

  if (tab === 'charting') return [
    {
      id: 'quote', label: 'Quote', icon: '💰',
      fetch: async () => {
        const r = await axios.get(`/api/market/stock/${symbol}/quote`).catch(() => null);
        const q = Array.isArray(r?.data) ? r.data[0] : r?.data;
        if (!q) return '';
        return `[Quote] ${symbol}: $${parseFloat(q.price ?? 0).toFixed(2)}, ${parseFloat(q.change_percent ?? 0).toFixed(2)}%`;
      },
    },
  ];

  if (tab === 'screener') return [
    {
      id: 'screener', label: 'Screener Results', icon: '🔍',
      fetch: async () => {
        const r = await axios.get('/api/market/screener').catch(() => null);
        const results = Array.isArray(r?.data) ? r.data.slice(0, 20) : [];
        if (!results.length) return '[Screener] No results loaded yet';
        return '[Screener Results]\n' + results.map((s: any) =>
          `${s.symbol}: $${parseFloat(s.price ?? 0).toFixed(2)}, MktCap=${fmt(s.market_cap)}, Sector=${s.sector ?? 'N/A'}, PE=${parseFloat(s.pe_ratio)?.toFixed(1) ?? 'N/A'}`
        ).join('\n');
      },
    },
  ];
  if (tab === 'calendar') return [
    {
      id: 'earnings', label: 'Earnings', icon: '📅',
      fetch: async () => {
        const r = await axios.get('/api/market/calendar/earnings').catch(() => null);
        const items = Array.isArray(r?.data) ? r.data.slice(0, 20) : [];
        if (!items.length) return '[Calendar] No upcoming earnings data';
        return '[Upcoming Earnings]\n' + items.map((e: any) =>
          `${e.symbol} (${e.date ?? e.report_date}): Est EPS=${e.eps_estimate ?? 'N/A'}, ${e.time ?? ''}`
        ).join('\n');
      },
    },
  ];
  if (tab === 'dashboard') return [
    {
      id: 'market', label: 'Market', icon: '📈',
      fetch: async () => {
        const [idx, gainers, losers, active, news] = await Promise.all([
          axios.get('/api/market/indices').catch(() => null),
          axios.get('/api/market/gainers').catch(() => null),
          axios.get('/api/market/losers').catch(() => null),
          axios.get('/api/market/active').catch(() => null),
          axios.get('/api/market/news').catch(() => null),
        ]);
        const lines: string[] = ['[Market Dashboard]'];

        const indices = Array.isArray(idx?.data) ? idx.data : [];
        if (indices.length) {
          lines.push('Indices: ' + indices.map((i: any) =>
            `${i.symbol ?? i.name}: $${parseFloat(i.price ?? i.last_price ?? 0).toFixed(2)} (${parseFloat(i.change_percent ?? i.percent_change ?? 0).toFixed(2)}%)`
          ).join(', '));
        }

        const g = Array.isArray(gainers?.data) ? gainers.data.slice(0, 5) : [];
        if (g.length) lines.push('Top Gainers: ' + g.map((s: any) => `${s.symbol} +${parseFloat(s.change_percent ?? 0).toFixed(1)}%`).join(', '));

        const l = Array.isArray(losers?.data) ? losers.data.slice(0, 5) : [];
        if (l.length) lines.push('Top Losers: ' + l.map((s: any) => `${s.symbol} ${parseFloat(s.change_percent ?? 0).toFixed(1)}%`).join(', '));

        const a = Array.isArray(active?.data) ? active.data.slice(0, 5) : [];
        if (a.length) lines.push('Most Active: ' + a.map((s: any) => `${s.symbol} Vol=${fmt(s.volume)}`).join(', '));

        const n = Array.isArray(news?.data) ? news.data.slice(0, 5) : [];
        if (n.length) lines.push('Market News:\n' + n.map((item: any) => `- ${item.title}`).join('\n'));

        return lines.join('\n');
      },
    },
  ];

  return [];
}

// ── Component ─────────────────────────────────────────────────────────
export default function AISidebar({ tab, symbol, chartCapture }: Props) {
  const [messages,        setMessages]        = useState<Message[]>([]);
  const [input,           setInput]           = useState('');
  const [loading,         setLoading]         = useState(false);
  const [files,           setFiles]           = useState<UploadedFile[]>([]);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set(['quote']));
  const [contextOpen,     setContextOpen]     = useState(false);
  const [isDragging,      setIsDragging]      = useState(false);

  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const contextKey = `${tab}::${symbol}`;

  // Reset chat when page context changes
  useEffect(() => {
    setMessages([]);
    setFiles([]);
    // Auto-select sensible defaults per tab
    if (tab === 'fundamentals') setSelectedSources(new Set(['quote', 'metrics']));
    else setSelectedSources(new Set(buildDataSources(tab, symbol).map(s => s.id)));
  }, [contextKey]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const dataSources = buildDataSources(tab, symbol);

  // ── File handling ─────────────────────────────────────────────────
  const processFile = useCallback((file: File) => {
    const maxSize = 20 * 1024 * 1024; // 20MB
    if (file.size > maxSize) { alert(`${file.name} is too large (max 20MB)`); return; }

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      // result is "data:mime/type;base64,XXXX" — strip the prefix
      const base64 = result.split(',')[1];
      const id = Math.random().toString(36).slice(2);

      const newFile: UploadedFile = {
        id, name: file.name, type: file.type, data: base64, size: file.size,
        preview: file.type.startsWith('image/') ? result : undefined,
      };
      setFiles(prev => [...prev, newFile]);
    };
    reader.readAsDataURL(file);
  }, []);

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    Array.from(e.target.files ?? []).forEach(processFile);
    e.target.value = '';
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    Array.from(e.dataTransfer.files).forEach(processFile);
  }

  // ── Send ──────────────────────────────────────────────────────────
  async function send(overrideText?: string, overrideFiles?: UploadedFile[]) {
    const text      = (overrideText ?? input).trim();
    const sendFiles = overrideFiles ?? files;
    if ((!text && sendFiles.length === 0) || loading) return;
    if (!overrideText) setInput('');
    if (!overrideFiles) setFiles([]);

    const newMsg: Message = { role: 'user', content: text, attachedFiles: sendFiles.length > 0 ? [...sendFiles] : undefined };
    const newMessages = [...messages, newMsg];
    setMessages(newMessages);
    setLoading(true);

    try {
      const sources = dataSources.filter(s => selectedSources.has(s.id));
      const fetched = await Promise.all(sources.map(s => s.fetch().catch(() => '')));
      const context = fetched.filter(Boolean).join('\n\n');

      const apiMessages = newMessages.map(m => ({ role: m.role, content: m.content }));
      const apiFiles    = newMsg.attachedFiles?.map(f => ({ name: f.name, type: f.type, data: f.data })) ?? [];

      const res = await axios.post('/api/ai/chat', { messages: apiMessages, context, files: apiFiles });
      setMessages([...newMessages, { role: 'assistant', content: res.data.content }]);
    } catch {
      setMessages([...newMessages, { role: 'assistant', content: 'Request failed. Please try again later.' }]);
    } finally {
      setLoading(false);
    }
  }

  // ── Analyze chart (called from sidebar button) ────────────────────
  async function handleAnalyzeChart() {
    if (!chartCapture?.current || loading) return;
    setLoading(true);
    try {
      const base64 = await chartCapture.current();
      const chartFile: UploadedFile = {
        id: 'chart', name: `${symbol}_chart.png`, type: 'image/png',
        data: base64, size: 0,
        preview: `data:image/png;base64,${base64}`,
      };
      await send(
        `Please analyze the technical picture of this ${symbol} price chart. Include: overall trend, key support/resistance levels, recent candlestick patterns, moving average signals, volume-price relationship, and short-term outlook for the next 1-4 weeks. Please reference specific price levels.`,
        [chartFile],
      );
    } catch {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  }

  function toggleSource(id: string) {
    setSelectedSources(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const tabLabel = tab === 'dashboard' ? 'Market Overview'
    : tab === 'charting'     ? `Chart · ${symbol}`
    : tab === 'fundamentals' ? `${symbol} · Data`
    : tab === 'screener'     ? 'Screener'
    : tab === 'calendar'     ? 'Calendar'
    : '';

  const suggestions = tab === 'fundamentals'
    ? ['What are the key investment highlights?', 'How does valuation compare to peers?', 'What are the main risks?', 'Any recent notable developments?']
    : ['What is the current market sentiment?', 'What opportunities are worth watching?', 'What are the main risks?', 'What are the latest developments?'];

  return (
    <div
      className="ai-sidebar"
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="ai-drop-overlay">
          <div className="ai-drop-label">Drop files to attach</div>
        </div>
      )}

      {/* Header */}
      <div className="ai-sidebar-header">
        <div className="ai-sidebar-title">AI Assistant</div>
        {tabLabel && <div className="ai-sidebar-context">{tabLabel}</div>}
      </div>

      {/* Context Panel */}
      {dataSources.length > 0 && (
        <div className="ai-context-panel">
          <button className="ai-context-toggle" onClick={() => setContextOpen(o => !o)}>
            <span>📊 Data Context</span>
            <span className="ai-context-count">{selectedSources.size} selected</span>
            <span className="ai-context-arrow">{contextOpen ? '▲' : '▼'}</span>
          </button>

          {contextOpen && (
            <div className="ai-context-chips">
              {dataSources.map(s => (
                <button
                  key={s.id}
                  className={`ai-chip ${selectedSources.has(s.id) ? 'ai-chip-on' : 'ai-chip-off'}`}
                  onClick={() => toggleSource(s.id)}
                >
                  {s.icon} {s.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="ai-messages">
        {messages.length === 0 && (
          <div className="ai-welcome">
            <div className="ai-welcome-text">Hello, I'm your investment research assistant.</div>
            <div className="ai-welcome-sub">Select data sources, upload files, or ask anything.</div>
            {tab === 'charting' && chartCapture && (
              <button
                className="ai-analyze-chart-btn"
                onClick={handleAnalyzeChart}
                disabled={loading}
              >
                📊 Analyze Chart
              </button>
            )}
            <div className="ai-suggestions">
              {suggestions.map((s, i) => (
                <button key={i} className="ai-suggestion-btn" onClick={() => { setInput(s); textareaRef.current?.focus(); }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`ai-msg ${m.role}`}>
            <div className="ai-msg-label">{m.role === 'user' ? 'You' : 'AI'}</div>
            {m.attachedFiles && m.attachedFiles.length > 0 && (
              <div className="ai-msg-files">
                {m.attachedFiles.map(f => (
                  <div key={f.id} className="ai-file-chip-sent">
                    <span>{f.type.startsWith('image/') ? '🖼️' : f.type === 'application/pdf' ? '📄' : '📝'}</span>
                    <span>{f.name}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="ai-msg-content">{m.role === 'assistant' ? renderMarkdown(m.content) : m.content}</div>
          </div>
        ))}

        {loading && (
          <div className="ai-msg assistant">
            <div className="ai-msg-label">AI</div>
            <div className="ai-msg-content ai-typing"><span /><span /><span /></div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Attached files preview */}
      {files.length > 0 && (
        <div className="ai-files-preview">
          {files.map(f => (
            <div key={f.id} className="ai-file-chip">
              {f.preview
                ? <img src={f.preview} className="ai-file-thumb" alt={f.name} />
                : <span className="ai-file-icon">{f.type === 'application/pdf' ? '📄' : '📝'}</span>
              }
              <span className="ai-file-name">{f.name}</span>
              <button className="ai-file-remove" onClick={() => setFiles(prev => prev.filter(x => x.id !== f.id))}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="ai-input-area">
        <div className="ai-input-row">
          <textarea
            ref={textareaRef}
            className="ai-input"
            value={input}
            placeholder="Ask anything about the current data..."
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
          />
          <button className="ai-send-btn" onClick={send} disabled={loading || (!input.trim() && files.length === 0)}>
            Send
          </button>
        </div>
        <div className="ai-input-actions">
          <button className="ai-attach-btn" onClick={() => fileInputRef.current?.click()} title="Attach files">
            📎 Attach
          </button>
          <span className="ai-attach-hint">PDF · Image · Text · Drag & drop</span>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.md"
            style={{ display: 'none' }}
            onChange={handleFileInput}
          />
        </div>
      </div>
    </div>
  );
}
