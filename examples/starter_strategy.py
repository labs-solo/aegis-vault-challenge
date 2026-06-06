"""Starter strategy for the Aegis Vault Challenge.

Contestants start with 100,000 USDC and 0 ETH in an ETH/USDC pool.
This starter borrows AEGIS L-units, places a small ETH/USDC range, collects
fees, then exits early so the six-month run finishes inside the hardened
neutrality gates. It is deliberately conservative: the goal is to demonstrate
clean CL edge and safe AEGIS debt handling, not to maximize profit.
"""

from decimal import Decimal

from aegis_challenge.api import BorrowL, BurnRange, CollectFees, MintRange, RepayL, SwapExactIn, WithdrawLimitOrder


class Strategy:
    def on_start(self, state):
        self.bootstrapped = False
        self.borrow_l = 1_000
        self.range_liquidity = 400
        self.range_half_width_steps = 28
        self.delta_repair_threshold = Decimal("0.020")
        self.ltv_repair_threshold_pips = 970_000
        self.collect_every_steps = 24
        self.last_collect_step = -10**9
        self.exit_step = 12
        self.exited = False

    def on_step(self, state):
        actions = []
        if state.step >= self.exit_step and not self.exited:
            for position in state.positions:
                actions.append(BurnRange(position_id=position.position_id))
            for order in state.limit_orders:
                if order.status == "filled":
                    actions.append(WithdrawLimitOrder(order_id=order.order_id))
            if state.vault.debt_l > 0:
                actions.append(RepayL(amount_l="all"))
            if actions:
                self.exited = True
                return actions
        if self.exited:
            return []
        # Public state uses money-first fields:
        # state.config.pool_pair == "ETH/USDC"
        # state.config.initial_balance_usdc == Decimal("100000")
        # state.eth_price is USDC per ETH
        # state.profit_usd is edge-first score after penalties so far
        # state.score_breakdown.raw_pnl is raw equity PnL for diagnosis
        # state.eth_exposure_usd is signed ETH exposure marked in USD
        for order in state.limit_orders:
            if order.status == "filled":
                actions.append(WithdrawLimitOrder(order_id=order.order_id))
        if state.vault.ltv_pips > self.ltv_repair_threshold_pips:
            if state.positions:
                actions.append(BurnRange(position_id=state.positions[0].position_id))
            actions.append(RepayL(amount_l="all"))
            return actions
        if state.vault.delta_normalized > self.delta_repair_threshold:
            actions.extend(self._delta_repair_actions(state))
            if actions:
                return actions
        if state.positions and state.step - self.last_collect_step >= self.collect_every_steps:
            actions.append(CollectFees(position_id=state.positions[0].position_id))
            self.last_collect_step = state.step
            return actions
        if not self.bootstrapped and not state.positions:
            lower, upper = self._range_around_current_tick(state)
            actions.append(BorrowL(amount_l=self.borrow_l))
            actions.append(MintRange(lower_tick=lower, upper_tick=upper, liquidity=self.range_liquidity))
            self.bootstrapped = True
        return actions

    def _range_around_current_tick(self, state):
        spacing = state.pool.tick_spacing
        mid = (state.pool.tick // spacing) * spacing
        width = self.range_half_width_steps * spacing
        return mid - width, mid + width

    def _delta_repair_actions(self, state):
        if state.vault.delta > 0 and state.vault.idle0 > 0:
            amount0 = min(state.vault.idle0 * Decimal("0.90"), state.vault.delta * Decimal("0.90"))
            if amount0 > 0:
                return [SwapExactIn(token_in="token0", amount_in=amount0, max_slippage_pips=20_000)]
        if state.vault.idle1 > 0:
            amount1 = min(state.vault.idle1 * Decimal("0.90"), abs(state.vault.delta) * state.price * Decimal("0.90"))
            if amount1 > 0:
                return [SwapExactIn(token_in="token1", amount_in=amount1, max_slippage_pips=20_000)]
        return []
