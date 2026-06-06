# Documentation

This directory is the repository documentation for the AEGIS Vault Challenge. It complements the in-app Strategy Academy at `web/docs.html`.

## Start Here

- [Participant Guide](participant-guide.md): how to participate from the website in a few steps.
- [Strategy API](strategy-api.md): every strategy action, important public state, and hidden-info boundary.
- [Simulation and Scoring](simulation-and-scoring.md): ETH/USDC market paths, AEGIS vault accounting, DFM fees, raw data, and leaderboard scoring.
- [Development Guide](development.md): setup, commands, repo map, tests, and local operations.
- [X Auth, Attempts, Cooldowns, Leaderboard, and Sharing](x-auth-attempts.md): identity, saved tries, rate limits, publishing, and share modal behavior.

## In-App Docs

The contestant-facing academy lives at:

```text
web/docs.html
```

When the local server is running:

```text
http://127.0.0.1:4173/web/docs.html
```

The academy is the best place for a contestant to quickly learn what AEGIS Engine is, what the challenge asks them to do, what actions their Python strategy can return, and how to improve a strategy.

## Useful Reports

- `reports/docs-academy-review.md`: docs/academy coverage and UX review.
- `reports/market-engine-v2-review.md`: market path realism and robustness review.
- `reports/base-realism-independent-review.md`: Base-like market realism review.
- `reports/launch-readiness.md`: launch-readiness dashboard.

## Documentation Standard

Good docs for this repo must answer four questions quickly:

1. What is the competition?
2. How does a contestant participate?
3. What can a strategy do and what can it read?
4. How do maintainers verify that the simulator, UI, and scoring are correct?
