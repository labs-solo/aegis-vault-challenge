import hashlib
import json
import zipfile
from decimal import Decimal
from pathlib import Path

from aegis_challenge.dfm import apply_dfm_fee_state
from aegis_challenge.export_verifier import verify_run_export
from aegis_challenge.flow import scenario
from aegis_challenge.pool import Pool
from aegis_challenge.runner import replay, run_strategy


def test_starter_runs_and_writes_artifacts(tmp_path):
    result = run_strategy("examples/starter_strategy.py", "smoke", 1, tmp_path)
    run_dir = Path(result["run_dir"])
    assert (run_dir / "public_replay.jsonl").exists()
    assert (run_dir / "score.json").exists()
    assert (run_dir / "comparison.json").exists()
    assert (run_dir / "calibration.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "trades.jsonl").exists()
    assert (run_dir / "actions.jsonl").exists()
    assert (run_dir / "period_stats.jsonl").exists()
    assert (run_dir / "period_stats.json").exists()
    assert zipfile.is_zipfile(run_dir / "raw_simulation_export.zip")
    assert len(replay(run_dir / "public_replay.jsonl")) == 60


def test_all_examples_run_smoke(tmp_path):
    examples = [
        "examples/starter_strategy.py",
        "examples/00_hold_idle.py",
        "examples/01_basic_delta_neutral_cl.py",
        "examples/02_limit_order_rebalancer.py",
    ]
    for example in examples:
        result = run_strategy(example, "smoke", 1, tmp_path)
        run_dir = Path(result["run_dir"])
        assert (run_dir / "public_replay.jsonl").exists()
        assert (run_dir / "score.json").exists()
        assert (run_dir / "comparison.json").exists()
        assert (run_dir / "calibration.json").exists()


def test_replay_is_deterministic(tmp_path):
    first = run_strategy("examples/00_hold_idle.py", "smoke", 1, tmp_path / "a")
    second = run_strategy("examples/00_hold_idle.py", "smoke", 1, tmp_path / "b")
    one = Path(first["run_dir"]) / "public_replay.jsonl"
    two = Path(second["run_dir"]) / "public_replay.jsonl"
    assert hashlib.sha256(one.read_bytes()).hexdigest() == hashlib.sha256(two.read_bytes()).hexdigest()


def test_public_replay_has_no_hidden_seed(tmp_path):
    result = run_strategy("examples/00_hold_idle.py", "smoke", 1, tmp_path)
    text = (Path(result["run_dir"]) / "public_replay.jsonl").read_text()
    assert "hidden" not in text.lower()
    assert '"seed"' not in text


def test_raw_export_independent_verifier_passes_smoke(tmp_path):
    result = run_strategy("examples/starter_strategy.py", "smoke", 1, tmp_path)
    run_dir = Path(result["run_dir"])
    verification = verify_run_export(run_dir)
    assert verification["status"] == "pass"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["schema"] == "aegis-vault-raw-simulation-export/v1"
    assert "public_replay.jsonl" in manifest["files"]
    assert "period_stats.json" in manifest["files"]
    periods = json.loads((run_dir / "period_stats.json").read_text())
    assert len(periods) == 60
    assert "base_lp_fees_usd" in periods[0]
    assert "dfm_lp_fee_lift_usd" in periods[0]


def test_public_train_export_splits_dfm_cl_fee_lift(tmp_path):
    result = run_strategy("examples/00_hold_idle.py", "public_train", 8, tmp_path)
    run_dir = Path(result["run_dir"])
    verification = verify_run_export(run_dir)
    assert verification["status"] == "pass"
    periods = json.loads((run_dir / "period_stats.json").read_text())
    surge_periods = [row for row in periods if row.get("dfm_surge_triggered") and Decimal(str(row.get("lp_fees_usd", "0"))) > 0]
    assert surge_periods
    assert any(Decimal(str(row.get("dfm_lp_fee_lift_usd", "0"))) > 0 for row in surge_periods)
    assert Decimal(str(verification["metrics"]["dfm_lp_fee_lift_usd"])) > 0


def test_dfm_surge_increases_lp_fee_growth_for_cl_liquidity():
    amount_in = Decimal("10000")
    static_pool = Pool(price=Decimal("2000"), active_liquidity=2_000_000, amount_scale=1_000_000)
    dynamic_pool = Pool(price=Decimal("2000"), active_liquidity=2_000_000, amount_scale=1_000_000)
    scen = scenario("public_train", 8)
    dfm_state = apply_dfm_fee_state(dynamic_pool, scen, "volatile", 0)

    static_swap = static_pool.swap_exact_in("retail", "token1", amount_in, 0)
    dynamic_swap = dynamic_pool.swap_exact_in("retail", "token1", amount_in, 0)

    assert dfm_state["dfm_surge_triggered"] is True
    assert dfm_state["dfm_lp_fee_pips"] > dfm_state["dfm_base_fee_pips"]
    assert dynamic_swap.lp_fee_paid > static_swap.lp_fee_paid
    assert dynamic_pool.fee_growth_global1_x128 > static_pool.fee_growth_global1_x128
    assert dynamic_swap.hook_fee_paid > 0


def test_replay_apr_annualizes_by_elapsed_days_not_full_horizon(tmp_path):
    result = run_strategy("examples/starter_strategy.py", "smoke", 1, tmp_path)
    events = result["events"]
    event = events[4]
    expected_apr = (
        Decimal(event["net_profit_usd_after_penalties"])
        / Decimal(event["initial_balance_usdc"])
        * (Decimal("365") / Decimal(event["elapsed_simulated_days"]))
        * Decimal("100")
    )
    fixed_horizon_apr = (
        Decimal(event["net_profit_usd_after_penalties"])
        / Decimal(event["initial_balance_usdc"])
        * (Decimal("365") / Decimal("180"))
        * Decimal("100")
    )
    assert abs(Decimal(event["apr_pct"]) - expected_apr) < Decimal("0.000000000001")
    assert abs(Decimal(event["apr_pct"]) - fixed_horizon_apr) > Decimal("1")
