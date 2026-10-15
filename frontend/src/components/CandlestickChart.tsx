import { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import axios from 'axios';

interface OHLCRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Particle {
  id: string;
  d: string;   // trade_date
  pd: string;  // actual published date (for x positioning)
  s: string | null;  // sentiment
  r: string | null;  // relevance
  t: string;   // title (truncated)
  rt1: number | null; // ret_t1
}

interface HoverData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  change: number;
}

interface RangeSelection {
  startDate: string;
  endDate: string;
  priceChange?: number;
  popupX?: number;
  popupY?: number;
}

interface ArticleSelection {
  newsId: string;
  date: string;
}

interface Props {
  symbol: string;
  lockedNewsId?: string | null;
  sourceFilter?: 'all' | 'news' | 'reddit';
  sentimentFilter?: 'all' | 'positive' | 'negative' | 'neutral';
  onHover: (date: string | null, ohlc?: HoverData) => void;
  onRangeSelect?: (range: RangeSelection | null) => void;
  onArticleSelect?: (article: ArticleSelection | null) => void;
  onDayClick?: (date: string) => void;
}

// Sentiment → color mapping (neon terminal palette)
const SENTIMENT_COLOR: Record<string, string> = {
  positive: '#00e676',
  negative: '#ff5252',
  neutral: '#00e5ff',
};
const SENTIMENT_COLOR_DEFAULT = '#555';

function getSentimentColor(s: string | null): string {
  return (s && SENTIMENT_COLOR[s]) || SENTIMENT_COLOR_DEFAULT;
}

function getParticleRadius(relevance: string | null, rt1: number | null): number {
  let r = 2;
  if (relevance === 'relevant') r += 0.8;
  if (rt1 !== null) r += Math.min(Math.abs(rt1) * 20, 1.5);
  return Math.min(r, 4.5);
}

function getParticleAlpha(relevance: string | null): number {
  return relevance === 'relevant' ? 0.7 : 0.3;
}

interface PlacedParticle extends Particle {
  px: number; // canvas x
  py: number; // canvas y
  radius: number;
  color: string;
  alpha: number;
}

type TimeRange = 'all' | '90d' | '60d' | '30d' | '7d';
const TIME_RANGE_DAYS: Record<TimeRange, number | null> = {
  all: null, '90d': 90, '60d': 60, '30d': 30, '7d': 7,
};

