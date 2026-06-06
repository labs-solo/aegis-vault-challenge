from decimal import Decimal

from aegis_challenge.aegis_market import (
    AegisMarket,
    debt_repayment_liability,
    full_range_amounts_for_liquidity,
    keeper_fee_pips,
    liquidity_for_principal,
    micro_liq_swap_deficit,
    principal_from_liquidity,
    repay_bridge,
    repay_fraction_pips,
)
from aegis_challenge.pool import Pool
from aegis_challenge.runner import apply_action, repair_vault
from aegis_challenge.api import BorrowL, MintRange, PlaceLimitOrder, RepayL
from aegis_challenge.vault import Vault


def test_interest_accrual_matches_aegis_vector_units():
    market = AegisMarket(total_rL_borrowed=100_000, borrow_index_wad=10**18)

    interest_wad = market.accrue_at_rate(seconds=60, rate_per_second_wad=1_000_000_000)

    assert interest_wad == 6_000_000_000_000_000
    assert market.borrow_index_wad == 1_000_000_060_000_000_000
    assert market.borrowed_l_wad() == 100_000_006_000_000_000_000_000


def test_ltv_idle_only_matches_aegis_vector():
    vault = Vault(idle0=Decimal("100"), idle1=Decimal("400"), debt_l=100, borrow_index=10**18)

    state = vault.state(Decimal("1"))

    assert state.collateral_floor_l == 200
    assert state.debt_liability0 == Decimal("100")
    assert state.debt_liability1 == Decimal("100")
    assert state.debt_liability_value == Decimal("200")
    assert state.ltv_pips == 500_000


def test_ltv_one_sided_idle_has_zero_floor():
    vault = Vault(idle0=Decimal("100"), idle1=Decimal("0"), debt_l=1, borrow_index=10**18)

    state = vault.state(Decimal("1"))

    assert state.collateral_floor_l == 0
    assert state.ltv_pips == 1_000_000


def test_repay_bridge_is_conservative():
    bridge = repay_bridge(500, Decimal("1000"), Decimal("1000"), 1_050_000_000_000_000_000)

    assert bridge["target_liquidity"] == 525
    assert bridge["bridge_liquidity"] == 525
    assert bridge["geometric_mean"] == 525
    assert bridge["actual_repaid_l"] == 500
    assert bridge["idle0_consumed"] == 525
    assert bridge["idle1_consumed"] == 525
    assert principal_from_liquidity(liquidity_for_principal(500, 1_050_000_000_000_000_000), 1_050_000_000_000_000_000) == 500


def test_debt_repayment_liability_uses_full_range_amounts():
    liability = debt_repayment_liability(1000, 1_050_000_000_000_000_000, Decimal("1"), 60)

    assert liability["liability0"] == Decimal("1050")
    assert liability["liability1"] == Decimal("1050")
    assert liability["value"] == Decimal("2100")
    assert liability["iterations"][0]["bridge_liquidity"] == 1050
    assert liability["iterations"][0]["repaid_l"] == 1000
    assert liability["residual_l"] == 0


def test_full_range_amounts_follow_price():
    amount0, amount1 = full_range_amounts_for_liquidity(1000, Decimal("2"), 60)

    assert amount0 == 708
    assert amount1 == 1415


def test_runner_repay_consumes_both_idle_sides():
    vault = Vault(idle0=Decimal("2000"), idle1=Decimal("2000"), debt_l=1000)
    market = AegisMarket(total_rL_borrowed=1000)

    apply_action(RepayL(amount_l=500), vault, Pool(), market, 0)

    assert vault.debt_l == 500
    assert market.total_rL_borrowed == 500
    assert vault.idle0 == Decimal("1500")
    assert vault.idle1 == Decimal("1500")


def test_runner_borrow_uses_market_principal_units():
    vault = Vault()
    market = AegisMarket()

    apply_action(BorrowL(amount_l=1000), vault, Pool(), market, 0)

    assert vault.debt_l == 1000
    assert market.total_rL_borrowed == 1000
    assert vault.idle0 == Decimal("1000")
    assert vault.idle1 == Decimal("101000")


