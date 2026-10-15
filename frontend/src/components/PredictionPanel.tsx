import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';

interface Driver {
  name: string;
  value: number;
  importance: number;
  z_score: number;
  contribution: number;
}

interface HorizonPrediction {
  direction: 'up' | 'down';
  confidence: number;
  model_type?: string;
  top_drivers: Driver[];
  model_accuracy: number | null;
  baseline_accuracy: number | null;
}

interface SimilarPeriod {
  period_start: string;
  period_end: string;
  similarity: number;
  avg_sentiment: number;
  n_relevant: number;
  ret_after_horizon: number | null;
}

interface Headline {
  date: string;
  title: string;
  sentiment: string;
  summary: string;
}

interface ImpactArticle {
  news_id: string;
  date: string;
  title: string;
  sentiment: string;
  relevance: string | null;
  key_discussion: string;
  ret_t0: number | null;
  ret_t1: number | null;
  article_url: string | null;
}

interface NewsSummary {
  total: number;
  positive: number;
  negative: number;
  neutral: number;
  sentiment_ratio: number;
  top_headlines: Headline[];
  top_impact: ImpactArticle[];
}

interface SimilarStats {
  count: number;
  horizon_days: number;
  up_ratio: number | null;
  avg_ret: number | null;
  weighted_up_ratio: number | null;
  weighted_avg_ret: number | null;
}

interface SimilarDaySnapshot {
  date: string;
  similarity: number;
  sentiment_score: number;
  n_relevant: number;
  ret_after_horizon: number | null;
  ret_t1_after: number | null;
}

interface SimilarDaysApiData {
  similar_days: SimilarDaySnapshot[];
  stats: {
    count: number;
    up_ratio_t1: number | null;
    avg_ret_t1: number | null;
    weighted_up_ratio_t1: number | null;
    weighted_avg_ret_t1: number | null;
  };
}

interface DeepAnalysis {
  news_id: string;
  discussion: string;
  growth_reasons: string;
  decrease_reasons: string;
}

interface Forecast {
  symbol: string;
  window_days: number;
  horizon_key: string;
  forecast_date: string;
  news_summary: NewsSummary;
  prediction: Record<string, HorizonPrediction>;
  similar_periods: SimilarPeriod[];
  similar_stats: SimilarStats;
  conclusion: string;
}

interface Props {
  symbol: string;
  refDate?: string;
}

interface CombinedSignal {
  direction: 'up' | 'down';
  confidence: number;
  similarityDirection: 'up' | 'down' | null;
  similarityProbability: number | null;
  mlEdge: number | null;
  mlWeight: number;
  simWeight: number;
  mlDirection: 'up' | 'down' | null;
  mlProbability: number | null;
}

async function fetchForecast(symbol: string, windowDays: 1 | 7 | 14, refDate?: string): Promise<Forecast | null> {
  const params = { window: windowDays, date: refDate || undefined };
  try {
    const res = await axios.get(`/api/predict/${symbol}/forecast`, { params });
    return res.data as Forecast;
  } catch {
    return null;
  }
}

function extractKeywords(headlines: Headline[]): string[] {
  const stopwords = new Set([
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought',
    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
    'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'out', 'off', 'over', 'under', 'again', 'further',
    'then', 'once', 'and', 'but', 'or', 'nor', 'not', 'so', 'yet',
    'both', 'either', 'neither', 'each', 'every', 'all', 'any',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'only',
    'own', 'same', 'than', 'too', 'very', 'just', 'because', 'about',
    'up', 'its', 'it', 'this', 'that', 'these', 'those', 'he', 'she',
    'they', 'them', 'their', 'what', 'which', 'who', 'whom', 'how',
    'new', 'says', 'said', 'also', 'like', 'now', 'one', 'two',
    'get', 'got', 'make', 'go', 'going', 'set', 'see', 'big', 'still',
  ]);

  const freq = new Map<string, number>();
  for (const h of headlines) {
    const words = h.title.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/);
    const seen = new Set<string>();
    for (const w of words) {
      if (w.length < 3 || stopwords.has(w) || seen.has(w)) continue;
      seen.add(w);
      freq.set(w, (freq.get(w) || 0) + 1);
    }
  }

  return Array.from(freq.entries())
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([w]) => w);
}

/**
 * Parse conclusion text and return styled JSX:
 * - [ModelName] → bold purple badge
 * - bullish/leaning bullish → green bold
 * - bearish/leaning bearish → red bold
 * - +N% / -N% / N% → colored by sign
 * - positive → green, negative → red
 */
