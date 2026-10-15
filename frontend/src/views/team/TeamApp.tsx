import { useEffect, useMemo, useState } from 'react';
import { marked } from 'marked';
import './team.css';

type Provider = 'anthropic' | 'google';
type Role = 'market' | 'social' | 'news' | 'fundamentals' | 'ivy';

interface TeamWorkflowStep {
  key: string;
  label: string;
  icon: string;
  status: 'selected' | 'active' | 'completed' | 'skipped';
}

interface TeamRunResponse {
  run_id: string;
  stock_code: string;
  trade_date: string;
  llm_provider: Provider;
  deep_model: string;
  quick_model: string;
  roles: Role[];
  workflow: TeamWorkflowStep[];
  reports: Record<string, string>;
  final_decision: string;
  investment_plan?: string | null;
  markdown_report: string;
  state: Record<string, string>;
}

interface TeamTaskAccepted {
  task_id: string;
  status: 'pending' | 'processing';
  message?: string;
}

interface TeamTaskInfo {
  task_id: string;
  stock_code: string;
  trade_date: string;
  llm_provider: Provider;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  current_step?: string | null;
  workflow: TeamWorkflowStep[];
  result?: TeamRunResponse | null;
  error?: string | null;
}

const ROLE_META: Array<{ key: Role; label: string; icon: string }> = [
  { key: 'market', label: 'Market', icon: '📈' },
  { key: 'social', label: 'Social', icon: '🌐' },
  { key: 'news', label: 'News', icon: '📰' },
  { key: 'fundamentals', label: 'Fundamentals', icon: '📚' },
  { key: 'ivy', label: 'Ivy', icon: '🪴' },
];

const PROVIDER_DEFAULTS: Record<Provider, { deep: string; quick: string }> = {
  anthropic: {
    deep: 'claude-sonnet-4-6',
    quick: 'claude-haiku-4-5',
  },
  google: {
    deep: 'gemini-2.5-pro',
    quick: 'gemini-2.5-flash',
  },
};

const MODEL_OPTIONS: Record<
  Provider,
  {
    deep: Array<{ value: string; label: string; note: string }>;
    quick: Array<{ value: string; label: string; note: string }>;
  }
