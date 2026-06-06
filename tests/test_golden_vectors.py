import json
from decimal import Decimal
from pathlib import Path

from aegis_challenge.aegis_market import AegisMarket, debt_repayment_liability, full_range_amounts_for_liquidity, keeper_fee_pips, liquidity_for_principal, micro_liq_swap_deficit, repay_bridge, repay_fraction_pips
from aegis_challenge.api import CollectFees, MintRange, PlaceLimitOrder, SwapExactIn
from aegis_challenge.pool import Pool
from aegis_challenge.runner import apply_action, repair_vault
from aegis_challenge.vault import Vault
from aegis_challenge.v4_math import Q96, compute_swap_step, get_sqrt_price_at_tick, get_tick_at_sqrt_price


def load_vectors(name):
    return json.loads(Path("tests/golden", name).read_text())["vectors"]


def test_uniswap_v4_golden_vectors_match_simulator():
    vectors = {vector["id"]: vector for vector in load_vectors("uniswap_v4_vectors.json")}

    tick_vector = vectors["UV4-TICK-000"]
    actual_ticks = [str(get_sqrt_price_at_tick(tick)) for tick in tick_vector["input"]["ticks"]]
    assert actual_ticks == tick_vector["expected"]["sqrt_price_x96"]

    swap0 = compute_swap_step(Q96, get_sqrt_price_at_tick(-120), 1_000_000, -1000, 0)
    assert str(swap0.sqrt_price_next_x96) == vectors["UV4-SWAP-001"]["expected"]["sqrt_price_x96_after"]
    assert str(swap0.amount_in) == vectors["UV4-SWAP-001"]["expected"]["amount0_in"]
    assert str(swap0.amount_out) == vectors["UV4-SWAP-001"]["expected"]["amount1_out"]
    assert get_tick_at_sqrt_price(swap0.sqrt_price_next_x96) == vectors["UV4-SWAP-001"]["expected"]["final_tick"]

    swap1 = compute_swap_step(Q96, get_sqrt_price_at_tick(120), 1_000_000, -1000, 0)
    assert str(swap1.sqrt_price_next_x96) == vectors["UV4-SWAP-002"]["expected"]["sqrt_price_x96_after"]
    assert str(swap1.amount_in) == vectors["UV4-SWAP-002"]["expected"]["amount1_in"]
    assert str(swap1.amount_out) == vectors["UV4-SWAP-002"]["expected"]["amount0_out"]
    assert get_tick_at_sqrt_price(swap1.sqrt_price_next_x96) == vectors["UV4-SWAP-002"]["expected"]["final_tick"]

    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0, initialized_ticks={60: -250_000})
    amount_to_cross = 3005
    event = pool.swap_exact_in("retail", "token1", Decimal(amount_to_cross), 0)
    tick_expected = vectors["UV4-TICK-001"]["expected"]
    assert event.ticks_crossed == (tick_expected["crossed_tick"],)
    assert str(pool.active_liquidity) == tick_expected["active_liquidity_after_cross"]
    assert pool.tick == tick_expected["current_tick_after_cross"]

    fee1 = vectors["UV4-FEE-001"]
    pool = Pool(
        active_liquidity=int(fee1["input"]["active_liquidity_before_position"]),
        lp_fee_pips=int(fee1["input"]["fee_pips"]),
    )
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(
        MintRange(
            lower_tick=fee1["input"]["position_range"][0],
            upper_tick=fee1["input"]["position_range"][1],
            liquidity=int(fee1["input"]["position_liquidity"]),
        ),
        vault,
        pool,
        market,
        0,
    )
    pool.swap_exact_in("retail", fee1["input"]["token_in"], Decimal(fee1["input"]["amount_in"]), 1)
    before = vault.idle0
    apply_action(CollectFees(position_id=1), vault, pool, market, 2)
    assert str(pool.fee_growth_global0_x128) == fee1["expected"]["fee_growth_global0_delta_x128"]
    assert str(vault.idle0 - before) == fee1["expected"]["collect_idle0_delta"]

    fee2 = vectors["UV4-FEE-002"]
    pool = Pool(
        active_liquidity=int(fee2["input"]["active_liquidity"]),
        lp_fee_pips=int(fee2["input"]["lp_fee_pips"]),
        protocol_fee_pips=int(fee2["input"]["protocol_fee_pips"]),
    )
    event = pool.swap_exact_in("retail", fee2["input"]["token_in"], Decimal(fee2["input"]["amount_in"]), 0)
    assert pool.state().pool_swap_fee_pips == fee2["expected"]["pool_swap_fee_pips"]
    assert str(event.lp_fee_paid + event.protocol_fee_paid) == fee2["expected"]["total_pool_fee_amount"]
    assert str(event.protocol_fee_paid) == fee2["expected"]["protocol_fee_amount"]
    assert str(event.lp_fee_paid) == fee2["expected"]["lp_fee_amount"]
    assert str(pool.fee_growth_global0_x128) == fee2["expected"]["fee_growth_global0_delta_x128"]