function renderStyledText(text: string): React.ReactNode[] {
  // Regex that matches all the patterns we want to style
  const pattern = /(\[[^\]]+\])|(bullish|leaning bullish|Bullish)|(bearish|leaning bearish|Bearish)|(positive)|(negative)|([+-]?\d+\.?\d*%)/gi;

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    // Push the plain text before this match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const [full, model, bullish, bearish, positive, negative, pct] = match;

    if (model) {
      // Hide model names like [XGBoost] — just skip them
      key++;
    } else if (bullish) {
      parts.push(
        <span key={key++} className="fc-text-bull">{full}</span>
      );
    } else if (bearish) {
      parts.push(
        <span key={key++} className="fc-text-bear">{full}</span>
      );
    } else if (positive) {
      parts.push(
        <span key={key++} className="fc-text-bull">{full}</span>
      );
    } else if (negative) {
      parts.push(
        <span key={key++} className="fc-text-bear">{full}</span>
      );
    } else if (pct) {
      const isNeg = pct.startsWith('-');
      parts.push(
        <span key={key++} className={isNeg ? 'fc-text-pct-down' : 'fc-text-pct-up'}>{full}</span>
      );
    }

    lastIndex = match.index + full.length;
  }

  // Remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function buildCombinedSignal(
  pred: HorizonPrediction | undefined,
  stats: SimilarStats
): CombinedSignal | null {
  const simProb = stats.weighted_up_ratio ?? stats.up_ratio;
  if (simProb == null) return null;

  const similarityDirection: 'up' | 'down' = simProb >= 0.5 ? 'up' : 'down';
  const mlEdge =
    pred?.model_accuracy != null && pred?.baseline_accuracy != null
      ? pred.model_accuracy - pred.baseline_accuracy
      : null;
  const mlUpProb = pred ? (pred.direction === 'up' ? pred.confidence : 1 - pred.confidence) : null;
  const mlDirection: 'up' | 'down' | null =
    mlUpProb == null ? null : (mlUpProb >= 0.5 ? 'up' : 'down');

  let mlWeight = 0;
  if (pred && mlEdge != null) {
    if (mlEdge <= -0.15) mlWeight = 0.08;
    else if (mlEdge <= -0.05) mlWeight = 0.15;
    else if (mlEdge <= 0) mlWeight = 0.20;
    else if (mlEdge <= 0.05) mlWeight = 0.30;
    else mlWeight = 0.40;
  }
  if (mlDirection && mlDirection === similarityDirection) {
    mlWeight = Math.min(0.50, mlWeight + 0.08);
  } else if (mlDirection && mlDirection !== similarityDirection) {
    mlWeight = Math.max(0.05, mlWeight - 0.04);
  }
  const simWeight = 1 - mlWeight;
  let upProb = simProb;
  if (mlUpProb != null && mlWeight > 0) {
    upProb = simWeight * simProb + mlWeight * mlUpProb;
  }

  return {
    direction: upProb >= 0.5 ? 'up' : 'down',
    confidence: Math.max(upProb, 1 - upProb),
    similarityDirection,
    similarityProbability: simProb,
    mlEdge,
    mlWeight,
    simWeight,
    mlDirection,
    mlProbability: mlUpProb,
  };
}

