import { useState, useEffect } from 'react';
import { redditAPI, xAPI, newsAPI } from '../api/adanos';
import Sparkline from './Sparkline';

const PLATFORMS = [
  { key: 'reddit', label: 'Reddit',     color: '#ff4500', icon: '👾' },
  { key: 'x',      label: 'X / Twitter', color: '#1d9bf0', icon: '𝕏' },
  { key: 'news',   label: 'News',        color: '#22c55e', icon: '📰' },
];

function TrendBadge({ trend }) {
  const cfg = {
    rising:  { color: '#4ade80', bg: '#052e16', label: '▲ Rising' },
    falling: { color: '#f87171', bg: '#450a0a', label: '▼ Falling' },
    stable:  { color: '#9ca3af', bg: '#1f2937', label: '● Stable' },
  };
  const c = cfg[trend] || cfg.stable;
  return (
    <span style={{ fontSize: '10px', padding: '2px 7px', borderRadius: '4px', color: c.color, background: c.bg, fontWeight: '700', whiteSpace: 'nowrap' }}>
      {c.label}
    </span>
  );
}

function SentimentBar({ bullish = 0, bearish = 0 }) {
  const neutral = Math.max(0, 100 - bullish - bearish);
  return (
    <div>
      <div style={{ display: 'flex', height: '5px', borderRadius: '3px', overflow: 'hidden', gap: '1px' }}>
        <div style={{ width: `${bullish}%`, background: '#22c55e' }} />
        <div style={{ width: `${neutral}%`, background: '#374151' }} />
        <div style={{ width: `${bearish}%`, background: '#ef4444' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '3px', fontSize: '10px' }}>
        <span style={{ color: '#22c55e' }}>▲ {bullish}%</span>
        <span style={{ color: '#6b7280' }}>{neutral}%</span>
        <span style={{ color: '#ef4444' }}>▼ {bearish}%</span>
      </div>
    </div>
  );
}

function CrossBadge({ others }) {
  if (!others.length) return null;
  return (
    <span style={{ fontSize: '9px', padding: '1px 5px', borderRadius: '3px', background: '#1e1b4b', color: '#a5b4fc', fontWeight: '700', marginLeft: '5px', verticalAlign: 'middle' }}>
      also on {others.join(' · ')}
    </span>
  );
}

