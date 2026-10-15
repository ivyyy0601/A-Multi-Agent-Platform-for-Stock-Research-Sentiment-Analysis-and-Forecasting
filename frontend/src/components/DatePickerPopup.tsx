import { useState, useRef, useEffect } from 'react';

interface Props {
  onSelectDayAnalysis: (date: string) => void;
  onSelectDayNews: (date: string) => void;
  onSelectRange: (start: string, end: string) => void;
  selectedDay: string | null;
  selectedRange: { startDate: string; endDate: string } | null;
}

type Mode = 'analysis' | 'news' | 'range';

export default function DatePickerPopup({
  onSelectDayAnalysis,
  onSelectDayNews,
  onSelectRange,
  selectedDay,
  selectedRange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>('analysis');
  const [dayValue, setDayValue] = useState('');
  const [startValue, setStartValue] = useState('');
  const [endValue, setEndValue] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  function handleApply() {
    if (mode === 'analysis' && dayValue) {
      onSelectDayAnalysis(dayValue);
      setOpen(false);
    } else if (mode === 'news' && dayValue) {
      onSelectDayNews(dayValue);
      setOpen(false);
    } else if (mode === 'range' && startValue && endValue && startValue <= endValue) {
      onSelectRange(startValue, endValue);
      setOpen(false);
    }
  }

  function handleClear() {
    setDayValue('');
    setStartValue('');
    setEndValue('');
    onSelectDayAnalysis('');
    setOpen(false);
  }

  function getLabel() {
    if (selectedRange) return `${selectedRange.startDate} ~ ${selectedRange.endDate}`;
    if (selectedDay) return selectedDay;
    return 'Select Date';
  }

  const hasSelection = selectedDay || selectedRange;

  return (
    <div className="datepicker-wrap" ref={ref}>
      <button
        className={`datepicker-btn ${hasSelection ? 'datepicker-btn-active' : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        📅 {getLabel()}
      </button>

      {open && (
        <div className="datepicker-popup">
          {/* Mode toggle */}
          <div className="datepicker-mode-row">
            <button
              className={`datepicker-mode-btn ${mode === 'analysis' ? 'active' : ''}`}
              onClick={() => setMode('analysis')}
            >📊 Day Analysis</button>
            <button
              className={`datepicker-mode-btn ${mode === 'news' ? 'active' : ''}`}
              onClick={() => setMode('news')}
            >📰 Day News</button>
            <button
              className={`datepicker-mode-btn ${mode === 'range' ? 'active' : ''}`}
              onClick={() => setMode('range')}
            >📅 Range News</button>
          </div>

          {/* Inputs */}
          {mode === 'range' ? (
            <div className="datepicker-inputs">
              <label className="datepicker-label">Start</label>
              <input
                type="date"
                className="datepicker-input"
                value={startValue}
                onChange={(e) => setStartValue(e.target.value)}
              />
              <label className="datepicker-label">End</label>
              <input
                type="date"
                className="datepicker-input"
                value={endValue}
                onChange={(e) => setEndValue(e.target.value)}
              />
            </div>
          ) : (
            <div className="datepicker-inputs">
              <label className="datepicker-label">
                {mode === 'analysis' ? 'Select day for Similar Days analysis' : 'Select day to view news'}
              </label>
              <input
                type="date"
                className="datepicker-input"
                value={dayValue}
                onChange={(e) => setDayValue(e.target.value)}
              />
            </div>
          )}

          {/* Actions */}
          <div className="datepicker-actions">
            {hasSelection && (
              <button className="datepicker-clear-btn" onClick={handleClear}>Clear</button>
            )}
            <button className="datepicker-apply-btn" onClick={handleApply}>Apply</button>
          </div>
        </div>
      )}
    </div>
  );
}
