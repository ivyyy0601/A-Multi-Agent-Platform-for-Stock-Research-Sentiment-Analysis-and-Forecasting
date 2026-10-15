import { useState, useEffect } from 'react';
import { Line, Doughnut } from 'react-chartjs-2';
import { redditAPI, xAPI, newsAPI } from '../api/adanos';

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: { legend: { labels: { color: '#6b7280', font: { size: 10 }, boxWidth: 10 } } },
  scales: {
    x:  { ticks: { color: '#4b5563', font: { size: 9 } }, grid: { color: '#1a1d27' } },
    y1: { type: 'linear', position: 'left',  ticks: { color: '#4b5563', font: { size: 9 } }, grid: { color: '#1a1d27' } },
    y2: { type: 'linear', position: 'right', min: -1, max: 1, ticks: { color: '#4b5563', font: { size: 9 } }, grid: { display: false } },
  },
};

const DONUT_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom', labels: { color: '#6b7280', font: { size: 10 }, padding: 8, boxWidth: 10 } },
  },
};

function SentimentLabel({ label }) {
  const cfg = { positive: '#22c55e', negative: '#ef4444', neutral: '#6b7280' };
  return <span style={{ color: cfg[label] || '#6b7280', fontWeight: '600' }}>{label}</span>;
}

