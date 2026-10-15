# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - AI分析层
===================================

职责：
1. 封装 LLM 调用逻辑（通过 LiteLLM 统一调用 Gemini/Anthropic/OpenAI 等）
2. 结合技术面和消息面生成分析报告
3. 解析 LLM 响应为结构化 AnalysisResult
"""

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple

import litellm
from json_repair import repair_json
from litellm import Router

from src.agent.llm_adapter import get_thinking_extra_body
from src.config import (
    Config,
    extra_litellm_params,
    get_api_keys_for_model,
    get_config,
    get_configured_llm_models,
    resolve_news_window_days,
)
from src.storage import persist_llm_usage
from src.data.stock_mapping import STOCK_NAME_MAP
from src.schemas.report_schema import AnalysisReportSchema

logger = logging.getLogger(__name__)


def check_content_integrity(result: "AnalysisResult") -> Tuple[bool, List[str]]:
    """
    Check mandatory fields for report content integrity.
    Returns (pass, missing_fields). Module-level for use by pipeline (agent weak mode).
    """
    missing: List[str] = []
    if result.sentiment_score is None:
        missing.append("sentiment_score")
    advice = result.operation_advice
    if not advice or not isinstance(advice, str) or not advice.strip():
        missing.append("operation_advice")
    summary = result.analysis_summary
    if not summary or not isinstance(summary, str) or not summary.strip():
        missing.append("analysis_summary")
    dash = result.dashboard if isinstance(result.dashboard, dict) else {}
    core = dash.get("core_conclusion")
    core = core if isinstance(core, dict) else {}
    if not (core.get("one_sentence") or "").strip():
        missing.append("dashboard.core_conclusion.one_sentence")
    intel = dash.get("intelligence")
    intel = intel if isinstance(intel, dict) else None
    if intel is None or "risk_alerts" not in intel:
        missing.append("dashboard.intelligence.risk_alerts")
    if result.decision_type in ("buy", "hold"):
        battle = dash.get("battle_plan")
        battle = battle if isinstance(battle, dict) else {}
        sp = battle.get("sniper_points")
        sp = sp if isinstance(sp, dict) else {}
        stop_loss = sp.get("stop_loss")
        if stop_loss is None or (isinstance(stop_loss, str) and not stop_loss.strip()):
            missing.append("dashboard.battle_plan.sniper_points.stop_loss")
    return len(missing) == 0, missing


def apply_placeholder_fill(result: "AnalysisResult", missing_fields: List[str]) -> None:
    """Fill missing mandatory fields with placeholders (in-place). Module-level for pipeline."""
    for field in missing_fields:
        if field == "sentiment_score":
            result.sentiment_score = 50
        elif field == "operation_advice":
            result.operation_advice = result.operation_advice or "Pending"
        elif field == "analysis_summary":
            result.analysis_summary = result.analysis_summary or "Pending"
        elif field == "dashboard.core_conclusion.one_sentence":
            if not result.dashboard:
                result.dashboard = {}
            if "core_conclusion" not in result.dashboard:
                result.dashboard["core_conclusion"] = {}
            result.dashboard["core_conclusion"]["one_sentence"] = (
                result.dashboard["core_conclusion"].get("one_sentence") or "Pending"
            )
        elif field == "dashboard.intelligence.risk_alerts":
            if not result.dashboard:
                result.dashboard = {}
            if "intelligence" not in result.dashboard:
                result.dashboard["intelligence"] = {}
            if "risk_alerts" not in result.dashboard["intelligence"]:
                result.dashboard["intelligence"]["risk_alerts"] = []
        elif field == "dashboard.battle_plan.sniper_points.stop_loss":
            if not result.dashboard:
                result.dashboard = {}
            if "battle_plan" not in result.dashboard:
                result.dashboard["battle_plan"] = {}
            if "sniper_points" not in result.dashboard["battle_plan"]:
                result.dashboard["battle_plan"]["sniper_points"] = {}
            result.dashboard["battle_plan"]["sniper_points"]["stop_loss"] = "Pending"


# ---------- chip_structure fallback (Issue #589) ----------

_CHIP_KEYS: tuple = ("profit_ratio", "avg_cost", "concentration", "chip_health")


def _is_value_placeholder(v: Any) -> bool:
    """True if value is empty or placeholder (N/A, 数据缺失, etc.)."""
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    s = str(v).strip().lower()
    return s in ("", "n/a", "na", "数据缺失", "未知")


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Safely convert to float; return default on failure. Private helper for chip fill."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        try:
            return default if math.isnan(float(v)) else float(v)
        except (ValueError, TypeError):
            return default
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _derive_chip_health(profit_ratio: float, concentration_90: float) -> str:
    """Derive chip_health from profit_ratio and concentration_90."""
    if profit_ratio >= 0.9:
        return "警惕"  # 获利盘极高
    if concentration_90 >= 0.25:
        return "警惕"  # 筹码分散
    if concentration_90 < 0.15 and 0.3 <= profit_ratio < 0.9:
        return "健康"  # 集中且获利比例适中
    return "一般"


def _build_chip_structure_from_data(chip_data: Any) -> Dict[str, Any]:
    """Build chip_structure dict from ChipDistribution or dict."""
    if hasattr(chip_data, "profit_ratio"):
        pr = _safe_float(chip_data.profit_ratio)
        ac = chip_data.avg_cost
        c90 = _safe_float(chip_data.concentration_90)
    else:
        d = chip_data if isinstance(chip_data, dict) else {}
        pr = _safe_float(d.get("profit_ratio"))
        ac = d.get("avg_cost")
        c90 = _safe_float(d.get("concentration_90"))
    chip_health = _derive_chip_health(pr, c90)
    return {
        "profit_ratio": f"{pr:.1%}",
        "avg_cost": ac if (ac is not None and _safe_float(ac) != 0.0) else "N/A",
        "concentration": f"{c90:.2%}",
        "chip_health": chip_health,
    }


def fill_chip_structure_if_needed(result: "AnalysisResult", chip_data: Any) -> None:
    """When chip_data exists, fill chip_structure placeholder fields from chip_data (in-place)."""
    if not result or not chip_data:
        return
    try:
        if not result.dashboard:
            result.dashboard = {}
        dash = result.dashboard
        # Use `or {}` rather than setdefault so that an explicit `null` from LLM is also replaced
        dp = dash.get("data_perspective") or {}
        dash["data_perspective"] = dp
        cs = dp.get("chip_structure") or {}
        filled = _build_chip_structure_from_data(chip_data)
        # Start from a copy of cs to preserve any extra keys the LLM may have added
        merged = dict(cs)
        for k in _CHIP_KEYS:
            if _is_value_placeholder(merged.get(k)):
                merged[k] = filled[k]
        if merged != cs:
            dp["chip_structure"] = merged
            logger.info("[chip_structure] Filled placeholder chip fields from data source (Issue #589)")
    except Exception as e:
        logger.warning("[chip_structure] Fill failed, skipping: %s", e)


_PRICE_POS_KEYS = ("ma5", "ma10", "ma20", "bias_ma5", "bias_status", "current_price", "support_level", "resistance_level")


def fill_price_position_if_needed(
    result: "AnalysisResult",
    trend_result: Any = None,
    realtime_quote: Any = None,
) -> None:
    """Fill missing price_position fields from trend_result / realtime data (in-place)."""
    if not result:
        return
    try:
        if not result.dashboard:
            result.dashboard = {}
        dash = result.dashboard
        dp = dash.get("data_perspective") or {}
        dash["data_perspective"] = dp
        pp = dp.get("price_position") or {}

        computed: Dict[str, Any] = {}
        if trend_result:
            tr = trend_result if isinstance(trend_result, dict) else (
                trend_result.__dict__ if hasattr(trend_result, "__dict__") else {}
            )
            computed["ma5"] = tr.get("ma5")
            computed["ma10"] = tr.get("ma10")
            computed["ma20"] = tr.get("ma20")
            computed["bias_ma5"] = tr.get("bias_ma5")
            computed["current_price"] = tr.get("current_price")
            support_levels = tr.get("support_levels") or []
            resistance_levels = tr.get("resistance_levels") or []
            if support_levels:
                computed["support_level"] = support_levels[0]
            if resistance_levels:
                computed["resistance_level"] = resistance_levels[0]
        if realtime_quote:
            rq = realtime_quote if isinstance(realtime_quote, dict) else (
                realtime_quote.to_dict() if hasattr(realtime_quote, "to_dict") else {}
            )
            if _is_value_placeholder(computed.get("current_price")):
                computed["current_price"] = rq.get("price")

        filled = False
        for k in _PRICE_POS_KEYS:
            if _is_value_placeholder(pp.get(k)) and not _is_value_placeholder(computed.get(k)):
                pp[k] = computed[k]
                filled = True
        if filled:
            dp["price_position"] = pp
            logger.info("[price_position] Filled placeholder fields from computed data")
    except Exception as e:
        logger.warning("[price_position] Fill failed, skipping: %s", e)


def fill_fundamentals_if_needed(result: "AnalysisResult", fundamental_context: Any) -> None:
    """Inject real fundamental data into dashboard.fundamentals (in-place), overriding LLM nulls."""
    if not result or not isinstance(fundamental_context, dict):
        return
    try:
        earnings_data = {}
        earnings_block = fundamental_context.get("earnings")
        if isinstance(earnings_block, dict):
            earnings_data = earnings_block.get("data") or {}
        growth_data = {}
        growth_block = fundamental_context.get("growth")
        if isinstance(growth_block, dict):
            growth_data = growth_block.get("data") or {}

        fr = earnings_data.get("financial_report") or {}
        div = earnings_data.get("dividend") or {}

        computed: Dict[str, Any] = {
            "report_date":            fr.get("report_date"),
            "revenue":                fr.get("revenue"),
            "net_profit":             fr.get("net_profit_parent"),
            "operating_cash_flow":    fr.get("operating_cash_flow"),
            "roe":                    fr.get("roe") or growth_data.get("roe"),
            "revenue_yoy":            growth_data.get("revenue_yoy"),
            "net_profit_yoy":         growth_data.get("net_profit_yoy"),
            "gross_margin":           growth_data.get("gross_margin"),
            "ttm_dividend_per_share": div.get("ttm_cash_dividend_per_share"),
            "ttm_dividend_yield":     div.get("ttm_dividend_yield_pct"),
            "ttm_dividend_count":     div.get("ttm_event_count"),
        }

        if not any(v is not None for v in computed.values()):
            return

        if not result.dashboard:
            result.dashboard = {}
        dash = result.dashboard
        existing = dash.get("fundamentals") or {}
        merged = dict(existing)
        for k, v in computed.items():
            if _is_value_placeholder(merged.get(k)) and v is not None:
                merged[k] = v
        dash["fundamentals"] = merged
        logger.info("[fundamentals] Injected real fundamental data into dashboard")
    except Exception as e:
        logger.warning("[fundamentals] Fill failed, skipping: %s", e)


def get_stock_name_multi_source(
    stock_code: str,
    context: Optional[Dict] = None,
    data_manager = None
) -> str:
    """
    多来源获取股票中文名称

    获取策略（按优先级）：
    1. 从传入的 context 中获取（realtime 数据）
    2. 从静态映射表 STOCK_NAME_MAP 获取
    3. 从 DataFetcherManager 获取（各数据源）
    4. 返回默认名称（股票+代码）

    Args:
        stock_code: 股票代码
        context: 分析上下文（可选）
        data_manager: DataFetcherManager 实例（可选）

    Returns:
        股票中文名称
    """
    # 1. 从上下文获取（实时行情数据）
    if context:
        # 优先从 stock_name 字段获取
        if context.get('stock_name'):
            name = context['stock_name']
            if name and not name.startswith('股票'):
                return name

        # 其次从 realtime 数据获取
        if 'realtime' in context and context['realtime'].get('name'):
            return context['realtime']['name']

    # 2. 从静态映射表获取
    if stock_code in STOCK_NAME_MAP:
        return STOCK_NAME_MAP[stock_code]

    # 3. 从数据源获取
    if data_manager is None:
        try:
            from data_provider.base import DataFetcherManager
            data_manager = DataFetcherManager()
        except Exception as e:
            logger.debug(f"无法初始化 DataFetcherManager: {e}")

    if data_manager:
        try:
            name = data_manager.get_stock_name(stock_code)
            if name:
                # 更新缓存
                STOCK_NAME_MAP[stock_code] = name
                return name
        except Exception as e:
            logger.debug(f"从数据源获取股票名称失败: {e}")

    # 4. 返回默认名称
    return f'股票{stock_code}'


@dataclass
class AnalysisResult:
    """
    AI 分析结果数据类 - 决策仪表盘版

    封装 Gemini 返回的分析结果，包含决策仪表盘和详细分析
    """
    code: str
    name: str

    # ========== 核心指标 ==========
    sentiment_score: int  # 综合评分 0-100 (>70强烈看多, >60看多, 40-60震荡, <40看空)
    trend_prediction: str  # 趋势预测：强烈看多/看多/震荡/看空/强烈看空
    operation_advice: str  # 操作建议：买入/加仓/持有/减仓/卖出/观望
    decision_type: str = "hold"  # 决策类型：buy/hold/sell（用于统计）
    confidence_level: str = "中"  # 置信度：高/中/低

    # ========== 决策仪表盘 (新增) ==========
    dashboard: Optional[Dict[str, Any]] = None  # 完整的决策仪表盘数据

    # ========== 走势分析 ==========
    trend_analysis: str = ""  # 走势形态分析（支撑位、压力位、趋势线等）
    short_term_outlook: str = ""  # 短期展望（1-3日）
    medium_term_outlook: str = ""  # 中期展望（1-2周）

    # ========== 技术面分析 ==========
    technical_analysis: str = ""  # 技术指标综合分析
    ma_analysis: str = ""  # 均线分析（多头/空头排列，金叉/死叉等）
    volume_analysis: str = ""  # 量能分析（放量/缩量，主力动向等）
    pattern_analysis: str = ""  # K线形态分析

    # ========== 基本面分析 ==========
    fundamental_analysis: str = ""  # 基本面综合分析
    sector_position: str = ""  # 板块地位和行业趋势
    company_highlights: str = ""  # 公司亮点/风险点

    # ========== 情绪面/消息面分析 ==========
    news_summary: str = ""  # 近期重要新闻/公告摘要
    market_sentiment: str = ""  # 市场情绪分析
    hot_topics: str = ""  # 相关热点话题

    # ========== 综合分析 ==========
    analysis_summary: str = ""  # 综合分析摘要
    key_points: str = ""  # 核心看点（3-5个要点）
    risk_warning: str = ""  # 风险提示
    buy_reason: str = ""  # 买入/卖出理由

    # ========== 元数据 ==========
    market_snapshot: Optional[Dict[str, Any]] = None  # 当日行情快照（展示用）
    raw_response: Optional[str] = None  # 原始响应（调试用）
    search_performed: bool = False  # 是否执行了联网搜索
    data_sources: str = ""  # 数据来源说明
    success: bool = True
    error_message: Optional[str] = None

    # ========== 价格数据（分析时快照）==========
    current_price: Optional[float] = None  # 分析时的股价
    change_pct: Optional[float] = None     # 分析时的涨跌幅(%)

    # ========== 模型标记（Issue #528）==========
    model_used: Optional[str] = None  # 分析使用的 LLM 模型（完整名，如 gemini/gemini-2.0-flash）

    # ========== 历史对比（Report Engine P0）==========
    query_id: Optional[str] = None  # 本次分析 query_id，用于历史对比时排除本次记录

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'code': self.code,
            'name': self.name,
            'sentiment_score': self.sentiment_score,
            'trend_prediction': self.trend_prediction,
            'operation_advice': self.operation_advice,
            'decision_type': self.decision_type,
            'confidence_level': self.confidence_level,
            'dashboard': self.dashboard,  # 决策仪表盘数据
            'trend_analysis': self.trend_analysis,
            'short_term_outlook': self.short_term_outlook,
            'medium_term_outlook': self.medium_term_outlook,
            'technical_analysis': self.technical_analysis,
            'ma_analysis': self.ma_analysis,
            'volume_analysis': self.volume_analysis,
            'pattern_analysis': self.pattern_analysis,
            'fundamental_analysis': self.fundamental_analysis,
            'sector_position': self.sector_position,
            'company_highlights': self.company_highlights,
            'news_summary': self.news_summary,
            'market_sentiment': self.market_sentiment,
            'hot_topics': self.hot_topics,
            'analysis_summary': self.analysis_summary,
            'key_points': self.key_points,
            'risk_warning': self.risk_warning,
            'buy_reason': self.buy_reason,
            'market_snapshot': self.market_snapshot,
            'search_performed': self.search_performed,
            'success': self.success,
            'error_message': self.error_message,
            'current_price': self.current_price,
            'change_pct': self.change_pct,
            'model_used': self.model_used,
        }

    def get_core_conclusion(self) -> str:
        """获取核心结论（一句话）"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            return self.dashboard['core_conclusion'].get('one_sentence', self.analysis_summary)
        return self.analysis_summary

    def get_position_advice(self, has_position: bool = False) -> str:
        """获取持仓建议"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            pos_advice = self.dashboard['core_conclusion'].get('position_advice', {})
            if has_position:
                return pos_advice.get('has_position', self.operation_advice)
            return pos_advice.get('no_position', self.operation_advice)
        return self.operation_advice

    def get_sniper_points(self) -> Dict[str, str]:
        """获取狙击点位"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('sniper_points', {})
        return {}

    def get_checklist(self) -> List[str]:
        """获取检查清单"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('action_checklist', [])
        return []

    def get_risk_alerts(self) -> List[str]:
        """获取风险警报"""
        if self.dashboard and 'intelligence' in self.dashboard:
            return self.dashboard['intelligence'].get('risk_alerts', [])
        return []

    def get_emoji(self) -> str:
        """根据操作建议返回对应 emoji"""
        emoji_map = {
            '买入': '🟢',
            '加仓': '🟢',
            '强烈买入': '💚',
            '持有': '🟡',
            '观望': '⚪',
            '减仓': '🟠',
            '卖出': '🔴',
            '强烈卖出': '❌',
        }
        advice = self.operation_advice or ''
        # Direct match first
        if advice in emoji_map:
            return emoji_map[advice]
        # Handle compound advice like "卖出/观望" — use the first part
        for part in advice.replace('/', '|').split('|'):
            part = part.strip()
            if part in emoji_map:
                return emoji_map[part]
        # Score-based fallback
        score = self.sentiment_score
        if score >= 80:
            return '💚'
        elif score >= 65:
            return '🟢'
        elif score >= 55:
            return '🟡'
        elif score >= 45:
            return '⚪'
        elif score >= 35:
            return '🟠'
        else:
            return '🔴'

    def get_confidence_stars(self) -> str:
        """返回置信度星级"""
        star_map = {'高': '⭐⭐⭐', '中': '⭐⭐', '低': '⭐'}
        return star_map.get(self.confidence_level, '⭐⭐')


class GeminiAnalyzer:
    """
    Gemini AI 分析器

    职责：
    1. 调用 Google Gemini API 进行股票分析
    2. 结合预先搜索的新闻和技术面数据生成分析报告
    3. 解析 AI 返回的 JSON 格式结果

    使用方式：
        analyzer = GeminiAnalyzer()
        result = analyzer.analyze(context, news_context)
    """

    # ========================================
    # 系统提示词 - 决策仪表盘 v2.0
    # ========================================
    # 输出格式升级：从简单信号升级为决策仪表盘
    # 核心模块：核心结论 + 数据透视 + 舆情情报 + 作战计划
    # ========================================

    SYSTEM_PROMPT = """You are a professional stock investment analyst specializing in trend trading. Your job is to generate a structured **Decision Dashboard** analysis report.