def test_liquidation_math_schedule_matches_aegis_reference_shape():
    assert repay_fraction_pips(992_999, 993_000, 996_000) == 0
    assert repay_fraction_pips(993_000, 993_000, 996_000) == 2_000
    assert repay_fraction_pips(994_000, 993_000, 996_000) == 134_000
    assert repay_fraction_pips(994_500, 993_000, 996_000) == 200_000
    assert repay_fraction_pips(995_250, 993_000, 996_000) == 600_000
    assert repay_fraction_pips(996_000, 993_000, 996_000) == 1_000_000
    assert keeper_fee_pips(993_000, 993_000, 996_000) == 0
    assert keeper_fee_pips(994_000, 993_000, 996_000) == 3333
    assert keeper_fee_pips(996_000, 993_000, 996_000) == 10_000
    assert micro_liq_swap_deficit(10_000_000, 100_000, 133_196, 133_196) == (True, 33_196)


def test_repair_vault_micro_liquidates_unhealthy_idle_only_vault():
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"), debt_l=994000, borrow_index=10**18)
    market = AegisMarket(total_rL_borrowed=994000)

    event = repair_vault(vault, Pool(), market, 7)

    assert event is not None
    assert event.kind == "micro_liquidation"
    assert event.initial_ltv_pips == 994_000
    assert event.repay_pips == 134_000
    assert event.keeper_fee_pips == 3333
    assert event.principal_repaid_l == 133196
    assert event.idle0_consumed == Decimal("133196")
    assert event.idle1_consumed == Decimal("133196")
    assert event.keeper_fee0 == Decimal("443")
    assert event.keeper_fee1 == Decimal("443")
    assert vault.debt_l == 860804
    assert market.total_rL_borrowed == 860804
    assert vault.idle0 == Decimal("866361")
    assert vault.idle1 == Decimal("866361")
    assert event.ltv_pips_after == vault.ltv_pips()


def test_repair_vault_swaps_excess_idle_to_cover_micro_liquidation_deficit():
    vault = Vault(idle0=Decimal("10000000"), idle1=Decimal("100000"), debt_l=994000, borrow_index=10**18)
    market = AegisMarket(total_rL_borrowed=994000)
    pool = Pool(active_liquidity=10_000_000, lp_fee_pips=1000)

    event = repair_vault(vault, pool, market, 9)

    assert event is not None
    assert event.kind == "micro_liquidation"
    assert event.swap_token_in == "token0"
    assert event.swap_amount_in == Decimal("33341")
    assert event.swap_amount_out == Decimal("33196")
    assert event.principal_repaid_l == 133196
    assert event.idle0_consumed == Decimal("133640")
    assert event.idle1_consumed == Decimal("132754")
    assert event.keeper_fee0 == Decimal("445")
    assert event.keeper_fee1 == Decimal("442")
    assert vault.debt_l == 860804
    assert market.total_rL_borrowed == 860804
    assert vault.idle0 == Decimal("9832574")
    assert vault.idle1 == Decimal("0")
    assert pool.event_index == 1


def test_repair_vault_peels_attached_cl_before_micro_liquidation():
    pool = Pool()
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(MintRange(lower_tick=-60, upper_tick=60, liquidity=10000), vault, pool, market, 0)
    vault.debt_l = vault.collateral_floor_l() * 994000 // 1_000_000
    market.total_rL_borrowed = vault.debt_l

    event = repair_vault(vault, pool, market, 3)

    assert event is not None
    assert event.kind == "peel"
    assert event.peeled_kind == "CL"
    assert event.peeled_id == 1
    assert event.peeled_liquidity == 10000
    assert event.principal_repaid_l == 0
    assert event.idle0_credited == Decimal("30")
    assert event.idle1_credited == Decimal("30")
    assert vault.positions == []
    assert pool.active_liquidity == 10_000_000
    assert vault.idle0 == Decimal("1000000")
    assert vault.idle1 == Decimal("1000000")
    assert market.total_rL_borrowed == 994000


def test_repair_vault_peels_attached_limit_order_before_micro_liquidation():
    pool = Pool()
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=10000), vault, pool, market, 0)
    vault.debt_l = vault.collateral_floor_l() * 994000 // 1_000_000
    market.total_rL_borrowed = vault.debt_l

    event = repair_vault(vault, pool, market, 4)

    assert event is not None
    assert event.kind == "peel"
    assert event.peeled_kind == "LO"
    assert event.peeled_id == 1
    assert event.peeled_liquidity == 10000
    assert event.keeper_fee0 == Decimal("0")
    assert event.idle0_credited == Decimal("30")
    assert event.idle1_credited == Decimal("0")
    assert vault.limit_orders == []
    assert pool.initialized_ticks[60] == 0
    assert pool.initialized_ticks[120] == 0
    assert vault.idle0 == Decimal("1000000")
    assert vault.idle1 == Decimal("1000000")
