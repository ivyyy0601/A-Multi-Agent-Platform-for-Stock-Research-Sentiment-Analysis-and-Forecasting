import { useState } from 'react';
import axios from 'axios';

interface Props { onSelectStock: (sym: string) => void }

const SECTORS = [
  '', 'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
  'Communication Services', 'Industrials', 'Consumer Defensive', 'Energy',
  'Basic Materials', 'Real Estate', 'Utilities',
];

function fmt(n: any): string {
  const v = parseFloat(n);
  if (isNaN(v) || v === 0) return '-';
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(1) + 'T';
  if (abs >= 1e9)  return (v / 1e9).toFixed(1)  + 'B';
  if (abs >= 1e6)  return (v / 1e6).toFixed(1)  + 'M';
  return v.toFixed(2);
}

export default function ScreenerView({ onSelectStock }: Props) {
  const [sector,     setSector]     = useState('');
  const [priceMin,   setPriceMin]   = useState('');
  const [priceMax,   setPriceMax]   = useState('');
  const [mktcapMin,  setMktcapMin]  = useState('');
  const [volumeMin,  setVolumeMin]  = useState('');
  const [betaMin,    setBetaMin]    = useState('');
  const [betaMax,    setBetaMax]    = useState('');
  const [results,    setResults]    = useState<any[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState('');
  const [ran,        setRan]        = useState(false);
  const [sortKey,    setSortKey]    = useState('');
  const [sortDir,    setSortDir]    = useState<1 | -1>(1);

  // NL Screener
  const [nlQuery,      setNlQuery]      = useState('');
  const [nlLoading,    setNlLoading]    = useState(false);
  const [nlExplanation, setNlExplanation] = useState('');

  async function run() {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, any> = { limit: 200 };
      if (sector)    params.sector     = sector;
      if (priceMin)  params.price_min  = parseFloat(priceMin);
      if (priceMax)  params.price_max  = parseFloat(priceMax);
      if (mktcapMin) params.mktcap_min = parseFloat(mktcapMin) * 1e6;
      if (volumeMin) params.volume_min = parseInt(volumeMin);
      if (betaMin)   params.beta_min   = parseFloat(betaMin);
      if (betaMax)   params.beta_max   = parseFloat(betaMax);
      const r = await axios.get('/api/market/screener', { params });
      setResults(Array.isArray(r.data) ? r.data : []);
      setRan(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Screening request failed');
    }
    setLoading(false);
  }

  function reset() {
    setSector(''); setPriceMin(''); setPriceMax('');
    setMktcapMin(''); setVolumeMin(''); setBetaMin(''); setBetaMax('');
    setResults([]); setRan(false); setError(''); setNlExplanation('');
  }

  async function runNL() {
    if (!nlQuery.trim() || nlLoading) return;
    setNlLoading(true);
    setError('');
    setNlExplanation('');
    try {
      const res = await axios.post('/api/ai/chat', {
        messages: [{
          role: 'user',
          content: `Parse this stock screening query into structured filters. Return ONLY a JSON object (no markdown, no explanation outside JSON).

Available filters:
- sector: one of ["technology","healthcare","financial","consumer_cyclical","consumer_defensive","communication_services","industrials","energy","materials","real_estate","utilities"] or omit if not specified
- price_min: number (USD)
- price_max: number (USD)
- mktcap_min: number (USD, e.g. 1000000000 for $1B, 50000000000 for $50B)
- mktcap_max: number (USD)
- volume_min: number
- beta_min: number
- beta_max: number
- explanation: string (1 sentence in English describing what you understood)

Query: "${nlQuery}"`,
        }],
        context: 'You are a stock screening assistant. Parse natural language queries into structured JSON filter parameters. Always respond with valid JSON only.',
      });

      let parsed: any = {};
      try {
        const text = res.data.content.trim();
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        parsed = JSON.parse(jsonMatch ? jsonMatch[0] : text);
      } catch {
        setError('AI could not parse the query, please rephrase');
        setNlLoading(false);
        return;
      }

      // Apply parsed filters to UI
      if (parsed.sector)     setSector(parsed.sector);
      if (parsed.price_min)  setPriceMin(String(parsed.price_min));
      if (parsed.price_max)  setPriceMax(String(parsed.price_max));
      if (parsed.mktcap_min) setMktcapMin(String(Math.round(parsed.mktcap_min / 1e6)));
      if (parsed.volume_min) setVolumeMin(String(parsed.volume_min));
      if (parsed.beta_min)   setBetaMin(String(parsed.beta_min));
      if (parsed.beta_max)   setBetaMax(String(parsed.beta_max));
      if (parsed.explanation) setNlExplanation(parsed.explanation);

      // Auto-run screener with parsed params
      setLoading(true);
      const params: Record<string, any> = { limit: 200 };
      if (parsed.sector)     params.sector     = parsed.sector;
      if (parsed.price_min)  params.price_min  = parsed.price_min;
      if (parsed.price_max)  params.price_max  = parsed.price_max;
      if (parsed.mktcap_min) params.mktcap_min = parsed.mktcap_min;
      if (parsed.mktcap_max) params.mktcap_max = parsed.mktcap_max;
      if (parsed.volume_min) params.volume_min = parsed.volume_min;
      if (parsed.beta_min)   params.beta_min   = parsed.beta_min;
      if (parsed.beta_max)   params.beta_max   = parsed.beta_max;
      const r = await axios.get('/api/market/screener', { params });
      setResults(Array.isArray(r.data) ? r.data : []);
      setRan(true);
      setLoading(false);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'NL screening failed');
      setLoading(false);
    }
    setNlLoading(false);
  }

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir(d => d === 1 ? -1 : 1);
    else { setSortKey(key); setSortDir(-1); }
  }

  const sorted = [...results].sort((a, b) => {
    if (!sortKey) return 0;
    const av = parseFloat(a[sortKey] ?? 0);
    const bv = parseFloat(b[sortKey] ?? 0);
    return (av - bv) * sortDir;
  });

  const SortTh = ({ k, label }: { k: string; label: string }) => (
    <th className="right" style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => toggleSort(k)}>
      {label}{sortKey === k ? (sortDir === -1 ? ' ↓' : ' ↑') : ''}
    </th>
  );

  return (
    <div className="screener-view">

      {/* NL Screener */}
      <div className="nl-screener-bar">
        <span className="nl-screener-icon">✨</span>
        <input
          className="nl-screener-input"
          placeholder='Describe in plain English, e.g. "tech stocks under $50B market cap with beta below 1.5"'
          value={nlQuery}
          onChange={e => setNlQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && runNL()}
        />
        <button className="nl-screener-btn" onClick={runNL} disabled={nlLoading || !nlQuery.trim()}>
          {nlLoading ? 'Parsing...' : 'AI Screen'}
        </button>
      </div>
      {nlExplanation && (
        <div className="nl-explanation">
          💡 AI interpreted as: {nlExplanation}
        </div>
      )}

      {/* Filters */}
      <div className="screener-filters">
        <div className="filter-group">
          <label className="filter-label">Sector</label>
          <select className="filter-select" value={sector} onChange={e => setSector(e.target.value)}>
            <option value="">All</option>
            {SECTORS.slice(1).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Min Price</label>
          <input className="filter-input" type="number" placeholder="0" value={priceMin} onChange={e => setPriceMin(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">Max Price</label>
          <input className="filter-input" type="number" placeholder="∞" value={priceMax} onChange={e => setPriceMax(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">Min Market Cap (M)</label>
          <input className="filter-input" type="number" placeholder="e.g. 1000" value={mktcapMin} onChange={e => setMktcapMin(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">Min Volume</label>
          <input className="filter-input" type="number" placeholder="e.g. 500000" value={volumeMin} onChange={e => setVolumeMin(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">Min Beta</label>
          <input className="filter-input" type="number" step="0.1" placeholder="e.g. 0.5" value={betaMin} onChange={e => setBetaMin(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">Max Beta</label>
          <input className="filter-input" type="number" step="0.1" placeholder="e.g. 2.0" value={betaMax} onChange={e => setBetaMax(e.target.value)} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="screener-run-btn" onClick={run} disabled={loading}>
            {loading ? 'Screening...' : 'Screen'}
          </button>
          <button className="screener-run-btn" onClick={reset}
            style={{ background: 'none', border: '1px solid #2a2d3a', color: '#888' }}>
            Reset
          </button>
        </div>
      </div>

      {error && <div className="overall-error">{error}</div>}

      {ran && (
        <div className="ov-card">
          <div className="screener-count">Found <strong>{results.length}</strong> stocks (click column headers to sort)</div>
          <div style={{ overflowX: 'auto' }}>
            <table className="ov-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Name</th>
                  <th>Sector</th>
                  <SortTh k="price"          label="Price" />
                  <SortTh k="change_percent" label="Chg%" />
                  <SortTh k="market_cap"     label="Mkt Cap" />
                  <SortTh k="volume"         label="Volume" />
                  <SortTh k="pe_ratio"       label="PE" />
                  <SortTh k="beta"           label="Beta" />
                </tr>
              </thead>
              <tbody>
                {sorted.map((s: any, i: number) => {
                  const sym = s.symbol ?? s.ticker ?? '';
                  const chg = parseFloat(s.change_percent ?? s.percent_change ?? 0);
                  return (
                    <tr key={sym || i} className="clickable" onClick={() => onSelectStock(sym)}>
                      <td><span className="sym">{sym}</span></td>
                      <td style={{ color: '#aaa', fontSize: 12, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s.name ?? s.company ?? '-'}
                      </td>
                      <td style={{ color: '#666', fontSize: 12 }}>{s.sector ?? '-'}</td>
                      <td className="right">${parseFloat(s.price ?? 0).toFixed(2)}</td>
                      <td className={`right ${chg >= 0 ? 'positive' : 'negative'}`}>
                        {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                      </td>
                      <td className="right">{fmt(s.market_cap)}</td>
                      <td className="right">{fmt(s.volume)}</td>
                      <td className="right">{s.pe_ratio != null ? parseFloat(s.pe_ratio).toFixed(1) : '-'}</td>
                      <td className="right">{s.beta != null ? parseFloat(s.beta).toFixed(2) : '-'}</td>
                    </tr>
                  );
                })}
                {sorted.length === 0 && (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 30, color: '#555' }}>No stocks match the criteria</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
