# Participant Trial

Status: pass

Date: 2026-06-05

Trial type: facilitator-run first-run workflow using the public contestant CLI and starter strategy.

## Task

A new participant should be able to run the starter strategy, replay the result, inspect step-level attribution, and find generated evidence without organizer help.

## Commands

```text
python3 -m aegis_challenge.cli run examples/starter_strategy.py --bundle smoke --seed 1 --out-dir reports/ux/participant-trial-runs
python3 -m aegis_challenge.cli replay reports/ux/participant-trial-runs/8a7711c8f5cf0ab1/public_replay.jsonl
python3 -m aegis_challenge.cli explain reports/ux/participant-trial-runs/8a7711c8f5cf0ab1/public_replay.jsonl --step 0
npm run ui:smoke
```

## Evidence

- `reports/ux/participant-trial-runs/8a7711c8f5cf0ab1/public_replay.jsonl`
- `reports/ux/participant-trial-runs/8a7711c8f5cf0ab1/score.json`
- `reports/ux/participant-trial-runs/8a7711c8f5cf0ab1/comparison.json`
- `reports/ux/participant-trial-runs/8a7711c8f5cf0ab1/calibration.json`
- `reports/screenshots/desktop-console.png`
- `reports/screenshots/mobile-console.png`

## Result

The starter workflow completed without errors. Replay reported 60 events from step 0 through step 59. Explain returned step 0 swaps, risk state, score, and vault debt/delta/LTV attribution. Playwright UI smoke passed on desktop and mobile screenshots.

## Residual UX Risk

This is not an external novice study. It proves the current public workflow is executable, but launch readiness still needs independent review before claiming serious public competition readiness.
