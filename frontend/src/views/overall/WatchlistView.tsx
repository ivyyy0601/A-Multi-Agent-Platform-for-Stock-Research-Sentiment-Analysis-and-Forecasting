import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

interface Props {
  watchlist: string[];
  onAdd: (sym: string) => void;
  onRemove: (sym: string) => void;
  onSelectStock: (sym: string) => void;
  onGoChart: (sym: string) => void;
}

type SignalType = 'price_up' | 'price_down' | 'volume' | 'earnings';

interface Signal {
  id: string;
  symbol: string;
  type: SignalType;
  title: string;
  detail: string;
  severity: 'high' | 'medium' | 'low';
}

interface QuoteData {
  price: number;
  changePct: number;
  volume: number;
  avgVolume: number;
  marketCap: number;
  yearHigh: number;
  yearLow: number;
}

function fmt(n: any): string {
  const v = parseFloat(n);
  if (isNaN(v)) return '-';
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(1) + 'T';
  if (abs >= 1e9)  return (v / 1e9).toFixed(1)  + 'B';
  if (abs >= 1e6)  return (v / 1e6).toFixed(1)  + 'M';
  if (abs >= 1e3)  return (v / 1e3).toFixed(1)  + 'K';
  return v.toFixed(2);
}

const SEV_COLOR = { high: '#ff4d4d', medium: '#ffd740', low: '#6c8fff' };
const SEV_BG    = { high: '#2a0000', medium: '#2a1a00', low: '#0d1530' };
const SEV_ORDER = { high: 0, medium: 1, low: 2 };

