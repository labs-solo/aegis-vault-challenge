# APR Live Update Fix

Status: fixed

Bug: during progressive simulation the browser could keep displaying a stale final `score.apr_pct` from the previous/default score until completion. This made APR appear to update only at the end even though replay profit and elapsed simulated days were changing.

Fix: `web/index.html` now gives precedence to the currently selected replay event. If the event has `apr_pct`, it displays that value. If the event is an older/live payload without `apr_pct`, it computes APR from `net_profit_usd_after_penalties`, `initial_balance_usdc`, and elapsed simulated days before falling back to score-level APR.

Follow-up fix: live-event APR no longer falls back to `totalDays()`/180. For an in-progress event, the browser now uses only event-level elapsed time (`elapsed_simulated_days`, `simulated_day`, or `timestamp`). If elapsed time is unavailable, APR stays in the non-finite/building state instead of silently using the fixed challenge horizon.

Live browser evidence against `http://127.0.0.1:4173/web/index.html`:

- Before run: `+2.11%`
- During run after 4.5s: `+4.82%`
- During run after 9s: `+11.61%`
- Completion status at sample time: still running
- Raw replay includes `apr_pct`: yes
- Raw replay includes `elapsed_simulated_days`: yes

Verification:

- `python3 -m pytest tests/test_runner.py::test_replay_apr_annualizes_by_elapsed_days_not_full_horizon tests/test_web.py::test_live_apr_uses_elapsed_event_time_not_fixed_horizon tests/test_web_app.py::test_score_and_replay_are_money_first_usdc_eth -q`: 3 passed
- `python3 -m pytest tests/test_web.py tests/test_web_app.py -q`: 20 passed
- `python3 -m pytest -q`: 79 passed

Operational note: local disk pressure was also blocking simulator writes. Cleared rebuildable pnpm package cache at `~/Library/pnpm/store`, restoring about 11 GiB free.
