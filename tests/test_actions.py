from decimal import Decimal

from aegis_challenge.aegis_market import AegisMarket
from aegis_challenge.api import (
    CancelLimitOrder,
    DecreaseRange,
    IncreaseRange,
    MintRange,
    PlaceLimitOrder,
    SwapExactIn,
)
from aegis_challenge.limit_orders import fill_crossed_orders
from aegis_challenge.pool import Pool
from aegis_challenge.runner import apply_action
from aegis_challenge.vault import Vault
from aegis_challenge.v4_math import amount_delta_for_range


def test_limit_order_fills_on_same_crossing_swap():
    pool = Pool()
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()

    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=500), vault, pool, market, 0)
    assert pool.initialized_ticks[60] == 500
    assert pool.initialized_ticks[120] == -500
    _, swaps, fills = apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), vault, pool, market, 0)

    assert swaps
    assert len(fills) == 1
    assert vault.limit_orders[0].status == "filled"
    assert vault.limit_orders[0].claimable1 > 0
    assert pool.initialized_ticks[60] == 0
    assert pool.initialized_ticks[120] == 0


def test_cancel_limit_order_returns_deposit():
    pool = Pool()
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()

    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=500), vault, pool, market, 0)
    deposit0, _ = amount_delta_for_range(500, pool.price, 60, 120)
    assert vault.idle0 == Decimal("1000") - deposit0

    apply_action(CancelLimitOrder(order_id=1), vault, pool, market, 1)

    assert vault.idle0 == Decimal("1000")
    assert vault.limit_orders == []
    assert pool.initialized_ticks[60] == 0
    assert pool.initialized_ticks[120] == 0


def test_range_increase_and_decrease_updates_liquidity_and_idle():
    pool = Pool()
    vault = Vault(idle0=Decimal("10000"), idle1=Decimal("10000"))
    market = AegisMarket()
    base_liquidity = pool.active_liquidity

    apply_action(MintRange(lower_tick=-60, upper_tick=60, liquidity=1000), vault, pool, market, 0)
    apply_action(IncreaseRange(position_id=1, liquidity=200), vault, pool, market, 1)
    apply_action(DecreaseRange(position_id=1, liquidity=500), vault, pool, market, 2)

    assert vault.positions[0].liquidity == 700
    assert pool.active_liquidity == base_liquidity + 700
    assert vault.idle0 > Decimal("9000")
    assert vault.idle1 > Decimal("9000")


def test_crossed_limit_order_rejected_without_mutating_vault():
    pool = Pool()
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()

    try:
        apply_action(PlaceLimitOrder(side="sell0", tick=0, liquidity=500), vault, pool, market, 0)
    except ValueError as exc:
        assert str(exc) == "ERR_CROSSED_LIMIT_ORDER"
    else:
        raise AssertionError("expected crossed order to fail")

    assert vault.idle0 == Decimal("1000")
    assert vault.limit_orders == []


def test_fill_crossed_orders_leaves_uncrossed_orders_open():
    pool = Pool()
    swap = pool.swap_exact_in("retail", "token1", Decimal("100"), 0)
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("0"))
    market = AegisMarket()
    apply_action(PlaceLimitOrder(side="sell0", tick=600, liquidity=100), vault, pool, market, 0)

    orders, fills = fill_crossed_orders(vault.limit_orders, swap)

    assert fills == []
    assert orders[0].status == "open"


def test_limit_orders_in_same_epoch_receive_proportional_payout_with_last_residual():
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0)
    vault = Vault(idle0=Decimal("1000"), idle1=Decimal("1000000"))
    market = AegisMarket()

    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=1000), vault, pool, market, 0)
    apply_action(PlaceLimitOrder(side="sell0", tick=60, liquidity=2000), vault, pool, market, 0)
    _, _, fills = apply_action(SwapExactIn(token_in="token1", amount_in=Decimal("250000")), vault, pool, market, 1)

    assert len(fills) == 2
    total_claimable1 = sum(order.claimable1 for order in vault.limit_orders)
    _, expected_total1 = amount_delta_for_range(3000, pool.price, 60, 120)
    assert total_claimable1 == expected_total1
    assert vault.limit_orders[0].claimable1 == expected_total1 * Decimal(1000) // Decimal(3000)
    assert vault.limit_orders[1].claimable1 == expected_total1 - vault.limit_orders[0].claimable1
