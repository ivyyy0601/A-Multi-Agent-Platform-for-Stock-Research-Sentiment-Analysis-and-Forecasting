import { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';

// Simple markdown renderer for AI panel
function renderMd(text: string) {
  return text.split('\n').map((line, i) => {
    if (line.startsWith('### ')) return <div key={i} style={{ fontWeight: 700, color: '#a0aec0', fontSize: 12, margin: '10px 0 4px' }}>{line.slice(4)}</div>;
    if (line.startsWith('## '))  return <div key={i} style={{ fontWeight: 700, color: '#6c8fff', fontSize: 13, margin: '12px 0 5px', borderBottom: '1px solid #1e2130', paddingBottom: 4 }}>{line.slice(3)}</div>;
    if (line.startsWith('- '))   return <div key={i} style={{ paddingLeft: 12, color: '#ccc', fontSize: 12, margin: '2px 0' }}>• {line.slice(2).replace(/\*\*([^*]+)\*\*/g, '$1')}</div>;
    if (/^---+$/.test(line.trim())) return <hr key={i} style={{ border: 'none', borderTop: '1px solid #1e2130', margin: '8px 0' }} />;
    if (line.trim() === '') return <div key={i} style={{ height: 6 }} />;
    const bold = line.replace(/\*\*([^*]+)\*\*/g, '|||B|||$1|||/B|||');
    const parts = bold.split('|||');
    return (
      <p key={i} style={{ margin: '0 0 5px', fontSize: 12, color: '#ccc', lineHeight: 1.6 }}>
        {parts.map((p, j) => p.startsWith('B|||') ? <strong key={j} style={{ color: '#e0e0e0' }}>{p.slice(4)}</strong> : p.startsWith('/B|||') ? null : p)}
      </p>
    );
  });
}

interface Props {
  symbol?: string;
  onSelectStock: (sym: string) => void;
  onChartReady?: (captureFunc: () => Promise<string>) => void;
  watchlist?: string[];
  onAddToWatchlist?: (sym: string) => void;
  onRemoveFromWatchlist?: (sym: string) => void;
}

function price(n: any) { const v = parseFloat(n); return isNaN(v) ? '-' : '$' + v.toFixed(2); }
function pct(n: any)   { const v = parseFloat(n); if (isNaN(v)) return '-'; return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
function vol(n: any)   { const v = parseFloat(n); if (isNaN(v)) return '-'; if (v >= 1e9) return (v/1e9).toFixed(1)+'B'; if (v >= 1e6) return (v/1e6).toFixed(1)+'M'; if (v >= 1e3) return (v/1e3).toFixed(1)+'K'; return String(v); }

type Period = '1w' | '1m' | '3m' | '6m' | '1y' | '2y';

interface Bar { date: string; open: number; high: number; low: number; close: number; volume: number }

function calcSMA(data: Bar[], period: number): (number | null)[] {
  return data.map((_, i) => {
    if (i < period - 1) return null;
    const avg = data.slice(i - period + 1, i + 1).reduce((s, d) => s + d.close, 0) / period;
    return parseFloat(avg.toFixed(2));
  });
}

export default function ChartingView({ symbol: initSym = 'AAPL', onSelectStock, onChartReady, watchlist = [], onAddToWatchlist, onRemoveFromWatchlist }: Props) {
  const [input,    setInput]    = useState(initSym);
  const [symbol,   setSymbol]   = useState(initSym);
  const [period,   setPeriod]   = useState<Period>('3m');

  useEffect(() => {
    setInput(initSym);
    setSymbol(initSym);
  }, [initSym]);
  const [quote,    setQuote]    = useState<any>(null);
  const [bars,     setBars]     = useState<Bar[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [showMA20, setShowMA20] = useState(true);
  const [showMA50, setShowMA50] = useState(true);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 420 });
  const [aiLoading, setAiLoading] = useState(false);

  // Expose capture function to parent whenever chart is ready
  useEffect(() => {
    if (bars.length === 0 || !svgRef.current) return;
    onChartReady?.(() => captureChartSVG());
  }, [bars, dims]);

  useEffect(() => {
    setInput(symbol);
    axios.get(`/api/market/stock/${symbol}/quote`)
      .then(r => setQuote(Array.isArray(r.data) ? r.data[0] : null))
      .catch(() => null);
  }, [symbol]);

  useEffect(() => {
    setLoading(true);
    axios.get(`/api/market/stock/${symbol}/historical?period=${period}`)
      .then(r => {
        const raw = (Array.isArray(r.data) ? r.data : [])
          .filter((d: any) => d.date && d.close)
          .sort((a: any, b: any) => a.date.localeCompare(b.date));
        setBars(raw.map((d: any) => ({
          date:   (d.date ?? '').slice(0, 10),
          open:   parseFloat(d.open ?? 0),
          high:   parseFloat(d.high ?? 0),
          low:    parseFloat(d.low  ?? 0),
          close:  parseFloat(d.close ?? 0),
          volume: parseFloat(d.volume ?? 0),
        })));
      })
      .catch(() => setBars([]))
      .finally(() => setLoading(false));
  }, [symbol, period]);

  // Measure container
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setDims({ w: Math.floor(width), h: Math.floor(height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  function search() { const s = input.trim().toUpperCase(); if (s) { setSymbol(s); onSelectStock(s); } }

  // ── Chart math ────────────────────────────────────────────────
  const PAD = { top: 20, right: 70, bottom: 32, left: 8 };
  const VOL_H = 60;
  const chartH = dims.h - PAD.top - PAD.bottom - VOL_H - 10;
  const chartW = dims.w - PAD.left - PAD.right;

  const ma20 = calcSMA(bars, 20);
  const ma50 = calcSMA(bars, 50);

  const highs   = bars.map(b => b.high);
  const lows    = bars.map(b => b.low);
  const volumes = bars.map(b => b.volume);

  const priceMin = lows.length   ? Math.min(...lows)   * 0.998 : 0;
  const priceMax = highs.length  ? Math.max(...highs)  * 1.002 : 1;
  const volMax   = volumes.length ? Math.max(...volumes) * 1.1  : 1;

  const n = bars.length;
  const barW = n > 0 ? Math.max(1, chartW / n - 1) : 4;

  function xOf(i: number) { return PAD.left + (i + 0.5) * (chartW / n); }
  function yPrice(v: number) { return PAD.top + chartH - ((v - priceMin) / (priceMax - priceMin)) * chartH; }
  function yVol(v: number)   { return PAD.top + chartH + 10 + VOL_H - (v / volMax) * VOL_H; }

  // MA paths
  function maPath(data: (number | null)[]) {
    let d = ''; let first = true;
    data.forEach((v, i) => {
      if (v == null) return;
      d += `${first ? 'M' : 'L'}${xOf(i).toFixed(1)},${yPrice(v).toFixed(1)} `;
      first = false;
    });
    return d;
  }

  // Y axis ticks
  const yTicks = 5;
  const yTickVals = Array.from({ length: yTicks }, (_, i) => priceMin + ((priceMax - priceMin) * i) / (yTicks - 1));
  const xTickStep = Math.max(1, Math.floor(n / 7));
  const xTicks = Array.from({ length: n }, (_, i) => i).filter(i => i % xTickStep === 0);

  const hBar = hoverIdx !== null ? bars[hoverIdx] : null;
  const chgPct = parseFloat(quote?.change_percent ?? 0);
  const isUp   = chgPct >= 0;
  const lineColor = isUp ? '#00e676' : '#ff5252';

  async function captureChartSVG(): Promise<string> {
    if (!svgRef.current) return '';
    try {
      const svgData = new XMLSerializer().serializeToString(svgRef.current);
      const canvas  = document.createElement('canvas');
      canvas.width  = dims.w * 2;
      canvas.height = dims.h * 2;
      const ctx = canvas.getContext('2d')!;
      ctx.scale(2, 2);
      ctx.fillStyle = '#0d0f17';
      ctx.fillRect(0, 0, dims.w, dims.h);
      await new Promise<void>((resolve) => {
        const img  = new Image();
        const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        const url  = URL.createObjectURL(blob);
        img.onload  = () => { ctx.drawImage(img, 0, 0, dims.w, dims.h); URL.revokeObjectURL(url); resolve(); };
        img.onerror = () => { URL.revokeObjectURL(url); resolve(); };
        img.src = url;
      });
      return canvas.toDataURL('image/png').split(',')[1];
    } catch { return ''; }
  }

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current || !n) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left - PAD.left;
    const idx = Math.round(mx / (chartW / n) - 0.5);
    setHoverIdx(idx >= 0 && idx < n ? idx : null);
  }, [n, chartW]);

  return (
    <div className="charting-view">
      {/* Toolbar */}
      <div className="charting-toolbar">
        <div className="charting-search">
          <input className="stock-search-input" value={input} placeholder="股票代码 AAPL"
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && search()} />
          <button className="stock-search-btn" onClick={search}>查询</button>
        </div>

        {quote && (
          <div className="charting-quote">
            <span className="cq-symbol">{symbol}</span>
            <span className="cq-price">{price(quote.price)}</span>
            <span className={`cq-chg ${isUp ? 'positive' : 'negative'}`}>{pct(chgPct)}</span>
            <span className="cq-detail muted">开 {price(quote.open)}  高 {price(quote.high)}  低 {price(quote.low)}  量 {vol(quote.volume)}</span>
          </div>
        )}

        <div className="charting-controls">
          {watchlist.includes(symbol)
            ? <button className="wl-star-btn wl-star-on"  onClick={() => onRemoveFromWatchlist?.(symbol)}>⭐</button>
            : <button className="wl-star-btn wl-star-off" onClick={() => onAddToWatchlist?.(symbol)}>☆ 关注</button>
          }
          <div className="period-group">
            {(['1w','1m','3m','6m','1y','2y'] as Period[]).map(p => (
              <button key={p} className={`period-btn ${period === p ? 'active' : ''}`} onClick={() => setPeriod(p)}>
                {p.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="indicator-group">
            <button className={`ind-btn ${showMA20 ? 'active ma20' : ''}`} onClick={() => setShowMA20(v => !v)}>MA20</button>
            <button className={`ind-btn ${showMA50 ? 'active ma50' : ''}`} onClick={() => setShowMA50(v => !v)}>MA50</button>
          </div>
        </div>
      </div>

      {/* Hover info bar */}
      <div className="chart-hover-bar">
        {hBar ? (
          <>
            <span className="muted">{hBar.date}</span>
            <span>开 <b>{price(hBar.open)}</b></span>
            <span>高 <b style={{ color: '#00e676' }}>{price(hBar.high)}</b></span>
            <span>低 <b style={{ color: '#ff5252' }}>{price(hBar.low)}</b></span>
            <span>收 <b style={{ color: lineColor }}>{price(hBar.close)}</b></span>
            <span className="muted">量 {vol(hBar.volume)}</span>
            {showMA20 && ma20[hoverIdx!] != null && <span style={{ color: '#ffd740' }}>MA20 {price(ma20[hoverIdx!])}</span>}
            {showMA50 && ma50[hoverIdx!] != null && <span style={{ color: '#ff9800' }}>MA50 {price(ma50[hoverIdx!])}</span>}
          </>
        ) : (
          <span className="muted">将鼠标移到图表上查看详情</span>
        )}
      </div>

      {/* SVG Chart */}
      <div ref={containerRef} style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0d0f17cc', zIndex: 5, fontSize: 13, color: '#555' }}>加载中...</div>
        )}
        {!loading && bars.length === 0 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#555', fontSize: 13 }}>暂无数据</div>
        )}
        {!loading && bars.length > 0 && (
          <svg ref={svgRef} width={dims.w} height={dims.h} style={{ display: 'block' }}
            onMouseMove={handleMouseMove} onMouseLeave={() => setHoverIdx(null)}>
            {/* Y grid + labels */}
            {yTickVals.map((v, i) => (
              <g key={i}>
                <line x1={PAD.left} x2={dims.w - PAD.right} y1={yPrice(v)} y2={yPrice(v)} stroke="#1a1d27" strokeWidth={1} />
                <text x={dims.w - PAD.right + 6} y={yPrice(v) + 4} fontSize={10} fill="#444">${v.toFixed(0)}</text>
              </g>
            ))}

            {/* X labels */}
            {xTicks.map(i => (
              <text key={i} x={xOf(i)} y={PAD.top + chartH + 8 + VOL_H + 16} fontSize={10} fill="#444" textAnchor="middle">
                {bars[i]?.date.slice(5)}
              </text>
            ))}

            {/* Candlesticks */}
            {bars.map((b, i) => {
              const isUp  = b.close >= b.open;
              const color = isUp ? '#00e676' : '#ff5252';
              const cx    = xOf(i);
              const bw    = Math.max(1, barW * 0.75);
              const bodyY = yPrice(Math.max(b.open, b.close));
              const bodyH = Math.max(1, Math.abs(yPrice(b.open) - yPrice(b.close)));
              return (
                <g key={i}>
                  {/* Wick */}
                  <line x1={cx} x2={cx} y1={yPrice(b.high)} y2={yPrice(b.low)}
                    stroke={color} strokeWidth={1} />
                  {/* Body */}
                  <rect
                    x={cx - bw / 2} y={bodyY}
                    width={bw} height={bodyH}
                    fill={isUp ? color : 'none'}
                    stroke={color} strokeWidth={1}
                  />
                </g>
              );
            })}

            {/* MA lines */}
            {showMA20 && <path d={maPath(ma20)} fill="none" stroke="#ffd740" strokeWidth={1.2} opacity={0.9} />}
            {showMA50 && <path d={maPath(ma50)} fill="none" stroke="#ff9800" strokeWidth={1.2} opacity={0.9} />}

            {/* Volume bars */}
            {bars.map((b, i) => {
              const isUp = b.close >= b.open;
              const bh   = Math.max(2, (b.volume / volMax) * VOL_H);
              return (
                <rect key={i}
                  x={xOf(i) - barW * 0.35} y={yVol(b.volume)}
                  width={Math.max(1, barW * 0.7)} height={bh}
                  fill={isUp ? '#00e67640' : '#ff525240'}
                />
              );
            })}

            {/* Hover crosshair */}
            {hoverIdx !== null && (
              <>
                <line x1={xOf(hoverIdx)} x2={xOf(hoverIdx)} y1={PAD.top} y2={PAD.top + chartH + VOL_H + 10}
                  stroke="#3a3d4a" strokeWidth={1} strokeDasharray="3,3" />
                <line x1={PAD.left} x2={dims.w - PAD.right} y1={yPrice(bars[hoverIdx].close)} y2={yPrice(bars[hoverIdx].close)}
                  stroke="#3a3d4a" strokeWidth={1} strokeDasharray="3,3" />
                <text x={dims.w - PAD.right + 4} y={yPrice(bars[hoverIdx].close) + 4} fontSize={10}
                  fill={bars[hoverIdx].close >= bars[hoverIdx].open ? '#00e676' : '#ff5252'}>
                  ${bars[hoverIdx].close.toFixed(2)}
                </text>
              </>
            )}
          </svg>
        )}
      </div>

    </div>
  );
}
