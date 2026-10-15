# -*- coding: utf-8 -*-
import json
import os
import subprocess
import textwrap
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from api.v1.schemas.team import TeamRunRequest, TeamRunResponse, TeamWorkflowStep


ROLE_LABELS = {
    "market": ("Market Analyst", "📈"),
    "social": ("Social Analyst", "🌐"),
    "news": ("News Analyst", "📰"),
    "fundamentals": ("Fundamentals Analyst", "📚"),
    "ivy": ("Ivy Agent", "🪴"),
}

FOLLOWUP_STEPS = [
    ("bull_researcher", "Bull Researcher", "🐂"),
    ("bear_researcher", "Bear Researcher", "🐻"),
    ("research_manager", "Research Manager", "🧭"),
    ("trader", "Trader", "💹"),
    ("portfolio_manager", "Portfolio Manager", "🛡️"),
]


def _default_tradingagents_root() -> Path:
    ivytrader_root = Path(__file__).resolve().parents[3]
    return ivytrader_root.parent / "TradingAgents"


def _resolve_tradingagents_runtime() -> tuple[Path, Path]:
    root = Path(os.environ.get("TEAM_TRADINGAGENTS_ROOT", str(_default_tradingagents_root()))).resolve()
    if not root.exists():
        raise RuntimeError(f"TradingAgents path not found: {root}")

    python_bin = root / ".venv" / "bin" / "python"
    if not python_bin.exists():
        raise RuntimeError(f"TradingAgents venv python not found: {python_bin}")

    return root, python_bin


def _provider_defaults(provider: str) -> Dict[str, str]:
    if provider == "google":
        return {
            "deep": "gemini-2.5-pro",
            "quick": "gemini-2.5-flash",
        }
    return {
        "deep": "claude-sonnet-4-6",
        "quick": "claude-haiku-4-5",
    }


def _load_dotenv_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _build_team_subprocess_env(root: Path) -> Dict[str, str]:
    env = os.environ.copy()

    # Also load the main IvyTrader .env so Team runs can reuse the same keys
    # even when backend_analysis has a separate EnvironmentFile.
    ivytrader_root = Path(__file__).resolve().parents[3]
    merged_env = _load_dotenv_file(ivytrader_root / ".env")
    merged_env.update(_load_dotenv_file(ivytrader_root / "backend_analysis" / ".env"))

    for key, value in merged_env.items():
        env.setdefault(key, value)

    # Normalize provider key names expected by downstream SDKs.
    if "GOOGLE_API_KEY" not in env and env.get("GEMINI_API_KEY"):
        env["GOOGLE_API_KEY"] = env["GEMINI_API_KEY"]

    env["TEAM_TRADINGAGENTS_ROOT"] = str(root)
    env.setdefault("IVYTRADER_API_BASE", os.environ.get("TEAM_IVYTRADER_API_BASE", "http://127.0.0.1:8001"))
    return env


def build_default_workflow(roles: List[str]) -> List["TeamWorkflowStep"]:
    from api.v1.schemas.team import TeamWorkflowStep

    selected = set(roles)
    steps: List[TeamWorkflowStep] = []
    for role in ["market", "social", "news", "fundamentals", "ivy"]:
        label, icon = ROLE_LABELS[role]
        steps.append(
            TeamWorkflowStep(
                key=role,
                label=label,
                icon=icon,
                status="completed" if role in selected else "skipped",
            )
        )

    for key, label, icon in FOLLOWUP_STEPS:
        steps.append(TeamWorkflowStep(key=key, label=label, icon=icon, status="completed"))
    return steps


def _build_markdown_report(request: "TeamRunRequest", state: Dict[str, str]) -> str:
    sections: List[str] = [
        f"# Team Report for {request.stock_code.upper()}",
        "",
        f"- Trade Date: {request.trade_date}",
        f"- Provider: {request.llm_provider}",
        f"- Deep Model: {state.get('deep_model', '')}",
        f"- Quick Model: {state.get('quick_model', '')}",
        f"- Roles: {', '.join(request.roles)}",
        "",
    ]

    report_sections = [
        ("market_report", "Market Report"),
        ("sentiment_report", "Social Report"),
        ("news_report", "News Report"),
        ("fundamentals_report", "Fundamentals Report"),
        ("ivy_report", "Ivy Report"),
        ("trader_investment_plan", "Trader Plan"),
        ("investment_plan", "Investment Plan"),
        ("final_trade_decision", "Final Trade Decision"),
    ]
    for key, title in report_sections:
        value = str(state.get(key, "") or "").strip()
        if value:
            sections.extend([f"## {title}", "", value, ""])
    return "\n".join(sections).strip()


