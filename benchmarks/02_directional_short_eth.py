from decimal import Decimal

from aegis_challenge.api import BorrowL, SwapExactIn


class Strategy:
    def on_start(self, state):
        self.done = False

    def on_step(self, state):
        if self.done:
            return []
        self.done = True
        return [
            BorrowL(amount_l=2_000),
            SwapExactIn(token_in="token0", amount_in=Decimal("25"), max_slippage_pips=20_000),
        ]
