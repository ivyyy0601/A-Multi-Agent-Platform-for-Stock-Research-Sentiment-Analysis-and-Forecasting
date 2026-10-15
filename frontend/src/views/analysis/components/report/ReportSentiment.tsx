import React, { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  PointElement, LineElement,
  ArcElement,
  Tooltip, Legend, Filler,
} from 'chart.js';
import { Line, Doughnut } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, ArcElement, Tooltip, Legend, Filler);

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import { redditAPI, xAPI, newsAPI } from '../../../sentiment/api/adanos';

const DAYS_OPTIONS = [1, 3, 7, 30];

function toNYTime(iso?: string) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/New_York',
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  }) + ' ET';
}

function toEDTDate(iso?: string) {
  if (!iso) return '';
  // Show date only in UTC-4 (EDT)
  const d = new Date(new Date(iso).getTime() - 4 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10);
}

const CHART_OPTS: any = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: { legend: { labels: { color: '#6b7280', font: { size: 9 }, boxWidth: 8 } } },
  scales: {
    x:  { ticks: { color: '#4b5563', font: { size: 8 } }, grid: { color: '#1a1d27' } },
    y1: { type: 'linear', position: 'left',  ticks: { color: '#4b5563', font: { size: 8 } }, grid: { color: '#1a1d27' } },
    y2: { type: 'linear', position: 'right', min: -1, max: 1, ticks: { color: '#4b5563', font: { size: 8 } }, grid: { display: false } },
  },
};

const DONUT_OPTS: any = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom' as const, labels: { color: '#6b7280', font: { size: 9 }, padding: 6, boxWidth: 8 } },
  },
};

interface PlatformData {
  found?: boolean;
  buzz_score?: number;
  trend?: string;
  mentions?: number;
  bullish_pct?: number;
  bearish_pct?: number;
  positive_count?: number;
  neutral_count?: number;
  negative_count?: number;
  sentiment_score?: number;
  daily_trend?: { date: string; mentions: number; sentiment_score: number }[];
  top_mentions?: any[];
  top_tweets?: any[];
  is_validated?: boolean;
}

function SentimentBadge({ label }: { label: string }) {
  const colors: Record<string, string> = { positive: '#22c55e', negative: '#ef4444', neutral: '#6b7280' };
  return <span style={{ color: colors[label] || '#6b7280', fontWeight: 700 }}>{label}</span>;
}

interface ExplanationData {
  explanation?: string;
  model?: string;
  generated_at?: string;
  cached?: boolean;
}

