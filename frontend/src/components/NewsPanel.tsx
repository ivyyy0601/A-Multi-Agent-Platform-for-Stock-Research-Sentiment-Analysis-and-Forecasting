import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

interface NewsItem {
  news_id: string;
  trade_date: string;
  published_utc: string;
  title: string;
  description: string;
  publisher: string;
  article_url: string;
  image_url: string | null;
  relevance: string | null;
  key_discussion: string | null;
  sentiment: string | null;
  reason_growth: string | null;
  reason_decrease: string | null;
  ret_t0: number | null;
  ret_t1: number | null;
  ret_t3: number | null;
  ret_t5: number | null;
  ret_t10: number | null;
}

interface Props {
  symbol: string;
  hoveredDate: string | null;
  onFindSimilar?: (newsId: string) => void;
  highlightedNewsId?: string | null;
  isLocked?: boolean;
  onUnlock?: () => void;
  sourceFilter?: 'all' | 'news' | 'reddit';
  onSourceFilterChange?: (f: 'all' | 'news' | 'reddit') => void;
  sentimentFilter?: 'all' | 'positive' | 'negative' | 'neutral';
  onSentimentFilterChange?: (f: 'all' | 'positive' | 'negative' | 'neutral') => void;
}

function sortBySentiment(items: NewsItem[]): NewsItem[] {
  const order: Record<string, number> = { positive: 0, negative: 1, neutral: 2 };
  return [...items].sort((a, b) => {
    const sa = order[a.sentiment || 'neutral'] ?? 2;
    const sb = order[b.sentiment || 'neutral'] ?? 2;
    return sa - sb;
  });
}

function pct(v: number | null) {
  if (v === null || v === undefined) return '-';
  const pctVal = v * 100;
  const color = pctVal > 0 ? '#26a69a' : pctVal < 0 ? '#ef5350' : '#888';
  return <span style={{ color, fontWeight: 600 }}>{pctVal > 0 ? '+' : ''}{pctVal.toFixed(2)}%</span>;
}

