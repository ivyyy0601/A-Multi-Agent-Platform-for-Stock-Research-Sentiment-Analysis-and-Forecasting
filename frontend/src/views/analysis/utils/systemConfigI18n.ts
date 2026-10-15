import type { SystemConfigCategory } from '../types/systemConfig';

const categoryTitleMap: Record<SystemConfigCategory, string> = {
  base: 'General',
  data_source: 'Data Sources',
  ai_model: 'AI Models',
  notification: 'Notifications',
  system: 'System',
  agent: 'Agent',
  backtest: 'Backtest',
  uncategorized: 'Other',
};

const categoryDescriptionMap: Partial<Record<SystemConfigCategory, string>> = {
  base: 'Manage watchlist and basic runtime parameters.',
  data_source: 'Manage market data sources and priority strategy.',
  ai_model: 'Manage model providers, model names, and inference parameters.',
  notification: 'Manage bot, webhook, and notification settings.',
  system: 'Manage scheduling, logging, ports, and other system-level parameters.',
  agent: 'Manage Agent mode, strategies, and multi-agent orchestration.',
  backtest: 'Manage backtest toggles, evaluation windows, and engine parameters.',
  uncategorized: 'Other uncategorized configuration items.',
};

const fieldTitleMap: Record<string, string> = {
  STOCK_LIST: 'Watchlist',
  TUSHARE_TOKEN: 'Tushare Token',
  BOCHA_API_KEYS: 'Bocha API Keys',
  TAVILY_API_KEYS: 'Tavily API Keys',
  SERPAPI_API_KEYS: 'SerpAPI API Keys',
  BRAVE_API_KEYS: 'Brave API Keys',
  SEARXNG_BASE_URLS: 'SearXNG Base URLs',
  MINIMAX_API_KEYS: 'MiniMax API Keys',
  NEWS_STRATEGY_PROFILE: 'News Window Profile',
  NEWS_MAX_AGE_DAYS: 'Max News Age (days)',
  REALTIME_SOURCE_PRIORITY: 'Realtime Data Source Priority',
  ENABLE_REALTIME_TECHNICAL_INDICATORS: 'Intraday Realtime Technicals',
  LITELLM_MODEL: 'Primary Model',
  AGENT_LITELLM_MODEL: 'Agent Primary Model',
  LITELLM_FALLBACK_MODELS: 'Fallback Models',
  LITELLM_CONFIG: 'LiteLLM Config File',
  LLM_CHANNELS: 'LLM Channels',
  LLM_TEMPERATURE: 'Sampling Temperature',
  AIHUBMIX_KEY: 'AIHubmix Key',
  DEEPSEEK_API_KEY: 'DeepSeek API Key',
  GEMINI_API_KEY: 'Gemini API Key',
  GEMINI_MODEL: 'Gemini Model',
  GEMINI_TEMPERATURE: 'Gemini Temperature',
  OPENAI_API_KEY: 'OpenAI API Key',
  OPENAI_BASE_URL: 'OpenAI Base URL',
  OPENAI_MODEL: 'OpenAI Model',
  WECHAT_WEBHOOK_URL: 'WeChat Work Webhook',
  DINGTALK_APP_KEY: 'DingTalk App Key',
  DINGTALK_APP_SECRET: 'DingTalk App Secret',
  PUSHPLUS_TOKEN: 'PushPlus Token',
  REPORT_SUMMARY_ONLY: 'Summary-only Notifications',
  MAX_WORKERS: 'Max Concurrent Workers',
  SCHEDULE_TIME: 'Scheduled Task Time',
  HTTP_PROXY: 'HTTP Proxy',
  LOG_LEVEL: 'Log Level',
  WEBUI_PORT: 'WebUI Port',
  AGENT_MODE: 'Enable Agent Mode',
  AGENT_MAX_STEPS: 'Agent Max Steps',
  AGENT_SKILLS: 'Agent Active Strategies',
  AGENT_STRATEGY_DIR: 'Agent Strategy Directory',
  AGENT_ARCH: 'Agent Architecture',
  AGENT_ORCHESTRATOR_MODE: 'Orchestration Mode',
  AGENT_ORCHESTRATOR_TIMEOUT_S: 'Orchestration Timeout (s)',
  AGENT_RISK_OVERRIDE: 'Risk Agent Override',
  AGENT_STRATEGY_AUTOWEIGHT: 'Strategy Auto-weighting',
  AGENT_STRATEGY_ROUTING: 'Strategy Routing Mode',
  AGENT_MEMORY_ENABLED: 'Memory & Calibration',
  BACKTEST_ENABLED: 'Enable Backtest',
  BACKTEST_EVAL_WINDOW_DAYS: 'Backtest Eval Window (trading days)',
  BACKTEST_MIN_AGE_DAYS: 'Backtest Min History Days',
  BACKTEST_ENGINE_VERSION: 'Backtest Engine Version',
  BACKTEST_NEUTRAL_BAND_PCT: 'Neutral Band Threshold (%)',
};

