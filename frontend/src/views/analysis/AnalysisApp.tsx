import type React from 'react';
import { MemoryRouter as Router, Route, Routes } from 'react-router-dom';
import { ThemeProvider, Shell } from './components/common';
import { HomePage } from './pages';
import './analysis-base.css';
import './analysis.css';

const AnalysisApp: React.FC = () => {
  return (
    <ThemeProvider>
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Router>
          <Routes>
            <Route element={<Shell />}>
              <Route path="/" element={<HomePage />} />
            </Route>
          </Routes>
        </Router>
      </div>
    </ThemeProvider>
  );
};

export default AnalysisApp;