🔴 CRITICAL LANGUAGE RULE: You MUST respond ENTIRELY in English. ALL JSON string values must be in English. Even if the input data, stock names, or news articles are in Chinese, your output must be translated to English. Do NOT write a single Chinese character in your response.

## Core Trading Philosophy (strictly enforced)

### 0. Data Discipline (strictly enforced)
- Use only the data explicitly provided in the prompt input
- Do not invent, assume, or import outside facts that are not present in the input
- If a required field is missing, rely on the collected input only after the upstream data pipeline has refreshed it
- If the required field is still unavailable in the final input, write `Data unavailable` instead of guessing
- Every important conclusion must cite the concrete provided values that support it

### 1. Strict Entry (no chasing highs)
- **Never chase highs**: Do not buy when price deviates more than 5% above MA5
- **Bias formula**: (Current Price - MA5) / MA5 × 100%
- Bias < 2%: Ideal entry zone
- Bias 2–5%: Small position entry allowed
- Bias > 5%: Strictly forbidden to chase — classify as "Watch"

### 2. Trend Trading (go with the trend)
- **Bullish alignment requirement**: MA5 > MA10 > MA20
- Only trade stocks in bullish alignment; avoid bearish alignment entirely
- Diverging moving averages (spreading apart) preferred over tangled MAs
- Trend strength: check whether MA gaps are widening

