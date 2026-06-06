from aegis_challenge.api import BorrowL, PlaceLimitOrder, WithdrawLimitOrder


class Strategy:
    def on_start(self, state):
        self.done = False

    def on_step(self, state):
        actions = [WithdrawLimitOrder(order_id=o.order_id) for o in state.limit_orders if o.status == "filled"]
        if self.done:
            return actions
        spacing = state.pool.tick_spacing
        mid = (state.pool.tick // spacing) * spacing
        self.done = True
        actions.extend([
            BorrowL(amount_l=4_000),
            PlaceLimitOrder(side="sell0", tick=mid + spacing, liquidity=900),
            PlaceLimitOrder(side="sell1", tick=mid - spacing, liquidity=900),
        ])
        return actions
