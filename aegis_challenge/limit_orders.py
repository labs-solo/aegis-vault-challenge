from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .api import FillEvent, LimitOrder, SwapEvent
from .v4_math import tick_to_price


def should_fill(order: LimitOrder, swap: SwapEvent) -> bool:
    if order.status != "open":
        return False
    if order.side == "sell0":
        return swap.pre_tick < order.tick <= swap.post_tick
    return swap.post_tick <= order.tick < swap.pre_tick


def fill_order(order: LimitOrder, swap: SwapEvent) -> tuple[LimitOrder, FillEvent]:
    price = tick_to_price(order.tick)
    if order.side == "sell0":
        claimable0 = Decimal("0")
        claimable1 = order.deposited0 * price
        amount_in = order.deposited0
        amount_out = claimable1
    else:
        claimable0 = order.deposited1 / price
        claimable1 = Decimal("0")
        amount_in = order.deposited1
        amount_out = claimable0
    filled = replace(
        order,
        status="filled",
        deposited0=Decimal("0"),
        deposited1=Decimal("0"),
        claimable0=claimable0,
        claimable1=claimable1,
        filled_step=swap.step,
    )
    event = FillEvent(
        event_index=swap.event_index,
        step=swap.step,
        order_id=order.order_id,
        side=order.side,
        tick=order.tick,
        liquidity_filled=order.liquidity,
        amount_in=amount_in,
        amount_out=amount_out,
        claimable0=claimable0,
        claimable1=claimable1,
    )
    return filled, event


def fill_crossed_orders(orders: list[LimitOrder], swap: SwapEvent) -> tuple[list[LimitOrder], list[FillEvent]]:
    next_orders: list[LimitOrder] = []
    fills: list[FillEvent] = []
    for order in orders:
        if should_fill(order, swap):
            filled, event = fill_order(order, swap)
            next_orders.append(filled)
            fills.append(event)
        else:
            next_orders.append(order)
    return next_orders, fills


def cancel_order(order: LimitOrder) -> tuple[Decimal, Decimal]:
    return (
        order.deposited0 + order.claimable0,
        order.deposited1 + order.claimable1,
    )
