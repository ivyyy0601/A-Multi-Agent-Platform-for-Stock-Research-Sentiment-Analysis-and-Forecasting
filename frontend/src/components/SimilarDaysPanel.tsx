import { useState, useEffect } from 'react';
import axios from 'axios';

interface NewsSnippet {
  title: string;
  sentiment: string | null;
}

interface SimilarDay {
  date: string;
  similarity: number;
  numeric_sim: number;
  semantic_sim: number | null;
  sentiment_score: number;
  n_relevant: number;
  n_articles: number;
  ret_1d: number | null;
  ret_5d: number | null;
  rsi_14: number;
  volatility_5d: number | null;
  ma5_vs_ma20: number | null;
  ret_t1_after: number | null;
  ret_t5_after: number | null;
  news: NewsSnippet[];
}

interface SimilarDaysData {
  symbol: string;
  target_date: string;
  target_features: Record<string, number | null>;
  similar_days: SimilarDay[];
  hybrid: boolean;
  stats: {
    up_ratio_t1: number | null;
    up_ratio_t5: number | null;
    avg_ret_t1: number | null;
    avg_ret_t5: number | null;
    weighted_up_ratio_t1: number | null;
    weighted_up_ratio_t5: number | null;
    weighted_avg_ret_t1: number | null;
    weighted_avg_ret_t5: number | null;
    count: number;
  };
}

interface Props {
  symbol: string;
  date: string;
  onClose: () => void;
}