export default function PredictionPanel({ symbol, refDate }: Props) {
  const [forecast1, setForecast1] = useState<Forecast | null>(null);
  const [forecast7, setForecast7] = useState<Forecast | null>(null);
  const [forecast14, setForecast14] = useState<Forecast | null>(null);
  const [similar1D, setSimilar1D] = useState<SimilarDaysApiData | null>(null);
  const [forecastCache, setForecastCache] = useState<Record<string, {
    f1: Forecast | null;
    f7: Forecast | null;
    f14: Forecast | null;
  }>>({});
  const [activeWindow, setActiveWindow] = useState<1 | 7 | 14>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(true);

  // Deep analysis state
  const [deepLoading, setDeepLoading] = useState<string | null>(null);
  const [deepResults, setDeepResults] = useState<Record<string, DeepAnalysis>>({});
  const [deepErrors, setDeepErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    setError('');
    const cacheKey = `${symbol}|${refDate || 'latest'}`;
    const cached = forecastCache[cacheKey];
    Promise.all([
      fetchForecast(symbol, 1, refDate),
      fetchForecast(symbol, 7, refDate),
      fetchForecast(symbol, 14, refDate),
    ])
      .then(([f1, f7, f14]) => {
        const next1 = f1 || cached?.f1 || null;
        const next7 = f7 || cached?.f7 || null;
        const next14 = f14 || cached?.f14 || null;

        setForecast1(next1);
        setForecast7(next7);
        setForecast14(next14);

        if (f1 || f7 || f14) {
          setForecastCache((prev) => ({
            ...prev,
            [cacheKey]: {
              f1: f1 || prev[cacheKey]?.f1 || null,
              f7: f7 || prev[cacheKey]?.f7 || null,
              f14: f14 || prev[cacheKey]?.f14 || null,
            },
          }));
        }

        if (!next1 && !next7 && !next14) {
          setError('No model available');
        } else if (f1 && f7 && f14) {
          setError('');
        } else if (!f1 || !f7 || !f14) {
          setError('Showing latest available forecast');
        }
      })
      .finally(() => setLoading(false));
  }, [symbol, refDate]);

  useEffect(() => {
    if (!symbol || !refDate) {
      setSimilar1D(null);
      return;
    }
    axios
      .get(`/api/predict/${symbol}/similar-days?date=${refDate}`)
      .then((res) => setSimilar1D(res.data as SimilarDaysApiData))
      .catch(() => setSimilar1D(null));
  }, [symbol, refDate]);

  const keywords = useMemo(() => {
    const fc = forecast1 || forecast7 || forecast14;
    if (!fc) return [];
    return extractKeywords(fc.news_summary.top_headlines);
  }, [forecast1, forecast7, forecast14]);

  const activeForecast =
    activeWindow === 1 ? (forecast1 || forecast7 || forecast14) :
    activeWindow === 7 ? (forecast7 || forecast1 || forecast14) :
    (forecast14 || forecast7 || forecast1);
  const primaryForecast = activeForecast;
  const primary = primaryForecast
    ? (primaryForecast.prediction.t1 || primaryForecast.prediction.t7 || primaryForecast.prediction.t14)
    : null;
  const isUp = primary?.direction === 'up';
  const ns = primaryForecast?.news_summary;

  if (loading) {
    return (
      <div className="pred-panel">
        <div className="pred-header" onClick={() => setExpanded(!expanded)}>
          <span className="pred-title">Forecast</span>
          <span className="pred-loading-dot" />
          <span className="pred-loading-text">Analyzing recent news...</span>
        </div>
      </div>
    );
  }

  if (error || (!forecast1 && !forecast7 && !forecast14)) {
    return (
      <div className="pred-panel">
        <div className="pred-header">
          <span className="pred-title">Forecast</span>
          <span className="pred-no-model">{error || 'No data'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`pred-panel ${expanded ? 'pred-expanded' : ''}`}>
      {/* Header bar */}
      <div className="pred-header" onClick={() => setExpanded(!expanded)}>
        <span className="pred-title">Forecast</span>
        <div className="pred-window-toggle" onClick={(e) => e.stopPropagation()}>
          <button
            className={`pred-window-btn ${activeWindow === 1 ? 'active' : ''}`}
            onClick={() => setActiveWindow(1)}
          >1D</button>
          <button
            className={`pred-window-btn ${activeWindow === 7 ? 'active' : ''}`}
            onClick={() => setActiveWindow(7)}
          >7D</button>
          <button
            className={`pred-window-btn ${activeWindow === 14 ? 'active' : ''}`}
            onClick={() => setActiveWindow(14)}
          >14D</button>
        </div>
        {primary && (
          <>
            <div className={`pred-arrow ${isUp ? 'up' : 'down'}`}>
              {isUp ? '\u2191' : '\u2193'}
            </div>
            <span className={`pred-dir ${isUp ? 'up' : 'down'}`}>
              {primary.direction.toUpperCase()}
            </span>
            <div className="pred-conf-bar">
              <div
                className={`pred-conf-fill ${isUp ? 'up' : 'down'}`}
                style={{ width: `${primary.confidence * 100}%` }}
              />
              <span className="pred-conf-label">{(primary.confidence * 100).toFixed(0)}%</span>
            </div>
          </>
        )}

        {ns && (
          <span className="pred-news-badge">
            {ns.total} news · {ns.positive}+ {ns.negative}-
          </span>
        )}

        <span className="pred-expand-icon">{expanded ? '\u25B2' : '\u25BC'}</span>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="pred-details">
          {/* Keyword tags (shared, show once) */}
          {keywords.length > 0 && (
            <div className="fc-keywords-section">
              <div className="fc-section-title">Key Topics</div>
              <div className="fc-keywords">
                {keywords.map((kw) => (
                  <span key={kw} className="fc-keyword-pill">{kw}</span>
                ))}
              </div>
            </div>
          )}

          {activeForecast && (
            <ForecastSection
              key={activeForecast.window_days}
              label={`${activeForecast.window_days}D`}
              forecast={activeForecast}
              exactSimilar1D={activeForecast.window_days === 1 ? similar1D : null}
              symbol={symbol}
              deepLoading={deepLoading}
              deepResults={deepResults}
              deepErrors={deepErrors}
              setDeepLoading={setDeepLoading}
              setDeepResults={setDeepResults}
              setDeepErrors={setDeepErrors}
            />
          )}
        </div>
      )}
    </div>
  );
}

