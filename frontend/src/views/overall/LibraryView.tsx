import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

interface Report {
  id: string;
  symbol: string;
  company?: string;
  report_type: 'deep' | 'quick';
  analyst?: string;
  sources?: string;
  created_at: string;
}

interface ReportDetail extends Report {
  content: string;
}

interface Note {
  id: number;
  symbol: string;
  report_id?: string;
  analyst?: string;
  content: string;
  created_at: string;
}

function renderMarkdown(text: string) {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    if (line.startsWith('### ')) return <h3 key={i} className="ts-ai-h3">{line.slice(4)}</h3>;
    if (line.startsWith('## '))  return <h2 key={i} className="ts-ai-h2">{line.slice(3)}</h2>;
    if (line.startsWith('# '))   return <h1 key={i} className="ts-ai-h1">{line.slice(2)}</h1>;
    if (line.startsWith('- ') || line.startsWith('• ')) {
      const parts = line.slice(2).split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
        p.startsWith('**') && p.endsWith('**') ? <strong key={j}>{p.slice(2,-2)}</strong> : p
      );
      return <li key={i} className="ts-ai-li">{parts}</li>;
    }
    if (line.trim() === '') return <div key={i} style={{ height: 8 }} />;
    const parts = line.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={j}>{p.slice(2,-2)}</strong> : p
    );
    return <p key={i} className="ts-ai-p">{parts}</p>;
  });
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)   return 'Just now';
  if (m < 60)  return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30)  return `${d}d ago`;
  return new Date(iso).toLocaleDateString('en-US');
}

interface Props {
  onSelectStock: (sym: string) => void;
  analystName: string;
}