function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export default function CandlestickChart({ symbol, lockedNewsId, sourceFilter = 'all', sentimentFilter = 'all', onHover, onRangeSelect, onArticleSelect, onDayClick }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>('90d');
  const allOhlcRef = useRef<OHLCRow[]>([]);
  const allParticlesRef = useRef<Particle[]>([]);

  // Refs for interaction state (avoid re-renders)
  const placedRef = useRef<PlacedParticle[]>([]);
  const quadtreeRef = useRef<d3.Quadtree<PlacedParticle> | null>(null);
  const hoveredParticleRef = useRef<PlacedParticle | null>(null);
  const lockedNewsIdRef = useRef<string | null>(null);
  const highlightedIdsRef = useRef<Set<string> | null>(null);
  const sourceFilterRef = useRef<'all' | 'news' | 'reddit'>('all');
  const sentimentFilterRef = useRef<'all' | 'positive' | 'negative' | 'neutral'>('all');
  const marginRef = useRef({ top: 16, right: 40, bottom: 24, left: 48 });

  // Keep refs in sync with props
  useEffect(() => {
    lockedNewsIdRef.current = lockedNewsId ?? null;
    drawParticles(hoveredParticleRef.current);
  }, [lockedNewsId]);

  useEffect(() => {
    sourceFilterRef.current = sourceFilter;
    drawParticles(hoveredParticleRef.current);
  }, [sourceFilter]);

  useEffect(() => {
    sentimentFilterRef.current = sentimentFilter;
    drawParticles(hoveredParticleRef.current);
  }, [sentimentFilter]);

  const drawParticles = useCallback((highlight: PlacedParticle | null = null) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const locked = lockedNewsIdRef.current;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const placed = placedRef.current;
    const sf = sourceFilterRef.current;
    const smf = sentimentFilterRef.current;
    for (const p of placed) {
      const isLocked = locked != null && p.id === locked;
      const isHover = p === highlight;

      if (!isLocked && !isHover) {
        // Source filter
        const isReddit = p.id.startsWith('reddit_');
        if (sf === 'reddit' && !isReddit) continue;
        if (sf === 'news' && isReddit) continue;
        // Sentiment filter
        if (smf === 'all') {
          if (p.s !== 'positive' && p.s !== 'negative') continue;
        } else {
          if (p.s !== smf) continue;
        }
      }

      ctx.globalAlpha = isHover || isLocked ? 1 : p.alpha;
      ctx.fillStyle = p.color;

      if (isHover || isLocked) {
        ctx.shadowColor = isLocked ? '#00e5ff' : p.color;
        ctx.shadowBlur = 14 * dpr;
      } else {
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
      }

      ctx.beginPath();
      ctx.arc(p.px * dpr, p.py * dpr, p.radius * dpr, 0, Math.PI * 2);
      ctx.fill();

      if (isLocked) {
        ctx.shadowColor = '#00e5ff';
        ctx.shadowBlur = 10 * dpr;
        ctx.strokeStyle = '#00e5ff';
        ctx.lineWidth = 1.5 * dpr;
        ctx.beginPath();
        ctx.arc(p.px * dpr, p.py * dpr, (p.radius + 3) * dpr, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    ctx.globalAlpha = 1;
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
  }, []);

  function filterByRange(ohlc: OHLCRow[], particles: Particle[], range: TimeRange) {
    const days = TIME_RANGE_DAYS[range];
    if (!days) return { ohlc, particles };
    // Use last N trading days (data points), not calendar days
    const sliced = ohlc.slice(-days);
    const cutoffStr = sliced.length > 0 ? sliced[0].date : '';
    return {
      ohlc: sliced,
      particles: particles.filter((p) => (p.pd || p.d) >= cutoffStr),
    };
  }

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);

    Promise.all([
      axios.get<OHLCRow[]>(`/api/stocks/${symbol}/ohlc`),
      axios.get<Particle[]>(`/api/news/${symbol}/particles`).catch((err) => {
        console.error('Particle load error:', err);
        return { data: [] as Particle[] };
      }),
    ])
      .then(([ohlcRes, particlesRes]) => {
        allOhlcRef.current = ohlcRes.data;
        allParticlesRef.current = particlesRes.data;
        const { ohlc, particles } = filterByRange(ohlcRes.data, particlesRes.data, timeRange);
        drawChart(ohlc, particles);
      })
      .catch((err) => console.error('Chart error:', err))
      .finally(() => setLoading(false));
  }, [symbol]);

  useEffect(() => {
    if (!allOhlcRef.current.length) return;
    const { ohlc, particles } = filterByRange(allOhlcRef.current, allParticlesRef.current, timeRange);
    drawChart(ohlc, particles);
  }, [timeRange]);

  function drawChart(rawData: OHLCRow[], particles: Particle[]) {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const container = containerRef.current;
    if (!container) return;

    const fullWidth = container.clientWidth;
    const fullHeight = container.clientHeight || 600;
    const margin = marginRef.current;
    const width = fullWidth - margin.left - margin.right;
    const height = fullHeight - margin.top - margin.bottom;

    svg.attr('width', fullWidth).attr('height', fullHeight);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const data = rawData.map((d, i) => ({
      date: parseDateOnly(d.date),
      dateStr: d.date,
      open: +d.open,
      high: +d.high,
      low: +d.low,
      close: +d.close,
      volume: +d.volume,
      change: i > 0 ? ((+d.close - +rawData[i - 1].close) / +rawData[i - 1].close) * 100 : 0,
    }));

    // Build a lookup: dateStr → OHLC row
    const dateToOhlc = new Map<string, typeof data[0]>();
    for (const d of data) {
      dateToOhlc.set(d.dateStr, d);
    }

    // Scales — full height, no split
    // Extend x domain 3 days past last candle so weekend/holiday particles are visible
    const [xMin, xMax] = d3.extent(data, (d) => d.date) as [Date, Date];
    const xMaxExtended = new Date(xMax.getTime() + 3 * 24 * 60 * 60 * 1000);
    const x = d3.scaleTime()
      .domain([xMin, xMaxExtended])
      .range([0, width]);

    const y = d3.scaleLinear()
      .domain([d3.min(data, (d) => d.low)! * 0.92, d3.max(data, (d) => d.high)! * 1.03])
      .range([height, 0]);

    // Grid lines
    g.append('g')
      .attr('class', 'grid-y')
      .call(
        d3.axisLeft(y)
          .ticks(8)
          .tickSize(-width)
          .tickFormat(() => '')
      )
      .selectAll('line')
      .style('stroke', '#1a1e2e')
      .style('stroke-width', 1);
    g.selectAll('.grid-y .domain').remove();

    // X Axis — adaptive ticks and format based on data length
    const xTickCount = data.length <= 10 ? data.length : data.length <= 60 ? 6 : 8;
    const xFmt = data.length <= 60
      ? d3.timeFormat('%m/%d')
      : d3.timeFormat('%b %y');
    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x).ticks(xTickCount).tickFormat(xFmt as any))
      .selectAll('text')
      .style('font-size', '12px')
      .style('fill', '#555');

    // Y Axis
    g.append('g')
      .call(d3.axisLeft(y).ticks(6).tickFormat((d) => `$${Number(d).toFixed(0)}`))
      .selectAll('text')
      .style('font-size', '12px')
      .style('fill', '#555');

    g.selectAll('.domain').style('stroke', '#1a2030');
    g.selectAll('.tick line').style('stroke', '#1a2030');

    const candleWidth = Math.max(1.5, Math.min(18, (width / data.length) * 0.65));

    // Candlesticks
    const candles = g.selectAll('.candle').data(data).enter().append('g').attr('class', 'candle');

    // Wicks
    candles.append('line')
      .attr('x1', (d) => x(d.date))
      .attr('x2', (d) => x(d.date))
      .attr('y1', (d) => y(d.high))
      .attr('y2', (d) => y(d.low))
      .attr('stroke', (d) => (d.close >= d.open ? '#00e676' : '#ff5252'))
      .attr('stroke-width', 1);

    // Bodies
    candles.append('rect')
      .attr('x', (d) => x(d.date) - candleWidth / 2)
      .attr('y', (d) => y(Math.max(d.open, d.close)))
      .attr('width', candleWidth)
      .attr('height', (d) => Math.max(1, Math.abs(y(d.open) - y(d.close))))
      .attr('fill', (d) => (d.close >= d.open ? '#00e676' : '#ff5252'));

    // --- Place particles overlaid on K-line ---
    // Group particles by actual published date (pd) for x positioning
    const particlesByDate = new Map<string, Particle[]>();
    for (const p of particles) {
      const key = p.pd || p.d;
      const arr = particlesByDate.get(key) || [];
      arr.push(p);
      particlesByDate.set(key, arr);
    }

    // Sorted dates for finding nearest trading day
    const sortedDates = data.map((d) => d.date.getTime()).sort((a, b) => a - b);

    const placed: PlacedParticle[] = [];
    // Particle vertical spacing in pixels
    const pSpacing = Math.max(4.5, Math.min(7, height / 80));

    for (const [dateStr, pArr] of particlesByDate) {
      const ohlc = dateToOhlc.get(dateStr);

      // For weekend/holiday dates: use time scale x, nearest trading day y
      const cx = ohlc ? x(ohlc.date) : x(parseDateOnly(dateStr));

      // Sort: relevant first, then by |ret_t1| descending
      pArr.sort((a, b) => {
        const ra = a.r === 'relevant' ? 0 : 1;
        const rb = b.r === 'relevant' ? 0 : 1;
        if (ra !== rb) return ra - rb;
        return Math.abs(b.rt1 || 0) - Math.abs(a.rt1 || 0);
      });

      // Stack particles downward from the candle low (or nearest trading day's low for weekend)
      let baseY: number;
      if (ohlc) {
        baseY = y(ohlc.low);
      } else {
        const t = parseDateOnly(dateStr).getTime();
        const nearest = sortedDates.reduce((prev, cur) =>
          Math.abs(cur - t) < Math.abs(prev - t) ? cur : prev
        );
        const nearestDate = data.find((d) => d.date.getTime() === nearest);
        const nearestOhlc = nearestDate ? dateToOhlc.get(nearestDate.dateStr) : undefined;
        baseY = nearestOhlc ? y(nearestOhlc.low) : y((d3.min(data, (d) => d.low)! + d3.max(data, (d) => d.high)!) / 2);
      }
      for (let i = 0; i < pArr.length; i++) {
        const p = pArr[i];
        const radius = getParticleRadius(p.r, p.rt1);
        const py = margin.top + baseY + 6 + i * pSpacing;

        // Don't render if beyond chart bottom
        if (py > margin.top + height + 10) break;

        placed.push({
          ...p,
          px: margin.left + cx,
          py,
          radius,
          color: getSentimentColor(p.s),
          alpha: getParticleAlpha(p.r),
        });
      }
    }

    placedRef.current = placed;

    // Build quadtree for hit testing
    quadtreeRef.current = d3.quadtree<PlacedParticle>()
      .x((d) => d.px)
      .y((d) => d.py)
      .addAll(placed);

    // --- Setup Canvas ---
    const canvas = canvasRef.current;
    if (canvas) {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = fullWidth * dpr;
      canvas.height = fullHeight * dpr;
      canvas.style.width = `${fullWidth}px`;
      canvas.style.height = `${fullHeight}px`;
      drawParticles();
    }

    // --- Crosshair elements ---
    const crossV = g.append('line')
      .style('stroke', '#333')
      .style('stroke-width', 0.5)
      .style('stroke-dasharray', '4,3')
      .style('display', 'none')
      .style('pointer-events', 'none');

    const crossH = g.append('line')
      .style('stroke', '#333')
      .style('stroke-width', 0.5)
      .style('stroke-dasharray', '4,3')
      .style('display', 'none')
      .style('pointer-events', 'none');

    // Price label on Y axis
    const priceLabel = g.append('g').style('display', 'none');
    priceLabel.append('rect')
      .attr('fill', '#1a1e2e')
      .attr('rx', 3)
      .attr('width', 46)
      .attr('height', 18);
    priceLabel.append('text')
      .attr('fill', '#aaa')
      .attr('font-size', '12px')
      .attr('text-anchor', 'middle')
      .attr('dy', '13px');

    // Date label on X axis
    const dateLabel = g.append('g').style('display', 'none');
    dateLabel.append('rect')
      .attr('fill', '#1a1e2e')
      .attr('rx', 3)
      .attr('width', 75)
      .attr('height', 20);
    dateLabel.append('text')
      .attr('fill', '#aaa')
      .attr('font-size', '13px')
      .attr('text-anchor', 'middle')
      .attr('dy', '14px');

    // Bisector for snapping to nearest date
    const bisect = d3.bisector<typeof data[0], Date>((d) => d.date).left;

    function snapToData(px: number) {
      const xDate = x.invert(px);
      const idx = bisect(data, xDate, 1);
      const d0 = data[idx - 1];
      const d1 = data[idx];
      if (!d0) return data[0];
      return d1 && xDate.getTime() - d0.date.getTime() > d1.date.getTime() - xDate.getTime() ? d1 : d0;
    }

    // --- Particle hit testing ---
    function findParticle(mouseX: number, mouseY: number): PlacedParticle | null {
      const qt = quadtreeRef.current;
      if (!qt) return null;
      const searchRadius = 8;
      let closest: PlacedParticle | null = null;
      let closestDist = searchRadius;
      const hlSet = highlightedIdsRef.current;
      const locked = lockedNewsIdRef.current;

      qt.visit((node, x0, y0, x1, y1) => {
        if (!('data' in node)) {
          return x0 > mouseX + searchRadius || x1 < mouseX - searchRadius ||
                 y0 > mouseY + searchRadius || y1 < mouseY - searchRadius;
        }
        let leaf: typeof node | undefined = node;
        while (leaf) {
          const p = leaf.data;
          // Skip particles hidden by category filter
          if (hlSet != null && !hlSet.has(p.id) && p.id !== locked) {
            leaf = (leaf as any).next;
            continue;
          }
          const dx = p.px - mouseX;
          const dy = p.py - mouseY;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < closestDist) {
            closestDist = dist;
            closest = p;
          }
          leaf = (leaf as any).next;
        }
        return false;
      });

      return closest;
    }

    // D3 Brush for range selection
    let brushMoving = false;
    const brush = d3.brushX<unknown>()
      .extent([[0, 0], [width, height + margin.bottom]])
      .on('end', function (event) {
        if (brushMoving) return; // guard against re-entrancy from brush.move
        if (!event.selection) {
          // Click (not drag) — find similar days or toggle lock
          if (event.sourceEvent) {
            const [mx] = d3.pointer(event.sourceEvent, g.node());
            const d = snapToData(mx);
            const [absX, absY] = d3.pointer(event.sourceEvent, container);
            const hit = findParticle(absX, absY);
            if (hit) {
              onArticleSelect?.({ newsId: hit.id, date: hit.d });
            } else {
              // Click on background: unlock any locked article, then show similar days
              onArticleSelect?.(null);
              onDayClick?.(d.dateStr);
            }
          }
          return;
        }
        const [x0, x1] = event.selection as [number, number];
        const d0 = snapToData(x0);
        const d1 = snapToData(x1);
        if (d0.dateStr === d1.dateStr) {
          brushMoving = true;
          d3.select(this).call(brush.move, null);
          brushMoving = false;
          return;
        }
        brushMoving = true;
        d3.select(this).call(brush.move, [x(d0.date), x(d1.date)]);
        brushMoving = false;
        const priceChange = ((d1.close - d0.open) / d0.open) * 100;
        // Position popup near the right edge of the selection, within the chart container
        const popupX = margin.left + x(d1.date) + 8;
        const popupY = margin.top + Math.min(y(d0.close), y(d1.close)) - 20;
        onRangeSelect?.({ startDate: d0.dateStr, endDate: d1.dateStr, priceChange, popupX, popupY });
      });

    const brushG = g.append('g')
      .attr('class', 'brush')
      .call(brush);

    brushG.selectAll('.selection')
      .attr('fill', '#667eea')
      .attr('fill-opacity', 0.15)
      .attr('stroke', '#667eea')
      .attr('stroke-width', 1);

    // Hover events on the brush overlay
    brushG.select('.overlay')
      .style('cursor', 'crosshair')
      .on('mousemove.hover', function (event) {
        const [mx, my] = d3.pointer(event);
        const d = snapToData(mx);
        const cx = x(d.date);
        const priceAtY = y.invert(my);

        // Vertical crosshair
        crossV.attr('x1', cx).attr('x2', cx).attr('y1', 0).attr('y2', height).style('display', null);
        // Horizontal crosshair
        crossH.attr('x1', 0).attr('x2', width).attr('y1', my).attr('y2', my).style('display', null);

        // Price label
        priceLabel.style('display', null)
          .attr('transform', `translate(${-46},${my - 9})`);
        priceLabel.select('text')
          .attr('x', 23)
          .text(`$${priceAtY.toFixed(2)}`);

        // Date label
        dateLabel.style('display', null)
          .attr('transform', `translate(${cx - 37.5},${height})`);
        dateLabel.select('text')
          .attr('x', 37.5)
          .text(d.dateStr);

        // Emit hover for OHLC
        onHover(d.dateStr, {
          date: d.dateStr,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          change: d.change,
        });

        // Check particle hover
        const [absX, absY] = d3.pointer(event, container);
        const hit = findParticle(absX, absY);

        if (hit !== hoveredParticleRef.current) {
          hoveredParticleRef.current = hit;
          drawParticles(hit);

          const tooltip = tooltipRef.current;
          if (tooltip) {
            if (hit) {
              const retStr = hit.rt1 !== null ? `${(hit.rt1 * 100).toFixed(2)}%` : '-';
              const retColor = hit.rt1 !== null ? (hit.rt1 >= 0 ? '#00e676' : '#ff5252') : '#555';
              tooltip.innerHTML = `
                <div class="pt-title">${hit.t}</div>
                <div class="pt-meta">
                  <span class="pt-sentiment" style="color:${hit.color}">${hit.s || 'unknown'}</span>
                  <span class="pt-ret" style="color:${retColor}">T+1: ${retStr}</span>
                </div>
              `;
              tooltip.style.display = 'block';
              const tipW = 280; // max-width of tooltip
              const onRight = hit.px < fullWidth / 2;
              const tipX = onRight ? hit.px + 12 : hit.px - tipW - 12;
              const tipY = hit.py - 40;
              tooltip.style.left = `${Math.max(4, tipX)}px`;
              tooltip.style.top = `${Math.max(4, tipY)}px`;
            } else {
              tooltip.style.display = 'none';
            }
          }
        }
      })
      .on('mouseleave.hover', function () {
        crossV.style('display', 'none');
        crossH.style('display', 'none');
        priceLabel.style('display', 'none');
        dateLabel.style('display', 'none');
        onHover(null);

        if (hoveredParticleRef.current) {
          hoveredParticleRef.current = null;
          drawParticles();
        }
        const tooltip = tooltipRef.current;
        if (tooltip) tooltip.style.display = 'none';
      });
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="chart-time-range">
        {(['7d', '30d', '60d', '90d', 'all'] as TimeRange[]).map((r) => (
          <button
            key={r}
            className={`chart-range-btn ${timeRange === r ? 'active' : ''}`}
            onClick={() => setTimeRange(r)}
          >
            {r === 'all' ? 'All' : r.toUpperCase()}
          </button>
        ))}
      </div>
      <div ref={containerRef} className="chart-container" style={{ flex: 1 }}>
        {loading && <div className="chart-loading">Loading...</div>}
        <svg ref={svgRef}></svg>
        <canvas
          ref={canvasRef}
          className="particle-layer"
        />
        <div ref={tooltipRef} className="particle-tooltip" style={{ display: 'none' }} />
      </div>
    </div>
  );
}