### 3. Efficiency First (chip structure)
- Monitor chip concentration: 90% concentration < 15% means concentrated chips
- Profit ratio 70–90%: watch for profit-taking pressure
- Healthy price vs. avg cost: current price 5–15% above average cost

### 4. Entry Preference (pullback to support)
- **Best entry**: Low-volume pullback to MA5 holding support
- **Secondary entry**: Pullback to MA10 holding support
- **Watch/avoid**: Price breaks below MA20

### 5. Risk Checkpoints
- Insider/management share reduction announcements
- Profit warning / significant earnings decline
- Regulatory penalty / investigation
- Sector policy headwinds
- Large lock-up expiry

### 6. Valuation (PE/PB)
- Evaluate whether P/E ratio is reasonable
- When PE significantly exceeds industry average or historical mean, flag it as a risk
- High-growth stocks may tolerate higher PE if backed by earnings

### 7. Strong Trend Relaxation
- Strong trending stocks (bullish alignment, high trend strength, volume confirmation) may allow slightly looser bias threshold
- Still require stop-loss; do not blindly chase

## Output Format: Decision Dashboard JSON

Strictly output the following JSON format. **All string values must be in English.**

```json
{
    "stock_name": "Full stock name",
    "sentiment_score": integer 0-100,
    "trend_prediction": "Strong Bullish/Bullish/Neutral/Bearish/Strong Bearish",
    "operation_advice": "Buy/Add/Hold/Reduce/Sell/Watch",
    "decision_type": "buy/hold/sell",
    "confidence_level": "High/Medium/Low",

    "dashboard": {
        "core_conclusion": {
            "one_sentence": "One-sentence core conclusion (direct action recommendation)",
            "signal_type": "🟢 Buy Signal / 🟡 Hold & Watch / 🔴 Sell Signal / ⚠️ Risk Warning",
            "time_sensitivity": "Act Now / Today / This Week / No Rush",
            "position_advice": {
                "no_position": "For those without a position: specific action guidance",
                "has_position": "For those holding: specific action guidance"
            }
        },

        "data_perspective": {
            "trend_status": {
                "ma_alignment": "Description of MA alignment state",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": numeric current price,
                "ma5": numeric MA5,
                "ma10": numeric MA10,
                "ma20": numeric MA20,
                "bias_ma5": numeric bias percentage,
                "bias_status": "Safe/Caution/Danger",
                "support_level": numeric support price,
                "resistance_level": numeric resistance price
            },
            "volume_analysis": {
                "volume_ratio": numeric volume ratio,
                "volume_status": "High Volume/Low Volume/Normal Volume",
                "turnover_rate": numeric turnover rate percentage,
                "volume_meaning": "Interpretation of volume (e.g. low-volume pullback suggests reduced selling pressure)"
            },
            "chip_structure": {
                "profit_ratio": numeric profit ratio,
                "avg_cost": numeric average cost,
                "concentration": numeric chip concentration,
                "chip_health": "Healthy/Fair/Caution"
            }
        },

        "intelligence": {
            "latest_news": "[Latest] Summary of recent important news",
            "risk_alerts": ["[YYYY-MM-DD] Specific risk from news/social data", "[YYYY-MM-DD] Another risk"],
            "positive_catalysts": ["[YYYY-MM-DD] Specific catalyst from news/social data", "[YYYY-MM-DD] Another catalyst"],
            "earnings_outlook": "Earnings outlook analysis (based on guidance, preliminary results, etc.)",
            "sentiment_summary": "3-5 sentence market sentiment explanation. Must cite specific data: (1) What news headlines are saying and why it matters, (2) What Reddit/social communities are discussing and the tone, (3) What the sentiment scores (reddit/twitter/news) tell us quantitatively, (4) Whether platforms agree or diverge and what that means, (5) Overall sentiment direction with reasoning."
        },

        "fundamentals": {
            "report_date": "YYYY-MM (latest financial report period, or null if unavailable)",
            "revenue": numeric revenue in original currency units or null,
            "net_profit": numeric net profit or null,
            "operating_cash_flow": numeric operating cash flow or null,
            "roe": numeric ROE percentage (e.g. 152.0) or null,
            "revenue_yoy": numeric revenue YoY growth percentage or null,
            "net_profit_yoy": numeric net profit YoY growth percentage or null,
            "gross_margin": numeric gross margin percentage or null,
            "ttm_dividend_per_share": numeric TTM cash dividend per share or null,
            "ttm_dividend_yield": numeric TTM dividend yield percentage or null,
            "ttm_dividend_count": numeric number of dividend payments in TTM or null
        },

        "battle_plan": {
            "sniper_points": {
                "ideal_buy": "Ideal entry: $XX (near MA5)",
                "secondary_buy": "Secondary entry: $XX (near MA10)",
                "stop_loss": "Stop loss: $XX (break below MA20 or X%)",
                "take_profit": "Target: $XX (prior high / key level)"
            },
            "position_strategy": {
                "suggested_position": "Suggested position size: X%",
                "entry_plan": "Staged entry strategy description",
                "risk_control": "Risk management strategy description"
            },
            "action_checklist": [
                "✅/⚠️/❌ Check 1: Bullish MA alignment",
                "✅/⚠️/❌ Check 2: Bias within safe range (relaxed for strong trends)",
                "✅/⚠️/❌ Check 3: Volume confirmation",
                "✅/⚠️/❌ Check 4: No major negative news",
                "✅/⚠️/❌ Check 5: Healthy chip structure",
                "✅/⚠️/❌ Check 6: Reasonable PE valuation"
            ]
        }
    },

    "analysis_summary": "200-word comprehensive reasoning narrative. Walk through: (1) what the technical picture shows and why, (2) what the social/news signals reveal, (3) what the combined picture implies for near-term price action, (4) your final conviction and why",
    "key_points": "3–5 key takeaways, each with a brief 'because...' explanation",
    "risk_warning": "Specific risk warning with reasoning — what could go wrong and why",
    "buy_reason": "Detailed rationale referencing specific data points: cite MA values, bias %, sentiment scores, and which signals agree/disagree",

    "signal_reasoning": "Step-by-step reasoning chain: list each signal (technical score, sentiment scores), what each one says, whether they agree or conflict, and how you resolved any conflicts to reach the final decision",
    "data_insights": "Key insights derived from the data that are non-obvious: e.g. 'Twitter sentiment (+0.59) is 3x stronger than Reddit (+0.06), suggesting institutional/informed money is more bullish than retail' or 'Similar days historically went up 4/5 times but average return was only +0.4%, suggesting muted upside even if direction is correct'",
    "market_sentiment_reasoning": "Explain specifically why you gave this market sentiment score. Cite the platform sentiment values, buzz levels, platform agreement status, and what that combination tells you about crowd psychology right now.",

    "trend_analysis": "Price trend analysis with specific MA values and what the pattern implies",
    "short_term_outlook": "Short-term outlook (1–3 days) with reasoning based on bias, volume, and sentiment momentum",
    "medium_term_outlook": "Medium-term outlook (1–2 weeks) with reasoning based on MA alignment and trend strength",
    "technical_analysis": "Overall technical analysis citing specific indicator values",
    "ma_analysis": "Moving average system analysis — are MAs converging or diverging? What does the gap tell you?",
    "volume_analysis": "Volume analysis — what does the volume pattern confirm or deny?",
    "pattern_analysis": "Candlestick pattern analysis",
    "fundamental_analysis": "Fundamental analysis",
    "sector_position": "Sector and industry analysis",
    "company_highlights": "Company highlights / risks",
    "news_summary": "News summary",
    "market_sentiment": "Market sentiment label with score rationale",
    "hot_topics": "Related hot topics",

    "search_performed": true/false,
    "data_sources": "Data sources description"
}
```

