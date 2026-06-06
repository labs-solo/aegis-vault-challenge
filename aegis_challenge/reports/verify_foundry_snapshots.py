from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_snapshot_paths(
    uniswap_fixture_path: str | Path = "tests/golden/uniswap_v4_vectors.json",
    aegis_fixture_path: str | Path = "tests/golden/aegis_vault_vectors.json",
    uniswap_snapshot_path: str | Path = "reports/golden/foundry-uniswap-v4-reference.json",
    aegis_snapshot_path: str | Path = "reports/golden/foundry-aegis-vault-reference.json",
) -> dict:
    errors: list[dict] = []
    uniswap_fixture = json.loads(Path(uniswap_fixture_path).read_text())
    aegis_fixture = json.loads(Path(aegis_fixture_path).read_text())
    uniswap_snapshot = json.loads(Path(uniswap_snapshot_path).read_text())
    aegis_snapshot = json.loads(Path(aegis_snapshot_path).read_text())

    errors.extend(_check_foundry_version(uniswap_snapshot_path, uniswap_snapshot))
    errors.extend(_check_foundry_version(aegis_snapshot_path, aegis_snapshot))
    errors.extend(_verify_uniswap(uniswap_fixture, uniswap_snapshot["values"]))
    errors.extend(_verify_aegis(aegis_fixture, aegis_snapshot["values"]))

    return {
        "status": "pass" if not errors else "fail",
        "checked": [
            str(uniswap_snapshot_path),
            str(aegis_snapshot_path),
        ],
        "errors": errors,
    }


def _check_foundry_version(path: str | Path, snapshot: dict) -> list[dict]:
    if snapshot.get("fixture_version") == "aegis-vault-challenge-v1-foundry-snapshot":
        return []
    return [{"path": str(path), "field": "fixture_version", "error": "unexpected foundry snapshot version"}]


def _verify_uniswap(fixture: dict, foundry: dict) -> list[dict]:
    vectors = fixture["vectors"]
    expected = {
        "tick_min_sqrt_price_x96": vectors[0]["expected"]["sqrt_price_x96"][0],
        "tick_zero_sqrt_price_x96": vectors[0]["expected"]["sqrt_price_x96"][1],
        "tick_max_sqrt_price_x96": vectors[0]["expected"]["sqrt_price_x96"][2],
        "swap0_sqrt_price_x96_after": vectors[1]["expected"]["sqrt_price_x96_after"],
        "swap0_amount0_in": vectors[1]["expected"]["amount0_in"],
        "swap0_amount1_out": vectors[1]["expected"]["amount1_out"],
        "swap0_fee_amount": "0",
        "swap0_final_tick": str(vectors[1]["expected"]["final_tick"]),
        "swap1_sqrt_price_x96_after": vectors[2]["expected"]["sqrt_price_x96_after"],
        "swap1_amount1_in": vectors[2]["expected"]["amount1_in"],
        "swap1_amount0_out": vectors[2]["expected"]["amount0_out"],
        "swap1_fee_amount": "0",
        "swap1_final_tick": str(vectors[2]["expected"]["final_tick"]),
        "tick_up_amount_in_consumed": vectors[3]["expected"]["amount_in_consumed"],
        "tick_down_amount_in_consumed": vectors[4]["expected"]["amount_in_consumed"],
        "fee_growth_global0_delta_x128": vectors[5]["expected"]["fee_growth_global0_delta_x128"],
    }
    return _compare("uniswap", expected, foundry)


