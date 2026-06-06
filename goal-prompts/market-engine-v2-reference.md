# Market Engine V2 Reference

This reference carries detailed requirements so `market-engine-v2-goal.md` stays under 4,000 characters.

## Intent

The simulator should test whether an AEGIS vault strategy makes robust delta-neutral liquidity/order-flow profit, not whether it memorized one path. Public practice must remain debuggable and reproducible. Ranked scoring must use hidden, distributional market paths.

## Seed Policy

- Every path is generated from `{engine_version, bundle, seed, calibration_hash}`.
- Public practice seeds are visible and replayable.
- Random practice creates a fresh public seed, stores it in exports, and labels it as practice.
- Hidden ranked seeds are server-side only; public artifacts show a hidden pack id/hash, path count, and aggregate stats, not seeds.
- Ranked path packs should be immutable for a competition round and refreshable between rounds.

## Price Process

Use regime-switching stochastic volatility plus jumps:

- Regimes: calm, volatile, trend_up, trend_down, mean_reversion, jump, low_liquidity, borrow_stress.
- Regime transitions may be Markov or scheduled by seed pack, but must be documented.
- Volatility clusters over time; variance must not be constant Gaussian noise.
- Jumps have configurable intensity, size distribution, and direction.
- Hidden fair price drives arbitrage and flow direction but is never visible to strategies.

## Trade Process

Use clustered flow:

- Cox/Hawkes-style intensity or an equivalent self-exciting process.
- Trade counts are overdispersed versus Poisson.
- Trade-size mixture includes small retail, medium flow, arbitrage, strategy, keeper, and rare whale trades.
- Flow imbalance correlates with regime, hidden fair-price drift, and recent volatility.
- Large trades may be split into child orders; exports may keep child counts instead of one row per child if this is documented and recomputable.

## AMM Endogeneity

The path is not a static tape. Strategy actions must affect:

- Realized pool price and tick path.
- Slippage and price impact.
- CL/LO fills and fee growth.
- DFM fee state and surge windows.
- Arbitrage response.
- Repair/liquidation outcomes.
- Ranked score distribution.

Add hold-idle, passive LP, aggressive swap, and adversarial strategies to prove endogeneity.

## Calibration Metrics

Use comparable Base WETH/USDC data from public sources such as GeckoTerminal, Base RPC/indexed swap logs, Uniswap subgraphs when available, or saved reference files under `reports/base-realism/`.

For a 100-path audit, compute and report:

- Daily volume distribution.
- Trades/day distribution.
- Average and max trade size.
- Realized volatility and volatility clustering.
- Price change distribution.
- Jump frequency and jump size.
- Average and max price impact.
- Active liquidity/depth distribution.
- DFM surge frequency, duration, and fee lift.
- Gas/action cost assumptions.
- Borrow utilization and borrow-rate assumptions.

Default pass targets unless better data justifies alternatives:

- Volume/day, trades/day, realized volatility, average price impact, and DFM surge frequency are within the comparable Base pool P10-P90 range, or within +/-35% of a chosen reference pool with documented rationale.
- Trade-count Fano factor > 1.5 over fixed periods.
- Volume autocorrelation at lag 1 > 0.10.
- At least 5% and at most 45% of paths include a jump regime or jump event.
- No generated path has impossible negative price, zero trade count for a full active day, zero slippage on large trades, free debt, or missing gas/action costs.

## Ranked Scoring Metrics

For every ranked submission, export private full details and public aggregate summaries:

- Path count.
- Mean score and median score.
- P10/worst decile and P90.
- Standard deviation and coefficient of variation.
- Max drawdown.
- Median and worst-decile USD profit.
- Median APR and P10 APR.
- Delta-band time.
- Average and max absolute ETH exposure.
- Repair/liquidation count and cost.
- Disqualification rate.
- Fee/order-flow edge share versus inventory beta share.

Ranking should reward robust neutral fee/order-flow edge. Strategies that win only from ETH beta, lucky paths, hidden-seed leakage, free fills, or missing costs must not rank well.

## Raw Export Requirements

Public exports include:

- Engine version and calibration hash.
- Bundle, public seed, or hidden seed redaction.
- Public replay.
- Market path stats.
- Regime/jump/intensity stats.
- Trades/actions/fills/repairs/debt snapshots.
- DFM surge states and fee lift.
- Ranked aggregate summaries.
- Manifest/checksums.

Private server artifacts may include hidden seeds for audit, but public UI/API/downloads must not.

## Required Tests

- Determinism: same seed and engine version yields identical replay/export hashes across 3 reruns.
- Random practice: 100 generated attempts have no duplicate seed/path.
- Hidden leakage: public artifacts contain no hidden seeds, future fair prices, private paths, or runner state.
- Distribution: 100-path audit meets calibration thresholds.
- Clustered flow: overdispersion and autocorrelation thresholds pass.
- Endogeneity: action-heavy strategy changes realized path/outcome versus hold-idle on same seed pack.
- Ranked aggregation: 20-100 hidden paths run and all robustness metrics are present.
- Export verifier: recomputes all public aggregate metrics from exports where possible.

## Required Playwright Checks

- Random practice button changes the seed/path and updates labels.
- Practice replay/export remains downloadable and auditable.
- Ranked submission shows aggregate robustness metrics.
- Hidden ranked UI does not expose hidden seeds.
- Mobile/desktop layouts do not overflow.
- No console errors.

## Review Artifact

`reports/market-engine-v2-review.md/json` must include:

- Hard gates.
- Calibration source URLs and saved evidence.
- Threshold table.
- Mismatch table.
- Commands run.
- Evidence paths.
- Independent score.
- Readiness status.
- Blockers and non-blocking risks.