export default function WatchlistView({ watchlist, onAdd, onRemove, onSelectStock, onGoChart }: Props) {
  const [input,       setInput]       = useState('');
  const [quotes,      setQuotes]      = useState<Record<string, QuoteData>>({});
  const [loading,     setLoading]     = useState(false);
  const [signals,     setSignals]     = useState<Signal[]>([]);
  const [earningsMap, setEarningsMap] = useState<Record<string, { date: string; epsEst: number }>>({});
  const [lastUpdate,  setLastUpdate]  = useState<Date | null>(null);

  const buildSignals = useCallback((
    qs: Record<string, QuoteData>,
    em: Record<string, { date: string; epsEst: number }>,
  ) => {
    const sigs: Signal[] = [];
    const today = new Date();

    for (const sym of watchlist) {
      const q = qs[sym];
      if (q) {
        const pct = q.changePct;

        // Price signal
        if (Math.abs(pct) >= 3) {
          sigs.push({
            id: `${sym}_price`,
            symbol: sym,
            type: pct > 0 ? 'price_up' : 'price_down',
            title: `${pct > 0 ? '📈' : '📉'} ${sym} ${pct > 0 ? 'surged' : 'dropped'} ${pct > 0 ? '+' : ''}${pct.toFixed(1)}% today`,
            detail: `Current $${q.price.toFixed(2)} · 52W: $${q.yearLow.toFixed(0)}–$${q.yearHigh.toFixed(0)}`,
            severity: Math.abs(pct) >= 6 ? 'high' : 'medium',
          });
        }

        // Volume signal
        if (q.avgVolume > 0) {
          const ratio = q.volume / q.avgVolume;
          if (ratio >= 1.5) {
            sigs.push({
              id: `${sym}_vol`,
              symbol: sym,
              type: 'volume',
              title: `📊 ${sym} unusual volume ${ratio.toFixed(1)}x`,
              detail: `Today ${fmt(q.volume)} · 10d avg ${fmt(q.avgVolume)}`,
              severity: ratio >= 3 ? 'high' : ratio >= 2 ? 'medium' : 'low',
            });
          }
        }
      }

      // Earnings signal
      const e = em[sym];
      if (e) {
        const daysUntil = Math.ceil(
          (new Date(e.date + 'T12:00:00').getTime() - today.getTime()) / 86400000,
        );
        if (daysUntil >= 0) {
          sigs.push({
            id: `${sym}_earnings`,
            symbol: sym,
            type: 'earnings',
            title: `📅 ${sym} earnings ${daysUntil === 0 ? 'today' : daysUntil === 1 ? 'tomorrow' : `in ${daysUntil} days`}`,
            detail: `${e.date}${!isNaN(e.epsEst) ? ` · Est. EPS $${e.epsEst.toFixed(2)}` : ''}`,
            severity: daysUntil <= 1 ? 'high' : daysUntil <= 4 ? 'medium' : 'low',
          });
        }
      }
    }

    sigs.sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
    return sigs;
  }, [watchlist]);

  const fetchAll = useCallback(async () => {
    if (watchlist.length === 0) { setSignals([]); return; }
    setLoading(true);

    // Fetch quotes in parallel
    const results = await Promise.all(
      watchlist.map(async sym => {
        try {
          const r = await axios.get(`/api/market/stock/${sym}/quote`);
          const q = Array.isArray(r.data) ? r.data[0] : r.data;
          return {
            sym, data: {
              price:     parseFloat(q.price ?? 0),
              changePct: parseFloat(q.change_percent ?? 0),
              volume:    parseFloat(q.volume ?? 0),
              avgVolume: parseFloat(q.volume_average_10d ?? q.volume_average ?? 0),
              marketCap: parseFloat(q.market_cap ?? 0),
              yearHigh:  parseFloat(q.year_high ?? 0),
              yearLow:   parseFloat(q.year_low ?? 0),
            } as QuoteData,
          };
        } catch { return { sym, data: null }; }
      }),
    );

    const newQuotes: Record<string, QuoteData> = {};
    for (const { sym, data } of results) {
      if (data) newQuotes[sym] = data;
    }
    setQuotes(newQuotes);

    // Fetch upcoming earnings (next 14 days)
    let newEarnings: Record<string, { date: string; epsEst: number }> = {};
    try {
      const today14 = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);
      const todayStr = new Date().toISOString().slice(0, 10);
      const er = await axios.get(`/api/market/calendar/earnings`, {
        params: { start_date: todayStr, end_date: today14 },
      });
      const earnings = Array.isArray(er.data) ? er.data : [];
      for (const e of earnings) {
        const sym = e.symbol ?? '';
        if (watchlist.includes(sym)) {
          newEarnings[sym] = { date: e.report_date, epsEst: parseFloat(e.eps_consensus ?? NaN) };
        }
      }
      setEarningsMap(newEarnings);
    } catch {}

    setSignals(buildSignals(newQuotes, newEarnings));
    setLastUpdate(new Date());
    setLoading(false);
  }, [watchlist, buildSignals]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  function addStock() {
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    if (!watchlist.includes(sym)) onAdd(sym);
    setInput('');
  }

  return (
    <div className="watchlist-view">
      {/* Add row */}
      <div className="wl-toolbar">
        <input
          className="wl-add-input"
          placeholder="Enter ticker, e.g. NVDA..."
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && addStock()}
        />
        <button className="wl-add-btn" onClick={addStock}>+ Add</button>
        {watchlist.length > 0 && (
          <button className="wl-refresh-btn" onClick={fetchAll} disabled={loading}>
            {loading ? 'Updating...' : '↻ Refresh'}
          </button>
        )}
        {lastUpdate && (
          <span className="wl-update-time">
            Updated {lastUpdate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
        {signals.length > 0 && (
          <span className="wl-signal-badge">{signals.filter(s => s.severity === 'high').length || signals.length} signal(s)</span>
        )}
      </div>

      {watchlist.length === 0 ? (
        <div className="wl-empty">
          <div className="wl-empty-icon">⭐</div>
          <div className="wl-empty-text">Watchlist is empty</div>
          <div className="wl-empty-sub">Enter a ticker to start tracking · You can also click ⭐ on the Data page to quickly add</div>
        </div>
      ) : (
        <div className="wl-body">

          {/* Signal Feed */}
          {signals.length > 0 && (
            <div className="wl-section">
              <div className="wl-section-title">⚡ Signals</div>
              <div className="wl-signals">
                {signals.map(sig => (
                  <div
                    key={sig.id}
                    className="wl-signal-card"
                    style={{ borderColor: SEV_COLOR[sig.severity] + '55', background: SEV_BG[sig.severity] }}
                    onClick={() => onSelectStock(sig.symbol)}
                  >
                    <div className="wl-signal-dot" style={{ background: SEV_COLOR[sig.severity] }} />
                    <div className="wl-signal-body">
                      <div className="wl-signal-title">{sig.title}</div>
                      <div className="wl-signal-detail">{sig.detail}</div>
                    </div>
                    <span className="wl-signal-sym">{sig.symbol} →</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Watchlist Table */}
          <div className="wl-section">
            <div className="wl-section-title">📋 Portfolio Monitor · {watchlist.length} stocks</div>
            <div style={{ overflowX: 'auto' }}>
              <table className="ov-table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th className="right">Price</th>
                    <th className="right">Today</th>
                    <th className="right">Volume</th>
                    <th className="right">Vol Ratio</th>
                    <th className="right">Mkt Cap</th>
                    <th className="right">52W Range</th>
                    <th className="right">Earnings</th>
                    <th className="right">Chart</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {watchlist.map(sym => {
                    const q   = quotes[sym];
                    const e   = earningsMap[sym];
                    const chg = q?.changePct ?? 0;
                    const volRatio = q && q.avgVolume > 0 ? q.volume / q.avgVolume : null;
                    const hasHighSig = signals.some(s => s.symbol === sym && s.severity === 'high');
                    return (
                      <tr key={sym} className="clickable" onClick={() => onSelectStock(sym)}>
                        <td>
                          <span className="sym">{sym}</span>
                          {hasHighSig && <span style={{ marginLeft: 5, fontSize: 9, color: '#ff4d4d' }}>●</span>}
                        </td>
                        <td className="right">
                          {q ? `$${q.price.toFixed(2)}` : loading ? <span className="wl-loading-dot">···</span> : '-'}
                        </td>
                        <td className={`right ${chg >= 0 ? 'positive' : 'negative'}`}>
                          {q ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '-'}
                        </td>
                        <td className="right">{q ? fmt(q.volume) : '-'}</td>
                        <td className="right" style={{
                          color: volRatio === null ? '#666'
                            : volRatio >= 2.5 ? '#ff4d4d'
                            : volRatio >= 2   ? '#ffd740'
                            : volRatio >= 1.5 ? '#ffaa00'
                            : '#888',
                          fontWeight: volRatio && volRatio >= 2 ? 600 : 400,
                        }}>
                          {volRatio ? `${volRatio.toFixed(1)}x` : '-'}
                        </td>
                        <td className="right">{q ? fmt(q.marketCap) : '-'}</td>
                        <td className="right muted" style={{ fontSize: 11 }}>
                          {q ? `$${q.yearLow.toFixed(0)}–$${q.yearHigh.toFixed(0)}` : '-'}
                        </td>
                        <td className="right" style={{ fontSize: 11 }}>
                          {e ? <span style={{ color: '#ffd740', fontWeight: 600 }}>{e.date}</span> : <span className="muted">-</span>}
                        </td>
                        <td className="right">
                          <button
                            className="wl-chart-btn"
                            onClick={ev => { ev.stopPropagation(); onGoChart(sym); }}
                            title="View chart"
                          >📈</button>
                        </td>
                        <td>
                          <button
                            className="wl-remove-btn"
                            onClick={ev => { ev.stopPropagation(); onRemove(sym); }}
                            title="Remove"
                          >✕</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
