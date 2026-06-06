from __future__ import annotations

from pathlib import Path
from decimal import Decimal
import time

from aegis_challenge.flow import scenario
from aegis_challenge.runner import run_strategy
from aegis_challenge.web_app import cancel_progressive_run, get_progressive_run, raw_export_path, run_web_strategy, start_progressive_run, submit_web_run


STARTER = Path("examples/starter_strategy.py").read_text()


def test_web_run_matches_cli_score_semantics(tmp_path):
    strategy = tmp_path / "starter.py"
    strategy.write_text(STARTER)
    cli = run_strategy(strategy, "smoke", 1, tmp_path / "cli")
    web = run_web_strategy(STARTER, "smoke", 1, tmp_path / "web")
    assert web["status"] == "ok"
    assert web["score"]["score_breakdown"]["scenario_score"] == cli["score"]["score_breakdown"]["scenario_score"]
    assert len(web["replay"]) == len(cli["events"]) == 60
    assert web["replay"][-1]["score"] == cli["events"][-1]["score"]


def test_web_submit_updates_leaderboard(tmp_path):
    run = run_web_strategy(STARTER, "smoke", 1, tmp_path)
    submitted = submit_web_run(run["run_id"], tmp_path)
    assert submitted["status"] == "ok"
    rows = submitted["leaderboard"]["leaderboard"]
    assert rows
    assert rows[0]["run_id"] == run["run_id"]


def test_web_invalid_python_is_actionable(tmp_path):
    run = run_web_strategy("class Strategy:\n    def on_step(self, state):\n        return [\n", "smoke", 1, tmp_path)
    assert run["status"] == "error"
    assert run["kind"] == "invalid_python"
    assert "Invalid Python" in run["message"]


def test_web_unsafe_strategy_fails_closed(tmp_path):
    run = run_web_strategy("import builtins\nclass Strategy:\n    def on_step(self, state):\n        return []\n", "smoke", 1, tmp_path)
    assert run["status"] == "error"
    assert run["kind"] == "unsafe_strategy"
    assert "Unsafe strategy blocked" in run["message"]


def test_web_blocks_builtin_open_escape(tmp_path):
    outside = tmp_path / "outside.txt"
    source = f"class Strategy:\n    def on_step(self, state):\n        __builtins__['open']({str(outside)!r}, 'w').write('x')\n        return []\n"
    run = run_web_strategy(source, "smoke", 1, tmp_path / "runs")
    assert run["status"] == "error"
    assert run["kind"] == "unsafe_strategy"
    assert not outside.exists()


def test_web_timeout_strategy_is_actionable(tmp_path):
    source = "class Strategy:\n    def on_start(self, state):\n        pass\n    def on_step(self, state):\n        while True:\n            pass\n"
    run = run_web_strategy(source, "smoke", 1, tmp_path)
    assert run["status"] == "error"
    assert run["kind"] == "timeout"
    assert "timed out" in run["message"]


def test_web_submit_rejects_disqualified_run(tmp_path):
    run = run_web_strategy("import os\nclass Strategy:\n    pass\n", "smoke", 1, tmp_path)
    submitted = submit_web_run(run.get("run_id", "missing"), tmp_path)
    assert submitted["status"] == "error"


def test_competition_bundle_is_180_simulated_days():
    scen = scenario("competition_6m", 1)
    assert scen.steps == 17_280
    assert scen.step_length_seconds == 900
    assert scen.steps * scen.step_length_seconds == 180 * 24 * 60 * 60
    assert scen.hidden_horizon_label == "180d"
    assert scen.regime_schedule
    assert scen.market.pool_pair == "ETH/USDC"
    assert scen.market.base_token == "USDC"
    assert scen.market.risk_token == "ETH"
    assert scen.market.initial_cash_usdc == Decimal("100000")
    assert scen.market.initial_eth == Decimal("0")
    assert scen.market.price_convention == "USDC per ETH"
    assert scen.market.initial_price > Decimal("100")


def test_score_and_replay_are_money_first_usdc_eth(tmp_path):
    run = run_web_strategy(STARTER, "smoke", 1, tmp_path)
    assert run["status"] == "ok"
    score = run["score"]
    event = run["replay"][-1]
    calibration = run["calibration"]
    for field in [
        "initial_balance_usdc",
        "equity_usd",
        "profit_usd",
        "profit_pct",
        "apr_pct",
        "elapsed_simulated_days",
        "net_profit_usd_after_penalties",
        "eth_price_usdc",
        "net_eth_delta",
        "eth_exposure_usd",
        "delta_penalty_usd",
        "exposure_penalty_usd",
        "fees_earned_usd",
        "lo_edge_usd",
        "borrow_cost_usd",
    ]:
        assert field in score
        assert field in event
    assert score["market"]["pool_pair"] == "ETH/USDC"
    assert score["market"]["initial_balance_usdc"].startswith("100000")
    assert calibration["market"]["pool_pair"] == "ETH/USDC"
    assert Decimal(score["initial_balance_usdc"]) == Decimal("100000")
    assert Decimal(event["eth_price_usdc"]) > Decimal("100")
    assert Decimal(score["net_profit_usd_after_penalties"]) == Decimal(score["score_breakdown"]["scenario_score"])
    expected_apr = (
        Decimal(score["net_profit_usd_after_penalties"])
        / Decimal(score["initial_balance_usdc"])
        * (Decimal("365") / Decimal(score["elapsed_simulated_days"]))
        * Decimal("100")
    )
    assert abs(Decimal(score["apr_pct"]) - expected_apr) < Decimal("0.000000000001")
    assert Decimal(event["elapsed_simulated_days"]) > 0
    assert "apr_pct" in event
    assert "market_stats" in event
    assert "strategy_stats" in event
    assert "dfm" in event
    assert "dfm_lp_fee_pips" in event["dfm"]


