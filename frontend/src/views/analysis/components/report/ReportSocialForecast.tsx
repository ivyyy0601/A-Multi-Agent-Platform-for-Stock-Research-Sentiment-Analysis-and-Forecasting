import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface SimilarDay { date: string; similarity: number; next_day_ret: number; went_up: boolean; }
interface SentimentNow { sentiment: number; buzz: number; bullish: number; }

interface Forecast {
  ticker: string;
  forecast_date: string;
  prediction: {
    direction: 'up' | 'down';
    confidence: number;
    model_accuracy: number | null;
    baseline_accuracy: number | null;
  };
  platform_agreement: boolean;
  sentiment_now: Record<string, SentimentNow>;
  similar_days: SimilarDay[];
  similar_stats: { count: number; up_ratio: number | null; avg_ret: number | null };
  overall: 'bullish' | 'bearish' | 'unclear';
}

const PC: Record<string, string> = { reddit: '#ff6314', twitter: '#1d9bf0', news: '#a78bfa' };

function nextTradingDay(date: string): string {
  const d = new Date(date + 'T00:00:00');
  d.setDate(d.getDate() + 1);
  if (d.getDay() === 6) d.setDate(d.getDate() + 2);
  if (d.getDay() === 0) d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

interface Props { stockCode: string; fetchedAt?: string; }

export const ReportSocialForecast: React.FC<Props> = ({ stockCode, fetchedAt }) => {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!stockCode) return;
    setLoading(true);
    setError('');
    setForecast(null);
    axios.get(`/api/adanos/${stockCode.toUpperCase()}/forecast`, {
      params: { date: fetchedAt ? fetchedAt.slice(0, 10) : undefined },
    })
      .then(r => setForecast(r.data))
      .catch(e => setError(e.response?.data?.detail || 'No model data'))
      .finally(() => setLoading(false));
  }, [stockCode, fetchedAt]);

  const goToSocial = () => {
    window.dispatchEvent(new CustomEvent('navigate-social', { detail: { ticker: stockCode.toUpperCase() } }));
  };

  return (
    <div className="glass-card rounded-xl p-4">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div />
        <button
          onClick={goToSocial}
          title="Open in Social"
          style={{ background: '#1e2030', border: '1px solid #2d3148', cursor: 'pointer', color: '#9ca3af', fontSize: '12px', fontWeight: 600, padding: '4px 12px', borderRadius: '6px', letterSpacing: '0.02em' }}
        >Detail ↗</button>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '32px', color: '#374151' }}>⏳ Analyzing sentiment signals...</div>
      )}
      {!loading && error && (
        <div style={{ textAlign: 'center', padding: '24px', color: '#6b7280', fontSize: '12px' }}>{error}</div>
      )}
      {!loading && forecast && (() => {
        const { prediction, platform_agreement, sentiment_now, similar_days, similar_stats, overall } = forecast;
        const isUp = prediction.direction === 'up';
        const conf = prediction.confidence;
        const heroColor = isUp ? '#26a69a' : '#ef5350';
        const heroBg = isUp ? '#26a69a12' : '#ef535012';
        const heroBorder = isUp ? '#26a69a33' : '#ef535033';

        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

            {/* Hero */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px', borderRadius: '8px', background: heroBg, border: `1px solid ${heroBorder}` }}>
              <span style={{ fontSize: '28px', color: heroColor }}>{isUp ? '↑' : '↓'}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '16px', fontWeight: 800, color: heroColor }}>{isUp ? 'BULLISH' : 'BEARISH'}</div>
                <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '2px' }}>
                  {(conf * 100).toFixed(0)}% confidence · Based on market data through {forecast.forecast_date} · Predicting next trading day {nextTradingDay(forecast.forecast_date)}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                {platform_agreement && (
                  <span style={{ fontSize: '10px', padding: '2px 7px', borderRadius: '4px', background: '#26a69a22', border: '1px solid #26a69a44', color: '#26a69a' }}>
                    ✓ Platforms agree
                  </span>
                )}
                <span style={{
                  fontSize: '10px', padding: '2px 8px', borderRadius: '4px', fontWeight: 700,
                  background: overall === 'bullish' ? '#26a69a18' : overall === 'bearish' ? '#ef535018' : '#88888818',
                  color:      overall === 'bullish' ? '#26a69a'   : overall === 'bearish' ? '#ef5350'   : '#888',
                  border: `1px solid ${overall === 'bullish' ? '#26a69a44' : overall === 'bearish' ? '#ef535044' : '#88888844'}`,
                }}>
                  {overall.toUpperCase()}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '14px' }}>

              {/* Sentiment Now */}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '9px', color: '#4b5563', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, marginBottom: '7px' }}>Sentiment Now</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {Object.entries(sentiment_now).map(([name, data]) => {
                    const up = data.sentiment > 0.05;
                    const down = data.sentiment < -0.05;
                    return (
                      <div key={name} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '5px 8px', background: '#0d0f17', borderRadius: '5px', fontSize: '11px' }}>
                        <span style={{ width: 48, color: PC[name], fontWeight: 700, fontSize: '10px' }}>{name}</span>
                        <span style={{ fontWeight: 700, color: up ? '#26a69a' : down ? '#ef5350' : '#6b7280' }}>
                          {up ? '▲' : down ? '▼' : '—'} {data.sentiment > 0 ? '+' : ''}{data.sentiment.toFixed(2)}
                        </span>
                        <span style={{ marginLeft: 'auto', color: '#374151', fontSize: '10px' }}>
                          {data.buzz.toFixed(0)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Similar Days */}
              {similar_days.length > 0 && (
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '9px', color: '#4b5563', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, marginBottom: '5px' }}>
                    Similar Days ({similar_stats.count})
                    {similar_stats.up_ratio !== null && (
                      <span style={{ color: similar_stats.up_ratio >= 0.5 ? '#26a69a' : '#ef5350', fontWeight: 600, marginLeft: 4 }}>
                        · {(similar_stats.up_ratio * 100).toFixed(0)}% ↑
                      </span>
                    )}
                    {similar_stats.avg_ret !== null && (
                      <span style={{ color: similar_stats.avg_ret >= 0 ? '#26a69a' : '#ef5350', fontWeight: 600, marginLeft: 4 }}>
                        avg {similar_stats.avg_ret >= 0 ? '+' : ''}{similar_stats.avg_ret.toFixed(1)}%
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    {similar_days.map((d, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '4px 6px', background: '#0d0f17', borderRadius: '4px', fontSize: '10px' }}>
                        <span style={{ color: '#6b7280' }}>{d.date}</span>
                        <span style={{ color: '#374151', marginLeft: 'auto' }}>{(d.similarity * 100).toFixed(0)}%</span>
                        <span style={{ fontWeight: 700, color: d.next_day_ret >= 0 ? '#26a69a' : '#ef5350' }}>
                          {d.next_day_ret >= 0 ? '+' : ''}{d.next_day_ret.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

          </div>
        );
      })()}
    </div>
  );
};
