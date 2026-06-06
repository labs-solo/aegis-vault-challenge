# Codex Goal Prompt: AEGIS Docs Academy

Goal: improve `/Users/page/Page/repos/aegis-vault-challenge` so the app has a polished in-app Docs/Academy that makes AEGIS Engine compelling, teaches the challenge fast, and gives contestants practical strategy guidance from the UI alone.

Read first:
`README.md`
`web/index.html`
`aegis_challenge/{api.py,runner.py,market_engine_v2.py,vault.py,pool.py,dfm.py}`
`examples/`
`tests/`
`scripts/`
`docs/x-auth-attempts.md`
`reports/market-engine-v2-review.md`
`goal-prompts/docs-academy-reference.md`

References:
`/Users/page/Page/repos/aegis-engine`
`/Users/page/Page/repos/aegis-vault-challenge-spec/{PARTICIPANT_GUIDE.md,docs/api.md,docs/ux-brand.md}`
`https://aegis.markets/`

Non-negotiables:
- Build a real in-app docs area, not a thin README/docs link.
- Docs are reachable from first screen, editor, mobile nav.
- In 60 seconds, contestants can answer: what is AEGIS Engine, what is this challenge, what can my strategy do, how do I improve?
- Explain the challenge: start with 100,000 USDC and 0 ETH, trade ETH/USDC, make USD profit, minimize ETH exposure, use AEGIS borrow/repay plus CL/LO tools.
- Present AEGIS Engine as vault-native infrastructure: L-unit borrow/repay, debt, collateral floor, LTV, repairs, CL/LO attachment, DFM BaseHook fees, ranked hidden paths.
- Document 100% of strategy actions from `api.py`: `BorrowL`, `RepayL`, `SwapExactIn`, `MintRange`, `IncreaseRange`, `DecreaseRange`, `CollectFees`, `BurnRange`, `PlaceLimitOrder`, `CancelLimitOrder`, `WithdrawLimitOrder`, `DetachPosition`.
- Document important public state fields and hidden-info limits. Contestants never get hidden fair price, hidden seeds, future flow, or private runner state.
- Guidance includes purpose, fields, snippets, use cases, risks, errors, and improvement ideas.
- UX must be calm, branded, searchable/scannable, mobile-safe, and not concept-dense.

Implement:
1. Add Docs/Academy route or drawer, with navigation from the main app.
2. Add sections from `docs-academy-reference.md`: AEGIS primer, challenge objective, strategy lifecycle, action reference, public state guide, hidden-info rules, scoring/robustness guide, and recipes.
3. Add strategy recipes: starter, passive wide LP, narrow LP, limit-order rebalancer, delta repair, DFM surge harvester, robustness-first ranked strategy.
4. Add valid copyable snippets and optional insert/copy buttons near the editor.
5. Update main UI copy so contestants know docs explain every action.
6. Add tests for docs coverage, snippet validity, broken links, hidden-info claims, and Playwright desktop/mobile docs UX.

Measurable gates:
- API coverage: every action has purpose, fields, example, risk, common errors.
- Public state coverage: price/tick, pool/DFM fees, positions, LOs, balances, debt/LTV, delta/exposure, score/APR, swaps/fills/repairs.
- Strategy guidance: at least 7 recipes with when-to-use and failure modes.
- Snippet validity: 100% compile or validation pass.
- Link health: 100% pass.
- Mobile: no horizontal overflow at 390x844.
- First-time clarity: reviewer answers "what can my strategy do?" in under 60 seconds.
- UX/content score >=95/100, no category below 4/5.

Independent review:
Run full pytest, docs coverage tests, Playwright docs checks, and independent UX/content review. Write `reports/docs-academy-review.md` and `.json` with gates, metrics, evidence, score, blockers, risks, readiness.

Loop until complete. Fix blockers, thin copy, missing API/state coverage, invalid snippets, broken links, hidden-info mistakes, confusing nav, weak AEGIS explanation, or rough mobile UX. Do not stop at recommendations.

Completion threshold: all tests pass; docs are in-app, branded, compelling, complete; Playwright passes; independent score >=95/100; readiness `world_class_ready`.

Final response: report changed files, docs URL, action/state coverage, recipes, commands, review paths, independent score, readiness, and non-blocking risks.
