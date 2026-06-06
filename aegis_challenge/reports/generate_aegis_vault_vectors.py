from __future__ import annotations

import json
from decimal import Decimal

from aegis_challenge.aegis_market import AegisMarket, debt_repayment_liability, full_range_amounts_for_liquidity, full_range_ticks, keeper_fee_pips, liquidity_for_principal, micro_liq_swap_deficit, repay_bridge, repay_fraction_pips
from aegis_challenge.api import BorrowL, CancelLimitOrder, MintRange, PlaceLimitOrder, SwapExactIn, WithdrawLimitOrder
from aegis_challenge.pool import Pool
from aegis_challenge.runner import apply_action, repair_vault
from aegis_challenge.vault import Vault


FIXTURE_VERSION = "aegis-vault-challenge-v1"
GENERATOR = {
    "aegis_engine_commit": "08d389e8b7c53cac1cc9ba05a85dfee596672465",
    "v4_core_commit": "59d3ecf53afa9264a16bba0e38f4c5d2231f80bc",
    "v4_periphery_commit": "60cd93803ac2b7fa65fd6cd351fd5fd4cc8c9db5",
    "rounding_policy": "local-python-aegis-reference-subset",
}


def build_vectors() -> dict:
    return {
        "fixture_version": FIXTURE_VERSION,
        "generator": GENERATOR,
        "vectors": [
            borrow_vector(),
            repay_vector(),
            ltv_idle_vector(),
            ltv_one_sided_vector(),
            lock_reject_vector(),
            interest_vector(),
            limit_order_fill_vector(),
            same_step_limit_order_vector(),
            hook_fee_vector(),
            hook_reinvest_vector(),
            nft_cap_vector(),
            debt_mark_vector(),
            repair_vector(),
            peel_vector(),
            repair_swap_vector(),
            limit_order_epoch_payout_vector(),
        ],
    }


def borrow_vector() -> dict:
    vault = Vault(idle0=Decimal("0"), idle1=Decimal("100000"))
    market = AegisMarket()
    apply_action(BorrowL(amount_l=1000), vault, Pool(), market, 0)
    liquidity_removed = liquidity_for_principal(1000, market.borrow_index_wad)
    idle0_delta, idle1_delta = full_range_amounts_for_liquidity(liquidity_removed, Decimal("1"), 60)
    return {
        "id": "AE-BORROW-001",
        "input": {
            "price": "1",
            "borrow_index_wad": "1000000000000000000",
            "vault_rL_before": "0",
            "vault_idle0_before": "0",
            "vault_idle1_before": "100000",
            "borrow_amount_l": "1000",
        },
        "expected": {
            "liquidity_removed": str(liquidity_removed),
            "idle0_delta": str(idle0_delta),
            "idle1_delta": str(idle1_delta),
            "vault_rL_after": str(vault.debt_l),
            "market_total_rL_after": str(market.total_rL_borrowed),
        },
        "source": "Aegis Vault.borrow L-unit accounting subset",
    }


def repay_vector() -> dict:
    bridge = repay_bridge(500, Decimal("1000"), Decimal("1000"), 1_050_000_000_000_000_000)
    return {
        "id": "AE-REPAY-001",
        "input": {
            "borrow_index_wad": "1050000000000000000",
            "vault_rL_before": "1000",
            "requested_repay_l": "500",
            "idle0": "1000",
            "idle1": "1000",
        },
        "expected": {
            "target_liquidity": str(bridge["target_liquidity"]),
            "idle0_consumed": str(bridge["idle0_consumed"]),
            "idle1_consumed": str(bridge["idle1_consumed"]),
            "geometric_mean": str(bridge["geometric_mean"]),
            "actual_repaid_l": str(bridge["actual_repaid_l"]),
            "vault_rL_after": "500",
        },
        "source": "Aegis Vault.repay conservative bridge subset",
    }


def ltv_idle_vector() -> dict:
    vault = Vault(idle0=Decimal("100"), idle1=Decimal("400"), debt_l=100, borrow_index=10**18)
    state = vault.state(Decimal("1"))
    return {
        "id": "AE-LTV-001",
        "input": {"idle0": "100", "idle1": "400", "rL": "100", "borrow_index_wad": "1000000000000000000"},
        "expected": {
            "collateral_floor_l": str(state.collateral_floor_l),
            "debt_l_wad": str(vault.debt_l * vault.borrow_index),
            "ltv_pips": str(state.ltv_pips),
        },
        "source": "Aegis Vault.computeLtvPips idle-only subset",
    }


