from aegis_challenge.api import BorrowL, PlaceLimitOrder, WithdrawLimitOrder


class Strategy:
    def on_start(self, state):
        self.bootstrapped = False

    def on_step(self, state):
        actions = [WithdrawLimitOrder(order_id=o.order_id) for o in state.limit_orders if o.status == "filled"]
        if not self.bootstrapped:
            spacing = state.pool.tick_spacing
            actions.append(BorrowL(amount_l=3_000))
            actions.append(PlaceLimitOrder(side="sell0", tick=state.pool.tick + spacing, liquidity=500))
            self.bootstrapped = True
        return actions
