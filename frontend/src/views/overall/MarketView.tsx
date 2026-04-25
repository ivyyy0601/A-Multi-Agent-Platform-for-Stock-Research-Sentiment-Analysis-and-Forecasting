import { useEffect, useState } from 'react';
import axios from 'axios';

interface Props { onSelectStock: (sym: string) => void }

const INDEX_META: Record<string, { name: string; color: string }> = {
  SPY: { name: 'S&P 500',      color: '#6c8fff' },
  QQQ: { name: 'Nasdaq 100',   color: '#a78bfa' },
  DIA: { name: 'Dow Jones',    color: '#34d399' },
};

function pct(n: any) { const v = parseFloat(n); if (isNaN(v)) return '-'; return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
function price(n: any) { const v = parseFloat(n); return isNaN(v) ? '-' : '$' + v.toFixed(2); }
function vol(n: any) { const v = parseFloat(n); if (isNaN(v)) return '-'; if (v >= 1e9) return (v/1e9).toFixed(1)+'B'; if (v >= 1e6) return (v/1e6).toFixed(1)+'M'; if (v >= 1e3) return (v/1e3).toFixed(1)+'K'; return String(v); }

type ListKey = 'gainers' | 'losers' | 'active';

export default function MarketView({ onSelectStock }: Props) {
  const [indices,  setIndices]  = useState<any[]>([]);
  const [gainers,  setGainers]  = useState<any[]>([]);
  const [losers,   setLosers]   = useState<any[]>([]);
  const [active,   setActive]   = useState<any[]>([]);
  const [news,     setNews]     = useState<any[]>([]);
  const [earnings, setEarnings] = useState<any[]>([]);
  const [list,     setList]     = useState<ListKey>('gainers');
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState('');

  useEffect(() => {
    setLoading(true);
    Promise.all([
      axios.get('/api/market/indices').catch(() => null),
      axios.get('/api/market/gainers').catch(() => null),
      axios.get('/api/market/losers').catch(() => null),
      axios.get('/api/market/active').catch(() => null),
      axios.get('/api/market/news').catch(() => null),
      axios.get('/api/market/calendar/earnings').catch(() => null),
    ]).then(([idx, g, l, a, n, e]) => {
      if (!idx && !g && !l) setError('Unable to fetch market data. Please ensure the backend is running.');
      setIndices(Array.isArray(idx?.data) ? idx.data : []);
      setGainers(Array.isArray(g?.data)   ? g.data.slice(0, 10) : []);
      setLosers (Array.isArray(l?.data)   ? l.data.slice(0, 10) : []);
      setActive (Array.isArray(a?.data)   ? a.data.slice(0, 10) : []);
      setNews   (Array.isArray(n?.data)   ? n.data.slice(0, 20) : []);
      setEarnings(Array.isArray(e?.data)  ? e.data.slice(0, 12) : []);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="overall-loading">Loading market data...</div>;
  if (error)   return <div className="overall-error">{error}</div>;

  const listData = list === 'gainers' ? gainers : list === 'losers' ? losers : active;

  return (
    <div className="dashboard-view">

      {/* Row 1: Index widgets */}
      <div className="dashboard-indices">
        {(indices.length > 0 ? indices : [{ symbol: 'SPY' }, { symbol: 'QQQ' }, { symbol: 'DIA' }]).map((idx: any) => {
          const sym  = idx.symbol ?? '';
          const meta = INDEX_META[sym] ?? { name: sym, color: '#6c8fff' };
          const chg  = parseFloat(idx.change_percent ?? 0);
          const isUp = chg >= 0;
          return (
            <div key={sym} className="index-widget" onClick={() => onSelectStock(sym)}
              style={{ borderTop: `3px solid ${meta.color}` }}>
              <div className="iw-name">{meta.name}</div>
              <div className="iw-price">{price(idx.price)}</div>
              <div className={`iw-chg ${isUp ? 'positive' : 'negative'}`}>{pct(chg)}</div>
              <div className="iw-extra muted">
                Vol {vol(idx.volume)} · 52W {price(idx.year_low)}–{price(idx.year_high)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Row 2: Movers + News */}
      <div className="dashboard-row2">

        {/* Movers widget */}
        <div className="dash-widget">
          <div className="dash-widget-header">
            <span className="dash-widget-title">Market Movers</span>
            <div className="dash-tab-group">
              {(['gainers','losers','active'] as ListKey[]).map(k => (
                <button key={k} className={`dash-tab ${list === k ? 'active' : ''}`} onClick={() => setList(k)}>
                  {{ gainers: 'Top Gainers', losers: 'Top Losers', active: 'Most Active' }[k]}
                </button>
              ))}
            </div>
          </div>
          <table className="ov-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="right">Price</th>
                <th className="right">Chg%</th>
                {list === 'active' && <th className="right">Volume</th>}
              </tr>
            </thead>
            <tbody>
              {listData.map((s: any, i: number) => {
                const sym = s.symbol ?? s.ticker ?? '';
                const chg = parseFloat(s.change_percent ?? s.percent_change ?? 0);
                return (
                  <tr key={sym || i} className="clickable" onClick={() => onSelectStock(sym)}>
                    <td>
                      <span className="sym">{sym}</span>
                      <br /><span className="muted" style={{ fontSize: 11 }}>{s.name ?? ''}</span>
                    </td>
                    <td className="right">{price(s.price ?? s.last_price)}</td>
                    <td className={`right ${chg >= 0 ? 'positive' : 'negative'}`}>{pct(chg)}</td>
                    {list === 'active' && <td className="right">{vol(s.volume)}</td>}
                  </tr>
                );
              })}
              {listData.length === 0 && (
                <tr><td colSpan={4} style={{ textAlign: 'center', padding: 20, color: '#555' }}>No data available</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* News widget */}
        <div className="dash-widget">
          <div className="dash-widget-header">
            <span className="dash-widget-title">Market News</span>
          </div>
          <div className="news-feed">
            {news.map((item: any, i: number) => (
              <a key={i} href={item.url} target="_blank" rel="noreferrer" className="news-feed-item">
                <div className="nfi-title">{item.title}</div>
                <div className="nfi-meta">
                  {item.source ?? item.publisher ?? ''}
                  {(item.date || item.published_utc) ? ' · ' + new Date(item.date ?? item.published_utc).toLocaleDateString('en-US') : ''}
                </div>
              </a>
            ))}
            {news.length === 0 && <div style={{ padding: 20, color: '#555', fontSize: 13 }}>No news available</div>}
          </div>
        </div>
      </div>

      {/* Row 3: Upcoming Earnings */}
      {earnings.length > 0 && (
        <div className="dash-widget">
          <div className="dash-widget-header">
            <span className="dash-widget-title">Upcoming Earnings</span>
          </div>
          <div className="earnings-grid">
            {earnings.map((e: any, i: number) => (
              <div key={i} className="earnings-chip" onClick={() => onSelectStock(e.symbol ?? '')}>
                <div className="ec-sym">{e.symbol ?? e.name ?? '-'}</div>
                <div className="ec-date muted">{(e.report_date ?? e.date ?? '').slice(0, 10)}</div>
                {e.eps_estimate != null && (
                  <div className="ec-eps muted">Est. EPS ${parseFloat(e.eps_estimate).toFixed(2)}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
