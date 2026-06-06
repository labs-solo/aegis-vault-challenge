from decimal import Decimal

from aegis_challenge.api import SwapExactIn


class Strategy:
    def on_start(self, state):
        self.done = False

    def on_step(self, state):
        if self.done or state.vault.idle1 <= 0:
            return []
        self.done = True
        return [SwapExactIn(token_in="token1", amount_in=state.vault.idle1 * Decimal("0.80"), max_slippage_pips=20_000)]
