from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isqrt

from .v4_math import (
    MAX_TICK,
    MIN_TICK,
    get_amount0_delta,
    get_amount1_delta,
    get_sqrt_price_at_tick,
    price_to_sqrt_price_x96,
    round_toward_zero_tick,
)

WAD = 10**18
UTILIZATION_CAP_PIPS = 950_000
MICRO_LIQ_ORACLE_BUFFER_PIPS = 4_000
MICRO_LIQ_MIN_RAMP_WIDTH_PIPS = 1_000
MICRO_LIQ_MAX_SWAP_FEE_PIPS = 10_000
MICRO_LIQ_FEE_MAX_PIPS = 10_000
PIPS_DENOMINATOR = 1_000_000


@dataclass
class AegisMarket:
    lender_equity_l: int = 10_000_000
    total_rL_borrowed: int = 0
    borrow_index_wad: int = WAD
    full_util_rate_per_second_wad: int = 1_000_000_000
    utilization_cap_pips: int = UTILIZATION_CAP_PIPS
    hook_fee_ppm: int = 0
    dynamic_fee_active: bool = False

    def borrowed_l_wad(self) -> int:
        return self.total_rL_borrowed * self.borrow_index_wad

    def debt_l(self, principal_l: int) -> int:
        return principal_l * self.borrow_index_wad // WAD

    def utilization_pips(self) -> int:
        if self.lender_equity_l <= 0:
            return 1_000_000
        equity_l_wad = self.lender_equity_l * WAD
        return min(1_000_000, self.borrowed_l_wad() * 1_000_000 // equity_l_wad)

    def can_borrow(self, amount_l: int) -> bool:
        projected = self.total_rL_borrowed + amount_l
        return projected * 1_000_000 // self.lender_equity_l <= self.utilization_cap_pips

    def borrow(self, amount_l: int) -> None:
        if amount_l <= 0:
            raise ValueError("ERR_NEGATIVE_OR_ZERO_AMOUNT")
        if not self.can_borrow(amount_l):
            raise ValueError("ERR_UTILIZATION_CAP")
        self.total_rL_borrowed += amount_l

    def repay(self, amount_l: int) -> None:
        self.total_rL_borrowed = max(0, self.total_rL_borrowed - amount_l)

    def accrue_at_rate(self, seconds: int, rate_per_second_wad: int) -> int:
        if self.total_rL_borrowed == 0:
            return 0
        delta = self.borrow_index_wad * rate_per_second_wad * seconds // WAD
        self.borrow_index_wad += delta
        return self.total_rL_borrowed * delta

    def accrue(self, seconds: int) -> Decimal:
        utilization = Decimal(self.utilization_pips()) / Decimal(1_000_000)
        rate = int(Decimal(self.full_util_rate_per_second_wad) * utilization)
        interest_wad = self.accrue_at_rate(seconds, rate)
        return Decimal(interest_wad) / Decimal(WAD)


def compute_ltv_thresholds(fee_pips: int, dynamic_fee: bool = False) -> tuple[int, int]:
    hard = 1_000_000 - MICRO_LIQ_ORACLE_BUFFER_PIPS
    fee_width = MICRO_LIQ_MAX_SWAP_FEE_PIPS if dynamic_fee else fee_pips
    max_ltv = hard - max(fee_width, MICRO_LIQ_MIN_RAMP_WIDTH_PIPS)
    return max_ltv, hard


def repay_fraction_pips(ltv_pips: int, max_ltv_pips: int, hard_ltv_pips: int) -> int:
    if ltv_pips < max_ltv_pips:
        return 0
    kappa = (max_ltv_pips + hard_ltv_pips) // 2
    if ltv_pips < kappa:
        span = kappa - max_ltv_pips
        progress = ltv_pips - max_ltv_pips
        return 2_000 + 198_000 * progress // span
    if ltv_pips < hard_ltv_pips:
        span = hard_ltv_pips - kappa
        progress = ltv_pips - kappa
        return 200_000 + 800_000 * progress // span
    return PIPS_DENOMINATOR


def keeper_fee_pips(ltv_pips: int, max_ltv_pips: int, hard_ltv_pips: int) -> int:
    if ltv_pips <= max_ltv_pips:
        return 0
    span = hard_ltv_pips - max_ltv_pips
    progress = span if ltv_pips >= hard_ltv_pips else ltv_pips - max_ltv_pips
    return MICRO_LIQ_FEE_MAX_PIPS * progress // span


def micro_liq_swap_deficit(idle0: Decimal, idle1: Decimal, amount0_required: Decimal, amount1_required: Decimal) -> tuple[bool, Decimal]:
    available0 = max(Decimal("0"), idle0)
    available1 = max(Decimal("0"), idle1)
    deficit0 = max(Decimal("0"), amount0_required - available0)
    deficit1 = max(Decimal("0"), amount1_required - available1)
    if deficit0 > 0 and deficit1 > 0:
        if available0 * amount1_required >= available1 * amount0_required:
            return True, deficit1
        return False, deficit0
    if deficit0 > 0:
        return False, deficit0
    if deficit1 > 0:
        return True, deficit1
    return False, Decimal("0")


def liquidity_for_principal(amount_l: int, borrow_index_wad: int) -> int:
    return (amount_l * borrow_index_wad + WAD - 1) // WAD


def principal_from_liquidity(liquidity: int, borrow_index_wad: int) -> int:
    return liquidity * WAD // borrow_index_wad


def full_range_ticks(tick_spacing: int = 60) -> tuple[int, int]:
    return round_toward_zero_tick(MIN_TICK, tick_spacing), round_toward_zero_tick(MAX_TICK, tick_spacing)


def full_range_amounts_for_liquidity(
    liquidity: int,
    price: Decimal = Decimal("1"),
    tick_spacing: int = 60,
    amount_scale: int = 1,
) -> tuple[Decimal, Decimal]:
    if liquidity <= 0:
        return Decimal("0"), Decimal("0")
    scale = max(1, amount_scale)
    lower_tick, upper_tick = full_range_ticks(tick_spacing)
    sqrt_price = price_to_sqrt_price_x96(price)
    sqrt_lower = get_sqrt_price_at_tick(lower_tick)
    sqrt_upper = get_sqrt_price_at_tick(upper_tick)
    amount0 = get_amount0_delta(sqrt_price, sqrt_upper, liquidity * scale, True)
    amount1 = get_amount1_delta(sqrt_lower, sqrt_price, liquidity * scale, True)
    divisor = Decimal(scale)
    return Decimal(amount0) / divisor, Decimal(amount1) / divisor


def full_range_liquidity_for_amounts(
    idle0: Decimal,
    idle1: Decimal,
    price: Decimal = Decimal("1"),
    tick_spacing: int = 60,
    amount_scale: int = 1,
) -> int:
    available0 = max(Decimal("0"), idle0)
    available1 = max(Decimal("0"), idle1)
    if available0 == 0 or available1 == 0:
        return 0
    per0, per1 = full_range_amounts_for_liquidity(1, price, tick_spacing, amount_scale)
    high = max(available0 // max(1, per0), available1 // max(1, per1), 1)
    high = int(high)
    while True:
        amount0, amount1 = full_range_amounts_for_liquidity(high, price, tick_spacing, amount_scale)
        if amount0 > available0 or amount1 > available1:
            break
        high *= 2
    lo = 0
    hi = high
    while lo < hi:
        mid = (lo + hi + 1) // 2
        amount0, amount1 = full_range_amounts_for_liquidity(mid, price, tick_spacing, amount_scale)
        if amount0 <= available0 and amount1 <= available1:
            lo = mid
        else:
            hi = mid - 1
    return lo


def repay_bridge(
    requested_l: int,
    idle0: Decimal,
    idle1: Decimal,
    borrow_index_wad: int,
    price: Decimal = Decimal("1"),
    tick_spacing: int = 60,
    amount_scale: int = 1,
) -> dict[str, int | Decimal]:
    target_liquidity = liquidity_for_principal(requested_l, borrow_index_wad)
    available_liquidity = full_range_liquidity_for_amounts(idle0, idle1, price, tick_spacing, amount_scale)
    minted_liquidity = min(target_liquidity, available_liquidity)
    idle0_consumed, idle1_consumed = full_range_amounts_for_liquidity(minted_liquidity, price, tick_spacing, amount_scale)
    geometric_mean = int((max(Decimal("0"), idle0_consumed) * max(Decimal("0"), idle1_consumed)).sqrt())
    actual_repaid_l = min(requested_l, principal_from_liquidity(geometric_mean, borrow_index_wad))
    return {
        "target_liquidity": target_liquidity,
        "idle0_required": full_range_amounts_for_liquidity(target_liquidity, price, tick_spacing, amount_scale)[0],
        "idle1_required": full_range_amounts_for_liquidity(target_liquidity, price, tick_spacing, amount_scale)[1],
        "bridge_liquidity": minted_liquidity,
        "idle0_consumed": idle0_consumed,
        "idle1_consumed": idle1_consumed,
        "geometric_mean": geometric_mean,
        "actual_repaid_l": actual_repaid_l,
        "residual_l": max(0, requested_l - actual_repaid_l),
    }


def debt_repayment_liability(
    principal_l: int,
    borrow_index_wad: int,
    price: Decimal = Decimal("1"),
    tick_spacing: int = 60,
    amount_scale: int = 1,
) -> dict[str, object]:
    if principal_l <= 0:
        return {
            "liability0": Decimal("0"),
            "liability1": Decimal("0"),
            "value": Decimal("0"),
            "iterations": [],
            "residual_l": 0,
        }
    target_liquidity = liquidity_for_principal(principal_l, borrow_index_wad)
    amount0, amount1 = full_range_amounts_for_liquidity(target_liquidity, price, tick_spacing, amount_scale)
    geometric_mean = int((max(Decimal("0"), amount0) * max(Decimal("0"), amount1)).sqrt())
    repaid_l = min(principal_l, principal_from_liquidity(geometric_mean, borrow_index_wad))
    residual_l = max(0, principal_l - repaid_l)
    liability0 = Decimal(amount0)
    liability1 = Decimal(amount1)
    return {
        "liability0": liability0,
        "liability1": liability1,
        "value": liability0 * price + liability1,
        "iterations": [
            {
                "target_liquidity": target_liquidity,
                "liability0": str(liability0),
                "liability1": str(liability1),
                "bridge_liquidity": target_liquidity,
                "geometric_mean": geometric_mean,
                "repaid_l": repaid_l,
                "residual_l": residual_l,
            }
        ],
        "residual_l": residual_l,
    }
