import { useState, useEffect } from 'react';

interface Props {
  symbol: string;
  profile: any;
  onClose: () => void;
  analystName?: string;
}

type Role = 'market' | 'social' | 'news' | 'fundamentals' | 'ivy';

interface WorkflowStep {
  key: string;
  label: string;
  icon: string;
  status: 'selected' | 'active' | 'completed' | 'skipped' | 'failed';
}

interface TaskInfo {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string | null;
  current_step?: string | null;
  workflow: WorkflowStep[];
  result?: {
    markdown_report: string;
    investment_plan?: string | null;
    final_decision: string;
    reports: Record<string, string>;
  } | null;
  error?: string | null;
}

const ROLE_META: { key: Role; icon: string; label: string; desc: string }[] = [
  { key: 'market',       icon: '📈', label: 'Market',       desc: 'Technical · Price Action · Momentum' },
  { key: 'social',       icon: '🌐', label: 'Social',       desc: 'Social Sentiment · Reddit · X' },
  { key: 'news',         icon: '📰', label: 'News',         desc: 'News Analysis · Event-Driven' },
  { key: 'fundamentals', icon: '📚', label: 'Fundamentals', desc: 'Fundamentals · Financials · Valuation' },
  { key: 'ivy',          icon: '🪴', label: 'Ivy',          desc: 'Local Integrated Analysis' },
];

const SYNTHESIS_STEPS = [
  { key: 'bull_researcher',   icon: '🐂', label: 'Bull Researcher' },
  { key: 'bear_researcher',   icon: '🐻', label: 'Bear Researcher' },
  { key: 'research_manager',  icon: '🧭', label: 'Research Manager' },
  { key: 'trader',            icon: '💹', label: 'Trader' },
  { key: 'portfolio_manager', icon: '🛡️', label: 'Portfolio Manager' },
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// Simple markdown → JSX (reuse pattern from rest of codebase)
function renderMd(text: string): React.ReactNode {
  const lines = text.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('### ')) { nodes.push(<div key={i} className="ic-h3">{line.slice(4)}</div>); i++; continue; }
    if (line.startsWith('## '))  { nodes.push(<div key={i} className="ic-h2">{line.slice(3)}</div>); i++; continue; }
    if (line.startsWith('# '))   { nodes.push(<div key={i} className="ic-h1">{line.slice(2)}</div>); i++; continue; }
    if (/^---+$/.test(line.trim())) { nodes.push(<hr key={i} className="ic-hr" />); i++; continue; }
    if (line.startsWith('- ') || line.startsWith('• ')) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('• '))) {
        const parts = lines[i].slice(2).split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
          p.startsWith('**') && p.endsWith('**') ? <strong key={j}>{p.slice(2,-2)}</strong> : p
        );
        items.push(<li key={i}>{parts}</li>);
        i++;
      }
      nodes.push(<ul key={`ul${i}`} className="ic-ul">{items}</ul>);
      continue;
    }
    if (line.trim() === '') { nodes.push(<div key={i} className="ic-gap" />); i++; continue; }
    const parts = line.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={j}>{p.slice(2,-2)}</strong> : p
    );
    nodes.push(<p key={i} className="ic-p">{parts}</p>);
    i++;
  }
  return <>{nodes}</>;
}

