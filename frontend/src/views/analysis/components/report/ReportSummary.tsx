import React from 'react';
import type { AnalysisResult, AnalysisReport } from '../../types/analysis';
import { ReportOverview } from './ReportOverview';
import { ReportStrategy } from './ReportStrategy';
import { ReportTechnicals } from './ReportTechnicals';
import { ReportChart } from './ReportChart';
import { ReportIntelligence } from './ReportIntelligence';
import { ReportDetails } from './ReportDetails';
import { ReportSentiment } from './ReportSentiment';
import { ReportFundamentals } from './ReportFundamentals';
import PredictionPanel from '../../../../components/PredictionPanel';

interface ReportSummaryProps {
  data: AnalysisResult | AnalysisReport;
  isHistory?: boolean;
}

/**
 * 完整报告展示组件
 * 整合概览、策略、资讯、详情四个区域
 */
export const ReportSummary: React.FC<ReportSummaryProps> = ({
  data,
  isHistory = false,
}) => {
  // 兼容 AnalysisResult 和 AnalysisReport 两种数据格式
  const report: AnalysisReport = 'report' in data ? data.report : data;
  // 使用 report id，因为 queryId 在批量分析时可能重复，且历史报告详情接口需要 recordId 来获取关联资讯和详情数据
  const recordId = report.meta.id;

  const { meta, summary, strategy, details } = report;
  const modelUsed = (meta.modelUsed || '').trim();
  const shouldShowModel = Boolean(
    modelUsed && !['unknown', 'error', 'none', 'null', 'n/a'].includes(modelUsed.toLowerCase()),
  );

  return (
    <div className="space-y-5 pb-8 animate-fade-in">
      {/* 概览区（首屏） */}
      <ReportOverview
        meta={meta}
        summary={summary}
        isHistory={isHistory}
      />

      {/* 策略点位区 */}
      <ReportStrategy strategy={strategy} />

      {/* K线图 */}
      <ReportChart stockCode={meta.stockCode} fetchedAt={meta.createdAt} />

      {/* 技术指标区 */}
      <ReportTechnicals
        rawResult={details?.rawResult}
        contextSnapshot={details?.contextSnapshot}
        fetchedAt={meta.createdAt}
      />

      {/* Fundamentals (US stocks: financials, growth, dividends) */}
      <ReportFundamentals
        rawResult={details?.rawResult}
        contextSnapshot={details?.contextSnapshot}
        fetchedAt={meta.createdAt}
      />

      {/* Social Sentiment（Adanos API） */}
      <ReportSentiment stockCode={meta.stockCode} />

      {/* AI 情报分析 */}
      <ReportIntelligence rawResult={details?.rawResult} />

      {/* Detail Forecast Snapshot (same-day detail result) */}
      <PredictionPanel symbol={meta.stockCode} refDate={meta.createdAt?.slice(0, 10)} />

      {/* 透明度与追溯区 */}
      <ReportDetails details={details} recordId={recordId} />

      {/* 分析模型标记（Issue #528）— 报告末尾 */}
      {shouldShowModel && (
        <p className="px-1 text-xs text-muted-text">
          Analysis Model: {modelUsed}
        </p>
      )}
    </div>
  );
};
