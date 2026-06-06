from decimal import Decimal

from aegis_challenge.api import BorrowL, CollectFees, MintRange, SwapExactIn


class Strategy:
    def on_start(self, state):
        self.bootstrapped = False
        self.last_collect = -10**9

    def on_step(self, state):
        if state.vault.delta_normalized > Decimal("0.03"):
            if state.vault.delta > 0 and state.vault.idle0 > 0:
                amount0 = min(state.vault.idle0 * Decimal("0.90"), state.vault.delta * Decimal("0.90"))
                if amount0 > 0:
                    return [SwapExactIn(token_in="token0", amount_in=amount0, max_slippage_pips=20_000)]
            if state.vault.idle1 > 0:
                amount1 = min(state.vault.idle1 * Decimal("0.90"), abs(state.vault.delta) * state.price * Decimal("0.90"))
                if amount1 > 0:
                    return [SwapExactIn(token_in="token1", amount_in=amount1, max_slippage_pips=20_000)]
        if state.positions and state.step - self.last_collect >= 18:
            self.last_collect = state.step
            return [CollectFees(position_id=state.positions[0].position_id)]
        if self.bootstrapped:
            return []
        spacing = state.pool.tick_spacing
        mid = (state.pool.tick // spacing) * spacing
        self.bootstrapped = True
        return [
            BorrowL(amount_l=18_000),
            MintRange(lower_tick=mid - 22 * spacing, upper_tick=mid + 22 * spacing, liquidity=7_000),
        ]
