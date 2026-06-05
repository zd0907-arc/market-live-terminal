from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def _reload(module_name: str):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def _collect_os_env_fallbacks(script_path: Path) -> dict[str, list[str]]:
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    fallbacks: dict[str, list[str]] = {}

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "getenv"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                env_name = node.args[0].value
                fallback_values: list[str] = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        fallback_values.append(child.value)
                fallbacks.setdefault(env_name, []).extend(fallback_values)
            self.generic_visit(node)

    Visitor().visit(tree)
    return fallbacks


def test_watchlist_snapshot_prefers_research_current(monkeypatch, tmp_path):
    research_root = tmp_path / "market-data" / "research" / "current"
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.delenv("SELECTION_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_MAINBOARD_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_COMPACT_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_DB_PATH", raising=False)

    mod = _reload("backend.scripts.build_research_watchlist_snapshot")

    assert mod.SELECTION_DB == research_root / "selection" / "selection_research.db"
    assert mod.ATOMIC_DB == research_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"


def test_opportunity_trade_review_payload_prefers_research_current(monkeypatch, tmp_path):
    research_root = tmp_path / "market-data" / "research" / "current"
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.delenv("SELECTION_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_MAINBOARD_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_COMPACT_DB_PATH", raising=False)

    mod = _reload("backend.scripts.export_opportunity_trade_review_payload")

    assert mod.DEFAULT_SELECTION_DB == research_root / "selection" / "selection_research.db"
    assert mod.DEFAULT_ATOMIC_DB == research_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"


def test_spark_pattern_payload_prefers_research_current(monkeypatch, tmp_path):
    research_root = tmp_path / "market-data" / "research" / "current"
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.delenv("SELECTION_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_MAINBOARD_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_COMPACT_DB_PATH", raising=False)

    mod = _reload("backend.scripts.export_spark_pattern_research_payloads")

    assert mod.DEFAULT_SELECTION_DB == research_root / "selection" / "selection_research.db"
    assert mod.DEFAULT_ATOMIC_DB == research_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"


def test_opportunity_discovery_model_prefers_research_current(monkeypatch, tmp_path):
    fallbacks = _collect_os_env_fallbacks(ROOT_DIR / "backend/scripts/research_opportunity_discovery_model.py")

    assert "RESEARCH_CURRENT_ROOT" in fallbacks
    assert "SELECTION_DB_PATH" in fallbacks
    assert "ATOMIC_COMPACT_DB_PATH" in fallbacks
    assert "FINE_THEME_HEAT_V2_DB" in fallbacks
    selection_fallbacks = "\n".join(fallbacks["SELECTION_DB_PATH"])
    atomic_fallbacks = "\n".join(fallbacks["ATOMIC_COMPACT_DB_PATH"])
    heat_fallbacks = "\n".join(fallbacks["FINE_THEME_HEAT_V2_DB"])
    assert "selection" in selection_fallbacks and "selection_research.db" in selection_fallbacks
    assert "atomic_facts" in atomic_fallbacks and "market_atomic_mainboard_compact_current.db" in atomic_fallbacks
    assert "market_heat" in heat_fallbacks and "fine_theme_heat_daily_v2.db" in heat_fallbacks


def test_market_heat_builder_scripts_prefer_research_current():
    script_names = [
        "build_hot_theme_trade_charts_page.py",
        "build_hot_theme_trade_l2_window_page.py",
        "build_fine_theme_heat_trend_page.py",
        "build_fine_theme_heat_trend_2025_2026_top10.py",
        "build_hot_theme_strong_momentum_case_page.py",
        "build_hot_theme_april_rule_hit_page_2026.py",
    ]
    for script_name in script_names:
        fallbacks = _collect_os_env_fallbacks(ROOT_DIR / f"backend/scripts/{script_name}")
        joined = "\n".join(sum(fallbacks.values(), []))
        assert "RESEARCH_CURRENT_ROOT" in fallbacks, script_name
        assert "ATOMIC_COMPACT_DB_PATH" in fallbacks, script_name
        assert "atomic_facts" in joined and "market_atomic_mainboard_compact_current.db" in joined, script_name
        if "trend" in script_name:
            assert "FINE_THEME_HEAT_DB" in fallbacks, script_name
            assert "TRADABLE_THEME_MAP_DB" in fallbacks, script_name
            assert "market_heat" in joined and "fine_theme_heat_daily.db" in joined, script_name
            assert "tradable_theme_map.db" in joined, script_name


def test_aggressive_10cm_research_scripts_prefer_research_current():
    script_expectations = {
        "research_aggressive_10cm_low_position_agent.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH", "SELECTION_DB_PATH", "FINE_THEME_HEAT_DB"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db", "selection_research.db", "fine_theme_heat_daily.db"},
        },
        "research_aggressive_10cm_hot_theme_agent.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH", "FINE_THEME_HEAT_DB"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db", "fine_theme_heat_daily.db"},
        },
        "research_combined_risk_stack.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db"},
        },
        "research_aggressive_10cm_execution_agent.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH", "SELECTION_DB_PATH", "FINE_THEME_HEAT_V2_DB", "FINE_THEME_HEAT_DB"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db", "selection_research.db", "fine_theme_heat_daily_v2.db"},
        },
    }
    for script_name, expected in script_expectations.items():
        fallbacks = _collect_os_env_fallbacks(ROOT_DIR / f"backend/scripts/{script_name}")
        joined = "\n".join(sum(fallbacks.values(), []))
        for env_name in expected["envs"]:
            assert env_name in fallbacks, script_name
        for token in expected["joined"]:
            assert token in joined, script_name


def test_market_heat_analysis_backtest_scripts_prefer_research_current():
    script_expectations = {
        "analyze_theme_lead_stock_lag_strategy.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH", "FINE_THEME_HEAT_DB", "TRADABLE_THEME_MAP_DB"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db", "fine_theme_heat_daily.db", "tradable_theme_map.db"},
        },
        "analyze_hot_theme_big_mover_l2_precondition.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH", "FINE_THEME_HEAT_DB"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db", "fine_theme_heat_daily.db"},
        },
        "backtest_hot_theme_monthly_samples.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH", "FINE_THEME_HEAT_DB"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db", "fine_theme_heat_daily.db"},
        },
        "backtest_hot_theme_rule_pack_portfolio_2025.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db"},
        },
        "research_combined_risk_stack_robustness.py": {
            "envs": {"RESEARCH_CURRENT_ROOT", "ATOMIC_COMPACT_DB_PATH", "ATOMIC_MAINBOARD_DB_PATH"},
            "joined": {"atomic_facts", "market_atomic_mainboard_compact_current.db"},
        },
    }
    for script_name, expected in script_expectations.items():
        fallbacks = _collect_os_env_fallbacks(ROOT_DIR / f"backend/scripts/{script_name}")
        joined = "\n".join(sum(fallbacks.values(), []))
        for env_name in expected["envs"]:
            assert env_name in fallbacks, script_name
        for token in expected["joined"]:
            assert token in joined, script_name