def ltv_one_sided_vector() -> dict:
    vault = Vault(idle0=Decimal("100"), idle1=Decimal("0"), debt_l=1, borrow_index=10**18)
    state = vault.state(Decimal("1"))
    return {
        "id": "AE-LTV-002",
        "input": {"idle0": "100", "idle1": "0", "rL": "1", "borrow_index_wad": "1000000000000000000", "attached_positions": 0},
        "expected": {"collateral_floor_l": str(state.collateral_floor_l), "ltv_pips": str(state.ltv_pips), "lock_error": "ERR_MAX_LTV"},
        "source": "Aegis Vault.computeLtvPips one-sided idle subset",
    }


def lock_reject_vector() -> dict:
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000"), debt_l=901, borrow_index=10**18)
    state = vault.state(Decimal("1"))
    return {
        "id": "AE-LOCK-001",
        "input": {"max_ltv_pips": 900000, "collateral_floor_l": "1000", "rL": "901", "borrow_index_wad": "1000000000000000000"},
        "expected": {"ltv_pips": str(state.ltv_pips), "lock_error": "ERR_MAX_LTV"},
        "source": "Aegis Engine lockVault max-LTV rejection subset",
    }


def interest_vector() -> dict:
    market = AegisMarket(total_rL_borrowed=100_000, borrow_index_wad=10**18)
    before = market.borrow_index_wad
    interest_wad = market.accrue_at_rate(60, 1_000_000_000)
    return {
        "id": "AE-INTEREST-001",
        "input": {"borrow_index_wad": str(before), "total_rL_borrowed": "100000", "rate_per_second_wad": "1000000000", "dt": "60"},
        "expected": {
            "delta_borrow_index_wad": str(market.borrow_index_wad - before),
            "borrow_index_wad_after": str(market.borrow_index_wad),
            "interest_accrued_wad": str(interest_wad),
        },
        "source": "Aegis Market.accrue subset",
    }


def limit_order_fill_vector() -> dict:
    pool = Pool()
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), vault, pool, market, 0)
    lower_net_after_place = pool.initialized_ticks.get(60, 0)
    upper_net_after_place = pool.initialized_ticks.get(120, 0)
    _, swaps, fills = apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), vault, pool, market, 0)
    filled = vault.limit_orders[0]
    lower_net_after_fill = pool.initialized_ticks.get(60, 0)
    upper_net_after_fill = pool.initialized_ticks.get(120, 0)
    cancel_vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    cancel_pool = Pool()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), cancel_vault, cancel_pool, market, 0)
    apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), cancel_vault, cancel_pool, market, 0)
    before0, before1 = cancel_vault.idle0, cancel_vault.idle1
    apply_action(CancelLimitOrder(order_id=1), cancel_vault, cancel_pool, market, 1)
    withdraw_vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    withdraw_pool = Pool()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), withdraw_vault, withdraw_pool, market, 0)
    apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), withdraw_vault, withdraw_pool, market, 0)
    wbefore0, wbefore1 = withdraw_vault.idle0, withdraw_vault.idle1
    apply_action(WithdrawLimitOrder(order_id=1), withdraw_vault, withdraw_pool, market, 1)
    return {
        "id": "AE-LO-001",
        "input": {"current_tick": 0, "tick_spacing": 60, "side": "sell0", "tick": 60, "liquidity": "1000", "swap_token_in": "token1"},
        "expected": {
            "order_status_after_cross": filled.status,
            "claimable0": str(filled.claimable0),
            "claimable1": str(filled.claimable1),
            "fill_event_index": fills[0].event_index,
            "swap_event_index": swaps[0].event_index,
            "cancel_idle0_delta": str(cancel_vault.idle0 - before0),
            "cancel_idle1_delta": str(cancel_vault.idle1 - before1),
            "withdraw_idle0_delta": str(withdraw_vault.idle0 - wbefore0),
            "withdraw_idle1_delta": str(withdraw_vault.idle1 - wbefore1),
            "tick_lower_liquidity_net_after_place": str(lower_net_after_place),
            "tick_upper_liquidity_net_after_place": str(upper_net_after_place),
            "tick_lower_liquidity_net_after_fill": str(lower_net_after_fill),
            "tick_upper_liquidity_net_after_fill": str(upper_net_after_fill),
        },
        "source": "Aegis LimitOrderManager fill/cancel/withdraw local subset",
    }


