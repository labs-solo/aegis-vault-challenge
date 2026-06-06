# Docs Academy Reference

This file carries detailed requirements so `docs-academy-goal.md` stays under 4,000 characters.

## Product Intent

The docs should feel like a Strategy Academy, not a static manual. A contestant should leave with momentum: "I understand AEGIS vaults, I know what my strategy can do, and I have concrete ideas to improve my score."

The tone should be technical, confident, and direct. Avoid generic DeFi copy. Tie every explanation to the actual challenge: earn USD edge in ETH/USDC while staying delta-neutral.

## Required Information Architecture

- Start Here: challenge objective, 100,000 USDC start, ETH/USDC pool, 180-day simulation, 30-120s replay, public practice paths, hidden ranked paths.
- AEGIS Engine Primer: vaults, L-units/rL debt, borrow index, collateral floor, LTV, repairs, CL/LO attachment, DFM BaseHook fees.
- Strategy Lifecycle: `on_start`, `on_step`, action list, action limit, sandbox limits, deterministic replay, public state only.
- Strategy Actions: full API reference grouped by Borrow, Liquidity, Limit Orders, Rebalance, Advanced.
- Public State Guide: what can be read from `state`, what each field means, and what decisions it supports.
- Hidden Info Rules: no hidden fair price, hidden seeds, future flow, private runner state, or external data.
- Scoring Guide: USD profit, APR, fees, LO edge, borrow costs, action costs, repairs, delta/exposure penalties, ranked robustness.
- Recipes: practical examples and upgrade paths.
- Debugging: common errors, rejected actions, LTV failures, tick alignment, insufficient idle balances, timeouts, sandbox errors.

## Action Reference Requirements

For each action include:

- What it does.
- Constructor fields.
- Token meaning: `token0` = ETH, `token1` = USDC.
- When to use it.
- Example snippet.
- Risk/common errors.
- Related public state fields to inspect first.

Actions that must be documented:

- `BorrowL(amount_l)`
- `RepayL(amount_l | "all")`
- `SwapExactIn(token_in, amount_in, max_slippage_pips)`
- `MintRange(lower_tick, upper_tick, liquidity)`
- `IncreaseRange(position_id, liquidity)`
- `DecreaseRange(position_id, liquidity)`
- `CollectFees(position_id)`
- `BurnRange(position_id)`
- `PlaceLimitOrder(side, tick, liquidity)`
- `CancelLimitOrder(order_id)`
- `WithdrawLimitOrder(order_id)`
- `DetachPosition(kind, id)`

## Public State Coverage

Explain these groups:

- Time/path: `step`, `timestamp`, `config.scenario_steps`, `config.step_length_seconds`, `config.scenario_name`.
- Price/tick: `price`, `eth_price`, `tick`, `twap`, `pool.tick_spacing`, initialized ticks.
- Pool/DFM: fee pips, DFM surge state/reason/window, active liquidity, hook fees.
- Vault: `idle0`, `idle1`, `debt_l`, `borrow_index`, debt liability, `ltv_pips`, `max_ltv_pips`, `hard_ltv_pips`, `collateral_floor_l`.
- Delta/money: `delta`, `delta_normalized`, `net_eth_delta`, `eth_exposure_usd`, `cash_usdc`, `eth_inventory`, `equity_usd`, `profit_usd`, `apr_pct`.
- Positions/orders: `positions`, `limit_orders`, uncollected fees, fill status.
- Recent events: `recent_swaps`, `recent_fills`, `recent_repairs`.
- Score: `score_so_far`, `score_breakdown`, fees, LO edge, borrow cost, repair cost, penalties.

## Recipe Requirements

Each recipe should include a short explanation, code snippet, when it works, when it fails, and how to improve it.

Required recipes:

- Starter delta-neutral vault.
- Passive wide LP.
- Narrow fee-capture LP.
- Limit-order rebalancer.
- Delta repair bot.
- DFM surge harvester.
- Robustness-first ranked strategy.

## UX Requirements

- Main app nav must include a clear Docs/Academy entry.
- Strategy editor should have a nearby "What can my strategy do?" affordance.
- Docs should use tabs, accordions, search/filter, or a concise sidebar.
- Include copy buttons; insert-snippet buttons are strongly preferred if they do not complicate UX.
- Mobile docs must be readable and not overflow.
- No walls of text before the contestant understands the objective.
- Brand should use AEGIS logo/colors and feel credible, calm, and technical.

## Verification Requirements

Automated tests should prove:

- Every action class in `api.py` appears in docs.
- Every required state group appears in docs.
- Snippets compile or pass sandbox validation.
- Docs links are valid.
- Hidden/future/private data is not promised.
- Playwright can open docs on desktop and mobile, navigate action reference, find objective, find hidden-info rules, and copy or insert a snippet if implemented.

Independent review should score:

- First-time clarity.
- AEGIS Engine explanation.
- Action/API completeness.
- Strategy usefulness.
- Hidden-info accuracy.
- Scoring/robustness clarity.
- Visual polish/brand fidelity.
- Mobile/accessibility.
- Overall readiness.
