# Simulation And Scoring

The challenge simulates an AEGIS vault operating in a Uniswap v4-style `ETH/USDC` concentrated-liquidity pool.

## Scenario

- Starting balance: `100,000 USDC`.
- Starting ETH inventory: `0 ETH`.
- Price convention: `USDC per ETH`.
- Default horizon: 180 simulated days.
- Step length: 15 minutes.
- Website pacing: results build progressively over roughly 30-120 seconds.

## Market Path

The V2 market engine is designed to be realistic enough for strategy testing while staying reproducible:

- Practice paths use seeded randomness for auditability.
- Ranked paths should use hidden seeded paths.
- ETH price uses stochastic regimes, volatility changes, and jumps.
- Trade arrivals cluster so volume and activity are not uniform.
- Volume, trade count, price movement, price impact, and DFM surge frequency are calibrated against Base-like WETH/USDC behavior.
- Strategy actions are endogenous: swaps, liquidity, limit orders, fees, fills, slippage, and arbitrage responses affect realized results.

## AEGIS Vault Accounting

The simulator tracks:

- AEGIS L-unit principal rL.
- Borrow index and live debt liability.
- Idle ETH and USDC balances.
- Concentrated-liquidity and limit-order inventory.
- Collateral floor.
- LTV, max LTV, hard LTV, and repair/liquidation behavior.
- Delta and ETH exposure after debt.

Repairs may burn or peel positions, consume idle balances, repay debt, charge keeper-style costs, or force penalties depending on the state.

## DFM BaseHook Fees

DFM fee logic affects:

- Swap costs.
- Hook fees.
- LP/CL fees earned.
- Surge windows.
- Strategy repair cost during expensive fee periods.

The UI highlights fee surge state when it triggers. Strategies can inspect public DFM fields on `state.pool`.

## Scoring

The leaderboard score rewards neutral liquidity/order-flow edge, not ETH beta. Raw equity PnL remains visible, but it is diagnostic.

Main components:

- `edge_profit_usd`: collected/uncollected CL fees plus realized/unrealized LO edge minus borrow, action, repair, liquidation, and invalid-action costs.
- `net_profit_usd_after_penalties`: ranked-score basis after beta/neutrality penalties and gates.
- `apr_pct`: annualized edge score based on elapsed simulated time.
- `profit_usd`: raw equity after debt minus the `100,000 USDC` start.
- `fees_earned_usd`: total concentrated-liquidity fees.
- `collected_cl_fees_usd` and `uncollected_cl_fees_usd`.
- `lo_edge_usd`, `realized_lo_edge_usd`, and `unrealized_lo_edge_usd`.
- `inventory_pnl_usd`: diagnostic inventory/debt mark-to-market contribution.
- `borrow_cost_usd`: AEGIS borrow cost.
- `action_costs`: strategy action costs.
- `repair_cost_usd` and `liquidation_cost_usd`.
- `delta_penalty_usd` and `exposure_penalty_usd`.
- `directional_profit_share`, `edge_profit_share`, `beta_to_eth`, and `mirrored_score_gap_usd`.

Hard neutrality gates cap or disqualify runs when average absolute ETH exposure exceeds `3%` of initial equity, max absolute exposure exceeds `8%`, terminal ETH exposure exceeds `3%` of equity, terminal LTV is above the safe threshold, or terminal directional profit share exceeds `25%`.

## Robustness Metrics

World-class ranked evaluation should report:

- Median profit.
- Worst-decile profit.
- Max drawdown.
- Delta-band time.
- Score variance.
- Forced repairs and liquidations.
- Profit source split: CL fees, LO edge, inventory, borrow cost, action cost, penalties.
- Neutrality gate status, failure reason, beta metrics, and terminal flattening status.

## Raw Data Export

The website exposes `Download raw data` after a run. The export includes:

```text
public_replay.jsonl
score.json
trades.jsonl
actions.jsonl
fills.jsonl
repairs.jsonl
debt_snapshots.jsonl
period_stats.jsonl
period_stats.json
period_stats.csv
manifest.json
checksums
```

Use this export to manually validate the strategy's actions, trade execution, fee accrual, debt accounting, LTV, repairs, and final score.

## Validation Evidence

Relevant reports:

- `reports/market-engine-v2-review.md`
- `reports/base-realism-independent-review.md`
- `reports/base-realism/full-run-verification.json`
- `reports/metrics-v2.md`
- `reports/independent-metrics-review.md`
- `reports/launch-readiness.md`