def same_step_limit_order_vector() -> dict:
    pool = Pool()
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), vault, pool, market, 0)
    _, retail_swaps, retail_fills = apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), vault, pool, market, 0)
    open_before_arbitrage = sum(1 for order in vault.limit_orders if order.status == "open")
    arbitrage_swap = pool.swap_exact_in("arbitrage", "token0", Decimal("1000"), 0)
    return {
        "id": "AE-LO-002",
        "input": {"priority_model": "baseline_batch", "market_event_0": "retail token1 exact-in crosses LO", "market_event_1": "same-step arbitrage"},
        "expected": {
            "market_event_0_filled_order_ids": [fill.order_id for fill in retail_fills],
            "order_open_before_market_event_1": open_before_arbitrage,
            "market_event_1_actor": arbitrage_swap.actor,
            "market_event_1_pre_tick": arbitrage_swap.pre_tick,
            "market_event_1_observed_claimable1": str(vault.limit_orders[0].claimable1),
        },
        "source": "Aegis same-step afterSwap limit-order fill local subset",
    }


def limit_order_epoch_payout_vector() -> dict:
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0)
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), vault, pool, market, 0)
    first_deposit0 = Decimal("1000") - vault.idle0
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=2000), vault, pool, market, 0)
    second_deposit0 = Decimal("1000") - vault.idle0 - first_deposit0
    _, _, fills = apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), vault, pool, market, 1)
    return {
        "id": "AE-LO-EPOCH-001",
        "input": {
            "side": "sell0",
            "tick": 60,
            "tick_spacing": 60,
            "liquidity_by_order": ["1000", "2000"],
            "pool_lp_fee_pips": 0,
            "swap_token_in": "token1",
            "swap_amount_in": "250000",
        },
        "expected": {
            "order_1_deposited0": str(first_deposit0),
            "order_2_deposited0": str(second_deposit0),
            "fill_count": len(fills),
            "order_1_claimable1": str(vault.limit_orders[0].claimable1),
            "order_2_claimable1": str(vault.limit_orders[1].claimable1),
            "total_claimable1": str(sum(order.claimable1 for order in vault.limit_orders)),
            "order_1_status": vault.limit_orders[0].status,
            "order_2_status": vault.limit_orders[1].status,
            "tick_lower_liquidity_net_after_fill": str(pool.initialized_ticks.get(60, 0)),
            "tick_upper_liquidity_net_after_fill": str(pool.initialized_ticks.get(120, 0)),
        },
        "source": "Aegis LimitOrderManager epoch payout proportional-with-residual local subset",
    }


def hook_fee_vector() -> dict:
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=3000, protocol_fee_pips=1000, hook_fee_ppm=1000)
    state_before = {"tick": pool.tick, "pending_hook_fees0": str(pool.pending_hook_fees0), "lp_fee_pips": pool.lp_fee_pips}
    event = pool.swap_exact_in("retail", "token0", Decimal("10000"), 0)
    state_after = {"tick": pool.tick, "pending_hook_fees0": str(pool.pending_hook_fees0), "lp_fee_pips": pool.lp_fee_pips}
    return {
        "id": "AE-HOOK-FEE-001",
        "input": {"fee_model": "aegis_dynamic", "hook_fee_ppm": 1000, "token_in": "token0", "amount_in": "10000", "pre_swap_tick": 0},
        "expected": {
            "hook_fee_token0": str(event.hook_fee_paid),
            "pool_input_after_hook_fee": str(event.amount_in - event.hook_fee_paid),
            "lp_fee_amount": str(event.lp_fee_paid),
            "protocol_fee_amount": str(event.protocol_fee_paid),
            "post_swap_tick": event.post_tick,
            "dynamic_fee_state_before": state_before,
            "dynamic_fee_state_after": state_after,
            "pending_hook_fee_delta": str(pool.pending_hook_fees0),
        },
        "source": "Aegis hook fee lifecycle local subset",
    }


