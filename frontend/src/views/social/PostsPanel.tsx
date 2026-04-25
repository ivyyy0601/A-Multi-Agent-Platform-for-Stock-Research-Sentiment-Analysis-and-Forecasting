import { useEffect, useState } from 'react';
import axios from 'axios';

interface Post {
  platform: 'reddit' | 'twitter' | 'news';
  text: string;
  sentiment: string | null;
  score: number | null;
  source: string;
  created_at: string | null;
  likes: number | null;
  retweets: number | null;
  views: number | null;
  author: string | null;
}

function fmt(n: number | null): string {
  if (n === null) return '';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const PLATFORM_ICON: Record<string, string> = {
  reddit: '🟠', twitter: '🐦', news: '📰',
};

export default function PostsPanel({ ticker, platform }: { ticker: string; platform: string }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    axios.get(`/api/adanos/${ticker}/posts`, { params: { platform } })
      .then(r => setPosts(r.data.posts || []))
      .catch(() => setPosts([]))
      .finally(() => setLoading(false));
  }, [ticker, platform]);

  if (loading) return <div className="posts-empty">Loading posts...</div>;
  if (posts.length === 0) return <div className="posts-empty">No posts found</div>;

  return (
    <div className="posts-list">
      {posts.map((p, i) => (
        <div key={i} className={`post-card post-${p.platform}`}>
          <div className="post-header">
            <span className="post-icon">{PLATFORM_ICON[p.platform]}</span>
            <span className="post-source">{p.source}</span>
            {p.author && <span className="post-author">@{p.author}</span>}
            <span className="post-time">{timeAgo(p.created_at)}</span>
            {p.sentiment && (
              <span className={`post-sentiment ${p.sentiment}`}>
                {p.sentiment === 'positive' ? '▲' : p.sentiment === 'negative' ? '▼' : '—'}
              </span>
            )}
          </div>
          <p className="post-text">{p.text}</p>
          {(p.likes !== null || p.retweets !== null || p.views !== null) && (
            <div className="post-stats">
              {p.likes    !== null && <span>❤️ {fmt(p.likes)}</span>}
              {p.retweets !== null && <span>🔁 {fmt(p.retweets)}</span>}
              {p.views    !== null && <span>👁 {fmt(p.views)}</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
