import type React from 'react';
import { useState, useEffect } from 'react';
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Card } from '../common';
import apiClient from '../../api/index';
import { SourceBadge } from './SourceBadge';

interface KLine {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change_percent?: number;
}

interface ChartPoint {
  date: string;
  close: number;
  volume: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
}

function calcMA(data: KLine[], n: number): (number | undefined)[] {
  return data.map((_, i) => {
    if (i < n - 1) return undefined;
    const sum = data.slice(i - n + 1, i + 1).reduce((s, d) => s + d.close, 0);
    return Math.round((sum / n) * 100) / 100;
  });
}

interface ReportChartProps {
  stockCode?: string;
  fetchedAt?: string;
}

export const ReportChart: React.FC<ReportChartProps> = ({ stockCode, fetchedAt }) => {
  const [chartData, setChartData] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(60);

  useEffect(() => {
    if (!stockCode) return;
    setLoading(true);
    apiClient.get(`/api/v1/stocks/${stockCode}/history?period=daily&days=${days}`)
      .then(r => {
        const raw: KLine[] = r.data?.data || [];
        const ma5  = calcMA(raw, 5);
        const ma10 = calcMA(raw, 10);
        const ma20 = calcMA(raw, 20);
        setChartData(raw.map((d, i) => ({
          date: d.date.slice(5),   // MM-DD
          close: d.close,
          volume: Math.round(d.volume / 10000), // 万手
          ma5: ma5[i],
          ma10: ma10[i],
          ma20: ma20[i],
        })));
      })
      .catch(() => setChartData([]))
      .finally(() => setLoading(false));
  }, [stockCode, days]);

  if (!stockCode) return null;

  return (
    <Card variant="bordered" padding="md">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="label-uppercase">CHART</span>
          <h3 className="text-base font-semibold text-white">Price Chart</h3>
          <SourceBadge source="yf" fetchedAt={fetchedAt} />
        </div>
        <div className="flex items-center gap-1">
          {[30, 60, 90].map(d => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`rounded-full px-2.5 py-0.5 text-xs transition-colors ${
                days === d
                  ? 'bg-cyan/20 text-cyan border border-cyan/30'
                  : 'text-muted-text hover:text-white border border-white/10 hover:border-white/20'
              }`}
            >
              {d}d
            </button>
          ))}
          {loading && <div className="w-3.5 h-3.5 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin ml-1" />}
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="space-y-4">
          {/* 价格 + MA 折线 */}
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#6b7280' }}
                interval={Math.floor(chartData.length / 6)}
              />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fontSize: 10, fill: '#6b7280' }}
                width={55}
                tickFormatter={v => `$${v}`}
              />
              <Tooltip
                contentStyle={{ background: '#1a1f2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(v: unknown) => [`$${Number(v).toFixed(2)}`]}
              />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
              <Line type="monotone" dataKey="close" name="Close" stroke="#22d3ee" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="ma5"   name="MA5"  stroke="#f59e0b" dot={false} strokeWidth={1} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="ma10"  name="MA10" stroke="#a78bfa" dot={false} strokeWidth={1} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="ma20"  name="MA20" stroke="#34d399" dot={false} strokeWidth={1} strokeDasharray="4 2" />
            </ComposedChart>
          </ResponsiveContainer>

          {/* 成交量柱状图 */}
          <ResponsiveContainer width="100%" height={80}>
            <ComposedChart data={chartData} margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" hide />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} width={55} tickFormatter={v => `${v}k`} />
              <Tooltip
                contentStyle={{ background: '#1a1f2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                formatter={(v: unknown) => [`${v}k`, 'Volume']}
              />
              <Bar dataKey="volume" name="Volume" fill="rgba(34,211,238,0.25)" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && chartData.length === 0 && (
        <div className="text-xs text-muted-text">No chart data available</div>
      )}
    </Card>
  );
};
