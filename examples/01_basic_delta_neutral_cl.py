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
            BorrowL(amount_l=10_000),
            MintRange(lower_tick=mid - 12 * spacing, upper_tick=mid + 12 * spacing, liquidity=3_000),
        ]