def _team_runner_script() -> str:
    return textwrap.dedent(
        """
        import json
        import os
        import sys

        root = os.environ["TEAM_TRADINGAGENTS_ROOT"]
        if root not in sys.path:
            sys.path.insert(0, root)

        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        import tradingagents.graph.setup as setup_module
        import tradingagents.agents as agents_module
        import tradingagents.agents.analysts.ivy_analyst as ivy_module
        import requests

        payload = json.loads(os.environ["TEAM_RUN_PAYLOAD"])
        progress_enabled = os.environ.get("TEAM_PROGRESS_ENABLED") == "1"
        progress_steps = json.loads(os.environ.get("TEAM_PROGRESS_STEPS", "[]"))

        def emit(event):
            print(json.dumps({"kind": "progress", **event}, ensure_ascii=False), flush=True)

        def wrap_factory(factory, key):
            def create(*args, **kwargs):
                original = factory(*args, **kwargs)
                def node(state):
                    if progress_enabled:
                        emit({"event": "step_started", "step": key})
                    result = original(state)
                    if progress_enabled:
                        emit({"event": "step_completed", "step": key})
                    return result
                return node
            return create

        def local_ivy_factory(_llm):
            def node(state):
                if progress_enabled:
                    emit({"event": "step_started", "step": "ivy"})
                response = requests.post(
                    os.environ.get("IVYTRADER_API_BASE", "http://127.0.0.1:8001").rstrip("/") + "/api/v1/analysis/ivy-report",
                    json={
                        "stock_code": str(state["company_of_interest"]).strip().upper(),
                        "report_type": "detailed",
                        "async_mode": False,
                    },
                    timeout=300,
                )
                response.raise_for_status()
                payload = response.json()
                report = str(payload.get("ivy_report", "")).strip()
                if progress_enabled:
                    emit({"event": "step_completed", "step": "ivy"})
                return {"ivy_report": report}
            return node

        setup_module.create_market_analyst = wrap_factory(setup_module.create_market_analyst, "market")
        setup_module.create_social_media_analyst = wrap_factory(setup_module.create_social_media_analyst, "social")
        setup_module.create_news_analyst = wrap_factory(setup_module.create_news_analyst, "news")
        setup_module.create_fundamentals_analyst = wrap_factory(setup_module.create_fundamentals_analyst, "fundamentals")
        setup_module.create_bull_researcher = wrap_factory(setup_module.create_bull_researcher, "bull_researcher")
        setup_module.create_bear_researcher = wrap_factory(setup_module.create_bear_researcher, "bear_researcher")
        setup_module.create_research_manager = wrap_factory(setup_module.create_research_manager, "research_manager")
        setup_module.create_trader = wrap_factory(setup_module.create_trader, "trader")
        setup_module.create_portfolio_manager = wrap_factory(setup_module.create_portfolio_manager, "portfolio_manager")
        setup_module.create_ivy_analyst = local_ivy_factory
        agents_module.create_ivy_analyst = local_ivy_factory
        ivy_module.create_ivy_analyst = local_ivy_factory

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = payload["llm_provider"]
        config["deep_think_llm"] = payload["deep_model"]
        config["quick_think_llm"] = payload["quick_model"]
        config["max_debate_rounds"] = payload["max_debate_rounds"]
        config["max_risk_discuss_rounds"] = payload["max_risk_discuss_rounds"]

        graph = TradingAgentsGraph(
            selected_analysts=payload["roles"],
            config=config,
            debug=False,
        )
        final_state, decision = graph.propagate(payload["stock_code"], payload["trade_date"])

        safe_state = {
            "company_of_interest": final_state.get("company_of_interest", payload["stock_code"]),
            "trade_date": final_state.get("trade_date", payload["trade_date"]),
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "ivy_report": final_state.get("ivy_report", ""),
            "trader_investment_plan": final_state.get("trader_investment_plan", ""),
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", decision),
            "deep_model": payload["deep_model"],
            "quick_model": payload["quick_model"],
        }
        print(json.dumps({"state": safe_state, "decision": decision}, ensure_ascii=False))
        """
    )


