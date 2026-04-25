import type React from 'react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { ApiErrorAlert, ConfirmDialog } from '../components/common';
import { getParsedApiError } from '../api/error';
import type { HistoryItem, AnalysisReport, TaskInfo } from '../types/analysis';
import { historyApi } from '../api/history';
import { analysisApi, DuplicateTaskError } from '../api/analysis';
import { validateStockCode } from '../utils/validation';
import { getRecentStartDate, getTodayInShanghai } from '../utils/format';
import { useAnalysisStore } from '../stores/analysisStore';
import { ReportSummary, ReportMarkdown } from '../components/report';
import { HistoryList } from '../components/history';
import { TaskPanel } from '../components/tasks';
import { useTaskStream } from '../hooks';
import { redditAPI } from '../../sentiment/api/adanos';
import { AskAIDrawer } from '../components/chat/AskAIDrawer';

/**
 * Home Page - Single Page Design
 * Top input + Left history + Right report
 */
const HomePage: React.FC = () => {
  const {
    error: analysisError,
    setLoading,
    setError: setStoreError,
  } = useAnalysisStore();

  // Set page title
  useEffect(() => {
    document.title = 'Stock Analysis';
  }, []);

  // Input state
  const [stockCode, setStockCode] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [inputError, setInputError] = useState<string>();

// History list state
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [selectedHistoryIds, setSelectedHistoryIds] = useState<number[]>([]);
  const [isDeletingHistory, setIsDeletingHistory] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // Report detail state
  const [selectedReport, setSelectedReport] = useState<AnalysisReport | null>(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);

  // Task queue state
  const [activeTasks, setActiveTasks] = useState<TaskInfo[]>([]);
  const [cancellingTaskIds, setCancellingTaskIds] = useState<string[]>([]);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [showAskAI, setShowAskAI] = useState(false);

  // Markdown report drawer state
  const [showMarkdownDrawer, setShowMarkdownDrawer] = useState(false);

  // Search suggestions via Adanos API (same pattern as DeepDive)
  const [searchResults, setSearchResults] = useState<{ ticker: string; name?: string; exchange?: string; sector?: string }[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleSearchInput(q: string) {
    setStockCode(q.toUpperCase());
    setInputError(undefined);
    if (q.trim().length < 2) { setSearchResults([]); return; }
    setSearchLoading(true);
    try {
      const res = await redditAPI.search(q, 7, 8).catch(() => ({ results: [] }));
      const results = ((res as any).results || []) as { ticker: string; name?: string; exchange?: string; sector?: string }[];
      const unique = results.filter((r, i, arr) => arr.findIndex(x => x.ticker === r.ticker) === i);
      setSearchResults(unique.slice(0, 8));
    } finally {
      setSearchLoading(false);
    }
  }

  async function handleAnalyzeWithCode(code: string) {
    const { valid, message, normalized } = validateStockCode(code);
    if (!valid) { setInputError(message); return; }
    setSearchResults([]);
    setStockCode('');
    setInputError(undefined);
    setDuplicateError(null);
    setIsAnalyzing(true);
    setLoading(true);
    setStoreError(null);
    const currentRequestId = ++analysisRequestIdRef.current;
    try {
      const response = await analysisApi.analyzeAsync({ stockCode: normalized!, reportType: 'detailed' });
      if ('taskId' in response) console.log('Task submitted:', response.taskId);
    } catch (err) {
      if (currentRequestId === analysisRequestIdRef.current) {
        if (err instanceof DuplicateTaskError) {
          setDuplicateError(`Stock ${err.stockCode} is currently being analyzed, please wait`);
        } else {
          setStoreError(getParsedApiError(err));
        }
      }
    } finally {
      setIsAnalyzing(false);
      setLoading(false);
    }
  }

  // Used to track the current analysis request to avoid race conditions
  const analysisRequestIdRef = useRef<number>(0);

  // Update task in task list
  const updateTask = useCallback((updatedTask: TaskInfo) => {
    setActiveTasks((prev) => {
      const index = prev.findIndex((t) => t.taskId === updatedTask.taskId);
      if (index >= 0) {
        const newTasks = [...prev];
        newTasks[index] = updatedTask;
        return newTasks;
      }
      return prev;
    });
  }, []);

  // Remove completed/failed tasks
  const removeTask = useCallback((taskId: string) => {
    setActiveTasks((prev) => prev.filter((t) => t.taskId !== taskId));
  }, []);

  const handleCancelTask = useCallback(async (taskId: string) => {
    setCancellingTaskIds((prev) => prev.includes(taskId) ? prev : [...prev, taskId]);
    try {
      await analysisApi.cancelTask(taskId);
      removeTask(taskId);
    } catch (err) {
      setStoreError(getParsedApiError(err));
    } finally {
      setCancellingTaskIds((prev) => prev.filter((id) => id !== taskId));
    }
  }, [removeTask, setStoreError]);

  // SSE Task Stream
  useTaskStream({
    onTaskCreated: (task) => {
      setActiveTasks((prev) => {
        // Avoid duplicate addition
        if (prev.some((t) => t.taskId === task.taskId)) return prev;
        return [...prev, task];
      });
    },
    onTaskStarted: updateTask,
    onTaskUpdated: updateTask,
    onTaskCompleted: (task) => {
      // Refresh history list
      fetchHistory();
      // Delay removal of task so user can see completion status
      setTimeout(() => removeTask(task.taskId), 2000);
    },
    onTaskFailed: (task) => {
      updateTask(task);
      // Show error prompt
      setStoreError(getParsedApiError(task.error || 'Analysis failed'));
      // Delay removal of task
      setTimeout(() => removeTask(task.taskId), 5000);
    },
    onTaskCancelled: (task) => {
      removeTask(task.taskId);
    },
    onError: () => {
      console.warn('SSE connection disconnected, reconnecting...');
    },
    enabled: true,
  });

// Use refs to track mutable state, avoiding frequent re-builds of fetchHistory that cause effect loops
  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;
  const historyItemsRef = useRef(historyItems);
  historyItemsRef.current = historyItems;
  const selectedReportRef = useRef(selectedReport);
  selectedReportRef.current = selectedReport;

  useEffect(() => {
    const visibleIds = new Set(historyItems.map((item) => item.id));
    setSelectedHistoryIds((prev) => prev.filter((id) => visibleIds.has(id)));
  }, [historyItems]);

  // Load history list
  const fetchHistory = useCallback(async (autoSelectFirst = false, reset = true, silent = false) => {
    if (!silent) {
      if (reset) {
        setIsLoadingHistory(true);
        setCurrentPage(1);
      } else {
        setIsLoadingMore(true);
      }
    }

    // page is always 1 when reset=true, regardless of currentPageRef; the ref
    // is only used for load-more (reset=false) to get the next page number.
    const page = reset ? 1 : currentPageRef.current + 1;

    try {
      const response = await historyApi.getList({
        startDate: getRecentStartDate(30),
        endDate: getTodayInShanghai(),
        page,
        limit: pageSize,
      });

      if (silent && reset) {
        // Background refresh: merge new items to the top of the list, 
        // preserving loaded pagination data and scroll position.
        setHistoryItems(prev => {
          const existingIds = new Set(prev.map(item => item.id));
          const newItems = response.items.filter(item => !existingIds.has(item.id));
          return newItems.length > 0 ? [...newItems, ...prev] : prev;
        });
      } else if (reset) {
        setHistoryItems(response.items);
        setCurrentPage(1);
      } else {
        setHistoryItems(prev => [...prev, ...response.items]);
        setCurrentPage(page);
      }

      // Determine if there is more data
      if (!silent) {
        const totalLoaded = reset ? response.items.length : historyItemsRef.current.length + response.items.length;
        setHasMore(totalLoaded < response.total);
      }

      // If auto-select first is needed, data exists, and no report is currently selected
      if (autoSelectFirst && response.items.length > 0 && !selectedReportRef.current) {
        const firstItem = response.items[0];
        setIsLoadingReport(true);
        try {
          const report = await historyApi.getDetail(firstItem.id);
          setStoreError(null);
          setSelectedReport(report);
        } catch (err) {
          console.error('Failed to fetch first report:', err);
          setStoreError(getParsedApiError(err));
        } finally {
          setIsLoadingReport(false);
        }
      }
    } catch (err) {
      console.error('Failed to fetch history:', err);
      setStoreError(getParsedApiError(err));
    } finally {
      setIsLoadingHistory(false);
      setIsLoadingMore(false);
    }
  }, [pageSize, setStoreError]);

  // Load more history records
  const handleLoadMore = useCallback(() => {
    if (!isLoadingMore && hasMore) {
      fetchHistory(false, false);
    }
  }, [fetchHistory, isLoadingMore, hasMore]);

  const handleToggleHistorySelection = useCallback((recordId: number) => {
    setSelectedHistoryIds((prev) => (
      prev.includes(recordId)
        ? prev.filter((id) => id !== recordId)
        : [...prev, recordId]
    ));
  }, []);

  const handleToggleSelectAllHistory = useCallback(() => {
    const visibleIds = historyItemsRef.current.map((item) => item.id);
    setSelectedHistoryIds((prev) => {
      const visibleSet = new Set(visibleIds);
      const allSelected = visibleIds.length > 0 && visibleIds.every((id) => prev.includes(id));
      if (allSelected) {
        return prev.filter((id) => !visibleSet.has(id));
      }
      return Array.from(new Set([...prev, ...visibleIds]));
    });
  }, []);

  const handleDeleteSelectedHistory = useCallback(async () => {
    const recordIds = Array.from(new Set(selectedHistoryIds));
    if (recordIds.length === 0 || isDeletingHistory) {
      return;
    }

    setIsDeletingHistory(true);
    try {
      await historyApi.deleteRecords(recordIds);
      const deletedIds = new Set(recordIds);
      const selectedWasDeleted = selectedReportRef.current?.meta.id !== undefined
        && deletedIds.has(selectedReportRef.current.meta.id);

      // Clear selection immediately for responsive UI feedback.
      setSelectedHistoryIds([]);

      // Re-fetch page 1 to reset the pagination cursor (currentPage) and hasMore
      // so subsequent onLoadMore calls use the correct server-side offset after
      // the deletion shifted remaining records upward.
      // We also fetch fresh page-1 data directly here so we can read the new
      // first item without depending on historyItemsRef (which only updates on
      // the next render, after React flushes the state from fetchHistory).
      const [freshPage] = await Promise.all([
        selectedWasDeleted
          ? historyApi.getList({
              startDate: getRecentStartDate(30),
              endDate: getTodayInShanghai(),
              page: 1,
              limit: pageSize,
            })
          : Promise.resolve(null),
        fetchHistory(false, true),
      ]);

      if (selectedWasDeleted) {
        const nextItem = freshPage?.items?.[0] ?? null;
        if (nextItem) {
          try {
            const report = await historyApi.getDetail(nextItem.id);
            setStoreError(null);
            setSelectedReport(report);
          } catch (err) {
            console.error('Failed to fetch replacement report:', err);
            setStoreError(getParsedApiError(err));
            setSelectedReport(null);
          }
        } else {
          setSelectedReport(null);
        }
      }
    } catch (err) {
      console.error('Failed to delete history:', err);
      setStoreError(getParsedApiError(err));
    } finally {
      setIsDeletingHistory(false);
      setShowDeleteConfirm(false);
    }
  }, [fetchHistory, isDeletingHistory, pageSize, selectedHistoryIds, setStoreError]);

  const confirmDeleteHistory = useCallback(() => {
    setShowDeleteConfirm(true);
  }, []);

  // Initial load - auto select first item (executes once on mount)
  useEffect(() => {
    fetchHistory(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Background polling: re-fetch history every 30s for CLI-initiated analyses
  useEffect(() => {
    const interval = setInterval(() => {
      fetchHistory(false, true, true);
    }, 30_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refresh when tab regains visibility (e.g. user ran main.py in another terminal)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchHistory(false, true, true);
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Click history item to load report
  const handleHistoryClick = async (recordId: number) => {
    // Increment request ID to cancel any in-flight auto-select result.
    const requestId = ++analysisRequestIdRef.current;

    // Keep the current report visible while
    // the new one loads so the right panel doesn't flash a blank spinner on
    // every click. isLoadingReport is only used for the initial empty state.
    try {
      const report = await historyApi.getDetail(recordId);
      // Ignore result if a newer click has already been issued.
      if (requestId === analysisRequestIdRef.current) {
        setStoreError(null);
        setSelectedReport(report);
      }
    } catch (err) {
      console.error('Failed to fetch report:', err);
      setStoreError(getParsedApiError(err));
    }
  };

  // Analyze stock (async mode)
  const handleAnalyze = async () => {
    const { valid, message, normalized } = validateStockCode(stockCode);
    if (!valid) {
      setInputError(message);
      return;
    }

    setInputError(undefined);
    setDuplicateError(null);
    setIsAnalyzing(true);
    setLoading(true);
    setStoreError(null);

    // Track current request ID
    const currentRequestId = ++analysisRequestIdRef.current;

    try {
      // Submit analysis using async mode
      const response = await analysisApi.analyzeAsync({
        stockCode: normalized,
        reportType: 'detailed',
      });

      // Clear input box
      if (currentRequestId === analysisRequestIdRef.current) {
        setStockCode('');
      }

      // Task submitted, SSE will push updates
      if ('taskId' in response) {
        console.log('Task submitted:', response.taskId);
      } else {
        console.log('Batch tasks submitted:', response.accepted.map((task) => task.taskId));
      }
    } catch (err) {
      console.error('Analysis failed:', err);
      if (currentRequestId === analysisRequestIdRef.current) {
        if (err instanceof DuplicateTaskError) {
          // Show duplicate task error
          setDuplicateError(`Stock ${err.stockCode} is currently being analyzed, please wait`);
        } else {
          setStoreError(getParsedApiError(err));
        }
      }
    } finally {
      setIsAnalyzing(false);
      setLoading(false);
    }
  };

  // Submit on Enter key
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && stockCode && !isAnalyzing) {
      handleAnalyze();
    }
  };

  const sidebarContent = (
    <div className="flex flex-col gap-3 overflow-hidden min-h-0 h-full">
      <TaskPanel tasks={activeTasks} onCancelTask={handleCancelTask} cancellingTaskIds={cancellingTaskIds} />
      <HistoryList
        items={historyItems}
        isLoading={isLoadingHistory}
        isLoadingMore={isLoadingMore}
        hasMore={hasMore}
        selectedId={selectedReport?.meta.id}
        selectedIds={new Set(selectedHistoryIds)}
        isDeleting={isDeletingHistory}
        onItemClick={(id) => { handleHistoryClick(id); setSidebarOpen(false); }}
        onLoadMore={handleLoadMore}
        onToggleItemSelection={handleToggleHistorySelection}
        onToggleSelectAll={handleToggleSelectAllHistory}
        onDeleteSelected={confirmDeleteHistory}
        className="flex-1 overflow-hidden"
      />
    </div>
  );

  return (
    <div
      className="flex min-h-0 w-full flex-col overflow-hidden md:grid md:h-full md:px-4 lg:h-full"
      style={{ gridTemplateColumns: '240px 1fr', gridTemplateRows: 'auto 1fr', columnGap: '16px' }}
    >
      {/* Top Input Bar */}
      <header
        className="md:col-span-2 md:row-start-1 py-3 px-3 md:px-0 flex-shrink-0 flex items-center min-w-0 overflow-hidden"
      >
        <div className="flex items-center gap-2 w-full min-w-0 flex-1">
          {/* Mobile hamburger */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-hover transition-colors text-secondary-text hover:text-foreground flex-shrink-0"
            title="History"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="flex-1 relative min-w-0">
            <input
              ref={inputRef}
              type="text"
              value={stockCode}
              onChange={(e) => handleSearchInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search ticker or company (e.g. TSLA, Apple, NVDA)..."
              disabled={isAnalyzing}
              className={`input-terminal w-full ${inputError ? 'border-danger/50' : ''}`}
            />
            {searchLoading && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-text">searching...</span>
            )}
            {/* Dropdown — fixed positioning to escape overflow:hidden parents */}
            {searchResults.length > 0 && (() => {
              const rect = inputRef.current?.getBoundingClientRect();
              if (!rect) return null;
              return (
                <div
                  style={{ position: 'fixed', top: rect.bottom + 4, left: rect.left, width: rect.width, zIndex: 9999 }}
                  className="bg-card border border-border/70 rounded-xl shadow-2xl overflow-hidden"
                >
                  {searchResults.map((r) => (
                    <div
                      key={r.ticker}
                      onMouseDown={() => handleAnalyzeWithCode(r.ticker)}
                      className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-hover transition-colors border-b border-border/30 last:border-0"
                    >
                      <div>
                        <span className="text-sm font-bold text-foreground font-mono">{r.ticker}</span>
                        {r.name && <span className="text-xs text-secondary-text ml-2">{r.name}</span>}
                      </div>
                      <div className="flex gap-2 text-xs text-muted-text">
                        {r.exchange && <span>{r.exchange}</span>}
                        {r.sector && <span>{r.sector}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              );
            })()}
            {inputError && (
              <p className="absolute -bottom-4 left-0 text-xs text-danger">{inputError}</p>
            )}
            {duplicateError && (
              <p className="absolute -bottom-4 left-0 text-xs text-warning">{duplicateError}</p>
            )}
          </div>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!stockCode || isAnalyzing}
            className="btn-primary flex items-center gap-1.5 whitespace-nowrap flex-shrink-0"
          >
            {isAnalyzing ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Analyzing...
              </>
            ) : (
              'Analyze'
            )}
          </button>
        </div>
      </header>

      {/* Desktop sidebar */}
      <div className="hidden md:flex md:col-start-1 md:row-start-2 flex-col gap-3 overflow-hidden min-h-0">
        {sidebarContent}
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-[var(--home-mobile-overlay-bg)]" />
          <div
            className="absolute left-0 top-0 bottom-0 w-72 flex flex-col glass-card overflow-hidden border-r border-border/70 shadow-2xl p-3"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Right Report Detail */}
      <section className="md:col-start-2 md:row-start-2 flex-1 overflow-y-auto py-4 min-w-0 min-h-0">
        {analysisError ? (
          <ApiErrorAlert
            error={analysisError}
            className="mb-3"
          />
        ) : null}
        {isLoadingReport ? (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="h-10 w-10 animate-spin rounded-full border-3 border-[var(--home-loading-ring-track)] border-t-[var(--home-loading-ring-head)]" />
            <p className="mt-3 text-secondary-text text-sm">Loading report...</p>
          </div>
        ) : selectedReport ? (
          <div className="w-full pb-8">
            {/* Action buttons */}
            <div className="mb-3 flex items-center justify-end gap-2">
              <button
                onClick={() => setShowAskAI(true)}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors bg-[var(--home-action-ai-bg)] border-[var(--home-action-ai-border)] text-[var(--home-action-ai-text)] hover:bg-[var(--home-action-ai-hover-bg)]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Ask AI
              </button>
              <button
                disabled={selectedReport.meta.id === undefined}
                onClick={() => setShowMarkdownDrawer(true)}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 bg-[var(--home-action-report-bg)] border-[var(--home-action-report-border)] text-[var(--home-action-report-text)] hover:bg-[var(--home-action-report-hover-bg)]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Full Report
              </button>
            </div>
            <ReportSummary data={selectedReport} isHistory />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 mb-3 rounded-xl bg-elevated flex items-center justify-center">
              <svg className="w-6 h-6 text-muted-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="text-base font-medium text-foreground mb-1.5">Start Analysis</h3>
            <p className="text-xs text-muted-text max-w-xs">
              Enter a stock ticker to analyze, or select a report from the history on the left
            </p>
          </div>
        )}
      </section>

      {/* Ask AI Drawer */}
      <AskAIDrawer
        open={showAskAI}
        onClose={() => setShowAskAI(false)}
        stockCode={selectedReport?.meta.stockCode}
      />

      {/* Markdown Report Drawer */}
      {showMarkdownDrawer && selectedReport && selectedReport.meta.id && (
        <ReportMarkdown
          recordId={selectedReport.meta.id}
          stockName={selectedReport.meta.stockName || ''}
          stockCode={selectedReport.meta.stockCode}
          onClose={() => setShowMarkdownDrawer(false)}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        title="Delete History"
        message={
          selectedHistoryIds.length === 1
            ? 'Are you sure you want to delete this record? This action cannot be undone.'
            : `Are you sure you want to delete ${selectedHistoryIds.length} selected records? This action cannot be undone.`
        }
        confirmText={isDeletingHistory ? 'Deleting...' : 'Confirm Delete'}
        cancelText="Cancel"
        isDanger={true}
        onConfirm={handleDeleteSelectedHistory}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
};

export default HomePage;