def test_web_run_exposes_downloadable_raw_export(tmp_path):
    run = run_web_strategy(STARTER, "smoke", 1, tmp_path)
    assert run["status"] == "ok"
    export = raw_export_path(run["run_id"], tmp_path)
    assert export is not None
    assert export.name == "raw_simulation_export.zip"
    assert export.exists()


def test_noop_strategy_does_not_create_unexplained_usd_profit(tmp_path):
    source = "class Strategy:\n    def on_start(self, state):\n        pass\n    def on_step(self, state):\n        return []\n"
    run = run_web_strategy(source, "smoke", 1, tmp_path)
    assert run["status"] == "ok"
    assert abs(Decimal(run["score"]["net_profit_usd_after_penalties"])) < Decimal("0.000000000001")
    assert abs(Decimal(run["score"]["eth_exposure_usd"])) < Decimal("0.000000000001")


def test_directional_eth_exposure_is_penalized(tmp_path):
    source = "from decimal import Decimal\nfrom aegis_challenge.api import SwapExactIn\nclass Strategy:\n    def on_start(self, state):\n        self.done = False\n    def on_step(self, state):\n        if self.done:\n            return []\n        self.done = True\n        return [SwapExactIn(token_in='token1', amount_in=Decimal('50000'), max_slippage_pips=500000)]\n"
    run = run_web_strategy(source, "smoke", 1, tmp_path)
    assert run["status"] == "ok"
    assert Decimal(run["score"]["max_eth_exposure_usd"]) > Decimal("3000")
    assert Decimal(run["score"]["score_breakdown"]["delta_penalty_usd"]) > 0
    assert Decimal(run["score"]["net_profit_usd_after_penalties"]) < Decimal(run["score"]["profit_usd"])


def test_late_flatten_eth_beta_still_pays_exposure_history_penalty(tmp_path):
    source = """from decimal import Decimal
from aegis_challenge.api import SwapExactIn

class Strategy:
    def on_start(self, state):
        self.entered = False
        self.exited = False

    def on_step(self, state):
        if not self.entered:
            self.entered = True
            return [SwapExactIn(token_in="token1", amount_in=Decimal("90000"), max_slippage_pips=800000)]
        if not self.exited and state.step >= state.config.scenario_steps - 2 and state.vault.idle0 > 0:
            self.exited = True
            return [SwapExactIn(token_in="token0", amount_in=state.vault.idle0, max_slippage_pips=800000)]
        return []
"""
    run = run_web_strategy(source, "smoke", 1, tmp_path)
    assert run["status"] == "ok"
    score = run["score"]
    assert Decimal(score["avg_eth_exposure_usd"]) > Decimal("3000")
    assert Decimal(score["score_breakdown"]["exposure_penalty_usd"]) > 0
    assert Decimal(score["net_profit_usd_after_penalties"]) < Decimal(score["profit_usd"])


def test_progressive_smoke_run_matches_final_runner_semantics(tmp_path):
    strategy = tmp_path / "starter.py"
    strategy.write_text(STARTER)
    cli = run_strategy(strategy, "smoke", 1, tmp_path / "cli")
    started = start_progressive_run(STARTER, "smoke", 1, tmp_path / "web", pace_seconds=0)
    assert started["status"] == "running"
    final = _wait_job(started["job_id"])
    assert final["status"] == "complete"
    assert final["progress"]["total_steps"] == 60
    assert abs(Decimal(final["score"]["score_breakdown"]["scenario_score"]) - Decimal(cli["score"]["score_breakdown"]["scenario_score"])) < Decimal("0.000000000000000001")
    assert abs(Decimal(final["replay"][-1]["score"]) - Decimal(cli["events"][-1]["score"])) < Decimal("0.000000000000000001")
    assert abs(Decimal(final["score"]["apr_pct"]) - Decimal(cli["score"]["apr_pct"])) < Decimal("0.000000000000000001")
    assert Decimal(final["replay"][-1]["elapsed_simulated_days"]) > Decimal("0")
    assert "apr_pct" in final["replay"][-1]


def test_progressive_cancel_does_not_create_submittable_run(tmp_path):
    started = start_progressive_run(STARTER, "competition_6m", 1, tmp_path, pace_seconds=35)
    cancelled = cancel_progressive_run(started["job_id"])
    assert cancelled["status"] == "running"
    final = _wait_job(started["job_id"])
    assert final["status"] == "cancelled"
    submitted = submit_web_run(started["run_id"], tmp_path)
    assert submitted["status"] == "error"


def _wait_job(job_id: str, timeout: float = 10) -> dict:
    deadline = time.time() + timeout
    current = get_progressive_run(job_id)
    while current["status"] == "running" and time.time() < deadline:
        time.sleep(0.05)
        current = get_progressive_run(job_id)
    return current
