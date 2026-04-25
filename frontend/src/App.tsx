import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import AppNav from './components/AppNav';
import axios from 'axios';
import StockSelector from './components/StockSelector';
import CandlestickChart from './components/CandlestickChart';
import NewsPanel from './components/NewsPanel';
import RangeAnalysisPanel from './components/RangeAnalysisPanel';
import RangeQueryPopup from './components/RangeQueryPopup';
import RangeNewsPanel from './components/RangeNewsPanel';
import SimilarDaysPanel from './components/SimilarDaysPanel';
import PredictionPanel from './components/PredictionPanel';
import DatePickerPopup from './components/DatePickerPopup';
import './App.css';

const AnalysisApp = lazy(() => import('./views/analysis/AnalysisApp'));
const SentimentApp = lazy(() => import('./views/sentiment/SentimentApp'));
const SocialApp = lazy(() => import('./views/social/SocialApp'));
const TeamApp = lazy(() => import('./views/team/TeamApp'));
const AutomationApp = lazy(() => import('./views/automation/AutomationApp'));
const OverallApp = lazy(() => import('./views/overall/OverallApp'));

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

function App() {
  const [activeTickers, setActiveTickers] = useState<string[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [hoveredDate, setHoveredDate] = useState<string | null>(null);
  const [hoveredOhlc, setHoveredOhlc] = useState<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    change: number;
  } | null>(null);
  const [selectedRange, setSelectedRange] = useState<RangeSelection | null>(null);
  const [rangeQuestion, setRangeQuestion] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<ArticleSelection | null>(null);
  const [lockedArticle, setLockedArticle] = useState<ArticleSelection | null>(null);
  const [activeView, setActiveView] = useState<'ticker' | 'analysis' | 'adanos' | 'social' | 'team' | 'automation' | 'overall'>('team');
  const [overallEverActive, setOverallEverActive] = useState(false);
  const [analysisEverActive, setAnalysisEverActive] = useState(false);
  const [sentimentEverActive, setSentimentEverActive] = useState(false);
  const [socialEverActive, setSocialEverActive] = useState(false);
  const [teamEverActive, setTeamEverActive] = useState(true);
  const [automationEverActive, setAutomationEverActive] = useState(false);
  const [socialInitTicker, setSocialInitTicker] = useState<string | undefined>(undefined);
  const [sourceFilter, setSourceFilter] = useState<'all' | 'news' | 'reddit'>('all');
  const [sentimentFilter, setSentimentFilter] = useState<'all' | 'positive' | 'negative' | 'neutral'>('all');
  const chartAreaRef = useRef<HTMLDivElement>(null);
  const [chartRect, setChartRect] = useState<DOMRect | undefined>(undefined);

  useEffect(() => {
    axios
      .get('/api/stocks')
      .then((res) => {
        const tickers = res.data
          .filter((t: any) => t.last_ohlc_fetch)
          .map((t: any) => t.symbol);
        setActiveTickers(tickers);
        if (tickers.length > 0 && !selectedSymbol) {
          setSelectedSymbol(tickers[0]);
        }
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedRange && chartAreaRef.current) {
      setChartRect(chartAreaRef.current.getBoundingClientRect());
    }
  }, [selectedRange]);

  useEffect(() => {
    const handler = (e: Event) => {
      const ticker = (e as CustomEvent<{ ticker: string }>).detail?.ticker;
      if (ticker) setSocialInitTicker(ticker);
      setActiveView('social');
      setSocialEverActive(true);
    };
    window.addEventListener('navigate-social', handler);
    return () => window.removeEventListener('navigate-social', handler);
  }, []);

  useEffect(() => {
    const handler = (e: Event) => {
      const ticker = (e as CustomEvent<{ ticker: string }>).detail?.ticker;
      if (ticker) handleSelectSymbol(ticker);
      setActiveView('ticker');
    };
    window.addEventListener('navigate-ticker', handler);
    return () => window.removeEventListener('navigate-ticker', handler);
  }, []);

  useEffect(() => {
    const handler = () => {
      setActiveView('adanos');
      setSentimentEverActive(true);
    };
    window.addEventListener('navigate-adanos', handler);
    return () => window.removeEventListener('navigate-adanos', handler);
  }, []);

  const handleHover = useCallback(
    (date: string | null, ohlc?: { date: string; open: number; high: number; low: number; close: number; change: number }) => {
      if (!lockedArticle) setHoveredDate(date);
      setHoveredOhlc(ohlc || null);
    },
    [lockedArticle]
  );

  const handleRangeSelect = useCallback((range: RangeSelection | null) => {
    setSelectedRange(range);
    setRangeQuestion(null);
    if (range) {
      setSelectedDay(null);
      setSelectedArticle(null);
      setLockedArticle(null);
    }
  }, []);

  const handleArticleSelect = useCallback((article: ArticleSelection | null) => {
    if (article === null) {
      setLockedArticle(null);
      setSelectedArticle(null);
      return;
    }
    setLockedArticle((prev) => {
      if (prev && prev.newsId === article.newsId) {
        setSelectedArticle(null);
        return null;
      }
      setSelectedArticle(article);
      setSelectedRange(null);
      setRangeQuestion(null);
      setSelectedDay(null);
      setHoveredDate(article.date);
      return article;
    });
  }, []);

  const handleDayClick = useCallback((date: string) => {
    setSelectedDay(date);
    setSelectedRange(null);
    setRangeQuestion(null);
    setSelectedArticle(null);
    setLockedArticle(null);
  }, []);

  const handleRangeAsk = useCallback((question: string) => {
    setRangeQuestion(question);
  }, []);

  function handleSelectSymbol(symbol: string) {
    setSelectedSymbol(symbol);
    setHoveredDate(null);
    setHoveredOhlc(null);
    setSelectedRange(null);
    setRangeQuestion(null);
    setSelectedDay(null);
    setSelectedArticle(null);
    setLockedArticle(null);
    setSourceFilter('all');
    setSentimentFilter('all');
  }

  function handleAddTicker(symbol: string) {
    if (!activeTickers.includes(symbol)) {
      setActiveTickers((prev) => [...prev, symbol]);
      axios.post('/api/stocks', { symbol }).catch(console.error);
    }
  }

  const effectiveDate = lockedArticle?.date ?? hoveredDate;
  const isLocked = lockedArticle !== null;

  function renderRightPanel() {
    if (selectedRange && rangeQuestion) {
      return (
        <RangeAnalysisPanel
          symbol={selectedSymbol}
          startDate={selectedRange.startDate}
          endDate={selectedRange.endDate}
          question={rangeQuestion}
          onClear={() => { setSelectedRange(null); setRangeQuestion(null); }}
        />
      );
    }
    if (selectedRange && !rangeQuestion) {
      return (
        <RangeNewsPanel
          symbol={selectedSymbol}
          startDate={selectedRange.startDate}
          endDate={selectedRange.endDate}
          priceChange={selectedRange.priceChange}
          onClose={() => setSelectedRange(null)}
          onAskAI={handleRangeAsk}
        />
      );
    }
    if (selectedDay) {
      return (
        <SimilarDaysPanel
          symbol={selectedSymbol}
          date={selectedDay}
          onClose={() => setSelectedDay(null)}
        />
      );
    }
    return (
      <NewsPanel
        symbol={selectedSymbol}
        hoveredDate={effectiveDate}
        onFindSimilar={(_newsId: string) => { if (effectiveDate) handleDayClick(effectiveDate); }}
        highlightedNewsId={selectedArticle?.newsId || null}
        isLocked={isLocked}
        onUnlock={() => { setLockedArticle(null); setSelectedArticle(null); }}
        sourceFilter={sourceFilter}
        onSourceFilterChange={setSourceFilter}
        sentimentFilter={sentimentFilter}
        onSentimentFilterChange={setSentimentFilter}
      />
    );
  }

  return (
    <div className="app-wrapper">
      <AppNav activeView={activeView} onChangeView={(view) => {
        setActiveView(view);
        if (view === 'overall') setOverallEverActive(true);
        if (view === 'analysis') setAnalysisEverActive(true);
        if (view === 'adanos') setSentimentEverActive(true);
        if (view === 'social') setSocialEverActive(true);
        if (view === 'team') setTeamEverActive(true);
        if (view === 'automation') setAutomationEverActive(true);
      }} />

      {/* Detail view */}
      <div className="app" style={{ display: activeView === 'ticker' ? 'flex' : 'none' }}>
        <header className="app-header">
          <div className="header-left"></div>
          <StockSelector
            activeTickers={activeTickers}
            selectedSymbol={selectedSymbol}
            onSelect={handleSelectSymbol}
            onAdd={handleAddTicker}
          />
          {selectedRange ? (
            <div className="header-ohlc">
              <span className="ohlc-date">{selectedRange.startDate} ~ {selectedRange.endDate}</span>
              <span className="range-badge">Range Selected</span>
            </div>
          ) : hoveredOhlc ? (
            <div className="header-ohlc">
              <span className="ohlc-date">{hoveredOhlc.date}</span>
              <span className="ohlc-label">O</span><span className="ohlc-val">${hoveredOhlc.open.toFixed(2)}</span>
              <span className="ohlc-label">H</span><span className="ohlc-val">${hoveredOhlc.high.toFixed(2)}</span>
              <span className="ohlc-label">L</span><span className="ohlc-val">${hoveredOhlc.low.toFixed(2)}</span>
              <span className="ohlc-label">C</span><span className="ohlc-val">${hoveredOhlc.close.toFixed(2)}</span>
              <span className={`ohlc-change ${hoveredOhlc.change >= 0 ? 'up' : 'down'}`}>
                {hoveredOhlc.change >= 0 ? '+' : ''}{hoveredOhlc.change.toFixed(2)}%
              </span>
            </div>
          ) : null}
          {selectedSymbol && (
            <DatePickerPopup
              onSelectDayAnalysis={(date) => { if (date) handleDayClick(date); }}
              onSelectDayNews={(date) => {
                if (date) {
                  setSelectedDay(null);
                  setSelectedRange(null);
                  setRangeQuestion(null);
                  setHoveredDate(date);
                  setLockedArticle({ newsId: '', date });
                }
              }}
              onSelectRange={(start, end) => handleRangeSelect({ startDate: start, endDate: end })}
              selectedDay={selectedDay}
              selectedRange={selectedRange}
            />
          )}
          <div className="header-right"></div>
        </header>

        <main className="app-main">
          <div className="chart-area" ref={chartAreaRef}>
            {selectedSymbol ? (
              <>
                <CandlestickChart
                  symbol={selectedSymbol}
                  lockedNewsId={lockedArticle?.newsId ?? null}
                  sourceFilter={sourceFilter}
                  sentimentFilter={sentimentFilter}
                  onHover={handleHover}
                  onRangeSelect={handleRangeSelect}
                  onArticleSelect={handleArticleSelect}
                  onDayClick={handleDayClick}
                />
                {selectedRange && !rangeQuestion && selectedRange.popupX !== undefined && (
                  <RangeQueryPopup
                    range={selectedRange}
                    chartRect={chartRect}
                    onAsk={handleRangeAsk}
                    onClose={() => setSelectedRange(null)}
                  />
                )}
              </>
            ) : (
              <div className="chart-placeholder">Select a ticker to view the chart</div>
            )}
          </div>
          {selectedSymbol && (
            <div className="prediction-area">
              <PredictionPanel
                symbol={selectedSymbol}
                refDate={selectedDay || undefined}
              />
            </div>
          )}
          <div className="news-area">{renderRightPanel()}</div>
        </main>
      </div>

      {/* Overall view */}
      <div style={{ display: activeView === 'overall' ? 'flex' : 'none', flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
        <Suspense fallback={<div style={{ color: '#888', padding: 40 }}>Loading Overall...</div>}>
          {overallEverActive && <OverallApp />}
        </Suspense>
      </div>

      {/* Analysis view — always mounted once visited, hidden via display:none to preserve state */}
      <div style={{ display: activeView === 'analysis' ? 'flex' : 'none', flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
        <Suspense fallback={<div style={{ color: '#888', padding: 40 }}>Loading Analysis...</div>}>
          {analysisEverActive && <AnalysisApp />}
        </Suspense>
      </div>

      {/* Sentiment view */}
      <div style={{ display: activeView === 'adanos' ? 'block' : 'none', flex: 1, overflow: 'auto' }}>
        <Suspense fallback={<div style={{ color: '#888', padding: 40 }}>Loading Sentiment...</div>}>
          {sentimentEverActive && <SentimentApp />}
        </Suspense>
      </div>

      {/* Social view */}
      <div style={{ display: activeView === 'social' ? 'flex' : 'none', flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
        <Suspense fallback={<div style={{ color: '#888', padding: 40 }}>Loading Social...</div>}>
          {socialEverActive && <SocialApp initTicker={socialInitTicker} />}
        </Suspense>
      </div>

      {/* Team view */}
      <div style={{ display: activeView === 'team' ? 'flex' : 'none', flex: 1, minWidth: 0, height: '100%', overflow: 'auto' }}>
        <Suspense fallback={<div style={{ color: '#888', padding: 40 }}>Loading Team...</div>}>
          {teamEverActive && <TeamApp />}
        </Suspense>
      </div>

      {/* Automation view */}
      <div style={{ display: activeView === 'automation' ? 'flex' : 'none', flex: 1, minWidth: 0, height: '100%', overflow: 'auto' }}>
        <Suspense fallback={<div style={{ color: '#888', padding: 40 }}>Loading Ops...</div>}>
          {automationEverActive && <AutomationApp />}
        </Suspense>
      </div>

      <a
        className="global-signature"
        href="https://ivyyy0601.github.io/"
        target="_blank"
        rel="noreferrer"
      >
        ivyyy0601
      </a>
    </div>
  );
}

export default App;
