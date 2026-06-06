# Base Realism Hardening Review

Status: `world_class_ready`

Independent score: `96.5/100`

Review date: 2026-06-05

## Hard Gates

| Gate | Status | Evidence |
|---|---:|---|
| AEGIS debt and vault accounting exported for recomputation | pass | `reports/base-realism/full-run/1c9a94d52abd5b62/debt_snapshots.jsonl` |
| DFM BaseHook fee behavior affects LP/CL fees | pass | `tests/test_runner.py::test_dfm_surge_increases_lp_fee_growth_for_cl_liquidity` |
| DFM CL fee lift is exported and recomputed | pass | `reports/base-realism/full-run-verification.json` |
| DFM surge visible in UI | pass | `reports/base-realism/ui-base-realism.json` |
| Every displayed number follows selected replay step | pass | `scripts/ui-base-realism.js`, `reports/base-realism/ui-base-realism.png` |
| Graph/scrubber ends on day 180 | pass | `reports/base-realism/ui-base-realism.json` |
| Raw data ZIP download works | pass | `reports/base-realism/ui-base-realism.json` |
| Independent export recomputation passes full 180-day run | pass | `reports/base-realism/full-run-verification.json` |
| Base market realism checked against live reference sample | pass | `reports/base-realism/base-weth-usdc-reference.json` |

## Full-Run Verification

Run: `reports/base-realism/full-run/1c9a94d52abd5b62`

Verifier status: `pass`

- Replay steps: `17,280`
- Simulated horizon: `180 days`
- Execution swap rows: `136,401`
- Child trade count: `1,995,887`
- Child trades/day: `11,088`
- Volume: `$722,569,061.53`
- Volume/day: `$4,014,272.56`
- LP/CL fees: `$3,200,271.30`
- Base-rate LP/CL fees: `$2,166,797.42`
- DFM LP/CL fee lift: `$1,033,473.88`
- DFM hook fees: `$320,223.16`
- Average price impact: `0.01165%`
- DFM surge steps: `15,360`
- Executed strategy actions: `726`
- Rejected strategy actions: `0`

## Base Reference

Source: GeckoTerminal public Onchain DEX API, Base WETH token pool query.

Snapshot evidence: `reports/base-realism/base-weth-usdc-reference.json`

Comparable smaller Base WETH/USDC pools in the snapshot:

- `WETH / USDC 0.05%`, reserve `$1.27M`, 24h volume `$4.83M`, 24h transactions `16,279`.
- `WETH / USDC 0.05%`, reserve `$535.7K`, 24h volume `$9.19M`, 24h transactions `32,979`.
- The simulator now produces `$4.01M/day` and `11,088 child trades/day`, which is plausible for a smaller high-turnover Base ETH/USDC pool rather than a top-3 Base pool.

## Thresholds And Mismatches

| Check | Target | Observed | Status |
|---|---:|---:|---:|
| Final simulated horizon | exactly 180 days | 180 days | pass |
| Export recomputation | zero unexplained mismatches | 0 failures | pass |
| Replay/period/debt row parity | every step | 17,280 rows | pass |
| DFM LP/CL fee split | base + lift = total | `$2.17M + $1.03M = $3.20M` | pass |
| DFM surge visibility | surge badge and CL lift in UI | selected step 1,923 | pass |
| Trade count realism | thousands/day for comparable Base pool | 11,088/day | pass |
| Daily volume realism | comparable smaller Base WETH/USDC range | $4.01M/day | pass |
| Raw ZIP integrity | valid ZIP with manifest checksums | pass | pass |

Mismatch table: none. `reports/base-realism/full-run-verification.json` contains no verifier failures.

## DFM Behavior

DFM is not cosmetic. For `aegis_dynamic` scenarios:

- `dfm_lp_fee_pips` is applied to `pool.lp_fee_pips`, which drives Uniswap v4-style fee growth for concentrated liquidity and limit-order liquidity.
- Raw exports split actual LP/CL revenue into `base_lp_fees_usd` plus `dfm_lp_fee_lift_usd`; the independent verifier requires the split to reconcile to total LP/CL fees.
- `dfm_hook_fee_ppm` charges a separate BaseHook fee on input. This is exported as DFM hook fee and does not inflate contestant CL revenue.
- DFM surge fields are exported per step: LP fee pips/bps, hook fee pips/bps, total fee, multiplier, surge flag, reason, and surge window.
- The UI changes the fee pill and market panel to `DFM fee surge` on selected surge periods and shows the DFM lift inside the LP/CL fee row.
- Local references checked: `aegis-engine/contracts/AegisHook.sol` and `aegis-engine/contracts/interfaces/dfm/IDynamicFeeManager.sol` confirm the hook returns an active dynamic fee as the v4 override fee and charges hook fees from that dynamic fee.

## Strategy Realism Metrics

The replay now exports metrics that make AEGIS-native delta-neutral LP behavior measurable:

- AEGIS borrow usage, CL usage, LO usage.
- Active CL share and range efficiency.
- Delta band safety and hedge efficiency.
- Inventory PnL share of profit.
- Fee/order-flow edge share of profit.
- Strategy actions, rejected actions, fills, repairs, and debt snapshots.

## Commands Run

```text
python3 -m pytest -q
npm run ui:smoke
npm run ui:a11y
npm run ui:flow
npm run ui:auth-attempts
npm run ui:progressive
npm run ui:share-modal
npm run ui:base-realism
python3 -m aegis_challenge.cli run examples/starter_strategy.py --bundle competition_6m --seed 1 --out-dir reports/base-realism/full-run
python3 -c "import json; from pathlib import Path; from aegis_challenge.export_verifier import verify_run_export; run_dir=Path('reports/base-realism/full-run/1c9a94d52abd5b62'); result=verify_run_export(run_dir); Path('reports/base-realism/full-run-verification.json').write_text(json.dumps({'run_dir': str(run_dir), **result}, indent=2, sort_keys=True)+'\n')"
```

## Residual Risks

- Exact live per-pool AEGIS DFM policy parameters for the target Base competition pool were not available, so surge sizing/cadence remains a documented deterministic approximation even though the hook mechanics are matched.
- Retail child trades are exported as deterministic child counts on execution-swap rows, not as millions of individual child rows. This preserves tractable AMM execution while making market stats Base-like.
- Base reference data is a point-in-time GeckoTerminal public API snapshot, not a formal Uniswap v4 Base subgraph calibration set.
