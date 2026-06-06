from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext

getcontext().prec = 100

Q96 = 2**96
Q128 = 2**128
MAX_SWAP_FEE = 1_000_000
MIN_TICK = -887272
MAX_TICK = 887272
MIN_SQRT_PRICE = 4295128739
MAX_SQRT_PRICE = 1461446703485210103287273052203988822378723970342


@dataclass(frozen=True)
class SwapStep:
    sqrt_price_next_x96: int
    amount_in: int
    amount_out: int
    fee_amount: int


def mul_div(a: int, b: int, denominator: int) -> int:
    return a * b // denominator


def mul_div_rounding_up(a: int, b: int, denominator: int) -> int:
    product = a * b
    return product // denominator + (1 if product % denominator else 0)


def div_rounding_up(numerator: int, denominator: int) -> int:
    return numerator // denominator + (1 if numerator % denominator else 0)


def get_sqrt_price_at_tick(tick: int) -> int:
    if tick < MIN_TICK or tick > MAX_TICK:
        raise ValueError("tick out of bounds")
    abs_tick = -tick if tick < 0 else tick
    price = 0x100000000000000000000000000000000
    if abs_tick & 0x1:
        price = 0xFFFcb933BD6FAD37AA2D162D1A594001
    if abs_tick & 0x2:
        price = (price * 0xFFF97272373D413259A46990580E213A) >> 128
    if abs_tick & 0x4:
        price = (price * 0xFFF2E50F5F656932EF12357CF3C7FDCC) >> 128
    if abs_tick & 0x8:
        price = (price * 0xFFE5CACA7E10E4E61C3624EAA0941CD0) >> 128
    if abs_tick & 0x10:
        price = (price * 0xFFCB9843D60F6159C9DB58835C926644) >> 128
    if abs_tick & 0x20:
        price = (price * 0xFF973B41FA98C081472E6896DFB254C0) >> 128
    if abs_tick & 0x40:
        price = (price * 0xFF2EA16466C96A3843EC78B326B52861) >> 128
    if abs_tick & 0x80:
        price = (price * 0xFE5DEE046A99A2A811C461F1969C3053) >> 128
    if abs_tick & 0x100:
        price = (price * 0xFCBE86C7900A88AEDCFFC83B479AA3A4) >> 128
    if abs_tick & 0x200:
        price = (price * 0xF987A7253AC413176F2B074CF7815E54) >> 128
    if abs_tick & 0x400:
        price = (price * 0xF3392B0822B70005940C7A398E4B70F3) >> 128
    if abs_tick & 0x800:
        price = (price * 0xE7159475A2C29B7443B29C7FA6E889D9) >> 128
    if abs_tick & 0x1000:
        price = (price * 0xD097F3BDFD2022B8845AD8F792AA5825) >> 128
    if abs_tick & 0x2000:
        price = (price * 0xA9F746462D870FDF8A65DC1F90E061E5) >> 128
    if abs_tick & 0x4000:
        price = (price * 0x70D869A156D2A1B890BB3DF62BAF32F7) >> 128
    if abs_tick & 0x8000:
        price = (price * 0x31BE135F97D08FD981231505542FCFA6) >> 128
    if abs_tick & 0x10000:
        price = (price * 0x9AA508B5B7A84E1C677DE54F3E99BC9) >> 128
    if abs_tick & 0x20000:
        price = (price * 0x5D6AF8DEDB81196699C329225EE604) >> 128
    if abs_tick & 0x40000:
        price = (price * 0x2216E584F5FA1EA926041BEDFE98) >> 128
    if abs_tick & 0x80000:
        price = (price * 0x48A170391F7DC42444E8FA2) >> 128
    if tick > 0:
        price = ((1 << 256) - 1) // price
    return (price >> 32) + (1 if price & ((1 << 32) - 1) else 0)


def get_tick_at_sqrt_price(sqrt_price_x96: int) -> int:
    if sqrt_price_x96 < MIN_SQRT_PRICE or sqrt_price_x96 >= MAX_SQRT_PRICE:
        raise ValueError("sqrt price out of bounds")
    lo = MIN_TICK
    hi = MAX_TICK
    while lo <= hi:
        mid = (lo + hi) // 2
        if get_sqrt_price_at_tick(mid) <= sqrt_price_x96:
            lo = mid + 1
        else:
            hi = mid - 1
    return hi


