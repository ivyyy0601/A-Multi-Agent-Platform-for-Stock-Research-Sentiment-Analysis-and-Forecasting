import type React from 'react';
import { Card } from '../common';
import { SourceBadge } from './SourceBadge';

interface ReportTechnicalsProps {
  rawResult?: Record<string, unknown>;
  contextSnapshot?: Record<string, unknown>;
  fetchedAt?: string;
}

function get(obj: unknown, ...keys: string[]): unknown {
  let cur = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

function fmt(v: unknown, decimals = 2): string {
  if (v == null) return 'N/A';
  const n = Number(v);
  return isNaN(n) ? 'N/A' : n.toFixed(decimals);
}

function fmtPercent(v: unknown, decimals = 2): string {
  if (v == null) return 'N/A';
  const n = Number(v);
  return isNaN(n) ? 'N/A' : `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`;
}

function fmtSigned(v: unknown, decimals = 2): string {
  if (v == null) return 'N/A';
  const n = Number(v);
  return isNaN(n) ? 'N/A' : `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}`;
}

function fmtVolume(v: unknown): string {
  if (v == null) return 'N/A';
  const n = Number(v);
  if (isNaN(n)) return 'N/A';
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(0);
}

function fmtMoneyCompact(v: unknown): string {
  if (v == null) return 'N/A';
  const n = Number(v);
  if (isNaN(n)) return 'N/A';
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
}

function normalizeMaPattern(value: unknown): string {
  const text = String(value ?? 'N/A');
  if (text === '多头排列 📈') return 'Bullish Alignment';
  if (text === '空头排列 📉') return 'Bearish Alignment';
  if (text === '短期向好 🔼') return 'Short-term Improving';
  if (text === '短期走弱 🔽') return 'Short-term Weakening';
  if (text === '震荡整理 ↔️') return 'Range-bound / Mixed';
  return text;
}

function SectionHeader({ title, source, fetchedAt }: { title: string; source: 'yf' | 'ai'; fetchedAt?: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3 border-b border-white/6 pb-2">
      <p className="text-[11px] text-muted-text uppercase tracking-[0.18em]">{title}</p>
      <SourceBadge source={source} fetchedAt={source === 'yf' ? fetchedAt : undefined} />
    </div>
  );
}

function Row({
  label,
  value,
  highlight,
  source,
}: {
  label: string;
  value: string;
  highlight?: 'green' | 'red' | 'yellow' | 'none';
  source?: 'yf' | 'ai';
}) {
  const colorMap = { green: 'text-emerald-400', red: 'text-red-400', yellow: 'text-yellow-400', none: 'text-white' };
  const color = highlight ? colorMap[highlight] : 'text-white';
  return (
    <div className="flex items-center justify-between gap-4 py-2 border-b border-white/5 last:border-0">
      <span className="text-xs text-secondary-text flex items-center min-w-0">
        {label}
        {source && <SourceBadge source={source} />}
      </span>
      <span className={`text-sm font-medium font-mono ${color} text-right`}>{value}</span>
    </div>
  );
}

function textOf(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    const text = textOf(value);
    if (text) return text;
  }
  return null;
}

function AnalysisResultNote({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <div className="mt-3 rounded-xl border border-white/6 bg-white/[0.03] px-3 py-2 text-xs leading-5 text-secondary-text">
      <span className="mr-2 text-[10px] uppercase tracking-[0.18em] text-muted-text">Analysis Result</span>
      {text}
    </div>
  );
}