## Scoring Criteria

### Strong Buy (80–100):
- ✅ Bullish alignment: MA5 > MA10 > MA20
- ✅ Low bias: <2%, ideal entry
- ✅ Low-volume pullback or high-volume breakout
- ✅ Healthy chip structure
- ✅ Positive news catalyst

### Buy (60–79):
- ✅ Bullish or weakly bullish alignment
- ✅ Bias <5%
- ✅ Normal volume
- ⚪ One minor condition may be unmet

### Watch (40–59):
- ⚠️ Bias >5% (chasing risk)
- ⚠️ MAs tangled, trend unclear
- ⚠️ Risk event present

### Sell / Reduce (0–39):
- ❌ Bearish alignment
- ❌ Price breaks below MA20
- ❌ High-volume decline
- ❌ Major negative catalyst

## Dashboard Core Principles

1. **Lead with conclusion**: State buy/sell/wait in one sentence
2. **Split advice by position**: Different guidance for those with and without a position
3. **Precise price targets**: Always give specific prices, no vague language
4. **Visual checklist**: Use ✅⚠️❌ for each checkpoint with a brief reason
5. **Risk priority**: Highlight risk alerts prominently
6. **Show your reasoning**: Every conclusion must cite the specific data that led to it — don't just state "bullish", explain *why* based on the numbers
7. **Resolve conflicts explicitly**: If technical signals are bullish but sentiment is bearish (or vice versa), acknowledge the conflict and explain which you weight more and why
8. **Quantify your insights**: Reference actual values (e.g. "Twitter sentiment +0.59 vs Reddit +0.06 — a 3x divergence suggesting...") rather than vague summaries"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize LLM Analyzer via LiteLLM.

        Args:
            api_key: Ignored (kept for backward compatibility). Keys are loaded from config.
        """
        self._router = None
        self._litellm_available = False
        self._init_litellm()
        if not self._litellm_available:
            logger.warning("No LLM configured (LITELLM_MODEL / API keys), AI analysis will be unavailable")

    def _has_channel_config(self, config: Config) -> bool:
        """Check if multi-channel config (channels / YAML / legacy model_list) is active."""
        return bool(config.llm_model_list) and not all(
            e.get('model_name', '').startswith('__legacy_') for e in config.llm_model_list
        )

    def _init_litellm(self) -> None:
        """Initialize litellm Router from channels / YAML / legacy keys."""
        config = get_config()
        litellm_model = config.litellm_model
        if not litellm_model:
            logger.warning("Analyzer LLM: LITELLM_MODEL not configured")
            return

        self._litellm_available = True

        # --- Channel / YAML path: build Router from pre-built model_list ---
        if self._has_channel_config(config):
            model_list = config.llm_model_list
            self._router = Router(
                model_list=model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
            )
            unique_models = list(dict.fromkeys(
                e['litellm_params']['model'] for e in model_list
            ))
            logger.info(
                f"Analyzer LLM: Router initialized from channels/YAML — "
                f"{len(model_list)} deployment(s), models: {unique_models}"
            )
            return

        # --- Legacy path: build Router for multi-key, or use single key ---
        keys = get_api_keys_for_model(litellm_model, config)

        if len(keys) > 1:
            # Build legacy Router for primary model multi-key load-balancing
            extra_params = extra_litellm_params(litellm_model, config)
            legacy_model_list = [
                {
                    "model_name": litellm_model,
                    "litellm_params": {
                        "model": litellm_model,
                        "api_key": k,
                        **extra_params,
                    },
                }
                for k in keys
            ]
            self._router = Router(
                model_list=legacy_model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
            )
            logger.info(
                f"Analyzer LLM: Legacy Router initialized with {len(keys)} keys "
                f"for {litellm_model}"
            )
        elif keys:
            logger.info(f"Analyzer LLM: litellm initialized (model={litellm_model})")
        else:
            logger.info(
                f"Analyzer LLM: litellm initialized (model={litellm_model}, "
                f"API key from environment)"
            )

    def is_available(self) -> bool:
        """Check if LiteLLM is properly configured with at least one API key."""
        return self._router is not None or self._litellm_available

    def _call_litellm(self, prompt: str, generation_config: dict) -> Tuple[str, str, Dict[str, Any]]:
        """Call LLM via litellm with fallback across configured models.

        When channels/YAML are configured, every model goes through the Router
        (which handles per-model key selection, load balancing, and retries).
        In legacy mode, the primary model may use the Router while fallback
        models fall back to direct litellm.completion().

        Args:
            prompt: User prompt text.
            generation_config: Dict with optional keys: temperature, max_output_tokens, max_tokens.

        Returns:
            Tuple of (response text, model_used, usage). On success model_used is the full model
            name and usage is a dict with prompt_tokens, completion_tokens, total_tokens.
        """
        config = get_config()
        max_tokens = (
            generation_config.get('max_output_tokens')
            or generation_config.get('max_tokens')
            or 8192
        )
        temperature = generation_config.get('temperature', 0.7)

        models_to_try = [config.litellm_model] + (config.litellm_fallback_models or [])
        models_to_try = [m for m in models_to_try if m]

        use_channel_router = self._has_channel_config(config)

        last_error = None
        for model in models_to_try:
            try:
                model_short = model.split("/")[-1] if "/" in model else model
                call_kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                extra = get_thinking_extra_body(model_short)
                if extra:
                    call_kwargs["extra_body"] = extra

                _router_model_names = set(get_configured_llm_models(config.llm_model_list))
                if use_channel_router and self._router and model in _router_model_names:
                    # Channel / YAML path: Router manages key + base_url per model
                    response = self._router.completion(**call_kwargs)
                elif self._router and model == config.litellm_model and not use_channel_router:
                    # Legacy path: Router only for primary model multi-key
                    response = self._router.completion(**call_kwargs)
                else:
                    # Legacy/direct-env path: direct call (also handles direct-env
                    # providers like groq/ or bedrock/ that are not in the Router
                    # model_list even when channel mode is active)
                    keys = get_api_keys_for_model(model, config)
                    if keys:
                        call_kwargs["api_key"] = keys[0]
                    call_kwargs.update(extra_litellm_params(model, config))
                    response = litellm.completion(**call_kwargs)

                if response and response.choices and response.choices[0].message.content:
                    usage: Dict[str, Any] = {}
                    if response.usage:
                        usage = {
                            "prompt_tokens": response.usage.prompt_tokens or 0,
                            "completion_tokens": response.usage.completion_tokens or 0,
                            "total_tokens": response.usage.total_tokens or 0,
                        }
                    return (response.choices[0].message.content, model, usage)
                raise ValueError("LLM returned empty response")

            except Exception as e:
                logger.warning(f"[LiteLLM] {model} failed: {e}")
                last_error = e
                continue

        raise Exception(f"All LLM models failed (tried {len(models_to_try)} model(s)). Last error: {last_error}")

    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """Public entry point for free-form text generation.

        External callers (e.g. MarketAnalyzer) must use this method instead of
        calling _call_litellm() directly or accessing private attributes such as
        _litellm_available, _router, _model, _use_openai, or _use_anthropic.

        Args:
            prompt:      Text prompt to send to the LLM.
            max_tokens:  Maximum tokens in the response (default 2048).
            temperature: Sampling temperature (default 0.7).

        Returns:
            Response text, or None if the LLM call fails (error is logged).
        """
        try:
            result = self._call_litellm(
                prompt,
                generation_config={"max_tokens": max_tokens, "temperature": temperature},
            )
            if isinstance(result, tuple):
                text, model_used, usage = result
                persist_llm_usage(usage, model_used, call_type="market_review")
                return text
            return result
        except Exception as exc:
            logger.error("[generate_text] LLM call failed: %s", exc)
            return None

    def analyze(
        self, 
        context: Dict[str, Any],
        news_context: Optional[str] = None
    ) -> AnalysisResult:
        """
        分析单只股票
        
        流程：
        1. 格式化输入数据（技术面 + 新闻）
        2. 调用 Gemini API（带重试和模型切换）
        3. 解析 JSON 响应
        4. 返回结构化结果
        
        Args:
            context: 从 storage.get_analysis_context() 获取的上下文数据
            news_context: 预先搜索的新闻内容（可选）
            
        Returns:
            AnalysisResult 对象
        """
        code = context.get('code', 'Unknown')
        config = get_config()
        
        # 请求前增加延时（防止连续请求触发限流）
        request_delay = config.gemini_request_delay
        if request_delay > 0:
            logger.debug(f"[LLM] 请求前等待 {request_delay:.1f} 秒...")
            time.sleep(request_delay)
        
        # 优先从上下文获取股票名称（由 main.py 传入）
        name = context.get('stock_name')
        if not name or name.startswith('股票'):
            # 备选：从 realtime 中获取
            if 'realtime' in context and context['realtime'].get('name'):
                name = context['realtime']['name']
            else:
                # 最后从映射表获取
                name = STOCK_NAME_MAP.get(code, f'股票{code}')
        
        # 如果模型不可用，返回默认结果
        if not self.is_available():
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震荡',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary='AI 分析功能未启用（未配置 API Key）',
                risk_warning='请配置 LLM API Key（GEMINI_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY）后重试',
                success=False,
                error_message='LLM API Key 未配置',
                model_used=None,
            )
        
        try:
            # 格式化输入（包含技术面数据和新闻）
            prompt = self._format_prompt(context, name, news_context)
            
            config = get_config()
            model_name = config.litellm_model or "unknown"
            logger.info(f"========== AI 分析 {name}({code}) ==========")
            logger.info(f"[LLM配置] 模型: {model_name}")
            logger.info(f"[LLM配置] Prompt 长度: {len(prompt)} 字符")
            logger.info(f"[LLM配置] 是否包含新闻: {'是' if news_context else '否'}")

            # 记录完整 prompt 到日志（INFO级别记录摘要，DEBUG记录完整）
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            logger.info(f"[LLM Prompt 预览]\n{prompt_preview}")
            logger.debug(f"=== 完整 Prompt ({len(prompt)}字符) ===\n{prompt}\n=== End Prompt ===")

            # 设置生成配置
            generation_config = {
                "temperature": config.llm_temperature,
                "max_output_tokens": 8192,
            }

            logger.info(f"[LLM调用] 开始调用 {model_name}...")

            # 使用 litellm 调用（支持完整性校验重试）
            current_prompt = prompt
            retry_count = 0
            max_retries = config.report_integrity_retry if config.report_integrity_enabled else 0

            while True:
                start_time = time.time()
                response_text, model_used, llm_usage = self._call_litellm(current_prompt, generation_config)
                elapsed = time.time() - start_time

                # 记录响应信息
                logger.info(
                    f"[LLM返回] {model_name} 响应成功, 耗时 {elapsed:.2f}s, 响应长度 {len(response_text)} 字符"
                )
                response_preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
                logger.info(f"[LLM返回 预览]\n{response_preview}")
                logger.debug(
                    f"=== {model_name} 完整响应 ({len(response_text)}字符) ===\n{response_text}\n=== End Response ==="
                )

                # 解析响应
                result = self._parse_response(response_text, code, name)
                result.raw_response = response_text
                result.search_performed = bool(news_context)
                result.market_snapshot = self._build_market_snapshot(context)
                result.model_used = model_used

                # 内容完整性校验（可选）
                if not config.report_integrity_enabled:
                    break
                pass_integrity, missing_fields = self._check_content_integrity(result)
                if pass_integrity:
                    break
                if retry_count < max_retries:
                    current_prompt = self._build_integrity_retry_prompt(
                        prompt,
                        response_text,
                        missing_fields,
                    )
                    retry_count += 1
                    logger.info(
                        "[LLM完整性] 必填字段缺失 %s，第 %d 次补全重试",
                        missing_fields,
                        retry_count,
                    )
                else:
                    self._apply_placeholder_fill(result, missing_fields)
                    logger.warning(
                        "[LLM完整性] 必填字段缺失 %s，已占位补全，不阻塞流程",
                        missing_fields,
                    )
                    break

            persist_llm_usage(llm_usage, model_used, call_type="analysis", stock_code=code)

            logger.info(f"[LLM解析] {name}({code}) 分析完成: {result.trend_prediction}, 评分 {result.sentiment_score}")

            return result
            
        except Exception as e:
            logger.error(f"AI 分析 {name}({code}) 失败: {e}")
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震荡',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary=f'分析过程出错: {str(e)[:100]}',
                risk_warning='分析失败，请稍后重试或手动分析',
                success=False,
                error_message=str(e),
                model_used=None,
            )
    
    def _format_prompt(
        self, 
        context: Dict[str, Any], 
        name: str,
        news_context: Optional[str] = None
    ) -> str:
        """
        格式化分析提示词（决策仪表盘 v2.0）
        
        包含：技术指标、实时行情（量比/换手率）、筹码分布、趋势分析、新闻
        
        Args:
            context: 技术面数据上下文（包含增强数据）
            name: 股票名称（默认值，可能被上下文覆盖）
            news_context: 预先搜索的新闻内容
        """
        code = context.get('code', 'Unknown')
        
        # 优先使用上下文中的股票名称（从 realtime_quote 获取）
        stock_name = context.get('stock_name', name)
        if not stock_name or stock_name == f'股票{code}':
            stock_name = STOCK_NAME_MAP.get(code, code)
            
        today = context.get('today', {})
        
        # ========== Build Decision Dashboard prompt ==========
        prompt = f"""# Decision Dashboard Analysis Request

