# Delta-Neutral Hardening Review

Status: complete
Readiness: world_class_ready
Issue: https://github.com/labs-solo/aegis-vault-challenge/issues/1
PR: https://github.com/labs-solo/aegis-vault-challenge/pull/2
Branch: `codex/delta-neutral-hardening-1`

## Gates

| Gate | Status | Evidence |
|---|---|---|
| Edge-first score | pass | `aegis_challenge/scoring.py`, `tests/test_runner.py::test_edge_first_score_attribution_and_gates_are_exported` |
| Directional beta cannot win | pass | `tests/test_runner.py::test_directional_baselines_fail_or_cap_score`, full baseline `5d2fb273c92e4586` |
| Neutral CL/LO baseline can remain positive | pass | smoke baseline `a6f9d939611d7a92`, score `7.08866719188068644363583641314873007144048602975825217850899` |
| Raw exports include attribution/gates | pass | `aegis_challenge/export_verifier.py`, raw export tests |
| UI/docs/examples match mechanics | pass | README/docs/web/example updates plus docs tests and Playwright checks |
| Hidden-info boundary preserved | pass | `python3 -m pytest -q` |

## Formula

Leaderboard score uses edge profit after neutrality penalties/gates:

```text
edge_profit_usd =
  collected_cl_fees_usd
  + uncollected_cl_fees_usd
  + realized_lo_edge_usd
  + unrealized_lo_edge_usd
  - borrow_cost_usd
  - action_costs
  - repair_cost_usd
  - liquidation_cost_usd
  - invalid_action_penalty
```

Raw equity PnL, inventory PnL, and debt mark-to-market remain diagnostics.

## Thresholds

- Average absolute ETH exposure above `3%` of initial equity fails/caps.
- Max absolute ETH exposure above `8%` of initial equity fails/caps.
- Terminal absolute ETH exposure above `3%` of equity fails/caps.
- Terminal LTV above the safe threshold fails/caps.
- Terminal directional profit share above `25%` fails/caps when inventory/debt explains the win.

## Baselines

| Strategy | Bundle | Seed | Run | Score | Raw PnL | Gate |
|---|---|---:|---|---:|---:|---|
| `benchmarks/01_directional_long_eth.py` | `competition_6m` | 1 | `5d2fb273c92e4586` | `-2661957.06226421217829438188140373788029711213238873173069842` | `-65199.7869873369531702059878667538985640113365842533433207858` | fail: average exposure above 3% |
| `benchmarks/07_delta_neutral_heuristic.py` | `competition_6m` | 1 | `3d5b74375f50dd0c` | `0` | `49195.060621688513939958845512122247741323237183227881545815` | fail: max exposure above 8% |
| `benchmarks/07_delta_neutral_heuristic.py` | `smoke` | 1 | `a6f9d939611d7a92` | `7.08866719188068644363583641314873007144048602975825217850899` | diagnostic only | pass |

The full six-month heuristic demonstrates the fix: even with large raw equity PnL, excess ETH exposure and directional share prevent a valid win.

## Verification

- `python3 -m pytest -q` -> `113 passed in 29.01s`
- `npm run ui:smoke` -> pass, screenshots in `reports/screenshots/`
- `npm run ui:docs-academy` -> pass, screenshots in `reports/docs-academy/`
- Full baselines written under `runs/delta-hardening-baselines/`

## Docs Coverage

Updated:

- `README.md`
- `docs/participant-guide.md`
- `docs/simulation-and-scoring.md`
- `docs/strategy-api.md`
- `examples/README.md`
- `examples/starter_strategy.py`
- `web/index.html`
- `web/docs.html`

## GitHub Proof

- Issue: https://github.com/labs-solo/aegis-vault-challenge/issues/1
- Branch: `codex/delta-neutral-hardening-1`
- PR: https://github.com/labs-solo/aegis-vault-challenge/pull/2
- Merge: `MERGED` at `2026-06-06T03:55:27Z`, merge commit `0b693d17f62b1821d1c6cac100156ddd29950d47`
- Branch deletion: remote branch deleted by `gh pr merge --delete-branch`; local branch `codex/delta-neutral-hardening-1` deleted after merge

## Blockers

None.