function BuzzBar({ score, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
      <div style={{ flex: 1, height: '5px', background: '#1e2030', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', background: `linear-gradient(90deg, ${color}80, ${color})`, borderRadius: '3px', transition: 'width 0.6s ease' }} />
      </div>
      <span style={{ fontSize: '13px', fontWeight: '800', color, minWidth: '38px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
        {score?.toFixed(1)}
      </span>
    </div>
  );
}

function StockCard({ item, rank, color, crossOthers, onSelect }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={() => onSelect(item.ticker)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '12px 14px',
        borderRadius: '8px',
        background: hovered ? '#1e2130' : '#151720',
        border: `1px solid ${hovered ? color + '60' : '#1e2030'}`,
        cursor: 'pointer',
        marginBottom: '6px',
        transition: 'all 0.15s',
      }}
    >
      {/* Top row: rank + ticker + trend + sparkline */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', minWidth: 0 }}>
          <span style={{ fontSize: '11px', color: '#374151', fontWeight: '700', minWidth: '18px', paddingTop: '2px' }}>#{rank}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '2px' }}>
              <span style={{ fontSize: '15px', fontWeight: '900', color: '#f1f5f9' }}>{item.ticker}</span>
              <CrossBadge others={crossOthers} />
            </div>
            <div style={{ fontSize: '11px', color: '#4b5563', marginTop: '1px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '160px' }}>
              {item.company_name}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '5px', flexShrink: 0 }}>
          <TrendBadge trend={item.trend} />
          <Sparkline data={item.trend_history} color={color} width={72} height={24} />
        </div>
      </div>

      {/* Buzz bar */}
      <BuzzBar score={item.buzz_score} color={color} />

      {/* Sentiment bar */}
      <SentimentBar bullish={item.bullish_pct} bearish={item.bearish_pct} />

      {/* Sentiment score + footer stats */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '6px' }}>
        {item.sentiment_score !== undefined && (
          <span style={{
            fontSize: '12px', fontWeight: '800', fontVariantNumeric: 'tabular-nums',
            color: item.sentiment_score > 0.1 ? '#4ade80' : item.sentiment_score < -0.1 ? '#f87171' : '#9ca3af',
            padding: '1px 6px', borderRadius: '4px',
            background: item.sentiment_score > 0.1 ? '#052e16' : item.sentiment_score < -0.1 ? '#450a0a' : '#1f2937',
          }}>
            sentiment {item.sentiment_score > 0 ? '+' : ''}{item.sentiment_score?.toFixed(2)}
          </span>
        )}
        <div style={{ display: 'flex', gap: '10px', fontSize: '10px', color: '#4b5563' }}>
          <span>{item.mentions?.toLocaleString()} mentions</span>
          {item.unique_posts && <span>{item.unique_posts} posts</span>}
          {item.subreddit_count && <span>{item.subreddit_count} subs</span>}
          {item.unique_tweets && <span>{item.unique_tweets} tweets</span>}
        </div>
      </div>
    </div>
  );
}

export default function TrendingView({ days, onSelectTicker }) {
  const [data, setData] = useState({ reddit: [], x: [], news: [] });
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState('all');

  useEffect(() => {
    setLoading(true);
    Promise.all([
      redditAPI.trending(days, 20, type).catch(() => []),
      xAPI.trending(days, 20, type).catch(() => []),
      newsAPI.trending(days, 20, type).catch(() => []),
    ]).then(([reddit, x, news]) => {
      setData({
        reddit: Array.isArray(reddit) ? reddit : [],
        x:      Array.isArray(x)      ? x      : [],
        news:   Array.isArray(news)   ? news   : [],
      });
      setLoading(false);
    });
  }, [days, type]);

  // For each ticker, find which OTHER platforms also have it
  const getCrossOthers = (ticker, currentKey) => {
    const names = { reddit: 'Reddit', x: 'X', news: 'News' };
    return Object.entries(data)
      .filter(([k, arr]) => k !== currentKey && arr.some(s => s.ticker === ticker))
      .map(([k]) => names[k]);
  };

  // Count cross-platform validated tickers
  const crossCount = [...new Set([...data.reddit, ...data.x, ...data.news].map(s => s.ticker))]
    .filter(t => [data.reddit, data.x, data.news].filter(arr => arr.some(s => s.ticker === t)).length >= 2).length;

  return (
    <div>
      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {['all', 'stock', 'etf'].map(t => (
            <button key={t} onClick={() => setType(t)} style={{
              padding: '5px 12px', borderRadius: '5px', border: '1px solid', cursor: 'pointer', fontSize: '12px', fontWeight: '600',
              borderColor: type === t ? '#6366f1' : '#1e2030',
              background: type === t ? '#1e1b4b' : 'transparent',
              color: type === t ? '#a5b4fc' : '#6b7280',
            }}>
              {t.toUpperCase()}
            </button>
          ))}
        </div>
        {crossCount > 0 && (
          <div style={{ fontSize: '12px', color: '#a5b4fc', padding: '4px 10px', background: '#1e1b4b', borderRadius: '5px' }}>
            🔗 {crossCount} cross-platform tickers
          </div>
        )}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '80px', color: '#374151' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>⏳</div>
          Loading trending data...
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
          {PLATFORMS.map(({ key, label, color, icon }) => {
            const list = data[key];
            return (
              <div key={key}>
                {/* Column header */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px',
                  padding: '10px 14px', borderRadius: '8px', background: '#151720',
                  borderLeft: `3px solid ${color}`,
                }}>
                  <span style={{ fontSize: '16px' }}>{icon}</span>
                  <span style={{ fontWeight: '800', color, fontSize: '14px' }}>{label}</span>
                  <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#374151', fontWeight: '600' }}>
                    {list.length} stocks
                  </span>
                </div>

                {list.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#374151', fontSize: '13px' }}>No data</div>
                ) : (
                  list.map((item, i) => (
                    <StockCard
                      key={item.ticker}
                      item={item}
                      rank={i + 1}
                      color={color}
                      crossOthers={getCrossOthers(item.ticker, key)}
                      onSelect={onSelectTicker}
                    />
                  ))
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
