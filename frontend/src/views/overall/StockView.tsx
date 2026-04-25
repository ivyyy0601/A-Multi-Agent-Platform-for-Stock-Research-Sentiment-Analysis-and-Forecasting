import React, { useEffect, useState, lazy, Suspense } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  PointElement, LineElement,
  BarElement, ArcElement,
  Title, Tooltip as ChartJSTooltip, Legend, Filler,
} from 'chart.js';

ChartJS.register(
  CategoryScale, LinearScale,
  PointElement, LineElement,
  BarElement, ArcElement,
  Title, ChartJSTooltip, Legend, Filler,
);

const DeepDive  = lazy(() => import('../sentiment/components/DeepDive'));
const TearSheet = lazy(() => import('./TearSheet'));
const ICMemo    = lazy(() => import('./ICMemo'));

interface Props {
  symbol: string;
  onSelectStock: (sym: string) => void;
  watchlist?: string[];
  onAddToWatchlist?: (sym: string) => void;
  onRemoveFromWatchlist?: (sym: string) => void;
  analystName?: string;
}

type TabKey = 'overview' | 'financials' | 'analyst' | 'ownership' | 'peers' | 'filings' | 'sentiment' | 'news';
type FinType = 'income' | 'balance' | 'cash';
type Period  = 'annual' | 'quarter';
type ChartPeriod = '1w' | '1m' | '3m' | '6m' | '1y' | '2y';

// ── helpers ─────────────────────────────────────────────────────────
const NA = 'N/P';   // free API doesn't return this field

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
  // If value looks like a ratio (< 2), treat as decimal percent
  return (Math.abs(v) < 2 ? (v * 100).toFixed(2) : v.toFixed(2)) + '%';
}
function price(n: any): string {
  const v = parseFloat(n);
  return isNaN(v) ? 'N/A' : '$' + v.toFixed(2);
}
function pct(n: any): string {
  const v = parseFloat(n);
  if (isNaN(v)) return '-';
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
}

// ── Simple markdown renderer (for filing AI responses) ───────────────
function renderMd(text: string): React.ReactNode {
  return text.split('\n').map((line, i) => {
    if (line.startsWith('### ')) return <div key={i} style={{ fontWeight: 700, fontSize: 13, color: '#c8d8ff', marginTop: 10 }}>{line.slice(4)}</div>;
    if (line.startsWith('## '))  return <div key={i} style={{ fontWeight: 700, fontSize: 14, color: '#a0b4ff', marginTop: 12 }}>{line.slice(3)}</div>;
    if (line.startsWith('# '))   return <div key={i} style={{ fontWeight: 700, fontSize: 15, color: '#fff', marginTop: 14 }}>{line.slice(2)}</div>;
    if (line.startsWith('- ') || line.startsWith('• ')) return <div key={i} style={{ paddingLeft: 12, color: '#ccc', fontSize: 12, lineHeight: 1.6 }}>• {line.slice(2)}</div>;
    if (/^---+$/.test(line.trim())) return <hr key={i} style={{ border: 'none', borderTop: '1px solid #2a2d3a', margin: '8px 0' }} />;
    if (line.trim() === '') return <div key={i} style={{ height: 6 }} />;
    // bold
    const parts = line.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={j}>{p.slice(2, -2)}</strong> : p
    );
    return <p key={i} style={{ margin: '3px 0', color: '#ccc', fontSize: 12, lineHeight: 1.6 }}>{parts}</p>;
  });
}

// ── Custom chart tooltip ─────────────────────────────────────────────
const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{ background: '#1a1d27', border: '1px solid #2a2d3a', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#e0e0e0' }}>
      <div style={{ marginBottom: 4, color: '#888' }}>{label}</div>
      <div>Close <strong style={{ color: '#6c8fff' }}>{price(d.close)}</strong></div>
      <div style={{ display: 'flex', gap: 10, color: '#888', marginTop: 2 }}>
        <span>Open {price(d.open)}</span>
        <span>High {price(d.high)}</span>
        <span>Low {price(d.low)}</span>
      </div>
    </div>
  );
};

