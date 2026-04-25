import { useState, useEffect } from 'react';
import type React from 'react';
import axios from 'axios';
import { Card } from '../common';

interface HorizonPrediction {
  direction: 'up' | 'down';
  confidence: number;
  top_drivers: { name: string; contribution: number }[];
}

interface Forecast {
  forecast_date?: string;
  prediction: Record<string, HorizonPrediction>;
  _isFallbackLatest?: boolean;
}

interface Props {
  stockCode: string;
  fetchedAt?: string;
}

function nextTradingDay(date: string): string {
  const d = new Date(date + 'T00:00:00');
  d.setDate(d.getDate() + 1);
  if (d.getDay() === 6) d.setDate(d.getDate() + 2);
  if (d.getDay() === 0) d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function HorizonBox({ label, pred }: { label: string; pred: HorizonPrediction }) {
  const up = pred.direction === 'up';
  const color = up ? '#22c55e' : '#ef4444';
  const bg = up ? 'rgba(34,197,94,0.07)' : 'rgba(239,68,68,0.07)';
  const pct = Math.round(pred.confidence * 100);
  const topDriver = pred.top_drivers?.[0]?.name ?? '—';

  return (
    <div style={{ flex: 1, background: bg, border: `1px solid ${color}22`, borderRadius: 8, padding: '10px 14px', minWidth: 0 }}>
      <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color, fontFamily: 'monospace', marginBottom: 4 }}>
        {up ? '▲' : '▼'} {up ? 'BULLISH' : 'BEARISH'}
      </div>
      <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 3 }}>
        Confidence: <span style={{ color, fontWeight: 600 }}>{pct}%</span>
      </div>
      <div style={{ fontSize: 10, color: '#6b7280' }}>
        Top driver: <span style={{ color: '#9ca3af' }}>{topDriver}</span>
      </div>
    </div>
  );
}

export const ReportForecast: React.FC<Props> = ({ stockCode, fetchedAt }) => {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!stockCode) return;
    setLoading(true);
    setForecast(null);
    const historicalParams = { window: 7, date: fetchedAt ? fetchedAt.slice(0, 10) : undefined };
    axios.get(`/api/predict/${stockCode}/forecast`, { params: historicalParams })
      .then(r => setForecast(r.data))
      .catch(() => {
        axios.get(`/api/predict/${stockCode}/forecast`, { params: { window: 7 } })
          .then(r => setForecast({ ...r.data, _isFallbackLatest: true }))
          .catch(() => {});
      })
      .finally(() => setLoading(false));
  }, [stockCode, fetchedAt]);

  if (loading) return (
    <Card>
      <div style={{ fontSize: 11, color: '#4b5563' }}>📰 Past News Forecast — Loading...</div>
    </Card>
  );

  if (!forecast) return null;

  const t1 = forecast.prediction?.t1;
  const t7 = forecast.prediction?.t7;
  const t14 = forecast.prediction?.t14;

  if (!t1 && !t7 && !t14) return null;

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
            📰 Past News Forecast
          </div>
          {forecast.forecast_date && (
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
              {forecast._isFallbackLatest ? 'Latest available snapshot · ' : ''}
              Based on market data through {forecast.forecast_date} · Predicting next trading day {nextTradingDay(forecast.forecast_date)}
            </div>
          )}
        </div>
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('navigate-ticker', { detail: { ticker: stockCode.toUpperCase() } }))}
          title="View news detail"
          style={{ background: '#1e2030', border: '1px solid #2d3148', cursor: 'pointer', color: '#9ca3af', fontSize: '12px', fontWeight: 600, padding: '4px 12px', borderRadius: '6px', letterSpacing: '0.02em' }}
        >Detail ↗</button>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        {t1 && <HorizonBox label="1D" pred={t1} />}
        {t7 && <HorizonBox label="7D" pred={t7} />}
        {t14 && <HorizonBox label="14D" pred={t14} />}
      </div>
    </Card>
  );
};