## 📊 Stock Information
| Field | Value |
|-------|-------|
| Ticker | **{code}** |
| Name | **{stock_name}** |
| Analysis Date | {context.get('date', 'Unknown')} |

---

## 📈 Technical Data

### Today's Quote
| Metric | Value |
|--------|-------|
| Close | {today.get('close', 'N/A')} |
| Open | {today.get('open', 'N/A')} |
| High | {today.get('high', 'N/A')} |
| Low | {today.get('low', 'N/A')} |
| Change % | {today.get('pct_chg', 'N/A')}% |
| Volume | {self._format_volume(today.get('volume'))} |
| Turnover | {self._format_amount(today.get('amount'))} |

### Moving Average System (key decision metric)
| MA | Value | Note |
|----|-------|------|
| MA5 | {today.get('ma5', 'N/A')} | Short-term trend |
| MA10 | {today.get('ma10', 'N/A')} | Medium-short trend |
| MA20 | {today.get('ma20', 'N/A')} | Medium-term trend |
| MA Pattern | {context.get('ma_status', 'Unknown')} | Bullish/Bearish/Tangled |
"""
        
        # Real-time quote data
        if 'realtime' in context:
            rt = context['realtime']
            prompt += f"""
### Real-time Enhanced Data
| Metric | Value | Note |
|--------|-------|------|
| Current Price | {rt.get('price', 'N/A')} | |
| **Volume Ratio** | **{rt.get('volume_ratio', 'N/A')}** | {rt.get('volume_ratio_desc', '')} |
| **Turnover Rate** | **{rt.get('turnover_rate', 'N/A')}%** | |
| P/E (TTM) | {rt.get('pe_ratio', 'N/A')} | |
| P/B | {rt.get('pb_ratio', 'N/A')} | |
| Market Cap | {self._format_amount(rt.get('total_mv'))} | |
| Float Market Cap | {self._format_amount(rt.get('circ_mv'))} | |
| 60-day Change | {rt.get('change_60d', 'N/A')}% | Medium-term performance |
"""

        # 添加财报与分红（价值投资口径）
        fundamental_context = context.get("fundamental_context") if isinstance(context, dict) else None
        earnings_block = (
            fundamental_context.get("earnings", {})
            if isinstance(fundamental_context, dict)
            else {}
        )
        earnings_data = (
            earnings_block.get("data", {})
            if isinstance(earnings_block, dict)
            else {}
        )
        financial_report = (
            earnings_data.get("financial_report", {})
            if isinstance(earnings_data, dict)
            else {}
        )
        dividend_metrics = (
            earnings_data.get("dividend", {})
            if isinstance(earnings_data, dict)
            else {}
        )
        if isinstance(financial_report, dict) or isinstance(dividend_metrics, dict):
            financial_report = financial_report if isinstance(financial_report, dict) else {}
            dividend_metrics = dividend_metrics if isinstance(dividend_metrics, dict) else {}
            ttm_yield = dividend_metrics.get("ttm_dividend_yield_pct", "N/A")
            ttm_cash = dividend_metrics.get("ttm_cash_dividend_per_share", "N/A")
            ttm_count = dividend_metrics.get("ttm_event_count", "N/A")
            report_date = financial_report.get("report_date", "N/A")
            prompt += f"""