export default function StockView({ symbol: initSymbol, onSelectStock, watchlist = [], onAddToWatchlist, onRemoveFromWatchlist, analystName }: Props) {
  const [input,   setInput]   = useState(initSymbol);
  const [symbol,  setSymbol]  = useState(initSymbol);

  // Sync when parent navigates to a new symbol
  useEffect(() => {
    setInput(initSymbol);
    setSymbol(initSymbol);
  }, [initSymbol]);
  const [tab,     setTab]     = useState<TabKey>('overview');
  const [period,  setPeriod]  = useState<ChartPeriod>('1y');
  const [finType, setFinType] = useState<FinType>('income');
  const [finPeriod, setFinPeriod] = useState<Period>('annual');

  const [quote,       setQuote]       = useState<any>(null);
  const [profile,     setProfile]     = useState<any>(null);
  const [metrics,     setMetrics]     = useState<any>(null);
  const [history,     setHistory]     = useState<any[]>([]);
  const [income,      setIncome]      = useState<any[]>([]);
  const [balance,     setBalance]     = useState<any[]>([]);
  const [cash,        setCash]        = useState<any[]>([]);
  const [consensus,   setConsensus]   = useState<any>(null);
  const [targets,     setTargets]     = useState<any[]>([]);
  const [_instit,     setInstit]      = useState<any[]>([]);
  const [insiders,    setInsiders]    = useState<any[]>([]);
  const [peers,       setPeers]       = useState<any[]>([]);
  const [filings,     setFilings]     = useState<any[]>([]);
  const [stockNews,   setStockNews]   = useState<any[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [chartLoad,   setChartLoad]   = useState(false);
  const [tabLoading,  setTabLoading]  = useState(false);
  const [showTearSheet, setShowTearSheet] = useState(false);
  const [showICMemo,    setShowICMemo]    = useState(false);
  const [expandedFiling,     setExpandedFiling]     = useState<string | null>(null);
  const [filingText,         setFilingText]         = useState<Record<string, string>>({});
  const [filingTextLoading,  setFilingTextLoading]  = useState<string | null>(null);
  const [filingAiResult,     setFilingAiResult]     = useState<Record<string, string>>({});
  const [filingAiLoading,    setFilingAiLoading]    = useState<string | null>(null);

  // Load base data when symbol changes
  useEffect(() => {
    setInput(symbol);
    setLoading(true);
    Promise.all([
      axios.get(`/api/market/stock/${symbol}/quote`).catch(() => null),
      axios.get(`/api/market/stock/${symbol}/profile`).catch(() => null),
      axios.get(`/api/market/stock/${symbol}/metrics`).catch(() => null),
    ]).then(([q, p, m]) => {
      setQuote(  Array.isArray(q?.data) ? q.data[0] : q?.data ?? null);
      setProfile(Array.isArray(p?.data) ? p.data[0] : p?.data ?? null);
      setMetrics(Array.isArray(m?.data) ? m.data[0] : m?.data ?? null);
      setLoading(false);
    });
  }, [symbol]);

  // Load chart data when period changes
  useEffect(() => {
    setChartLoad(true);
    axios.get(`/api/market/stock/${symbol}/historical?period=${period}`)
      .then(r => setHistory(Array.isArray(r.data) ? r.data : []))
      .catch(() => setHistory([]))
      .finally(() => setChartLoad(false));
  }, [symbol, period]);

  // Load tab-specific data lazily
  useEffect(() => {
    if (tab === 'overview') return;
    setTabLoading(true);
    if (tab === 'financials') {
      Promise.all([
        axios.get(`/api/market/stock/${symbol}/income?period=${finPeriod}`).then(r => setIncome(Array.isArray(r.data) ? r.data : [])).catch(() => setIncome([])),
        axios.get(`/api/market/stock/${symbol}/balance?period=${finPeriod}`).then(r => setBalance(Array.isArray(r.data) ? r.data : [])).catch(() => setBalance([])),
        axios.get(`/api/market/stock/${symbol}/cash?period=${finPeriod}`).then(r => setCash(Array.isArray(r.data) ? r.data : [])).catch(() => setCash([])),
      ]).finally(() => setTabLoading(false));
    }
    if (tab === 'analyst') {
      Promise.all([
        axios.get(`/api/market/stock/${symbol}/consensus`).then(r => setConsensus(Array.isArray(r.data) && r.data[0] ? r.data[0] : null)).catch(() => setConsensus(null)),
        axios.get(`/api/market/stock/${symbol}/targets`).then(r => setTargets(Array.isArray(r.data) ? r.data : [])).catch(() => setTargets([])),
      ]).finally(() => setTabLoading(false));
    }
    if (tab === 'ownership') {
      Promise.all([
        axios.get(`/api/market/stock/${symbol}/institutional`).then(r => setInstit(Array.isArray(r.data) ? r.data.slice(0, 15) : [])).catch(() => setInstit([])),
        axios.get(`/api/market/stock/${symbol}/insiders`).then(r => setInsiders(Array.isArray(r.data) ? r.data.slice(0, 15) : [])).catch(() => setInsiders([])),
      ]).finally(() => setTabLoading(false));
    }
    if (tab === 'peers') {
      axios.get(`/api/market/stock/${symbol}/peers`).then(r => setPeers(Array.isArray(r.data) ? r.data : [])).catch(() => setPeers([])).finally(() => setTabLoading(false));
    }
    if (tab === 'filings') {
      axios.get(`/api/market/stock/${symbol}/filings`).then(r => setFilings(Array.isArray(r.data) ? r.data : [])).catch(() => setFilings([])).finally(() => setTabLoading(false));
    }
    if (tab === 'news') {
      axios.get(`/api/market/stock/${symbol}/news`).then(r => setStockNews(Array.isArray(r.data) ? r.data : [])).catch(() => setStockNews([])).finally(() => setTabLoading(false));
    }
  }, [tab, symbol, finPeriod]);

  function search() {
    const s = input.trim().toUpperCase();
    if (s) { setSymbol(s); onSelectStock(s); }
  }

  // ── derived ───────────────────────────────────────────────────────
  const currentPrice = parseFloat(quote?.price ?? quote?.last_price ?? 0);
  const chgPct       = parseFloat(quote?.change_percent ?? quote?.percent_change ?? 0);
  const chartColor   = chgPct >= 0 ? '#00e676' : '#ff5252';

  const chartData = history.map((d: any) => ({
    date:  (d.date ?? '').slice(0, 10),
    close: parseFloat(d.close ?? 0),
    open:  parseFloat(d.open  ?? 0),
    high:  parseFloat(d.high  ?? 0),
    low:   parseFloat(d.low   ?? 0),
  }));

  // ── Financial table helper ────────────────────────────────────────
  function FinTable({ rows, cols }: { rows: any[]; cols: { key: string; label: string; money?: boolean }[] }) {
    if (tabLoading) return <div className="overall-loading" style={{ height: 80 }}>Loading...</div>;
    if (!rows.length) return <div className="muted" style={{ padding: '20px 0', fontSize: 13 }}>No data available</div>;
    const dates = rows.slice(0, 5).map(r => (r.period_ending ?? r.date ?? r.period ?? '').slice(0, 10));
    return (
      <div style={{ overflowX: 'auto' }}>
        <table className="ov-table">
          <thead>
            <tr>
              <th>Metric</th>
              {dates.map(d => <th key={d} className="right">{d}</th>)}
            </tr>
          </thead>
          <tbody>
            {cols.map(col => (
              <tr key={col.key}>
                <td style={{ color: '#aaa' }}>{col.label}</td>
                {rows.slice(0, 5).map((r, i) => {
                  const v = r[col.key];
                  return <td key={i} className="right">{v != null ? (col.money ? fmt(v) : String(v)) : '-'}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // ── Analyst tab ───────────────────────────────────────────────────
  function AnalystTab() {
    if (tabLoading) return <div className="overall-loading" style={{ height: 80 }}>Loading...</div>;
    const targetMean = parseFloat(consensus?.target_consensus ?? consensus?.target_mean_price ?? consensus?.price_target_mean ?? consensus?.price_target ?? 0);
    const targetHigh = parseFloat(consensus?.target_high ?? consensus?.target_high_price ?? consensus?.price_target_high ?? 0);
    const targetLow  = parseFloat(consensus?.target_low ?? consensus?.target_low_price ?? consensus?.price_target_low ?? 0);
    const numAnalysts = parseInt(consensus?.number_of_analysts ?? consensus?.analyst_count ?? 0);
    const rec = consensus?.recommendation ?? '';
    const recMean = parseFloat(consensus?.recommendation_mean ?? 0);
    // recommendation_mean: 1=strong buy, 2=buy, 3=hold, 4=sell, 5=strong sell
    const buy  = recMean > 0 ? Math.round(numAnalysts * Math.max(0, (3 - recMean) / 2)) : 0;
    const sell = recMean > 0 ? Math.round(numAnalysts * Math.max(0, (recMean - 3) / 2)) : 0;
    const hold = Math.max(0, numAnalysts - buy - sell);
    const total = buy + hold + sell || 1;

    return (
      <div>
        <div className="analyst-section">
          <div className="analyst-section-title">Analyst Price Targets</div>
          <div className="target-range">
            <div className="target-item">
              <div className="target-lbl">Low</div>
              <div className="target-val">{price(targetLow)}</div>
            </div>
            <div style={{ flex: 1, padding: '0 10px' }}>
              <div style={{ height: 4, background: '#2a2d3a', borderRadius: 2, position: 'relative' }}>
                {targetHigh > 0 && targetLow > 0 && currentPrice > 0 && (
                  <div style={{
                    position: 'absolute',
                    left: `${Math.max(0, Math.min(100, ((currentPrice - targetLow) / (targetHigh - targetLow)) * 100))}%`,
                    top: -4, width: 3, height: 12, background: '#6c8fff', borderRadius: 2,
                  }} />
                )}
              </div>
            </div>
            <div className="target-item">
              <div className="target-lbl">Mean</div>
              <div className="target-val" style={{ color: '#6c8fff' }}>{price(targetMean)}</div>
            </div>
            <div className="target-item">
              <div className="target-lbl">High</div>
              <div className="target-val">{price(targetHigh)}</div>
            </div>
          </div>
        </div>

        {consensus && (
          <div className="analyst-section">
            <div className="analyst-section-title">Consensus Rating</div>
            <div style={{ display: 'flex', gap: 20, padding: '12px 16px', background: '#0d0f17', border: '1px solid #2a2d3a', borderRadius: 6, marginBottom: 12, alignItems: 'center' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#666', marginBottom: 4 }}>Rating</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: rec === 'buy' || rec === 'strong_buy' ? '#00e676' : rec === 'sell' ? '#ff5252' : '#ffd740', textTransform: 'capitalize' }}>{rec || '-'}</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#666', marginBottom: 4 }}>Analysts</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{numAnalysts}</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#666', marginBottom: 4 }}>Current Price</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{price(consensus.current_price)}</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#666', marginBottom: 4 }}>Median Target</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#6c8fff' }}>{price(consensus.target_median ?? consensus.target_median_price ?? consensus.target_mean_price)}</div>
              </div>
            </div>
          </div>
        )}

        {(buy + hold + sell) > 0 && (
          <div className="analyst-section">
            <div className="analyst-section-title">Rating Distribution</div>
            <div className="rating-bar">
              <div className="rating-buy"  style={{ width: `${(buy  / total) * 100}%` }} />
              <div className="rating-hold" style={{ width: `${(hold / total) * 100}%` }} />
              <div className="rating-sell" style={{ width: `${(sell / total) * 100}%` }} />
            </div>
            <div className="rating-legend">
              <span><span className="legend-dot" style={{ background: '#00e676' }} />Buy {buy}</span>
              <span><span className="legend-dot" style={{ background: '#ffd740' }} />Hold {hold}</span>
              <span><span className="legend-dot" style={{ background: '#ff5252' }} />Sell {sell}</span>
            </div>
          </div>
        )}

        {targets.length > 0 && (
          <div className="analyst-section">
            <div className="analyst-section-title">Recent Target Records</div>
            <table className="ov-table">
              <thead><tr><th>Firm</th><th className="right">Target</th><th className="right">Rating</th><th className="right">Date</th></tr></thead>
              <tbody>
                {targets.slice(0, 10).map((t: any, i: number) => (
                  <tr key={i}>
                    <td>{t.analyst_company ?? t.analyst_firm ?? t.company ?? '-'}</td>
                    <td className="right">{price(t.adj_price_target ?? t.price_target ?? t.target)}</td>
                    <td className="right" style={{ color: '#6c8fff' }}>{t.rating_change ?? t.rating_current ?? t.action_company ?? t.rating ?? '-'}</td>
                    <td className="right muted">{(t.published_date ?? t.date ?? '').slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {targets.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No analyst data available</div>}
      </div>
    );
  }

  // ── Ownership tab ─────────────────────────────────────────────────
  function OwnershipTab() {
    if (tabLoading) return <div className="overall-loading" style={{ height: 80 }}>Loading...</div>;
    const summary = _instit.filter((r: any) => r.type === 'summary');
    const holders = _instit.filter((r: any) => r.type === 'holder');

    const summaryLabels: Record<string, string> = {
      insidersPercentHeld:         'Insider Ownership',
      institutionsPercentHeld:     'Institutional Ownership',
      institutionsFloatPercentHeld:'Inst. Float Ownership',
      institutionsCount:           'Institution Count',
    };

    return (
      <div>
        {/* Ownership summary */}
        {summary.length > 0 && (
          <div className="ownership-section">
            <div className="ownership-title">Ownership Structure</div>
            <div className="stats-grid" style={{ marginBottom: 0 }}>
              {summary.map((r: any, i: number) => {
                const label = summaryLabels[r.label] ?? r.label;
                const isCount = r.label === 'institutionsCount';
                const val = isCount
                  ? Number(r.value).toLocaleString()
                  : (r.value != null ? (parseFloat(r.value) * 100).toFixed(2) + '%' : '-');
                return (
                  <div key={i} className="stat-item">
                    <div className="stat-label">{label}</div>
                    <div className="stat-value">{val}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Top institutional holders */}
        <div className="ownership-section">
          <div className="ownership-title">Top Institutional Holders (Source: Yahoo Finance)</div>
          {holders.length > 0 ? (
            <table className="ov-table">
              <thead>
                <tr>
                  <th>Institution</th>
                  <th className="right">% Held</th>
                  <th className="right">Shares</th>
                  <th className="right">Value</th>
                  <th className="right">Change</th>
                  <th className="right">Report Date</th>
                </tr>
              </thead>
              <tbody>
                {holders.map((r: any, i: number) => {
                  const chg = parseFloat(r.pctChange ?? 0);
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 500 }}>{r.Holder ?? '-'}</td>
                      <td className="right">{r.pctHeld != null ? (parseFloat(r.pctHeld) * 100).toFixed(2) + '%' : '-'}</td>
                      <td className="right">{fmt(r.Shares)}</td>
                      <td className="right">{fmt(r.Value)}</td>
                      <td className={`right ${chg >= 0 ? 'positive' : 'negative'}`}>
                        {chg >= 0 ? '+' : ''}{(chg * 100).toFixed(2)}%
                      </td>
                      <td className="right muted">{(r['Date Reported'] ?? '').slice(0, 10)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <div className="muted" style={{ fontSize: 13 }}>Loading...</div>}
        </div>

        {/* Insider trading */}
        <div className="ownership-section">
          <div className="ownership-title">Insider Trading (Source: SEC Form 4)</div>
          {insiders.length > 0 ? (
            <table className="ov-table">
              <thead>
                <tr><th>Name</th><th>Title</th><th className="right">Type</th><th className="right">Shares</th><th className="right">Price</th><th className="right">Date</th></tr>
              </thead>
              <tbody>
                {insiders.map((r: any, i: number) => {
                  const isBuy = (r.acquisition_or_disposition ?? '').toUpperCase() === 'A';
                  return (
                    <tr key={i}>
                      <td>{r.owner_name ?? '-'}</td>
                      <td className="muted" style={{ fontSize: 12 }}>{r.owner_title ?? '-'}</td>
                      <td className={`right ${isBuy ? 'positive' : 'negative'}`}>{isBuy ? 'Buy/Award' : 'Sell/Tax'}</td>
                      <td className="right">{fmt(r.securities_transacted ?? r.securities_owned)}</td>
                      <td className="right">{price(r.transaction_price)}</td>
                      <td className="right muted">{(r.transaction_date ?? r.filing_date ?? '').slice(0, 10)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <div className="muted" style={{ fontSize: 13 }}>No insider trading data available</div>}
        </div>
      </div>
    );
  }

  // ── render ────────────────────────────────────────────────────────
  return (
    <div className="stock-view">
      {/* Search */}
      <div className="stock-search">
        <input
          className="stock-search-input"
          value={input}
          placeholder="Enter ticker, e.g. AAPL"
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && search()}
        />
        <button className="stock-search-btn" onClick={search}>Search</button>
      </div>

      {loading && <div className="overall-loading">Loading...</div>}

      {!loading && quote && (
        <>
          {/* Header */}
          <div className="stock-header">
            <span className="sh-symbol">{symbol}</span>
            <span className={`sh-price ${chgPct >= 0 ? 'positive' : 'negative'}`}>{price(currentPrice)}</span>
            <span className={`sh-chg ${chgPct >= 0 ? 'positive' : 'negative'}`}>{pct(chgPct)}</span>
            <span className="sh-name">{profile?.name ?? quote?.name ?? ''}</span>
            {watchlist.includes(symbol)
              ? <button className="wl-star-btn wl-star-on"  onClick={() => onRemoveFromWatchlist?.(symbol)} title="Remove from Watchlist">⭐ Watching</button>
              : <button className="wl-star-btn wl-star-off" onClick={() => onAddToWatchlist?.(symbol)}    title="Add to Watchlist">☆ Watch</button>
            }
            <button className="ic-trigger-btn" onClick={() => setShowICMemo(true)}>
              🔬 Deep Analysis
            </button>
            <button className="ts-trigger-btn" onClick={() => setShowTearSheet(true)}>
              ⚡ Quick Analysis
            </button>
          </div>

          {/* Chart */}
          <div className="chart-wrap">
            <div className="chart-periods">
              {(['1w','1m','3m','6m','1y','2y'] as ChartPeriod[]).map(p => (
                <button key={p} className={`period-btn ${period === p ? 'active' : ''}`} onClick={() => setPeriod(p)}>
                  {p.toUpperCase()}
                </button>
              ))}
            </div>
            {chartLoad
              ? <div className="overall-loading" style={{ height: 200 }}>Loading chart...</div>
              : (
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={chartColor} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={chartColor} stopOpacity={0}   />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#555' }} tickLine={false} axisLine={false}
                      interval={Math.floor(chartData.length / 6)} />
                    <YAxis domain={['auto','auto']} tick={{ fontSize: 10, fill: '#555' }} tickLine={false}
                      axisLine={false} tickFormatter={v => '$' + v.toFixed(0)} width={55} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="close" stroke={chartColor} strokeWidth={1.5}
                      fill="url(#chartGrad)" dot={false} activeDot={{ r: 3, fill: chartColor }} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
          </div>

          {/* Tabs */}
          <div className="stock-tabs-container">
            <div className="tab-nav">
              {([
                ['overview', 'Overview'], ['financials', 'Financials'],
                ['analyst', 'Analyst'], ['ownership', 'Ownership'], ['peers', 'Peers'], ['filings', 'SEC Filings'], ['sentiment', 'Sentiment'], ['news', 'News'],
              ] as [TabKey, string][]).map(([k, label]) => (
                <button key={k} className={`tab-btn ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
              ))}
            </div>

            <div className="tab-body">
              {/* Overview */}
              {tab === 'overview' && (
                <>
                  {/* Quick stats row */}
                  <div className="stats-grid">
                    {[
                      ['Mkt Cap',  fmt(metrics?.market_cap ?? quote?.market_cap)],
                      ['52W High', price(quote?.year_high ?? quote?.high_52_week)],
                      ['52W Low',  price(quote?.year_low  ?? quote?.low_52_week)],
                      ['Volume',   fmt(quote?.volume)],
                      ['50D MA',   price(quote?.ma_50d)],
                      ['Open',     price(quote?.open)],
                      ['High',     price(quote?.high)],
                      ['Low',      price(quote?.low)],
                    ].map(([label, val]) => (
                      <div key={label} className="stat-item">
                        <div className="stat-label">{label}</div>
                        <div className="stat-value">{val}</div>
                      </div>
                    ))}
                  </div>

                  {/* Valuation */}
                  <div className="metrics-section">
                    <div className="metrics-section-title">Valuation</div>
                    <div className="metrics-grid">
                      {([
                        ['PE (TTM)',    metrics?.pe_ratio != null ? parseFloat(metrics.pe_ratio).toFixed(2) : 'N/A'],
                        ['Forward PE', metrics?.forward_pe != null ? parseFloat(metrics.forward_pe).toFixed(2) : 'N/A'],
                        ['PEG',        metrics?.peg_ratio_ttm != null ? parseFloat(metrics.peg_ratio_ttm).toFixed(2) : 'N/A'],
                        ['P/B',        metrics?.price_to_book != null ? parseFloat(metrics.price_to_book).toFixed(2) : 'N/A'],
                        ['P/S',        NA],
                        ['EV',         fmt(metrics?.enterprise_value)],
                        ['EV/EBITDA',  metrics?.enterprise_to_ebitda != null ? parseFloat(metrics.enterprise_to_ebitda).toFixed(2) : 'N/A'],
                        ['EV/Revenue', metrics?.enterprise_to_revenue != null ? parseFloat(metrics.enterprise_to_revenue).toFixed(2) : 'N/A'],
                      ] as [string, string][]).map(([label, val]) => (
                        <div key={label} className="metric-item">
                          <div className="metric-label">{label}</div>
                          <div className={`metric-value ${val === NA ? 'metric-na' : val === 'N/A' ? 'metric-value-na' : ''}`}>{val}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Profitability */}
                  <div className="metrics-section">
                    <div className="metrics-section-title">Profitability</div>
                    <div className="metrics-grid">
                      {([
                        ['Gross Margin',    fmtPct(metrics?.gross_margin)],
                        ['Operating Margin', fmtPct(metrics?.operating_margin)],
                        ['EBITDA Margin',   fmtPct(metrics?.ebitda_margin)],
                        ['Net Margin',      fmtPct(metrics?.profit_margin)],
                        ['ROA',             fmtPct(metrics?.return_on_assets)],
                        ['ROE',             fmtPct(metrics?.return_on_equity)],
                        ['EPS (TTM)',        NA],
                        ['Forward EPS',     NA],
                      ] as [string, string][]).map(([label, val]) => (
                        <div key={label} className="metric-item">
                          <div className="metric-label">{label}</div>
                          <div className={`metric-value ${val === NA ? 'metric-na' : val === 'N/A' ? 'metric-value-na' : ''}`}>{val}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Growth */}
                  <div className="metrics-section">
                    <div className="metrics-section-title">Growth</div>
                    <div className="metrics-grid">
                      {([
                        ['Earnings Growth', metrics?.earnings_growth != null ? fmtPct(metrics.earnings_growth) : 'N/A'],
                        ['Revenue Growth',  fmtPct(metrics?.revenue_growth)],
                        ['1Y Return',       metrics?.price_return_1y != null ? pct(parseFloat(metrics.price_return_1y) * 100) : '-'],
                        ['Beta',            metrics?.beta != null ? parseFloat(metrics.beta).toFixed(2) : '-'],
                        ['50D MA',          price(quote?.ma_50d)],
                        ['200D MA',         price(quote?.ma_200d)],
                      ] as [string, string][]).map(([label, val]) => (
                        <div key={label} className="metric-item">
                          <div className="metric-label">{label}</div>
                          <div className={`metric-value ${val === NA ? 'metric-na' : val === 'N/A' ? 'metric-value-na' : ''}`}>{val}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Financial Health */}
                  <div className="metrics-section">
                    <div className="metrics-section-title">Financial Health</div>
                    <div className="metrics-grid">
                      {([
                        ['Debt/Equity',   metrics?.debt_to_equity != null ? parseFloat(metrics.debt_to_equity).toFixed(2) : '-'],
                        ['Quick Ratio',   metrics?.quick_ratio    != null ? parseFloat(metrics.quick_ratio).toFixed(2) : '-'],
                        ['Current Ratio', metrics?.current_ratio  != null ? parseFloat(metrics.current_ratio).toFixed(2) : '-'],
                        ['Total Debt',    NA],
                        ['Cash & Equiv',  NA],
                        ['Free Cash Flow', NA],
                      ] as [string, string][]).map(([label, val]) => (
                        <div key={label} className="metric-item">
                          <div className="metric-label">{label}</div>
                          <div className={`metric-value ${val === NA ? 'metric-na' : val === 'N/A' ? 'metric-value-na' : ''}`}>{val}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Dividend */}
                  <div className="metrics-section">
                    <div className="metrics-section-title">Dividends</div>
                    <div className="metrics-grid">
                      {([
                        ['Div Yield',      metrics?.dividend_yield != null ? fmtPct(metrics.dividend_yield) : 'N/A'],
                        ['5Y Avg Yield',   fmtPct(metrics?.dividend_yield_5y_avg)],
                        ['Payout Ratio',   fmtPct(metrics?.payout_ratio)],
                        ['Div per Share',  NA],
                      ] as [string, string][]).map(([label, val]) => (
                        <div key={label} className="metric-item">
                          <div className="metric-label">{label}</div>
                          <div className={`metric-value ${val === NA ? 'metric-na' : val === 'N/A' ? 'metric-value-na' : ''}`}>{val}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {profile?.description && (
                    <div className="company-desc">{profile.description}</div>
                  )}
                </>
              )}

              {/* Financials */}
              {tab === 'financials' && (
                <>
                  <div className="fin-controls">
                    {(['income', 'balance', 'cash'] as FinType[]).map(k => (
                      <button key={k} className={`fin-btn ${finType === k ? 'active' : ''}`} onClick={() => setFinType(k)}>
                        {{ income: 'Income', balance: 'Balance Sheet', cash: 'Cash Flow' }[k]}
                      </button>
                    ))}
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                      {(['annual', 'quarter'] as Period[]).map(p => (
                        <button key={p} className={`fin-btn ${finPeriod === p ? 'active' : ''}`} onClick={() => setFinPeriod(p)}>
                          {{ annual: 'Annual', quarter: 'Quarterly' }[p]}
                        </button>
                      ))}
                    </div>
                  </div>

                  {finType === 'income' && <FinTable rows={income} cols={[
                    { key: 'total_revenue',            label: 'Revenue',       money: true },
                    { key: 'gross_profit',             label: 'Gross Profit',  money: true },
                    { key: 'operating_income',         label: 'Op. Income',    money: true },
                    { key: 'net_income',               label: 'Net Income',    money: true },
                    { key: 'ebitda',                   label: 'EBITDA',        money: true },
                    { key: 'diluted_earnings_per_share', label: 'EPS (Diluted)' },
                  ]} />}
                  {finType === 'balance' && <FinTable rows={balance} cols={[
                    { key: 'total_assets',                      label: 'Total Assets',    money: true },
                    { key: 'total_liabilities_net_minority_interest', label: 'Total Liabilities', money: true },
                    { key: 'common_stock_equity',               label: 'Equity',          money: true },
                    { key: 'cash_and_cash_equivalents',         label: 'Cash & Equiv',    money: true },
                    { key: 'total_debt',                        label: 'Total Debt',      money: true },
                    { key: 'net_debt',                          label: 'Net Debt',        money: true },
                    { key: 'working_capital',                   label: 'Working Capital', money: true },
                  ]} />}
                  {finType === 'cash' && <FinTable rows={cash} cols={[
                    { key: 'operating_cash_flow',    label: 'Operating CF',  money: true },
                    { key: 'investing_cash_flow',    label: 'Investing CF',  money: true },
                    { key: 'financing_cash_flow',    label: 'Financing CF',  money: true },
                    { key: 'free_cash_flow',         label: 'Free CF',       money: true },
                    { key: 'capital_expenditure',    label: 'CapEx',         money: true },
                    { key: 'stock_based_compensation', label: 'SBC',         money: true },
                  ]} />}
                </>
              )}

              {tab === 'analyst'   && <AnalystTab />}
              {tab === 'ownership' && <OwnershipTab />}

              {/* Peers */}
              {tab === 'peers' && (
                tabLoading
                  ? <div className="overall-loading" style={{ height: 80 }}>Loading...</div>
                  : peers.length === 0
                    ? <div className="muted" style={{ padding: '20px 0', fontSize: 13 }}>No peer data available</div>
                    : <div style={{ overflowX: 'auto' }}>
                        <table className="ov-table">
                          <thead>
                            <tr>
                              <th>Ticker</th>
                              <th>Company</th>
                              <th className="right">Price</th>
                              <th className="right">Mkt Cap</th>
                              <th className="right">PE</th>
                              <th className="right">Forward PE</th>
                              <th className="right">P/B</th>
                              <th className="right">Net Margin</th>
                              <th className="right">Rev Growth</th>
                              <th className="right">ROE</th>
                              <th className="right">Debt/Eq</th>
                            </tr>
                          </thead>
                          <tbody>
                            {peers.map((p: any, i: number) => (
                              <tr key={i}
                                className={p.is_target ? 'itm-row clickable' : 'clickable'}
                                onClick={() => onSelectStock(p.symbol)}
                              >
                                <td><span className="sym">{p.symbol}</span></td>
                                <td style={{ color: '#aaa', fontSize: 12, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name ?? '-'}</td>
                                <td className="right">{p.price != null ? '$' + parseFloat(p.price).toFixed(2) : '-'}</td>
                                <td className="right">{fmt(p.market_cap)}</td>
                                <td className="right">{p.pe_ratio != null ? parseFloat(p.pe_ratio).toFixed(1) : '-'}</td>
                                <td className="right">{p.forward_pe != null ? parseFloat(p.forward_pe).toFixed(1) : '-'}</td>
                                <td className="right">{p.price_to_book != null ? parseFloat(p.price_to_book).toFixed(2) : '-'}</td>
                                <td className="right">{p.profit_margin != null ? (parseFloat(p.profit_margin) * 100).toFixed(1) + '%' : '-'}</td>
                                <td className={`right ${p.revenue_growth != null ? (parseFloat(p.revenue_growth) >= 0 ? 'positive' : 'negative') : ''}`}>
                                  {p.revenue_growth != null ? (parseFloat(p.revenue_growth) * 100).toFixed(1) + '%' : '-'}
                                </td>
                                <td className="right">{p.return_on_equity != null ? (parseFloat(p.return_on_equity) * 100).toFixed(1) + '%' : '-'}</td>
                                <td className="right">{p.debt_to_equity != null ? parseFloat(p.debt_to_equity).toFixed(2) : '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {(() => {
                          const t = peers.find((p: any) => p.is_target);
                          return t?.sector ? (
                            <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                              Filter basis: {t.sector}{t.industry ? ` · ${t.industry}` : ''} · similar market cap
                            </div>
                          ) : null;
                        })()}
                      </div>
              )}

              {/* SEC Filings */}
              {tab === 'filings' && (
                tabLoading
                  ? <div className="overall-loading" style={{ height: 80 }}>Loading...</div>
                  : filings.length === 0
                    ? <div className="muted" style={{ padding: '20px 0', fontSize: 13 }}>No SEC filings available</div>
                    : <div className="filing-list">
                        {filings.map((f: any, i: number) => {
                          const key = f.url || String(i);
                          const isOpen = expandedFiling === key;
                          const typeColor = f.type === '10-K' ? { bg: '#1a3a6c', fg: '#6c8fff' }
                            : f.type === '10-Q' ? { bg: '#1a4a2e', fg: '#00e676' }
                            : f.type === '8-K'  ? { bg: '#3a2a0a', fg: '#ffd740' }
                            : { bg: '#2a2d3a', fg: '#aaa' };

                          async function toggleFiling() {
                            if (isOpen) { setExpandedFiling(null); return; }
                            setExpandedFiling(key);
                            if (filingText[key] !== undefined) return; // already fetched
                            setFilingTextLoading(key);
                            try {
                              const r = await axios.get(`/api/market/filing-text?url=${encodeURIComponent(f.url)}`);
                              setFilingText(prev => ({ ...prev, [key]: r.data.text + (r.data.truncated ? '\n\n─── [Document truncated — showing first 80,000 characters] ───' : '') }));
                            } catch (err: any) {
                              const msg = err?.response?.data?.detail || err?.message || 'Unknown error';
                              setFilingText(prev => ({ ...prev, [key]: `⚠️ Unable to load filing content: ${msg}` }));
                            } finally {
                              setFilingTextLoading(null);
                            }
                          }

                          async function aiRead() {
                            if (filingAiLoading) return;
                            const text = filingText[key];
                            if (!text) return;
                            setFilingAiLoading(key);
                            try {
                              const res = await axios.post('/api/ai/chat', {
                                messages: [{ role: 'user', content: `Please analyze the following ${f.type} filing (${f.date}) for ${symbol}. Focus on: key business developments, financial highlights/risks, changes in management language, potential stock price impact, and key points investors should watch.\n\n---\n${text.slice(0, 60000)}` }],
                                context: `User is reading ${symbol}'s ${f.type} SEC filing dated ${f.date}.`,
                              });
                              setFilingAiResult(prev => ({ ...prev, [key]: res.data.content }));
                            } catch {
                              setFilingAiResult(prev => ({ ...prev, [key]: 'Analysis failed, please retry.' }));
                            } finally {
                              setFilingAiLoading(null);
                            }
                          }

                          return (
                            <div key={i} className="filing-item">
                              {/* Row header — click to expand */}
                              <div className="filing-row" onClick={toggleFiling}>
                                <span className="filing-badge" style={{ background: typeColor.bg, color: typeColor.fg }}>{f.type}</span>
                                <span className="filing-title">{f.title || f.type}</span>
                                <span className="filing-date">{f.date}</span>
                                <span className="filing-chevron">{isOpen ? '▲' : '▼'}</span>
                              </div>

                              {/* Expanded panel */}
                              {isOpen && (
                                <div className="filing-panel">
                                  {/* Action bar */}
                                  <div className="filing-panel-actions">
                                    <button
                                      className="filing-ai-btn"
                                      onClick={aiRead}
                                      disabled={!!filingAiLoading || !filingText[key]}
                                    >
                                      {filingAiLoading === key ? '⏳ Analyzing...' : '🤖 AI Interpret'}
                                    </button>
                                    {f.url && (
                                      <a href={f.url} target="_blank" rel="noreferrer" className="filing-ext-link">
                                        Open Original ↗
                                      </a>
                                    )}
                                  </div>

                                  {/* AI result */}
                                  {filingAiResult[key] && (
                                    <div className="filing-ai-result">
                                      <div className="filing-ai-label">🤖 AI Interpretation</div>
                                      <div className="filing-ai-body">{renderMd(filingAiResult[key])}</div>
                                    </div>
                                  )}

                                  {/* Raw text content */}
                                  <div className="filing-content">
                                    {filingTextLoading === key
                                      ? <div className="filing-content-loading">Loading filing content...</div>
                                      : <pre className="filing-text">{filingText[key]}</pre>
                                    }
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
              )}

              {/* Sentiment */}
              {tab === 'sentiment' && (
                <Suspense fallback={<div className="overall-loading" style={{ height: 80 }}>Loading sentiment module...</div>}>
                  <div className="deepdive-embed">
                    <div className="deepdive-embed-header">
                      <span className="sym">{symbol}</span>
                      <span className="muted" style={{ fontSize: 12, marginLeft: 10 }}>Sentiment Analysis · Reddit · X · News · 30 days</span>
                    </div>
                    <DeepDive initialTicker={symbol} days={30} />
                  </div>
                </Suspense>
              )}

              {/* News */}
              {tab === 'news' && (
                tabLoading
                  ? <div className="overall-loading" style={{ height: 80 }}>Loading...</div>
                  : <div className="news-tab-list">
                      {stockNews.map((item: any, i: number) => (
                        <a key={i} href={item.url} target="_blank" rel="noreferrer" className="news-tab-item">
                          <div className="news-tab-title">{item.title}</div>
                          <div className="news-tab-meta">
                            {item.source ?? item.publisher ?? ''}{' · '}
                            {item.date || item.published_utc ? new Date(item.date ?? item.published_utc).toLocaleDateString('en-US') : ''}
                          </div>
                        </a>
                      ))}
                      {stockNews.length === 0 && <div className="muted" style={{ fontSize: 13, padding: '10px 0' }}>No news available</div>}
                    </div>
              )}
            </div>
          </div>
        </>
      )}

      {!loading && !quote && (
        <div className="overall-error">Stock "{symbol}" not found. Please check the ticker symbol.</div>
      )}

      {showICMemo && (
        <Suspense fallback={null}>
          <ICMemo
            symbol={symbol}
            profile={profile}
            onClose={() => setShowICMemo(false)}
            analystName={analystName}
          />
        </Suspense>
      )}

      {showTearSheet && (
        <Suspense fallback={null}>
          <TearSheet
            symbol={symbol}
            quote={quote}
            profile={profile}
            metrics={metrics}
            onClose={() => setShowTearSheet(false)}
            analystName={analystName}
          />
        </Suspense>
      )}
    </div>
  );
}