export default function SimilarDaysPanel({ symbol, date, onClose }: Props) {
  const [data, setData] = useState<SimilarDaysData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [daySummaries, setDaySummaries] = useState<Record<string, string>>({});
  const [dayLoading, setDayLoading] = useState<Record<string, boolean>>({});

  const handleDaySummary = async (day: SimilarDay) => {
    if (!data) return;
    setDayLoading(prev => ({ ...prev, [day.date]: true }));
    const targetNews = data.target_features;
    const simNews = day.news.slice(0, 3).map(n => n.title).join(' | ');
    const numericPct = (day.numeric_sim * 100).toFixed(0);
    const semanticPct = day.semantic_sim != null ? (day.semantic_sim * 100).toFixed(0) : null;
    const similarityExplanation = semanticPct != null
      ? `Technical features are ${numericPct}% similar (sentiment score, RSI, momentum, volatility nearly identical). News content themes are ${semanticPct}% similar — ${parseInt(semanticPct) >= 70 ? 'the news topics are closely related' : parseInt(semanticPct) >= 50 ? 'the news topics partially overlap' : 'the news topics are quite different despite similar technicals'}.`
      : `Technical features are ${numericPct}% similar (sentiment score, RSI, momentum, volatility nearly identical). News semantic score unavailable.`;

    const message = `${symbol} on ${date} vs ${day.date} — similarity breakdown:
${similarityExplanation}

${day.date} data:
- Sentiment: ${day.sentiment_score.toFixed(2)}, RSI: ${day.rsi_14.toFixed(0)}, ${day.n_relevant} relevant articles
- Prev 1D: ${day.ret_1d != null ? (day.ret_1d*100).toFixed(1)+'%' : 'N/A'}, Prev 5D: ${day.ret_5d != null ? (day.ret_5d*100).toFixed(1)+'%' : 'N/A'}
- News headlines: ${simNews || 'N/A'}
- Outcome: T+1 ${day.ret_t1_after != null ? (day.ret_t1_after >= 0 ? '+' : '')+day.ret_t1_after.toFixed(2)+'%' : 'N/A'}, T+5 ${day.ret_t5_after != null ? (day.ret_t5_after >= 0 ? '+' : '')+day.ret_t5_after.toFixed(2)+'%' : 'N/A'}

In 2-3 sentences: explain what drives the similarity between these two dates. If numeric is high but semantic is low, note that technicals match but news themes differ (or vice versa). Then comment on what the historical outcome suggests.`;

    try {
      const res = await axios.post('/api/v1/agent/chat', { message, context: { symbol } });
      setDaySummaries(prev => ({ ...prev, [day.date]: res.data.content || 'No response' }));
    } catch {
      setDaySummaries(prev => ({ ...prev, [day.date]: 'AI summary failed.' }));
    } finally {
      setDayLoading(prev => ({ ...prev, [day.date]: false }));
    }
  };

  useEffect(() => {
    setLoading(true);
    setError('');
    axios
      .get(`/api/predict/${symbol}/similar-days?date=${date}`)
      .then((res) => setData(res.data))
      .catch(() => setError('Failed to find similar days'))
      .finally(() => setLoading(false));
  }, [symbol, date]);

  return (
    <div className="news-panel">
      <div className="news-panel-header">
        <h2>Similar Days</h2>
        <span className="news-date-badge">{date}</span>
        <button className="range-clear-btn" onClick={onClose}>Close</button>
      </div>

      {loading ? (
        <div className="news-empty">
          <div className="range-loading">
            <div className="range-spinner" />
            <span>Finding similar days...</span>
          </div>
        </div>
      ) : error ? (
        <div className="news-empty">{error}</div>
      ) : data ? (
        <div className="news-list">
          {/* Target day info */}
          <div className="sim-target-card">
            <div className="sim-section-label">Today Features</div>
            <div className="sim-feat-grid">
              <div className="sim-feat">
                <span className="sim-feat-label">Sentiment</span>
                <span className={`sim-feat-val ${(data.target_features.sentiment_score ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {(data.target_features.sentiment_score ?? 0).toFixed(2)}
                </span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">Relevant</span>
                <span className="sim-feat-val">{data.target_features.n_relevant ?? 0}</span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">RSI</span>
                <span className="sim-feat-val">{(data.target_features.rsi_14 ?? 0).toFixed(0)}</span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">Prev 1D</span>
                <span className={`sim-feat-val ${(data.target_features.ret_1d ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {((data.target_features.ret_1d ?? 0) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">Prev 5D</span>
                <span className={`sim-feat-val ${(data.target_features.ret_5d ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {((data.target_features.ret_5d ?? 0) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">Vol 5D</span>
                <span className="sim-feat-val">
                  {((data.target_features.volatility_5d ?? 0) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">MA5 vs 20</span>
                <span className={`sim-feat-val ${(data.target_features.ma5_vs_ma20 ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {((data.target_features.ma5_vs_ma20 ?? 0) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="sim-feat">
                <span className="sim-feat-label">Momentum</span>
                <span className={`sim-feat-val ${(data.target_features.sentiment_momentum_3d ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {(data.target_features.sentiment_momentum_3d ?? 0).toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* Stats summary */}
          <div className="sim-stats-card">
            <div className="sim-section-label">Historical Pattern ({data.stats.count} similar days)</div>
            <div className="sim-stats-grid">
              <div className="sim-stat-block">
                <span className="sim-stat-title">T+1 Up Ratio</span>
                <span className="sim-stat-sub" style={{ display: 'block', fontSize: '10px', color: '#6b7280', marginTop: '2px' }}>
                  Frequency
                </span>
                <span className={`sim-stat-big ${((data.stats.weighted_up_ratio_t1 ?? data.stats.up_ratio_t1) ?? 0) >= 0.5 ? 'up' : 'down'}`}>
                  {(data.stats.weighted_up_ratio_t1 ?? data.stats.up_ratio_t1) !== null ? `${(((data.stats.weighted_up_ratio_t1 ?? data.stats.up_ratio_t1) ?? 0) * 100).toFixed(0)}%` : '-'}
                </span>
              </div>
              <div className="sim-stat-block">
                <span className="sim-stat-title">T+5 Up Ratio</span>
                <span className="sim-stat-sub" style={{ display: 'block', fontSize: '10px', color: '#6b7280', marginTop: '2px' }}>
                  Frequency
                </span>
                <span className={`sim-stat-big ${((data.stats.weighted_up_ratio_t5 ?? data.stats.up_ratio_t5) ?? 0) >= 0.5 ? 'up' : 'down'}`}>
                  {(data.stats.weighted_up_ratio_t5 ?? data.stats.up_ratio_t5) !== null ? `${(((data.stats.weighted_up_ratio_t5 ?? data.stats.up_ratio_t5) ?? 0) * 100).toFixed(0)}%` : '-'}
                </span>
              </div>
              <div className="sim-stat-block">
                <span className="sim-stat-title">Avg T+1</span>
                <span className={`sim-stat-big ${((data.stats.weighted_avg_ret_t1 ?? data.stats.avg_ret_t1) ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {(data.stats.weighted_avg_ret_t1 ?? data.stats.avg_ret_t1) !== null ? `${((data.stats.weighted_avg_ret_t1 ?? data.stats.avg_ret_t1) ?? 0) >= 0 ? '+' : ''}${((data.stats.weighted_avg_ret_t1 ?? data.stats.avg_ret_t1) ?? 0).toFixed(2)}%` : '-'}
                </span>
              </div>
              <div className="sim-stat-block">
                <span className="sim-stat-title">Avg T+5</span>
                <span className={`sim-stat-big ${((data.stats.weighted_avg_ret_t5 ?? data.stats.avg_ret_t5) ?? 0) >= 0 ? 'up' : 'down'}`}>
                  {(data.stats.weighted_avg_ret_t5 ?? data.stats.avg_ret_t5) !== null ? `${((data.stats.weighted_avg_ret_t5 ?? data.stats.avg_ret_t5) ?? 0) >= 0 ? '+' : ''}${((data.stats.weighted_avg_ret_t5 ?? data.stats.avg_ret_t5) ?? 0).toFixed(2)}%` : '-'}
                </span>
              </div>
            </div>
          </div>

          {/* Similar days list */}
          <div className="sim-section-label" style={{ padding: '8px 4px 4px' }}>Similar Days</div>
          {data.similar_days.map((day) => (
            <div key={day.date} className="sim-day-card">
              <div className="sim-day-header">
                <span className="sim-day-date">{day.date}</span>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                  <span className="sim-day-chip neutral" title="Numeric similarity (price + sentiment features)">
                    📊 {(day.numeric_sim * 100).toFixed(0)}%
                  </span>
                  {day.semantic_sim !== null && (
                    <span className="sim-day-chip neutral" title="Semantic similarity (news text meaning)">
                      💬 {(day.semantic_sim * 100).toFixed(0)}%
                    </span>
                  )}
                  <span className="sim-day-score" title={day.semantic_sim !== null ? 'Combined score (0.65×numeric + 0.35×semantic)' : 'Numeric similarity only'}>
                    = {(day.similarity * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              <div className="sim-day-details">
                <span className={`sim-day-chip ${day.sentiment_score >= 0 ? 'up' : 'down'}`}>
                  sent {day.sentiment_score.toFixed(2)}
                </span>
                <span className="sim-day-chip neutral">
                  {day.n_relevant} rel
                </span>
                <span className="sim-day-chip neutral">
                  RSI {day.rsi_14.toFixed(0)}
                </span>
                {day.ret_1d !== null && (
                  <span className={`sim-day-chip ${day.ret_1d >= 0 ? 'up' : 'down'}`}>
                    1D {(day.ret_1d * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="sim-day-returns">
                <span className="sim-day-ret-label">After:</span>
                {day.ret_t1_after !== null && (
                  <span className={`sim-day-ret ${day.ret_t1_after >= 0 ? 'up' : 'down'}`}>
                    T+1 {day.ret_t1_after >= 0 ? '+' : ''}{day.ret_t1_after.toFixed(2)}%
                  </span>
                )}
                {day.ret_t5_after !== null && (
                  <span className={`sim-day-ret ${day.ret_t5_after >= 0 ? 'up' : 'down'}`}>
                    T+5 {day.ret_t5_after >= 0 ? '+' : ''}{day.ret_t5_after.toFixed(2)}%
                  </span>
                )}
              </div>
              {day.news && day.news.length > 0 && (
                <div className="sim-day-news">
                  {day.news.map((n, i) => (
                    <div key={i} className="sim-day-news-item">
                      <span className={`sentiment-dot ${n.sentiment || 'neutral'}`} />
                      <span className="sim-day-news-title">{n.title}</span>
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={() => handleDaySummary(day)}
                disabled={dayLoading[day.date]}
                style={{
                  marginTop: '8px', width: '100%', padding: '5px',
                  borderRadius: '4px', background: dayLoading[day.date] ? '#374151' : '#1e3a5f',
                  color: '#93c5fd', border: '1px solid #1d4ed8',
                  cursor: dayLoading[day.date] ? 'wait' : 'pointer', fontSize: '12px',
                }}
              >
                {dayLoading[day.date] ? 'Analyzing...' : 'Why similar?'}
              </button>
              {daySummaries[day.date] && (
                <div style={{
                  marginTop: '6px', padding: '8px 10px', borderRadius: '4px',
                  background: '#1f2937', color: '#d1d5db', fontSize: '12px',
                  lineHeight: '1.6', whiteSpace: 'pre-wrap',
                }}>
                  {daySummaries[day.date]}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
