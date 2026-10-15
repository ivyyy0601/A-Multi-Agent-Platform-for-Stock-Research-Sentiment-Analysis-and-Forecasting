# -*- coding: utf-8 -*-
"""
IntelAgent — news & intelligence gathering specialist.

Responsible for:
- Searching latest stock news and announcements
- Running comprehensive intelligence search
- Detecting risk events (reduce holdings, earnings warnings, regulatory)
- Summarising sentiment and catalysts
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class IntelAgent(BaseAgent):
    agent_name = "intel"
    max_steps = 4
    tool_names = [
        "get_stock_info",
    ]

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
You are an **Intelligence & Sentiment Agent** specialising in US equities.

Your task: analyse the social sentiment data already provided in the context \
(Reddit / X / News via Adanos API, 3-day window) and produce a structured JSON opinion.
Do NOT search the web — all intelligence is pre-loaded in the context under news_context.

## Workflow
1. Read the news_context (Reddit, X, News sentiment data) from the provided context
2. Classify positive catalysts and risk alerts from that data
3. Assess overall sentiment direction

## ML Forecast Signals (in news_context — low weight)
The news_context may contain two ML forecast blocks:
- `[Past News Forecast]`: XGBoost trained on historical news sentiment — very low predictive weight
- `[Social Sentiment Forecast]`: Logistic Regression + similarity on 51 social features — supplementary only
Rules:
- Only factor these in if confidence > 65% AND they align with the social posts
- Confidence near 50% = no signal — ignore entirely
- Never let ML forecasts override your primary signal derived from actual news/social posts
- Treat them as a weak tiebreaker at most (~10% of your final confidence)

## Risk Detection Priorities
- Insider / major shareholder sell-downs
- Earnings warnings or pre-loss announcements
- Regulatory penalties or investigations
- Industry-wide policy headwinds
- PE valuation anomalies

## Output Format
Return **only** a JSON object:
{
  "signal": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentence summary based on the provided social sentiment data",
  "risk_alerts": ["list", "of", "detected", "risks"],
  "positive_catalysts": ["list", "of", "catalysts"],
  "sentiment_label": "very_positive|positive|neutral|negative|very_negative",
  "key_news": [
    {"title": "...", "impact": "positive|negative|neutral"}
  ]
}
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        parts = [f"Gather intelligence and assess sentiment for stock **{ctx.stock_code}**"]
        if ctx.stock_name:
            parts[0] += f" ({ctx.stock_name})"
        parts.append("Read the news_context in the provided context (Adanos Reddit/X/News data) and output the JSON opinion.")
        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[IntelAgent] failed to parse opinion JSON")
            return None

        # Cache parsed intel so downstream agents (especially RiskAgent) can
        # reuse it instead of re-searching the same evidence.
        ctx.set_data("intel_opinion", parsed)

        # Propagate risk alerts to context
        for alert in parsed.get("risk_alerts", []):
            if isinstance(alert, str) and alert:
                ctx.add_risk_flag(category="intel", description=alert)

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=parsed.get("signal", "hold"),
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=parsed.get("reasoning", ""),
            raw_data=parsed,
        )


