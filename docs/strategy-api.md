# Strategy API

Contestants submit one Python strategy file. The runner imports `class Strategy`, calls `on_start(state)` once, then calls `on_step(state)` throughout the simulation. `on_step` returns a list of action objects.

```python
class Strategy:
    def on_start(self, state):
        self.bootstrapped = False

    def on_step(self, state):
        return []
```

Token convention:

```text
token0 = ETH
token1 = USDC
price = USDC per ETH
```

## Actions

Import actions from `aegis_challenge.api`.

### Borrow And Repair

- `BorrowL(amount_l)`: borrow AEGIS L-unit principal rL. Use before placing CL/LO inventory. Watch LTV, collateral floor, debt liability, and borrow cost.
- `RepayL(amount_l | "all")`: repay AEGIS L-unit debt. Use when LTV is high, borrow cost dominates, or you are exiting inventory.
- `SwapExactIn(token_in, amount_in, max_slippage_pips=5000)`: swap vault inventory through the pool. Use for delta repair or repayment inventory. Watch DFM fee state, slippage, idle balances, and active liquidity.

### Concentrated Liquidity

- `MintRange(lower_tick, upper_tick, liquidity)`: create a CL position. Ticks must align to `state.pool.tick_spacing`.
- `IncreaseRange(position_id, liquidity)`: add liquidity to an existing CL position.
- `DecreaseRange(position_id, liquidity)`: remove part of a CL position.
- `CollectFees(position_id)`: move uncollected CL fees into idle vault balances.
- `BurnRange(position_id)`: remove a CL position and return current inventory to the vault.

### Limit Orders

- `PlaceLimitOrder(side, tick, liquidity)`: place a single-sided order. `side="sell0"` sells ETH; `side="sell1"` sells USDC.
- `CancelLimitOrder(order_id)`: cancel an open order.
- `WithdrawLimitOrder(order_id)`: withdraw proceeds from a filled order.

### Advanced

- `DetachPosition(kind, id)`: detach a `CL` or `LO` object when the vault state permits advanced cleanup.

The in-app Strategy Academy at `web/docs.html#actions` has purpose, fields, when-to-use guidance, risks, common errors, and copyable snippets for every action.

## Public State

Strategies can inspect public `state` fields only.

### Time And Path

```text
state.step
state.timestamp
state.config.scenario_steps
state.config.step_length_seconds
state.config.scenario_name
state.config.public_run_id
```

### Price And Tick

```text
state.price
state.eth_price
state.tick
state.twap
state.pool.tick
state.pool.tick_spacing
state.pool.initialized_ticks
```

### Pool And DFM Fees

```text
state.pool.active_liquidity
state.pool.fee_pips
state.pool.lp_fee_pips
state.pool.protocol_fee_pips
state.pool.pool_swap_fee_pips
state.pool.dynamic_fee_active
state.pool.fee_surge_active
state.pool.dfm_base_fee_pips
state.pool.dfm_lp_fee_pips
state.pool.dfm_surge_fee_pips
state.pool.dfm_surge_reason
state.pool.dfm_surge_start_step
state.pool.dfm_surge_end_step
state.pool.pending_hook_fees0
state.pool.pending_hook_fees1
```

DFM BaseHook fee logic affects swap costs and concentrated-liquidity fees earned.

### Vault Debt And Balances

```text
state.vault.idle0
state.vault.idle1
state.vault.debt_l
state.vault.borrow_index
state.vault.debt_liability0
state.vault.debt_liability1
state.vault.debt_liability_value
state.vault.ltv_pips
state.vault.max_ltv_pips
state.vault.hard_ltv_pips
state.vault.collateral_floor_l
state.vault.cash_usdc
state.vault.eth_inventory
```

### Delta And Money

```text
state.vault.delta
state.vault.delta_normalized
state.net_eth_delta
state.eth_exposure_usd
state.cash_usdc
state.eth_inventory
state.equity_usd
state.profit_usd
state.apr_pct
state.borrow_cost_usd
state.fees_earned_usd
```

### Positions, Orders, And Events

```text
state.positions
state.limit_orders
state.recent_swaps
state.recent_fills
state.recent_repairs
```

### Score

```text
state.score_so_far
state.score_breakdown.raw_pnl
state.score_breakdown.cl_fee_pnl
state.score_breakdown.lo_edge_pnl
state.score_breakdown.inventory_mark_pnl
state.score_breakdown.borrow_interest_attribution
state.score_breakdown.action_costs
state.score_breakdown.delta_penalty
state.score_breakdown.liquidation_penalty
state.score_breakdown.net_profit_usd_after_penalties
```

## Sandbox And Hidden Information

Allowed:

- Public `state`.
- Memory on `self`.
- Deterministic Python logic.
- Decimal arithmetic.

Not allowed:

- Hidden fair price.
- Hidden seeds.
- Future flow or future trades.
- Private runner state.
- Local filesystem reads.
- Network calls.
- Unsafe imports.
- Nondeterministic replay behavior.

Invalid actions, forbidden side effects, resource-limit violations, timeouts, and strategy exceptions fail closed with penalties or disqualification.
