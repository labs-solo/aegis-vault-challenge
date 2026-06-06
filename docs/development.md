# Development Guide

This guide is for builders working on the local AEGIS Vault Challenge implementation.

## Setup

```text
python3 -m pip install -e .
npm install
```

Python package entry point:

```text
aegis-vault
```

Equivalent module command:

```text
python3 -m aegis_challenge.cli
```

## Run The Website

```text
python3 -m aegis_challenge.web_server --port 4173
```

Open:

```text
http://127.0.0.1:4173/web/index.html
```

The in-app Strategy Academy is:

```text
http://127.0.0.1:4173/web/docs.html
```

## CLI Commands

```text
python3 -m aegis_challenge.cli run examples/starter_strategy.py --bundle smoke --seed 1
python3 -m aegis_challenge.cli replay runs/<run_id>/public_replay.jsonl
python3 -m aegis_challenge.cli explain runs/<run_id>/public_replay.jsonl --step 0
python3 -m aegis_challenge.cli submit examples/starter_strategy.py
python3 -m aegis_challenge.cli report
python3 -m aegis_challenge.cli metrics-v2
```

Common bundles:

```text
smoke
public_train
competition_6m
hidden_ranked
```

## Tests

Core suite:

```text
python3 -m pytest -q
```

Focused docs tests:

```text
python3 -m pytest tests/test_repo_docs.py tests/test_docs_academy.py -q
```

Playwright/UI checks:

```text
npm run ui:smoke
npm run ui:a11y
npm run ui:flow
npm run ui:auth-attempts
npm run ui:progressive
npm run ui:share-modal
npm run ui:docs-academy
npm run ui:base-realism
npm run ui:market-engine-v2
```

## Repo Map

```text
aegis_challenge/api.py        Strategy action and public state dataclasses
aegis_challenge/runner.py     Strategy runner, replay artifacts, raw exports
aegis_challenge/sandbox.py    Strategy import/runtime guardrails
aegis_challenge/pool.py       Concentrated-liquidity pool mechanics
aegis_challenge/v4_math.py    Uniswap v4-style math helpers
aegis_challenge/vault.py      AEGIS debt, LTV, repair, and vault accounting
aegis_challenge/dfm.py        DFM BaseHook fee logic
aegis_challenge/scoring.py    Score and penalty calculations
aegis_challenge/leaderboard.py Local leaderboard and submission records
aegis_challenge/auth_attempts.py X/mock auth, sessions, attempts, cooldowns
aegis_challenge/web_app.py    Website API orchestration
aegis_challenge/web_server.py Local HTTP server
web/index.html                Main contestant app
web/docs.html                 In-app Strategy Academy
docs/                         Repository documentation
examples/                     Example strategies
tests/                        Test suite and golden vectors
scripts/                      UI and realism verification scripts
reports/                      Evidence artifacts
```

## Documentation Maintenance

When the strategy API changes, update all of:

- `aegis_challenge/api.py`
- `web/docs.html`
- `docs/strategy-api.md`
- `README.md`
- `tests/test_docs_academy.py`
- `tests/test_repo_docs.py`

When simulator or scoring behavior changes, update:

- `docs/simulation-and-scoring.md`
- Relevant reports under `reports/`
- UI labels in `web/index.html` if displayed behavior changed.

## Local Auth And Sharing

Local development does not require real X credentials. If real X env vars are absent, login uses mock auth. See [x-auth-attempts.md](x-auth-attempts.md).

Important environment variables:

```text
X_CLIENT_ID
X_CLIENT_SECRET
X_REDIRECT_URI
X_AUTH_SCOPES
AEGIS_COMPETITION_URL
AEGIS_SHARE_MODE
AEGIS_ENV
```

Secrets must stay in environment/config only. Do not commit credentials or write them into reports.
