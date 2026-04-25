import { useEffect, useState } from 'react';
import axios from 'axios';

interface Props { symbol?: string }

function fmt(n: any, dec = 2) { if (n == null) return '-'; const v = parseFloat(n); return isNaN(v) ? '-' : v.toFixed(dec); }
function price(n: any) { const v = parseFloat(n); return isNaN(v) ? '-' : '$' + v.toFixed(2); }
function vol(n: any) { const v = parseFloat(n); if (isNaN(v)) return '-'; if (v >= 1e6) return (v/1e6).toFixed(1)+'M'; if (v >= 1e3) return (v/1e3).toFixed(0)+'K'; return String(v); }

type OptionType = 'call' | 'put';

export default function OptionsView({ symbol: initSym = 'AAPL' }: Props) {
  const [input,      setInput]      = useState(initSym);
  const [symbol,     setSymbol]     = useState(initSym);

  useEffect(() => {
    setInput(initSym);
    setSymbol(initSym);
    setExpiration('');
  }, [initSym]);
  const [optType,    setOptType]    = useState<OptionType>('call');
  const [expiration, setExpiration] = useState('');
  const [data,       setData]       = useState<any[]>([]);
  const [expirations, setExpirations] = useState<string[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState('');

  // Fetch calls to get available expirations
  useEffect(() => {
    setLoading(true);
    setError('');
    axios.get(`/api/market/stock/${symbol}/options?option_type=call`)
      .then(r => {
        const rows: any[] = Array.isArray(r.data) ? r.data : [];
        const exps = [...new Set(rows.map((d: any) => d.expiration).filter(Boolean))].sort();
        setExpirations(exps as string[]);
        if (exps.length && !expiration) setExpiration(exps[0] as string);
        setData(rows);
      })
      .catch(e => setError(e?.response?.data?.detail ?? '无法获取期权数据'))
      .finally(() => setLoading(false));
  }, [symbol]);

  // Refetch when type or expiration changes
  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    const params = new URLSearchParams({ option_type: optType });
    if (expiration) params.set('expiration', expiration);
    axios.get(`/api/market/stock/${symbol}/options?${params}`)
      .then(r => setData(Array.isArray(r.data) ? r.data : []))
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [symbol, optType, expiration]);

  function search() { const s = input.trim().toUpperCase(); if (s) { setSymbol(s); setExpiration(''); } }

  const filtered = expiration ? data.filter(d => d.expiration === expiration) : data;

  return (
    <div className="options-view">
      <div className="options-toolbar">
        <div className="charting-search">
          <input
            className="stock-search-input"
            value={input}
            placeholder="股票代码 AAPL"
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
          <button className="stock-search-btn" onClick={search}>查询</button>
        </div>

        <div className="options-controls">
          <div className="opt-type-group">
            {(['call','put'] as OptionType[]).map(t => (
              <button key={t} className={`opt-type-btn ${optType === t ? 'active ' + t : ''}`}
                onClick={() => setOptType(t)}>
                {t === 'call' ? '看涨 Call' : '看跌 Put'}
              </button>
            ))}
          </div>

          {expirations.length > 0 && (
            <div className="exp-scroll">
              {expirations.map(e => (
                <button key={e} className={`exp-btn ${expiration === e ? 'active' : ''}`}
                  onClick={() => setExpiration(e)}>
                  {e}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {error && <div className="overall-error">{error}</div>}

      {loading
        ? <div className="overall-loading">加载期权数据...</div>
        : (
          <div className="options-table-wrap">
            <table className="ov-table options-table">
              <thead>
                <tr>
                  <th>行权价</th>
                  <th className="right">买价</th>
                  <th className="right">卖价</th>
                  <th className="right">最新价</th>
                  <th className="right">成交量</th>
                  <th className="right">持仓量</th>
                  <th className="right">隐波</th>
                  <th className="right">Delta</th>
                  <th className="right">Gamma</th>
                  <th className="right">Theta</th>
                  <th className="right">Vega</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row: any, i: number) => {
                  const iv = parseFloat(row.implied_volatility ?? 0);
                  const isHighIV = iv > 0.6;
                  return (
                    <tr key={i} className={row.in_the_money ? 'itm-row' : ''}>
                      <td style={{ fontWeight: 700, color: '#6c8fff' }}>{price(row.strike)}</td>
                      <td className="right">{price(row.bid)}</td>
                      <td className="right">{price(row.ask)}</td>
                      <td className="right">{price(row.last_trade_price ?? row.last)}</td>
                      <td className="right">{vol(row.volume)}</td>
                      <td className="right">{vol(row.open_interest)}</td>
                      <td className={`right ${isHighIV ? 'positive' : ''}`}>
                        {iv > 0 ? (iv * 100).toFixed(1) + '%' : '-'}
                      </td>
                      <td className="right muted">{fmt(row.delta, 3)}</td>
                      <td className="right muted">{fmt(row.gamma, 4)}</td>
                      <td className={`right ${parseFloat(row.theta ?? 0) < 0 ? 'negative' : ''}`}>{fmt(row.theta, 3)}</td>
                      <td className="right muted">{fmt(row.vega, 3)}</td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && (
                  <tr><td colSpan={11} style={{ textAlign: 'center', padding: 30, color: '#555' }}>暂无期权数据</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )
      }
    </div>
  );
}
