from decimal import Decimal

from aegis_challenge.aegis_market import AegisMarket
from aegis_challenge.api import CollectFees, MintRange
from aegis_challenge.pool import Pool
from aegis_challenge.runner import apply_action
from aegis_challenge.vault import Vault
from aegis_challenge.v4_math import (
    Q96,
    Q128,
    compute_swap_step,
    get_amount1_delta,
    get_amount0_delta,
    get_sqrt_price_at_tick,
    get_tick_at_sqrt_price,
)


def test_tick_math_matches_v4_reference_constants():
    assert get_sqrt_price_at_tick(0) == Q96
    assert get_sqrt_price_at_tick(-887272) == 4295128739
    assert get_sqrt_price_at_tick(887272) == 1461446703485210103287273052203988822378723970342
    assert get_tick_at_sqrt_price(Q96) == 0
    assert get_tick_at_sqrt_price(get_sqrt_price_at_tick(60)) == 60


def test_swap_step_token0_exact_in_matches_spec_vector():
    step = compute_swap_step(
        sqrt_price_current_x96=Q96,
        sqrt_price_target_x96=get_sqrt_price_at_tick(-120),
        liquidity=1_000_000,
        amount_remaining=-1000,
        fee_pips=0,
    )

    assert step.sqrt_price_next_x96 == 79149013500763574019524425911
    assert step.amount_in == 1000
    assert step.amount_out == 999
    assert get_tick_at_sqrt_price(step.sqrt_price_next_x96) == -20


def test_swap_step_token1_exact_in_matches_spec_vector():
    step = compute_swap_step(
        sqrt_price_current_x96=Q96,
        sqrt_price_target_x96=get_sqrt_price_at_tick(120),
        liquidity=1_000_000,
        amount_remaining=-1000,
        fee_pips=0,
    )

    assert step.sqrt_price_next_x96 == 79307390676778601931137494286
    assert step.amount_in == 1000
    assert step.amount_out == 999
    assert get_tick_at_sqrt_price(step.sqrt_price_next_x96) == 19


def test_amount_delta_rounding_matches_v4_shape():
    sqrt_lower = get_sqrt_price_at_tick(-60)
    sqrt_upper = get_sqrt_price_at_tick(60)

    assert get_amount0_delta(sqrt_lower, sqrt_upper, 1_000_000, False) == 5999
    assert get_amount0_delta(sqrt_lower, sqrt_upper, 1_000_000, True) == 6000
    assert get_amount1_delta(sqrt_lower, sqrt_upper, 1_000_000, False) == 5999
    assert get_amount1_delta(sqrt_lower, sqrt_upper, 1_000_000, True) == 6000


def test_pool_uses_v4_swap_step_for_price_movement():
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0)

    swap = pool.swap_exact_in("retail", "token0", Decimal("1000"), 0)

    assert swap.post_sqrt_price_x96 == 79149013500763574019524425911
    assert swap.amount_out == Decimal("999")
    assert swap.post_tick == -20


def test_pool_crosses_initialized_tick_directionally():
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0, initialized_ticks={60: -250_000})
    amount_to_cross = get_amount1_delta(Q96, get_sqrt_price_at_tick(60), 1_000_000, True)

    swap = pool.swap_exact_in("retail", "token1", Decimal(amount_to_cross), 0)

    assert swap.ticks_crossed == (60,)
    assert pool.active_liquidity == 750_000
    assert swap.post_tick == 60


def test_pool_crosses_lower_tick_with_v4_zero_for_one_tick_rule():
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0, initialized_ticks={-60: 250_000})
    amount_to_cross = get_amount0_delta(get_sqrt_price_at_tick(-60), Q96, 1_000_000, True)

    swap = pool.swap_exact_in("retail", "token0", Decimal(amount_to_cross), 0)

    assert swap.ticks_crossed == (-60,)
    assert pool.active_liquidity == 750_000
    assert swap.post_tick == -61


def test_pool_updates_fee_growth_and_protocol_split():
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=3000, protocol_fee_pips=1000)

    swap = pool.swap_exact_in("retail", "token0", Decimal("10000"), 0)

    assert swap.lp_fee_paid == Decimal("30")
    assert swap.protocol_fee_paid == Decimal("10")
    assert pool.fee_growth_global0_x128 == 30 * Q128 // 1_000_000
    assert pool.fee_growth_global1_x128 == 0


def test_hook_fee_reduces_pool_input_before_swap():
    baseline = Pool(active_liquidity=1_000_000, lp_fee_pips=3000, protocol_fee_pips=1000)
    with_hook = Pool(active_liquidity=1_000_000, lp_fee_pips=3000, protocol_fee_pips=1000, hook_fee_ppm=1000)

    baseline_swap = baseline.swap_exact_in("retail", "token0", Decimal("10000"), 0)
    hook_swap = with_hook.swap_exact_in("retail", "token0", Decimal("10000"), 0)

    assert hook_swap.hook_fee_paid == Decimal("1")
    assert with_hook.pending_hook_fees0 == Decimal("1")
    assert hook_swap.amount_out < baseline_swap.amount_out
    assert hook_swap.post_sqrt_price_x96 > baseline_swap.post_sqrt_price_x96


def test_hook_fee_reinvest_uses_prior_pending_before_current_swap_fee():
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

    swap = pool.swap_exact_in("retail", "token0", Decimal("10000"), 100)

    assert swap.hook_fee_paid == Decimal("20")
    assert pool.hook_reinvested_liquidity == 1200
    assert pool.hook_reinvested0 == Decimal("1200")
    assert pool.hook_reinvested1 == Decimal("1200")
    assert pool.pending_hook_fees0 == Decimal("20")
    assert pool.pending_hook_fees1 == Decimal("300")
    assert pool.active_liquidity == active_before + 1200


def test_cl_position_collects_from_fee_growth_checkpoint():
    pool = Pool(active_liquidity=500_000, lp_fee_pips=3000)
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()

    apply_action(MintRange(lower_tick=-1200, upper_tick=1200, liquidity=500_000), vault, pool, market, 0)
    pool.swap_exact_in("retail", "token0", Decimal("10000"), 1)
    idle0_before_collect = vault.idle0
    apply_action(CollectFees(position_id=1), vault, pool, market, 2)

    assert vault.idle0 - idle0_before_collect == Decimal("14")
