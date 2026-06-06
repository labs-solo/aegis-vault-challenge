from aegis_challenge.api import BorrowL, MintRange


class Strategy:
    def on_start(self, state):
        self.done = False

    def on_step(self, state):
        if self.done:
            return []
        spacing = state.pool.tick_spacing
        mid = (state.pool.tick // spacing) * spacing
        self.done = True
        return [
            BorrowL(amount_l=20_000),
            MintRange(lower_tick=mid - 8 * spacing, upper_tick=mid + 8 * spacing, liquidity=8_000),
        ]
