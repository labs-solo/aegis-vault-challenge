# Codex Goal Prompt: X Auth, Attempts, Cooldowns, Leaderboard, and Sharing

Goal: improve `/Users/page/Page/repos/aegis-vault-challenge` so contestants get a measured, delightful social competition flow: one anonymous run, Sign in with X to continue, auto-saved named attempts, explicit publishing, social leaderboard rows, and X sharing after publish.

Read first:
`/Users/page/Page/repos/aegis-vault-challenge/goal-prompts/x-auth-attempts-reference.md`
`/Users/page/Page/repos/aegis-vault-challenge/README.md`
`/Users/page/Page/repos/aegis-vault-challenge/web/index.html`
`/Users/page/Page/repos/aegis-vault-challenge/aegis_challenge/{web_app.py,web_server.py,leaderboard.py,runner.py,api.py}`
`/Users/page/Page/repos/aegis-vault-challenge/tests/`
`/Users/page/Page/repos/aegis-vault-challenge/scripts/`

Before implementation, verify current X docs for OAuth 2.0 Authorization Code with PKCE, user/profile lookup, web intent/share URLs, and post/write scopes if direct posting is considered.

Non-negotiables:
- Never collect X passwords. Use OAuth/OIDC-style X auth with PKCE, CSRF state, exact redirect URI, secure session cookie, logout, and token secrecy.
- Local mock X auth must work without real X credentials.
- Anonymous users get exactly one simulation. A second anonymous start is blocked with `auth_required` and preserves strategy/result.
- Authenticated users are server-side limited to one simulation start every 300s. Cooldown must not block editing, inspecting, saving, renaming, cloning, comparing, publishing, or sharing.
- Completed successful runs auto-save as attempts with editable strategy names.
- Only explicitly published attempts appear on leaderboard.
- Leaderboard rows show handle, avatar/fallback, strategy name, rank, APR, USD profit, ETH exposure/risk, and badges.
- Sharing defaults to X web intent/copyable text; do not auto-post.
- Preserve AEGIS branding, 180-day ETH/USDC simulation, elapsed-time APR, sandbox, and no-hidden-info rules.
- Never expose secrets, tokens, raw cookies, private paths, hidden seeds, or private runner state.

Implement:
1. Auth/session APIs: status, login, callback/mock-login, logout.
2. Run-limit APIs: anonymous one-run gate; authenticated 300s cooldown; structured block reasons.
3. Attempt persistence/actions: list, rename, clone, publish, unpublish, safe score/artifact refs.
4. UX: top-right identity, non-destructive login wall, attempt drawer/table, cooldown countdown, publish/share panel, friendly states.
5. Social leaderboard and share intent/copy fallback.
6. Docs for auth setup, env vars, mock mode, cooldowns, attempts, publishing, sharing, privacy/security.
7. Pytest and Playwright coverage for every flow and metric in the reference file.

Verification:
- Run full pytest.
- Run Playwright smoke, flow, progressive, auth/attempt/share, mobile, keyboard/a11y checks.
- Run security/privacy/auth scan.
- Write `reports/x-auth-attempts-review.md` and `.json` with hard gates, metrics, evidence, scorecard, risks, and readiness.

Completion threshold:
All tests pass; metrics in the reference file meet gates; mock auth works locally; real X auth is env-ready and documented; full flow is obvious and delightful; independent review says `world_class_ready` with score >=90/100 and no blocker/high issues.

Final response:
Report changed files, auth model, run-limit behavior, attempt lifecycle, leaderboard/share behavior, metrics results, test commands, review paths, local URL, and non-blocking risks.
