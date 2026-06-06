from __future__ import annotations

from decimal import Decimal
from typing import Any

from .flow import dynamic_fee_pips


DFM_BASE_FEE_PIPS = 3000
DFM_HOOK_FEE_PPM = 100_000

SURGE_REASONS = {
    "volatile": "volatility cluster",
    "trend": "sustained directional flow",
    "trend_up": "sustained ETH buy flow",
    "trend_down": "sustained ETH sell flow",
    "mean_reversion": "order-flow reversal",
    "jump": "price-jump protection",
    "low_liquidity": "liquidity-depth shock",
    "borrow_stress": "borrow-utilization stress",
}


def apply_dfm_fee_state(pool: Any, scen: Any, regime: str, step: int) -> dict[str, Any]:
    state = dfm_fee_state(scen, regime, step)
    pool.lp_fee_pips = state["dfm_pool_swap_fee_pips"]
    pool.hook_fee_ppm = state["dfm_hook_fee_ppm"]
    pool.dynamic_fee_active = state["dfm_dynamic_fee_active"]
    pool.fee_surge_active = state["dfm_surge_triggered"]
    pool.dfm_base_fee_pips = state["dfm_base_fee_pips"]
    pool.dfm_surge_fee_pips = state["dfm_surge_fee_pips"]
    pool.dfm_surge_reason = state["dfm_surge_reason"]
    pool.dfm_surge_start_step = state["dfm_surge_start_step"]
    pool.dfm_surge_end_step = state["dfm_surge_end_step"]
    return state


def dfm_fee_state(scen: Any, regime: str, step: int) -> dict[str, Any]:
    dynamic = scen.fee_model == "aegis_dynamic"
    pool_swap_fee_pips = dynamic_fee_pips(regime, scen.fee_model, DFM_BASE_FEE_PIPS)
    surge_pips = max(0, pool_swap_fee_pips - DFM_BASE_FEE_PIPS)
    hook_fee_ppm = DFM_HOOK_FEE_PPM if dynamic else 0
    hook_fee_pips = pool_swap_fee_pips * hook_fee_ppm // 1_000_000
    total_fee_pips = pool_swap_fee_pips + hook_fee_pips
    start_step, end_step = surge_window(scen, step) if surge_pips else (None, None)
    reason = SURGE_REASONS.get(regime, "dynamic fee signal") if surge_pips else None
    return {
        "dfm_dynamic_fee_active": dynamic,
        "dfm_base_fee_pips": DFM_BASE_FEE_PIPS,
        "dfm_lp_fee_pips": pool_swap_fee_pips,
        "dfm_pool_swap_fee_pips": pool_swap_fee_pips,
        "dfm_surge_fee_pips": surge_pips,
        "dfm_hook_fee_ppm": hook_fee_ppm,
        "dfm_hook_fee_pips": hook_fee_pips,
        "dfm_total_fee_pips": total_fee_pips,
        "dfm_base_fee_bps": pips_to_bps(DFM_BASE_FEE_PIPS),
        "dfm_lp_fee_bps": pips_to_bps(pool_swap_fee_pips),
        "dfm_pool_swap_fee_bps": pips_to_bps(pool_swap_fee_pips),
        "dfm_surge_fee_bps": pips_to_bps(surge_pips),
        "dfm_hook_fee_bps": pips_to_bps(hook_fee_pips),
        "dfm_total_fee_bps": pips_to_bps(total_fee_pips),
        "dfm_fee_multiplier": Decimal(total_fee_pips) / Decimal(DFM_BASE_FEE_PIPS),
        "dfm_surge_triggered": surge_pips > 0,
        "dfm_surge_reason": reason,
        "dfm_surge_start_step": start_step,
        "dfm_surge_end_step": end_step,
    }


def surge_window(scen: Any, step: int) -> tuple[int, int]:
    if not scen.regime_schedule:
        return 0, scen.steps
    current_index = min(len(scen.regime_schedule) - 1, step * len(scen.regime_schedule) // max(1, scen.steps))
    start_step = current_index * scen.steps // len(scen.regime_schedule)
    end_step = (current_index + 1) * scen.steps // len(scen.regime_schedule)
    return start_step, min(scen.steps, end_step)


def pips_to_bps(value: int) -> Decimal:
    return Decimal(value) / Decimal(100)