function PlatformCard({ title, color, icon, data, explanation, explainError, onExplain, loadingExplain, canExplain }) {
  if (!data || data.found === false) {
    return (
      <div style={{ flex: 1, background: '#111318', borderRadius: '10px', border: '1px solid #1e2030', padding: '16px' }}>
        <div style={{ color, fontWeight: '800', fontSize: '14px', marginBottom: '12px' }}>{icon} {title}</div>
        <div style={{ color: '#374151', fontSize: '13px', textAlign: 'center', padding: '40px 0' }}>No data for this period</div>
      </div>
    );
  }

  const dailyTrend = [...(data.daily_trend || [])]
    .filter(d => d?.date)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const dates = dailyTrend.map(d => d.date?.slice(5));
  const trendColor = data.trend === 'rising' ? '#4ade80' : data.trend === 'falling' ? '#f87171' : '#9ca3af';

  const lineData = {
    labels: dates,
    datasets: [
      {
        label: 'Mentions',
        data: dailyTrend.map(d => d.mentions),
        borderColor: color,
        backgroundColor: color + '18',
        yAxisID: 'y1',
        tension: 0.4,
        fill: true,
        borderWidth: 2,
        pointRadius: 2,
      },
      {
        label: 'Sentiment',
        data: dailyTrend.map(d => d.sentiment_score),
        borderColor: '#a855f7',
        backgroundColor: 'transparent',
        yAxisID: 'y2',
        tension: 0.4,
        borderWidth: 2,
        pointRadius: 2,
        borderDash: [4, 3],
      },
    ],
  };

  const donutData = {
    labels: ['Positive', 'Neutral', 'Negative'],
    datasets: [{
      data: [data.positive_count || 0, data.neutral_count || 0, data.negative_count || 0],
      backgroundColor: ['#22c55e', '#374151', '#ef4444'],
      borderWidth: 0,
    }],
  };

  const mentions = [...(data.top_mentions || data.top_tweets || [])]
    .sort((a, b) => (b.upvotes || b.likes || 0) - (a.upvotes || a.likes || 0));

  return (
    <div style={{ flex: 1, background: '#111318', borderRadius: '10px', border: `1px solid ${color}30`, padding: '16px', minWidth: 0 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <span style={{ color, fontWeight: '800', fontSize: '14px' }}>{icon} {title}</span>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {data.sentiment_score !== undefined && data.sentiment_score !== null && (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '9px', color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sentiment</div>
              <div style={{
                fontSize: '15px', fontWeight: '800', fontVariantNumeric: 'tabular-nums',
                color: data.sentiment_score > 0.05 ? '#22c55e' : data.sentiment_score < -0.05 ? '#ef4444' : '#6b7280',
              }}>
                {data.sentiment_score > 0 ? '+' : ''}{data.sentiment_score.toFixed(2)}
              </div>
            </div>
          )}
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '9px', color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Buzz</div>
            <div style={{ fontSize: '22px', fontWeight: '900', color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
              {data.buzz_score?.toFixed(1)}
            </div>
            <div style={{ fontSize: '10px', color: trendColor }}>
              {data.trend === 'rising' ? '▲' : data.trend === 'falling' ? '▼' : '●'} {data.trend}
            </div>
          </div>
        </div>
      </div>

      {/* Stats grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '5px', marginBottom: '12px' }}>
        {[
          ['Mentions', data.mentions?.toLocaleString()],
          ['Bullish',  `${data.bullish_pct ?? '—'}%`],
          ['Bearish',  `${data.bearish_pct ?? '—'}%`],
        ].map(([label, val]) => (
          <div key={label} style={{ background: '#0d0f15', borderRadius: '6px', padding: '6px', textAlign: 'center' }}>
            <div style={{ fontSize: '9px', color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
            <div style={{ fontSize: '13px', fontWeight: '800', color: '#e2e8f0', fontVariantNumeric: 'tabular-nums' }}>{val ?? '—'}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '12px', alignItems: 'center' }}>
        <div style={{ width: '110px', height: '110px', flexShrink: 0 }}>
          <Doughnut data={donutData} options={DONUT_OPTIONS} />
        </div>
        <div style={{ flex: 1, height: '110px' }}>
          {dates.length > 1
            ? <Line data={lineData} options={CHART_DEFAULTS} />
            : <div style={{ color: '#374151', fontSize: '12px', textAlign: 'center', paddingTop: '40px' }}>Not enough history</div>
          }
        </div>
      </div>

      {/* AI Explain */}
      {canExplain && (
        <button
          onClick={onExplain}
          disabled={loadingExplain}
          style={{
            width: '100%', padding: '8px', borderRadius: '6px',
            border: `1px solid ${color}40`, background: 'transparent',
            color, cursor: 'pointer', fontSize: '12px', fontWeight: '700',
            marginBottom: explanation ? '10px' : '0',
            opacity: loadingExplain ? 0.6 : 1,
          }}
        >
          {loadingExplain ? '⏳ Generating explanation...' : '🤖 AI Explain why it\'s trending'}
        </button>
      )}

      {explanation && (
        <div style={{ padding: '10px 12px', background: '#0d0f15', borderRadius: '6px', fontSize: '12px', color: '#cbd5e1', lineHeight: '1.6', marginBottom: '10px', borderLeft: `2px solid ${color}` }}>
          {explanation.explanation}
          <div style={{ marginTop: '6px', fontSize: '10px', color: '#374151' }}>
            via {explanation.model} · {explanation.generated_at?.slice(0, 10)}{explanation.cached ? ' · cached' : ''}
          </div>
        </div>
      )}

      {explainError && !explanation && (
        <div style={{ padding: '8px 12px', background: '#1a0a0a', borderRadius: '6px', fontSize: '11px', color: '#f87171', marginBottom: '10px' }}>
          {explainError}
        </div>
      )}

      {/* Top mentions */}
      {mentions.length > 0 && (
        <div>
          <div style={{ fontSize: '10px', color: '#374151', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>
            Top Mentions
          </div>
          <div style={{ maxHeight: '220px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px', paddingRight: '4px' }}>
            {mentions.map((m, i) => (
              <div key={i} style={{ padding: '8px', background: '#0d0f15', borderRadius: '6px', flexShrink: 0 }}>
                <div style={{ fontSize: '11px', color: '#cbd5e1', lineHeight: '1.4', marginBottom: '4px' }}>{m.text_snippet}</div>
                <div style={{ display: 'flex', gap: '8px', fontSize: '10px', color: '#4b5563', flexWrap: 'wrap' }}>
                  <SentimentLabel label={m.sentiment_label} />
                  <span>↑ {(m.upvotes || m.likes)?.toLocaleString() ?? '—'}</span>
                  {m.subreddit && <span>r/{m.subreddit}</span>}
                  {m.source    && <span>{m.source}</span>}
                  {m.author    && <span>@{m.author}</span>}
                  <span>{m.created_utc?.slice(0, 10) || m.created_at?.slice(0, 10)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DeepDive({ initialTicker, days }) {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [ticker, setTicker] = useState(initialTicker || '');
  const [company, setCompany] = useState('');
  const [data, setData] = useState({ reddit: null, x: null, news: null });
  const [explanations, setExplanations] = useState({});
  const [explainErrors, setExplainErrors] = useState({});
  const [loadingExplain, setLoadingExplain] = useState({});
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    if (initialTicker) {
      setTicker(initialTicker);
      fetchTicker(initialTicker);
    }
  }, [initialTicker]);

  useEffect(() => {
    if (ticker) fetchTicker(ticker);
  }, [days]);

  async function handleSearch(q) {
    setQuery(q);
    if (q.trim().length < 2) { setSearchResults([]); return; }
    setSearchLoading(true);
    const [r1, r2, r3] = await Promise.all([
      redditAPI.search(q, days).catch(() => ({ results: [] })),
      xAPI.search(q, days).catch(() => ({ results: [] })),
      newsAPI.search(q, days).catch(() => ({ results: [] })),
    ]);
    const combined = [...(r1.results || []), ...(r2.results || []), ...(r3.results || [])];
    const unique = combined.filter((r, i, arr) => arr.findIndex(x => x.ticker === r.ticker) === i);
    setSearchResults(unique.slice(0, 8));
    setSearchLoading(false);
  }

  async function fetchTicker(t) {
    setLoading(true);
    setData({ reddit: null, x: null, news: null });
    setExplanations({});
    const [reddit, x, news] = await Promise.all([
      redditAPI.stock(t, days).catch(() => null),
      xAPI.stock(t, days).catch(() => null),
      newsAPI.stock(t, days).catch(() => null),
    ]);
    setData({ reddit, x, news });
    setLoading(false);
    setSearchResults([]);
    setQuery('');
  }

  function selectResult(r) {
    setTicker(r.ticker);
    setCompany(r.name || '');
    fetchTicker(r.ticker);
  }

  async function handleExplain(platform) {
    setLoadingExplain(prev => ({ ...prev, [platform]: true }));
    setExplainErrors(prev => ({ ...prev, [platform]: null }));
    try {
      const fn = platform === 'reddit' ? redditAPI.explain : newsAPI.explain;
      const result = await fn(ticker);
      setExplanations(prev => ({ ...prev, [platform]: result }));
    } catch (e) {
      const msg = e.status === 404
        ? 'No explanation available — stock may not be trending enough.'
        : 'Failed to load explanation. Please try again.';
      setExplainErrors(prev => ({ ...prev, [platform]: msg }));
    }
    setLoadingExplain(prev => ({ ...prev, [platform]: false }));
  }

  // Cross-platform divergence
  const scores = [data.reddit?.sentiment_score, data.x?.sentiment_score, data.news?.sentiment_score]
    .filter(s => s !== null && s !== undefined);
  const divergence = scores.length > 1 ? (Math.max(...scores) - Math.min(...scores)) : null;
  const highDiv = divergence !== null && divergence > 0.3;

  // Viral score: social buzz vs news coverage
  const socialBuzz = [data.reddit?.buzz_score, data.x?.buzz_score].filter(Boolean);
  const avgSocial = socialBuzz.length ? socialBuzz.reduce((a, b) => a + b, 0) / socialBuzz.length : null;
  const viralScore = avgSocial !== null && data.news?.buzz_score ? (avgSocial - data.news.buzz_score).toFixed(1) : null;

  return (
    <div>
      {/* Search */}
      <div style={{ position: 'relative', marginBottom: '16px' }}>
        <div style={{ position: 'relative' }}>
          <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#4b5563', fontSize: '14px' }}>🔍</span>
          <input
            type="text"
            value={query}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search ticker or company (e.g. TSLA, Apple, NVDA)..."
            style={{
              width: '100%', padding: '12px 16px 12px 38px',
              borderRadius: '8px', border: '1px solid #1e2030',
              background: '#111318', color: '#f1f5f9', fontSize: '14px',
              outline: 'none', boxSizing: 'border-box',
            }}
            onFocus={e => e.target.style.borderColor = '#6366f1'}
            onBlur={e => e.target.style.borderColor = '#1e2030'}
          />
          {searchLoading && (
            <span style={{ position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)', color: '#4b5563', fontSize: '12px' }}>searching...</span>
          )}
        </div>

        {searchResults.length > 0 && (
          <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#111318', border: '1px solid #1e2030', borderRadius: '8px', zIndex: 100, marginTop: '4px', overflow: 'hidden' }}>
            {searchResults.map(r => (
              <div
                key={r.ticker}
                onClick={() => selectResult(r)}
                style={{ padding: '10px 16px', cursor: 'pointer', borderBottom: '1px solid #1a1d27', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                onMouseEnter={e => e.currentTarget.style.background = '#1a1d27'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div>
                  <span style={{ fontWeight: '800', color: '#f1f5f9' }}>{r.ticker}</span>
                  <span style={{ fontSize: '12px', color: '#6b7280', marginLeft: '8px' }}>{r.name}</span>
                </div>
                <div style={{ fontSize: '11px', color: '#374151', display: 'flex', gap: '8px' }}>
                  {r.summary?.buzz_score && <span style={{ color: '#6366f1' }}>buzz {r.summary.buzz_score?.toFixed(0)}</span>}
                  <span>{r.exchange}</span>
                  <span>{r.sector}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Ticker header + metrics */}
      {ticker && !loading && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px', padding: '12px 16px', background: '#111318', borderRadius: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '26px', fontWeight: '900', color: '#f1f5f9' }}>{ticker}</span>
            {company && <span style={{ fontSize: '14px', color: '#4b5563' }}>{company}</span>}

            {divergence !== null && (
              <div style={{ padding: '5px 10px', borderRadius: '6px', background: highDiv ? '#450a0a' : '#052e16', color: highDiv ? '#fca5a5' : '#86efac', fontSize: '12px', fontWeight: '700' }}>
                {highDiv ? '⚠️' : '✓'} Sentiment divergence: {divergence.toFixed(2)}
                {highDiv ? ' — platforms disagree' : ' — aligned'}
              </div>
            )}

            {viralScore !== null && parseFloat(viralScore) > 15 && (
              <div style={{ padding: '5px 10px', borderRadius: '6px', background: '#1e1b4b', color: '#a5b4fc', fontSize: '12px', fontWeight: '700' }}>
                ⚡ Viral: social buzz +{viralScore} ahead of news
              </div>
            )}

            {data.x?.is_validated && (
              <div style={{ padding: '5px 10px', borderRadius: '6px', background: '#0c1a0c', color: '#4ade80', fontSize: '12px', fontWeight: '700' }}>
                🔗 Cross-validated on Reddit + X
              </div>
            )}

            <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#374151' }}>{days}d window</span>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <PlatformCard
              title="Reddit" icon="👾" color="#ff4500"
              data={data.reddit}
              explanation={explanations.reddit}
              explainError={explainErrors.reddit}
              onExplain={() => handleExplain('reddit')}
              loadingExplain={loadingExplain.reddit}
              canExplain={true}
            />
            <PlatformCard
              title="X / Twitter" icon="𝕏" color="#1d9bf0"
              data={data.x}
              explanation={null}
              onExplain={null}
              loadingExplain={false}
              canExplain={false}
            />
            <PlatformCard
              title="News" icon="📰" color="#22c55e"
              data={data.news}
              explanation={explanations.news}
              explainError={explainErrors.news}
              onExplain={() => handleExplain('news')}
              loadingExplain={loadingExplain.news}
              canExplain={true}
            />
          </div>
        </>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '80px', color: '#374151' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>⏳</div>
          Loading {ticker}...
        </div>
      )}

      {!ticker && !loading && (
        <div style={{ textAlign: 'center', padding: '80px', color: '#374151' }}>
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>🔍</div>
          <div style={{ fontSize: '15px', marginBottom: '6px' }}>Search for any stock ticker</div>
          <div style={{ fontSize: '12px' }}>Get side-by-side Reddit, X, and News sentiment data</div>
        </div>
      )}
    </div>
  );
}
