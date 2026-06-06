# APR Display Independent Review

Status: world_class_ready

Reviewer mode: fallback independent rubric pass. A separate sub-agent was not spawned because this session's sub-agent tool is restricted to explicit user requests for delegation. The review below uses fresh test, Playwright, source-scan, and artifact evidence.

## Hard Gates

| Gate | Status | Evidence |
|---|---|---|
| Participant-facing performance says APR, not Return | pass | `web/index.html`, `tests/test_web.py` |
| APR uses annualized net USD profit over elapsed simulated days | pass | `aegis_challenge/runner.py`, `tests/test_web_app.py` |
| Replay events expose `apr_pct` and `elapsed_simulated_days` | pass | `reports/ux/flow-metrics.json`, `tests/test_web_app.py` |
| Final score exposes `apr_pct` and `elapsed_simulated_days` | pass | `aegis_challenge/runner.py`, `tests/test_web_app.py` |
| Leaderboard displays APR while preserving old run compatibility | pass | `aegis_challenge/leaderboard.py`, `aegis_challenge/web_app.py`, `web/index.html` |
| Day-zero behavior avoids fake precision | pass | `web/index.html` initializes APR as `building`; `annualized_apr_pct(..., elapsed_days=0)` returns `None` |
| Negative profit produces negative APR | pass | helper check and formula path in `aegis_challenge/runner.py` |
| Verification suite passes | pass | `python3 -m pytest -q`: 77 passed |
| Browser flow passes with APR rendered | pass | `node scripts/ui-flow.js`: pass; `reports/ux/flow-metrics.json` rendered `apr` |

## Scorecard

| Category | Score |
|---|---:|
| APR math correctness | 25/25 |
| Replay/score/API field integrity | 20/20 |
| Participant-facing UX language | 20/20 |
| Progressive browser evidence | 15/15 |
| Regression coverage and compatibility | 18/20 |

Final score: 98/100.

Readiness: world_class_ready.

## Notes

- `profit_pct` and `return_pct` remain only as compatibility/internal fallback fields for older artifacts and saved leaderboard rows.
- Fresh Playwright evidence shows rendered APR and raw replay fields: `apr_pct`, `elapsed_simulated_days`, `net_profit_usd_after_penalties`, and `initial_balance_usdc`.
- No participant-facing `Return` metric label remains in the website. The only scanned occurrence in active source is the regression assertion that prevents `Return</span>` from reappearing.

## Evidence Paths

- `aegis_challenge/runner.py`
- `aegis_challenge/api.py`
- `aegis_challenge/leaderboard.py`
- `aegis_challenge/web_app.py`
- `web/index.html`
- `tests/test_web_app.py`
- `tests/test_web.py`
- `scripts/ui-flow.js`
- `reports/ux/flow-metrics.json`
- `reports/ux/flow-metrics.md`
