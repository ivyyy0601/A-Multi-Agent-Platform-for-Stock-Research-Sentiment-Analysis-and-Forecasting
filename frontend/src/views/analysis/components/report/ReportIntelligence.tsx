import type React from 'react';
import { Card } from '../common';
import { SourceBadge } from './SourceBadge';

interface ReportIntelligenceProps {
  rawResult?: Record<string, unknown>;
}

function get(obj: unknown, ...keys: string[]): unknown {
  let cur = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

function toArr(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map(String);
}

function toStr(v: unknown): string {
  if (v == null) return '';
  return String(v);
}

export const ReportIntelligence: React.FC<ReportIntelligenceProps> = ({ rawResult }) => {
  if (!rawResult) return null;

  const dash = get(rawResult, 'dashboard') as Record<string, unknown> | undefined;

  // core_conclusion
  const cc       = (get(dash, 'coreConclusion') ?? get(dash, 'core_conclusion')) as Record<string, unknown> | undefined;
  const posAdv   = (get(cc, 'positionAdvice') ?? get(cc, 'position_advice')) as Record<string, unknown> | undefined;
  const signal   = toStr(cc?.signalType ?? cc?.signal_type);
  const timeSens = toStr(cc?.timeSensitivity ?? cc?.time_sensitivity);
  const noPos    = toStr(posAdv?.noPosition ?? posAdv?.no_position);
  const hasPos   = toStr(posAdv?.hasPosition ?? posAdv?.has_position);

  // intelligence
  const intel   = get(dash, 'intelligence') as Record<string, unknown> | undefined;
  const risks   = toArr(intel?.riskAlerts ?? intel?.risk_alerts);
  const cats    = toArr(intel?.positiveCatalysts ?? intel?.positive_catalysts);
  const outlook = toStr(intel?.earningsOutlook ?? intel?.earnings_outlook);
  const sentSum = toStr(intel?.sentimentSummary ?? intel?.sentiment_summary);

  // battle_plan
  const bp        = (get(dash, 'battlePlan') ?? get(dash, 'battle_plan')) as Record<string, unknown> | undefined;
  const checklist = toArr(bp?.actionChecklist ?? bp?.action_checklist);
  const ps        = (get(bp, 'positionStrategy') ?? get(bp, 'position_strategy')) as Record<string, unknown> | undefined;
  const sugPos    = toStr(ps?.suggestedPosition ?? ps?.suggested_position);
  const entryPlan = toStr(ps?.entryPlan ?? ps?.entry_plan);
  const riskCtrl  = toStr(ps?.riskControl ?? ps?.risk_control);

  // reasoning fields (top-level, camelCase after API transform)
  const signalReasoning = toStr(rawResult?.signalReasoning ?? rawResult?.signal_reasoning);
  const dataInsights    = toStr(rawResult?.dataInsights ?? rawResult?.data_insights);
  const sentReasoning   = toStr(rawResult?.marketSentimentReasoning ?? rawResult?.market_sentiment_reasoning);

  const hasData = signal || risks.length || cats.length || checklist.length || signalReasoning || dataInsights || sentReasoning;
  if (!hasData) return null;

  return (
    <div className="space-y-4">
      {/* 信号 + 操作建议 */}
      {(signal || noPos || hasPos) && (
        <Card variant="bordered" padding="md">
          <div className="mb-4 flex items-center gap-3">
            <div className="flex items-baseline gap-2">
              <span className="label-uppercase">SIGNAL</span>
              <h3 className="text-base font-semibold text-white">Signal</h3>
            </div>
            <span className="rounded px-1 py-0.5 text-[10px] font-medium bg-purple-400/10 text-purple-400 border border-purple-400/20">AI</span>
          </div>
          <div className="space-y-3">
            {signal && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-secondary-text">Signal Type</span>
                <span className="text-sm font-medium text-white">{signal}</span>
              </div>
            )}
            {timeSens && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-secondary-text">Time Sensitivity</span>
                <span className="text-xs text-cyan">{timeSens}</span>
              </div>
            )}
            {noPos && (
              <div className="rounded-lg bg-emerald-400/8 border border-emerald-400/15 p-3">
                <p className="text-xs text-emerald-400 font-medium mb-1">No Position</p>
                <p className="text-xs text-secondary-text leading-relaxed">{noPos}</p>
              </div>
            )}
            {hasPos && (
              <div className="rounded-lg bg-yellow-400/8 border border-yellow-400/15 p-3">
                <p className="text-xs text-yellow-400 font-medium mb-1">Has Position</p>
                <p className="text-xs text-secondary-text leading-relaxed">{hasPos}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 风险 + 利好 */}
      {(risks.length > 0 || cats.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {risks.length > 0 && (
            <Card variant="bordered" padding="md">
              <div className="mb-3 flex items-center gap-2">
                <span className="label-uppercase">RISKS</span>
                <h3 className="text-sm font-semibold text-white">Risk Alerts</h3>
                <SourceBadge source="ai" />
              </div>
              <div className="space-y-2">
                {risks.map((r, i) => (
                  <div key={i} className="flex gap-2 text-xs text-secondary-text leading-relaxed">
                    <span className="text-red-400 shrink-0">⚠</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {cats.length > 0 && (
            <Card variant="bordered" padding="md">
              <div className="mb-3 flex items-center gap-2">
                <span className="label-uppercase">CATALYSTS</span>
                <h3 className="text-sm font-semibold text-white">Catalysts</h3>
                <SourceBadge source="ai" />
              </div>
              <div className="space-y-2">
                {cats.map((c, i) => (
                  <div key={i} className="flex gap-2 text-xs text-secondary-text leading-relaxed">
                    <span className="text-emerald-400 shrink-0">↑</span>
                    <span>{c}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* 业绩预期 + 情绪摘要 */}
      {(outlook || sentSum) && (
        <Card variant="bordered" padding="md">
          <div className="mb-3 flex items-center gap-2">
            <span className="label-uppercase">OUTLOOK</span>
            <h3 className="text-sm font-semibold text-white">Outlook</h3>
            <SourceBadge source="ai" />
          </div>
          <div className="space-y-3">
            {outlook && (
              <div>
                <p className="text-xs text-muted-text mb-1">Earnings Outlook</p>
                <p className="text-xs text-secondary-text leading-relaxed">{outlook}</p>
              </div>
            )}
            {sentSum && (
              <div>
                <p className="text-xs text-muted-text mb-1">Sentiment Summary</p>
                <p className="text-xs text-secondary-text leading-relaxed">{sentSum}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 推理链 + 数据洞察 + 情绪解释 */}
      {(signalReasoning || dataInsights || sentReasoning) && (
        <Card variant="bordered" padding="md">
          <div className="mb-3 flex items-center gap-2">
            <span className="label-uppercase">REASONING</span>
            <h3 className="text-sm font-semibold text-white">Analysis Reasoning</h3>
            <SourceBadge source="ai" />
          </div>
          <div className="space-y-4">
            {signalReasoning && (
              <div>
                <p className="text-xs text-muted-text mb-1">Signal Reasoning</p>
                <p className="text-xs text-secondary-text leading-relaxed whitespace-pre-line">{signalReasoning}</p>
              </div>
            )}
            {dataInsights && (
              <div>
                <p className="text-xs text-muted-text mb-1">Data Insights</p>
                <p className="text-xs text-secondary-text leading-relaxed whitespace-pre-line">{dataInsights}</p>
              </div>
            )}
            {sentReasoning && (
              <div>
                <p className="text-xs text-muted-text mb-1">Market Sentiment Reasoning</p>
                <p className="text-xs text-secondary-text leading-relaxed whitespace-pre-line">{sentReasoning}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 仓位策略 */}
      {(sugPos || entryPlan || riskCtrl) && (
        <Card variant="bordered" padding="md">
          <div className="mb-3 flex items-center gap-2">
            <span className="label-uppercase">POSITION</span>
            <h3 className="text-sm font-semibold text-white">Position Strategy</h3>
            <SourceBadge source="ai" />
          </div>
          <div className="space-y-3">
            {sugPos && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-secondary-text">Suggested Position</span>
                <span className="text-xs font-medium text-cyan">{sugPos}</span>
              </div>
            )}
            {entryPlan && (
              <div>
                <p className="text-xs text-muted-text mb-1">Entry Plan</p>
                <p className="text-xs text-secondary-text leading-relaxed">{entryPlan}</p>
              </div>
            )}
            {riskCtrl && (
              <div>
                <p className="text-xs text-muted-text mb-1">Risk Control</p>
                <p className="text-xs text-secondary-text leading-relaxed">{riskCtrl}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 操作检查清单 */}
      {checklist.length > 0 && (
        <Card variant="bordered" padding="md">
          <div className="mb-3 flex items-center gap-2">
            <span className="label-uppercase">CHECKLIST</span>
            <h3 className="text-sm font-semibold text-white">Entry Checklist</h3>
            <SourceBadge source="ai" />
          </div>
          <div className="space-y-2">
            {checklist.map((item, i) => {
              const isOk   = item.startsWith('✅');
              const isWarn = item.startsWith('⚠');
              const color  = isOk ? 'text-emerald-400' : isWarn ? 'text-yellow-400' : 'text-red-400';
              return (
                <div key={i} className={`text-xs leading-relaxed ${color}`}>{item}</div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
};
