# AEGIS Vault Challenge

![Aegis logo](web/assets/aegis-logo.svg)

Programmable infrastructure for Uniswap v4 pools.

AEGIS Vault Challenge is a delta-neutral strategy competition. Contestants paste one Python strategy, control an AEGIS vault in an ETH/USDC pool, and compete on edge-first USD score: concentrated-liquidity fees and limit-order edge after costs, while keeping ETH exposure near zero.

The challenge is designed to teach AEGIS Engine by using it: borrow and repay AEGIS L-units, place concentrated liquidity, use limit orders, react to DFM BaseHook fees, inspect six months of simulated market activity, and publish only the attempts you choose.

## Status

This repository is a local participant-testing build. It includes:

- Python strategy API and sandboxed runner.
- Six-month ETH/USDC simulation with progressive browser results.
- AEGIS debt, LTV, repairs, CL/LO attachment, DFM fee state, scoring, raw data export, saved attempts, and leaderboard flows.
- In-app Strategy Academy at `web/docs.html`.
- CLI/debug runner, examples, tests, UI smoke checks, and launch-readiness reports.

It is not yet a hosted public competition.

## Quickstart

Requirements:

- Python 3.9 or newer.
- Node.js and npm for Playwright UI checks.

Install and run:

```text
python3 -m pip install -e .
npm install
python3 -m aegis_challenge.web_server --port 4173
```

Open:

```text
http://127.0.0.1:4173/web/index.html
```

Learn the strategy API in the app:

```text
http://127.0.0.1:4173/web/docs.html
```

## Contestant Flow

1. Open the website.
2. Read the first screen and Strategy Academy enough to understand the goal.
3. Paste or edit one Python `Strategy` class.
4. Run the 180-day ETH/USDC simulation.
5. Watch APR, edge score, raw USD equity PnL, ETH exposure, LTV, market stats, DFM fees, repairs, fills, and replay data update.
6. Download raw data if you want to audit every strategy action, trade, fill, debt snapshot, and period statistic.
7. Sign in with X to iterate after the anonymous trial.
8. Name saved tries, publish the try you want ranked, and share the result card if you choose.

## Challenge Rules

- Start: `100,000 USDC`, `0 ETH`.
- Pool: `ETH/USDC`, price shown as `USDC per ETH`.
- Horizon: 180 simulated days with 15-minute simulation steps.
- Goal: maximize edge-first USD score from CL fees and LO edge after borrow costs, action costs, repairs, liquidation costs, and neutrality gates.
- Constraint: minimize ETH exposure so leaderboard gains cannot come from ETH beta or unresolved terminal inventory/debt.
- Practice: public seeded paths are reproducible for debugging.
- Ranking: serious submissions should be robust across hidden seeded paths.
- Data boundary: strategies never see hidden fair price, hidden seeds, future flow, private runner state, local files, or external network data.

## Strategy API

Strategies define `class Strategy` with:

```python
class Strategy:
    def on_start(self, state):
        self.bootstrapped = False

    def on_step(self, state):
        return []
```

Available actions:

```text
BorrowL, RepayL, SwapExactIn,
MintRange, IncreaseRange, DecreaseRange, CollectFees, BurnRange,
PlaceLimitOrder, CancelLimitOrder, WithdrawLimitOrder,
DetachPosition
```

Token convention:

```text
token0 = ETH
token1 = USDC
```

Start with:

- [Strategy API](docs/strategy-api.md)
- [Participant Guide](docs/participant-guide.md)
- [In-app Strategy Academy](web/docs.html)
- [Examples](examples/README.md)

## CLI

Run a strategy:

```text
python3 -m aegis_challenge.cli run examples/starter_strategy.py --bundle smoke --seed 1
```

Replay a public artifact:

```text
python3 -m aegis_challenge.cli replay runs/<run_id>/public_replay.jsonl
python3 -m aegis_challenge.cli explain runs/<run_id>/public_replay.jsonl --step 0
```

Submit locally to the training leaderboard:

```text
python3 -m aegis_challenge.cli submit examples/starter_strategy.py
```

Generate readiness metrics:

```text
python3 -m aegis_challenge.cli report
python3 -m aegis_challenge.cli metrics-v2
```

## Raw Simulation Data

After a web run, click `Download raw data` to download a ZIP with:

```text
public_replay.jsonl
score.json
trades.jsonl
actions.jsonl
fills.jsonl
repairs.jsonl
debt_snapshots.jsonl
period_stats.jsonl / period_stats.json / period_stats.csv
manifest.json
checksums
```

Use this to manually validate strategy behavior, math, market stats, fills, and scoring.

## Repository Map

```text
aegis_challenge/api.py              Strategy actions and public state dataclasses
aegis_challenge/runner.py           Strategy execution and replay generation
aegis_challenge/market_engine_v2.py Realistic seeded ETH/USDC market paths
aegis_challenge/pool.py             Uniswap v4-style pool mechanics
aegis_challenge/vault.py            AEGIS vault debt, LTV, repair, and accounting
aegis_challenge/dfm.py              DFM BaseHook dynamic fee logic
aegis_challenge/scoring.py          Profit, APR, penalties, and robustness scoring
aegis_challenge/web_server.py       Local web/API server
web/index.html                      Contestant app
web/docs.html                       In-app Strategy Academy
docs/                               Repository documentation
examples/                           Starter contestant strategies
tests/                              Unit, integration, docs, and golden-vector tests
scripts/                            Playwright and audit scripts
reports/                            Review, validation, screenshots, and metrics artifacts
```

## Documentation

- [Docs Index](docs/README.md)
- [Participant Guide](docs/participant-guide.md)
- [Strategy API](docs/strategy-api.md)
- [Simulation and Scoring](docs/simulation-and-scoring.md)
- [Development Guide](docs/development.md)
- [X Auth, Attempts, Cooldowns, Leaderboard, and Sharing](docs/x-auth-attempts.md)
- [In-app Strategy Academy](web/docs.html)

## Verification

Core tests:

```text
python3 -m pytest -q
```

UI checks:

```text
npm run ui:smoke
npm run ui:a11y
npm run ui:flow
npm run ui:docs-academy
npm run ui:base-realism
npm run ui:market-engine-v2
```

Focused docs checks:

```text
python3 -m pytest tests/test_repo_docs.py tests/test_docs_academy.py -q
```

Recent evidence:

- `reports/docs-academy-review.md`
- `reports/market-engine-v2-review.md`
- `reports/base-realism-independent-review.md`
- `reports/launch-readiness.md`

## Security And Privacy

- Strategy execution is sandboxed and fails closed.
- The UI never asks for X passwords.
- Local development supports mock X auth when real credentials are absent.
- Secrets are environment variables only.
- Public leaderboard rows omit strategy source, local paths, hidden seeds, cookies, tokens, and private runner state.
- Sharing uses X web intent; the app does not silently post.

## Financial Notice

This is a simulation and competition environment. It is not financial advice. Past simulated performance does not predict future results. Smart contracts and market systems can contain bugs or vulnerabilities.