def test_aegis_vault_golden_vectors_match_simulator():
    vectors = {vector["id"]: vector for vector in load_vectors("aegis_vault_vectors.json")}

    borrow = vectors["AE-BORROW-001"]
    liquidity_removed = liquidity_for_principal(
        int(borrow["input"]["borrow_amount_l"]),
        int(borrow["input"]["borrow_index_wad"]),
    )
    assert str(liquidity_removed) == borrow["expected"]["liquidity_removed"]
    amount0, amount1 = full_range_amounts_for_liquidity(
        liquidity_removed,
        Decimal(borrow["input"]["price"]),
    )
    assert str(amount0) == borrow["expected"]["idle0_delta"]
    assert str(amount1) == borrow["expected"]["idle1_delta"]

    repay = vectors["AE-REPAY-001"]
    bridge = repay_bridge(
        int(repay["input"]["requested_repay_l"]),
        Decimal(repay["input"]["idle0"]),
        Decimal(repay["input"]["idle1"]),
        int(repay["input"]["borrow_index_wad"]),
    )
    assert str(bridge["target_liquidity"]) == repay["expected"]["target_liquidity"]
    assert str(bridge["idle0_consumed"]) == repay["expected"]["idle0_consumed"]
    assert str(bridge["idle1_consumed"]) == repay["expected"]["idle1_consumed"]
    assert str(bridge["geometric_mean"]) == repay["expected"]["geometric_mean"]
    assert str(bridge["actual_repaid_l"]) == repay["expected"]["actual_repaid_l"]

    ltv = vectors["AE-LTV-001"]
    vault = Vault(
        idle0=Decimal(ltv["input"]["idle0"]),
        idle1=Decimal(ltv["input"]["idle1"]),
        debt_l=int(ltv["input"]["rL"]),
        borrow_index=int(ltv["input"]["borrow_index_wad"]),
    )
    state = vault.state(Decimal("1"))
    assert str(state.collateral_floor_l) == ltv["expected"]["collateral_floor_l"]
    assert str(int(vault.debt_l) * int(vault.borrow_index)) == ltv["expected"]["debt_l_wad"]
    assert str(state.ltv_pips) == ltv["expected"]["ltv_pips"]

    interest = vectors["AE-INTEREST-001"]
    market = AegisMarket(
        total_rL_borrowed=int(interest["input"]["total_rL_borrowed"]),
        borrow_index_wad=int(interest["input"]["borrow_index_wad"]),
    )
    before = market.borrow_index_wad
    interest_wad = market.accrue_at_rate(
        int(interest["input"]["dt"]),
        int(interest["input"]["rate_per_second_wad"]),
    )
    assert str(market.borrow_index_wad - before) == interest["expected"]["delta_borrow_index_wad"]
    assert str(market.borrow_index_wad) == interest["expected"]["borrow_index_wad_after"]
    assert str(interest_wad) == interest["expected"]["interest_accrued_wad"]

    limit_order = vectors["AE-LO-001"]
    pool = Pool()
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), vault, pool, market, 0)
    assert str(pool.initialized_ticks.get(60, 0)) == limit_order["expected"]["tick_lower_liquidity_net_after_place"]
    assert str(pool.initialized_ticks.get(120, 0)) == limit_order["expected"]["tick_upper_liquidity_net_after_place"]
    apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), vault, pool, market, 0)
    assert vault.limit_orders[0].status == limit_order["expected"]["order_status_after_cross"]
    assert str(pool.initialized_ticks.get(60, 0)) == limit_order["expected"]["tick_lower_liquidity_net_after_fill"]
    assert str(pool.initialized_ticks.get(120, 0)) == limit_order["expected"]["tick_upper_liquidity_net_after_fill"]

    lo_epoch = vectors["AE-LO-EPOCH-001"]
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=int(lo_epoch["input"]["pool_lp_fee_pips"]))
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(
        PlaceLimitOrder(side="sell0", tick=lo_epoch["input"]["tick"], liquidity=int(lo_epoch["input"]["liquidity_by_order"][0])),
        vault,
        pool,
        market,
        0,
    )
    apply_action(
        PlaceLimitOrder(side="sell0", tick=lo_epoch["input"]["tick"], liquidity=int(lo_epoch["input"]["liquidity_by_order"][1])),
        vault,
        pool,
        market,
        0,
    )
    _, _, fills = apply_action(
        SwapExactIn(token_in=lo_epoch["input"]["swap_token_in"], amount_in=Decimal(lo_epoch["input"]["swap_amount_in"])),
        vault,
        pool,
        market,
        1,
    )
    assert len(fills) == lo_epoch["expected"]["fill_count"]
    assert str(vault.limit_orders[0].claimable1) == lo_epoch["expected"]["order_1_claimable1"]
    assert str(vault.limit_orders[1].claimable1) == lo_epoch["expected"]["order_2_claimable1"]
    assert str(vault.limit_orders[0].claimable1 + vault.limit_orders[1].claimable1) == lo_epoch["expected"]["total_claimable1"]

    hook_fee = vectors["AE-HOOK-FEE-001"]
    pool = Pool(
        active_liquidity=int(hook_fee["input"].get("active_liquidity", "1000000")),
        lp_fee_pips=3000,
        protocol_fee_pips=1000,
        hook_fee_ppm=int(hook_fee["input"]["hook_fee_ppm"]),
    )
    event = pool.swap_exact_in("retail", hook_fee["input"]["token_in"], Decimal(hook_fee["input"]["amount_in"]), 0)
    assert str(event.hook_fee_paid) == hook_fee["expected"]["hook_fee_token0"]
    assert str(event.amount_in - event.hook_fee_paid) == hook_fee["expected"]["pool_input_after_hook_fee"]
    assert str(pool.pending_hook_fees0) == hook_fee["expected"]["pending_hook_fee_delta"]

    hook_reinvest = vectors["AE-HOOK-REINVEST-001"]
    pool = Pool(
        active_liquidity=int(hook_reinvest["input"]["pre_active_liquidity"]),
        lp_fee_pips=3000,
        protocol_fee_pips=1000,
        hook_fee_ppm=int(hook_reinvest["input"]["hook_fee_ppm"]),
        hook_reinvest_cooldown_steps=0,
    )
    pool.pending_hook_fees0 = Decimal(hook_reinvest["input"]["pre_pending_hook_fees0"])
    pool.pending_hook_fees1 = Decimal(hook_reinvest["input"]["pre_pending_hook_fees1"])
    event = pool.swap_exact_in(
        "retail",
        hook_reinvest["input"]["token_in"],
        Decimal(hook_reinvest["input"]["amount_in"]),
        int(hook_reinvest["input"]["step"]),
    )
    assert str(event.hook_fee_paid) == hook_reinvest["expected"]["current_swap_hook_fee_token0"]
    assert str(pool.hook_reinvested_liquidity) == hook_reinvest["expected"]["reinvested_liquidity"]
    assert str(pool.hook_reinvested0) == hook_reinvest["expected"]["reinvested0"]
    assert str(pool.hook_reinvested1) == hook_reinvest["expected"]["reinvested1"]
    assert str(pool.pending_hook_fees0) == hook_reinvest["expected"]["pending_hook_fees0_after"]
    assert str(pool.pending_hook_fees1) == hook_reinvest["expected"]["pending_hook_fees1_after"]
    assert str(pool.active_liquidity) == hook_reinvest["expected"]["active_liquidity_after"]

    debt_mark = vectors["AE-DEBT-MARK-001"]
    liability = debt_repayment_liability(
        int(debt_mark["input"]["vault_rL"]),
        int(debt_mark["input"]["borrow_index_wad"]),
        Decimal(debt_mark["input"]["price"]),
        int(debt_mark["input"]["tick_spacing"]),
    )
    assert str(liability["value"]) == debt_mark["expected"]["debt_repayment_value"]
    assert str(liability["liability0"]) == debt_mark["expected"]["liability0"]
    assert str(liability["liability1"]) == debt_mark["expected"]["liability1"]
    assert str(liability["residual_l"]) == debt_mark["expected"]["residual_l"]
    assert liability["iterations"][0]["bridge_liquidity"] == int(debt_mark["expected"]["iterations"][0]["bridge_liquidity"])

    repair = vectors["AE-REPAIR-001"]
    assert str(repay_fraction_pips(994000, 993000, 996000)) == repair["expected"]["repay_fraction_pips"]
    assert str(keeper_fee_pips(994000, 993000, 996000)) == repair["expected"]["keeper_fee_pips"]
    vault = Vault(
        idle0=Decimal(repair["input"]["idle0"]),
        idle1=Decimal(repair["input"]["idle1"]),
        debt_l=int(repair["input"]["rL"]),
        borrow_index=int(repair["input"]["borrow_index_wad"]),
    )
    market = AegisMarket(total_rL_borrowed=int(repair["input"]["rL"]))
    event = repair_vault(vault, Pool(), market, int(repair["input"]["step"]))
    assert event is not None
    assert event.kind == repair["expected"]["event_kind"]
    assert str(event.initial_ltv_pips) == repair["expected"]["initial_ltv_pips"]
    assert str(event.principal_repaid_l) == repair["expected"]["principal_repaid_l"]
    assert str(event.keeper_fee0) == repair["expected"]["keeper_fee0"]
    assert str(event.keeper_fee1) == repair["expected"]["keeper_fee1"]
    assert str(vault.idle0) == repair["expected"]["idle0_after"]
    assert str(vault.idle1) == repair["expected"]["idle1_after"]

    peel = vectors["AE-PEEL-001"]
    pool = Pool()
    vault = Vault(idle0=Decimal(peel["input"]["idle0_before_mint"]), idle1=Decimal(peel["input"]["idle1_before_mint"]))
    market = AegisMarket()
    apply_action(
        MintRange(
            lower_tick=peel["input"]["position_range"][0],
            upper_tick=peel["input"]["position_range"][1],
            liquidity=int(peel["input"]["position_liquidity"]),
        ),
        vault,
        pool,
        market,
        0,
    )
    vault.debt_l = int(peel["input"]["rL"])
    market.total_rL_borrowed = vault.debt_l
    event = repair_vault(vault, pool, market, 3)
    assert event is not None
    assert event.kind == peel["expected"]["event_kind"]
    assert event.peeled_kind == peel["expected"]["peeled_kind"]
    assert str(event.peeled_liquidity) == peel["expected"]["peeled_liquidity"]
    assert str(event.repay_pips) == peel["expected"]["repay_fraction_pips"]
    assert str(event.idle0_credited) == peel["expected"]["idle0_credited"]
    assert str(event.idle1_credited) == peel["expected"]["idle1_credited"]
    assert str(len(vault.positions)) == peel["expected"]["position_count_after"]
    assert str(pool.active_liquidity) == peel["expected"]["active_liquidity_after"]

    repair_swap = vectors["AE-REPAIR-SWAP-001"]
    zero_for_one, exact_out = micro_liq_swap_deficit(
        Decimal(repair_swap["input"]["idle0"]),
        Decimal(repair_swap["input"]["idle1"]),
        int(repair_swap["input"]["amount0_required"]),
        int(repair_swap["input"]["amount1_required"]),
    )
    assert zero_for_one is repair_swap["expected"]["deficit_zero_for_one"]
    assert str(exact_out) == repair_swap["expected"]["deficit_exact_out"]
    pool = Pool(
        active_liquidity=int(repair_swap["input"]["pool_active_liquidity"]),
        lp_fee_pips=int(repair_swap["input"]["pool_lp_fee_pips"]),
    )
    vault = Vault(
        idle0=Decimal(repair_swap["input"]["idle0"]),
        idle1=Decimal(repair_swap["input"]["idle1"]),
        debt_l=int(repair_swap["input"]["rL"]),
        borrow_index=int(repair_swap["input"]["borrow_index_wad"]),
    )
    market = AegisMarket(total_rL_borrowed=int(repair_swap["input"]["rL"]))
    event = repair_vault(vault, pool, market, int(repair_swap["input"]["step"]))
    assert event is not None
    assert event.swap_token_in == repair_swap["expected"]["swap_token_in"]
    assert str(event.swap_amount_in) == repair_swap["expected"]["swap_amount_in"]
    assert str(event.swap_amount_out) == repair_swap["expected"]["swap_amount_out"]
    assert str(event.principal_repaid_l) == repair_swap["expected"]["principal_repaid_l"]
    assert str(vault.idle0) == repair_swap["expected"]["idle0_after"]
    assert str(vault.idle1) == repair_swap["expected"]["idle1_after"]