export default function NewsPanel({ symbol, hoveredDate, onFindSimilar, highlightedNewsId, isLocked, onUnlock, sourceFilter = 'all', onSourceFilterChange, sentimentFilter = 'all', onSentimentFilterChange }: Props) {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [displayDate, setDisplayDate] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const cacheRef = useRef<Map<string, NewsItem[]>>(new Map());
  const listRef = useRef<HTMLDivElement>(null);

  // Debounced fetch on hover
  useEffect(() => {
    if (!symbol || !hoveredDate) return;
    // If locked and date hasn't changed, skip refetch
    if (isLocked && displayDate === hoveredDate) return;

    if (debounceRef.current) clearTimeout(debounceRef.current);

    debounceRef.current = setTimeout(() => {
      const cacheKey = `${symbol}_${hoveredDate}`;
      const cached = cacheRef.current.get(cacheKey);
      if (cached) {
        setNews(sortBySentiment(cached));
        setDisplayDate(hoveredDate);
        return;
      }

      setLoading(true);
      axios
        .get(`/api/news/${symbol}?date=${hoveredDate}`)
        .then((res) => {
          cacheRef.current.set(cacheKey, res.data);
          setNews(sortBySentiment(res.data));
          setDisplayDate(hoveredDate);
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 120);
  }, [symbol, hoveredDate]);

  // Clear cache on symbol change
  useEffect(() => {
    cacheRef.current.clear();
    setNews([]);
    setDisplayDate(null);
  }, [symbol]);

  // Auto-scroll to highlighted article
  useEffect(() => {
    if (!highlightedNewsId || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-news-id="${highlightedNewsId}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightedNewsId, news]);

  const filteredNews = news.filter((item) => {
    if (sourceFilter === 'reddit' && !item.publisher?.startsWith('Reddit')) return false;
    if (sourceFilter === 'news' && item.publisher?.startsWith('Reddit')) return false;
    if (sentimentFilter !== 'all' && item.sentiment !== sentimentFilter) return false;
    return true;
  });

  if (!displayDate) {
    return (
      <div className="news-panel">
        <div className="news-panel-header">
          <h2>News</h2>
        </div>
        <div className="news-empty">Tap on a chart dot to see news</div>
      </div>
    );
  }

  return (
    <div className="news-panel">
      <div className="news-panel-header">
        <h2>News</h2>
        <span className="news-date-badge">{displayDate}</span>
        <span className="news-count">{filteredNews.length} articles</span>
        {isLocked && (
          <button className="lock-badge" onClick={onUnlock} title="Click to unlock">
            Locked
          </button>
        )}
      </div>
      <div className="news-source-tabs">
        <button className={`news-source-tab ${sourceFilter === 'all' ? 'active' : ''}`} onClick={() => onSourceFilterChange?.('all')}>All</button>
        <button className={`news-source-tab ${sourceFilter === 'news' ? 'active' : ''}`} onClick={() => onSourceFilterChange?.('news')}>News</button>
        <button className={`news-source-tab ${sourceFilter === 'reddit' ? 'active' : ''}`} onClick={() => onSourceFilterChange?.('reddit')}>Reddit</button>
      </div>
      <div className="news-source-tabs">
        <button className={`news-source-tab ${sentimentFilter === 'all' ? 'active' : ''}`} onClick={() => onSentimentFilterChange?.('all')}>All</button>
        <button className={`news-source-tab sentiment-pos ${sentimentFilter === 'positive' ? 'active' : ''}`} onClick={() => onSentimentFilterChange?.('positive')}>▲ Positive</button>
        <button className={`news-source-tab sentiment-neg ${sentimentFilter === 'negative' ? 'active' : ''}`} onClick={() => onSentimentFilterChange?.('negative')}>▼ Negative</button>
        <button className={`news-source-tab ${sentimentFilter === 'neutral' ? 'active' : ''}`} onClick={() => onSentimentFilterChange?.('neutral')}>Neutral</button>
      </div>

      {loading && news.length === 0 ? (
        <div className="news-empty">Loading...</div>
      ) : filteredNews.length === 0 ? (
        <div className="news-empty">No {sourceFilter === 'reddit' ? 'Reddit posts' : sourceFilter === 'news' ? 'news articles' : 'news'} for this date</div>
      ) : (
        <div className="news-list" ref={listRef}>
          {filteredNews.map((item) => {
            return (
              <div
                key={item.news_id}
                data-news-id={item.news_id}
                className={`news-card ${item.sentiment === 'positive' ? 'card-positive' : item.sentiment === 'negative' ? 'card-negative' : 'card-neutral'}${highlightedNewsId === item.news_id ? ' card-highlighted' : ''}`}
              >
                <div className="news-card-top">
                  <span className={`sentiment-dot ${item.sentiment || 'neutral'}`} />
                  <a href={item.article_url} target="_blank" rel="noreferrer" className="news-title">
                    {item.title}
                  </a>
                </div>

                {item.image_url && (
                  <div className="news-image-wrap">
                    <img
                      src={item.image_url}
                      alt=""
                      className="news-image"
                      loading="lazy"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  </div>
                )}

                {item.key_discussion && (
                  <p className="news-summary">{item.key_discussion}</p>
                )}

                {(item.reason_growth || item.reason_decrease) && (
                  <div className="news-reasons">
                    {item.reason_growth && (
                      <div className="reason up">
                        <span className="reason-icon">+</span> {item.reason_growth}
                      </div>
                    )}
                    {item.reason_decrease && (
                      <div className="reason down">
                        <span className="reason-icon">-</span> {item.reason_decrease}
                      </div>
                    )}
                  </div>
                )}

                <div className="news-card-footer">
                  <span className="news-publisher">{item.publisher}</span>
                  <div className="returns-chips">
                    <span className="ret-chip">T+1 {pct(item.ret_t1)}</span>
                    <span className="ret-chip">T+5 {pct(item.ret_t5)}</span>
                    {onFindSimilar && (
                      <button
                        className="find-similar-btn"
                        onClick={(e) => { e.stopPropagation(); onFindSimilar(item.news_id); }}
                      >
                        Find Similar
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
