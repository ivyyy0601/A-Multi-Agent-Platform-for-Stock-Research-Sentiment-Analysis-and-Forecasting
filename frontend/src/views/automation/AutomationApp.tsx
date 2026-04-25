import { useEffect, useState } from 'react';
import axios from 'axios';
import './automation.css';

type RunStatus = 'running' | 'completed' | 'failed';

interface AutomationRun {
  id: number;
  pipeline: string;
  run_date: string;
  status: RunStatus;
  current_step: string | null;
  message: string | null;
  started_at: string;
  finished_at: string | null;
  details: Record<string, unknown>;
}

interface AutomationStatusPayload {
  current: Record<string, AutomationRun>;
  latest: Record<string, AutomationRun>;
  runs: AutomationRun[];
}

interface TriggerResponse {
  status: string;
  pipeline: string;
  message: string;
}

const PIPELINES = [
  {
    key: 'nightly_pipeline',
    label: 'Nightly Pipeline',
    steps: [
      'start',
      'fetch_recent',
      'ensure_ohlc',
      'submit_batch',
      'wait_batch',
      'collect_batch',
      'finbert',
      'train_detail',
      'cache_detail_forecast',
      'update_rag',
    ],
    stepLabels: {
      start: 'Start',
      fetch_recent: 'Fetch Recent',
      ensure_ohlc: 'Ensure OHLC',
      submit_batch: 'Submit Batch',
      wait_batch: 'Wait Batch',
      collect_batch: 'Collect Batch',
      finbert: 'Run FinBERT',
      train_detail: 'Train Detail',
      cache_detail_forecast: 'Cache Detail Forecasts',
      update_rag: 'Update RAG',
    } as Record<string, string>,
  },
];

function formatDateTime(value: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function formatPipelineName(name: string) {
  return name.replace(/_/g, ' ');
}

function triggerLabel(pipelineKey: string) {
  return pipelineKey === 'nightly_pipeline' ? 'Run Nightly Pipeline' : 'Run Pipeline';
}

function PipelineCard({
  pipeline,
  run,
  onRun,
  triggering,
}: {
  pipeline: (typeof PIPELINES)[number];
  run?: AutomationRun;
  onRun: (pipeline: string) => void;
  triggering: boolean;
}) {
  const activeStep = run?.current_step || null;
  const isRunning = run?.status === 'running';

  return (
    <section className="automation-card">
      <div className="automation-card-head">
        <div>
          <div className="automation-card-eyebrow">Pipeline</div>
          <h2>{pipeline.label}</h2>
        </div>
        <span className={`automation-status automation-status-${run?.status || 'idle'}`}>
          {run?.status || 'idle'}
        </span>
      </div>

      <div className="automation-card-meta">
        <div>
          <span className="automation-meta-label">Current Step</span>
          <span className="automation-meta-value">
            {activeStep ? pipeline.stepLabels[activeStep] || activeStep : 'Waiting'}
          </span>
        </div>
        <div>
          <span className="automation-meta-label">Started</span>
          <span className="automation-meta-value">{formatDateTime(run?.started_at || null)}</span>
        </div>
        <div>
          <span className="automation-meta-label">Finished</span>
          <span className="automation-meta-value">{formatDateTime(run?.finished_at || null)}</span>
        </div>
      </div>

      <div className="automation-steps">
        {pipeline.steps.map((step) => {
          const currentIndex = activeStep ? pipeline.steps.indexOf(activeStep) : -1;
          const stepIndex = pipeline.steps.indexOf(step);
          const completed = currentIndex > stepIndex || (!isRunning && run?.status === 'completed');
          const running = isRunning && activeStep === step;
          const failed = run?.status === 'failed' && activeStep === step;

          return (
            <div
              key={step}
              className={[
                'automation-step',
                completed ? 'completed' : '',
                running ? 'running' : '',
                failed ? 'failed' : '',
              ].join(' ').trim()}
            >
              <div className="automation-step-dot" />
              <div className="automation-step-label">{pipeline.stepLabels[step] || step}</div>
            </div>
          );
        })}
      </div>

      <div className="automation-card-message">
        {run?.message || 'No recent activity recorded for this pipeline.'}
      </div>

      <button
        className="automation-run-btn"
        onClick={() => onRun(pipeline.key)}
        disabled={isRunning || triggering}
      >
        {isRunning ? 'Running…' : triggering ? 'Starting…' : triggerLabel(pipeline.key)}
      </button>
    </section>
  );
}

export default function AutomationApp() {
  const [payload, setPayload] = useState<AutomationStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [triggering, setTriggering] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await axios.get<AutomationStatusPayload>('/api/automation/status?limit=20');
        if (cancelled) return;
        setPayload(response.data);
        setError('');
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load automation status');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 8000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const current = payload?.current || {};
  const latest = payload?.latest || {};
  const runs = payload?.runs || [];
  const anyRunning = Object.keys(current).length > 0;

  const refresh = async () => {
    const response = await axios.get<AutomationStatusPayload>('/api/automation/status?limit=20');
    setPayload(response.data);
    setError('');
  };

  const handleRun = async (pipeline: string) => {
    setTriggering(pipeline);
    try {
      await axios.post<TriggerResponse>(`/api/automation/run/${pipeline}`);
      await refresh();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (detail?.message) {
        setError(detail.message);
      } else {
        setError(err instanceof Error ? err.message : 'Failed to trigger automation');
      }
    } finally {
      setTriggering(null);
    }
  };

  return (
    <div className="automation-shell">
      <div className="automation-hero">
        <div>
          <div className="automation-eyebrow">Automation</div>
          <h1>Pipeline Status</h1>
          <p>
            Run the full evening pipeline from data ingestion through model training so
            the next day&apos;s forecast is ready after the nightly job completes.
          </p>
        </div>
        <div className={`automation-hero-badge ${anyRunning ? 'running' : 'idle'}`}>
          {anyRunning ? 'Running' : 'Idle'}
        </div>
      </div>

      {loading && <div className="automation-panel">Loading automation status…</div>}
      {error && !loading && <div className="automation-panel automation-error">{error}</div>}

      {!loading && !error && (
        <>
          <div className="automation-grid">
            {PIPELINES.map((pipeline) => (
              <PipelineCard
                key={pipeline.key}
                pipeline={pipeline}
                run={current[pipeline.key] || latest[pipeline.key]}
                onRun={handleRun}
                triggering={triggering === pipeline.key}
              />
            ))}
          </div>

          <section className="automation-panel">
            <div className="automation-panel-head">
              <div>
                <div className="automation-card-eyebrow">History</div>
                <h2>Recent Runs</h2>
              </div>
            </div>
            <div className="automation-table-wrap">
              <table className="automation-table">
                <thead>
                  <tr>
                    <th>Pipeline</th>
                    <th>Status</th>
                    <th>Step</th>
                    <th>Started</th>
                    <th>Finished</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id}>
                      <td>{formatPipelineName(run.pipeline)}</td>
                      <td>
                        <span className={`automation-status automation-status-${run.status}`}>
                          {run.status}
                        </span>
                      </td>
                      <td>{run.current_step || '—'}</td>
                      <td>{formatDateTime(run.started_at)}</td>
                      <td>{formatDateTime(run.finished_at)}</td>
                      <td className="automation-message-cell">{run.message || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