def _run_tradingagents_subprocess(
    request: "TeamRunRequest",
    deep_model: str,
    quick_model: str,
    progress_callback=None,
) -> Dict[str, str]:
    root, python_bin = _resolve_tradingagents_runtime()
    payload = {
        "stock_code": request.stock_code.upper(),
        "trade_date": request.trade_date,
        "llm_provider": request.llm_provider,
        "deep_model": deep_model,
        "quick_model": quick_model,
        "roles": request.roles,
        "max_debate_rounds": request.max_debate_rounds,
        "max_risk_discuss_rounds": request.max_risk_discuss_rounds,
    }
    env = _build_team_subprocess_env(root)
    env["TEAM_RUN_PAYLOAD"] = json.dumps(payload)
    env["TEAM_PROGRESS_ENABLED"] = "1" if progress_callback else "0"

    process = subprocess.Popen(
        [str(python_bin), "-c", _team_runner_script()],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    final_payload = None
    stdout_lines: List[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        stdout_lines.append(line)
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("kind") == "progress":
            if progress_callback:
                progress_callback(item)
            continue
        final_payload = item

    stderr = process.stderr.read().strip() if process.stderr else ""
    return_code = process.wait(timeout=int(os.environ.get("TEAM_RUN_TIMEOUT_SECONDS", "1800")))
    if return_code != 0:
        raise RuntimeError(f"TradingAgents run failed: {stderr or 'Unknown error'}")
    if final_payload is None:
        raise RuntimeError(f"TradingAgents returned invalid JSON: {' '.join(stdout_lines)[-500:]}")

    state = final_payload.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("TradingAgents response missing state payload")
    return {key: str(value or "") for key, value in state.items()}


def run_team_with_progress(request: "TeamRunRequest", progress_callback=None) -> "TeamRunResponse":
    from api.v1.schemas.team import TeamRunResponse

    defaults = _provider_defaults(request.llm_provider)
    deep_model = request.deep_model or defaults["deep"]
    quick_model = request.quick_model or defaults["quick"]

    workflow_steps = build_default_workflow(request.roles)
    step_keys = [step.key for step in workflow_steps if step.status != "skipped"]

    def relay_progress(event: Dict[str, str]) -> None:
        if not progress_callback:
            return
        event_type = event.get("event")
        current_step = event.get("step")
        workflow_payload = []
        for step in workflow_steps:
            status = step.status
            if current_step == step.key and event_type == "step_started":
                status = "active"
            elif current_step == step.key and event_type == "step_completed":
                status = "completed"
            workflow_payload.append({
                "key": step.key,
                "label": step.label,
                "icon": step.icon,
                "status": status,
            })
        index = step_keys.index(current_step) if current_step in step_keys else -1
        progress = min(95, max(10, int(((index + (1 if event_type == "step_completed" else 0)) / max(len(step_keys), 1)) * 100)))
        progress_callback({
            "current_step": current_step,
            "progress": progress,
            "message": f"{current_step} {'completed' if event_type == 'step_completed' else 'running'}",
            "workflow": workflow_payload,
        })

    safe_state = _run_tradingagents_subprocess(request, deep_model, quick_model, relay_progress)
    markdown_report = _build_markdown_report(request, safe_state)
    reports = {
        "market": safe_state.get("market_report", ""),
        "social": safe_state.get("sentiment_report", ""),
        "news": safe_state.get("news_report", ""),
        "fundamentals": safe_state.get("fundamentals_report", ""),
        "ivy": safe_state.get("ivy_report", ""),
    }

    return TeamRunResponse(
        run_id=uuid.uuid4().hex,
        stock_code=request.stock_code.upper(),
        trade_date=request.trade_date,
        llm_provider=request.llm_provider,
        deep_model=deep_model,
        quick_model=quick_model,
        roles=request.roles,
        workflow=build_default_workflow(request.roles),
        reports=reports,
        final_decision=safe_state.get("final_trade_decision", "").strip(),
        investment_plan=safe_state.get("investment_plan", "").strip() or None,
        markdown_report=markdown_report,
        state=safe_state,
    )


def run_team(request: "TeamRunRequest") -> "TeamRunResponse":
    return run_team_with_progress(request, None)