function ForecastSection({
  label,
  forecast,
  exactSimilar1D,
  symbol,
  deepLoading,
  deepResults,
  deepErrors,
  setDeepLoading,
  setDeepResults,
  setDeepErrors,
}: {
  label: string;
  forecast: Forecast;
  exactSimilar1D: SimilarDaysApiData | null;
  symbol: string;
  deepLoading: string | null;
  deepResults: Record<string, DeepAnalysis>;
  deepErrors: Record<string, string>;
  setDeepLoading: (id: string | null) => void;
  setDeepResults: React.Dispatch<React.SetStateAction<Record<string, DeepAnalysis>>>;
  setDeepErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}) {
  const horizonKey = forecast.horizon_key;
  const primary = forecast.prediction[horizonKey];
  const ns = forecast.news_summary;
  const stats = exactSimilar1D
    ? {
        count: exactSimilar1D.stats.count,
        horizon_days: 1,
        up_ratio: exactSimilar1D.stats.up_ratio_t1,
        avg_ret: exactSimilar1D.stats.avg_ret_t1,
        weighted_up_ratio: exactSimilar1D.stats.weighted_up_ratio_t1,
        weighted_avg_ret: exactSimilar1D.stats.weighted_avg_ret_t1,
      }
    : forecast.similar_stats;
  const similarPeriods = exactSimilar1D
    ? exactSimilar1D.similar_days.map((day) => ({
        period_start: day.date,
        period_end: day.date,
        similarity: day.similarity,
        avg_sentiment: day.sentiment_score,
        n_relevant: day.n_relevant,
        ret_after_horizon: day.ret_t1_after ?? day.ret_after_horizon,
      }))
    : forecast.similar_periods;
  const combined = buildCombinedSignal(primary, stats);
  const combinedUp = combined?.direction === 'up';

  const conclusionBullets = forecast.conclusion
    ? forecast.conclusion.split(/(?<=[.!?])\s+/).filter((s) => s.trim().length > 0)
    : [];

  return (
    <div className="fc-section-block">
      <div className="fc-section-divider">
        {label} Forecast
        {forecast.forecast_date && (
          <span style={{ fontSize: '11px', color: '#888', marginLeft: '8px', fontWeight: 'normal' }}>
            Based on market data through {forecast.forecast_date}
          </span>
        )}
      </div>

      {/* AI Prediction Hero */}
      {combined && (
        <div className={`fc-hero ${combinedUp ? 'fc-hero-up' : 'fc-hero-down'}`}>
          <span className="fc-hero-arrow">{combinedUp ? '\u2191' : '\u2193'}</span>
          <div className="fc-hero-text">
            <span className="fc-hero-label">{label} Combined:</span>
            <span className="fc-hero-dir">{combinedUp ? 'Bullish' : 'Bearish'}</span>
          </div>
          <span className="fc-hero-conf">{(combined.confidence * 100).toFixed(0)}%</span>
        </div>
      )}

      {/* Structured analysis bullets */}
      {conclusionBullets.length > 0 && (
        <div className="fc-analysis">
          <div className="fc-section-title">Analysis</div>
          <ul className="fc-bullet-list">
            {conclusionBullets.map((bullet, i) => (
              <li key={i} className="fc-bullet-item">{renderStyledText(bullet)}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Combined explanation */}
      {combined && (
        <div className="fc-analysis" style={{ marginTop: 8 }}>
          <div className="fc-section-title">Combined Judgment</div>
          <ul className="fc-bullet-list">
            <li className="fc-bullet-item">
              Similarity leans <strong>{combined.similarityDirection === 'up' ? 'bullish' : 'bearish'}</strong>
              {combined.similarityProbability != null ? ` (${(combined.similarityProbability * 100).toFixed(0)}% up-ratio signal).` : '.'}
            </li>
            <li className="fc-bullet-item">
              {combined.mlDirection
                ? `ML leans ${combined.mlDirection === 'up' ? 'bullish' : 'bearish'} and contributes ${(combined.mlWeight * 100).toFixed(0)}% of the final signal (${combined.mlEdge != null ? `${combined.mlEdge >= 0 ? '+' : ''}${(combined.mlEdge * 100).toFixed(1)}pp vs baseline` : 'no baseline info'}).`
                : 'No ML contribution available for this horizon.'}
            </li>
          </ul>
        </div>
      )}

      {/* Prediction cards */}
      {primary && (
        <div className="fc-predictions">
          <PredictionCard label={`${forecast.window_days}D ML`} pred={primary} />
        </div>
      )}

      {/* Similar historical days */}
      {stats.count > 0 && (
        <div className="fc-similar-section">
          <div className="fc-section-title">Similarity Prediction ({stats.count} similar days)</div>
          <div className="fc-similar-stats">
            <div className="fc-stat">
              <span className="fc-stat-label">Up Ratio</span>
              <span className="fc-stat-sub" style={{ display: 'block', fontSize: '10px', color: '#6b7280', marginTop: '2px' }}>
                Frequency
              </span>
              <span className={`fc-stat-value ${((stats.weighted_up_ratio ?? stats.up_ratio) ?? 0) > 0.5 ? 'up' : 'down'}`}>
                {((stats.weighted_up_ratio ?? stats.up_ratio) ?? 0) !== null ? `${((((stats.weighted_up_ratio ?? stats.up_ratio) ?? 0) * 100)).toFixed(0)}%` : '-'}
              </span>
            </div>
            <div className="fc-stat">
              <span className="fc-stat-label">Avg Return</span>
              <span className={`fc-stat-value ${((stats.weighted_avg_ret ?? stats.avg_ret) ?? 0) >= 0 ? 'up' : 'down'}`}>
                {(stats.weighted_avg_ret ?? stats.avg_ret) != null ? `${(stats.weighted_avg_ret ?? stats.avg_ret)! >= 0 ? '+' : ''}${(stats.weighted_avg_ret ?? stats.avg_ret)!.toFixed(1)}%` : '-'}
              </span>
            </div>
          </div>

          <div className="fc-periods-list">
            {similarPeriods.slice(0, 5).map((p, i) => (
              <div key={i} className="fc-period-card">
                <div className="fc-period-header">
                  <span className="fc-period-dates">{p.period_start}</span>
                  <span className="fc-period-sim">{(p.similarity * 100).toFixed(0)}% match</span>
                </div>
                <div className="fc-period-detail">
                  <span>{p.n_relevant} relevant</span>
                  <span>Sentiment: {p.avg_sentiment >= 0 ? '+' : ''}{p.avg_sentiment.toFixed(2)}</span>
                  {p.ret_after_horizon != null && (
                    <span className={p.ret_after_horizon >= 0 ? 'up' : 'down'}>
                      {forecast.window_days}D: {p.ret_after_horizon >= 0 ? '+' : ''}{p.ret_after_horizon.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top Impact News */}
      {ns.top_impact && ns.top_impact.length > 0 && (
        <div className="fc-impact-section">
          <div className="fc-section-title">Key Impact News</div>
          <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          {ns.top_impact.map((article) => {
            const retClass = (article.ret_t0 ?? 0) >= 0 ? 'up' : 'down';
            const deep = deepResults[article.news_id];
            const deepError = deepErrors[article.news_id];
            const isAnalyzing = deepLoading === article.news_id;
            return (
              <div key={article.news_id} className={`fc-impact-card fc-impact-${retClass}`}>
                <div className="fc-impact-header">
                  <span className={`fc-impact-ret ${retClass}`}>
                    {article.ret_t0 != null ? `${article.ret_t0 >= 0 ? '+' : ''}${article.ret_t0.toFixed(2)}%` : '-'}
                  </span>
                  <span className={`fc-impact-sentiment ${article.sentiment || 'unknown'}`}>
                    {article.sentiment === 'positive' ? 'Bullish' : article.sentiment === 'negative' ? 'Bearish' : article.sentiment === 'neutral' ? 'Neutral' : 'N/A'}
                  </span>
                  <span className="fc-impact-date">{article.date}</span>
                </div>
                <div className="fc-impact-title">
                  {article.article_url ? (
                    <a href={article.article_url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}>
                      {article.title}
                    </a>
                  ) : article.title}
                </div>
                {article.key_discussion && (
                  <div className="fc-impact-summary">{article.key_discussion}</div>
                )}
                {deep ? (
                  <div className="fc-deep-result">
                    <div className="fc-deep-discussion">{deep.discussion}</div>
                    {deep.growth_reasons && (
                      <div className="fc-deep-reasons fc-deep-bull">
                        <span className="fc-deep-reasons-label">{'▲ Bullish Factors'}</span>
                        <div className="fc-deep-reasons-text">{deep.growth_reasons}</div>
                      </div>
                    )}
                    {deep.decrease_reasons && (
                      <div className="fc-deep-reasons fc-deep-bear">
                        <span className="fc-deep-reasons-label">{'▼ Risk Factors'}</span>
                        <div className="fc-deep-reasons-text">{deep.decrease_reasons}</div>
                      </div>
                    )}
                  </div>
                ) : deepError ? (
                  <div className="fc-deep-result">
                    <div className="fc-deep-reasons fc-deep-bear">
                      <span className="fc-deep-reasons-label">AI unavailable</span>
                      <div className="fc-deep-reasons-text">{deepError}</div>
                    </div>
                  </div>
                ) : (
                  <button
                    className="fc-deep-btn"
                    disabled={isAnalyzing}
                    onClick={() => {
                      setDeepLoading(article.news_id);
                      setDeepErrors((prev) => {
                        const next = { ...prev };
                        delete next[article.news_id];
                        return next;
                      });
                      axios
                        .post('/api/analysis/deep', { news_id: article.news_id, symbol })
                        .then((res) => {
                          setDeepResults((prev) => ({ ...prev, [article.news_id]: res.data }));
                        })
                        .catch((err) => {
                          const msg =
                            err?.response?.data?.detail ||
                            err?.response?.data?.error ||
                            'Deep analysis failed';
                          setDeepErrors((prev) => ({ ...prev, [article.news_id]: msg }));
                        })
                        .finally(() => setDeepLoading(null));
                    }}
                  >
                    {isAnalyzing ? 'Analyzing...' : '🔍 AI Deep Analysis'}
                  </button>
                )}
              </div>
            );
          })}
          </div>
        </div>
      )}

    </div>
  );
}

function PredictionCard({ label, pred }: { label: string; pred: HorizonPrediction }) {
  const isUp = pred.direction === 'up';
  const hasAccuracy = pred.model_accuracy != null && pred.baseline_accuracy != null;
  const lift = hasAccuracy ? (pred.model_accuracy! - pred.baseline_accuracy!) : 0;
  const beatsBaseline = hasAccuracy ? lift > 0 : false;
  const maxContrib = pred.top_drivers.length > 0
    ? Math.max(...pred.top_drivers.map((d) => d.contribution), 0.01)
    : 0.01;

  return (
    <div className={`fc-pred-card ${isUp ? 'up' : 'down'}`}>
      <div className="fc-pred-header">
        <span className="fc-pred-label">{label}</span>
        {/* model_type hidden — show generic "AI" label */}
        <span className={`fc-pred-dir ${isUp ? 'up' : 'down'}`}>
          {isUp ? '\u2191' : '\u2193'} {pred.direction.toUpperCase()}
        </span>
      </div>
      {hasAccuracy && (
        <div className="fc-pred-meta">
          Conf {(pred.confidence * 100).toFixed(0)}% · Acc {(pred.model_accuracy! * 100).toFixed(1)}% / Base {(pred.baseline_accuracy! * 100).toFixed(1)}% / Lift {lift >= 0 ? '+' : ''}{(lift * 100).toFixed(1)}pp
          {!beatsBaseline && ' · below baseline'}
        </div>
      )}
      {pred.top_drivers.length > 0 && (
        <div className="fc-drivers">
          {pred.top_drivers.slice(0, 4).map((d) => (
            <div key={d.name} className="fc-driver-row">
              <span className="fc-driver-name">{d.name}</span>
              <div className="fc-driver-bar-track">
                <div
                  className={`fc-driver-bar-fill ${d.z_score > 0 ? 'up' : 'down'}`}
                  style={{ width: `${(d.contribution / maxContrib) * 100}%` }}
                />
              </div>
              <span className="fc-driver-val">
                {d.value.toFixed(2)} ({d.z_score > 0 ? '+' : ''}{d.z_score.toFixed(1)}\u03C3)
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