def hook_reinvest_vector() -> dict:
    pool = Pool(
        active_liquidity=1_000_000,
        lp_fee_pips=3000,
        protocol_fee_pips=1000,
        hook_fee_ppm=500_000,
        hook_reinvest_cooldown_steps=0,
    )
    pool.pending_hook_fees0 = Decimal("1200")
    pool.pending_hook_fees1 = Decimal("1500")
    active_before = pool.active_liquidity
    event = pool.swap_exact_in("retail", "token0", Decimal("10000"), 100)
    return {
        "id": "AE-HOOK-REINVEST-001",
        "input": {
            "fee_model": "aegis_dynamic",
            "hook_fee_ppm": 500000,
            "token_in": "token0",
            "amount_in": "10000",
            "pre_pending_hook_fees0": "1200",
            "pre_pending_hook_fees1": "1500",
            "pre_active_liquidity": str(active_before),
            "step": 100,
        },
        "expected": {
            "current_swap_hook_fee_token0": str(event.hook_fee_paid),
            "reinvested_liquidity": str(pool.hook_reinvested_liquidity),
            "reinvested0": str(pool.hook_reinvested0),
            "reinvested1": str(pool.hook_reinvested1),
            "pending_hook_fees0_after": str(pool.pending_hook_fees0),
            "pending_hook_fees1_after": str(pool.pending_hook_fees1),
            "active_liquidity_after": str(pool.active_liquidity),
            "last_reinvest_step": str(pool.hook_last_reinvest_step),
        },
        "source": "AegisHook deferred pending-fee reinvest lifecycle local subset",
    }


def nft_cap_vector() -> dict:
    pool = Pool()
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(MintRange(lower_tick=-120, upper_tick=120, liquidity=100), vault, pool, market, 0)
    apply_action(MintRange(lower_tick=-240, upper_tick=240, liquidity=100), vault, pool, market, 0)
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=100), vault, pool, market, 0)
    apply_action(PlaceLimitOrder(side="sell0", tick=120, liquidity=100), vault, pool, market, 0)
    before_count = len(vault.positions) + len(vault.limit_orders)
    try:
        apply_action(MintRange(lower_tick=-360, upper_tick=360, liquidity=100), vault, pool, market, 1)
        error = None
    except ValueError as exc:
        error = str(exc)
    return {
        "id": "AE-NFT-CAP-001",
        "input": {"attached_nft_count_before": before_count, "action": "MintRange", "lower_tick": -360, "upper_tick": 360, "liquidity": "100"},
        "expected": {"batch_reverted": True, "error": error, "attached_nft_count_after": len(vault.positions) + len(vault.limit_orders)},
        "source": "Aegis vault attached NFT cap local subset",
    }


def debt_mark_vector() -> dict:
    tick_spacing = 60
    min_tick, max_tick = full_range_ticks(tick_spacing)
    liability = debt_repayment_liability(1000, 1_050_000_000_000_000_000, Decimal("1"), tick_spacing)
    iteration = liability["iterations"][0]
    return {
        "id": "AE-DEBT-MARK-001",
        "input": {
            "price": "1",
            "tick_spacing": tick_spacing,
            "borrow_index_wad": "1050000000000000000",
            "vault_rL": "1000",
            "full_range_min_tick": min_tick,
            "full_range_max_tick": max_tick,
        },
        "expected": {
            "debt_repayment_value": str(liability["value"]),
            "liability0": str(liability["liability0"]),
            "liability1": str(liability["liability1"]),
            "iterations": [
                {
                    "target_liquidity": str(iteration["target_liquidity"]),
                    "liability0": iteration["liability0"],
                    "liability1": iteration["liability1"],
                    "bridge_liquidity": str(iteration["bridge_liquidity"]),
                    "geometric_mean": str(iteration["geometric_mean"]),
                    "repaid_l": str(iteration["repaid_l"]),
                    "residual_l": str(iteration["residual_l"]),
                }
            ],
            "residual_l": str(liability["residual_l"]),
        },
        "source": "Aegis repay-path debt liability local subset",
    }


def repair_vector() -> dict:
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"), debt_l=994000, borrow_index=10**18)
    market = AegisMarket(total_rL_borrowed=994000)
    pool = Pool()
    event = repair_vault(vault, pool, market, 7)
    assert event is not None
    return {
        "id": "AE-REPAIR-001",
        "input": {
            "idle0": "1000000",
            "idle1": "1000000",
            "rL": "994000",
            "borrow_index_wad": "1000000000000000000",
            "max_ltv_pips": 993000,
            "hard_ltv_pips": 996000,
            "step": 7,
        },
        "expected": {
            "repay_fraction_pips": str(repay_fraction_pips(994000, 993000, 996000)),
            "keeper_fee_pips": str(keeper_fee_pips(994000, 993000, 996000)),
            "event_kind": event.kind,
            "initial_ltv_pips": str(event.initial_ltv_pips),
            "principal_repaid_l": str(event.principal_repaid_l),
            "idle0_consumed": str(event.idle0_consumed),
            "idle1_consumed": str(event.idle1_consumed),
            "keeper_fee0": str(event.keeper_fee0),
            "keeper_fee1": str(event.keeper_fee1),
            "debt_l_after": str(event.debt_l_after),
            "ltv_pips_after": str(event.ltv_pips_after),
            "idle0_after": str(vault.idle0),
            "idle1_after": str(vault.idle1),
            "market_total_rL_after": str(market.total_rL_borrowed),
        },
        "source": "Aegis peelOrMicroLiquidate idle-only micro-liquidation local subset",
    }


