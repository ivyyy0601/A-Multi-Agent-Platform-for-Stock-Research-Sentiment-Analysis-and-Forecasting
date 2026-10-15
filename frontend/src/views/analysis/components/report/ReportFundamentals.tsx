import type React from 'react';
import { Card } from '../common';
import { SourceBadge } from './SourceBadge';

interface ReportFundamentalsProps {
  rawResult?: Record<string, unknown>;
  contextSnapshot?: Record<string, unknown>;
  fetchedAt?: string;
}

function get(obj: unknown, key: string): unknown {
  if (obj == null || typeof obj !== 'object') return undefined;
  return (obj as Record<string, unknown>)[key];
}

function fmt(v: unknown, decimals = 2): string {
  if (v == null || v === '' || v === 'N/A') return 'N/A';
  const n = Number(v);
  return isNaN(n) ? 'N/A' : n.toFixed(decimals);
}

function fmtLarge(v: unknown): string {
  if (v == null || v === '' || v === 'N/A') return 'N/A';
  const n = Number(v);
  if (isNaN(n)) return 'N/A';
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
}

function fmtPct(v: unknown, decimals = 1): string {
  if (v == null || v === '' || v === 'N/A') return 'N/A';
  const n = Number(v);
  return isNaN(n) ? 'N/A' : `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`;
}

