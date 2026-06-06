# Codex Goal Prompt: USDC/ETH Money-First Challenge

Goal: improve `/Users/page/Page/repos/aegis-vault-challenge` until the contestant website, simulator output, examples, tests, and reports make the challenge unmistakably: contestants start with `100,000 USDC`, trade an `ETH/USDC` AEGIS vault/pool, seek real USD profit, and minimize ETH exposure with AEGIS borrow/repay. The UX must answer in 5 seconds: what tokens, what balance, what market, what goal, what risk, how to win.

Read first:
`/Users/page/Page/repos/aegis-vault-challenge/goal-prompts/usdc-eth-money-first-reference.md`
`/Users/page/Page/repos/aegis-vault-challenge/README.md`
`/Users/page/Page/repos/aegis-vault-challenge/web/index.html`
`/Users/page/Page/repos/aegis-vault-challenge/aegis_challenge/{flow.py,runner.py,web_app.py,web_server.py}`
`/Users/page/Page/repos/aegis-vault-challenge/examples/`
`/Users/page/Page/repos/aegis-vault-challenge/tests/`
`/Users/page/Page/repos/aegis-vault-challenge/scripts/`
`/Users/page/Page/repos/aegis-vault-challenge/reports/`

Non-negotiables:
- Default competition pool is `ETH/USDC`; price is displayed as `USDC per ETH`.
- Starting contestant capital is exactly `100,000 USDC`; primary objective is USD profit after penalties.
- The UI, API, replay, score, examples, leaderboard, and docs use money-first names: equity USD, profit USD, return %, ETH exposure, delta band, borrow cost, fees, penalties.
- Winning must come from CL/LO/order-flow edge while staying delta neutral, not from hidden ETH beta.
- Default web run remains a real 180-day progressive simulation over 30-120s, with final submit using the same real simulator artifacts.
- Strategies stay sandboxed, deterministic by seed, fail closed, and never see future flow, hidden fair price, hidden seed, or private runner state.
- Preserve Aegis logo/favicon/H1/brand context.

Implement:
1. Add/propagate canonical config fields: base token USDC, risk token ETH, initial cash 100000 USDC, initial ETH 0, initial ETH/USDC price, 180-day horizon.
2. Add score/replay/API fields for `initial_balance_usdc`, `equity_usd`, `profit_usd`, `profit_pct`, `eth_price_usdc`, `net_eth_delta`, `eth_exposure_usd`, `delta_penalty_usd`, `fees_earned_usd`, `borrow_cost_usd`, and net profit after penalties.
3. Redesign first viewport, metrics, charts, replay, event tape, and leaderboard around USD profit and ETH exposure.
4. Update starter strategy and docs so contestants understand USDC capital, ETH/USDC liquidity, borrow/repay neutrality, and USD PnL quickly.
5. Add tests and Playwright checks from the reference file.

Independent review and scoring:
- Before declaring success, run an independent review. Use a separate reviewer/agent/session if available; otherwise run a fresh rubric pass as a fallback artifact.
- Write `/Users/page/Page/repos/aegis-vault-challenge/reports/usdc-eth-money-review.md` and `.json` with hard gates, 100-point score, evidence paths, blockers, and readiness.
- Loop until all hard gates pass, total score >=90/100, no category below 80%, no blocker/high UX issue remains, and reviewer status is `world_class_ready`.

Final response: report score, hard gates, readiness, changed files, test commands, Playwright evidence, local URL, remaining non-blocking risks, and the final participant steps.
