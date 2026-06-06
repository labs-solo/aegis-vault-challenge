# Base Realism Independent Review

Review date: 2026-06-05

Hard-gate status: `pass`

Readiness: `world_class_ready`

Independent score: `95/100`

## Verdict

The current Base-realistic AEGIS math hardening is world-class ready for the stated challenge scope. The key clarification is verified: DFM does affect concentrated-liquidity LP fee growth through the pool swap fee path, not merely through separate hook fees. Hook fees remain separately modeled and exported.

There are no blocking issues. The main residual risk is calibration, not mechanics: exact live per-pool AEGIS DFM policy parameters were not available in the reviewed materials, so surge magnitude/cadence remains a deterministic approximation of the live policy.

## Hard Gates

| Gate | Status | Evidence |
|---|---:|---|
| 1. DFM active fee changes pool LP/CL fee growth, not only separate hook fees | pass | `aegis_challenge/dfm.py:24`, `aegis_challenge/pool.py:121`, `aegis_challenge/pool.py:155`, `aegis_challenge/pool.py:160`, `tests/test_runner.py:88` |
| 2. Hook fees are exported separately and not counted as CL revenue | pass | `aegis_challenge/pool.py:126`, `aegis_challenge/pool.py:200`, `aegis_challenge/pool.py:202`, `aegis_challenge/runner.py:453`, `aegis_challenge/runner.py:457`, `aegis_challenge/runner.py:589`, `aegis_challenge/runner.py:593` |
| 3. Raw exports split CL fees into base LP fees and DFM LP fee lift, and verifier requires base + lift = total | pass | `aegis_challenge/runner.py:454`, `aegis_challenge/runner.py:455`, `aegis_challenge/runner.py:590`, `aegis_challenge/runner.py:591`, `aegis_challenge/export_verifier.py:71`, `aegis_challenge/export_verifier.py:77` |
| 4. UI highlights DFM surge and shows DFM lift in CL fee row | pass | `web/index.html:1061`, `web/index.html:1070`, `web/index.html:1075`, `web/index.html:1077`, `scripts/ui-base-realism.js:95`, `scripts/ui-base-realism.js:99`, `reports/base-realism/ui-base-realism.json` |
| 5. Full 180-day export recomputation passes with no mismatch | pass | `reports/base-realism/full-run/1c9a94d52abd5b62`, `reports/base-realism/full-run-verification.json`, read-only verifier rerun on 2026-06-05 |
| 6. Tests and Playwright evidence support the claims | pass | `python3 -m pytest -q -p no:cacheprovider` passed `90 passed`; `reports/base-realism/ui-base-realism.json` status `pass` |
| 7. Residual risks are accurately stated, especially exact live per-pool DFM policy calibration | pass | `reports/base-realism-hardening.md:111`, this report's residual risks |

## DFM Mechanics Finding

DFM is economically active in the CL fee path. `apply_dfm_fee_state` writes the dynamic fee into `pool.lp_fee_pips`, and `Pool.swap_exact_in` feeds that value into swap-step fee computation. The resulting LP fee is added to global fee growth (`fee_growth_global{0,1}_x128`), which is later settled into CL positions through fee-growth-inside accounting.

The AEGIS contract references support the same interpretation. `AegisHook._beforeSwap` obtains `activeFee` from `DYNAMIC_FEE_MANAGER.prepareSwap` and returns it as the Uniswap v4 override fee. Hook fees are computed separately from that active fee, charged in the input currency, accumulated as pending hook fees, and potentially reinvested.

## Full-Run Verification

Run directory: `reports/base-realism/full-run/1c9a94d52abd5b62`

Verifier status: `pass`

- Replay steps: `17,280`
- Simulated horizon: `180.0000 days`
- Execution swap rows: `136,401`
- Child trade count: `1,995,887`
- Total volume: `$722,569,061.525085019461007847107936347629016984784281715644364`
- LP/CL fees: `$3,200,271.29973064609731761750524235153994841923416626279920532`
- Base LP/CL fees: `$2,166,797.42399533475867658947370471631320911446666054922742459`
- DFM LP/CL fee lift: `$1,033,473.87573531133864102803153763522673930476750571357178125`
- Base plus lift minus total: `5.2E-52`
- DFM hook fees: `$320,223.160230995694779559321488250125465026084518839363454230`
- DFM surge steps: `15,360`
- Rejected strategy actions: `0`
- Raw export ZIP: valid

## Test Evidence

Commands run:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_runner.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
from aegis_challenge.export_verifier import verify_run_export
print(verify_run_export(Path('reports/base-realism/full-run/1c9a94d52abd5b62')))
PY
```

Results:

- `tests/test_runner.py`: `8 passed`
- Full pytest suite: `90 passed`
- Read-only export verifier rerun: `status=pass`, `failures=[]`

I did not rerun `npm run ui:base-realism` because that script writes `reports/base-realism/ui-base-realism.{json,md,png}` and the review scope only authorized writing the two independent-review artifacts. I verified the existing Playwright evidence file and the script assertions instead.

## Blockers

None.

## Non-Blocking Risks

- Exact live per-pool DFM policy parameters were not available in the reviewed materials. The simulator mechanics match the hook shape, but fee surge sizing/cadence should remain labeled as deterministic calibration until live per-pool policy snapshots are available.
- Playwright was not rerun in this review to avoid overwriting existing UI evidence outside the allowed artifact list. Existing Playwright evidence and the script assertions support the UI gate.
- The Base market comparison relies on a point-in-time GeckoTerminal reference file, not a formal Uniswap v4 Base subgraph calibration set.
- Retail child trades are exported as deterministic counts on execution swap rows, not as one row per child trade. This is reasonable for tractability but should stay documented.

## Not Verified

- Exact live target-pool DFM policy calibration.
- Fresh Playwright rerun output generated during this independent review.

## Evidence Paths

- `reports/base-realism-hardening.md`
- `reports/base-realism-hardening.json`
- `reports/base-realism/full-run-verification.json`
- `reports/base-realism/ui-base-realism.json`
- `reports/base-realism/ui-base-realism.png`
- `reports/base-realism/base-weth-usdc-reference.json`
- `reports/base-realism/full-run/1c9a94d52abd5b62`
- `aegis_challenge/dfm.py`
- `aegis_challenge/pool.py`
- `aegis_challenge/runner.py`
- `aegis_challenge/export_verifier.py`
- `tests/test_runner.py`
- `scripts/ui-base-realism.js`
- `web/index.html`
- `/Users/page/Page/repos/aegis-engine/contracts/AegisHook.sol`
- `/Users/page/Page/repos/aegis-engine/contracts/interfaces/dfm/IDynamicFeeManager.sol`