### Financials & Dividends (Value Metrics)
| Metric | Value | Note |
|--------|-------|------|
| Latest Report Period | {report_date} | From structured financial data |
| Revenue | {financial_report.get('revenue', 'N/A')} | |
| Net Profit (attributable) | {financial_report.get('net_profit_parent', 'N/A')} | |
| Operating Cash Flow | {financial_report.get('operating_cash_flow', 'N/A')} | |
| ROE | {financial_report.get('roe', 'N/A')} | |
| TTM Cash Dividend per Share | {ttm_cash} | Cash dividend only, pre-tax |
| TTM Dividend Yield | {ttm_yield} | Formula: TTM cash div / current price × 100% |
| TTM Dividend Events | {ttm_count} | |

> If any field above is N/A or missing, explicitly state "Data unavailable" — do not fabricate values.
"""

        # Growth metrics block (works for both A-shares and US stocks)
        growth_block = (
            fundamental_context.get("growth", {})
            if isinstance(fundamental_context, dict)
            else {}
        )
        growth_data = growth_block.get("data", {}) if isinstance(growth_block, dict) else {}
        if isinstance(growth_data, dict) and any(v is not None for v in growth_data.values()):
            def _fmt_pct(v):
                if v is None:
                    return "N/A"
                try:
                    return f"{float(v):+.1f}%"
                except (TypeError, ValueError):
                    return "N/A"
            prompt += f"""
### Growth Metrics (Year-over-Year)
| Metric | Value |
|--------|-------|
| Revenue YoY | {_fmt_pct(growth_data.get('revenue_yoy'))} |
| Net Profit YoY | {_fmt_pct(growth_data.get('net_profit_yoy'))} |
| ROE | {_fmt_pct(growth_data.get('roe'))} |
| Gross Margin | {_fmt_pct(growth_data.get('gross_margin'))} |
"""

        # Chip distribution data
        if 'chip' in context:
            chip = context['chip']
            profit_ratio = chip.get('profit_ratio', 0)
            prompt += f"""
### Chip Distribution (Efficiency Metrics)
| Metric | Value | Healthy Range |
|--------|-------|---------------|
| **Profit Ratio** | **{profit_ratio:.1%}** | Caution at 70–90% |
| Average Cost | {chip.get('avg_cost', 'N/A')} | Price should be 5–15% above avg cost |
| 90% Chip Concentration | {chip.get('concentration_90', 0):.2%} | <15% = concentrated |
| 70% Chip Concentration | {chip.get('concentration_70', 0):.2%} | |
| Chip Status | {chip.get('chip_status', 'Unknown')} | |
"""
        
        # Trend analysis
        if 'trend_analysis' in context:
            trend = context['trend_analysis']
            bias_warning = "🚨 Over 5% — do NOT chase!" if trend.get('bias_ma5', 0) > 5 else "✅ Safe range"
            prompt += f"""
### Trend Analysis (based on trading philosophy)
| Metric | Value | Assessment |
|--------|-------|------------|
| Trend Status | {trend.get('trend_status', 'Unknown')} | |
| MA Alignment | {trend.get('ma_alignment', 'Unknown')} | MA5>MA10>MA20 = Bullish |
| Trend Strength | {trend.get('trend_strength', 0)}/100 | |
| **Bias (MA5)** | **{trend.get('bias_ma5', 0):+.2f}%** | {bias_warning} |
| Bias (MA10) | {trend.get('bias_ma10', 0):+.2f}% | |
| Volume Status | {trend.get('volume_status', 'Unknown')} | {trend.get('volume_trend', '')} |
| System Signal | {trend.get('buy_signal', 'Unknown')} | |
| System Score | {trend.get('signal_score', 0)}/100 | |

#### System Analysis Rationale
**Buy Reasons**:
{chr(10).join('- ' + r for r in trend.get('signal_reasons', ['None'])) if trend.get('signal_reasons') else '- None'}

**Risk Factors**:
{chr(10).join('- ' + r for r in trend.get('risk_factors', ['None'])) if trend.get('risk_factors') else '- None'}
"""
        
        # Day-over-day comparison
        if 'yesterday' in context:
            volume_change = context.get('volume_change_ratio', 'N/A')
            prompt += f"""
### Volume & Price Change (vs. Prior Day)
- Volume change: {volume_change}x
- Price change: {context.get('price_change_ratio', 'N/A')}%
"""
        
        # 添加新闻搜索结果（重点区域）
        news_window_days: Optional[int] = None
        context_window = context.get("news_window_days")
        try:
            if context_window is not None:
                parsed_window = int(context_window)
                if parsed_window > 0:
                    news_window_days = parsed_window
        except (TypeError, ValueError):
            news_window_days = None

        if news_window_days is None:
            prompt_config = get_config()
            news_window_days = resolve_news_window_days(
                news_max_age_days=getattr(prompt_config, "news_max_age_days", 3),
                news_strategy_profile=getattr(prompt_config, "news_strategy_profile", "short"),
            )
        prompt += """