def peel_vector() -> dict:
    pool = Pool()
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(MintRange(lower_tick=-60, upper_tick=60, liquidity=10000), vault, pool, market, 0)
    initial_floor = vault.collateral_floor_l()
    vault.debt_l = initial_floor * 994000 // 1_000_000
    market.total_rL_borrowed = vault.debt_l
    event = repair_vault(vault, pool, market, 3)
    assert event is not None
    return {
        "id": "AE-PEEL-001",
        "input": {
            "position_kind": "CL",
            "position_range": [-60, 60],
            "position_liquidity": "10000",
            "idle0_before_mint": "1000000",
            "idle1_before_mint": "1000000",
            "initial_collateral_floor_l": str(initial_floor),
            "rL": "994000",
            "max_ltv_pips": 993000,
            "hard_ltv_pips": 996000,
        },
        "expected": {
            "event_kind": event.kind,
            "peeled_kind": event.peeled_kind,
            "peeled_id": str(event.peeled_id),
            "peeled_liquidity": str(event.peeled_liquidity),
            "initial_ltv_pips": str(event.initial_ltv_pips),
            "repay_fraction_pips": str(event.repay_pips),
            "peel_bounty_pips": str(event.keeper_fee_pips),
            "principal_repaid_l": str(event.principal_repaid_l),
            "idle0_credited": str(event.idle0_credited),
            "idle1_credited": str(event.idle1_credited),
            "keeper_fee0": str(event.keeper_fee0),
            "keeper_fee1": str(event.keeper_fee1),
            "debt_l_after": str(event.debt_l_after),
            "ltv_pips_after": str(event.ltv_pips_after),
            "position_count_after": str(len(vault.positions)),
            "active_liquidity_after": str(pool.active_liquidity),
            "idle0_after": str(vault.idle0),
            "idle1_after": str(vault.idle1),
        },
        "source": "Aegis peelOrMicroLiquidate CL peel local subset",
    }


def repair_swap_vector() -> dict:
    pool = Pool(active_liquidity=10_000_000, lp_fee_pips=1000)
    vault = Vault(idle0=Decimal("10000000"), idle1=Decimal("100000"), debt_l=994000, borrow_index=10**18)
    market = AegisMarket(total_rL_borrowed=994000)
    event = repair_vault(vault, pool, market, 9)
    assert event is not None
    return {
        "id": "AE-REPAIR-SWAP-001",
        "input": {
            "idle0": "10000000",
            "idle1": "100000",
            "rL": "994000",
            "borrow_index_wad": "1000000000000000000",
            "pool_active_liquidity": "10000000",
            "pool_lp_fee_pips": 1000,
            "max_ltv_pips": 993000,
            "hard_ltv_pips": 996000,
            "amount0_required": "133196",
            "amount1_required": "133196",
            "step": 9,
        },
        "expected": {
            "deficit_zero_for_one": micro_liq_swap_deficit(Decimal("10000000"), Decimal("100000"), 133196, 133196)[0],
            "deficit_exact_out": str(micro_liq_swap_deficit(Decimal("10000000"), Decimal("100000"), 133196, 133196)[1]),
            "event_kind": event.kind,
            "initial_ltv_pips": str(event.initial_ltv_pips),
            "repay_fraction_pips": str(event.repay_pips),
            "keeper_fee_pips": str(event.keeper_fee_pips),
            "swap_token_in": event.swap_token_in,
            "swap_amount_in": str(event.swap_amount_in),
            "swap_amount_out": str(event.swap_amount_out),
            "principal_repaid_l": str(event.principal_repaid_l),
            "idle0_consumed": str(event.idle0_consumed),
            "idle1_consumed": str(event.idle1_consumed),
            "keeper_fee0": str(event.keeper_fee0),
            "keeper_fee1": str(event.keeper_fee1),
            "debt_l_after": str(event.debt_l_after),
            "ltv_pips_after": str(event.ltv_pips_after),
            "idle0_after": str(vault.idle0),
            "idle1_after": str(vault.idle1),
            "pool_event_index_after": str(pool.event_index),
        },
        "source": "Aegis peelOrMicroLiquidate swap-assisted micro-liquidation local subset",
    }


def main() -> int:
    print(json.dumps(build_vectors(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
