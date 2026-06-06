from __future__ import annotations

import json
from decimal import Decimal

from aegis_challenge.aegis_market import AegisMarket
from aegis_challenge.api import CollectFees, MintRange
from aegis_challenge.pool import Pool
from aegis_challenge.runner import apply_action
from aegis_challenge.v4_math import Q96, compute_swap_step, get_amount0_delta, get_amount1_delta, get_sqrt_price_at_tick, get_tick_at_sqrt_price
from aegis_challenge.vault import Vault


FIXTURE_VERSION = "aegis-vault-challenge-v1"
GENERATOR = {
    "aegis_engine_commit": "08d389e8b7c53cac1cc9ba05a85dfee596672465",
    "v4_core_commit": "59d3ecf53afa9264a16bba0e38f4c5d2231f80bc",
    "v4_periphery_commit": "60cd93803ac2b7fa65fd6cd351fd5fd4cc8c9db5",
    "rounding_policy": "local-python-v4-reference-subset",
}


def build_vectors() -> dict:
    swap0 = compute_swap_step(Q96, get_sqrt_price_at_tick(-120), 1_000_000, -1000, 0)
    swap1 = compute_swap_step(Q96, get_sqrt_price_at_tick(120), 1_000_000, -1000, 0)

    tick_up_amount = get_amount1_delta(Q96, get_sqrt_price_at_tick(60), 1_000_000, True)
    tick_up_pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0, initialized_ticks={60: -250_000})
    tick_up = tick_up_pool.swap_exact_in("retail", "token1", Decimal(tick_up_amount), 0)

    tick_down_amount = get_amount0_delta(get_sqrt_price_at_tick(-60), Q96, 1_000_000, True)
    tick_down_pool = Pool(active_liquidity=1_000_000, lp_fee_pips=0, initialized_ticks={-60: 250_000})
    tick_down = tick_down_pool.swap_exact_in("retail", "token0", Decimal(tick_down_amount), 0)

    fee_collect = fee_collect_vector()
    protocol_fee = protocol_fee_vector()

    return {
        "fixture_version": FIXTURE_VERSION,
        "generator": GENERATOR,
        "vectors": [
            {
                "id": "UV4-TICK-000",
                "input": {"ticks": [-887272, 0, 887272]},
                "expected": {
                    "sqrt_price_x96": [
                        str(get_sqrt_price_at_tick(-887272)),
                        str(get_sqrt_price_at_tick(0)),
                        str(get_sqrt_price_at_tick(887272)),
                    ]
                },
                "source": "v4-core TickMath",
            },
            {
                "id": "UV4-SWAP-001",
                "input": {
                    "sqrt_price_x96": str(Q96),
                    "current_tick": 0,
                    "tick_spacing": 60,
                    "active_liquidity": "1000000",
                    "fee_pips": 0,
                    "token_in": "token0",
                    "amount_in": "1000",
                    "next_initialized_tick": -120,
                },
                "expected": {
                    "sqrt_price_x96_after": str(swap0.sqrt_price_next_x96),
                    "amount0_in": str(swap0.amount_in),
                    "amount1_out": str(swap0.amount_out),
                    "final_tick": get_tick_at_sqrt_price(swap0.sqrt_price_next_x96),
                    "active_liquidity_after": "1000000",
                },
                "source": "v4-core SwapMath",
            },
            {
                "id": "UV4-SWAP-002",
                "input": {
                    "sqrt_price_x96": str(Q96),
                    "current_tick": 0,
                    "tick_spacing": 60,
                    "active_liquidity": "1000000",
                    "fee_pips": 0,
                    "token_in": "token1",
                    "amount_in": "1000",
                    "next_initialized_tick": 120,
                },
                "expected": {
                    "sqrt_price_x96_after": str(swap1.sqrt_price_next_x96),
                    "amount1_in": str(swap1.amount_in),
                    "amount0_out": str(swap1.amount_out),
                    "final_tick": get_tick_at_sqrt_price(swap1.sqrt_price_next_x96),
                    "active_liquidity_after": "1000000",
                },
                "source": "v4-core SwapMath",
            },
            {
                "id": "UV4-TICK-001",
                "input": {
                    "current_tick": 0,
                    "active_liquidity_before": "1000000",
                    "initialized_tick": 60,
                    "liquidity_net": "-250000",
                    "token_in": "token1",
                    "amount_in": str(tick_up_amount),
                },
                "expected": {
                    "crossed_tick": tick_up.ticks_crossed[0],
                    "amount_in_consumed": str(tick_up.amount_in),
                    "amount_out": str(tick_up.amount_out),
                    "sqrt_price_x96_after": str(tick_up.post_sqrt_price_x96),
                    "active_liquidity_after_cross": str(tick_up_pool.active_liquidity),
                    "fee_growth_outside0_x128_after": str(tick_up_pool.fee_growth_outside0_x128[60]),
                    "fee_growth_outside1_x128_after": str(tick_up_pool.fee_growth_outside1_x128[60]),
                    "current_tick_after_cross": tick_up_pool.tick,
                },
                "source": "v4-core Pool.swap tick crossing upper",
            },
            {
                "id": "UV4-TICK-002",
                "input": {
                    "current_tick": 0,
                    "active_liquidity_before": "1000000",
                    "initialized_tick": -60,
                    "liquidity_net": "250000",
                    "token_in": "token0",
                    "amount_in": str(tick_down_amount),
                },
                "expected": {
                    "crossed_tick": tick_down.ticks_crossed[0],
                    "amount_in_consumed": str(tick_down.amount_in),
                    "amount_out": str(tick_down.amount_out),
                    "sqrt_price_x96_after": str(tick_down.post_sqrt_price_x96),
                    "active_liquidity_after_cross": str(tick_down_pool.active_liquidity),
                    "fee_growth_outside0_x128_after": str(tick_down_pool.fee_growth_outside0_x128[-60]),
                    "fee_growth_outside1_x128_after": str(tick_down_pool.fee_growth_outside1_x128[-60]),
                    "current_tick_after_cross": tick_down_pool.tick,
                },
                "source": "v4-core Pool.swap tick crossing lower",
            },
            fee_collect,
            protocol_fee,
        ],
    }