export default function ICMemo({ symbol, profile, onClose, analystName }: Props) {
  const [phase,     setPhase]     = useState<'configure' | 'running' | 'done' | 'error'>('configure');
  const [roles,     setRoles]     = useState<Role[]>(['market', 'social', 'news', 'fundamentals']);
  const [taskInfo,  setTaskInfo]  = useState<TaskInfo | null>(null);
  const [error,     setError]     = useState('');
  const [expanded,  setExpanded]  = useState<Record<string, boolean>>({});
  const [saved,     setSaved]     = useState(false);
  const [saving,    setSaving]    = useState(false);

  function toggleRole(r: Role) {
    setRoles(prev => prev.includes(r) ? prev.filter(x => x !== r) : [...prev, r]);
  }

  // SSE polling once we have a task_id
  useEffect(() => {
    const taskId = taskInfo?.task_id;
    if (!taskId || phase !== 'running') return;

    const source = new EventSource('/api/v1/team/tasks/stream');

    function handle(ev: MessageEvent<string>) {
      const payload = JSON.parse(ev.data) as TaskInfo & { task_id: string };
      if (payload.task_id !== taskId) return;
      setTaskInfo(payload);
      if (payload.status === 'completed') {
        setPhase('done');
        source.close();
      }
      if (payload.status === 'failed') {
        setError(payload.error || 'Workflow failed');
        setPhase('error');
        source.close();
      }
    }

    ['team_task_created','team_task_started','team_task_updated','team_task_completed','team_task_failed']
      .forEach(evt => source.addEventListener(evt, handle as EventListener));
    source.onerror = () => source.close();
    return () => source.close();
  }, [taskInfo?.task_id, phase]);

  async function run() {
    if (roles.length === 0) return;
    setPhase('running');
    setError('');
    setTaskInfo(null);

    const ivySelected = roles.includes('ivy');
    const tradeDate = todayISO();

    try {
      const res = await fetch('/api/v1/team/run-async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: symbol,
          trade_date: tradeDate,
          llm_provider: 'anthropic',
          deep_model: 'claude-sonnet-4-6',
          quick_model: 'claude-haiku-4-5',
          roles,
          max_debate_rounds: 1,
          max_risk_discuss_rounds: 1,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail?.message || data?.message || 'Failed to start');

      setTaskInfo({
        task_id: data.task_id,
        status: data.status,
        progress: 0,
        workflow: [],
        message: data.message,
      });
    } catch (e: any) {
      setError(e.message);
      setPhase('error');
    }
  }

  // Build unified workflow view
  const workflowSteps: { key: string; icon: string; label: string; status: WorkflowStep['status'] }[] = [
    ...ROLE_META.filter(r => roles.includes(r.key)).map(r => ({
      key: r.key, icon: r.icon, label: r.label,
      status: (taskInfo?.workflow?.find(s => s.key === r.key)?.status ?? 'selected') as WorkflowStep['status'],
    })),
    ...SYNTHESIS_STEPS.map(s => ({
      key: s.key, icon: s.icon, label: s.label,
      status: (taskInfo?.workflow?.find(w => w.key === s.key)?.status ?? 'selected') as WorkflowStep['status'],
    })),
  ];

  const statusColor: Record<WorkflowStep['status'], string> = {
    selected: '#333', active: '#6c8fff', completed: '#00e676', skipped: '#444', failed: '#ff4d4d',
  };
  const statusLabel: Record<WorkflowStep['status'], string> = {
    selected: 'Standby', active: 'Running', completed: 'Done', skipped: 'Skipped', failed: 'Failed',
  };

  async function saveReport() {
    if (!result || saving || saved) return;
    setSaving(true);
    try {
      await fetch('/api/library/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          company: profile?.name ?? profile?.company_name ?? null,
          report_type: 'deep',
          analyst: analystName || null,
          content: result.markdown_report || result.final_decision,
          sources: JSON.stringify(roles),
        }),
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  const result = taskInfo?.result;

  return (
    <div className="ic-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ic-modal" style={{ width: 'min(960px, 96vw)' }}>

        {/* Header */}
        <div className="ic-modal-header">
          <div>
            <div className="ic-modal-title">🔬 Deep Analysis · Multi-Agent Desk</div>
            <div className="ic-modal-sub">{symbol} · {profile?.name ?? ''}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {(phase === 'done' || phase === 'error') && (
              <button className="ic-regen-btn" onClick={() => { setPhase('configure'); setTaskInfo(null); }}>
                ⚙ Reconfigure
              </button>
            )}
            <button className="ic-close-btn" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="ic-modal-body">

          {/* ── Configure ─────────────────────────────────── */}
          {phase === 'configure' && (
            <div className="ic-configure">
              <div className="ic-configure-title">Select Input Analysts</div>
              <div className="ic-configure-sub">
                Selected analysts handle data collection and initial analysis. Then 🐂 Bull / 🐻 Bear → 🧭 Research Manager → 💹 Trader → 🛡️ Portfolio Manager automatically generate the final IC Memo.
              </div>

              <div className="ic-select-grid">
                {ROLE_META.map(r => {
                  const on = roles.includes(r.key);
                  const locked = r.key === 'ivy'; // ivy locks date to today
                  return (
                    <div
                      key={r.key}
                      className={`ic-select-card ${on ? 'selected' : ''}`}
                      style={on ? { borderColor: '#6c8fff66', background: '#6c8fff0d' } : {}}
                      onClick={() => toggleRole(r.key)}
                    >
                      <div className="ic-select-card-top">
                        <span className="ic-select-icon">{r.icon}</span>
                        <div className="ic-select-check" style={on ? { background: '#6c8fff', borderColor: '#6c8fff' } : {}}>
                          {on && '✓'}
                        </div>
                      </div>
                      <div className="ic-select-name" style={on ? { color: '#6c8fff' } : {}}>{r.label}</div>
                      <div className="ic-select-desc">{r.desc}</div>
                      {locked && <div style={{ fontSize: 10, color: '#555', marginTop: 4 }}>Date locked to today</div>}
                    </div>
                  );
                })}
              </div>

              {/* Synthesis pipeline preview */}
              <div className="ic-pipeline-preview">
                <div className="ic-pipeline-label">Auto Synthesis Pipeline</div>
                <div className="ic-pipeline-steps">
                  {SYNTHESIS_STEPS.map((s, i) => (
                    <div key={s.key} className="ic-pipeline-step">
                      <span>{s.icon}</span>
                      <span>{s.label}</span>
                      {i < SYNTHESIS_STEPS.length - 1 && <span className="ic-pipeline-arrow">→</span>}
                    </div>
                  ))}
                </div>
              </div>

              <div className="ic-configure-footer">
                <span className="ic-configure-count">
                  {roles.length} analyst(s) selected
                  {roles.length === 0 && <span style={{ color: '#ff4d4d', marginLeft: 8 }}>Select at least one</span>}
                </span>
                <button className="ic-generate-btn" disabled={roles.length === 0} onClick={run}>
                  🚀 Launch Multi-Agent Desk →
                </button>
              </div>
            </div>
          )}

          {/* ── Running ───────────────────────────────────── */}
          {phase === 'running' && (
            <div className="ic-agents-panel">
              <div className="ic-agents-label">
                {taskInfo?.current_step
                  ? `🔄 ${taskInfo.current_step}`
                  : taskInfo?.message ?? 'Starting...'}
                {taskInfo?.progress != null && taskInfo.progress > 0 && (
                  <span style={{ marginLeft: 10, color: '#6c8fff' }}>{taskInfo.progress}%</span>
                )}
              </div>

              {/* Progress bar */}
              <div className="ic-progress-bar">
                <div className="ic-progress-fill" style={{ width: `${taskInfo?.progress ?? 0}%` }} />
              </div>

              {/* Workflow steps */}
              <div className="ic-workflow-grid">
                {workflowSteps.map(step => (
                  <div key={step.key} className="ic-workflow-step"
                    style={{ borderColor: statusColor[step.status] + '44' }}>
                    <div className="ic-workflow-step-top">
                      <span>{step.icon}</span>
                      <span className="ic-wf-status" style={{ color: statusColor[step.status] }}>
                        {step.status === 'active' && <span className="ic-spinner" style={{ borderTopColor: '#6c8fff' }} />}
                        {statusLabel[step.status]}
                      </span>
                    </div>
                    <div className="ic-workflow-step-label">{step.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Done ─────────────────────────────────────── */}
          {phase === 'done' && result && (
            <>
              {/* Save bar */}
              <div className="library-save-bar">
                <span style={{ color: '#888', fontSize: 12 }}>Report generated</span>
                <button
                  className="library-save-btn"
                  onClick={saveReport}
                  disabled={saving || saved}
                  style={saved ? { background: '#00e67622', color: '#00e676', borderColor: '#00e67644' } : {}}
                >
                  {saved ? '✓ Saved to Library' : saving ? 'Saving...' : '💾 Save to Library'}
                </button>
              </div>
              {/* Individual reports accordion */}
              {Object.keys(result.reports ?? {}).length > 0 && (
                <div className="ic-agents-panel">
                  <div className="ic-agents-label">📎 Analyst Reports (click to expand)</div>
                  {Object.entries(result.reports).map(([key, content]) => {
                    const meta = [...ROLE_META, ...SYNTHESIS_STEPS.map(s => ({ key: s.key, icon: s.icon, label: s.label }))].find(m => m.key === key);
                    return (
                      <div key={key} className="ic-agent-card done">
                        <div className="ic-agent-header" style={{ cursor: 'pointer' }}
                          onClick={() => setExpanded(p => ({ ...p, [key]: !p[key] }))}>
                          <span className="ic-agent-icon">{meta?.icon ?? '📄'}</span>
                          <div className="ic-agent-info">
                            <div className="ic-agent-name">{meta?.label ?? key}</div>
                          </div>
                          <div className="ic-agent-status" style={{ color: '#00e676' }}>Done</div>
                          <span className="ic-agent-toggle">{expanded[key] ? '▲' : '▼'}</span>
                        </div>
                        {expanded[key] && (
                          <div className="ic-agent-output">{renderMd(content)}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Final memo */}
              <div className="ic-memo-output">
                {renderMd(result.markdown_report || result.final_decision)}
              </div>

              {result.investment_plan && (
                <div className="ic-investment-plan">
                  <div className="ic-plan-label">💹 Investment Plan</div>
                  {renderMd(result.investment_plan)}
                </div>
              )}
            </>
          )}

          {/* ── Error ────────────────────────────────────── */}
          {phase === 'error' && (
            <div className="ic-error">
              ❌ {error || 'Workflow failed'}
              <br />
              <button className="ic-regen-btn" style={{ marginTop: 12 }}
                onClick={() => { setPhase('configure'); setTaskInfo(null); setError(''); }}>
                Reconfigure
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
