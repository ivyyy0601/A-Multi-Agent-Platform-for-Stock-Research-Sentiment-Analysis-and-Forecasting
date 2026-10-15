import { useEffect, useState } from 'react';
import axios from 'axios';

interface Driver { name: string; value: number; z_score: number; importance: number; contribution: number; }
interface SimilarDay { date: string; similarity: number; next_day_ret: number; went_up: boolean; }
interface SentimentNow { sentiment: number; buzz: number; bullish: number; }

interface Forecast {
  ticker: string;
  forecast_date: string;
  prediction: {
    direction: 'up' | 'down';
    confidence: number;
    lr_p_up: number;
    cosine_up_ratio: number | null;
    cosine_avg_ret: number | null;
    cosine_weighted_ret?: number | null;
    model_accuracy: number | null;
    baseline_accuracy: number | null;
  };
  platform_agreement: boolean;
  sentiment_now: Record<string, SentimentNow>;
  similar_days: SimilarDay[];
  similar_stats: { count: number; up_ratio: number | null; avg_ret: number | null; weighted_avg_ret?: number | null };
  top_drivers: Driver[];
  overall: 'bullish' | 'bearish' | 'unclear';
}

const PLATFORM_COLORS: Record<string, string> = {
  reddit: '#ff6314', twitter: '#1d9bf0', news: '#a78bfa',
};

function PlatformBadge({ name, data }: { name: string; data: SentimentNow }) {
  const isUp = data.sentiment > 0.05;
  const isDown = data.sentiment < -0.05;
  return (
    <div className="sp-platform-badge">
      <span className="sp-platform-name" style={{ color: PLATFORM_COLORS[name] }}>{name}</span>
      <span className={`sp-platform-sent ${isUp ? 'up' : isDown ? 'down' : 'neutral'}`}>
        {isUp ? '▲' : isDown ? '▼' : '—'} {data.sentiment > 0 ? '+' : ''}{data.sentiment.toFixed(2)}
      </span>
      <span className="sp-platform-buzz">buzz {data.buzz.toFixed(0)}</span>
    </div>
  );
}