def sqrt_price_x96_to_price(sqrt_price_x96: int) -> Decimal:
    ratio = Decimal(sqrt_price_x96) / Decimal(Q96)
    return ratio * ratio


def price_to_tick(price: Decimal, spacing: int = 1) -> int:
    tick = get_tick_at_sqrt_price(price_to_sqrt_price_x96(price))
    return (tick // spacing) * spacing


def tick_to_price(tick: int) -> Decimal:
    return sqrt_price_x96_to_price(get_sqrt_price_at_tick(tick))


def price_to_sqrt_price_x96(price: Decimal) -> int:
    if price <= 0:
        raise ValueError("price must be positive")
    return int(price.sqrt() * Q96)


def round_toward_zero_tick(tick: int, spacing: int) -> int:
    return (abs(tick) // spacing) * spacing * (1 if tick >= 0 else -1)


def get_amount0_delta(sqrt_price_a_x96: int, sqrt_price_b_x96: int, liquidity: int, round_up: bool) -> int:
    if sqrt_price_a_x96 > sqrt_price_b_x96:
        sqrt_price_a_x96, sqrt_price_b_x96 = sqrt_price_b_x96, sqrt_price_a_x96
    if sqrt_price_a_x96 == 0:
        raise ValueError("invalid price")
    numerator1 = liquidity << 96
    numerator2 = sqrt_price_b_x96 - sqrt_price_a_x96
    if round_up:
        return div_rounding_up(mul_div_rounding_up(numerator1, numerator2, sqrt_price_b_x96), sqrt_price_a_x96)
    return mul_div(numerator1, numerator2, sqrt_price_b_x96) // sqrt_price_a_x96


def get_amount1_delta(sqrt_price_a_x96: int, sqrt_price_b_x96: int, liquidity: int, round_up: bool) -> int:
    if sqrt_price_a_x96 > sqrt_price_b_x96:
        sqrt_price_a_x96, sqrt_price_b_x96 = sqrt_price_b_x96, sqrt_price_a_x96
    numerator = sqrt_price_b_x96 - sqrt_price_a_x96
    return mul_div_rounding_up(liquidity, numerator, Q96) if round_up else mul_div(liquidity, numerator, Q96)


def get_next_sqrt_price_from_amount0_rounding_up(sqrt_price_x96: int, liquidity: int, amount: int, add: bool) -> int:
    if amount == 0:
        return sqrt_price_x96
    numerator1 = liquidity << 96
    product = amount * sqrt_price_x96
    if add:
        denominator = numerator1 + product
        return mul_div_rounding_up(numerator1, sqrt_price_x96, denominator)
    if numerator1 <= product:
        raise ValueError("price overflow")
    denominator = numerator1 - product
    return mul_div_rounding_up(numerator1, sqrt_price_x96, denominator)


def get_next_sqrt_price_from_amount1_rounding_down(sqrt_price_x96: int, liquidity: int, amount: int, add: bool) -> int:
    if add:
        quotient = (amount << 96) // liquidity if amount <= (1 << 160) - 1 else mul_div(amount, Q96, liquidity)
        return sqrt_price_x96 + quotient
    quotient = div_rounding_up(amount << 96, liquidity) if amount <= (1 << 160) - 1 else mul_div_rounding_up(amount, Q96, liquidity)
    if sqrt_price_x96 <= quotient:
        raise ValueError("not enough liquidity")
    return sqrt_price_x96 - quotient


def get_next_sqrt_price_from_input(sqrt_price_x96: int, liquidity: int, amount_in: int, zero_for_one: bool) -> int:
    if sqrt_price_x96 == 0 or liquidity == 0:
        raise ValueError("invalid price or liquidity")
    if zero_for_one:
        return get_next_sqrt_price_from_amount0_rounding_up(sqrt_price_x96, liquidity, amount_in, True)
    return get_next_sqrt_price_from_amount1_rounding_down(sqrt_price_x96, liquidity, amount_in, True)


def get_next_sqrt_price_from_output(sqrt_price_x96: int, liquidity: int, amount_out: int, zero_for_one: bool) -> int:
    if sqrt_price_x96 == 0 or liquidity == 0:
        raise ValueError("invalid price or liquidity")
    if zero_for_one:
        return get_next_sqrt_price_from_amount1_rounding_down(sqrt_price_x96, liquidity, amount_out, False)
    return get_next_sqrt_price_from_amount0_rounding_up(sqrt_price_x96, liquidity, amount_out, False)


def compute_swap_step(
    sqrt_price_current_x96: int,
    sqrt_price_target_x96: int,
    liquidity: int,
    amount_remaining: int,
    fee_pips: int,
) -> SwapStep:
    if fee_pips > MAX_SWAP_FEE:
        raise ValueError("fee too large")
    zero_for_one = sqrt_price_current_x96 >= sqrt_price_target_x96
    exact_in = amount_remaining < 0
    if exact_in:
        amount_remaining_less_fee = mul_div(-amount_remaining, MAX_SWAP_FEE - fee_pips, MAX_SWAP_FEE)
        amount_in = (
            get_amount0_delta(sqrt_price_target_x96, sqrt_price_current_x96, liquidity, True)
            if zero_for_one
            else get_amount1_delta(sqrt_price_current_x96, sqrt_price_target_x96, liquidity, True)
        )
        if amount_remaining_less_fee >= amount_in:
            sqrt_price_next_x96 = sqrt_price_target_x96
            fee_amount = amount_in if fee_pips == MAX_SWAP_FEE else mul_div_rounding_up(amount_in, fee_pips, MAX_SWAP_FEE - fee_pips)
        else:
            amount_in = amount_remaining_less_fee
            sqrt_price_next_x96 = get_next_sqrt_price_from_input(sqrt_price_current_x96, liquidity, amount_in, zero_for_one)
            fee_amount = -amount_remaining - amount_in
        amount_out = (
            get_amount1_delta(sqrt_price_next_x96, sqrt_price_current_x96, liquidity, False)
            if zero_for_one
            else get_amount0_delta(sqrt_price_current_x96, sqrt_price_next_x96, liquidity, False)
        )
    else:
        amount_out = (
            get_amount1_delta(sqrt_price_target_x96, sqrt_price_current_x96, liquidity, False)
            if zero_for_one
            else get_amount0_delta(sqrt_price_current_x96, sqrt_price_target_x96, liquidity, False)
        )
        if amount_remaining >= amount_out:
            sqrt_price_next_x96 = sqrt_price_target_x96
        else:
            amount_out = amount_remaining
            sqrt_price_next_x96 = get_next_sqrt_price_from_output(sqrt_price_current_x96, liquidity, amount_out, zero_for_one)
        amount_in = (
            get_amount0_delta(sqrt_price_next_x96, sqrt_price_current_x96, liquidity, True)
            if zero_for_one
            else get_amount1_delta(sqrt_price_current_x96, sqrt_price_next_x96, liquidity, True)
        )
        fee_amount = mul_div_rounding_up(amount_in, fee_pips, MAX_SWAP_FEE - fee_pips)
    return SwapStep(sqrt_price_next_x96, amount_in, amount_out, fee_amount)


def liquidity_for_principal(amount_l: int, borrow_index_wad: int) -> int:
    return (amount_l * borrow_index_wad + 10**18 - 1) // 10**18


def principal_from_liquidity(liquidity: int, borrow_index_wad: int) -> int:
    return liquidity * 10**18 // borrow_index_wad


def amount_delta_for_range(liquidity: int, price: Decimal, lower_tick: int, upper_tick: int) -> tuple[Decimal, Decimal]:
    sqrt_price = price_to_sqrt_price_x96(price)
    sqrt_lower = get_sqrt_price_at_tick(lower_tick)
    sqrt_upper = get_sqrt_price_at_tick(upper_tick)
    if sqrt_price <= sqrt_lower:
        return Decimal(get_amount0_delta(sqrt_lower, sqrt_upper, liquidity, True)), Decimal("0")
    if sqrt_price >= sqrt_upper:
        return Decimal("0"), Decimal(get_amount1_delta(sqrt_lower, sqrt_upper, liquidity, True))
    amount0 = get_amount0_delta(sqrt_price, sqrt_upper, liquidity, True)
    amount1 = get_amount1_delta(sqrt_lower, sqrt_price, liquidity, True)
    return Decimal(amount0), Decimal(amount1)


def amount_delta_for_range_scaled(
    liquidity: int,
    price: Decimal,
    lower_tick: int,
    upper_tick: int,
    amount_scale: int = 1,
) -> tuple[Decimal, Decimal]:
    scale = max(1, amount_scale)
    if scale == 1:
        return amount_delta_for_range(liquidity, price, lower_tick, upper_tick)
    amount0, amount1 = amount_delta_for_range(liquidity * scale, price, lower_tick, upper_tick)
    divisor = Decimal(scale)
    return amount0 / divisor, amount1 / divisor
