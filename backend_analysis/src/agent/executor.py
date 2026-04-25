# -*- coding: utf-8 -*-
"""
Agent Executor — ReAct loop with tool calling.

Orchestrates the LLM + tools interaction loop:
1. Build system prompt (persona + tools + skills)
2. Send to LLM with tool declarations
3. If tool_call → execute tool → feed result back
4. If text → parse as final answer
5. Loop until final answer or max_steps

The core execution loop is delegated to :mod:`src.agent.runner` so that
both the legacy single-agent path and future multi-agent runners share the
same implementation.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.agent.llm_adapter import LLMToolAdapter
from src.agent.runner import run_agent_loop, parse_dashboard_json
from src.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================
# Agent result
# ============================================================

@dataclass
class AgentResult:
    """Result from an agent execution run."""
    success: bool = False
    content: str = ""                          # final text answer from agent
    dashboard: Optional[Dict[str, Any]] = None  # parsed dashboard JSON
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)  # execution trace
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""                            # comma-separated models used (supports fallback)
    error: Optional[str] = None


# ============================================================
# System prompt builder
# ============================================================

AGENT_SYSTEM_PROMPT = """You are a professional stock investment analyst Agent specializing in trend trading. You have access to data tools and trading strategies. Your job is to generate a structured **Decision Dashboard** analysis report.

🔴 CRITICAL: ALL output MUST be in English. Every JSON string value must be in English. Do NOT use Chinese or any other language, even if input data is in Chinese. Translate everything to English.

## Workflow (must execute in strict phase order — wait for each phase to complete before proceeding)

**Phase 1 · Quote & Candlestick** (execute first)
- `get_realtime_quote` — fetch real-time quote
- `get_daily_history` — fetch historical candlestick data

**Phase 2 · Technicals & Chips** (after Phase 1 returns)
- `analyze_trend` — get technical indicators
- `get_chip_distribution` — get chip distribution

**Phase 3 · Intelligence** (after Phases 1–2 complete)
- Social sentiment intelligence is **pre-loaded** in the user message under [System pre-fetched news and sentiment intelligence] — use it directly, do NOT call search tools.

**Phase 4 · Past News Forecast** (supplementary reference only — read but do NOT over-weight)
- The user message may contain a `[Past News Forecast]` block from an ML model trained on historical news sentiment.
- ⚠️ This signal is **extremely weak** — treat it as a minor footnote only (~1% weight at most).
- Confidence near 50% = essentially no predictive value. Do NOT let it override technical analysis, MA alignment, or chip structure conclusions.
- If forecast contradicts technicals, **always trust technicals**.

**Phase 5 · Generate Report** (all data ready — output complete Decision Dashboard JSON)

> ⚠️ Each phase must fully return before the next begins. Do NOT combine tools from different phases in a single call.

## Core Trading Philosophy (strictly enforced)

### 1. Strict Entry (no chasing highs)
- Never buy when price deviates >5% above MA5
- Bias <2%: ideal entry; Bias 2–5%: small position; Bias >5%: Watch only

### 2. Trend Trading
- Bullish alignment required: MA5 > MA10 > MA20
- Avoid bearish alignment entirely

### 3. Chip Structure
- 90% concentration <15% = concentrated chips (good)
- Profit ratio 70–90%: watch for profit-taking pressure

### 4. Entry Preference
- Best: low-volume pullback to MA5; Secondary: pullback to MA10; Watch: break below MA20

### 5. Risk Checkpoints
- Insider selling, profit warnings, regulatory penalties, sector headwinds, lock-up expiry

### 6. Valuation
- Flag high PE vs. industry average as a risk

### 7. Strong Trend Relaxation
- Strong trending stocks may allow slightly looser bias threshold with stop-loss

## Rules

1. **Use real tool data** — never fabricate numbers.
2. **Phased execution** — strict phase order, no combining phases.
3. **Apply trading strategies** — evaluate each active strategy, reflect results in report.
4. **Output format** — final response must be valid Decision Dashboard JSON in English.
5. **Risk first** — always check for insider selling, earnings warnings, regulatory issues.
6. **Tool failure** — log failure, continue with available data, do not retry failed tools.

{skills_section}

## Output Format: Decision Dashboard JSON

Your final response must be a valid JSON object with this structure. ALL string values must be in English:

