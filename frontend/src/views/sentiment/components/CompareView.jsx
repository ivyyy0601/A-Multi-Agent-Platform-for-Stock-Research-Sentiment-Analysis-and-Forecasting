import { useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { redditAPI, xAPI, newsAPI } from '../api/adanos';
import Sparkline from './Sparkline';

const BAR_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { labels: { color: '#9ca3af', font: { size: 11 }, boxWidth: 12 } },
  },
  scales: {
    x:  { ticks: { color: '#9ca3af', font: { size: 12, weight: '700' } }, grid: { color: '#1a1d27' } },
    y:  { max: 100, ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: '#1a1d27' } },
  },
};

function TrendIcon({ trend }) {
  if (trend === 'rising')  return <span style={{ color: '#4ade80' }}>▲</span>;
  if (trend === 'falling') return <span style={{ color: '#f87171' }}>▼</span>;
  if (trend)               return <span style={{ color: '#6b7280' }}>●</span>;
  return <span style={{ color: '#1f2937' }}>—</span>;
}

function SentimentMini({ score }) {
  if (score === undefined || score === null) return <span style={{ color: '#374151' }}>—</span>;
  const color = score > 0.1 ? '#4ade80' : score < -0.1 ? '#f87171' : '#9ca3af';
  return <span style={{ color, fontWeight: '700', fontVariantNumeric: 'tabular-nums' }}>{score > 0 ? '+' : ''}{score.toFixed(2)}</span>;
}