> = {
  anthropic: {
    deep: [
      { value: 'claude-opus-4-6', label: 'Claude Opus 4.6', note: 'Most intelligent, strongest for complex synthesis.' },
      { value: 'claude-opus-4-5', label: 'Claude Opus 4.5', note: 'Premium heavy model, slower and more expensive.' },
      { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', note: 'Best balance of quality and speed.' },
      { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5', note: 'Good for agents and coding, slightly older.' },
    ],
    quick: [
      { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', note: 'Fast with strong reasoning quality.' },
      { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', note: 'Fastest Claude option for quick steps.' },
      { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5', note: 'Solid fallback quick model.' },
    ],
  },
  google: {
    deep: [
      { value: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro', note: 'Reasoning-first for the hardest workflows.' },
      { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash', note: 'Fast newer model with strong all-around performance.' },
      { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', note: 'Stable pro-tier model.' },
      { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', note: 'Balanced and cheaper than pro.' },
    ],
    quick: [
      { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash', note: 'Best quick Gemini for speed and capability.' },
      { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', note: 'Stable balanced quick model.' },
      { value: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite', note: 'Most cost-efficient quick option.' },
      { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite', note: 'Low-cost fast fallback.' },
    ],
  },
};

function todayLocal() {
  return new Date().toISOString().slice(0, 10);
}

function renderMarkdown(text: string) {
  return marked.parse(text || '', { async: false }) as string;
}

// Opens the report as a styled page and triggers the print dialog, so it can be saved as PDF.
function downloadPdf(result: TeamRunResponse) {
  const reportSections = ROLE_META
    .filter((role) => result.reports?.[role.key]?.trim())
    .map((role) => ({ title: `${role.icon} ${role.label} Report`, body: result.reports[role.key], hero: false }));
  const sections = [
    { title: '📋 Final Decision', body: result.final_decision, hero: true },
    ...(result.investment_plan ? [{ title: '💼 Investment Plan', body: result.investment_plan, hero: false }] : []),
    ...reportSections,
  ];

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${result.stock_code} Team Report — ${result.trade_date}</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.7; color: #1a1a1a; max-width: 820px; margin: 0 auto; padding: 52px 48px; }
  h1.report-title { font-size: 28px; font-weight: 700; margin-bottom: 6px; }
  .meta { color: #666; font-size: 12px; margin-bottom: 44px; border-bottom: 1px solid #e8e8e8; padding-bottom: 16px; }
  .section { margin-bottom: 36px; }
  .section-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: #888; margin-bottom: 12px; }
  .section-body h1,.section-body h2,.section-body h3,.section-body h4 { font-weight: 700; margin: 18px 0 8px; line-height: 1.3; }
  .section-body h1 { font-size: 20px; } .section-body h2 { font-size: 17px; } .section-body h3 { font-size: 15px; color: #333; } .section-body h4 { font-size: 14px; }
  .section-body p { margin-bottom: 10px; }
  .section-body ul, .section-body ol { padding-left: 20px; margin-bottom: 10px; }
  .section-body li { margin-bottom: 4px; }
  .section-body strong { font-weight: 700; }
  .section-body em { font-style: italic; }
  .section-body code { background: #f4f4f4; padding: 1px 5px; border-radius: 3px; font-size: 13px; font-family: monospace; }
  .section-body hr { border: none; border-top: 1px solid #e0e0e0; margin: 16px 0; }
  .section-body table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 13px; }
  .section-body th, .section-body td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
  .section-body th { background: #f7f7f7; font-weight: 600; }
  .hero { background: #fffbef; border: 1px solid #f0d070; border-radius: 10px; padding: 24px 28px; }
  .hero .section-label { color: #a07800; }
  .divider { border: none; border-top: 1px solid #ebebeb; margin: 36px 0; }
  @media print { body { padding: 20px 28px; } @page { margin: 1.5cm; } }
</style>
</head>
<body>
<h1 class="report-title">${result.stock_code} — Multi-Agent Team Analysis</h1>
<div class="meta">
  <strong>Date:</strong> ${result.trade_date} &nbsp;|&nbsp;
  <strong>Provider:</strong> ${result.llm_provider} &nbsp;|&nbsp;
  <strong>Deep Model:</strong> ${result.deep_model} &nbsp;|&nbsp;
  <strong>Quick Model:</strong> ${result.quick_model} &nbsp;|&nbsp;
  <strong>Roles:</strong> ${result.roles.join(', ')}
</div>
${sections.map((section, index) => `
${index > 0 ? '<hr class="divider">' : ''}
<div class="section${section.hero ? ' hero' : ''}">
  <div class="section-label">${section.title}</div>
  <div class="section-body">${renderMarkdown(section.body || '')}</div>
</div>`).join('')}
</body></html>`;

  const win = window.open('', '_blank');
  if (!win) return;
  win.document.write(html);
  win.document.close();
  setTimeout(() => win.print(), 500);
}

// The last finished run is kept in the browser so it survives a page refresh.
const RESULT_STORAGE_KEY = 'team_last_result';

function loadStoredResult(): TeamRunResponse | null {
  try {
    const raw = localStorage.getItem(RESULT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TeamRunResponse) : null;
  } catch {
    return null;
  }
}

export default function TeamApp() {
  const [provider, setProvider] = useState<Provider>('anthropic');
  const [ticker, setTicker] = useState('AAPL');
  const [tradeDate, setTradeDate] = useState(todayLocal());
  const [deepModel, setDeepModel] = useState(PROVIDER_DEFAULTS.anthropic.deep);
  const [quickModel, setQuickModel] = useState(PROVIDER_DEFAULTS.anthropic.quick);
  const [roles, setRoles] = useState<Role[]>(['market', 'social', 'news', 'fundamentals', 'ivy']);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TeamRunResponse | null>(loadStoredResult);
  const [taskInfo, setTaskInfo] = useState<TeamTaskInfo | null>(null);
  const ivySelected = roles.includes('ivy');

  const deepOptions = MODEL_OPTIONS[provider].deep;
  const quickOptions = MODEL_OPTIONS[provider].quick;
  const deepNote = deepOptions.find((item) => item.value === deepModel)?.note;
  const quickNote = quickOptions.find((item) => item.value === quickModel)?.note;
  useEffect(() => {
    if (ivySelected) {
      setTradeDate(todayLocal());
    }
  }, [ivySelected]);

  useEffect(() => {
    if (!result) return;
    try {
      localStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(result));
    } catch {
      // Storage may be full or blocked; the result just won't survive a refresh.
    }
  }, [result]);

  function handleClear() {
    setResult(null);
    setTaskInfo(null);
    setError(null);
    try {
      localStorage.removeItem(RESULT_STORAGE_KEY);
    } catch {
      // Ignore blocked storage.
    }
  }

  const workflow = useMemo(() => {
    if (taskInfo?.workflow?.length) return taskInfo.workflow;
    if (result) return result.workflow;
    return [
      ...ROLE_META.map((role) => ({ key: role.key, label: role.label, icon: role.icon, status: roles.includes(role.key) ? 'selected' as const : 'skipped' as const })),
      { key: 'bull_researcher', label: 'Bull Researcher', icon: '🐂', status: 'selected' as const },
      { key: 'bear_researcher', label: 'Bear Researcher', icon: '🐻', status: 'selected' as const },
      { key: 'research_manager', label: 'Research Manager', icon: '🧭', status: 'selected' as const },
      { key: 'trader', label: 'Trader', icon: '💹', status: 'selected' as const },
      { key: 'portfolio_manager', label: 'Portfolio Manager', icon: '🛡️', status: 'selected' as const },
    ];
  }, [taskInfo, result, roles]);

  function handleProviderChange(next: Provider) {
    setProvider(next);
    setDeepModel(PROVIDER_DEFAULTS[next].deep);
    setQuickModel(PROVIDER_DEFAULTS[next].quick);
  }

  function toggleRole(role: Role) {
    setRoles((prev) => {
      if (prev.includes(role)) return prev.filter((item) => item !== role);
      return [...prev, role];
    });
  }

  function handleDateChange(nextDate: string) {
    if (ivySelected) return;
    setTradeDate(nextDate);
  }

  async function handleRun() {
    if (!ticker.trim()) {
      setError('Please enter a stock ticker.');
      return;
    }
    if (roles.length === 0) {
      setError('Pick at least one analyst role.');
      return;
    }

    setRunning(true);
    setError(null);
    setResult(null);
    setTaskInfo(null);

    try {
      const response = await fetch('/api/v1/team/run-async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: ticker.trim().toUpperCase(),
          trade_date: tradeDate,
          llm_provider: provider,
          deep_model: deepModel.trim() || undefined,
          quick_model: quickModel.trim() || undefined,
          roles,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        const message = payload?.detail?.message || payload?.message || 'Team run failed';
        throw new Error(message);
      }
      const accepted = payload as TeamTaskAccepted;
      setTaskInfo({
        task_id: accepted.task_id,
        stock_code: ticker.trim().toUpperCase(),
        trade_date: tradeDate,
        llm_provider: provider,
        status: accepted.status,
        progress: 0,
        message: accepted.message || 'Team task accepted',
        created_at: new Date().toISOString(),
        workflow,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Team run failed');
      setRunning(false);
    }
  }

  // Poll the task status every 3s while it runs.
  useEffect(() => {
    const taskId = taskInfo?.task_id;
    if (!taskId || !running) return;

    let cancelled = false;
    async function poll() {
      while (!cancelled) {
        try {
          const response = await fetch(`/api/v1/team/status/${taskId}`);
          if (!response.ok) throw new Error('status fetch failed');
          const payload = (await response.json()) as TeamTaskInfo;
          if (cancelled) return;
          setTaskInfo(payload);
          if (payload.result) setResult(payload.result);
          if (payload.status === 'completed') {
            setRunning(false);
            return;
          }
          if (payload.status === 'failed') {
            setRunning(false);
            setError(payload.error || 'Team workflow failed');
            return;
          }
        } catch {
          // Transient errors: keep polling.
        }
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    }
    void poll();
    return () => {
      cancelled = true;
    };
  }, [taskInfo?.task_id, running]);

  return (
    <div className="team-shell">
      <div className="team-backdrop" />
      <div className="team-layout">
        <section className="team-control-card">
          <div className="team-eyebrow">Team</div>
          <h1>Multi-Agent Desk</h1>
          <p className="team-subtitle">
            Run the TradingAgents workflow inside IvyTrader locally. This version uses the local analysis chain for Ivy.
          </p>

          <label className="team-field">
            <span>LLM Provider</span>
            <select value={provider} onChange={(e) => handleProviderChange(e.target.value as Provider)}>
              <option value="anthropic">Claude</option>
              <option value="google">Gemini</option>
            </select>
          </label>

          <div className="team-grid two">
            <label className="team-field">
              <span>Ticker</span>
              <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="AAPL" />
            </label>
            <label className="team-field">
              <span>Trade Date</span>
              <input type="date" value={tradeDate} onChange={(e) => handleDateChange(e.target.value)} disabled={ivySelected} />
            </label>
          </div>

          {ivySelected ? (
            <div className="team-inline-note">
              Ivy is limited to current-day analysis in this local setup, so the date is locked to today when the Ivy role is selected.
            </div>
          ) : null}

          <label className="team-field">
            <span>Deep Model</span>
            <select value={deepModel} onChange={(e) => setDeepModel(e.target.value)}>
              {deepOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {deepNote ? <div className="team-model-note">{deepNote}</div> : null}

          <label className="team-field">
            <span>Quick Model</span>
            <select value={quickModel} onChange={(e) => setQuickModel(e.target.value)}>
              {quickOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {quickNote ? <div className="team-model-note">{quickNote}</div> : null}

          <div className="team-field">
            <span>Roles</span>
            <div className="team-role-grid">
              {ROLE_META.map((role) => {
                const active = roles.includes(role.key);
                return (
                  <button
                    key={role.key}
                    type="button"
                    className={`team-role-chip ${active ? 'active' : ''}`}
                    onClick={() => toggleRole(role.key)}
                  >
                    <span>{role.icon}</span>
                    <span>{role.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {error ? <div className="team-error">{error}</div> : null}
          {running ? <div className="team-inline-note">Running the full team usually takes 1-2 minutes. Keep this page open while the agents finish.</div> : null}
          {taskInfo?.message ? <div className="team-model-note">{taskInfo.message}</div> : null}

          <div className="team-actions">
            <button type="button" className="team-run-btn" onClick={handleRun} disabled={running}>
              {running ? 'Running Team...' : 'Run Team'}
            </button>
            {result ? (
              <>
                <button type="button" className="team-secondary-btn" onClick={() => downloadPdf(result)}>
                  Download PDF
                </button>
                <button type="button" className="team-secondary-btn" onClick={handleClear}>
                  Clear
                </button>
              </>
            ) : null}
          </div>
        </section>

        <section className="team-visual-card">
          <div className="team-card-header">
            <div>
              <div className="team-eyebrow">Flow</div>
              <h2>Agent Workflow</h2>
            </div>
            <div className={`team-status-pill ${running ? 'running' : result ? 'done' : ''}`}>
              {running ? 'Running' : result ? 'Finished' : 'Idle'}
            </div>
          </div>

          <div className="team-flow">
            {workflow.map((step, index) => (
              <div key={step.key} className={`team-node ${step.status}`}>
                <div className="team-node-icon">{step.icon}</div>
                <div className="team-node-label">{step.label}</div>
                {index < workflow.length - 1 ? <div className="team-node-line" /> : null}
              </div>
            ))}
          </div>

          <div className="team-results-grid">
            <article className="team-result-card team-result-hero">
              <div className="team-result-heading">
                <div className="team-eyebrow">Portfolio Manager</div>
                <h3>Final Decision</h3>
              </div>
              <pre>{result?.final_decision || 'Run the desk to get the final manager output.'}</pre>
            </article>
            <article className="team-result-card">
              <div className="team-result-heading">
                <div className="team-eyebrow">Final</div>
                <h3>Investment Plan</h3>
              </div>
              <pre>{result?.investment_plan || 'The final investment plan will appear here.'}</pre>
            </article>
          </div>

          <div className="team-report-stack">
            {(['market', 'social', 'news', 'fundamentals', 'ivy'] as Role[]).map((key) => {
              const content = result?.reports?.[key];
              if (!content) return null;
              return (
                <article key={key} className="team-report-card">
                  <div className="team-report-title">
                    {ROLE_META.find((item) => item.key === key)?.icon} {ROLE_META.find((item) => item.key === key)?.label} Report
                  </div>
                  <pre>{content}</pre>
                </article>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
