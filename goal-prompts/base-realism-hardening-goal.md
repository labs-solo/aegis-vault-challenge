# Codex Goal Prompt: Base-Realistic AEGIS Math Hardening

Goal: harden `/Users/page/Page/repos/aegis-vault-challenge` until AEGIS vault math, UI numbers, exports, DFM BaseHook fees, delta-neutral LP behavior, and Base ETH/USDC realism are independently verified.

Read first:
`README.md`, `web/index.html`, `aegis_challenge/{runner.py,market.py,aegis_market.py,actions.py,web_app.py,api.py}`, `tests/`, `scripts/`, `docs/`, `goal-prompts/base-realism-hardening-reference.md`
Refs:
`/Users/page/Page/repos/{aegis-engine,aegis-engine-sdk,aegis-research,aegis-app,aegis-arena}`
`/Users/page/Page/repos/aegis-vault-challenge-spec/`

Non-negotiables:
- Canonical accounting must be exact integer/fixed-point/Decimal, not float-driven state.
- AEGIS/CL math must be correct: rL principal, borrow index, liability, LTV, floor, repay, repair/liquidation, equity, CL/LO attachment, ticks, fee growth, hook fees, rounding.
- DFM is the Uniswap v4 BaseHook: it changes CL/LP fee earnings via fee growth and charges hook fees; surges are exported, scored, highlighted.
- AEGIS usage must be realistic for delta-neutral LP: study refs and justify borrow/repay, CL ranges, LOs, swaps, or no swaps by metrics. Liquidity must minimize inventory risk while maximizing net fees.
- Every displayed number maps to the selected replay step/final score and updates during progressive simulation.
- Graph ends on day 180 and never snaps back after completion, refresh, publish, auth, share, or download.
- Raw ZIP enables third-party recomputation without leaking hidden seeds, future info, local paths, credentials, or private runner state.
- Market stats and simulated flow must be realistic versus comparable Base ETH/USDC data.

Implement:
1. Build traceability for every debt, liquidity, fee/surge, price, exposure, APR, score, market-stat, strategy-realism metric, and UI number.
2. Add independent verifier reading only exports; recompute debt, equity, PnL, APR, exposure, fees, slippage, DFM surges, market stats, score.
3. Add golden/property/fuzz tests for debt, CL, LO fills, DFM fees/surge, fee growth, slippage, repairs, scoring, APR, units, UI parity.
4. Add raw ZIP + UI button: replay, score, calibration, actions, trades, fills, repairs, debt snapshots, period stats CSV/JSON, manifest, checksums.
5. Add market/strategy UI: volume, trades, fees, price change, volatility, trade size, slippage, gas/action cost, borrow rate, depth, DFM state/reason, delta-band time, inventory-PnL share, range/hedge efficiency.
6. Fetch/load comparable Base ETH/USDC data; save sources, pool addresses, queries, timestamps, samples, caveats, rationale.
7. Calibrate/fix cadence, volume, volatility clustering, depth, slippage, gas, hook/protocol/LP fees, DFM surges, interest, repairs, MEV, LP/hedge behavior.
8. Add Playwright desktop/laptop/tablet/mobile checks for every-step numbers, day-180 graph, raw download integrity, DFM surge highlight, market stats, no overflow/errors.
9. Write `reports/base-realism-hardening.md/json` with gates, mismatches, formulas, real-data evidence, DFM behavior, screenshots, commands, score, blockers, risks.

Verification:
- Run full pytest.
- Run all Playwright checks.
- Run independent export recomputation on at least one full 180-day run.
- Run adversarial/fuzz suite.
- Run fallback independent review if no separate reviewer is available.

Completion threshold:
All hard gates pass; no unexplained math/display mismatch; Base realism within thresholds; fees, DFM surge, interest, slippage, gas, trade count, depth, volatility, delta neutrality, range efficiency, and hedge efficiency independently verified; review score >=95/100; readiness `world_class_ready`.

Final response:
Report score, hard gates, changed files, test commands, Base data sources, realism thresholds, DFM fee behavior, export format, review paths, screenshots, local URL, and remaining non-blocking risks.
