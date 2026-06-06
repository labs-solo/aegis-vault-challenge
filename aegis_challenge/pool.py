from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .api import InitializedTick, PoolState, SwapEvent
from .v4_math import (
    MAX_SQRT_PRICE,
    MAX_TICK,
    MIN_SQRT_PRICE,
    MIN_TICK,
    Q128,
    compute_swap_step,
    get_sqrt_price_at_tick,
    get_tick_at_sqrt_price,
    price_to_sqrt_price_x96,
    round_toward_zero_tick,
    sqrt_price_x96_to_price,
)


@dataclass
class Pool:
    price: Decimal = Decimal("1")
    tick_spacing: int = 60
    active_liquidity: int = 10_000_000
    lp_fee_pips: int = 3000
    protocol_fee_pips: int = 0
    hook_fee_ppm: int = 0
    hook_reinvest_min_liquidity: int = 1_000
    hook_reinvest_cooldown_steps: int = 60
    fee_growth_global0_x128: int = 0
    fee_growth_global1_x128: int = 0
    pending_hook_fees0: Decimal = Decimal("0")
    pending_hook_fees1: Decimal = Decimal("0")
    hook_reinvested_liquidity: int = 0
    hook_reinvested0: Decimal = Decimal("0")
    hook_reinvested1: Decimal = Decimal("0")
    hook_last_reinvest_step: int = -1_000_000_000
    dynamic_fee_active: bool = False
    fee_surge_active: bool = False
    dfm_base_fee_pips: int = 3000
    dfm_surge_fee_pips: int = 0
    dfm_surge_reason: str | None = None
    dfm_surge_start_step: int | None = None
    dfm_surge_end_step: int | None = None
    event_index: int = 0
    amount_scale: int = 1
    sqrt_price_x96_value: int = 0
    current_tick: int = 0
    initialized_ticks: dict[int, int] = field(default_factory=dict)
    fee_growth_outside0_x128: dict[int, int] = field(default_factory=dict)
    fee_growth_outside1_x128: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sqrt_price_x96_value == 0:
            self.sqrt_price_x96_value = price_to_sqrt_price_x96(self.price)
        self.current_tick = get_tick_at_sqrt_price(self.sqrt_price_x96_value)
        self.price = sqrt_price_x96_to_price(self.sqrt_price_x96_value)

    @property
    def tick(self) -> int:
        return self.current_tick

    @property
    def sqrt_price_x96(self) -> int:
        return self.sqrt_price_x96_value

    def all_in_fee_pips(self) -> int:
        hook_pips = (self.lp_fee_pips + self.protocol_fee_pips) * self.hook_fee_ppm // 1_000_000
        return self.lp_fee_pips + self.protocol_fee_pips + hook_pips

    def state(self) -> PoolState:
        ticks = tuple(
            InitializedTick(
                tick=t,
                liquidity_gross=abs(net),
                liquidity_net=net,
                fee_growth_outside0_x128=self.fee_growth_outside0_x128.get(t, 0),
                fee_growth_outside1_x128=self.fee_growth_outside1_x128.get(t, 0),
            )
            for t, net in sorted(self.initialized_ticks.items())
        )
        hook_pips = (self.lp_fee_pips + self.protocol_fee_pips) * self.hook_fee_ppm // 1_000_000
        return PoolState(
            sqrt_price_x96=self.sqrt_price_x96,
            tick=self.tick,
            tick_spacing=self.tick_spacing,
            full_range_min_tick=round_toward_zero_tick(MIN_TICK, self.tick_spacing),
            full_range_max_tick=round_toward_zero_tick(MAX_TICK, self.tick_spacing),
            active_liquidity=self.active_liquidity,
            initialized_ticks=ticks,
            fee_pips=self.lp_fee_pips,
            lp_fee_pips=self.lp_fee_pips,
            protocol_fee_pips=self.protocol_fee_pips,
            pool_swap_fee_pips=self.lp_fee_pips + self.protocol_fee_pips,
            hook_fee_ppm=self.hook_fee_ppm,
            hook_fee_pips_estimate=hook_pips,
            all_in_input_fee_pips_estimate=self.lp_fee_pips + self.protocol_fee_pips + hook_pips,
            dynamic_fee_active=self.dynamic_fee_active,
            fee_surge_active=self.fee_surge_active,
            dfm_base_fee_pips=self.dfm_base_fee_pips,
            dfm_lp_fee_pips=self.lp_fee_pips,
            dfm_surge_fee_pips=self.dfm_surge_fee_pips,
            dfm_hook_fee_pips_estimate=hook_pips,
            dfm_total_fee_pips_estimate=self.lp_fee_pips + self.protocol_fee_pips + hook_pips,
            dfm_fee_multiplier=Decimal(self.lp_fee_pips + self.protocol_fee_pips + hook_pips) / Decimal(max(1, self.dfm_base_fee_pips)),
            dfm_surge_reason=self.dfm_surge_reason,
            dfm_surge_start_step=self.dfm_surge_start_step,
            dfm_surge_end_step=self.dfm_surge_end_step,
            fee_growth_global0_x128=self.fee_growth_global0_x128,
            fee_growth_global1_x128=self.fee_growth_global1_x128,
            pending_hook_fees0=self.pending_hook_fees0,
            pending_hook_fees1=self.pending_hook_fees1,
            hook_reinvested_liquidity=self.hook_reinvested_liquidity,
            hook_reinvested0=self.hook_reinvested0,
            hook_reinvested1=self.hook_reinvested1,
            accounting_scale=self.amount_scale,
        )

    def swap_exact_in(self, actor: str, token_in: str, amount_in: Decimal, step: int) -> SwapEvent:
        pre_tick = self.tick
        pre_sqrt = self.sqrt_price_x96
        gross_input_amount = self._to_raw_amount(amount_in)
        fee_pips = min(1_000_000, self.lp_fee_pips + self.protocol_fee_pips)
        hook_fee_units = self._hook_fee_units(gross_input_amount, fee_pips)
        hook_fee = self._to_public_amount(hook_fee_units)
        input_amount = max(0, gross_input_amount - hook_fee_units)
        self.try_reinvest_hook_fees(step)
        zero_for_one = token_in == "token0"
        amount_remaining = -input_amount
        total_fee = 0
        total_lp_fee = 0
        total_protocol_fee = 0
        total_out = 0
        crossed_list: list[int] = []
        while amount_remaining < 0:
            target_tick = self._next_initialized_tick(zero_for_one)
            target_sqrt = get_sqrt_price_at_tick(target_tick) if target_tick is not None else (MIN_SQRT_PRICE if zero_for_one else MAX_SQRT_PRICE - 1)
            step_result = compute_swap_step(
                self.sqrt_price_x96,
                target_sqrt,
                self._raw_active_liquidity(),
                amount_remaining,
                fee_pips,
            )
            consumed = step_result.amount_in + step_result.fee_amount
            if consumed == 0:
                break
            amount_remaining += consumed
            total_fee += step_result.fee_amount
            protocol_fee_step = 0
            if self.protocol_fee_pips and fee_pips:
                protocol_fee_step = step_result.fee_amount * self.protocol_fee_pips // fee_pips
            lp_fee_step = step_result.fee_amount - protocol_fee_step
            total_protocol_fee += protocol_fee_step
            total_lp_fee += lp_fee_step
            raw_liquidity = self._raw_active_liquidity()
            if raw_liquidity > 0:
                growth_delta = lp_fee_step * Q128 // raw_liquidity
                if token_in == "token0":
                    self.fee_growth_global0_x128 += growth_delta
                else:
                    self.fee_growth_global1_x128 += growth_delta
            total_out += step_result.amount_out
            self.sqrt_price_x96_value = step_result.sqrt_price_next_x96
            if target_tick is not None and step_result.sqrt_price_next_x96 == target_sqrt:
                crossed_list.append(target_tick)
                self.fee_growth_outside0_x128[target_tick] = self.fee_growth_global0_x128 - self.fee_growth_outside0_x128.get(target_tick, 0)
                self.fee_growth_outside1_x128[target_tick] = self.fee_growth_global1_x128 - self.fee_growth_outside1_x128.get(target_tick, 0)
                liquidity_net = self.initialized_ticks[target_tick]
                self.active_liquidity += -liquidity_net if zero_for_one else liquidity_net
                self.current_tick = target_tick - 1 if zero_for_one else target_tick
            else:
                self.current_tick = get_tick_at_sqrt_price(self.sqrt_price_x96_value)
                break
        _ = total_fee
        protocol_fee = self._to_public_amount(total_protocol_fee)
        lp_fee = self._to_public_amount(total_lp_fee)
        amount_out = self._to_public_amount(total_out)
        self.price = sqrt_price_x96_to_price(self.sqrt_price_x96_value)
        post_tick = self.tick
        if token_in == "token0":
            self.pending_hook_fees0 += hook_fee
        else:
            self.pending_hook_fees1 += hook_fee
        self.event_index += 1
        return SwapEvent(
            event_index=self.event_index,
            step=step,
            actor=actor,  # type: ignore[arg-type]
            token_in=token_in,  # type: ignore[arg-type]
            amount_in=amount_in,
            amount_out=amount_out,
            pre_tick=pre_tick,
            post_tick=post_tick,
            pre_sqrt_price_x96=pre_sqrt,
            post_sqrt_price_x96=self.sqrt_price_x96,
            ticks_crossed=tuple(crossed_list),
            lp_fee_paid=lp_fee,
            protocol_fee_paid=protocol_fee,
            hook_fee_paid=hook_fee,
        )

    def try_reinvest_hook_fees(self, step: int) -> int:
        if step < self.hook_last_reinvest_step + self.hook_reinvest_cooldown_steps:
            return 0
        liquidity = min(int(self.pending_hook_fees0), int(self.pending_hook_fees1))
        if liquidity < self.hook_reinvest_min_liquidity:
            return 0
        self.pending_hook_fees0 -= Decimal(liquidity)
        self.pending_hook_fees1 -= Decimal(liquidity)
        self.hook_reinvested_liquidity += liquidity
        self.hook_reinvested0 += Decimal(liquidity)
        self.hook_reinvested1 += Decimal(liquidity)
        self.active_liquidity += liquidity
        self.hook_last_reinvest_step = step
        return liquidity

    def _hook_fee_units(self, gross_input_amount: int, fee_pips: int) -> int:
        if self.hook_fee_ppm <= 0 or gross_input_amount <= 0 or fee_pips <= 0:
            return 0
        swap_fee_amount = gross_input_amount * fee_pips // 1_000_000
        if swap_fee_amount == 0:
            return 0
        return (swap_fee_amount * self.hook_fee_ppm + 1_000_000 - 1) // 1_000_000

    def _raw_active_liquidity(self) -> int:
        return max(self.active_liquidity * max(1, self.amount_scale), 1)

    def _to_raw_amount(self, amount: Decimal) -> int:
        return max(0, int(amount * Decimal(max(1, self.amount_scale))))

    def _to_public_amount(self, raw_amount: int) -> Decimal:
        return Decimal(raw_amount) / Decimal(max(1, self.amount_scale))

    def _next_initialized_tick(self, zero_for_one: bool) -> int | None:
        if zero_for_one:
            candidates = [tick for tick in self.initialized_ticks if tick < self.tick]
            return max(candidates) if candidates else None
        candidates = [tick for tick in self.initialized_ticks if tick > self.tick]
        return min(candidates) if candidates else None
