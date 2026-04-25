import { useState, useRef, useEffect, lazy, Suspense } from 'react';
import './overall.css';
import AISidebar from './AISidebar';

const MarketView    = lazy(() => import('./MarketView'));
const ChartingView  = lazy(() => import('./ChartingView'));
const StockView     = lazy(() => import('./StockView'));
const ScreenerView  = lazy(() => import('./ScreenerView'));
const CalendarView  = lazy(() => import('./CalendarView'));
const WatchlistView = lazy(() => import('./WatchlistView'));
const LibraryView   = lazy(() => import('./LibraryView'));

type Tab = 'dashboard' | 'charting' | 'fundamentals' | 'screener' | 'calendar' | 'watchlist' | 'library';

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'dashboard',    label: 'Dashboard',    icon: '⬛' },
  { key: 'charting',     label: 'Charting',     icon: '📈' },
  { key: 'fundamentals', label: 'Data',         icon: '📋' },
  { key: 'screener',     label: 'Screener',     icon: '🔍' },
  { key: 'calendar',     label: 'Calendar',     icon: '📅' },
  { key: 'watchlist',    label: 'Watchlist',    icon: '⭐' },
  { key: 'library',      label: 'Library',      icon: '📚' },
];

export default function OverallApp() {
  const [tab,    setTab]    = useState<Tab>('dashboard');
  const [symbol, setSymbol] = useState('AAPL');
  const [visited, setVisited] = useState<Set<Tab>>(new Set(['dashboard']));
  const chartCaptureRef = useRef<(() => Promise<string>) | null>(null);

  const [analystName, setAnalystName] = useState<string>(() =>
    localStorage.getItem('ivytrader_analyst') ?? ''
  );

  const [watchlist, setWatchlist] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('ivytrader_watchlist') ?? '[]'); }
    catch { return []; }
  });
  useEffect(() => {
    localStorage.setItem('ivytrader_watchlist', JSON.stringify(watchlist));
  }, [watchlist]);
  useEffect(() => {
    localStorage.setItem('ivytrader_analyst', analystName);
  }, [analystName]);
  const addToWatchlist    = (sym: string) => setWatchlist(prev => prev.includes(sym) ? prev : [...prev, sym]);
  const removeFromWatchlist = (sym: string) => setWatchlist(prev => prev.filter(s => s !== sym));

  const goStock = (sym: string) => {
    const s = sym.toUpperCase();
    setSymbol(s);
    setTab('fundamentals');
    setVisited(v => new Set([...v, 'fundamentals']));
  };

  const goChart = (sym: string) => {
    const s = sym.toUpperCase();
    setSymbol(s);
    setTab('charting');
    setVisited(v => new Set([...v, 'charting']));
  };

  function handleTabChange(t: Tab) {
    setTab(t);
    setVisited(v => new Set([...v, t]));
  }

  const aiContextLabel = tab === 'dashboard'    ? 'Market Overview'
    : tab === 'charting'     ? `Chart · ${symbol}`
    : tab === 'fundamentals' ? `${symbol} · Data`
    : tab === 'screener'     ? 'Screener'
    : tab === 'calendar'     ? 'Calendar'
    : '';

  const aiContext = tab === 'fundamentals'
    ? `User is viewing the Data page for stock: ${symbol}. They can see quote, financials, analyst ratings, institutional ownership, peers comparison, and SEC filings for this company.`
    : tab === 'dashboard'
    ? `User is viewing the Market Dashboard with indices (SPY, QQQ, DIA), top gainers/losers, most active stocks, market news, and upcoming earnings.`
    : tab === 'screener'
    ? `User is using the Stock Screener to filter stocks by sector, price, market cap, volume, and beta.`
    : tab === 'calendar'
    ? `User is viewing the financial calendar with upcoming earnings reports, IPOs, and dividend dates.`
    : tab === 'charting'
    ? `User is viewing the price chart for ${symbol} with candlestick data and moving averages.`
    : '';

  return (
    <div className="overall-container">
      <nav className="overall-subnav">
        <div className="subnav-brand">Terminal</div>
        {TABS.map(({ key, label, icon }) => (
          <button
            key={key}
            className={`subnav-btn ${tab === key ? 'active' : ''}`}
            onClick={() => handleTabChange(key)}
          >
            <span className="subnav-icon">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <input
          className="subnav-analyst-input"
          placeholder="Your name..."
          value={analystName}
          onChange={e => setAnalystName(e.target.value)}
          title="Analyst name shown when saving reports"
        />
      </nav>

      <div className="overall-body">
        <div className="overall-content">
          <Suspense fallback={<div className="overall-loading">Loading...</div>}>
            <div style={{ display: tab === 'dashboard'    ? 'block' : 'none' }}>
              {visited.has('dashboard') && <MarketView onSelectStock={goStock} />}
            </div>
            <div style={{ display: tab === 'charting'     ? 'block' : 'none' }}>
              {visited.has('charting') && <ChartingView symbol={symbol} onSelectStock={goChart} onChartReady={(fn) => { chartCaptureRef.current = fn; }} watchlist={watchlist} onAddToWatchlist={addToWatchlist} onRemoveFromWatchlist={removeFromWatchlist} />}
            </div>
            <div style={{ display: tab === 'fundamentals' ? 'block' : 'none' }}>
              {visited.has('fundamentals') && <StockView symbol={symbol} onSelectStock={goStock} watchlist={watchlist} onAddToWatchlist={addToWatchlist} onRemoveFromWatchlist={removeFromWatchlist} analystName={analystName} />}
            </div>
            <div style={{ display: tab === 'screener'     ? 'block' : 'none' }}>
              {visited.has('screener') && <ScreenerView onSelectStock={goStock} />}
            </div>
            <div style={{ display: tab === 'calendar'     ? 'block' : 'none' }}>
              {visited.has('calendar') && <CalendarView onSelectStock={goStock} />}
            </div>
            <div style={{ display: tab === 'watchlist'    ? 'block' : 'none' }}>
              {visited.has('watchlist') && (
                <WatchlistView
                  watchlist={watchlist}
                  onAdd={addToWatchlist}
                  onRemove={removeFromWatchlist}
                  onSelectStock={goStock}
                  onGoChart={goChart}
                />
              )}
            </div>
            <div style={{ display: tab === 'library' ? 'block' : 'none', height: '100%' }}>
              {visited.has('library') && (
                <LibraryView onSelectStock={goStock} analystName={analystName} />
              )}
            </div>
          </Suspense>
        </div>

        <AISidebar tab={tab} symbol={symbol} chartCapture={chartCaptureRef} />
      </div>
    </div>
  );
}
