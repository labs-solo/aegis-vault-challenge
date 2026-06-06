# Base Realism Hardening Reference

This reference carries detailed requirements so the Codex goal prompt can stay under 4,000 characters.

## Core Question

Would a strategy that wins in the simulator plausibly work on Base in a similar ETH/USDC Uniswap v4 hooked pool using AEGIS Engine vaults? The answer must be backed by raw data, independent recomputation, UI parity checks, and real comparable Base pool calibration.

## AEGIS And Uniswap Math Gates

- AEGIS debt math: rL principal, borrow index, debt liability, LTV, collateral floor, repay, repair/liquidation, idle balances, equity after debt.
- Uniswap v4 CL math: ticks, sqrt price, liquidity deltas, rounding, tick crossing, fee growth, LP fee accrual, same-swap limit-order fills.
- Exact accounting: canonical math uses integer/fixed-point/Decimal; floats may only be display/convenience values with bounded tests.
- Ordering proof: market trades, strategy actions, DFM hook fee updates, fills, debt accrual, repairs, and scoring must be ordered and documented.

## DFM BaseHook Requirement

The AEGIS Engine pool must model the Dynamic Fee Manager as the pool BaseHook. It is not a cosmetic label.

DFM must affect concentrated-liquidity economics in two distinct ways:

- The DFM-selected LP/pool swap fee is applied to Uniswap v4 swap math before execution, so it changes fee growth and therefore fees earned by in-range CL and same-swap limit-order liquidity.
- Any separate hook fee is charged and exported separately; it must not be misclassified as contestant CL revenue.
- Exports and UI must split actual CL fees into base-rate LP fees and DFM LP fee lift so validators can see surge-driven CL upside.

Minimum exported fields per step/period:

- `dfm_base_fee_bps`
- `dfm_hook_fee_bps`
- `dfm_total_fee_bps`
- `dfm_fee_multiplier`
- `dfm_surge_triggered`
- `dfm_surge_reason`
- `dfm_surge_start_step`
- `dfm_surge_end_step`
- `lp_fee_paid`
- `base_lp_fee_paid` or `base_lp_fee_usd`
- `dfm_lp_fee_lift_paid` or `dfm_lp_fee_lift_usd`
- `hook_fee_paid`
- `protocol_fee_paid`

Surge triggers must be measurable and documented, such as volatility jump, tick crossing density, trade-size outlier, liquidity-depth shock, or order-flow imbalance. If AEGIS reference code exposes exact DFM rules, match those rules; otherwise document the approximation and mark any uncertainty as a launch risk.

UI must highlight fee surge when it triggers:

- Badge/pill changes from normal DFM fee to `DFM fee surge`.
- Fee metric, waterfall, market stats, and replay chart show the surge period.
- Selected-period market stats include surge reason, total fee bps, hook fees, and LP fee effect.
- Playwright must prove the highlight appears on a seeded surge scenario and disappears outside surge periods.

## AEGIS Delta-Neutral LP Strategy Realism

The challenge must model realistic AEGIS Engine usage for delta-neutral liquidity provision, not merely allow arbitrary profitable actions. Agents executing the goal must study the local AEGIS references and determine the best supported vault mechanics for the simulator. A valid implementation may use borrow/repay, CL range placement, limit orders, swaps, or no swaps, but the final behavior must be justified by metrics.

Evaluate at least these strategy mechanics:

- CL range placement around the active ETH/USDC price using volatility, volume, DFM fee state, liquidity depth, and expected fee density.
- Range width/recenter cadence that balances fee capture against inventory risk, gas/action costs, and repair risk.
- Borrow/repay usage to neutralize ETH exposure through AEGIS L-unit debt without creating unrealistic free leverage.
- Limit orders for order-flow capture and inventory rebalancing only when fills are realistic and same-step ordering is correct.
- Swaps only when they are strategically justified by lower inventory risk or better neutrality after slippage, DFM hook fees, LP/protocol fees, and gas.
- Exit/repair logic during fee surge, low liquidity, volatility jumps, and LTV stress.

Minimum metrics:

- Average and max absolute ETH exposure in USD.
- Time inside delta-safe band.
- Fee revenue per unit of average liquidity and per unit of inventory risk.
- Net USD PnL after borrow, DFM/hook, LP/protocol, gas/action, repair, and slippage costs.
- Inventory PnL share of total PnL, proving the strategy is not winning from ETH beta.
- Active liquidity utilization: percent of time range is in range and earning.
- Range efficiency: fees earned versus comparable passive wide/narrow baselines.
- Hedge efficiency: delta reduction per dollar of borrow/swap/LO cost.
- Repair/liquidation count and cost.
- Turnover/action frequency versus realistic Base costs.

Completion requires quantitative thresholds in the report. A strategy/simulator is not ready if profitability depends on impossible fills, zero slippage, missing gas, free debt, no DFM hook fee, stale ranges that earn unrealistic fees, or directional ETH inventory beta.

## Market Realism Gates

Use real comparable Base ETH/USDC pool data from reliable public sources/APIs/subgraphs. Save source URLs, pool addresses, query parameters, timestamps, raw samples, and caveats.

Compare simulated vs real by computed period and full run:

- Volume
- Trade count
- Trade-size distribution
- Price change
- Realized volatility and volatility clustering
- Active liquidity depth and tick crossing frequency
- LP fee revenue and fee APR
- DFM hook/protocol fees
- Average and max slippage/price impact
- Gas/action costs
- Borrow/interest rates
- Repair/keeper costs
- MEV/arbitrage pressure

Hard blockers:

- Periods with implausibly low/zero trade count unless real reference supports it.
- Free or impossible fills.
- Missing gas/action costs.
- Unrealistically cheap debt.
- No slippage or price impact for large trades.
- Smooth price path or volume path that would not resemble Base.
- Missing or cosmetic DFM BaseHook fee behavior.

## Raw Export And Independent Recompute

Raw download must include enough data for third-party recomputation:

- `public_replay.jsonl`
- `score.json`
- `calibration.json`
- `actions.jsonl`
- `trades.jsonl`
- `fills.jsonl`
- `repairs.jsonl`
- `debt_snapshots.jsonl`
- `period_stats.json`
- `period_stats.csv`
- `manifest.json`
- checksums

Verifier must read only exports and recompute debt, equity, PnL, APR, exposure, fees, slippage, DFM surge periods, market stats, and final score. Any unexplained mismatch is a blocker.

Verifier must also prove `base_lp_fees_usd + dfm_lp_fee_lift_usd == lp_fees_usd` and fail if a DFM surge period earns CL fees without positive DFM LP fee lift.

## UI Number Parity

Every displayed number must map to the selected replay step or final score:

- Metrics cards
- Risk panel
- Score waterfall
- Market stats
- Replay chart labels
- Leaderboard/share values
- Raw export manifest

Playwright must verify progressive updates at multiple steps and final day 180. Graph/scrubber must end at day 180 and never snap back after completion, refresh, publish, auth, share modal, or download.

## Completion Evidence

Write:

- `reports/base-realism-hardening.md`
- `reports/base-realism-hardening.json`

Reports must include hard gates, threshold table, mismatch table, formulas, real-data evidence, DFM BaseHook behavior, screenshots, commands, score, blockers, and residual risks.
