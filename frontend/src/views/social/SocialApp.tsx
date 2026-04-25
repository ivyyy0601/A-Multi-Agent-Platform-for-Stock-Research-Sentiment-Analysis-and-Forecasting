import { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import SentimentChart, { type DayData } from './SentimentChart';
import SocialPrediction from './SocialPrediction';
import StockSelector from '../../components/StockSelector';
import './social.css';

const PC: Record<string, string> = { reddit: '#ff6314', twitter: '#1d9bf0', news: '#a78bfa' };
const PLATFORMS = ['reddit', 'twitter', 'news'] as const;

function DaySentiment({ sentData, date, onClose }: {
  sentData: DayData; date: string; onClose: () => void;
}) {
  return (
    <div className="day-sent-bar">
      <span className="day-sent-date">📅 {date}</span>
      <div className="day-sent-platforms">
        {PLATFORMS.map(p => {
          const d = sentData[p];
          if (!d || d.sentiment == null) return null;
          const dir = d.sentiment > 0.05 ? 'up' : d.sentiment < -0.05 ? 'down' : 'neutral';
          return (
            <div key={p} className="day-sent-item">
              <span className="day-sent-name" style={{ color: PC[p] }}>{p}</span>
              <span className={`day-sent-val ${dir}`}>
                {dir === 'up' ? '▲' : dir === 'down' ? '▼' : '—'}{d.sentiment > 0 ? '+' : ''}{d.sentiment.toFixed(2)}
              </span>
              {d.buzz != null && <span className="day-sent-buzz">{d.buzz.toFixed(0)} buzz</span>}
              {d.bullish != null && (
                <span className="day-sent-bull">🟢{d.bullish}% / 🔴{d.bearish}%</span>
              )}
            </div>
          );
        })}
      </div>
      <button className="day-sent-close" onClick={onClose}>✕</button>
    </div>
  );
}

export default function SocialApp({ initTicker }: { initTicker?: string }) {
  const [ticker, setTicker]             = useState(initTicker || 'NVDA');
  const [activeTickers, setActiveTickers] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [sentimentData, setSentimentData] = useState<DayData[]>([]);

  useEffect(() => {
    axios.get('/api/stocks').then(r => {
      setActiveTickers(r.data.filter((t: any) => t.last_ohlc_fetch).map((t: any) => t.symbol));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const handler = (e: Event) => {
      const t = (e as CustomEvent<{ ticker: string }>).detail?.ticker;
      if (t) { setTicker(t); setSelectedDate(null); }
    };
    window.addEventListener('navigate-social', handler);
    return () => window.removeEventListener('navigate-social', handler);
  }, []);

  const selectedDayData = selectedDate
    ? sentimentData.find(d => d.date === selectedDate) ?? null
    : null;

  const handleDayClick = (date: string) => {
    setSelectedDate(prev => prev === date ? null : date);
  };

  const handleDataLoad = useCallback((data: DayData[]) => {
    setSentimentData(data);
  }, []);

  const handleTickerChange = (t: string) => {
    setTicker(t);
    setSelectedDate(null);
  };

  return (
    <div className="social-app">
      {/* Header */}
      <div className="social-header">
        <span className="social-title">Social</span>
        <StockSelector
          activeTickers={activeTickers}
          selectedSymbol={ticker}
          onSelect={handleTickerChange}
          onAdd={() => {}}
        />
      </div>

      {/* 2-column layout */}
      <div className="social-main">

        {/* Left: chart + day detail */}
        <div className="social-left">
          <div className="social-chart-area">
            <SentimentChart
              ticker={ticker}
              onDayClick={handleDayClick}
              selectedDate={selectedDate}
              onDataLoad={handleDataLoad}
            />
          </div>
          {selectedDate && selectedDayData && (
            <DaySentiment
              sentData={selectedDayData}
              date={selectedDate}
              onClose={() => setSelectedDate(null)}
            />
          )}
          {selectedDate && !selectedDayData && (
            <div className="day-sent-bar">
              <span className="day-sent-date">📅 {selectedDate}</span>
              <span style={{ color: '#666', fontSize: 12 }}>No sentiment data for this date</span>
              <button className="day-sent-close" onClick={() => setSelectedDate(null)}>✕</button>
            </div>
          )}
        </div>

        {/* Right: prediction */}
        <div className="social-prediction-area">
          <SocialPrediction ticker={ticker} />
        </div>

      </div>
    </div>
  );
}
