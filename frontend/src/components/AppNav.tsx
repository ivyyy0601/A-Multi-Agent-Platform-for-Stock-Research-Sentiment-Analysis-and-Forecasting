import { useEffect, useState } from 'react';
import axios from 'axios';

interface AppNavProps {
  activeView: 'ticker' | 'analysis' | 'adanos' | 'social' | 'team' | 'automation' | 'overall';
  onChangeView: (view: 'ticker' | 'analysis' | 'adanos' | 'social' | 'team' | 'automation' | 'overall') => void;
}

export default function AppNav({ activeView, onChangeView }: AppNavProps) {
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await axios.get('/api/automation/status?limit=6');
        if (cancelled) return;
        const current = response.data?.current || {};
        setRunning(Object.keys(current).length > 0);
      } catch {
        if (!cancelled) setRunning(false);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <nav className="app-nav">
      <a
        className="app-nav-logo"
        href="https://ivyyy0601.github.io/"
        target="_blank"
        rel="noreferrer"
      >
        ivy
      </a>
      <button
        className={`app-nav-btn ${activeView === 'overall' ? 'active' : ''}`}
        onClick={() => onChangeView('overall')}
        title="Market Overview"
      >
        <span className="nav-icon">🌐</span>
        <span className="nav-label">Overall</span>
      </button>
      <button
        className={`app-nav-btn ${activeView === 'analysis' ? 'active' : ''}`}
        onClick={() => onChangeView('analysis')}
        title="Stock Analysis"
      >
        <span className="nav-icon">📊</span>
        <span className="nav-label">Analysis</span>
      </button>
      <button
        className={`app-nav-btn ${activeView === 'adanos' ? 'active' : ''}`}
        onClick={() => onChangeView('adanos')}
        title="Sentiment"
      >
        <span className="nav-icon">📈</span>
        <span className="nav-label">Sentiment</span>
      </button>
      <button
        className={`app-nav-btn ${activeView === 'team' ? 'active' : ''}`}
        onClick={() => onChangeView('team')}
        title="Team"
      >
        <span className="nav-icon">🪴</span>
        <span className="nav-label">Team</span>
      </button>
      <button
        className={`app-nav-btn ${activeView === 'ticker' ? 'active' : ''}`}
        onClick={() => onChangeView('ticker')}
        title="Detail"
      >
        <span className="nav-icon">📰</span>
        <span className="nav-label">Detail</span>
      </button>
      <button
        className={`app-nav-btn ${activeView === 'automation' ? 'active' : ''}`}
        onClick={() => onChangeView('automation')}
        title="Automation"
      >
        <span className="nav-icon">OP</span>
        <span className="nav-label">Ops</span>
        {running && <span className="nav-status-dot" />}
      </button>
    </nav>
  );
}
