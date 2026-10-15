import { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import * as d3 from 'd3';

interface DayData {
  date: string;
  reddit?: { buzz: number; sentiment: number; bullish: number; bearish: number };
  twitter?: { buzz: number; sentiment: number; bullish: number; bearish: number };
  news?: { buzz: number; sentiment: number; bullish: number; bearish: number };
}

interface OhlcBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

type MetricKey = 'sentiment' | 'buzz' | 'bullish';

const PLATFORM_COLORS: Record<string, string> = {
  reddit:  '#ff6314',
  twitter: '#1d9bf0',
  news:    '#a78bfa',
};

export type { DayData };

export default function SentimentChart({
  ticker,
  onDayClick,
  selectedDate,
  onDataLoad,
}: {
  ticker: string;
  onDayClick?: (date: string) => void;
  selectedDate?: string | null;
  onDataLoad?: (data: DayData[]) => void;
}) {
  const [sentiment, setSentiment] = useState<DayData[]>([]);
  const [ohlc, setOhlc]           = useState<OhlcBar[]>([]);
  const [metric, setMetric]       = useState<MetricKey>('sentiment');
  const [loading, setLoading]     = useState(false);
  const [size, setSize]           = useState({ w: 600, h1: 200, h2: 90 });
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef  = useRef<SVGSVGElement>(null);
  const svg2Ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      const headerH = 28;
      const total = Math.max(160, height - headerH - 8);
      const h1 = Math.max(96, Math.floor(total * 0.65));
      const h2 = Math.max(56, Math.floor(total * 0.32));
      setSize({
        w: Math.max(320, Math.floor(width)),
        h1,
        h2,
      });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    Promise.all([
      axios.get(`/api/adanos/${ticker}/sentiment?days=90`),
      axios.get(`/api/stocks/${ticker}/ohlc`).catch(() => ({ data: [] })),
    ]).then(([s, o]) => {
      const sentData: DayData[] = s.data;
      // Only show OHLC bars that overlap with sentiment date range
      const minSentDate = sentData.length > 0 ? sentData[0].date : '';
      const filteredOhlc = (o.data as OhlcBar[]).filter(bar => bar.date >= minSentDate);
      setSentiment(sentData);
      setOhlc(filteredOhlc);
      onDataLoad?.(sentData);
    }).finally(() => setLoading(false));
  }, [ticker]);

  // Draw candlestick chart — x-axis driven by sentiment dates so weekend sentiment shows
  useEffect(() => {
    if (!svgRef.current || sentiment.length === 0) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const rawW = size.w || svgRef.current.clientWidth || 600;
    const rawH = size.h1 || 200;
    const W = Math.max(320, rawW);
    const H = Math.max(96, rawH);
    const margin = { top: 8, right: 10, bottom: 20, left: 50 };
    const w = Math.max(40, W - margin.left - margin.right);
    const h = Math.max(40, H - margin.top - margin.bottom);
    if (W <= 0 || H <= 0) return;

    const g = svg.attr('width', W).attr('height', H)
      .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    // Use ALL sentiment dates as x-axis domain (includes weekends)
    const allDates = sentiment.map(d => d.date);
    const ohlcMap = new Map(ohlc.map(b => [b.date, b]));

    const xScale = d3.scaleBand().domain(allDates).range([0, w]).padding(0.2);
    const yMin = ohlc.length ? d3.min(ohlc, d => d.low)! : 0;
    const yMax = ohlc.length ? d3.max(ohlc, d => d.high)! : 1;
    const yScale = d3.scaleLinear().domain([yMin * 0.995, yMax * 1.005]).range([h, 0]);

    const tickInterval = Math.max(1, Math.floor(allDates.length / 6));
    g.append('g').attr('transform', `translate(0,${h})`).call(
      d3.axisBottom(xScale)
        .tickValues(allDates.filter((_, i) => i % tickInterval === 0))
        .tickFormat(d => (d as string).slice(5))
    ).attr('color', '#555').call(ax => ax.select('.domain').remove());

    g.append('g').call(d3.axisLeft(yScale).ticks(4).tickFormat(d => `$${d3.format('.0f')(d as number)}`))
      .attr('color', '#555').call(ax => ax.select('.domain').remove());

    // Selected date highlight
    if (selectedDate && xScale(selectedDate) !== undefined) {
      g.append('rect')
        .attr('x', xScale(selectedDate)! - 1)
        .attr('y', 0)
        .attr('width', xScale.bandwidth() + 2)
        .attr('height', h)
        .attr('fill', '#ffffff14');
    }

    allDates.forEach(date => {
      const x = xScale(date)!;
      const bw = xScale.bandwidth();
      const bar = ohlcMap.get(date);

      // Clickable hit area for every date (including weekends)
      g.append('rect')
        .attr('x', x - 2).attr('y', 0)
        .attr('width', bw + 4).attr('height', h)
        .attr('fill', 'transparent')
        .attr('cursor', 'pointer')
        .on('click', () => onDayClick?.(date));

      if (bar) {
        // Normal trading day — draw candle
        const isUp = bar.close >= bar.open;
        const isSelected = date === selectedDate;
        const color = isSelected ? '#fff' : isUp ? '#26a69a' : '#ef5350';

        g.append('line')
          .attr('x1', x + bw / 2).attr('x2', x + bw / 2)
          .attr('y1', yScale(bar.high)).attr('y2', yScale(bar.low))
          .attr('stroke', color).attr('stroke-width', 1);

        g.append('rect')
          .attr('x', x).attr('y', yScale(Math.max(bar.open, bar.close)))
          .attr('width', bw)
          .attr('height', Math.max(1, Math.abs(yScale(bar.open) - yScale(bar.close))))
          .attr('fill', color)
          .attr('cursor', 'pointer')
          .on('click', () => onDayClick?.(date));
      } else {
        // Weekend / no-trading day — dashed vertical line to show sentiment exists
        g.append('line')
          .attr('x1', x + bw / 2).attr('x2', x + bw / 2)
          .attr('y1', h * 0.1).attr('y2', h * 0.9)
          .attr('stroke', '#333')
          .attr('stroke-width', 1)
          .attr('stroke-dasharray', '2,3');
      }
    });
  }, [ohlc, sentiment, size, selectedDate, onDayClick]);

  // Draw sentiment overlay chart
  useEffect(() => {
    if (!svg2Ref.current || sentiment.length === 0) return;
    const svg = d3.select(svg2Ref.current);
    svg.selectAll('*').remove();

    const rawW = size.w || svg2Ref.current.clientWidth || 600;
    const rawH = size.h2 || 90;
    const W = Math.max(320, rawW);
    const H = Math.max(60, rawH);
    const margin = { top: 8, right: 10, bottom: 20, left: 50 };
    const w = Math.max(40, W - margin.left - margin.right);
    const h = Math.max(32, H - margin.top - margin.bottom);
    if (W <= 0 || H <= 0) return;

    const g = svg.attr('width', W).attr('height', H)
      .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    let yMin = -0.6, yMax = 0.6;
    if (metric === 'buzz') { yMin = 0; yMax = 100; }
    if (metric === 'bullish') { yMin = 0; yMax = 100; }

    const xScale = d3.scalePoint().domain(sentiment.map(d => d.date)).range([0, w]).padding(0.1);
    const yScale = d3.scaleLinear().domain([yMin, yMax]).range([h, 0]);

    if (metric === 'sentiment') {
      g.append('line')
        .attr('x1', 0).attr('x2', w)
        .attr('y1', yScale(0)).attr('y2', yScale(0))
        .attr('stroke', '#333').attr('stroke-dasharray', '3,3');
    }

    g.append('g').attr('transform', `translate(0,${h})`).call(
      d3.axisBottom(xScale)
        .tickValues(sentiment.filter((_, i) => i % Math.max(1, Math.floor(sentiment.length / 6)) === 0).map(d => d.date))
        .tickFormat(d => (d as string).slice(5))
    ).attr('color', '#555').call(ax => ax.select('.domain').remove());

    g.append('g').call(d3.axisLeft(yScale).ticks(4))
      .attr('color', '#555').call(ax => ax.select('.domain').remove());

    (['reddit', 'twitter', 'news'] as const).forEach(p => {
      const vals = sentiment.map(d => ({
        date: d.date,
        val: d[p]?.[metric] ?? null,
      })).filter(d => d.val !== null);

      if (vals.length < 2) return;

      g.append('path')
        .datum(vals as { date: string; val: number }[])
        .attr('fill', 'none')
        .attr('stroke', PLATFORM_COLORS[p])
        .attr('stroke-width', 1.5)
        .attr('d', d3.line<{ date: string; val: number }>()
          .x(d => xScale(d.date)!)
          .y(d => yScale(d.val))
          .curve(d3.curveMonotoneX)
        );
    });

    (['reddit', 'twitter', 'news'] as const).forEach((p, i) => {
      g.append('circle').attr('cx', i * 80 + 5).attr('cy', -2).attr('r', 4).attr('fill', PLATFORM_COLORS[p]);
      g.append('text').attr('x', i * 80 + 13).attr('y', 2).attr('fill', PLATFORM_COLORS[p])
        .attr('font-size', '10px').text(p);
    });
    // Selected date vertical line
    if (selectedDate) {
      const sx = xScale(selectedDate);
      if (sx !== undefined) {
        g.append('line')
          .attr('x1', sx).attr('x2', sx)
          .attr('y1', 0).attr('y2', h)
          .attr('stroke', '#ffffff88').attr('stroke-width', 1).attr('stroke-dasharray', '3,2');
      }
    }
  }, [sentiment, metric, size, selectedDate]);

  if (loading) return <div className="social-chart-loading">Loading chart...</div>;

  return (
    <div className="social-chart-wrap" ref={wrapRef}>
      <div className="social-chart-header">
        <span className="social-chart-title">{ticker} — Price + Sentiment</span>
        <div className="social-metric-tabs">
          {(['sentiment', 'buzz', 'bullish'] as MetricKey[]).map(m => (
            <button key={m}
              className={`social-metric-tab ${metric === m ? 'active' : ''}`}
              onClick={() => setMetric(m)}
            >
              {m === 'sentiment' ? 'Sentiment' : m === 'buzz' ? 'Buzz' : 'Bullish %'}
            </button>
          ))}
        </div>
      </div>
      <svg ref={svgRef}  style={{ display: 'block' }} />
      <svg ref={svg2Ref} style={{ display: 'block', marginTop: 4 }} />
    </div>
  );
}
