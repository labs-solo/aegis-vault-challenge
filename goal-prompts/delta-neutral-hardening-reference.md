# Delta-Neutral Hardening Reference

Issue: https://github.com/labs-solo/aegis-vault-challenge/issues/1

## GitHub Delivery Checklist

1. Work from `main` on a scoped `codex/...` branch.
2. Link the PR to the issue.
3. Keep commits focused and exclude secrets, private paths, hidden seeds, and large run artifacts.
4. Merge only after tests, baseline evidence, docs coverage, and review reports pass.
5. Delete the remote and local feature branch after merge.
6. Confirm `main` is clean and current.

## Scoring Contract

- Leaderboard score is `edge_profit_usd` after neutrality penalties and gates.
- `edge_profit_usd = collected_cl_fees_usd + uncollected_cl_fees_usd + realized_lo_edge_usd + unrealized_lo_edge_usd - borrow_cost_usd - action_costs - repair_cost_usd - liquidation_cost_usd - invalid_action_penalty`.
- Raw equity PnL, inventory PnL, and debt mark-to-market remain diagnostics.
- Average absolute ETH exposure above `3%` of initial equity fails or caps score.
- Max absolute ETH exposure above `8%` of initial equity fails or caps score.
- Terminal exposure above `3%` of equity, terminal LTV above the safe threshold, or terminal directional profit share above `25%` fails or caps score when it explains a win.
- DFM BaseHook fees and fee surges remain part of CL fee attribution.

## Evidence Requirements

- Directional baseline fails or caps.
- Neutral CL/LO baseline can remain positive.
- Score files, replay events, raw exports, UI, README, docs, and examples expose the same scoring vocabulary.
- Docs never imply that raw USD equity PnL alone wins.
- Review report includes commands, baseline outputs, changed docs, issue/branch/PR/merge proof, blockers, and readiness.