export const ReportTechnicals: React.FC<ReportTechnicalsProps> = ({
  rawResult,
  contextSnapshot,
  fetchedAt,
}) => {
  const dash = get(rawResult, 'dashboard') as Record<string, unknown> | undefined;
  const dp    = (get(dash, 'dataPerspective') ?? get(dash, 'data_perspective')) as Record<string, unknown> | undefined;
  const price = (get(dp, 'pricePosition')   ?? get(dp, 'price_position'))   as Record<string, unknown> | undefined;
  const vol   = (get(dp, 'volumeAnalysis')  ?? get(dp, 'volume_analysis'))  as Record<string, unknown> | undefined;
  const trend = (get(dp, 'trendStatus')     ?? get(dp, 'trend_status'))     as Record<string, unknown> | undefined;

  const enhanced = (get(contextSnapshot, 'enhancedContext') ?? get(contextSnapshot, 'enhanced_context')) as Record<string, unknown> | undefined;
  const today = get(enhanced, 'today') as Record<string, unknown> | undefined;
  const realtime = get(enhanced, 'realtime') as Record<string, unknown> | undefined;
  const trendContext = get(enhanced, 'trendAnalysis') as Record<string, unknown> | undefined;

  if (!price && !vol && !trend && !today && !realtime && !trendContext) return null;

  const isBullish  = trend?.isBullish ?? trend?.is_bullish;
  const trendColor = isBullish === true ? 'green' : isBullish === false ? 'red' : 'none';
  const volRatio   = Number(
    realtime?.volumeRatio ?? realtime?.volume_ratio
    ?? vol?.volumeRatio ?? vol?.volume_ratio
    ?? 0,
  );
  const volColor   = volRatio >= 1.5 ? 'green' : volRatio < 0.5 ? 'yellow' : 'none';
  const biasVal    = Number(
    trendContext?.biasMa5 ?? trendContext?.bias_ma5
    ?? price?.biasMa5 ?? price?.bias_ma5
    ?? 0,
  );
  const biasColor  = Math.abs(biasVal) > 5 ? 'red' : Math.abs(biasVal) < 2 ? 'green' : 'none';

  const buyReasons = Array.isArray(trendContext?.signalReasons ?? trendContext?.signal_reasons)
    ? (trendContext?.signalReasons ?? trendContext?.signal_reasons) as unknown[]
    : [];
  const riskFactors = Array.isArray(trendContext?.riskFactors ?? trendContext?.risk_factors)
    ? (trendContext?.riskFactors ?? trendContext?.risk_factors) as unknown[]
    : [];
  const todayResult = firstText(
    get(rawResult, 'technicalAnalysis'),
    get(rawResult, 'technical_analysis'),
    get(rawResult, 'maAnalysis'),
    get(rawResult, 'ma_analysis'),
  );
  const realtimeResult = firstText(
    get(rawResult, 'volumeAnalysis'),
    get(rawResult, 'volume_analysis'),
    get(rawResult, 'dataInsights'),
    get(rawResult, 'data_insights'),
  );
  const trendResultText = firstText(
    get(rawResult, 'trendAnalysis'),
    get(rawResult, 'trend_analysis'),
    get(rawResult, 'shortTermOutlook'),
    get(rawResult, 'short_term_outlook'),
    get(rawResult, 'signalReasoning'),
    get(rawResult, 'signal_reasoning'),
  );
  const buyReasonText = firstText(
    get(rawResult, 'buyReason'),
    get(rawResult, 'buy_reason'),
    get(rawResult, 'analysisSummary'),
    get(rawResult, 'analysis_summary'),
  );
  const riskWarningText = firstText(
    get(rawResult, 'riskWarning'),
    get(rawResult, 'risk_warning'),
  );

  return (
    <Card variant="bordered" padding="md" className="overflow-hidden">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex items-baseline gap-2">
          <span className="label-uppercase">TECHNICALS</span>
          <h3 className="text-base font-semibold text-white">Technical View</h3>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-muted-text">
          <SourceBadge source="yf" fetchedAt={fetchedAt} /> Real Data
          <SourceBadge source="ai" /> AI Estimated
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {today && (
          <div className="rounded-2xl border border-white/6 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <SectionHeader title="Today's Quote" source="yf" fetchedAt={fetchedAt} />
            <Row label="Close" value={`$${fmt(today.close)}`} />
            <Row label="Open" value={`$${fmt(today.open)}`} />
            <Row label="High" value={`$${fmt(today.high)}`} />
            <Row label="Low" value={`$${fmt(today.low)}`} />
            <Row label="Volume" value={fmtVolume(today.volume)} />
            <Row label="Change %" value={fmtPercent(today.pctChg ?? today.pct_chg)} />
            <Row label="Turnover" value={fmtMoneyCompact(today.amount)} />
            <Row label="MA5" value={`$${fmt(today.ma5)}`} />
            <Row label="MA10" value={`$${fmt(today.ma10)}`} />
            <Row label="MA20" value={`$${fmt(today.ma20)}`} />
            <Row label="MA Pattern" value={normalizeMaPattern(get(enhanced, 'maStatus') ?? get(enhanced, 'ma_status') ?? 'N/A')} />
            <AnalysisResultNote text={todayResult} />
          </div>
        )}

        {realtime && (
          <div className="rounded-2xl border border-white/6 bg-[linear-gradient(180deg,rgba(8,145,178,0.08),rgba(255,255,255,0.015))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <SectionHeader title="Real-time Enhanced Data" source="yf" fetchedAt={fetchedAt} />
            <Row label="Current Price" value={`$${fmt(realtime.price)}`} />
            <Row label="P/E (TTM)" value={fmt(realtime.peRatio ?? realtime.pe_ratio)} />
            <Row label="P/B" value={fmt(realtime.pbRatio ?? realtime.pb_ratio)} />
            <Row label="Market Cap" value={fmtMoneyCompact(realtime.totalMv ?? realtime.total_mv)} />
            <Row label="Float Market Cap" value={fmtMoneyCompact(realtime.circMv ?? realtime.circ_mv)} />
            <Row label="60-day Change" value={fmtPercent(realtime.change60d ?? realtime.change_60d)} />
            <Row label="Volume Ratio" value={fmt(realtime.volumeRatio ?? realtime.volume_ratio)} highlight={volColor} />
            <Row label="Turnover Rate" value={fmtPercent(realtime.turnoverRate ?? realtime.turnover_rate, 4)} />
            <AnalysisResultNote text={realtimeResult} />
          </div>
        )}

        {trendContext && (
          <div className="rounded-2xl border border-white/6 bg-[linear-gradient(180deg,rgba(245,158,11,0.08),rgba(255,255,255,0.015))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <SectionHeader title="Trend Analysis" source="ai" />
            <Row label="Trend Status" value={String(trendContext.trendStatus ?? trendContext.trend_status ?? 'N/A')} highlight={trendColor} />
            <Row label="MA Alignment" value={String(trendContext.maAlignment ?? trendContext.ma_alignment ?? 'N/A')} />
            <Row label="Trend Strength" value={fmtSigned(trendContext.trendStrength ?? trendContext.trend_strength, 0)} />
            <Row label="Bias (MA5)" value={fmtPercent(trendContext.biasMa5 ?? trendContext.bias_ma5)} highlight={biasColor} />
            <Row label="Bias (MA10)" value={fmtPercent(trendContext.biasMa10 ?? trendContext.bias_ma10)} />
            <Row label="Volume Status" value={String(trendContext.volumeStatus ?? trendContext.volume_status ?? vol?.volumeStatus ?? vol?.volume_status ?? 'N/A')} />
            <Row label="System Signal" value={String(trendContext.buySignal ?? trendContext.buy_signal ?? 'N/A')} />
            <Row label="System Score" value={fmtSigned(trendContext.signalScore ?? trendContext.signal_score, 0)} />
            <Row label="Volume change" value={fmtSigned(get(enhanced, 'volumeChangeRatio') ?? get(enhanced, 'volume_change_ratio')) + 'x'} />
            <Row label="Price change" value={fmtPercent(get(enhanced, 'priceChangeRatio') ?? get(enhanced, 'price_change_ratio'))} />
            <AnalysisResultNote text={trendResultText} />
          </div>
        )}

        {(buyReasons.length > 0 || riskFactors.length > 0) && (
          <div className="lg:col-span-2">
            <SectionHeader title="System Analysis Rationale" source="ai" />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-2xl border border-emerald-400/12 bg-[linear-gradient(180deg,rgba(16,185,129,0.08),rgba(255,255,255,0.015))] p-4">
                <p className="mb-2 text-xs text-muted-text uppercase tracking-wider">Buy Reasons</p>
                {buyReasons.length > 0 ? (
                  <div className="space-y-1.5">
                    {buyReasons.map((reason, index) => (
                      <p key={`${String(reason)}-${index}`} className="text-sm leading-6 text-white">
                        {String(reason)}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-secondary-text">N/A</p>
                )}
                <AnalysisResultNote text={buyReasonText} />
              </div>
              <div className="rounded-2xl border border-red-400/12 bg-[linear-gradient(180deg,rgba(239,68,68,0.08),rgba(255,255,255,0.015))] p-4">
                <p className="mb-2 text-xs text-muted-text uppercase tracking-wider">Risk Factors</p>
                {riskFactors.length > 0 ? (
                  <div className="space-y-1.5">
                    {riskFactors.map((factor, index) => (
                      <p key={`${String(factor)}-${index}`} className="text-sm leading-6 text-white">
                        {String(factor)}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-secondary-text">N/A</p>
                )}
                <AnalysisResultNote text={riskWarningText} />
              </div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};