def _verify_aegis(fixture: dict, foundry: dict) -> list[dict]:
    vectors = {vector["id"]: vector for vector in fixture["vectors"]}
    expected = {
        "full_range_min_tick": str(vectors["AE-DEBT-MARK-001"]["input"]["full_range_min_tick"]),
        "full_range_max_tick": str(vectors["AE-DEBT-MARK-001"]["input"]["full_range_max_tick"]),
        "borrow_liquidity_removed": vectors["AE-BORROW-001"]["expected"]["liquidity_removed"],
        "borrow_idle0_delta": vectors["AE-BORROW-001"]["expected"]["idle0_delta"],
        "borrow_idle1_delta": vectors["AE-BORROW-001"]["expected"]["idle1_delta"],
        "repay_target_liquidity": vectors["AE-REPAY-001"]["expected"]["target_liquidity"],
        "repay_geometric_mean": vectors["AE-REPAY-001"]["expected"]["geometric_mean"],
        "repay_actual_repaid_l": vectors["AE-REPAY-001"]["expected"]["actual_repaid_l"],
        "ltv_idle_collateral_floor_l": vectors["AE-LTV-001"]["expected"]["collateral_floor_l"],
        "ltv_idle_ltv_pips": vectors["AE-LTV-001"]["expected"]["ltv_pips"],
        "ltv_one_sided_collateral_floor_l": vectors["AE-LTV-002"]["expected"]["collateral_floor_l"],
        "ltv_one_sided_ltv_pips": vectors["AE-LTV-002"]["expected"]["ltv_pips"],
        "lock_reject_ltv_pips": vectors["AE-LOCK-001"]["expected"]["ltv_pips"],
        "interest_delta_borrow_index_wad": vectors["AE-INTEREST-001"]["expected"]["delta_borrow_index_wad"],
        "interest_borrow_index_wad_after": vectors["AE-INTEREST-001"]["expected"]["borrow_index_wad_after"],
        "interest_accrued_wad": vectors["AE-INTEREST-001"]["expected"]["interest_accrued_wad"],
        "debt_mark_target_liquidity": vectors["AE-DEBT-MARK-001"]["expected"]["iterations"][0]["target_liquidity"],
        "debt_mark_liability0": vectors["AE-DEBT-MARK-001"]["expected"]["liability0"],
        "debt_mark_liability1": vectors["AE-DEBT-MARK-001"]["expected"]["liability1"],
        "debt_mark_geometric_mean": vectors["AE-DEBT-MARK-001"]["expected"]["iterations"][0]["geometric_mean"],
        "debt_mark_repaid_l": vectors["AE-DEBT-MARK-001"]["expected"]["iterations"][0]["repaid_l"],
        "debt_repayment_value": vectors["AE-DEBT-MARK-001"]["expected"]["debt_repayment_value"],
        "hook_fee_exact_in_10000_fee4000_cut1000": vectors["AE-HOOK-FEE-001"]["expected"]["hook_fee_token0"],
        "hook_fee_exact_in_10000_fee4000_cut500000": vectors["AE-HOOK-REINVEST-001"]["expected"]["current_swap_hook_fee_token0"],
        "hook_reinvest_min_liquidity": "1000",
        "limit_order_tick_lower": str(vectors["AE-LO-001"]["input"]["tick"]),
        "limit_order_tick_upper_for_spacing60": str(vectors["AE-LO-001"]["input"]["tick"] + 60),
        "limit_order_lower_liquidity_net": vectors["AE-LO-001"]["expected"]["tick_lower_liquidity_net_after_place"],
        "limit_order_upper_liquidity_net": vectors["AE-LO-001"]["expected"]["tick_upper_liquidity_net_after_place"],
        "limit_order_amount0_for_liquidity1000_tick60_120": vectors["AE-LO-EPOCH-001"]["expected"]["order_1_deposited0"],
        "limit_order_amount0_for_liquidity2000_tick60_120": vectors["AE-LO-EPOCH-001"]["expected"]["order_2_deposited0"],
        "limit_order_amount1_for_liquidity3000_tick60_120": vectors["AE-LO-EPOCH-001"]["expected"]["total_claimable1"],
        "repair_repay_fraction_pips": vectors["AE-REPAIR-001"]["expected"]["repay_fraction_pips"],
        "repair_keeper_fee_pips": vectors["AE-REPAIR-001"]["expected"]["keeper_fee_pips"],
        "peel_bounty_pips": vectors["AE-PEEL-001"]["expected"]["peel_bounty_pips"],
        "repair_swap_deficit_zero_for_one": str(vectors["AE-REPAIR-SWAP-001"]["expected"]["deficit_zero_for_one"]).lower(),
        "repair_swap_deficit_exact_out": vectors["AE-REPAIR-SWAP-001"]["expected"]["deficit_exact_out"],
    }
    return _compare("aegis", expected, foundry)


def _compare(domain: str, expected: dict[str, str], actual: dict[str, str]) -> list[dict]:
    errors: list[dict] = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            errors.append({"domain": domain, "field": key, "expected": expected_value, "actual": actual_value})
    for key in sorted(set(actual) - set(expected)):
        errors.append({"domain": domain, "field": key, "error": "unexpected snapshot field"})
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aegis_challenge.reports.verify_foundry_snapshots")
    parser.parse_args(argv)
    result = verify_snapshot_paths()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
