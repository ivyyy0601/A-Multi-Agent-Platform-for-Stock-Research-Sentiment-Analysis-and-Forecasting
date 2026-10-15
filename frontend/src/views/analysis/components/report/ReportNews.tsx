import type React from 'react';
import { useState, useEffect } from 'react';
import { Card } from '../common';
import apiClient from '../../api/index';
import { SourceBadge } from './SourceBadge';

interface NewsItem {
  title: string;
  summary?: string;
  snippet?: string;
  url?: string;
  source?: string;
  published_at?: string;
}

interface RedditItem {
  title: string;
  text?: string;
  url?: string;
  subreddit?: string;
  author?: string;
  score?: number;
  num_comments?: number;
  published_at?: string;
}

interface ReportNewsProps {
  recordId?: number;
  stockCode?: string;
  limit?: number;
}

function FeedCard({
  label,
  title,
  items,
  isLoading,
  onRefresh,
  renderItem,
}: {
  label: string;
  title: string;
  items: unknown[];
  isLoading: boolean;
  onRefresh: () => void;
  renderItem: (item: unknown, index: number) => React.ReactNode;
}) {
  return (
    <Card variant="bordered" padding="md">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="label-uppercase">{label}</span>
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <SourceBadge source="db" />
        </div>
        <div className="flex items-center gap-2">
          {isLoading && (
            <div className="w-3.5 h-3.5 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
          )}
          <button
            type="button"
            onClick={onRefresh}
            className="text-xs text-cyan hover:text-white transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-xs text-secondary-text">
          <div className="w-4 h-4 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
          Loading...
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="text-xs text-muted-text">No content available</div>
      )}

      {!isLoading && items.length > 0 && (
        <div className="space-y-3 text-left max-h-[480px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
          {items.map((item, i) => renderItem(item, i))}
        </div>
      )}
    </Card>
  );
}

export const ReportNews: React.FC<ReportNewsProps> = ({ stockCode }) => {
  const [newsItems, setNewsItems] = useState<NewsItem[]>([]);
  const [redditItems, setRedditItems] = useState<RedditItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [redditLoading, setRedditLoading] = useState(false);
  const [newsRefresh, setNewsRefresh] = useState(0);
  const [redditRefresh, setRedditRefresh] = useState(0);

  useEffect(() => {
    if (!stockCode) return;
    setNewsItems([]);
    setNewsLoading(true);
    apiClient.get(`/api/v1/stocks/${stockCode}/ext-news?limit=200&days=30`)
      .then(r => setNewsItems(r.data?.items || []))
      .catch(() => setNewsItems([]))
      .finally(() => setNewsLoading(false));
  }, [stockCode, newsRefresh]);

  useEffect(() => {
    if (!stockCode) return;
    setRedditItems([]);
    setRedditLoading(true);
    apiClient.get(`/api/v1/stocks/${stockCode}/reddit?limit=200&days=30`)
      .then(r => setRedditItems(r.data?.items || []))
      .catch(() => setRedditItems([]))
      .finally(() => setRedditLoading(false));
  }, [stockCode, redditRefresh]);

  if (!stockCode) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* News 框 */}
      <FeedCard
        label="NEWS FEED"
        title="Related News"
        items={newsItems}
        isLoading={newsLoading}
        onRefresh={() => setNewsRefresh(n => n + 1)}
        renderItem={(item, i) => {
          const n = item as NewsItem;
          return (
            <div
              key={i}
              className="group rounded-xl border border-white/6 bg-elevated/75 p-4 transition-colors hover:border-cyan/25 hover:bg-hover"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium leading-6 text-white">{n.title}</p>
                  {(n.summary || n.snippet) && (
                    <p className="mt-1 text-xs text-secondary-text line-clamp-2">
                      {n.summary || n.snippet}
                    </p>
                  )}
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-text">
                    {n.source && <span>{n.source}</span>}
                    {n.published_at && <span>{n.published_at.slice(0, 10)}</span>}
                  </div>
                </div>
                {n.url && (
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border border-cyan/18 bg-cyan/10 px-2.5 py-1 text-xs text-cyan transition-colors hover:border-cyan/30 hover:text-white"
                  >
                    View
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 3h7m0 0v7m0-7L10 14" />
                    </svg>
                  </a>
                )}
              </div>
            </div>
          );
        }}
      />

      {/* Reddit 框 */}
      <FeedCard
        label="REDDIT"
        title="Community Discussion"
        items={redditItems}
        isLoading={redditLoading}
        onRefresh={() => setRedditRefresh(n => n + 1)}
        renderItem={(item, i) => {
          const r = item as RedditItem;
          return (
            <div
              key={i}
              className="group rounded-xl border border-white/6 bg-elevated/75 p-4 transition-colors hover:border-cyan/25 hover:bg-hover"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium leading-6 text-white">{r.title}</p>
                  {r.text && (
                    <p className="mt-1 text-xs text-secondary-text line-clamp-2">{r.text}</p>
                  )}
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-text">
                    {r.subreddit && <span>r/{r.subreddit}</span>}
                    {r.score != null && <span>▲ {r.score}</span>}
                    {r.num_comments != null && <span>💬 {r.num_comments}</span>}
                    {r.published_at && <span>{r.published_at.slice(0, 10)}</span>}
                  </div>
                </div>
                {r.url && (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border border-orange-400/20 bg-orange-400/10 px-2.5 py-1 text-xs text-orange-400 transition-colors hover:border-orange-400/40 hover:text-white"
                  >
                    Post
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 3h7m0 0v7m0-7L10 14" />
                    </svg>
                  </a>
                )}
              </div>
            </div>
          );
        }}
      />
    </div>
  );
};