export default function CompareView({ days }) {
  const [input, setInput] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleCompare() {
    const tickers = input.toUpperCase().split(/[\s,;]+/).filter(Boolean).slice(0, 10).join(',');
    if (!tickers) return;
    setError('');
    setLoading(true);
    try {
      const [r, x, n] = await Promise.all([
        redditAPI.compare(tickers, days).catch(() => null),
        xAPI.compare(tickers, days).catch(() => null),
        newsAPI.compare(tickers, days).catch(() => null),
      ]);
      setResult({ reddit: r?.stocks || [], x: x?.stocks || [], news: n?.stocks || [] });
    } catch (e) {
      setError('Failed to fetch comparison data.');
    }
    setLoading(false);
  }

  const allTickers = result
    ? [...new Set([...result.reddit, ...result.x, ...result.news].map(s => s.ticker))]
    : [];

  const rdMap = result ? Object.fromEntries(result.reddit.map(s => [s.ticker, s])) : {};
  const xMap  = result ? Object.fromEntries(result.x.map(s => [s.ticker, s])) : {};
  const nMap  = result ? Object.fromEntries(result.news.map(s => [s.ticker, s])) : {};

  const barData = {
    labels: allTickers,
    datasets: [
      { label: 'Reddit Buzz',  data: allTickers.map(t => rdMap[t]?.buzz_score || 0), backgroundColor: '#ff450090', borderColor: '#ff4500', borderWidth: 1, borderRadius: 4 },
      { label: 'X Buzz',       data: allTickers.map(t => xMap[t]?.buzz_score  || 0), backgroundColor: '#1d9bf090', borderColor: '#1d9bf0', borderWidth: 1, borderRadius: 4 },
      { label: 'News Buzz',    data: allTickers.map(t => nMap[t]?.buzz_score  || 0), backgroundColor: '#22c55e90', borderColor: '#22c55e', borderWidth: 1, borderRadius: 4 },
    ],
  };

  const th = (label, color = '#6b7280') => (
    <th style={{ padding: '8px 10px', textAlign: 'center', color, fontSize: '10px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap', background: '#0d0f15', borderBottom: '1px solid #1e2030' }}>
      {label}
    </th>
  );

  return (
    <div>
      {/* Input */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCompare()}
          placeholder="Enter tickers, e.g.  TSLA, NVDA, AAPL, AMD, META  (up to 10)"
          style={{
            flex: 1, padding: '12px 16px', borderRadius: '8px',
            border: '1px solid #1e2030', background: '#111318',
            color: '#f1f5f9', fontSize: '14px', outline: 'none',
          }}
          onFocus={e => e.target.style.borderColor = '#6366f1'}
          onBlur={e => e.target.style.borderColor = '#1e2030'}
        />
        <button
          onClick={handleCompare}
          disabled={loading || !input.trim()}
          style={{
            padding: '12px 28px', borderRadius: '8px', border: 'none',
            background: loading ? '#312e81' : '#6366f1',
            color: '#fff', fontWeight: '800', cursor: 'pointer', fontSize: '14px',
            opacity: !input.trim() ? 0.4 : 1,
            transition: 'background 0.15s',
          }}
        >
          {loading ? '⏳' : 'Compare'}
        </button>
      </div>

      {error && <div style={{ color: '#f87171', marginBottom: '12px', fontSize: '13px' }}>{error}</div>}

      {result && allTickers.length > 0 && (
        <>
          {/* Bar chart */}
          <div style={{ background: '#111318', borderRadius: '10px', padding: '16px 16px 12px', marginBottom: '16px', height: '200px' }}>
            <Bar data={barData} options={BAR_OPTIONS} />
          </div>

          {/* Comparison table */}
          <div style={{ overflowX: 'auto', borderRadius: '10px', border: '1px solid #1e2030' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
              <thead>
                <tr>
                  {th('Ticker', '#9ca3af')}
                  {th('Reddit Buzz', '#ff4500')}
                  {th('Trend', '#ff4500')}
                  {th('History', '#ff4500')}
                  {th('X Buzz', '#1d9bf0')}
                  {th('Trend', '#1d9bf0')}
                  {th('History', '#1d9bf0')}
                  {th('News Buzz', '#22c55e')}
                  {th('Trend', '#22c55e')}
                  {th('History', '#22c55e')}
                  {th('Sentiment R', '#ff4500')}
                  {th('Sentiment X', '#1d9bf0')}
                  {th('Sentiment N', '#22c55e')}
                </tr>
              </thead>
              <tbody>
                {allTickers.map((ticker, rowIdx) => {
                  const rd = rdMap[ticker];
                  const xd = xMap[ticker];
                  const nd = nMap[ticker];
                  const rowBg = rowIdx % 2 === 0 ? '#111318' : '#0d0f15';
                  const scores = [rd?.sentiment_score, xd?.sentiment_score, nd?.sentiment_score].filter(s => s !== null && s !== undefined);
                  const divergence = scores.length > 1 ? Math.max(...scores) - Math.min(...scores) : 0;

                  return (
                    <tr key={ticker} style={{ background: rowBg, borderBottom: '1px solid #1a1d27' }}>
                      <td style={{ padding: '10px 14px', fontWeight: '800', color: '#f1f5f9', fontSize: '14px', whiteSpace: 'nowrap' }}>
                        {ticker}
                        <div style={{ fontSize: '10px', color: '#374151', fontWeight: '400', maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {rd?.company_name || xd?.company_name || nd?.company_name}
                        </div>
                        {divergence > 0.3 && (
                          <div style={{ fontSize: '9px', color: '#fbbf24', marginTop: '2px' }}>⚠️ div {divergence.toFixed(2)}</div>
                        )}
                      </td>

                      {[
                        { d: rd, color: '#ff4500' },
                        { d: xd, color: '#1d9bf0' },
                        { d: nd, color: '#22c55e' },
                      ].map(({ d, color }, i) => (
                        <>
                          <td key={`${i}b`} style={{ padding: '10px 10px', textAlign: 'center', fontWeight: '800', color: d ? color : '#1f2937', fontSize: '14px', fontVariantNumeric: 'tabular-nums' }}>
                            {d?.buzz_score?.toFixed(1) ?? '—'}
                          </td>
                          <td key={`${i}t`} style={{ padding: '10px 8px', textAlign: 'center', fontSize: '13px' }}>
                            <TrendIcon trend={d?.trend} />
                          </td>
                          <td key={`${i}s`} style={{ padding: '10px 8px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', justifyContent: 'center' }}>
                              <Sparkline data={d?.trend_history} color={color} width={64} height={20} />
                            </div>
                          </td>
                        </>
                      ))}

                      <td style={{ padding: '10px 10px', textAlign: 'center', fontSize: '12px' }}>
                        <SentimentMini score={rd?.sentiment_score} />
                      </td>
                      <td style={{ padding: '10px 10px', textAlign: 'center', fontSize: '12px' }}>
                        <SentimentMini score={xd?.sentiment_score} />
                      </td>
                      <td style={{ padding: '10px 10px', textAlign: 'center', fontSize: '12px' }}>
                        <SentimentMini score={nd?.sentiment_score} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!result && !loading && (
        <div style={{ textAlign: 'center', padding: '80px', color: '#374151' }}>
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>⚖️</div>
          <div style={{ fontSize: '15px', marginBottom: '6px' }}>Compare up to 10 tickers</div>
          <div style={{ fontSize: '12px' }}>See buzz scores, trends, and sentiment across Reddit, X, and News side by side</div>
        </div>
      )}
    </div>
  );
}
