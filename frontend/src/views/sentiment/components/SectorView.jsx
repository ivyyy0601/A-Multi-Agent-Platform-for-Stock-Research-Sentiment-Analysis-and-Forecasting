import { useState, useEffect } from 'react';
import { redditAPI, xAPI, newsAPI } from '../api/adanos';

// Interpolate color from cool dark → hot orange based on buzz (0–100)
function buzzToColor(score) {
  if (!score) return { bg: '#111318', text: '#374151' };
  const t = Math.min(score / 100, 1);
  // dark blue (#0f1b2e) → deep orange (#c2410c) → bright (#f97316)
  const r = Math.round(15  + (244 - 15)  * t);
  const g = Math.round(27  + (97  - 27)  * t * (t < 0.5 ? 1 : 1 - (t - 0.5) * 1.2));
  const b = Math.round(46  + (12  - 46)  * t);
  const text = t > 0.45 ? '#fff' : '#94a3b8';
  return { bg: `rgb(${r},${g},${b})`, text };
}

function TrendArrow({ trend }) {
  if (trend === 'rising')  return <span style={{ color: '#4ade80', fontSize: '12px' }}>▲</span>;
  if (trend === 'falling') return <span style={{ color: '#f87171', fontSize: '12px' }}>▼</span>;
  return <span style={{ color: '#6b7280', fontSize: '12px' }}>●</span>;
}

function Cell({ d }) {
  const [hovered, setHovered] = useState(false);
  if (!d) return <td style={{ padding: '10px 12px', background: '#0d0f15', textAlign: 'center', border: '1px solid #111318' }}>
    <span style={{ color: '#1f2937', fontSize: '13px' }}>—</span>
  </td>;

  const { bg, text } = buzzToColor(d.buzz_score);
  return (
    <td
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ padding: '10px 12px', background: bg, border: '1px solid #0d0f15', position: 'relative', verticalAlign: 'top', cursor: 'default', transition: 'filter 0.15s', filter: hovered ? 'brightness(1.15)' : 'none' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '3px' }}>
        <span style={{ fontSize: '15px', fontWeight: '800', color: text }}>{d.buzz_score?.toFixed(1)}</span>
        <TrendArrow trend={d.trend} />
      </div>
      <div style={{ fontSize: '10px', color: text, opacity: 0.7, marginBottom: '4px' }}>
        {d.mentions?.toLocaleString()} mentions
      </div>
      <div style={{ display: 'flex', gap: '2px', flexWrap: 'wrap' }}>
        {d.top_tickers?.slice(0, 4).map(t => (
          <span key={t} style={{ fontSize: '9px', padding: '1px 4px', background: 'rgba(0,0,0,0.35)', borderRadius: '3px', color: text, fontWeight: '600' }}>
            {t}
          </span>
        ))}
      </div>
      {hovered && (
        <div style={{ marginTop: '5px', fontSize: '10px', color: text, opacity: 0.8, display: 'flex', gap: '8px' }}>
          <span style={{ color: '#4ade80' }}>▲{d.bullish_pct}%</span>
          <span style={{ color: '#f87171' }}>▼{d.bearish_pct}%</span>
          {d.unique_tickers && <span>{d.unique_tickers} tickers</span>}
        </div>
      )}
    </td>
  );
}

export default function SectorView({ days }) {
  const [data, setData] = useState({ reddit: [], x: [], news: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      redditAPI.trendingSectors(days, 20).catch(() => []),
      xAPI.trendingSectors(days, 20).catch(() => []),
      newsAPI.trendingSectors(days, 20).catch(() => []),
    ]).then(([reddit, x, news]) => {
      setData({
        reddit: Array.isArray(reddit) ? reddit : [],
        x:      Array.isArray(x)      ? x      : [],
        news:   Array.isArray(news)   ? news   : [],
      });
      setLoading(false);
    });
  }, [days]);

  const sectors = [...new Set([
    ...data.reddit.map(s => s.sector),
    ...data.x.map(s => s.sector),
    ...data.news.map(s => s.sector),
  ])].filter(Boolean).sort();

  const rdMap = Object.fromEntries(data.reddit.map(s => [s.sector, s]));
  const xMap  = Object.fromEntries(data.x.map(s => [s.sector, s]));
  const nMap  = Object.fromEntries(data.news.map(s => [s.sector, s]));

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '80px', color: '#374151' }}>
      <div style={{ fontSize: '24px', marginBottom: '8px' }}>⏳</div>Loading sector data...
    </div>
  );

  return (
    <div>
      <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', fontSize: '12px', color: '#4b5563', alignItems: 'center' }}>
        <span>Color intensity = buzz score (0–100)</span>
        <div style={{ display: 'flex', gap: '2px', height: '12px', flex: '0 0 120px', borderRadius: '3px', overflow: 'hidden' }}>
          {Array.from({ length: 20 }, (_, i) => {
            const { bg } = buzzToColor((i / 19) * 100);
            return <div key={i} style={{ flex: 1, background: bg }} />;
          })}
        </div>
        <span>0 → 100</span>
        <span style={{ marginLeft: 'auto' }}>Hover for details</span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'separate', borderSpacing: '2px', width: '100%' }}>
          <thead>
            <tr>
              <th style={{ padding: '10px 16px', textAlign: 'left', color: '#6b7280', fontSize: '11px', fontWeight: '700', background: '#0d0f15', whiteSpace: 'nowrap' }}>
                SECTOR
              </th>
              {[
                { label: '👾 Reddit',     color: '#ff4500' },
                { label: '𝕏 Twitter',    color: '#1d9bf0' },
                { label: '📰 News',       color: '#22c55e' },
              ].map(({ label, color }) => (
                <th key={label} style={{ padding: '10px 12px', textAlign: 'center', color, fontSize: '11px', fontWeight: '700', background: '#0d0f15', minWidth: '160px' }}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sectors.map(sector => (
              <tr key={sector}>
                <td style={{ padding: '10px 16px', color: '#e2e8f0', fontSize: '13px', fontWeight: '700', background: '#151720', whiteSpace: 'nowrap', border: '1px solid #0d0f15' }}>
                  {sector}
                </td>
                <Cell d={rdMap[sector]} />
                <Cell d={xMap[sector]} />
                <Cell d={nMap[sector]} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