export default function SocialPrediction({ ticker }: { ticker: string }) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError('');
    axios.get(`/api/adanos/${ticker}/forecast`)
      .then(r => setForecast(r.data))
      .catch(e => setError(e.response?.data?.detail || 'No model yet'))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) return <div className="sp-wrap"><div className="sp-loading">Analyzing...</div></div>;
  if (error || !forecast) return (
    <div className="sp-wrap">
      <div className="sp-error">{error || 'No data'}</div>
      <div className="sp-hint">Run backfill + train first</div>
    </div>
  );

  const { prediction, platform_agreement, sentiment_now, similar_days, similar_stats, top_drivers, overall } = forecast;
  const isUp = prediction.direction === 'up';
  const conf = (prediction.confidence * 100).toFixed(0);
  const maxContrib = Math.max(...top_drivers.map(d => d.contribution), 0.01);

  const forecastDate = forecast.forecast_date;
  const nextDay = (() => {
    const d = new Date(forecastDate + 'T00:00:00');
    d.setDate(d.getDate() + 1);
    // Skip weekend
    if (d.getDay() === 6) d.setDate(d.getDate() + 2);
    if (d.getDay() === 0) d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  })();

  return (
    <div className="sp-wrap">
      {/* Hero */}
      <div className={`sp-hero ${isUp ? 'up' : 'down'}`}>
        <span className="sp-hero-arrow">{isUp ? '↑' : '↓'}</span>
        <div>
          <div className="sp-hero-dir">{isUp ? 'BULLISH' : 'BEARISH'}</div>
          <div className="sp-hero-sub">{conf}% confidence</div>
          <div className="sp-hero-dates">based on {forecastDate} → predicting {nextDay}</div>
        </div>
        {platform_agreement && (
          <span className="sp-agreement-badge">✓ All platforms agree</span>
        )}
      </div>

      {/* Signal breakdown */}
      <div className="sp-section-title">Signal Breakdown</div>
      <div className="sp-signals">
        {/* Logistic Regression */}
        {(() => {
          const lrUp = prediction.lr_p_up >= 0.5;
          const lrPct = lrUp ? prediction.lr_p_up : 1 - prediction.lr_p_up;
          return (
            <div className="sp-signal-row">
              <span className="sp-signal-label">ML Model</span>
              <div className="sp-signal-bar-track">
                <div className={`sp-signal-bar-fill ${lrUp ? 'up' : 'down'}`}
                  style={{ width: `${lrPct * 100}%` }} />
              </div>
              <span className={`sp-signal-pct ${lrUp ? 'up' : 'down'}`}>
                {lrUp ? '▲' : '▼'} {(lrPct * 100).toFixed(0)}%
              </span>
            </div>
          );
        })()}
        {/* Cosine similarity */}
        {prediction.cosine_weighted_ret !== null && prediction.cosine_weighted_ret !== undefined && (() => {
          const cosUp = prediction.cosine_weighted_ret >= 0;
          const cosPct = prediction.cosine_up_ratio !== null
            ? (cosUp ? prediction.cosine_up_ratio : 1 - prediction.cosine_up_ratio)
            : 0.5;
          return (
            <div className="sp-signal-row">
              <span className="sp-signal-label">Similar History</span>
              <div className="sp-signal-bar-track">
                <div className={`sp-signal-bar-fill ${cosUp ? 'up' : 'down'}`}
                  style={{ width: `${cosPct * 100}%` }} />
              </div>
              <span className={`sp-signal-pct ${cosUp ? 'up' : 'down'}`}>
                {cosUp ? '▲' : '▼'} {(cosPct * 100).toFixed(0)}%
                {prediction.cosine_weighted_ret !== null && (
                  <span className="sp-signal-ret">
                    {' '}weighted {prediction.cosine_weighted_ret >= 0 ? '+' : ''}{prediction.cosine_weighted_ret.toFixed(1)}%
                  </span>
                )}
              </span>
            </div>
          );
        })()}
        {/* Combined */}
        <div className="sp-signal-row sp-signal-combined">
          <span className="sp-signal-label">Combined</span>
          <div className="sp-signal-bar-track">
            <div className={`sp-signal-bar-fill ${isUp ? 'up' : 'down'}`}
              style={{ width: `${prediction.confidence * 100}%` }} />
          </div>
          <span className={`sp-signal-pct ${isUp ? 'up' : 'down'}`}>
            {isUp ? '▲' : '▼'} {conf}%
          </span>
        </div>
      </div>

      {/* Platform sentiment now */}
      <div className="sp-section-title">Platform Sentiment Now</div>
      <div className="sp-platforms">
        {Object.entries(sentiment_now).map(([name, data]) => (
          <PlatformBadge key={name} name={name} data={data} />
        ))}
      </div>

      {/* Top drivers */}
      {top_drivers.length > 0 && (
        <>
          <div className="sp-section-title">Top Drivers</div>
          <div className="sp-drivers">
            {top_drivers.slice(0, 6).map(d => (
              <div key={d.name} className="sp-driver-row">
                <span className="sp-driver-name">{d.name.replace(/_/g, ' ')}</span>
                <div className="sp-driver-track">
                  <div
                    className={`sp-driver-fill ${d.z_score >= 0 ? 'up' : 'down'}`}
                    style={{ width: `${(d.contribution / maxContrib) * 100}%` }}
                  />
                </div>
                <span className="sp-driver-val">
                  {d.value.toFixed(2)} ({d.z_score > 0 ? '+' : ''}{d.z_score.toFixed(1)}σ)
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Similar historical days */}
      {similar_days.length > 0 && (
        <>
          <div className="sp-section-title">
            Similar Days ({similar_stats.count})
            {similar_stats.weighted_avg_ret !== null && similar_stats.weighted_avg_ret !== undefined && (
              <span className="sp-sim-stats">
                <span className={similar_stats.weighted_avg_ret >= 0 ? 'up' : 'down'}>
                  · weighted {similar_stats.weighted_avg_ret > 0 ? '+' : ''}{similar_stats.weighted_avg_ret.toFixed(1)}%
                </span>
                {similar_stats.avg_ret !== null && (
                  <span className={similar_stats.avg_ret >= 0 ? 'up' : 'down'}> · avg {similar_stats.avg_ret > 0 ? '+' : ''}{similar_stats.avg_ret.toFixed(1)}%</span>
                )}
              </span>
            )}
          </div>
          <div className="sp-similar-list">
            {similar_days.map((d, i) => (
              <div key={i} className="sp-similar-row">
                <span className="sp-sim-date">{d.date}</span>
                <span className="sp-sim-match">{(d.similarity * 100).toFixed(0)}% match</span>
                <span className={`sp-sim-ret ${d.next_day_ret >= 0 ? 'up' : 'down'}`}>
                  {d.next_day_ret >= 0 ? '+' : ''}{d.next_day_ret.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Overall */}
      <div className={`sp-overall ${overall}`}>
        Multi-signal: {overall.toUpperCase()}
      </div>
    </div>
  );
}
