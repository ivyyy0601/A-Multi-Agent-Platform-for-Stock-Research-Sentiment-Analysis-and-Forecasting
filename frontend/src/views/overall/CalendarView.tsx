import { useEffect, useState } from 'react';
import axios from 'axios';

interface Props { onSelectStock: (sym: string) => void }

type CalTab = 'earnings' | 'ipo' | 'dividends';

function today()   { return new Date().toISOString().slice(0, 10); }
function in14()    { const d = new Date(); d.setDate(d.getDate() + 14); return d.toISOString().slice(0, 10); }
function in30()    { const d = new Date(); d.setDate(d.getDate() + 30); return d.toISOString().slice(0, 10); }
function weekday(s: string) {
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date(s + 'T12:00:00').getDay()];
}

export default function CalendarView({ onSelectStock }: Props) {
  const [tab,       setTab]       = useState<CalTab>('earnings');
  const [startDate, setStartDate] = useState(today());
  const [endDate,   setEndDate]   = useState(in14());
  const [earnings,  setEarnings]  = useState<any[]>([]);
  const [ipo,       setIpo]       = useState<any[]>([]);
  const [divs,      setDivs]      = useState<any[]>([]);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    const end = tab === 'ipo' ? in30() : in14();
    setEndDate(end);
    load(tab, startDate, end);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  function load(t: CalTab, start: string, end: string) {
    setLoading(true);
    const url = `/api/market/calendar/${t === 'dividends' ? 'dividends' : t}`;
    axios.get(url, { params: { start_date: start, end_date: end } })
      .then(r => {
        const data = Array.isArray(r.data) ? r.data : [];
        if (t === 'earnings')  setEarnings(data);
        if (t === 'ipo')       setIpo(data);
        if (t === 'dividends') setDivs(data);
      })
      .catch(() => {
        if (t === 'earnings')  setEarnings([]);
        if (t === 'ipo')       setIpo([]);
        if (t === 'dividends') setDivs([]);
      })
      .finally(() => setLoading(false));
  }

  function applyDates() { load(tab, startDate, endDate); }

  // Group by date
  function groupByDate(rows: any[], dateField: string) {
    const groups: Record<string, any[]> = {};
    rows.forEach(r => {
      const d = (r[dateField] ?? '').slice(0, 10);
      if (!groups[d]) groups[d] = [];
      groups[d].push(r);
    });
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }

  return (
    <div className="calendar-view">
      {/* Tab & Date controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div className="cal-tabs">
          {(['earnings', 'ipo', 'dividends'] as CalTab[]).map(t => (
            <button key={t} className={`cal-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {{ earnings: 'Earnings', ipo: 'IPO', dividends: 'Dividends' }[t]}
            </button>
          ))}
        </div>
        <span className="cal-date-lbl">From</span>
        <input type="date" className="cal-date-input" value={startDate} onChange={e => setStartDate(e.target.value)} />
        <span className="cal-date-lbl">To</span>
        <input type="date" className="cal-date-input" value={endDate}   onChange={e => setEndDate(e.target.value)} />
        <button className="screener-run-btn" onClick={applyDates} disabled={loading}>
          {loading ? 'Loading...' : 'Query'}
        </button>
      </div>

      {loading && <div className="overall-loading">Loading calendar data...</div>}

      {/* Earnings */}
      {!loading && tab === 'earnings' && (
        <div>
          {groupByDate(earnings, 'report_date').length === 0
            ? <div className="ov-card" style={{ padding: 30, textAlign: 'center', color: '#555' }}>No earnings in this period</div>
            : groupByDate(earnings, 'report_date').map(([date, rows]) => (
                <div key={date} className="ov-card" style={{ marginBottom: 12 }}>
                  <div className="ov-card-title">
                    {date} &nbsp;{weekday(date)}
                  </div>
                  <table className="ov-table">
                    <thead>
                      <tr>
                        <th>Ticker</th>
                        <th>Company</th>
                        <th className="right">Est. EPS</th>
                        <th className="right">Prior EPS</th>
                        <th className="right">Est. Revenue</th>
                        <th className="right">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r: any, i: number) => {
                        const sym      = r.symbol ?? r.ticker ?? '';
                        const epsEst   = parseFloat(r.eps_consensus ?? r.estimated_eps ?? r.eps_estimate ?? NaN);
                        const epsPrev  = parseFloat(r.eps_previous ?? r.actual_eps_prior ?? r.eps_prior ?? NaN);
                        const revEst   = parseFloat(r.revenue_consensus ?? r.revenue_estimated ?? r.estimated_revenue ?? NaN);
                        const timing   = r.reporting_time ?? r.time ?? '';
                        return (
                          <tr key={sym || i} className="clickable" onClick={() => sym && onSelectStock(sym)}>
                            <td><span className="sym">{sym}</span></td>
                            <td style={{ color: '#aaa', fontSize: 12 }}>{r.name ?? r.company ?? '-'}</td>
                            <td className="right">{isNaN(epsEst) ? '-' : '$' + epsEst.toFixed(2)}</td>
                            <td className="right muted">{isNaN(epsPrev) ? '-' : '$' + epsPrev.toFixed(2)}</td>
                            <td className="right muted">
                              {isNaN(revEst) ? '-' : (revEst >= 1e9 ? (revEst / 1e9).toFixed(2) + 'B' : (revEst / 1e6).toFixed(0) + 'M')}
                            </td>
                            <td className="right" style={{ fontSize: 11, color: '#666' }}>
                              {timing.toLowerCase().includes('before') ? 'Pre-market' :
                               timing.toLowerCase().includes('after')  ? 'After-hours' : '-'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ))}
        </div>
      )}

      {/* IPO */}
      {!loading && tab === 'ipo' && (
        <div className="ov-card">
          <table className="ov-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th className="right">IPO Price</th>
                <th className="right">Shares</th>
                <th className="right">Raise</th>
                <th className="right">IPO Date</th>
                <th className="right">Exchange</th>
              </tr>
            </thead>
            <tbody>
              {ipo.map((r: any, i: number) => {
                const sym    = r.symbol ?? r.ticker ?? '';
                const price  = parseFloat(r.ipo_price ?? r.price ?? NaN);
                const shares = parseFloat(r.shares ?? r.shares_offered ?? NaN);
                const raise  = parseFloat(r.total_offer_size ?? r.proceeds ?? NaN);
                return (
                  <tr key={sym || i} className="clickable" onClick={() => sym && onSelectStock(sym)}>
                    <td><span className="sym">{sym || '-'}</span></td>
                    <td style={{ color: '#aaa', fontSize: 12 }}>{r.name ?? r.company ?? '-'}</td>
                    <td className="right">{isNaN(price)  ? r.price_range ?? '-' : '$' + price.toFixed(2)}</td>
                    <td className="right muted">{isNaN(shares) ? '-' : (shares >= 1e6 ? (shares / 1e6).toFixed(1) + 'M' : shares.toLocaleString())}</td>
                    <td className="right muted">{isNaN(raise)  ? '-' : (raise  >= 1e9 ? (raise  / 1e9).toFixed(2) + 'B' : (raise / 1e6).toFixed(0) + 'M')}</td>
                    <td className="right muted">{(r.ipo_date ?? r.date ?? '').slice(0, 10)}</td>
                    <td className="right" style={{ fontSize: 11, color: '#666' }}>{r.exchange ?? r.market ?? '-'}</td>
                  </tr>
                );
              })}
              {ipo.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 30, color: '#555' }}>No IPOs in this period</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Dividends */}
      {!loading && tab === 'dividends' && (
        <div>
          {groupByDate(divs, 'ex_dividend_date').length === 0
            ? <div className="ov-card" style={{ padding: 30, textAlign: 'center', color: '#555' }}>No dividends in this period</div>
            : groupByDate(divs, 'ex_dividend_date').map(([date, rows]) => (
                <div key={date} className="ov-card" style={{ marginBottom: 12 }}>
                  <div className="ov-card-title">Ex-Div Date {date} &nbsp;{weekday(date)}</div>
                  <table className="ov-table">
                    <thead>
                      <tr>
                        <th>Ticker</th>
                        <th>Company</th>
                        <th className="right">Dividend</th>
                        <th className="right">Annual Yield</th>
                        <th className="right">Pay Date</th>
                        <th className="right">Record Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r: any, i: number) => {
                        const sym  = r.symbol ?? r.ticker ?? '';
                        const div  = parseFloat(r.cash_dividend_rate ?? r.amount ?? r.dividend ?? NaN);
                        const yld  = parseFloat(r.dividend_yield ?? NaN);
                        return (
                          <tr key={sym || i} className="clickable" onClick={() => sym && onSelectStock(sym)}>
                            <td><span className="sym">{sym}</span></td>
                            <td style={{ color: '#aaa', fontSize: 12 }}>{r.name ?? r.company ?? '-'}</td>
                            <td className="right positive">{isNaN(div) ? '-' : '$' + div.toFixed(4)}</td>
                            <td className="right">{isNaN(yld) ? '-' : (yld * 100).toFixed(2) + '%'}</td>
                            <td className="right muted">{(r.payment_date ?? r.pay_date ?? '').slice(0, 10) || '-'}</td>
                            <td className="right muted">{(r.record_date ?? '').slice(0, 10) || '-'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ))}
        </div>
      )}
    </div>
  );
}
