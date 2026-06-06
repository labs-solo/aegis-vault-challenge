# Participant Guide

The AEGIS Vault Challenge is a Python strategy competition. You start with `100,000 USDC`, hold `0 ETH`, and control an AEGIS vault in an `ETH/USDC` pool. Your goal is to make the most net USD profit while keeping ETH exposure near zero.

## The Short Version

1. Open the app.
2. Read the objective and Strategy Academy.
3. Paste one Python `Strategy` class.
4. Run the six-month ETH/USDC simulation.
5. Inspect profit, APR, ETH exposure, LTV, fees, repairs, fills, replay, and raw data.
6. Sign in with X to keep iterating after the anonymous trial.
7. Name saved tries and publish only the try you want on the leaderboard.

## Run The App Locally

```text
python3 -m aegis_challenge.web_server --port 4173
```

Open:

```text
http://127.0.0.1:4173/web/index.html
```

Open the in-app docs:

```text
http://127.0.0.1:4173/web/docs.html
```

## What You Are Optimizing

Leaderboard profit is USD equity above the `100,000 USDC` start after:

- Concentrated-liquidity fees.
- Limit-order edge.
- Inventory mark-to-market.
- Borrow interest.
- Action costs.
- DFM hook fees and swap costs.
- Repairs and liquidation costs.
- Delta/exposure penalties.

APR updates during the run from elapsed simulated days. It is not just a final 180-day calculation.

## What Delta Neutral Means Here

Delta is the sensitivity of vault equity after debt to ETH price. In plain language:

```text
If ETH moves, how much does the vault's USD equity move because of net ETH exposure?
```

Good strategies try to earn from order flow and fee capture while keeping this exposure small. A strategy that only wins because ETH went up or down is not doing the job.

## What Your Strategy Can Do

Your strategy can return action objects from `aegis_challenge.api`:

```text
BorrowL, RepayL, SwapExactIn,
MintRange, IncreaseRange, DecreaseRange, CollectFees, BurnRange,
PlaceLimitOrder, CancelLimitOrder, WithdrawLimitOrder,
DetachPosition
```

Read [Strategy API](strategy-api.md) for details, or use the in-app Strategy Academy for copyable snippets.

## Suggested First Strategy Path

Start simple:

1. Borrow a small amount of AEGIS L-units.
2. Mint a wide ETH/USDC range around the current tick.
3. Collect fees on a cadence.
4. Burn or reduce the range when delta drifts.
5. Repay if LTV approaches the repair band.
6. Add limit orders only after the basic CL strategy stays stable.

## What To Watch In The UI

- `USD profit`: whether you are actually making money after costs.
- `APR`: annualized return based on elapsed simulated time.
- `ETH exposure`: signed value of net ETH delta.
- `Delta band`: whether the strategy is staying neutral enough.
- `LTV used`: how close the vault is to debt trouble.
- `Fees + LO edge`: whether the strategy has a real order-flow edge.
- `Market + DFM`: volume, trades, price move, DFM fee surge, and fee split.
- `Sampled Event Tape`: what your strategy and the market just did.
- `Raw data export`: exact trades, actions, fills, repairs, debt snapshots, period stats, and score files.

## Practice And Ranking

Practice paths are reproducible so you can debug. Ranked scoring should use hidden seeded paths so submissions are judged on robustness, not path memorization.

Robust strategies usually have:

- Positive median profit.
- Tolerable worst-decile results.
- Low drawdown.
- High delta-band time.
- Low score variance.
- Few or no forced repairs.

## Fair-Play Boundary

Strategies may use public `state` and memory on `self`. They may not use hidden fair price, hidden seeds, future flow, private runner state, local files, network calls, unsafe imports, or nondeterministic shortcuts.
