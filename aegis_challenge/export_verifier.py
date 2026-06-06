from __future__ import annotations

import json
import zipfile
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 60


def verify_run_export(run_dir: str | Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    failures: list[str] = []
    replay = read_jsonl(run_dir / "public_replay.jsonl")
    trades = read_jsonl(run_dir / "trades.jsonl")
    periods = read_jsonl(run_dir / "period_stats.jsonl")
    market_path_rows = read_jsonl(run_dir / "market_path_stats.jsonl")
    market_path_json = json.loads((run_dir / "market_path_stats.json").read_text()) if (run_dir / "market_path_stats.json").exists() else []
    period_json = json.loads((run_dir / "period_stats.json").read_text()) if (run_dir / "period_stats.json").exists() else []
    debts = read_jsonl(run_dir / "debt_snapshots.jsonl")
    actions = read_jsonl(run_dir / "actions.jsonl")
    score = json.loads((run_dir / "score.json").read_text())
    calibration = json.loads((run_dir / "calibration.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text()) if (run_dir / "manifest.json").exists() else {}

    if not replay:
        failures.append("public_replay.jsonl is empty")
    if len(replay) != int(calibration.get("steps", 0)):
        failures.append(f"replay steps {len(replay)} != calibration steps {calibration.get('steps')}")
    if len(periods) != len(replay):
        failures.append(f"period rows {len(periods)} != replay rows {len(replay)}")
    if len(period_json) != len(periods):
        failures.append(f"period_stats.json rows {len(period_json)} != period_stats.jsonl rows {len(periods)}")
    if len(market_path_rows) != len(replay):
        failures.append(f"market path rows {len(market_path_rows)} != replay rows {len(replay)}")
    if len(market_path_json) != len(market_path_rows):
        failures.append(f"market_path_stats.json rows {len(market_path_json)} != market_path_stats.jsonl rows {len(market_path_rows)}")
    if len(debts) != len(replay):
        failures.append(f"debt snapshot rows {len(debts)} != replay rows {len(replay)}")

    if replay:
        final = replay[-1]
        expected_days = Decimal(str(calibration.get("steps", 0))) * Decimal(str(calibration.get("step_length_seconds", 0))) / Decimal(86400)
        assert_close(Decimal(str(final.get("elapsed_simulated_days", "0"))), expected_days, Decimal("0.0001"), "final elapsed days", failures)
        assert_close(Decimal(str(score.get("elapsed_simulated_days", "0"))), expected_days, Decimal("0.0001"), "score elapsed days", failures)
        assert_close(Decimal(str(score.get("net_profit_usd_after_penalties", "0"))), Decimal(str(final.get("net_profit_usd_after_penalties", "0"))), Decimal("0.000000000001"), "final net profit", failures)
        assert_close(Decimal(str(score.get("score_breakdown", {}).get("scenario_score", "0"))), Decimal(str(final.get("score", "0"))), Decimal("0.000000000001"), "final score", failures)
        assert_close(Decimal(str(score.get("equity_usd", "0"))), Decimal(str(final.get("equity_usd", "0"))), Decimal("0.000001"), "final equity", failures)
        assert_close(Decimal(str(score.get("eth_exposure_usd", "0"))), Decimal(str(final.get("eth_exposure_usd", "0"))), Decimal("0.000001"), "final exposure", failures)
        expected_apr = (
            Decimal(str(final.get("net_profit_usd_after_penalties", "0")))
            / Decimal(str(final.get("initial_balance_usdc", "1")))
            * (Decimal("365") / Decimal(str(final.get("elapsed_simulated_days", "1"))))
            * Decimal("100")
        )
        assert_close(Decimal(str(final.get("apr_pct", "0"))), expected_apr, Decimal("0.000000000001"), "final APR", failures)
        assert_close(Decimal(str(score.get("apr_pct", "0"))), expected_apr, Decimal("0.000000000001"), "score APR", failures)
        if Decimal(str(final.get("elapsed_simulated_days", "0"))).quantize(Decimal("0.0001")) != Decimal("180.0000") and calibration.get("bundle") == "competition_6m":
            failures.append("competition replay does not end on day 180")

    for index, (event, period) in enumerate(zip(replay, periods)):
        check_event_period_parity(index, event, period, failures)
    for index, (event, path_row) in enumerate(zip(replay, market_path_rows)):
        check_market_path_parity(index, event, path_row, failures)
    for index, (event, debt) in enumerate(zip(replay, debts)):
        check_debt_snapshot_parity(index, event, debt, failures)

    period_trade_count = sum(int(row.get("trade_count", 0)) for row in periods)
    exported_child_trade_count = sum(int(row.get("child_trade_count", 1)) for row in trades)
    if period_trade_count != exported_child_trade_count:
        failures.append(f"period trade count {period_trade_count} != exported child trades {exported_child_trade_count}")
    period_volume = sum_decimal(periods, "volume_usd")
    trade_volume = sum_decimal(trades, "notional_usd")
    assert_close(period_volume, trade_volume, Decimal("0.000001"), "trade volume", failures)
    period_lp_fees = sum_decimal(periods, "lp_fees_usd")
    trade_lp_fees = sum_decimal(trades, "lp_fee_usd")
    assert_close(period_lp_fees, trade_lp_fees, Decimal("0.000001"), "LP fees", failures)
    period_base_lp_fees = sum_decimal(periods, "base_lp_fees_usd")
    trade_base_lp_fees = sum_decimal(trades, "base_lp_fee_usd")
    assert_close(period_base_lp_fees, trade_base_lp_fees, Decimal("0.000001"), "base LP fees", failures)
    period_dfm_lp_lift = sum_decimal(periods, "dfm_lp_fee_lift_usd")
    trade_dfm_lp_lift = sum_decimal(trades, "dfm_lp_fee_lift_usd")
    assert_close(period_dfm_lp_lift, trade_dfm_lp_lift, Decimal("0.000001"), "DFM LP fee lift", failures)
    assert_close(period_base_lp_fees + period_dfm_lp_lift, period_lp_fees, Decimal("0.000001"), "base LP fees plus DFM LP lift", failures)
    period_hook_fees = sum_decimal(periods, "dfm_hook_fees_usd")
    trade_hook_fees = sum_decimal(trades, "dfm_hook_fee_usd")
    assert_close(period_hook_fees, trade_hook_fees, Decimal("0.000001"), "DFM hook fees", failures)
    period_slippage_weighted = weighted_average(periods, "average_price_impact_pct", "execution_swap_count")
    trade_slippage_weighted = average_decimal(trades, "price_impact_pct")
    assert_close(period_slippage_weighted, trade_slippage_weighted, Decimal("0.000001"), "price impact", failures)

    dfm_rows = [row for row in periods if truthy(row.get("dfm_dynamic_fee_active"))]
    surge_rows = [row for row in periods if truthy(row.get("dfm_surge_triggered"))]
    if calibration.get("fee_model") == "aegis_dynamic" or score.get("bundle") == "competition_6m":
        if not dfm_rows:
            failures.append("aegis_dynamic run has no DFM rows")
        if not surge_rows and score.get("bundle") == "competition_6m":
            failures.append("competition run has no DFM surge rows")
    for row in surge_rows[:100]:
        if Decimal(str(row.get("dfm_lp_fee_pips", "0"))) <= Decimal(str(row.get("dfm_base_fee_pips", "0"))):
            failures.append(f"DFM surge step {row.get('step')} does not increase LP fee pips")
            break
        if Decimal(str(row.get("lp_fees_usd", "0") or "0")) > 0 and Decimal(str(row.get("dfm_lp_fee_lift_usd", "0") or "0")) <= 0:
            failures.append(f"DFM surge step {row.get('step')} has CL fees but no DFM LP fee lift")
            break
        if not row.get("dfm_surge_reason"):
            failures.append(f"DFM surge step {row.get('step')} missing reason")
            break

    rejected_actions = [row for row in actions if row.get("status") == "rejected"]
    executed_actions = [row for row in actions if row.get("status") == "executed"]
    zip_ok = zipfile.is_zipfile(run_dir / "raw_simulation_export.zip")
    if not zip_ok:
        failures.append("raw_simulation_export.zip is missing or invalid")
    for required in ["public_replay.jsonl", "score.json", "calibration.json", "trades.jsonl", "period_stats.jsonl", "period_stats.json", "period_stats.csv", "market_path_stats.jsonl", "market_path_stats.json", "debt_snapshots.jsonl"]:
        if required not in manifest.get("files", {}):
            failures.append(f"manifest missing {required}")
    public_text = "\n".join(
        [
            json.dumps(score).lower(),
            json.dumps(calibration).lower(),
            json.dumps(replay[:10]).lower(),
            json.dumps(market_path_rows[:10]).lower(),
        ]
    )
    for forbidden in ["fair_price", "hidden_fair", "future_flow", "private_runner_state"]:
        if forbidden in public_text:
            failures.append(f"public artifacts leak forbidden market field {forbidden}")

    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "metrics": {
            "replay_steps": len(replay),
            "trade_rows": len(trades),
            "child_trade_count": exported_child_trade_count,
            "period_trade_count": period_trade_count,
            "volume_usd": str(period_volume),
            "lp_fees_usd": str(period_lp_fees),
            "base_lp_fees_usd": str(period_base_lp_fees),
            "dfm_lp_fee_lift_usd": str(period_dfm_lp_lift),
            "dfm_hook_fees_usd": str(period_hook_fees),
            "average_price_impact_pct": str(trade_slippage_weighted),
            "dfm_surge_steps": len(surge_rows),
            "market_path_rows": len(market_path_rows),
            "executed_strategy_actions": len(executed_actions),
            "rejected_strategy_actions": len(rejected_actions),
            "zip_ok": zip_ok,
        },
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_event_period_parity(index: int, event: dict[str, Any], period: dict[str, Any], failures: list[str]) -> None:
    if event.get("step") != period.get("step"):
        failures.append(f"period step mismatch at row {index}: {event.get('step')} != {period.get('step')}")
        return
    pairs = [
        ("elapsed_simulated_days", "simulated_day", Decimal("0.0001")),
        ("price", "price_usdc_per_eth", Decimal("0.000000000001")),
        ("net_profit_usd_after_penalties", "net_profit_usd_after_penalties", Decimal("0.000000000001")),
        ("apr_pct", "apr_pct", Decimal("0.000000000001")),
        ("eth_exposure_usd", "eth_exposure_usd", Decimal("0.000001")),
    ]
    for event_field, period_field, tolerance in pairs:
        assert_close(
            Decimal(str(event.get(event_field, "0") or "0")),
            Decimal(str(period.get(period_field, "0") or "0")),
            tolerance,
            f"{event_field}/{period_field} step {event.get('step')}",
            failures,
        )
    market = event.get("market_stats") or {}
    for field in [
        "trade_count",
        "execution_swap_count",
        "volume_usd",
        "lp_fees_usd",
        "base_lp_fees_usd",
        "dfm_lp_fee_lift_usd",
        "dfm_hook_fees_usd",
        "average_price_impact_pct",
        "max_price_impact_pct",
        "planned_retail_swaps",
        "trade_intensity",
        "stochastic_volatility",
    ]:
        assert_close(
            Decimal(str(market.get(field, "0") or "0")),
            Decimal(str(period.get(field, "0") or "0")),
            Decimal("0.000001"),
            f"market {field} step {event.get('step')}",
            failures,
        )
    dfm = event.get("dfm") or {}
    for field in ["dfm_base_fee_bps", "dfm_hook_fee_bps", "dfm_total_fee_bps", "dfm_fee_multiplier"]:
        assert_close(
            Decimal(str(dfm.get(field, "0") or "0")),
            Decimal(str(period.get(field, "0") or "0")),
            Decimal("0.000000000001"),
            f"DFM {field} step {event.get('step')}",
            failures,
        )


def check_market_path_parity(index: int, event: dict[str, Any], path_row: dict[str, Any], failures: list[str]) -> None:
    path = event.get("market_path") or {}
    if event.get("step") != path_row.get("step"):
        failures.append(f"market path step mismatch at row {index}: {event.get('step')} != {path_row.get('step')}")
        return
    for field in [
        "engine_version",
        "calibration_hash",
        "regime",
        "jump_event",
        "planned_retail_swaps",
        "whale_count",
    ]:
        if str(path.get(field)) != str(path_row.get(field)):
            failures.append(f"market path {field} mismatch at step {event.get('step')}")
            return
    for field in [
        "stochastic_volatility",
        "jump_return_pct",
        "trade_intensity",
        "base_lambda",
        "flow_imbalance",
        "mean_trade_size_usd",
    ]:
        assert_close(
            Decimal(str(path.get(field, "0") or "0")),
            Decimal(str(path_row.get(field, "0") or "0")),
            Decimal("0.000000000001"),
            f"market path {field} step {event.get('step')}",
            failures,
        )


def check_debt_snapshot_parity(index: int, event: dict[str, Any], debt: dict[str, Any], failures: list[str]) -> None:
    if event.get("step") != debt.get("step"):
        failures.append(f"debt step mismatch at row {index}: {event.get('step')} != {debt.get('step')}")
        return
    vault = event.get("vault") or {}
    for field in ["debt_l", "borrow_index", "debt_liability0", "debt_liability1", "debt_liability_value", "ltv_pips", "collateral_floor_l"]:
        assert_close(
            Decimal(str(vault.get(field, "0") or "0")),
            Decimal(str(debt.get(field, "0") or "0")),
            Decimal("0.000001"),
            f"debt {field} step {event.get('step')}",
            failures,
        )
    for field in ["equity_usd", "net_eth_delta", "eth_exposure_usd"]:
        assert_close(
            Decimal(str(event.get(field, "0") or "0")),
            Decimal(str(debt.get(field, "0") or "0")),
            Decimal("0.000001"),
            f"debt event {field} step {event.get('step')}",
            failures,
        )


def sum_decimal(rows: list[dict[str, Any]], field: str) -> Decimal:
    return sum((Decimal(str(row.get(field, "0") or "0")) for row in rows), Decimal("0"))


def average_decimal(rows: list[dict[str, Any]], field: str) -> Decimal:
    if not rows:
        return Decimal("0")
    return sum_decimal(rows, field) / Decimal(len(rows))


def weighted_average(rows: list[dict[str, Any]], value_field: str, weight_field: str) -> Decimal:
    numerator = Decimal("0")
    denominator = Decimal("0")
    for row in rows:
        weight = Decimal(str(row.get(weight_field, "0") or "0"))
        numerator += Decimal(str(row.get(value_field, "0") or "0")) * weight
        denominator += weight
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def assert_close(actual: Decimal, expected: Decimal, tolerance: Decimal, label: str, failures: list[str]) -> None:
    if abs(actual - expected) > tolerance:
        failures.append(f"{label} mismatch: actual {actual} expected {expected} tolerance {tolerance}")


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"
