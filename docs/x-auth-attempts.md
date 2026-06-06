# X Auth, Attempts, Cooldowns, Leaderboard, and Sharing

This website uses a passwordless X identity flow for competition identity and local mock auth for development. Contestants can run one anonymous simulation, then sign in with X to continue iterating.

## Participant Rules

- Anonymous contestants may start exactly one simulation.
- A second anonymous start returns `auth_required` and the UI keeps the edited strategy and latest result visible.
- Signed-in contestants may start one simulation every 300 seconds.
- Cooldown only blocks starting another simulation. Contestants can still edit, inspect replay, rename/clone attempts, publish/unpublish, and share.
- Successful runs auto-save as attempts with a strategy name.
- Publishing is explicit. Unpublished attempts stay private to the signed-in contestant and never appear on the public leaderboard.
- Sharing opens a polished modal with editable X text, an attempt-specific AEGIS result card, copy/download controls, and an explicit X web intent. The app never silently posts.

## Local Development

No X credentials are required locally. If `X_CLIENT_ID` and `X_REDIRECT_URI` are absent, `POST /api/auth/login` uses mock X auth and signs the current session in as a development user.

Useful endpoints:

```text
GET  /api/auth/status
POST /api/auth/login
POST /api/auth/mock-login
GET  /api/auth/callback
POST /api/auth/logout
GET  /api/attempts
POST /api/attempts/rename
POST /api/attempts/clone
POST /api/attempts/publish
POST /api/attempts/unpublish
```

## Real X Auth Configuration

Set these environment variables before starting the server:

```text
X_CLIENT_ID=...
X_CLIENT_SECRET=...              # optional for confidential clients
X_REDIRECT_URI=https://your.host/api/auth/callback
X_AUTH_SCOPES="users.read tweet.read"
AEGIS_COMPETITION_URL=https://your.host/web/index.html
AEGIS_SHARE_MODE=production       # optional hard gate: never emit localhost/127.0.0.1 share URLs
```

The X app callback URL must exactly match `X_REDIRECT_URI`.

Current X documentation confirms the required OAuth 2.0 Authorization Code with PKCE parameters: `response_type=code`, `client_id`, exact `redirect_uri`, `state`, `code_challenge`, and `code_challenge_method`. The app requests read scopes for identity lookup. `tweet.write` is not requested because sharing uses a web intent instead of direct posting.

Primary references:

- https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code
- https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/user-access-token
- https://docs.x.com/x-api/posts/manage-tweets/quickstart
- https://developer.x.com/en/docs/twitter-for-websites/tweet-button/guides/web-intent

## Stored Attempt Fields

Attempts are persisted under the local run state and contain safe competition data:

```text
attempt_id
owner_id
public user id/handle/name/avatar URL
run_id
bundle
strategy_name
strategy_source              # returned only to the owning session
created_at/saved_at/published_at
published
score
profit_usd
apr_pct
avg_eth_exposure_usd
max_eth_exposure_usd
repairs_liquidations
safe_artifacts               # run id plus score/replay filenames only
```

Public leaderboard rows omit `strategy_source`, local paths, hidden seeds, raw cookies, tokens, and private runner state.

## Share Modal And Result Card

Publishing a try, or selecting `Share` from a published saved try, opens the share modal. The modal includes:

- `You're ranked #N` headline when the attempt is on the public leaderboard.
- Editable post copy with clean rank/profit/APR formatting such as `+$7,785 on $100K | +15.79% APR`.
- A generated canvas result card containing AEGIS branding, rank, handle, strategy name, ETH/USDC, `$100K start`, profit, APR, and one risk/neutrality badge.
- Explicit buttons for `Share on X`, `Copy text`, `Download card`, and `Close`.

The X intent uses `text` plus the separate `url` query parameter so the link is not duplicated. The downloadable PNG is for optional manual attachment on X; the app does not request `tweet.write`, upload media, or post on the user's behalf.

Local development defaults to a local challenge URL. When the URL is local, the modal labels it as a local/dev link and warns that it only works on the current machine. For production, set `AEGIS_COMPETITION_URL` to the public competition URL. If `AEGIS_SHARE_MODE=production` or `AEGIS_ENV=production` is set and the configured URL is still local, the share payload suppresses the local URL and asks for `AEGIS_COMPETITION_URL` before public sharing.

## Security Notes

- The UI never renders password fields or asks for X credentials.
- The session cookie is `HttpOnly`, `SameSite=Lax`, path scoped, and `Secure` outside localhost.
- OAuth state is random and server-side.
- PKCE verifier values are server-side only.
- Access tokens are used only in memory for profile lookup and are not persisted.
- Secrets are read from environment variables only.
- Share links use `https://twitter.com/intent/tweet` so the user can review or edit before posting.
- Share cards are generated from already-public attempt fields and do not expose local paths, hidden seeds, strategy source, tokens, cookies, or private replay state.
