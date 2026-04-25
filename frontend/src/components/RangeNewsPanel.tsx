import { useState, useEffect } from 'react';
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
  chinese_summary: string | null;
  sentiment: string | null;
  reason_growth: string | null;
  reason_decrease: string | null;
  ret_t0: number | null;
  ret_t1: number | null;
  ret_t3: number | null;
  ret_t5: number | null;
  ret_t10: number | null;
}

interface RangeNewsResponse {
  total: number;
  date_range: [string, string];
  articles: NewsItem[];
  top_bullish: NewsItem[];
  top_bearish: NewsItem[];
}

interface Props {
  symbol: string;
  startDate: string;
  endDate: string;
  priceChange?: number;
  onClose: () => void;
  onAskAI: (question: string) => void;
}

const PREVIEW = 5;

function pct(v: number | null) {
  if (v === null || v === undefined) return '-';
  const p = v * 100;
  const color = p > 0 ? '#26a69a' : p < 0 ? '#ef5350' : '#888';
  return <span style={{ color, fontWeight: 600 }}>{p > 0 ? '+' : ''}{p.toFixed(2)}%</span>;
}

function SentimentSection({
  label,
  icon,
  color,
  items,
}: {
  label: string;
  icon: string;
  color: string;
  items: NewsItem[];
}) {
  const [expanded, setExpanded] = useState(false);
  if (items.length === 0) return null;
  const visible = expanded ? items : items.slice(0, PREVIEW);

  return (
    <div className="range-news-section">
      <button
        className="range-news-section-title-btn"
        style={{ color }}
        onClick={() => setExpanded((v) => !v)}
      >
        <span>{icon} {label} ({items.length})</span>
        <span className="range-section-chevron">{expanded ? '▲' : '▼'}</span>
      </button>
      <div className="range-section-body">
        {visible.map((item) => (
          <RangeNewsCard key={item.news_id} item={item} />
        ))}
        {items.length > PREVIEW && (
          <button
            className="range-news-more-btn"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? 'Show less' : `Show ${items.length - PREVIEW} more`}
          </button>
        )}
      </div>
    </div>
  );
}

export default function RangeNewsPanel({ symbol, startDate, endDate, priceChange, onClose, onAskAI }: Props) {
  const [data, setData] = useState<RangeNewsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setData(null);
    axios
      .get(`/api/news/${symbol}/range?start=${startDate}&end=${endDate}`)
      .then((res) => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [symbol, startDate, endDate]);

  const change = priceChange ?? 0;
  const isUp = change >= 0;

  const bullish = data?.articles.filter((a) => a.sentiment === 'positive') ?? [];
  const bearish = data?.articles.filter((a) => a.sentiment === 'negative') ?? [];
  const neutral = data?.articles.filter((a) => a.sentiment !== 'positive' && a.sentiment !== 'negative') ?? [];

  return (
    <div className="news-panel">
      <div className="news-panel-header">
        <h2>Range News</h2>
        <span className={`range-news-change ${isUp ? 'up' : 'down'}`}>
          {isUp ? '+' : ''}{change.toFixed(2)}%
        </span>
        <button className="range-clear-btn" onClick={onClose}>Close</button>
      </div>

      <div className="range-news-dates">
        {startDate} ~ {endDate}
        {data && <span className="news-count" style={{ marginLeft: 8 }}>{data.total} articles</span>}
      </div>

      {loading ? (
        <div className="news-empty">
          <div className="range-loading">
            <div className="range-spinner" />
            <span>Loading range news...</span>
          </div>
        </div>
      ) : !data || data.total === 0 ? (
        <div className="news-empty">No news in this range</div>
      ) : (
        <div className="news-list">
          <SentimentSection label="Bullish News" icon="▲" color="#26a69a" items={bullish} />
          <SentimentSection label="Bearish News" icon="▼" color="#ef5350" items={bearish} />
          <SentimentSection label="Neutral" icon="—" color="#888" items={neutral} />

          <button
            className="range-news-ai-btn"
            onClick={() => onAskAI("What's driving the price movement?")}
          >
            Ask AI
          </button>
        </div>
      )}
    </div>
  );
}

function RangeNewsCard({ item }: { item: NewsItem }) {
  const sentiment = item.sentiment || 'neutral';
  const borderClass = sentiment === 'positive' ? 'card-positive' : sentiment === 'negative' ? 'card-negative' : 'card-neutral';

  return (
    <div className={`news-card ${borderClass}`}>
      <div className="news-card-top">
        <span className={`sentiment-dot ${sentiment}`} />
        <a href={item.article_url} target="_blank" rel="noreferrer" className="news-title">
          {item.title}
        </a>
      </div>

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
        <span className="news-publisher">{item.trade_date} · {item.publisher}</span>
        <div className="returns-chips">
          <span className="ret-chip">T+0 {pct(item.ret_t0)}</span>
          <span className="ret-chip">T+1 {pct(item.ret_t1)}</span>
        </div>
      </div>
    </div>
  );
}
