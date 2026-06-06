# USDC/ETH Money-First Reference

## Product Truth

The challenge should read like a real competition:

Contestants start with `100,000 USDC`, trade an `ETH/USDC` AEGIS vault/pool, and try to maximize USD profit while keeping ETH exposure close to zero. ETH price is always shown as `USDC per ETH`. Delta means how much the vault's USD equity changes when ETH price moves.

The first viewport must make these facts obvious without requiring docs:

- Starting capital: `100,000 USDC`
- Market: `ETH/USDC`
- Objective: maximize USD profit after penalties
- Risk: ETH exposure / delta drift
- Tools: AEGIS vault liquidity, limit orders, borrow/repay, repairs
- Horizon: 180 simulated days, progressive web run over 30-120 seconds

## Implementation Scope

Update the simulator config, public artifacts, frontend, docs, examples, tests, Playwright scripts, and review reports.

Canonical fields should include:

- `base_token: "USDC"`
- `risk_token: "ETH"`
- `quote_token: "USDC"`
- `pool_pair: "ETH/USDC"`
- `price_quote: "USDC per ETH"`
- `initial_cash_usdc: 100000`
- `initial_eth: 0`
- `initial_price_usdc_per_eth`
- `horizon_days: 180`

Score/replay/API fields should include:

- `initial_balance_usdc`
- `equity_usd`
- `profit_usd`
- `profit_pct`
- `net_profit_usd_after_penalties`
- `eth_price_usdc`
- `net_eth_delta`
- `eth_exposure_usd`
- `avg_eth_exposure_usd`
- `max_eth_exposure_usd`
- `delta_penalty_usd`
- `exposure_penalty_usd`
- `fees_earned_usd`
- `lo_edge_usd`
- `inventory_pnl_usd`
- `borrow_cost_usd`
- `repair_cost_usd`
- `liquidation_cost_usd`

Keep compatibility fields only where useful, but the UI should prefer the money-first fields.

## UX And Copy

Use direct contestant-centered copy:

- Hero/console line: `Start with 100,000 USDC. Trade ETH/USDC. Make USD profit without taking ETH direction risk.`
- CTA: `Run 6-month ETH/USDC simulation`
- Helper: `Your Python strategy controls AEGIS vault liquidity, limit orders, and borrow/repay over 180 simulated days.`
- Delta explanation: `ETH exposure shows how much your vault gains or loses when ETH moves. Stay near zero so profit comes from liquidity and order flow, not a directional ETH bet.`
- Score explanation: `Leaderboard profit is USD equity above 100,000 USDC after borrow costs, repairs, liquidations, and delta penalties.`

Primary metric order:

1. USD profit
2. Current equity
3. Return %
4. Net ETH exposure
5. ETH exposure USD
6. Delta band
7. Borrow health / LTV
8. Fees and order-flow edge

## Graphics

Required visualizations:

- USD profit over time, anchored at `$0` against `$100,000` starting capital
- ETH/USDC price over time
- ETH exposure with visible neutral band
- LTV/debt/borrow health
- PnL attribution: CL fees, LO edge, inventory PnL, borrow costs, repairs/liquidations, delta penalties
- Regime markers across the 180-day replay
- Event tape labels that include day, ETH price, profit, exposure, and action

Charts must be professional: real axes, currency formatting, useful labels, no arbitrary decorative formatting, no fake data.

## Leaderboard

Rank by `net_profit_usd_after_penalties`. Show:

- Strategy
- Profit USD
- Return %
- Avg ETH exposure
- Max ETH exposure
- Repairs / liquidations
- Submission time or run id

Directional ETH strategies should not win merely because ETH rallied or fell.

## Tests

Unit/integration tests should verify:

- Default bundle uses `ETH/USDC`, `100000 USDC`, `initial_eth == 0`, 180 days.
- Empty/no-op strategy does not create unexplained USD profit.
- Directional ETH exposure is penalized and cannot dominate scoring.
- Late-flatten directional ETH exposure is penalized using average/max exposure over the run, not only terminal delta.
- Delta-neutral fee/order-flow strategy can score positively.
- Replay and score fields are USD-denominated and deterministic.
- Web progressive final output matches simulator artifacts.
- Submission uses final complete run only.
- Unsafe strategies still fail closed.

Playwright should verify:

- First viewport includes `100,000 USDC`, `ETH/USDC`, `USD profit`, and `ETH exposure`.
- Button says `Run 6-month ETH/USDC simulation`.
- Progress, charts, event tape, results, and leaderboard use USD/ETH labels.
- Final run displays profit, equity, return, ETH exposure, and delta band.
- Submit remains disabled until final success.
- Desktop, laptop, tablet, mobile, keyboard navigation, no console errors.

## Independent Scoring Rubric

Hard gates, all required:

- HG1: Website first viewport makes tokens, starting balance, objective, and ETH exposure clear.
- HG2: Simulator artifacts contain canonical USDC/ETH money fields.
- HG3: Score rewards USD profit after neutrality penalties, not ETH beta.
- HG4: Default web run remains the real 180-day progressive simulator.
- HG5: Sandbox and hidden-information protections still pass.
- HG6: Playwright and pytest evidence exists and passes.

Score out of 100:

- Product clarity, 15
- Simulator/accounting correctness, 20
- Delta-neutral scoring integrity, 20
- UX/charts/leaderboard quality, 15
- Strategy API and examples, 10
- Test and Playwright coverage, 10
- Aegis brand fidelity and polish, 5
- Report/evidence quality, 5

World-class threshold:

- All hard gates pass
- Total score >= 90
- No category below 80%
- No blocker/high UX or correctness issue
- Review status: `world_class_ready`

Review artifacts:

- `/Users/page/Page/repos/aegis-vault-challenge/reports/usdc-eth-money-review.md`
- `/Users/page/Page/repos/aegis-vault-challenge/reports/usdc-eth-money-review.json`

The review must cite exact files, tests, screenshots, metrics, and remaining risks. If any hard gate fails or the score is below threshold, the agent must continue fixing instead of stopping at recommendations.