const fieldDescriptionMap: Record<string, string> = {
  STOCK_LIST: 'Comma-separated stock codes, e.g.: AAPL,TSLA,AMZN.',
  TUSHARE_TOKEN: 'Credentials for accessing the Tushare Pro data service.',
  BOCHA_API_KEYS: 'Bocha keys for news search (highest priority). Comma-separate multiple keys.',
  TAVILY_API_KEYS: 'Tavily keys for news search. Comma-separate multiple keys.',
  SERPAPI_API_KEYS: 'SerpAPI keys for news search. Comma-separate multiple keys.',
  BRAVE_API_KEYS: 'Brave Search keys for news search. Comma-separate multiple keys.',
  SEARXNG_BASE_URLS: 'SearXNG self-hosted instance URLs (comma-separated). Requires format: json in settings.yml.',
  MINIMAX_API_KEYS: 'MiniMax keys for news search (lowest priority). Comma-separate multiple keys.',
  NEWS_STRATEGY_PROFILE: 'News window profile: ultra_short=1d, short=3d, medium=7d, long=30d.',
  NEWS_MAX_AGE_DAYS: 'Max news age cap. Effective window = min(profile days, NEWS_MAX_AGE_DAYS).',
  REALTIME_SOURCE_PRIORITY: 'Comma-separated data source call priority.',
  ENABLE_REALTIME_TECHNICAL_INDICATORS: 'Use real-time price to compute MA5/MA10/MA20 and bullish alignment during intraday analysis; disabled = use prior close.',
  LITELLM_MODEL: 'Primary model, format provider/model (e.g. gemini/gemini-2.5-flash). Auto-inferred when channels are configured.',
  AGENT_LITELLM_MODEL: 'Agent-specific primary model. Inherits primary model if empty; parsed as openai/<model> if no provider prefix.',
  LITELLM_FALLBACK_MODELS: 'Fallback models, comma-separated, tried in order when primary fails.',
  LITELLM_CONFIG: 'LiteLLM YAML config file path (advanced). Highest priority.',
  LLM_CHANNELS: 'Channel name list (comma-separated). Recommended to manage via the channel editor above.',
  LLM_TEMPERATURE: 'Controls output randomness. 0 = deterministic, 2 = maximum randomness. Recommended: 0.7.',
  AIHUBMIX_KEY: 'AIHubmix all-in-one key, auto-routes to aihubmix.com/v1.',
  DEEPSEEK_API_KEY: 'DeepSeek official API key. Auto-uses deepseek-chat model when set.',
  GEMINI_API_KEY: 'API key for Gemini service.',
  GEMINI_MODEL: 'Gemini model name for analysis.',
  GEMINI_TEMPERATURE: 'Controls output randomness, typically 0.0 to 2.0.',
  OPENAI_API_KEY: 'API key for OpenAI-compatible service.',
  OPENAI_BASE_URL: 'OpenAI-compatible API endpoint, e.g. https://api.deepseek.com/v1.',
  OPENAI_MODEL: 'OpenAI-compatible model name, e.g. gpt-4o-mini, deepseek-chat.',
  WECHAT_WEBHOOK_URL: 'WeChat Work bot webhook URL.',
  DINGTALK_APP_KEY: 'DingTalk app-mode App Key.',
  DINGTALK_APP_SECRET: 'DingTalk app-mode App Secret.',
  PUSHPLUS_TOKEN: 'PushPlus push token.',
  REPORT_SUMMARY_ONLY: 'Push analysis summary only, without individual stock details. Useful for quick review of multiple stocks.',
  MAX_WORKERS: 'Max concurrent workers in async task queue. Applied when queue is idle after save; deferred when busy.',
  SCHEDULE_TIME: 'Daily scheduled task execution time in HH:MM format.',
  HTTP_PROXY: 'Network proxy address. Leave blank to disable.',
  LOG_LEVEL: 'Log output level.',
  WEBUI_PORT: 'Web UI server listening port.',
  AGENT_MODE: 'Enable ReAct Agent for stock analysis.',
  AGENT_MAX_STEPS: 'Max steps the Agent can think and invoke tools.',
  AGENT_SKILLS: 'Comma-separated trading strategy list, e.g.: bull_trend,ma_golden_cross,shrink_pullback.',
  AGENT_STRATEGY_DIR: 'Directory path containing Agent strategy YAML files.',
  AGENT_ARCH: 'Agent execution architecture. single = classic single agent; multi = multi-agent orchestration (experimental).',
  AGENT_ORCHESTRATOR_MODE: 'Multi-Agent orchestration depth. quick (tech→decision), standard (tech→intel→decision), full (with risk control), strategy (with strategy eval).',
  AGENT_ORCHESTRATOR_TIMEOUT_S: 'Total timeout budget for multi-agent orchestration (seconds). 0 = unlimited.',
  AGENT_RISK_OVERRIDE: 'Allow risk control agent to veto buy signals when critical risks are detected.',
  AGENT_STRATEGY_AUTOWEIGHT: 'Automatically adjust strategy weights based on backtest performance.',
  AGENT_STRATEGY_ROUTING: 'Strategy selection mode. auto = auto-select by market state, manual = use AGENT_SKILLS list.',
  AGENT_MEMORY_ENABLED: 'Enable memory and calibration system to track historical analysis accuracy and auto-adjust confidence.',
  BACKTEST_ENABLED: 'Enable backtest functionality (true/false).',
  BACKTEST_EVAL_WINDOW_DAYS: 'Backtest evaluation window length in trading days.',
  BACKTEST_MIN_AGE_DAYS: 'Only backtest analysis records older than this many days.',
  BACKTEST_ENGINE_VERSION: 'Backtest engine version identifier for distinguishing result versions.',
  BACKTEST_NEUTRAL_BAND_PCT: 'Neutral band threshold percentage, e.g. 2 means -2% to +2%.',
};

export function getCategoryTitleZh(category: SystemConfigCategory, fallback?: string): string {
  return categoryTitleMap[category] || fallback || category;
}

export function getCategoryDescriptionZh(category: SystemConfigCategory, fallback?: string): string {
  return categoryDescriptionMap[category] || fallback || '';
}

export function getFieldTitleZh(key: string, fallback?: string): string {
  return fieldTitleMap[key] || fallback || key;
}

export function getFieldDescriptionZh(key: string, fallback?: string): string {
  return fieldDescriptionMap[key] || fallback || '';
}
