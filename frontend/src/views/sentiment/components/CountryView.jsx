import { useState, useEffect } from 'react';
import { redditAPI, xAPI, newsAPI } from '../api/adanos';

const PLATFORMS = [
  { key: 'reddit', label: '👾 Reddit',    color: '#ff4500' },
  { key: 'x',      label: '𝕏 Twitter',   color: '#1d9bf0' },
  { key: 'news',   label: '📰 News',      color: '#22c55e' },
];

function CountryCard({ item, rank, color, maxBuzz }) {
  const [hovered, setHovered] = useState(false);
  const pct = maxBuzz ? (item.buzz_score / maxBuzz) * 100 : 0;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        marginBottom: '6px', padding: '10px 12px', borderRadius: '7px',
        background: hovered ? '#1a1d27' : '#141620',
        border: `1px solid ${hovered ? color + '50' : '#1e2030'}`,
        transition: 'all 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '11px', color: '#374151', fontWeight: '700', minWidth: '16px' }}>#{rank}</span>
          <span style={{ fontSize: '13px', fontWeight: '700', color: '#e2e8f0' }}>{item.country}</span>
        </div>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span style={{ fontSize: '13px', fontWeight: '800', color, fontVariantNumeric: 'tabular-nums' }}>
            {item.buzz_score?.toFixed(1)}
          </span>
          <span style={{ fontSize: '10px', color: item.trend === 'rising' ? '#4ade80' : item.trend === 'falling' ? '#f87171' : '#6b7280' }}>
            {item.trend === 'rising' ? '▲' : item.trend === 'falling' ? '▼' : '●'}
          </span>
        </div>
      </div>

      {/* Buzz bar */}
      <div style={{ height: '4px', background: '#1e2030', borderRadius: '2px', overflow: 'hidden', marginBottom: '6px' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: `linear-gradient(90deg, ${color}60, ${color})`, borderRadius: '2px', transition: 'width 0.5s ease' }} />
      </div>

      {/* Top tickers */}
      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: hovered ? '6px' : '0' }}>
        {item.top_tickers?.slice(0, 5).map(t => (
          <span key={t} style={{ fontSize: '10px', padding: '1px 6px', borderRadius: '3px', background: '#0d0f15', color: '#6b7280', border: '1px solid #1e2030', fontWeight: '600' }}>
            {t}
          </span>
        ))}
      </div>

      {hovered && (
        <div style={{ display: 'flex', gap: '12px', fontSize: '10px', color: '#4b5563', marginTop: '4px' }}>
          <span>{item.mentions?.toLocaleString()} mentions</span>
          {item.unique_tickers && <span>{item.unique_tickers} tickers</span>}
          <span style={{ color: '#4ade80' }}>▲ {item.bullish_pct}%</span>
          <span style={{ color: '#f87171' }}>▼ {item.bearish_pct}%</span>
        </div>
      )}
    </div>
  );
}

function PlatformColumn({ data, color, label }) {
  const maxBuzz = Math.max(...data.map(d => d.buzz_score || 0), 1);
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', padding: '10px 14px', borderRadius: '8px', background: '#151720', borderLeft: `3px solid ${color}` }}>
        <span style={{ fontWeight: '800', color, fontSize: '14px' }}>{label}</span>
        <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#374151', fontWeight: '600' }}>{data.length} countries</span>
      </div>
      {data.length === 0
        ? <div style={{ textAlign: 'center', padding: '40px', color: '#374151', fontSize: '13px' }}>No data</div>
        : data.map((item, i) => (
          <CountryCard key={item.country} item={item} rank={i + 1} color={color} maxBuzz={maxBuzz} />
        ))
      }
    </div>
  );
}

export default function CountryView({ days }) {
  const [data, setData] = useState({ reddit: [], x: [], news: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      redditAPI.trendingCountries(days, 15).catch(() => []),
      xAPI.trendingCountries(days, 15).catch(() => []),
      newsAPI.trendingCountries(days, 15).catch(() => []),
    ]).then(([reddit, x, news]) => {
      setData({
        reddit: Array.isArray(reddit) ? reddit : [],
        x:      Array.isArray(x)      ? x      : [],
        news:   Array.isArray(news)   ? news   : [],
      });
      setLoading(false);
    });
  }, [days]);

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '80px', color: '#374151' }}>
      <div style={{ fontSize: '24px', marginBottom: '8px' }}>⏳</div>Loading country data...
    </div>
  );

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
      {PLATFORMS.map(({ key, label, color }) => (
        <PlatformColumn key={key} data={data[key]} color={color} label={label} />
      ))}
    </div>
  );
}
