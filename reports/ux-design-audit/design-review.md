# Aegis Vault Challenge UX Review

Status: ready_for_participant_testing.

The app now supports the full contestant flow from the website: understand the 180-day USDC/ETH challenge, edit strategy, run a real progressive six-month simulation, inspect USD profit, ETH exposure, replay/risk, submit, and see the leaderboard update. The normal path no longer requires CLI commands, file pickers, or manual JSON artifact loading.

## What Changed

- Restored branded first viewport: official logo, `AEGIS Engine` kicker, and `Aegis Vault Challenge` H1.
- Kept the plain-language value prop: start with 100,000 USDC, trade ETH/USDC, and make USD profit without ETH direction risk.
- Added real web `Run 6-month ETH/USDC simulation`, `Cancel run`, and `Submit run` controls backed by the Python simulator.
- Removed normal-path replay/score/leaderboard file loaders.
- Results now build progressively: day counter, replay, USD profit, ETH exposure, risk, metrics, event tape, and leaderboard.
- Added actionable UI states for invalid Python, unsafe strategy, timeout, and runtime failure.
- Rebuilt metrics as interpreted cards with health bars: USD profit, current equity, continuously updated APR, ETH exposure, delta band, LTV, borrow cost, and fees/order-flow edge.
- Rebuilt replay as long-horizon lanes for ETH/USDC price, USD profit, drawdown, ETH exposure, LTV, repairs, and regime changes.
- Rebuilt leaderboard around net USD profit after penalties, APR, and ETH exposure.
- Closed the late-flatten ETH beta loophole with average/max exposure penalties across the run, not only terminal delta.

## Measured Results

- Happy-path actions after load: 2.
- Default challenge horizon: 180 simulated days.
- Step size: 15 minutes.
- Starting balance: 100,000 USDC.
- Pool: ETH/USDC, displayed as USDC per ETH.
- Progressive six-month run duration: 39,003 ms.
- Progressive visual updates: 39.
- Repeated six-month starter runs: 10/10 completed sequentially, 35,155-37,359 ms each with `pace_seconds:0`.
- Fast smoke flow first run: 1,331 ms.
- Submit after successful run: 40 ms.
- Normal-path CLI commands: 0.
- Normal-path file pickers: 0.
- Normal-path manual artifact loads: 0.
- Console messages/errors: 0.
- Rendered run evidence includes 180-day progress, USD profit, current equity, continuously updated APR, ETH price, ETH exposure, delta band, LTV, debt, fees, sampled event tape, raw replay money fields, and long-horizon chart polylines.
- Progressive evidence: `reports/ux/progressive-metrics.json`, `reports/ux/progressive-metrics.md`.
- Progressive screenshot: `reports/ux/progressive-final.png`.
- Flow evidence: `reports/ux/flow-metrics.json`, `reports/ux/flow-metrics.md`.
- Flow screenshot: `reports/ux/flow-final.png`.

## Verification

- Pytest: 77 passed, including late-flatten directional ETH beta penalty regression.
- Playwright smoke: pass at 1440x1000, 1280x800, 768x1024, 390x844.
- Playwright control pass: navigation, docs link, selects, reset/starter/refresh buttons, score tabs, and replay scrubber respond.
- Playwright accessibility: pass at all target viewports.
- Playwright flow: pass for happy path, submit, 10 repeated runs, invalid Python, unsafe strategy, timeout, runtime failure.
- Playwright progressive: pass for default 180-day ETH/USDC run, 30-120 second progressive build, cancellation/reset, submit gating, money-field replay checks, and 10 repeated six-month jobs.
- Smoke screenshots: `reports/screenshots/desktop-console.png`, `reports/screenshots/laptop-console.png`, `reports/screenshots/tablet-console.png`, `reports/screenshots/mobile-console.png`.
- Accessibility evidence: `reports/ux/accessibility-audit.json`, `reports/ux/accessibility-audit.md`.

## Remaining Risk

The app is ready for participant testing, not proven public-launch perfect. Next validation should use 3-5 representative contestants and verify that each can answer within 60 seconds:

- What do I start with?
- What market am I trading?
- How much USD did I make?
- How much ETH exposure did I carry?
- Why participate?
- What does delta-neutral mean here?
- How do I run and improve a strategy?
- What does the replay tell me?
