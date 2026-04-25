import type React from 'react';
import type { TaskInfo } from '../../types/analysis';

/**
 * 任务项组件属性
 */
interface TaskItemProps {
  task: TaskInfo;
  onCancel?: (taskId: string) => void;
  cancelling?: boolean;
}

/**
 * 单个任务项
 */
const TaskItem: React.FC<TaskItemProps> = ({ task, onCancel, cancelling = false }) => {
  const isPending = task.status === 'pending';
  const isProcessing = task.status === 'processing';
  const isWaitingForFundamentals = task.status === 'waiting_for_fundamentals';
  const isActive = isPending || isProcessing || isWaitingForFundamentals;

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-elevated rounded-lg border border-white/5">
      {/* 状态图标 */}
      <div className="shrink-0">
        {isProcessing || isWaitingForFundamentals ? (
          // 加载动画
          <svg className={`w-4 h-4 animate-spin ${isWaitingForFundamentals ? 'text-amber-400' : 'text-cyan'}`} fill="none" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : isPending ? (
          // 等待图标
          <svg className="w-4 h-4 text-muted-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        ) : null}
      </div>

      {/* 任务信息 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white truncate">
            {task.stockName || task.stockCode}
          </span>
          <span className="text-xs text-muted-text">
            {task.stockCode}
          </span>
        </div>
        {task.message && (
          <p className="text-xs text-secondary-text truncate mt-0.5">
            {task.message}
          </p>
        )}
      </div>

      {/* 状态标签 */}
      <div className="flex-shrink-0 flex items-center gap-2">
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            isWaitingForFundamentals
              ? 'bg-amber-400/15 text-amber-300'
              : isProcessing
              ? 'bg-cyan/20 text-cyan'
              : 'bg-white/10 text-muted-text'
          }`}
        >
          {isWaitingForFundamentals ? 'Waiting For Fundamentals' : isProcessing ? 'Analyzing' : 'Pending'}
        </span>
        {isActive && onCancel ? (
          <button
            type="button"
            onClick={() => onCancel(task.taskId)}
            disabled={cancelling}
            className="text-xs px-2 py-0.5 rounded border border-red-400/20 bg-red-400/10 text-red-300 disabled:opacity-50"
          >
            {cancelling ? 'Cancelling...' : 'Cancel'}
          </button>
        ) : null}
      </div>
    </div>
  );
};

/**
 * 任务面板属性
 */
interface TaskPanelProps {
  /** 任务列表 */
  tasks: TaskInfo[];
  /** 是否显示 */
  visible?: boolean;
  /** 标题 */
  title?: string;
  /** 自定义类名 */
  className?: string;
  /** 取消任务 */
  onCancelTask?: (taskId: string) => void;
  /** 正在取消中的任务 */
  cancellingTaskIds?: string[];
}

/**
 * 任务面板组件
 * 显示进行中的分析任务列表
 */
export const TaskPanel: React.FC<TaskPanelProps> = ({
  tasks,
  visible = true,
  title = 'Analysis Tasks',
  className = '',
  onCancelTask,
  cancellingTaskIds = [],
}) => {
  // 筛选活跃任务（pending 和 processing）
  const activeTasks = tasks.filter(
    (t) => t.status === 'pending' || t.status === 'processing' || t.status === 'waiting_for_fundamentals'
  );

  // 无任务或不可见时不渲染
  if (!visible || activeTasks.length === 0) {
    return null;
  }

  const pendingCount = activeTasks.filter((t) => t.status === 'pending').length;
  const processingCount = activeTasks.filter((t) => t.status === 'processing').length;
  const waitingFundamentalCount = activeTasks.filter((t) => t.status === 'waiting_for_fundamentals').length;

  return (
    <div className={`bg-card rounded-xl border border-white/5 overflow-hidden ${className}`}>
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          <span className="text-sm font-medium text-white">{title}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-text">
          {processingCount > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-cyan rounded-full animate-pulse" />
              {processingCount} running
            </span>
          )}
          {waitingFundamentalCount > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
              {waitingFundamentalCount} waiting fundamentals
            </span>
          )}
          {pendingCount > 0 && (
            <span>{pendingCount} waiting</span>
          )}
        </div>
      </div>

      {/* 任务列表 */}
      <div className="p-2 space-y-2 max-h-64 overflow-y-auto">
        {activeTasks.map((task) => (
          <TaskItem
            key={task.taskId}
            task={task}
            onCancel={onCancelTask}
            cancelling={cancellingTaskIds.includes(task.taskId)}
          />
        ))}
      </div>
    </div>
  );
};

export default TaskPanel;
