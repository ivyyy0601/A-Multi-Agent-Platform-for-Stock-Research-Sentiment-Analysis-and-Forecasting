import { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  PointElement, LineElement,
  BarElement, ArcElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js';

ChartJS.register(
  CategoryScale, LinearScale,
  PointElement, LineElement,
  BarElement, ArcElement,
  Title, Tooltip, Legend, Filler
);
import TrendingView from './components/TrendingView';
import SectorView from './components/SectorView';
import CountryView from './components/CountryView';
import DeepDive from './components/DeepDive';
import CompareView from './components/CompareView';

const TABS = [
  { id: 'trending',  label: '🔥 Trending'  },
  { id: 'sectors',   label: '🏭 Sectors'   },
  { id: 'countries', label: '🌍 Countries'  },
  { id: 'deepdive',  label: '🔍 Deep Dive' },
  { id: 'compare',   label: '⚖️ Compare'   },
];

const DAYS = [1, 3, 7, 14, 30, 90];

export default function App() {
  const [tab, setTab]           = useState('trending');
  const [days, setDays]         = useState(7);
  const [deepTicker, setDeepTicker] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  useEffect(() => { setLastUpdated(new Date()); }, [days]);

  useEffect(() => {
    const handler = (e) => {
      const ticker = e.detail?.ticker;
      if (ticker) { setDeepTicker(ticker); setTab('deepdive'); }
    };
    window.addEventListener('navigate-adanos', handler);
    return () => window.removeEventListener('navigate-adanos', handler);
  }, []);

  function handleSelectTicker(ticker) {
    setDeepTicker(ticker);
    setTab('deepdive');
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0d0f17' }}>
      {/* ── Sticky header ── */}
      <div style={{ position: 'sticky', top: 0, zIndex: 50, background: '#0d0f17', borderBottom: '1px solid #1a1d27' }}>
        <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '10px 24px', display: 'flex', alignItems: 'center', gap: '20px' }}>
          {/* Logo */}
          <div style={{ flexShrink: 0 }}>
            <span style={{ fontSize: '17px', fontWeight: '900', color: '#f1f5f9', letterSpacing: '-0.03em' }}>Market</span>
            <span style={{ fontSize: '17px', fontWeight: '900', color: '#6366f1', letterSpacing: '-0.03em' }}>Pulse</span>
            <div style={{ fontSize: '9px', color: '#374151', letterSpacing: '0.06em', textTransform: 'uppercase', marginTop: '-1px' }}>
              Reddit · X · News
            </div>
          </div>

          {/* Nav tabs */}
          <nav style={{ display: 'flex', gap: '3px', flex: 1 }}>
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                  fontSize: '13px', fontWeight: '600',
                  background: tab === t.id ? '#6366f1' : 'transparent',
                  color: tab === t.id ? '#ffffff' : '#4b5563',
                  transition: 'all 0.15s',
                }}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {/* Last updated */}
          {lastUpdated && (
            <div style={{ flexShrink: 0, fontSize: '11px', color: '#374151', textAlign: 'right' }}>
              <div style={{ color: '#4b5563' }}>Last updated</div>
              <div style={{ color: '#6366f1', fontWeight: '700', fontVariantNumeric: 'tabular-nums' }}>
                {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          )}

          {/* Days selector */}
          <div style={{ display: 'flex', gap: '3px', flexShrink: 0 }}>
            <span style={{ fontSize: '11px', color: '#374151', alignSelf: 'center', marginRight: '4px' }}>Window:</span>
            {DAYS.map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                style={{
                  padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', fontSize: '12px', fontWeight: '700',
                  border: `1px solid ${days === d ? '#6366f1' : '#1e2030'}`,
                  background: days === d ? '#1e1b4b' : 'transparent',
                  color: days === d ? '#a5b4fc' : '#4b5563',
                  transition: 'all 0.15s',
                }}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>

      </div>

      {/* ── Main content ── */}
      <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '20px 24px 40px' }}>
        {tab === 'trending'  && <TrendingView days={days} onSelectTicker={handleSelectTicker} />}
        {tab === 'sectors'   && <SectorView   days={days} />}
        {tab === 'countries' && <CountryView  days={days} />}
        {tab === 'deepdive'  && <DeepDive initialTicker={deepTicker} days={days} />}
        {tab === 'compare'   && <CompareView  days={days} />}
      </div>
    </div>
  );
}