export default function LibraryView({ onSelectStock, analystName }: Props) {
  const [reports,     setReports]     = useState<Report[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [filterSym,   setFilterSym]   = useState('');

  // Email modal state
  const [showEmail,    setShowEmail]    = useState(false);
  const [emailTo,      setEmailTo]      = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody,    setEmailBody]    = useState('');
  const [emailRecipientHint, setEmailRecipientHint] = useState('');
  const [draftLoading, setDraftLoading] = useState(false);
  const [sendLoading,  setSendLoading]  = useState(false);
  const [sendResult,   setSendResult]   = useState<'ok' | 'error' | 'copied' | null>(null);
  const emailToRef = useRef<HTMLInputElement>(null);
  const [filterType,  setFilterType]  = useState('');
  const [selected,    setSelected]    = useState<ReportDetail | null>(null);
  const [notes,       setNotes]       = useState<Note[]>([]);
  const [noteText,    setNoteText]    = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [deleting,    setDeleting]    = useState<string | null>(null);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (filterSym)  params.symbol      = filterSym.toUpperCase();
      if (filterType) params.report_type = filterType;
      const res = await axios.get('/api/library/reports', { params });
      setReports(Array.isArray(res.data) ? res.data : []);
    } finally {
      setLoading(false);
    }
  }, [filterSym, filterType]);

  useEffect(() => { loadReports(); }, [loadReports]);

  async function openReport(r: Report) {
    const res = await axios.get(`/api/library/reports/${r.id}`);
    setSelected(res.data);
    const notesRes = await axios.get('/api/library/notes', { params: { report_id: r.id } });
    setNotes(Array.isArray(notesRes.data) ? notesRes.data : []);
  }

  async function addNote() {
    if (!noteText.trim() || !selected) return;
    setNoteLoading(true);
    try {
      const res = await axios.post('/api/library/notes', {
        symbol: selected.symbol,
        report_id: selected.id,
        analyst: analystName || undefined,
        content: noteText.trim(),
      });
      setNotes(prev => [{ ...res.data, symbol: selected.symbol, content: noteText.trim(), analyst: analystName, report_id: selected.id }, ...prev]);
      setNoteText('');
    } finally {
      setNoteLoading(false);
    }
  }

  async function deleteNote(id: number) {
    await axios.delete(`/api/library/notes/${id}`);
    setNotes(prev => prev.filter(n => n.id !== id));
  }

  async function deleteReport(id: string) {
    setDeleting(id);
    try {
      await axios.delete(`/api/library/reports/${id}`);
      setReports(prev => prev.filter(r => r.id !== id));
      if (selected?.id === id) setSelected(null);
    } finally {
      setDeleting(null);
    }
  }

  function openEmailModal() {
    if (!selected) return;
    const rtype = selected.report_type === 'deep' ? 'Deep Analysis' : 'Quick Analysis';
    setEmailSubject(`[IvyTrader] ${selected.symbol} ${rtype} — ${selected.created_at.slice(0,10)}`);
    setEmailBody('');
    setEmailTo('');
    setEmailRecipientHint('');
    setSendResult(null);
    setShowEmail(true);
    setTimeout(() => emailToRef.current?.focus(), 100);
  }

  async function draftBody() {
    if (!selected) return;
    setDraftLoading(true);
    try {
      const res = await axios.post('/api/library/draft-email', {
        report_id: selected.id,
        recipient: emailRecipientHint,
      });
      setEmailBody(res.data.body);
    } finally {
      setDraftLoading(false);
    }
  }

  function stripMarkdown(md: string): string {
    return md
      .replace(/^#{1,3}\s+/gm, '')          // remove # ## ###
      .replace(/\*\*([^*]+)\*\*/g, '$1')    // remove **bold**
      .replace(/\*([^*]+)\*/g, '$1')        // remove *italic*
      .replace(/^[-•]\s+/gm, '• ')          // normalize bullets
      .replace(/^---+$/gm, '─────────────') // horizontal rules
      .trim();
  }

  function sendEmail() {
    if (!selected || !emailTo.trim()) return;
    // Keep body short — Gmail rejects URLs over ~2000 chars
    const url = 'https://mail.google.com/mail/?view=cm&fs=1'
      + '&to='   + encodeURIComponent(emailTo)
      + '&su='   + encodeURIComponent(emailSubject)
      + '&body=' + encodeURIComponent(emailBody);
    window.open(url, '_blank');
    setSendResult('ok');
  }

  function sendMailto() {
    if (!selected || !emailTo.trim()) return;
    const uri = `mailto:${encodeURIComponent(emailTo)}?subject=${encodeURIComponent(emailSubject)}&body=${encodeURIComponent(emailBody)}`;
    window.location.href = uri;
  }

  async function copyReport() {
    if (!selected) return;
    await navigator.clipboard.writeText(stripMarkdown(selected.content));
    setSendResult('copied');
  }

  function downloadReport() {
    if (!selected) return;
    const text = `${selected.symbol} — ${selected.report_type === 'deep' ? 'Deep Analysis' : 'Quick Analysis'}\n`
      + `${new Date(selected.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}\n`
      + (selected.analyst ? `Analyst: ${selected.analyst}\n` : '')
      + '\n' + '─'.repeat(60) + '\n\n'
      + stripMarkdown(selected.content);
    const blob = new Blob([text], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `${selected.symbol}_${selected.created_at.slice(0,10)}_report.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const typeLabel = (t: string) => t === 'deep' ? '🔬 Deep' : '⚡ Quick';
  const typeColor = (t: string) => t === 'deep' ? '#6c8fff' : '#f59e0b';

  return (
    <>
    <div className="library-layout">

      {/* ── Left panel: list ───────────────────────────── */}
      <div className="library-sidebar">
        <div className="library-header">
          <div className="library-title">📚 Research Library</div>
          <div className="library-count">{reports.length} reports</div>
        </div>

        {/* Filters */}
        <div className="library-filters">
          <input
            className="library-filter-input"
            placeholder="Search by ticker..."
            value={filterSym}
            onChange={e => setFilterSym(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadReports()}
          />
          <select className="library-filter-select" value={filterType} onChange={e => setFilterType(e.target.value)}>
            <option value="">All types</option>
            <option value="deep">🔬 Deep Analysis</option>
            <option value="quick">⚡ Quick Analysis</option>
          </select>
          <button className="library-filter-btn" onClick={loadReports}>Filter</button>
        </div>

        {/* Report list */}
        <div className="library-list">
          {loading && <div className="library-empty">Loading...</div>}
          {!loading && reports.length === 0 && (
            <div className="library-empty">
              No reports yet.<br />
              <span style={{ fontSize: 11, color: '#444', marginTop: 4, display: 'block' }}>
                Generate a Deep or Quick Analysis and save it.
              </span>
            </div>
          )}
          {reports.map(r => (
            <div
              key={r.id}
              className={`library-item ${selected?.id === r.id ? 'active' : ''}`}
              onClick={() => openReport(r)}
            >
              <div className="library-item-top">
                <span className="library-item-sym" onClick={e => { e.stopPropagation(); onSelectStock(r.symbol); }}>
                  {r.symbol}
                </span>
                <span className="library-item-type" style={{ color: typeColor(r.report_type) }}>
                  {typeLabel(r.report_type)}
                </span>
                <button className="library-item-del"
                  onClick={e => { e.stopPropagation(); deleteReport(r.id); }}
                  disabled={deleting === r.id}
                  title="Delete report"
                >✕</button>
              </div>
              <div className="library-item-company">{r.company || r.symbol}</div>
              <div className="library-item-meta">
                {r.analyst && <span>{r.analyst} · </span>}
                {timeAgo(r.created_at)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel: detail ────────────────────────── */}
      <div className="library-detail">
        {!selected ? (
          <div className="library-empty-detail">
            <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
            <div style={{ color: '#555' }}>Select a report from the left to view</div>
          </div>
        ) : (
          <>
            {/* Report header */}
            <div className="library-detail-header">
              <div>
                <div className="library-detail-title">
                  <span
                    className="library-detail-sym"
                    onClick={() => onSelectStock(selected.symbol)}
                    title="Go to stock"
                  >
                    {selected.symbol}
                  </span>
                  {selected.company && <span style={{ color: '#888', fontWeight: 400, marginLeft: 8 }}>{selected.company}</span>}
                </div>
                <div className="library-detail-meta">
                  <span style={{ color: typeColor(selected.report_type) }}>{typeLabel(selected.report_type)}</span>
                  {selected.analyst && <span> · {selected.analyst}</span>}
                  <span> · {new Date(selected.created_at).toLocaleString('en-US')}</span>
                  {selected.sources && (
                    <span style={{ marginLeft: 6, color: '#555' }}>
                      · {(() => { try { const s = JSON.parse(selected.sources); return Array.isArray(s) ? s.join(', ') : selected.sources; } catch { return selected.sources; } })()}
                    </span>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
              <button className="library-email-btn" onClick={openEmailModal}>
                📧 Send
              </button>
              <button className="library-detail-del"
                onClick={() => deleteReport(selected.id)}
                disabled={deleting === selected.id}
              >
                🗑 Delete
              </button>
              </div>
            </div>

            {/* Report content */}
            <div className="library-detail-content">
              <div className="ts-ai-content">
                {renderMarkdown(selected.content)}
              </div>
            </div>

            {/* Notes section */}
            <div className="library-notes">
              <div className="library-notes-title">💬 Notes</div>

              <div className="library-note-input-row">
                <textarea
                  className="library-note-input"
                  placeholder="Add notes, follow-ups..."
                  value={noteText}
                  onChange={e => setNoteText(e.target.value)}
                  rows={2}
                />
                <button className="library-note-btn" onClick={addNote} disabled={noteLoading || !noteText.trim()}>
                  {noteLoading ? '...' : 'Add'}
                </button>
              </div>

              <div className="library-notes-list">
                {notes.length === 0 && <div style={{ color: '#444', fontSize: 12 }}>No notes yet</div>}
                {notes.map(n => (
                  <div key={n.id} className="library-note-item">
                    <div className="library-note-meta">
                      {n.analyst && <span className="library-note-analyst">{n.analyst}</span>}
                      <span className="library-note-time">{timeAgo(n.created_at)}</span>
                      <button className="library-note-del" onClick={() => deleteNote(n.id)}>✕</button>
                    </div>
                    <div className="library-note-text">{n.content}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>

    {/* ── Email Modal ────────────────────────────────── */}
    {showEmail && selected && (
      <div className="email-overlay" onClick={e => { if (e.target === e.currentTarget) setShowEmail(false); }}>
        <div className="email-modal">
          <div className="email-modal-header">
            <div className="email-modal-title">📧 Send Research Report</div>
            <button className="ic-close-btn" onClick={() => setShowEmail(false)}>✕</button>
          </div>

          <div className="email-modal-body">
            {/* Report info */}
            <div className="email-report-badge">
              <span style={{ color: typeColor(selected.report_type) }}>{typeLabel(selected.report_type)}</span>
              <span style={{ color: '#888', marginLeft: 8 }}>{selected.symbol}</span>
              {selected.company && <span style={{ color: '#555', marginLeft: 6 }}>· {selected.company}</span>}
            </div>

            {/* To */}
            <div className="email-field">
              <label className="email-label">To</label>
              <input
                ref={emailToRef}
                className="email-input"
                placeholder="email@example.com, separate multiple with commas"
                value={emailTo}
                onChange={e => setEmailTo(e.target.value)}
              />
            </div>

            {/* Subject */}
            <div className="email-field">
              <label className="email-label">Subject</label>
              <input
                className="email-input"
                value={emailSubject}
                onChange={e => setEmailSubject(e.target.value)}
              />
            </div>

            {/* AI draft */}
            <div className="email-field">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <label className="email-label" style={{ marginBottom: 0 }}>Email Body</label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    className="email-hint-input"
                    placeholder="Recipient hint (e.g. Investment Committee)"
                    value={emailRecipientHint}
                    onChange={e => setEmailRecipientHint(e.target.value)}
                  />
                  <button className="email-draft-btn" onClick={draftBody} disabled={draftLoading}>
                    {draftLoading ? 'Drafting...' : '✨ AI Draft'}
                  </button>
                </div>
              </div>
              <textarea
                className="email-body-input"
                placeholder='Write the email body here, or click "AI Draft" to auto-generate...'
                value={emailBody}
                onChange={e => setEmailBody(e.target.value)}
                rows={8}
              />
              <div style={{ fontSize: 10, color: '#444', marginTop: 4 }}>
                📎 Full report content will be included below
              </div>
            </div>

            {/* Attachment section */}
            <div className="email-attach-section">
              <div className="email-attach-label">📎 Attach Report</div>
              <div style={{ fontSize: 11, color: '#666', marginBottom: 8 }}>
                Browsers can't attach files to Gmail directly. Download the report first, then attach it manually in Gmail.
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button className="email-download-btn" onClick={downloadReport}>
                  ⬇ Download Report (.txt)
                </button>
                <button className="email-copy-btn" style={{ flex: 1 }} onClick={copyReport}>
                  📋 Copy to Clipboard
                </button>
              </div>
              {sendResult === 'copied' && <div style={{ color: '#00e676', fontSize: 11, marginTop: 4 }}>✓ Copied!</div>}
            </div>

            {sendResult === 'ok' && (
              <div className="email-result ok">✓ Opened Gmail compose in new tab</div>
            )}
          </div>

          <div className="email-modal-footer">
            <button className="email-cancel-btn" onClick={() => setShowEmail(false)}>Cancel</button>
            <button
              className="email-send-btn secondary"
              onClick={sendMailto}
              disabled={!emailTo.trim()}
              title="Send via default mail app"
            >
              📮 Mail App
            </button>
            <button
              className="email-send-btn"
              onClick={sendEmail}
              disabled={!emailTo.trim() || !emailBody.trim()}
            >
              Send via Gmail →
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
