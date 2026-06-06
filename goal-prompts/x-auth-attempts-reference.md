# X Auth, Attempts, Cooldowns, Leaderboard, and Sharing Reference

Use this file as the detailed requirement source for the short Codex goal prompt. Build a delightful social competition flow without weakening the existing AEGIS vault challenge simulation.

## Product Outcome

Contestants can run one anonymous simulation, then sign in with X to keep iterating. Completed runs auto-save as named attempts. Users can rename, clone, compare, publish, unpublish, and share attempts. Only explicitly published attempts appear on the leaderboard. The leaderboard feels social and alive with X handle, avatar or fallback avatar, strategy name, rank, APR, USD profit, ETH exposure/risk, badges, and personal-best/rank movement where practical.

## Auth And Security

- Say "Sign in with X"; never ask for credentials or render password fields.
- Use OAuth/OIDC-style X auth with Authorization Code + PKCE, CSRF `state`, exact redirect URI, minimal scopes, secure session cookies, and logout.
- Default local/dev behavior must work through mock X auth when real X env vars are absent.
- Real X auth must be env-ready and documented, including callback URL, scopes, and failure states.
- Prefer X web intent/share URLs for sharing. Do not auto-post. If direct X posting is implemented, request write scope only at share time and require an explicit click.
- No secrets, access tokens, refresh tokens, raw cookies, hidden seeds, private paths, or private runner state may appear in public HTML, JSON, replay, leaderboard, reports, logs, or tests.
- Cookies must be HttpOnly, SameSite, path-scoped, and Secure outside localhost.

## Run Limits

- Anonymous sessions may start exactly one simulation.
- On the second anonymous run attempt, block with structured reason `auth_required`, preserve strategy text and latest result, and show "Sign in with X to try again".
- Authenticated users may start one simulation every 300 seconds, enforced server-side by user id.
- Cooldown must not block editing, replay inspection, saving, renaming, cloning, comparing, publishing, unpublishing, or sharing.
- Cooldown UI must show countdown, next available time, and useful actions while waiting.

## Attempt Persistence

Persist safe records for attempt id, user id, X handle, avatar URL, run id, strategy name, created/saved/published timestamps, score/APR/profit/risk fields, published flag, share URL/text, and safe artifact references. Do not expose full local paths or hidden data. Completed successful runs auto-save with a sensible default strategy name. Users can rename, clone, publish, unpublish, and list attempts.

## UX Requirements

- Top-right identity state: anonymous, signed in, avatar/handle, logout.
- First-run flow: page load to first simulation start in 1 click.
- Login wall is non-destructive and appears only when needed.
- Saved attempts surface is clear and compact, not a separate admin console.
- Use direct labels: "Sign in with X", "Save try", "Rename", "Clone", "Publish this try", "Unpublish", "Share on X".
- Empty, cooldown, auth error, provider-misconfigured, publish success, and share fallback states must be friendly and actionable.
- Mobile and keyboard flows must remain usable.

## Leaderboard And Sharing

- Ranking should preserve canonical net USD profit/score unless existing docs require otherwise.
- Leaderboard rows show rank, handle, avatar/fallback, strategy name, APR, USD profit, ETH exposure/risk, badges, and published time.
- Badge examples: personal best, beat starter, beat no-op, delta-safe, no-liquidation, low-churn, robust-tail.
- After publishing, generate X share intent URL and copyable text with competition name, rank, strategy name, APR/profit, and URL. Include copy-link fallback.

## Required Metrics And Gates

- Funnel task completion: anonymous first run, mock login, second run after login/cooldown, save/rename attempt, publish, share intent, and leaderboard display all pass in Playwright.
- First-run friction: anonymous user can start first simulation in <=1 click after page load.
- Login recovery: blocked second run preserves strategy text and latest result in 100% of tested cases.
- Auth gate correctness: anonymous second run blocked 100%; authenticated run before 300s blocked 100%; run at/after 300s allowed 100%.
- Cooldown UX: countdown visible within 1s of blocked attempt; next available time shown; at least 3 useful actions remain enabled.
- Attempt lifecycle: auto-save after successful run 100%; rename/clone/publish/unpublish round trip passes; unpublished attempts never appear on leaderboard.
- Leaderboard identity: published row shows handle, avatar/fallback, strategy name, rank, APR, profit, and risk on desktop and mobile.
- Share delight: share text includes competition name, rank, strategy name, APR/profit, and URL; URL encodes correctly; no auto-post.
- Security: no password fields; no tokens/secrets/private paths in public JSON, replay, leaderboard, reports, console logs, or HTML.
- Accessibility: keyboard path completes mock login, save, publish, and share; visible focus; no critical a11y smoke failures.
- Performance: auth/status and attempts APIs p95 <=200ms locally; UI updates after run/publish <=1s excluding simulation time.
- UX readiness score >=4.5/5 overall; no category below 4/5 for clarity, friction, cooldown comprehension, leaderboard delight, sharing clarity, mobile, accessibility.
- Independent review score >=90/100, no blocker/high issues, readiness `world_class_ready`.

## Tests And Review

Add pytest coverage for auth/session, anonymous and authenticated rate limits, attempts, publishing, leaderboard privacy, share text/URL, and security scans. Add Playwright coverage for anonymous first-run, login-required second run, mock login, cooldown, attempts, publish, leaderboard, share, mobile, and keyboard/a11y smoke.

Write:

- `reports/x-auth-attempts-review.md`
- `reports/x-auth-attempts-review.json`

Review must include hard gates, metrics table, scorecard, evidence paths, remaining risks, and readiness status.