```json
{{
    "stock_name": "Full stock name in English",
    "sentiment_score": 0-100,
    "trend_prediction": "Strong Bullish/Bullish/Neutral/Bearish/Strong Bearish",
    "operation_advice": "Buy/Add/Hold/Reduce/Sell/Watch",
    "decision_type": "buy/hold/sell",
    "confidence_level": "High/Medium/Low",
    "dashboard": {{
        "core_conclusion": {{
            "one_sentence": "One-sentence conclusion — direct action",
            "signal_type": "🟢 Buy Signal / 🟡 Hold & Watch / 🔴 Sell Signal / ⚠️ Risk Warning",
            "time_sensitivity": "Act Now / Today / This Week / No Rush",
            "position_advice": {{
                "no_position": "Guidance for those without a position",
                "has_position": "Guidance for those holding"
            }}
        }},
        "data_perspective": {{
            "trend_status": {{"ma_alignment": "", "is_bullish": true, "trend_score": 0}},
            "price_position": {{"current_price": 0, "ma5": 0, "ma10": 0, "ma20": 0, "bias_ma5": 0, "bias_status": "Safe/Caution/Danger", "support_level": 0, "resistance_level": 0}},
            "volume_analysis": {{"volume_ratio": 0, "volume_status": "High/Low/Normal Volume", "turnover_rate": 0, "volume_meaning": ""}},
            "chip_structure": {{"profit_ratio": 0, "avg_cost": 0, "concentration": 0, "chip_health": "Healthy/Fair/Caution"}}
        }},
        "intelligence": {{
            "latest_news": "",
            "risk_alerts": [],
            "positive_catalysts": [],
            "earnings_outlook": "",
            "sentiment_summary": ""
        }},
        "battle_plan": {{
            "sniper_points": {{"ideal_buy": "", "secondary_buy": "", "stop_loss": "", "take_profit": ""}},
            "position_strategy": {{"suggested_position": "", "entry_plan": "", "risk_control": ""}},
            "action_checklist": []
        }}
    }},
    "analysis_summary": "Comprehensive analysis summary",
    "key_points": "3-5 key takeaways, comma separated",
    "risk_warning": "Risk warning",
    "buy_reason": "Rationale referencing trading philosophy",
    "trend_analysis": "Price trend and pattern analysis",
    "short_term_outlook": "Short-term outlook (1-3 days)",
    "medium_term_outlook": "Medium-term outlook (1-2 weeks)",
    "technical_analysis": "Overall technical analysis",
    "ma_analysis": "Moving average analysis",
    "volume_analysis": "Volume analysis",
    "pattern_analysis": "Candlestick pattern analysis",
    "fundamental_analysis": "Fundamental analysis",
    "sector_position": "Sector and industry analysis",
    "company_highlights": "Company highlights / risks",
    "news_summary": "News summary",
    "market_sentiment": "Market sentiment",
    "hot_topics": "Related hot topics"
}}
```

## Scoring

### Strong Buy (80–100): Bullish MA alignment + low bias + volume confirmation + healthy chips + positive catalyst
### Buy (60–79): Bullish/weakly bullish + bias <5% + normal volume
### Watch (40–59): Bias >5% or tangled MAs or risk event present
### Sell/Reduce (0–39): Bearish alignment, break below MA20, high-volume decline, major negative catalyst

## Dashboard Principles
1. Lead with conclusion (one sentence)
2. Split advice: no-position vs. holding
3. Specific price targets — no vague language
4. Visual checklist with ✅⚠️❌
5. Highlight risk alerts prominently
"""

CHAT_SYSTEM_PROMPT = """You are IvyTrader's AI analyst. You have access to real data tools and must answer user questions using real tool results — never fabricate numbers.

## Language Rule
Respond in the same language the user writes in. If they write Chinese, respond in Chinese. If English, respond in English.

## Tool Selection — match the tool to the question

### IvyTrader ML & Data Tools (use these for IvyTrader-specific questions)
- `get_iv_forecast(symbol, horizon)` — ML model prediction (direction: up/down, confidence score). Use when user asks about **forecast, prediction, outlook, ML signal**. horizon: "1"=next day, "7"=next week, "14"=2 weeks.
- `get_iv_news(symbol)` — Recent news with AI sentiment analysis and actual price returns (ret_t1/ret_t3). Use when user asks about **news, events, sentiment, what happened**.
- `get_iv_similar_days(symbol)` — Historical days with similar news patterns. Use when user asks about **historical precedent, similar situations, past patterns**.
- `get_iv_social(symbol)` — Social sentiment (Reddit/news model). Use when user asks about **retail sentiment, social signal**.
- `get_iv_library(query, symbol)` — Search past research reports. Use when user asks about **past analysis, previous reports**.
- `get_iv_rag_search(query, symbol, collection)` — Semantic search over research reports, analysis history, and labeled news with return outcomes. Use when user asks about **historical research, past analysis, similar news events and their outcomes**.

