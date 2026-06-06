# Codex Goal Prompt: Market Engine V2

Goal: improve `/Users/page/Page/repos/aegis-vault-challenge` until practice/ranked simulation uses realistic ETH/USDC path distributions and ranked scoring proves AEGIS delta-neutral strategies robust across hidden seeds.

Read first:
`README.md`
`web/index.html`
`aegis_challenge/{flow.py,runner.py,dfm.py,pool.py,web_app.py,web_server.py,export_verifier.py}`
`tests/`
`scripts/`
`reports/base-realism-hardening.md`
`reports/base-realism-independent-review.md`
`goal-prompts/base-realism-hardening-reference.md`
`goal-prompts/market-engine-v2-reference.md`

References:
`/Users/page/Page/repos/aegis-engine`
`/Users/page/Page/repos/aegis-vault-challenge-spec/`
Base WETH/USDC evidence: `reports/base-realism/`; fetch fresh data if needed.

Non-negotiables:
- Seeded determinism: same bundle + seed + engine version gives identical replay/export hashes.
- Add UI "Random path" with fresh labeled public practice seeds.
- Ranked submissions score over 20-100 hidden paths; target 50.
- Contestants never see hidden seeds, future flow, hidden fair price, or private runner state.
- Fair ETH price uses regime-switching stochastic volatility plus jumps.
- Trades use clustered Cox/Hawkes-style intensity, not smooth fixed flow.
- Calibrate trade count, volume, price impact, volatility, and DFM surge frequency against Base WETH/USDC data.
- AMM execution is endogenous: strategy actions affect pool price, fees, fills, slippage, DFM state, repairs, and arbitrage.
- Preserve AEGIS/Uniswap math, DFM BaseHook fees, exports, sandboxing, and Decimal accounting.

Implement:
1. Add Market Engine V2 with engine version, calibration config/hash, public practice seeds, hidden ranked packs, random practice seeds, regime switching, stochastic vol, jumps, clustered trades, whales, flow imbalance, arbitrage/MEV/latency, and documented gas/fee/depth assumptions.
2. Update ranked scoring to aggregate hidden paths and report mean, median, P10, P90, max drawdown, score variance, delta-band time, repair/liquidation count, disqualification rate, and robustness rank.
3. Update UX so practice vs ranked is obvious, random practice is one click, robustness is readable, and the interface stays simple.
4. Update exports/verifier with V2 path stats, regime/jump/intensity stats, public seed or hidden redaction, calibration hash, per-path ranked summaries, and no hidden leakage.
5. Add tests and Playwright checks listed in `market-engine-v2-reference.md`.

Measurable completion gates:
- Determinism: 3 same-seed reruns produce identical hashes.
- Random practice: 100 attempts produce no seed/path collision.
- Ranked: configured path count is 20-100 and hidden from public artifacts.
- Distribution audit: at least 100 V2 paths meet documented Base calibration bands.
- Clustered flow: volume/trade count overdispersion and autocorrelation pass thresholds.
- Endogeneity: strategy actions change realized path/outcomes versus hold-idle control.
- Robustness: ranked report includes all required aggregate metrics.
- Privacy: hidden seed/future/private-state scan passes.

Independent review:
Run full pytest, relevant Playwright checks, 100-path distribution audit, ranked hidden-pack audit on starter plus adversarial strategies, and export recomputation. Use a separate reviewer/agent if available. Write `reports/market-engine-v2-review.md/json` with gates, metrics, commands, evidence, score, blockers, and risks.

Loop until complete: fix blockers, metric failures, hidden-info leaks, stale docs, confusing UX, or unrealistic calibration. Do not stop at recommendations.

Completion threshold: all gates pass; tests pass; calibration is within bands; ranked hidden scoring works; no hidden leakage; UX is clear; independent score >=95/100; readiness `world_class_ready`.

Final response: report changed files, engine design, ranked scoring behavior, calibration sources, key metrics, commands, review paths, local URL, and non-blocking risks.