def fee_collect_vector() -> dict:
    pool = Pool(active_liquidity=500_000, lp_fee_pips=3000)
    vault = Vault(idle0=Decimal("1000000"), idle1=Decimal("1000000"))
    market = AegisMarket()
    apply_action(MintRange(lower_tick=-1200, upper_tick=1200, liquidity=500_000), vault, pool, market, 0)
    pool.swap_exact_in("retail", "token0", Decimal("10000"), 1)
    before = vault.idle0
    apply_action(CollectFees(position_id=1), vault, pool, market, 2)
    return {
        "id": "UV4-FEE-001",
        "input": {
            "position_range": [-1200, 1200],
            "position_liquidity": "500000",
            "active_liquidity_before_position": "500000",
            "fee_pips": 3000,
            "token_in": "token0",
            "amount_in": "10000",
        },
        "expected": {
            "total_fee_amount0": "30",
            "lp_fee_amount0": "30",
            "protocol_fee_amount0": "0",
            "fee_growth_global0_delta_x128": str(pool.fee_growth_global0_x128),
            "position_owed0": str(vault.idle0 - before),
            "collect_idle0_delta": str(vault.idle0 - before),
        },
        "source": "v4-core SwapMath fee growth subset",
    }


def protocol_fee_vector() -> dict:
    pool = Pool(active_liquidity=1_000_000, lp_fee_pips=3000, protocol_fee_pips=1000)
    event = pool.swap_exact_in("retail", "token0", Decimal("10000"), 0)
    return {
        "id": "UV4-FEE-002",
        "input": {
            "active_liquidity": "1000000",
            "lp_fee_pips": 3000,
            "protocol_fee_pips": 1000,
            "token_in": "token0",
            "amount_in": "10000",
        },
        "expected": {
            "pool_swap_fee_pips": pool.state().pool_swap_fee_pips,
            "total_pool_fee_amount": str(event.lp_fee_paid + event.protocol_fee_paid),
            "protocol_fee_amount": str(event.protocol_fee_paid),
            "lp_fee_amount": str(event.lp_fee_paid),
            "fee_growth_global0_delta_x128": str(pool.fee_growth_global0_x128),
        },
        "source": "v4-core SwapMath protocol-fee split subset",
    }


def main() -> int:
    print(json.dumps(build_vectors(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
