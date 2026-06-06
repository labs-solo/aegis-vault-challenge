from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .aegis_market import debt_repayment_liability
from .api import ClPosition, LimitOrder, VaultState
from .v4_math import amount_delta_for_range_scaled

WAD = 10**18
MAX_LTV_PIPS = 993_000
HARD_LTV_PIPS = 996_000


@dataclass
class Vault:
    idle0: Decimal = Decimal("0")
    idle1: Decimal = Decimal("100000")
    debt_l: int = 0
    borrow_index: int = WAD
    positions: list[ClPosition] = field(default_factory=list)
    limit_orders: list[LimitOrder] = field(default_factory=list)
    next_position_id: int = 1
    next_order_id: int = 1

    def collateral_floor_l(self, price: Decimal = Decimal("1"), amount_scale: int = 1) -> int:
        floor = (self.idle0 * self.idle1).sqrt() if self.idle0 > 0 and self.idle1 > 0 else Decimal("0")
        for pos in self.positions:
            amount0, amount1 = self.position_amounts(pos, price, amount_scale)
            floor += (amount0 * amount1).sqrt() if amount0 > 0 and amount1 > 0 else Decimal("0")
        for order in self.limit_orders:
            floor += (order.deposited0 * order.deposited1).sqrt() if order.deposited0 > 0 and order.deposited1 > 0 else Decimal("0")
        return int(floor)

    def equity(self, price: Decimal, amount_scale: int = 1) -> Decimal:
        value = self.idle0 * price + self.idle1
        for pos in self.positions:
            amount0, amount1 = self.position_amounts(pos, price, amount_scale)
            value += amount0 * price + amount1 + pos.uncollected_fees0 * price + pos.uncollected_fees1
        for order in self.limit_orders:
            value += order.deposited0 * price + order.deposited1 + order.claimable0 * price + order.claimable1
        return value - self.debt_value(price, amount_scale)

    def debt_value(self, price: Decimal, amount_scale: int = 1) -> Decimal:
        return debt_repayment_liability(self.debt_l, self.borrow_index, price, amount_scale=amount_scale)["value"]  # type: ignore[index,return-value]

    def ltv_pips(self, price: Decimal = Decimal("1"), amount_scale: int = 1) -> int:
        floor = self.collateral_floor_l(price, amount_scale)
        if self.debt_l == 0:
            return 0
        if floor == 0:
            return 1_000_000
        return min(1_000_000, int((Decimal(self.debt_l * self.borrow_index) / Decimal(WAD)) * Decimal(1_000_000) / Decimal(floor)))

    def delta(self, price: Decimal, amount_scale: int = 1) -> Decimal:
        eps = max(price * Decimal("0.0001"), Decimal("0.000001"))
        up = self.equity(price + eps, amount_scale)
        down = self.equity(max(price - eps, Decimal("0.000001")), amount_scale)
        return (up - down) / (eps * 2)

    def state(self, price: Decimal, amount_scale: int = 1) -> VaultState:
        equity = self.equity(price, amount_scale)
        delta = self.delta(price, amount_scale)
        delta_norm = abs(delta) * price / max(equity, Decimal("0.000000001"))
        liability = debt_repayment_liability(self.debt_l, self.borrow_index, price, amount_scale=amount_scale)
        debt_value = liability["value"]
        return VaultState(
            idle0=self.idle0,
            idle1=self.idle1,
            debt_l=self.debt_l,
            borrow_index=self.borrow_index,
            debt_liability0=liability["liability0"],
            debt_liability1=liability["liability1"],
            debt_liability_value=debt_value,  # type: ignore[arg-type]
            ltv_pips=self.ltv_pips(price, amount_scale),
            max_ltv_pips=MAX_LTV_PIPS,
            hard_ltv_pips=HARD_LTV_PIPS,
            delta=delta,
            delta_normalized=delta_norm,
            equity=equity,
            collateral_floor_l=self.collateral_floor_l(price, amount_scale),
            unlocked=False,
            cash_usdc=self.idle1,
            eth_inventory=self.idle0,
            equity_usd=equity,
            net_eth_delta=delta,
            eth_exposure_usd=delta * price,
        )

    def position_amounts(self, pos: ClPosition, price: Decimal, amount_scale: int = 1) -> tuple[Decimal, Decimal]:
        return amount_delta_for_range_scaled(pos.liquidity, price, pos.lower_tick, pos.upper_tick, amount_scale)

    def accrue_interest(self, seconds: int) -> Decimal:
        if self.debt_l == 0:
            return Decimal("0")
        old = self.borrow_index
        self.borrow_index += self.borrow_index * seconds * 1_000_000 // WAD
        return Decimal(self.debt_l * (self.borrow_index - old)) / Decimal(WAD)