---

## 📰 Market Intelligence
"""
        if news_context:
            prompt += f"""
The following are news and Reddit posts for **{stock_name} ({code})** from the past {news_window_days} days. Focus on extracting:
1. 🚨 **Risk Alerts**: insider selling, penalties, negative catalysts
2. 🎯 **Positive Catalysts**: earnings beats, contracts, policy tailwinds
3. 📊 **Earnings Outlook**: annual guidance, preliminary results
4. 💬 **Sentiment Summary**: Write 2-3 sentences covering:
   - What the **news articles** are reporting (key themes, headlines)
   - What **Reddit/social** discussions are saying (community sentiment, hot topics)
   - Overall sentiment direction (bullish / bearish / mixed)
5. 🕒 **Time Rules (mandatory)**:
   - Every item in `risk_alerts` / `positive_catalysts` / `latest_news` must include a specific date (YYYY-MM-DD)
   - News older than {news_window_days} days must be ignored
   - News with unknown publication date must be ignored
6. ⚠️ **Source Rules (mandatory)**:
   - `intelligence.risk_alerts` and `intelligence.positive_catalysts` must ONLY contain items derived from the news_context above (Reddit/X/News social data)
   - Do NOT put technical analysis observations (MA, price levels, bias, volume) into `risk_alerts` — those belong in the technical fields only
7. 📦 **Data Discipline Rules (mandatory)**:
   - Use only the data explicitly shown in the tables and news_context above
   - Do not add outside facts, estimates, industry averages, or assumptions that are not present in the input
   - If a required metric is unavailable in the input, write `Data unavailable`

```
{news_context}
```
"""
        else:
            prompt += """
No recent news found for this stock. Base analysis primarily on technical data.
"""

        # Data missing warning
        if context.get('data_missing'):
            prompt += """
⚠️ **Data Missing Warning**
Due to API limitations, complete real-time quote and technical indicator data is unavailable.
**Ignore N/A values** in the tables above and base analysis on the **Market Intelligence** section.
For technical questions (MA, bias, etc.), explicitly state "Data unavailable" — do not fabricate values.
"""

        # Final analysis task
        prompt += f"""
---

## ✅ Analysis Task

Generate a **Decision Dashboard** for **{stock_name} ({code})**. Output strictly in JSON format. **All text fields must be in English.**
"""
        if context.get('is_index_etf'):
            prompt += """
> ⚠️ **Index/ETF Constraint**: This is an index-tracking ETF or market index.
> - Risk analysis should only cover: **index trend, tracking error, market liquidity**
> - Do NOT include fund company lawsuits, reputation, or management changes in risk alerts
> - Earnings outlook should be based on **index constituent performance**, not the fund company's financials
> - `risk_alerts` must not contain fund manager business operation risks

"""
        prompt += f"""
### Key Questions (answer each with specific data and reasoning):
1. ❓ Does MA5 > MA10 > MA20 bullish alignment hold? → State the actual MA values and whether gaps are widening or narrowing
2. ❓ Is the current bias within safe range (<5%)? → State exact bias %, what it means for entry risk
3. ❓ Is volume confirming the move? → Cite volume ratio, describe what the pattern implies
4. ❓ Is the chip structure healthy? → Cite profit ratio and avg cost, explain the implication
5. ❓ Are there any major negative catalysts? → Cite specific news/social evidence or confirm absence
6. ❓ Do the social sentiment signals agree with the technical picture? → Compare sentiment scores vs MA direction, explain any divergence

### Dashboard Requirements:
- **Stock name**: Use the correct full name (e.g. "Apple Inc." not "StockAAPL")
- **Core conclusion**: One sentence — buy / sell / wait, followed by the single most important reason
- **Split position advice**: What to do with no position vs. holding — with specific price triggers
- **Precise price targets**: Specific entry, stop-loss, and target prices with reasoning for each level
- **Action checklist**: Mark each item with ✅/⚠️/❌ and a brief reason
- **Reasoning chain**: Fill `signal_reasoning` with a clear step-by-step: list each signal, its value, what it implies, and how conflicts were resolved
- **Data insights**: Fill `data_insights` with non-obvious observations that add analytical value beyond the raw numbers
- **News time compliance**: `latest_news`, `risk_alerts`, `positive_catalysts` must not include items outside the {news_window_days}-day window or with unknown dates
- **Evidence discipline**: Every major conclusion must point to specific provided values from the input tables or news_context
- **Missing data behavior**: If the input does not contain a required fact after collection, output `Data unavailable` rather than inferring it

Output the complete JSON Decision Dashboard.