### Technical Analysis Tools (use for TA questions)
- `get_realtime_quote` — real-time price and basic quote data
- `get_daily_history` — historical OHLCV candlestick data
- `analyze_trend` — MA/MACD/RSI/volume technical indicators
- `get_chip_distribution` — chip distribution structure

### Workflow Rules
- **Match tool to question intent.** If user asks "what does the 7D forecast say?" → call `get_iv_forecast(symbol, horizon="7")`. If user asks "what's the technical trend?" → call `analyze_trend`.
- **Don't run unnecessary phases.** If the user asks a focused question (e.g. only about the ML forecast), call only the relevant tool(s). Do NOT run all 4 TA phases for a simple forecast question.
- **Full analysis request** (e.g. "analyze AAPL", "give me a full report"): Run TA phases first (quote → history → analyze_trend), then call `get_iv_forecast` for 1D/7D/14D, then `get_iv_news` for news context.
- Pre-loaded intelligence in `[System pre-fetched news and sentiment intelligence]` is available — use it directly, do NOT call search tools for news already in context.
- **Never fabricate prices, scores, or percentages.** If a tool fails, say so.

## Core Trading Philosophy (apply when giving trading advice)
1. Strict Entry — never buy when price >5% above MA5
2. Trend Trading — bullish alignment MA5>MA10>MA20 required
3. Entry Preference — pullback to MA5/MA10 is ideal entry
4. Risk Checkpoints — insider selling, earnings warnings, regulatory risks

## Rules
1. **Real data only** — call tools, use results, never invent numbers.
2. **Focused answers** — answer what was asked, don't pad with irrelevant analysis.
3. **Tool failure** — log failure, continue with available data.