function PlatformCard({ title, icon, color, data, explanation }: {
  title: string; icon: string; color: string; data: PlatformData | null; explanation?: ExplanationData | null;
}) {
  if (!data || data.found === false) {
    return (
      <div style={{ flex: 1, minWidth: 0, background: '#0d0f17', border: '1px solid #1e2030', borderRadius: '10px', padding: '14px' }}>
        <div style={{ color, fontWeight: 800, fontSize: '13px', marginBottom: '10px' }}>{icon} {title}</div>
        <div style={{ color: '#374151', fontSize: '12px', textAlign: 'center', padding: '32px 0' }}>No data for this period</div>
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
    .sort((a: any, b: any) => (b.upvotes || b.likes || 0) - (a.upvotes || a.likes || 0));

  return (
    <div style={{ flex: 1, minWidth: 0, background: '#0d0f17', border: `1px solid ${color}28`, borderRadius: '10px', padding: '14px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <span style={{ color, fontWeight: 800, fontSize: '13px' }}>{icon} {title}</span>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {data.sentiment_score !== undefined && data.sentiment_score !== null && (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '8px', color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sentiment</div>
              <div style={{
                fontSize: '14px', fontWeight: 800, fontVariantNumeric: 'tabular-nums',
                color: data.sentiment_score > 0.05 ? '#22c55e' : data.sentiment_score < -0.05 ? '#ef4444' : '#6b7280',
              }}>
                {data.sentiment_score > 0 ? '+' : ''}{data.sentiment_score.toFixed(2)}
              </div>
            </div>
          )}
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '8px', color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Buzz</div>
            <div style={{ fontSize: '20px', fontWeight: 900, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
              {data.buzz_score?.toFixed(1)}
            </div>
            <div style={{ fontSize: '9px', color: trendColor }}>
              {data.trend === 'rising' ? '▲' : data.trend === 'falling' ? '▼' : '●'} {data.trend}
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', marginBottom: '10px' }}>
        {([
          ['Mentions', data.mentions?.toLocaleString()],
          ['Bullish',  `${data.bullish_pct ?? '—'}%`],
          ['Bearish',  `${data.bearish_pct ?? '—'}%`],
        ] as [string, string | undefined][]).map(([label, val]) => (
          <div key={label} style={{ background: '#13151f', borderRadius: '6px', padding: '5px', textAlign: 'center' }}>
            <div style={{ fontSize: '8px', color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
            <div style={{ fontSize: '12px', fontWeight: 800, color: '#e2e8f0', fontVariantNumeric: 'tabular-nums' }}>{val ?? '—'}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', alignItems: 'center' }}>
        <div style={{ width: '90px', height: '90px', flexShrink: 0 }}>
          <Doughnut data={donutData} options={DONUT_OPTS} />
        </div>
        <div style={{ flex: 1, height: '90px' }}>
          {dates.length > 1
            ? <Line data={lineData} options={CHART_OPTS} />
            : <div style={{ color: '#374151', fontSize: '11px', textAlign: 'center', paddingTop: '32px' }}>Not enough history</div>
          }
        </div>
      </div>

      {/* AI Summary */}
      {explanation?.explanation && (
        <div style={{ margin: '10px 0', padding: '10px 12px', background: '#0d0f15', borderRadius: '6px', borderLeft: `2px solid ${color}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
            <span style={{ fontSize: '9px', fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              🤖 AI Summary
            </span>
            <span style={{ fontSize: '9px', color: '#374151' }}>
              {toEDTDate(explanation.generated_at)}
              {explanation.cached ? ' · cached' : ''}
              {explanation.model ? ` · ${explanation.model}` : ''}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: '#cbd5e1', lineHeight: '1.6' }}>
            {explanation.explanation}
          </div>
        </div>
      )}

      {/* Top mentions */}
      {mentions.length > 0 && (
        <div>
          <div style={{ fontSize: '9px', color: '#374151', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '5px' }}>
            Top Mentions
          </div>
          <div style={{ maxHeight: '160px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {mentions.map((m: any, i: number) => (
              <div key={i} style={{ padding: '7px', background: '#13151f', borderRadius: '5px', flexShrink: 0 }}>
                <div style={{ fontSize: '10px', color: '#cbd5e1', lineHeight: '1.4', marginBottom: '3px' }}>{m.text_snippet}</div>
                <div style={{ display: 'flex', gap: '6px', fontSize: '9px', color: '#4b5563', flexWrap: 'wrap' }}>
                  <SentimentBadge label={m.sentiment_label} />
                  <span>↑ {(m.upvotes || m.likes)?.toLocaleString() ?? '—'}</span>
                  {m.subreddit && <span>r/{m.subreddit}</span>}
                  {m.author    && <span>@{m.author}</span>}
                  <span>{toNYTime(m.created_utc || m.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface ReportSentimentProps {
  stockCode: string;
}

export const ReportSentiment: React.FC<ReportSentimentProps> = ({ stockCode }) => {
  const [days, setDays] = useState(3);
  const [data, setData] = useState<{ reddit: PlatformData | null; x: PlatformData | null; news: PlatformData | null }>({ reddit: null, x: null, news: null });
  const [explanations, setExplanations] = useState<{ reddit: ExplanationData | null; news: ExplanationData | null }>({ reddit: null, news: null });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!stockCode) return;
    let cancelled = false;
    setLoading(true);
    setData({ reddit: null, x: null, news: null });
    setExplanations({ reddit: null, news: null });

    Promise.all([
      redditAPI.stock(stockCode, days).catch(() => null),
      xAPI.stock(stockCode, days).catch(() => null),
      newsAPI.stock(stockCode, days).catch(() => null),
    ]).then(([reddit, x, news]) => {
      if (cancelled) return;
      setData({ reddit, x, news });
      setLoading(false);
      // Auto-fetch AI explanations for Reddit and News
      redditAPI.explain(stockCode).then((r: ExplanationData) => { if (!cancelled) setExplanations(prev => ({ ...prev, reddit: r })); }).catch(() => {});
      newsAPI.explain(stockCode).then((r: ExplanationData) => { if (!cancelled) setExplanations(prev => ({ ...prev, news: r })); }).catch(() => {});
    });

    return () => { cancelled = true; };
  }, [stockCode, days]);

  // Cross-platform divergence
  const scores = [data.reddit?.sentiment_score, data.x?.sentiment_score, data.news?.sentiment_score]
    .filter((s): s is number => s !== null && s !== undefined);
  const divergence = scores.length > 1 ? Math.max(...scores) - Math.min(...scores) : null;
  const highDiv = divergence !== null && divergence > 0.3;

  return (
    <div className="glass-card rounded-xl p-4">
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13px', fontWeight: 800, color: '#e2e8f0', letterSpacing: '0.03em' }}>
            📡 Social Sentiment
          </span>
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('navigate-adanos', { detail: { ticker: stockCode.toUpperCase() } }))}
            title="Open in Sentiment Deep Dive"
            style={{ background: '#1e2030', border: '1px solid #2d3148', cursor: 'pointer', color: '#9ca3af', fontSize: '12px', fontWeight: 600, padding: '4px 12px', borderRadius: '6px', letterSpacing: '0.02em' }}
          >Detail ↗</button>
          {divergence !== null && (
            <span style={{
              fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px',
              background: highDiv ? '#450a0a' : '#052e16',
              color: highDiv ? '#fca5a5' : '#86efac',
            }}>
              {highDiv ? '⚠️' : '✓'} divergence {divergence.toFixed(2)}
            </span>
          )}
        </div>

        {/* Window selector */}
        <div style={{ display: 'flex', gap: '3px' }}>
          {DAYS_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              style={{
                padding: '3px 9px', borderRadius: '4px', cursor: 'pointer',
                fontSize: '11px', fontWeight: 700,
                border: `1px solid ${days === d ? '#6366f1' : '#1e2030'}`,
                background: days === d ? '#1e1b4b' : 'transparent',
                color: days === d ? '#a5b4fc' : '#4b5563',
                transition: 'all 0.15s',
              }}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#374151' }}>
          <div style={{ fontSize: '20px', marginBottom: '8px' }}>⏳</div>
          Loading sentiment for {stockCode}...
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '10px' }}>
          <PlatformCard title="Reddit"      icon="👾" color="#ff4500" data={data.reddit} explanation={explanations.reddit} />
          <PlatformCard title="X / Twitter" icon="𝕏"  color="#1d9bf0" data={data.x}      explanation={null} />
          <PlatformCard title="News"        icon="📰" color="#22c55e" data={data.news}   explanation={explanations.news} />
        </div>
      )}
    </div>
  );
};
