import { useEffect, useMemo, useState } from 'react';
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

function downloadText(filename: string, content: string, type = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
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
  const [result, setResult] = useState<TeamRunResponse | null>(null);
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

  useEffect(() => {
    const taskId = taskInfo?.task_id;
    if (!taskId) return;

    const source = new EventSource('/api/v1/team/tasks/stream');

    const parse = (raw: MessageEvent<string>) => {
      const payload = JSON.parse(raw.data) as TeamTaskInfo;
      if (payload.task_id !== taskId) return;
      setTaskInfo(payload);
      if (payload.result) {
        setResult(payload.result);
      }
      if (payload.status === 'completed') {
        setRunning(false);
        source.close();
      }
      if (payload.status === 'failed') {
        setRunning(false);
        setError(payload.error || 'Team workflow failed');
        source.close();
      }
    };

    source.addEventListener('team_task_created', parse as EventListener);
    source.addEventListener('team_task_started', parse as EventListener);
    source.addEventListener('team_task_updated', parse as EventListener);
    source.addEventListener('team_task_completed', parse as EventListener);
    source.addEventListener('team_task_failed', parse as EventListener);
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [taskInfo?.task_id]);

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
                <button
                  type="button"
                  className="team-secondary-btn"
                  onClick={() => downloadText(`${result.stock_code}_team_report.md`, result.markdown_report, 'text/markdown;charset=utf-8')}
                >
                  Download Markdown
                </button>
                <button
                  type="button"
                  className="team-secondary-btn"
                  onClick={() => downloadText(`${result.stock_code}_team_state.json`, JSON.stringify(result, null, 2), 'application/json;charset=utf-8')}
                >
                  Download JSON
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