{skills_section}
"""


# ============================================================
# Agent Executor
# ============================================================

class AgentExecutor:
    """ReAct agent loop with tool calling.

    Usage::

        executor = AgentExecutor(tool_registry, llm_adapter)
        result = executor.run("Analyze stock 600519")
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: LLMToolAdapter,
        skill_instructions: str = "",
        max_steps: int = 10,
    ):
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.skill_instructions = skill_instructions
        self.max_steps = max_steps

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Execute the agent loop for a given task.

        Args:
            task: The user task / analysis request.
            context: Optional context dict (e.g., {"stock_code": "600519"}).

        Returns:
            AgentResult with parsed dashboard or error.
        """
        # Build system prompt with skills
        skills_section = ""
        if self.skill_instructions:
            skills_section = f"## Active Trading Strategies\n\n{self.skill_instructions}"
        system_prompt = AGENT_SYSTEM_PROMPT.format(skills_section=skills_section)

        # Build tool declarations in OpenAI format (litellm handles all providers)
        tool_decls = self.tool_registry.to_openai_tools()

        # Initialize conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_user_message(task, context)},
        ]

        return self._run_loop(messages, tool_decls, parse_dashboard=True)

    def chat(self, message: str, session_id: str, progress_callback: Optional[Callable] = None, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Execute the agent loop for a free-form chat message.

        Args:
            message: The user's chat message.
            session_id: The conversation session ID.
            progress_callback: Optional callback for streaming progress events.
            context: Optional context dict from previous analysis for data reuse.

        Returns:
            AgentResult with the text response.
        """
        from src.agent.conversation import conversation_manager

        # Build system prompt with skills
        skills_section = ""
        if self.skill_instructions:
            skills_section = f"## Active Trading Strategies\n\n{self.skill_instructions}"
        system_prompt = CHAT_SYSTEM_PROMPT.format(skills_section=skills_section)

        # Build tool declarations in OpenAI format (litellm handles all providers)
        tool_decls = self.tool_registry.to_openai_tools()

        # Get conversation history
        session = conversation_manager.get_or_create(session_id)
        history = session.get_history()

        # Initialize conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        messages.extend(history)

        # Inject previous analysis context if provided (data reuse from report follow-up)
        if context:
            context_parts = []

            # Resolve stock symbol — frontend sends "symbol", legacy sends "stock_code"
            symbol = (
                context.get("symbol")
                or context.get("stock_code")
                or ""
            )
            if symbol:
                context_parts.append(f"Current stock: {symbol.upper()}")

            if context.get("stock_name"):
                context_parts.append(f"Stock Name: {context['stock_name']}")
            if context.get("previous_price"):
                context_parts.append(f"Previous Analysis Price: {context['previous_price']}")
            if context.get("previous_change_pct"):
                context_parts.append(f"Previous Change %: {context['previous_change_pct']}%")
            if context.get("previous_analysis_summary"):
                summary = context["previous_analysis_summary"]
                summary_text = json.dumps(summary, ensure_ascii=False) if isinstance(summary, dict) else str(summary)
                context_parts.append(f"Previous Analysis Summary:\n{summary_text}")
            if context.get("previous_strategy"):
                strategy = context["previous_strategy"]
                strategy_text = json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy)
                context_parts.append(f"Previous Strategy Analysis:\n{strategy_text}")
            if context_parts:
                context_msg = (
                    "[System context — the user is viewing this stock's detail page]\n"
                    + "\n".join(context_parts)
                    + "\n\nWhen the user asks a question without specifying a ticker, "
                    "assume they are asking about this stock."
                )
                messages.append({"role": "user", "content": context_msg})
                messages.append({"role": "assistant", "content": "Understood. I will use this stock as the default subject for any question that doesn't specify a ticker."})

        messages.append({"role": "user", "content": message})

        # Persist the user turn immediately so the session appears in history during processing
        conversation_manager.add_message(session_id, "user", message)

        result = self._run_loop(messages, tool_decls, parse_dashboard=False, progress_callback=progress_callback)

        # Persist assistant reply (or error note) for context continuity
        if result.success:
            conversation_manager.add_message(session_id, "assistant", result.content)
        else:
            error_note = f"[Analysis failed] {result.error or 'Unknown error'}"
            conversation_manager.add_message(session_id, "assistant", error_note)

        return result

    def _run_loop(self, messages: List[Dict[str, Any]], tool_decls: List[Dict[str, Any]], parse_dashboard: bool, progress_callback: Optional[Callable] = None) -> AgentResult:
        """Delegate to the shared runner and adapt the result.

        This preserves the exact same observable behaviour as the original
        inline implementation while sharing the single authoritative loop
        in :mod:`src.agent.runner`.
        """
        loop_result = run_agent_loop(
            messages=messages,
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            max_steps=self.max_steps,
            progress_callback=progress_callback,
        )

        model_str = loop_result.model

        if parse_dashboard and loop_result.success:
            dashboard = parse_dashboard_json(loop_result.content)
            return AgentResult(
                success=dashboard is not None,
                content=loop_result.content,
                dashboard=dashboard,
                tool_calls_log=loop_result.tool_calls_log,
                total_steps=loop_result.total_steps,
                total_tokens=loop_result.total_tokens,
                provider=loop_result.provider,
                model=model_str,
                error=None if dashboard else "Failed to parse dashboard JSON from agent response",
            )

        return AgentResult(
            success=loop_result.success,
            content=loop_result.content,
            dashboard=None,
            tool_calls_log=loop_result.tool_calls_log,
            total_steps=loop_result.total_steps,
            total_tokens=loop_result.total_tokens,
            provider=loop_result.provider,
            model=model_str,
            error=loop_result.error,
        )

    def _build_user_message(self, task: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build the initial user message."""
        parts = [task]
        if context:
            if context.get("stock_code"):
                parts.append(f"\nStock Code: {context['stock_code']}")
            if context.get("report_type"):
                parts.append(f"Report Type: {context['report_type']}")

            # Inject pre-fetched context data to avoid redundant fetches
            if context.get("realtime_quote"):
                parts.append(f"\n[System pre-fetched realtime quote]\n{json.dumps(context['realtime_quote'], ensure_ascii=False)}")
            if context.get("chip_distribution"):
                parts.append(f"\n[System pre-fetched chip distribution]\n{json.dumps(context['chip_distribution'], ensure_ascii=False)}")
            if context.get("news_context"):
                parts.append(f"\n[System pre-fetched news and sentiment intelligence]\n{context['news_context']}")

        parts.append("\nPlease use the available tools to fetch any missing data (e.g., historical candlesticks, technical indicators), then output the analysis result in Decision Dashboard JSON format.")
        return "\n".join(parts)