function Row({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: 'green' | 'red' | 'none';
}) {
  const color =
    highlight === 'green' ? 'text-emerald-400' :
    highlight === 'red'   ? 'text-red-400' :
    'text-white';
  return (
    <div className="flex items-center justify-between gap-4 py-2 border-b border-white/5 last:border-0">
      <span className="text-xs text-secondary-text">{label}</span>
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

function pctColor(v: unknown): 'green' | 'red' | 'none' {
  const n = Number(v);
  if (isNaN(n)) return 'none';
  return n > 0 ? 'green' : n < 0 ? 'red' : 'none';
}

export const ReportFundamentals: React.FC<ReportFundamentalsProps> = ({
  rawResult,
  contextSnapshot,
  fetchedAt,
}) => {
  const dash = get(rawResult, 'dashboard') as Record<string, unknown> | undefined;
  const fund = (get(dash, 'fundamentals') ?? get(rawResult, 'fundamentals')) as Record<string, unknown> | undefined;
  const enhanced = (get(contextSnapshot, 'enhancedContext') ?? get(contextSnapshot, 'enhanced_context')) as Record<string, unknown> | undefined;
  const fundamentalContext = (get(enhanced, 'fundamentalContext') ?? get(enhanced, 'fundamental_context')) as Record<string, unknown> | undefined;
  const growthBlock = get(fundamentalContext, 'growth') as Record<string, unknown> | undefined;
  const earningsBlock = get(fundamentalContext, 'earnings') as Record<string, unknown> | undefined;
  const growthData = get(growthBlock, 'data') as Record<string, unknown> | undefined;
  const earningsData = get(earningsBlock, 'data') as Record<string, unknown> | undefined;
  const financialReport = get(earningsData, 'financialReport') as Record<string, unknown> | undefined
    ?? get(earningsData, 'financial_report') as Record<string, unknown> | undefined;
  const dividend = get(earningsData, 'dividend') as Record<string, unknown> | undefined;

  const source = fund ?? {};

  // API response goes through toCamelCase({ deep: true }), so all keys are camelCase.
  // Read both camelCase and snake_case to handle both live results and historical records.
  const revenue          = source.revenue ?? financialReport?.revenue;
  const netProfit        = source.netProfit ?? source.net_profit ?? financialReport?.netProfitParent ?? financialReport?.net_profit_parent;
  const operatingCF      = source.operatingCashFlow ?? source.operating_cash_flow ?? financialReport?.operatingCashFlow ?? financialReport?.operating_cash_flow;
  const roe              = source.roe ?? financialReport?.roe;
  const revenueYoy       = source.revenueYoy ?? source.revenue_yoy ?? growthData?.revenueYoy ?? growthData?.revenue_yoy;
  const netProfitYoy     = source.netProfitYoy ?? source.net_profit_yoy ?? growthData?.netProfitYoy ?? growthData?.net_profit_yoy;
  const grossMargin      = source.grossMargin ?? source.gross_margin ?? growthData?.grossMargin ?? growthData?.gross_margin;
  const ttmDivPerShare   = source.ttmDividendPerShare ?? source.ttm_dividend_per_share ?? dividend?.ttmCashDividendPerShare ?? dividend?.ttm_cash_dividend_per_share;
  const ttmDivYield      = source.ttmDividendYield ?? source.ttm_dividend_yield ?? dividend?.ttmDividendYieldPct ?? dividend?.ttm_dividend_yield_pct;
  const ttmDivCount      = source.ttmDividendCount ?? source.ttm_dividend_count ?? dividend?.ttmEventCount ?? dividend?.ttm_event_count;
  const reportDate       = source.reportDate ?? source.report_date ?? financialReport?.reportDate ?? financialReport?.report_date;

  const hasFinancials =
    revenue != null ||
    netProfit != null ||
    operatingCF != null ||
    roe != null;

  const hasGrowth =
    revenueYoy != null ||
    netProfitYoy != null ||
    roe != null ||
    grossMargin != null;

  const hasDividend =
    ttmDivPerShare != null ||
    ttmDivYield != null;
  const fundamentalResult = firstText(
    get(rawResult, 'fundamentalAnalysis'),
    get(rawResult, 'fundamental_analysis'),
    get(rawResult, 'companyHighlights'),
    get(rawResult, 'company_highlights'),
  );
  const growthResult = firstText(
    get(rawResult, 'mediumTermOutlook'),
    get(rawResult, 'medium_term_outlook'),
    get(rawResult, 'fundamentalAnalysis'),
    get(rawResult, 'fundamental_analysis'),
  );
  const coverageResult = firstText(
    get(rawResult, 'analysisSummary'),
    get(rawResult, 'analysis_summary'),
  );
  if (!hasFinancials && !hasGrowth && !hasDividend) return null;

  return (
    <Card variant="bordered" padding="md" className="overflow-hidden">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex items-baseline gap-2">
          <span className="label-uppercase">FUNDAMENTALS</span>
          <h3 className="text-base font-semibold text-white">Fundamental View</h3>
        </div>
        <SourceBadge source="yf" fetchedAt={fetchedAt} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {hasFinancials && (
          <div className="rounded-2xl border border-white/6 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <div className="flex items-center gap-2 mb-2">
              <p className="text-[11px] text-muted-text uppercase tracking-[0.18em]">Financials & Dividends</p>
              {reportDate != null && (
                <span className="text-[10px] text-muted-text">({String(reportDate).slice(0, 10)})</span>
              )}
            </div>
            {reportDate != null && (
              <Row label="Latest Report Period" value={String(reportDate).slice(0, 10)} />
            )}
            {revenue != null && (
              <Row label="Revenue" value={fmtLarge(revenue)} />
            )}
            {netProfit != null && (
              <Row label="Net Profit (attributable)" value={fmtLarge(netProfit)} />
            )}
            {operatingCF != null && (
              <Row label="Operating Cash Flow" value={fmtLarge(operatingCF)} />
            )}
            {roe != null && (
              <Row label="ROE" value={`${fmt(roe)}%`} highlight={pctColor(roe)} />
            )}
            {ttmDivPerShare != null && (
              <Row label="TTM Cash Dividend per Share" value={`$${fmt(ttmDivPerShare, 4)}`} />
            )}
            {ttmDivYield != null && (
              <Row label="TTM Dividend Yield" value={`${fmt(ttmDivYield, 4)}%`} highlight="green" />
            )}
            {ttmDivCount != null && (
              <Row label="TTM Dividend Events" value={String(ttmDivCount)} />
            )}
            <AnalysisResultNote text={fundamentalResult} />
          </div>
        )}

        {hasGrowth && (
          <div className="rounded-2xl border border-white/6 bg-[linear-gradient(180deg,rgba(59,130,246,0.08),rgba(255,255,255,0.015))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <p className="mb-3 text-[11px] text-muted-text uppercase tracking-[0.18em]">Growth Metrics</p>
            {revenueYoy != null && (
              <Row label="Revenue YoY" value={fmtPct(revenueYoy)} highlight={pctColor(revenueYoy)} />
            )}
            {netProfitYoy != null && (
              <Row label="Net Profit YoY" value={fmtPct(netProfitYoy)} highlight={pctColor(netProfitYoy)} />
            )}
            {roe != null && (
              <Row label="ROE" value={fmtPct(roe)} highlight={pctColor(roe)} />
            )}
            {grossMargin != null && (
              <Row label="Gross Margin" value={`${fmt(grossMargin)}%`} />
            )}
            <AnalysisResultNote text={growthResult} />
          </div>
        )}

        {fund != null && (
          <div className="rounded-2xl border border-white/6 bg-[linear-gradient(180deg,rgba(168,85,247,0.08),rgba(255,255,255,0.015))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <p className="mb-3 text-[11px] text-muted-text uppercase tracking-[0.18em]">Coverage</p>
            <Row label="Source" value="Yahoo Finance + pipeline aggregation" />
            <Row label="Financials" value={hasFinancials ? 'Available' : 'Unavailable'} />
            <Row label="Growth" value={hasGrowth ? 'Available' : 'Unavailable'} />
            <Row label="Dividend" value={hasDividend ? 'Available' : 'Unavailable'} />
            <AnalysisResultNote text={coverageResult} />
          </div>
        )}
      </div>
    </Card>
  );
};
