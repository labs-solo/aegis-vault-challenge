# Console Smoke UX Evidence

Status: smoke evidence only.

Verified surfaces:

- Aegis console layout with primary rail, strategy workspace, and right activity rail.
- Strategy editor with starter content.
- Replay JSONL, score JSON, and leaderboard JSON file inputs.
- Visual replay SVG renderer for price, delta, LTV, and fills.
- Step scrubber, event tape, raw public replay panel, risk panel, score waterfall, concept widgets, positions, and leaderboard.
- Public-safe leaderboard display with strategy filenames only.
- Accessibility smoke markers: page language, primary navigation label, run metrics label, replay chart image label, replay step label, and tablist role.

Not verified:

- Real screenshot evidence. Playwright was not available in the local Node runtime during this pass.
- Representative participant trial.
- Screen-reader walkthrough.
- Keyboard-only task completion.
- Timed first-run and first-edit measurements.

Launch implication:

This improves the UI implementation and automated smoke coverage, but does not satisfy the UX critical-path hard gate.