⚠️ LANGUAGE REQUIREMENT (MANDATORY): Every single string value in the JSON output MUST be written in English. This is a hard requirement. Do NOT use Chinese, Japanese, or any other language. If the input data or news is in Chinese, translate all text fields to English in your output. Non-compliance will cause a parsing error."""
        
        return prompt
    
    def _format_volume(self, volume: Optional[float]) -> str:
        """格式化成交量显示"""
        if volume is None:
            return 'N/A'
        if volume >= 1e8:
            return f"{volume / 1e8:.2f}B shares"
        elif volume >= 1e4:
            return f"{volume / 1e4:.2f}W shares"
        else:
            return f"{volume:.0f} shares"
    
    def _format_amount(self, amount: Optional[float]) -> str:
        """格式化成交额显示"""
        if amount is None:
            return 'N/A'
        if amount >= 1e8:
            return f"{amount / 1e8:.2f}B"
        elif amount >= 1e4:
            return f"{amount / 1e4:.2f}W"
        else:
            return f"{amount:.0f}"

    def _format_percent(self, value: Optional[float]) -> str:
        """格式化百分比显示"""
        if value is None:
            return 'N/A'
        try:
            return f"{float(value):.2f}%"
        except (TypeError, ValueError):
            return 'N/A'

    def _format_price(self, value: Optional[float]) -> str:
        """格式化价格显示"""
        if value is None:
            return 'N/A'
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return 'N/A'

    def _build_market_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """构建当日行情快照（展示用）"""
        today = context.get('today', {}) or {}
        realtime = context.get('realtime', {}) or {}
        yesterday = context.get('yesterday', {}) or {}

        prev_close = yesterday.get('close')
        close = today.get('close')
        high = today.get('high')
        low = today.get('low')

        amplitude = None
        change_amount = None
        if prev_close not in (None, 0) and high is not None and low is not None:
            try:
                amplitude = (float(high) - float(low)) / float(prev_close) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                amplitude = None
        if prev_close is not None and close is not None:
            try:
                change_amount = float(close) - float(prev_close)
            except (TypeError, ValueError):
                change_amount = None

        snapshot = {
            "date": context.get('date', '未知'),
            "close": self._format_price(close),
            "open": self._format_price(today.get('open')),
            "high": self._format_price(high),
            "low": self._format_price(low),
            "prev_close": self._format_price(prev_close),
            "pct_chg": self._format_percent(today.get('pct_chg')),
            "change_amount": self._format_price(change_amount),
            "amplitude": self._format_percent(amplitude),
            "volume": self._format_volume(today.get('volume')),
            "amount": self._format_amount(today.get('amount')),
        }

        if realtime:
            snapshot.update({
                "price": self._format_price(realtime.get('price')),
                "volume_ratio": realtime.get('volume_ratio', 'N/A'),
                "turnover_rate": self._format_percent(realtime.get('turnover_rate')),
                "source": getattr(realtime.get('source'), 'value', realtime.get('source', 'N/A')),
            })

        return snapshot

    def _check_content_integrity(self, result: AnalysisResult) -> Tuple[bool, List[str]]:
        """Delegate to module-level check_content_integrity."""
        return check_content_integrity(result)

    def _build_integrity_complement_prompt(self, missing_fields: List[str]) -> str:
        """Build complement instruction for missing mandatory fields."""
        lines = ["### 补全要求：请在上方分析基础上补充以下必填内容，并输出完整 JSON："]
        for f in missing_fields:
            if f == "sentiment_score":
                lines.append("- sentiment_score: 0-100 综合评分")
            elif f == "operation_advice":
                lines.append("- operation_advice: 买入/加仓/持有/减仓/卖出/观望")
            elif f == "analysis_summary":
                lines.append("- analysis_summary: 综合分析摘要")
            elif f == "dashboard.core_conclusion.one_sentence":
                lines.append("- dashboard.core_conclusion.one_sentence: 一句话决策")
            elif f == "dashboard.intelligence.risk_alerts":
                lines.append("- dashboard.intelligence.risk_alerts: 风险警报列表（可为空数组）")
            elif f == "dashboard.battle_plan.sniper_points.stop_loss":
                lines.append("- dashboard.battle_plan.sniper_points.stop_loss: 止损价")
        return "\n".join(lines)

    def _build_integrity_retry_prompt(
        self,
        base_prompt: str,
        previous_response: str,
        missing_fields: List[str],
    ) -> str:
        """Build retry prompt using the previous response as the complement baseline."""
        complement = self._build_integrity_complement_prompt(missing_fields)
        previous_output = previous_response.strip()
        return "\n\n".join([
            base_prompt,
            "### 上一次输出如下，请在该输出基础上补齐缺失字段，并重新输出完整 JSON。不要省略已有字段：",
            previous_output,
            complement,
        ])

    def _apply_placeholder_fill(self, result: AnalysisResult, missing_fields: List[str]) -> None:
        """Delegate to module-level apply_placeholder_fill."""
        apply_placeholder_fill(result, missing_fields)

    def _parse_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """
        解析 Gemini 响应（决策仪表盘版）
        
        尝试从响应中提取 JSON 格式的分析结果，包含 dashboard 字段
        如果解析失败，尝试智能提取或返回默认结果
        """
        try:
            # 清理响应文本：移除 markdown 代码块标记
            cleaned_text = response_text
            if '```json' in cleaned_text:
                cleaned_text = cleaned_text.replace('```json', '').replace('```', '')
            elif '```' in cleaned_text:
                cleaned_text = cleaned_text.replace('```', '')
            
            # 尝试找到 JSON 内容
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = cleaned_text[json_start:json_end]
                
                # 尝试修复常见的 JSON 问题
                json_str = self._fix_json_string(json_str)
                
                data = json.loads(json_str)

                # Schema validation (lenient: on failure, continue with raw dict)
                try:
                    AnalysisReportSchema.model_validate(data)
                except Exception as e:
                    logger.warning(
                        "LLM report schema validation failed, continuing with raw dict: %s",
                        str(e)[:100],
                    )

                # 提取 dashboard 数据
                dashboard = data.get('dashboard', None)

                # 优先使用 AI 返回的股票名称（如果原名称无效或包含代码）
                ai_stock_name = data.get('stock_name')
                if ai_stock_name and (name.startswith('股票') or name == code or 'Unknown' in name):
                    name = ai_stock_name

                # 解析所有字段，使用默认值防止缺失
                # 解析 decision_type，如果没有则根据 operation_advice 推断
                decision_type = data.get('decision_type', '')
                if not decision_type:
                    op = data.get('operation_advice', '持有')
                    if op in ['买入', '加仓', '强烈买入']:
                        decision_type = 'buy'
                    elif op in ['卖出', '减仓', '强烈卖出']:
                        decision_type = 'sell'
                    else:
                        decision_type = 'hold'
                
                return AnalysisResult(
                    code=code,
                    name=name,
                    # 核心指标
                    sentiment_score=int(data.get('sentiment_score', 50)),
                    trend_prediction=data.get('trend_prediction', '震荡'),
                    operation_advice=data.get('operation_advice', '持有'),
                    decision_type=decision_type,
                    confidence_level=data.get('confidence_level', '中'),
                    # 决策仪表盘
                    dashboard=dashboard,
                    # 走势分析
                    trend_analysis=data.get('trend_analysis', ''),
                    short_term_outlook=data.get('short_term_outlook', ''),
                    medium_term_outlook=data.get('medium_term_outlook', ''),
                    # 技术面
                    technical_analysis=data.get('technical_analysis', ''),
                    ma_analysis=data.get('ma_analysis', ''),
                    volume_analysis=data.get('volume_analysis', ''),
                    pattern_analysis=data.get('pattern_analysis', ''),
                    # 基本面
                    fundamental_analysis=data.get('fundamental_analysis', ''),
                    sector_position=data.get('sector_position', ''),
                    company_highlights=data.get('company_highlights', ''),
                    # 情绪面/消息面
                    news_summary=data.get('news_summary', ''),
                    market_sentiment=data.get('market_sentiment', ''),
                    hot_topics=data.get('hot_topics', ''),
                    # 综合
                    analysis_summary=data.get('analysis_summary', '分析完成'),
                    key_points=data.get('key_points', ''),
                    risk_warning=data.get('risk_warning', ''),
                    buy_reason=data.get('buy_reason', ''),
                    # 元数据
                    search_performed=data.get('search_performed', False),
                    data_sources=data.get('data_sources', '技术面数据'),
                    success=True,
                )
            else:
                # 没有找到 JSON，尝试从纯文本中提取信息
                logger.warning(f"无法从响应中提取 JSON，使用原始文本分析")
                return self._parse_text_response(response_text, code, name)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}，尝试从文本提取")
            return self._parse_text_response(response_text, code, name)
    
    def _fix_json_string(self, json_str: str) -> str:
        """修复常见的 JSON 格式问题"""
        import re
        
        # 移除注释
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # 修复尾随逗号
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # 确保布尔值是小写
        json_str = json_str.replace('True', 'true').replace('False', 'false')
        
        # fix by json-repair
        json_str = repair_json(json_str)
        
        return json_str
    
    def _parse_text_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """从纯文本响应中尽可能提取分析信息"""
        # 尝试识别关键词来判断情绪
        sentiment_score = 50
        trend = '震荡'
        advice = '持有'
        
        text_lower = response_text.lower()
        
        # 简单的情绪识别
        positive_keywords = ['看多', '买入', '上涨', '突破', '强势', '利好', '加仓', 'bullish', 'buy']
        negative_keywords = ['看空', '卖出', '下跌', '跌破', '弱势', '利空', '减仓', 'bearish', 'sell']
        
        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if positive_count > negative_count + 1:
            sentiment_score = 65
            trend = '看多'
            advice = '买入'
            decision_type = 'buy'
        elif negative_count > positive_count + 1:
            sentiment_score = 35
            trend = '看空'
            advice = '卖出'
            decision_type = 'sell'
        else:
            decision_type = 'hold'
        
        # 截取前500字符作为摘要
        summary = response_text[:500] if response_text else '无分析结果'
        
        return AnalysisResult(
            code=code,
            name=name,
            sentiment_score=sentiment_score,
            trend_prediction=trend,
            operation_advice=advice,
            decision_type=decision_type,
            confidence_level='低',
            analysis_summary=summary,
            key_points='JSON解析失败，仅供参考',
            risk_warning='分析结果可能不准确，建议结合其他信息判断',
            raw_response=response_text,
            success=True,
        )
    
    def batch_analyze(
        self, 
        contexts: List[Dict[str, Any]],
        delay_between: float = 2.0
    ) -> List[AnalysisResult]:
        """
        批量分析多只股票
        
        注意：为避免 API 速率限制，每次分析之间会有延迟
        
        Args:
            contexts: 上下文数据列表
            delay_between: 每次分析之间的延迟（秒）
            
        Returns:
            AnalysisResult 列表
        """
        results = []
        
        for i, context in enumerate(contexts):
            if i > 0:
                logger.debug(f"等待 {delay_between} 秒后继续...")
                time.sleep(delay_between)
            
            result = self.analyze(context)
            results.append(result)
        
        return results


# 便捷函数
def get_analyzer() -> GeminiAnalyzer:
    """获取 LLM 分析器实例"""
    return GeminiAnalyzer()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    # 模拟上下文数据
    test_context = {
        'code': '600519',
        'date': '2026-01-09',
        'today': {
            'open': 1800.0,
            'high': 1850.0,
            'low': 1780.0,
            'close': 1820.0,
            'volume': 10000000,
            'amount': 18200000000,
            'pct_chg': 1.5,
            'ma5': 1810.0,
            'ma10': 1800.0,
            'ma20': 1790.0,
            'volume_ratio': 1.2,
        },
        'ma_status': '多头排列 📈',
        'volume_change_ratio': 1.3,
        'price_change_ratio': 1.5,
    }
    
    analyzer = GeminiAnalyzer()
    
    if analyzer.is_available():
        print("=== AI 分析测试 ===")
        result = analyzer.analyze(test_context)
        print(f"分析结果: {result.to_dict()}")
    else:
        print("Gemini API 未配置，跳过测试")
