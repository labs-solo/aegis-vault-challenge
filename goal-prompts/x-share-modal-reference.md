# X Share Modal Reference

This file is the detailed requirement source for the short Codex goal prompt.

## Product Outcome

After publishing a saved try, contestants see a polished share modal that makes the result feel worth posting. The modal should celebrate the participant, show a good-looking attempt-specific card, and provide clean X copy plus explicit user-controlled actions.

## Share Copy

- Lead with rank, USD profit, and APR.
- Use clean numbers: `#2`, `+$7,785`, `+15.79% APR`.
- Mention `Aegis Vault Challenge`.
- Explain the competition in one short line: make USD profit in ETH/USDC while staying delta-neutral.
- Include the challenge URL.
- Avoid raw decimals, overly long strategy names in the first line, and administrative phrasing like `I published`.
- Never auto-post. Use X web intent only unless a future explicit direct-post feature is added.
- The visible/copyable text may include the URL. The X intent should pass post text and URL separately so the displayed post does not duplicate the link.

Good local/dev copy:

```text
Ranked #2 in the Aegis Vault Challenge.

+$7,785 on $100K | +15.79% APR
Strategy: Starter delta-neutral vault

Make USD profit in ETH/USDC while staying delta-neutral.
Local dev link: http://127.0.0.1:4173/web/index.html
```

Good production copy:

```text
Ranked #2 in the Aegis Vault Challenge.

+$7,785 on $100K | +15.79% APR
Strategy: Starter delta-neutral vault

Make USD profit in ETH/USDC while staying delta-neutral.
https://aegis.markets/vault-challenge
```

## URL Behavior

- `AEGIS_COMPETITION_URL` is the canonical public challenge URL.
- Local URLs are acceptable only in dev and must be labeled as local/dev.
- Production share text and X intent must not contain `127.0.0.1` or `localhost`.
- If only a local URL is configured, the UI should warn that the link is local and provide copy/download fallback.
- In production share mode, localhost and `127.0.0.1` must be suppressed until `AEGIS_COMPETITION_URL` is configured.

## Share Modal UX

Open the modal after publish and when a user selects share from a saved try. It must include:

- Headline: `You're ranked #N`.
- Attempt card preview.
- Editable/copyable post text.
- Buttons: `Share on X`, `Copy text`, `Download card`, `Close`.
- A local/dev link warning when relevant.
- Mobile-safe layout with no overflow.

## Attempt Graphic

The graphic should be generated from the specific attempt and include:

- AEGIS logo/brand colors.
- Rank and X handle.
- Strategy name.
- USD profit and APR.
- `ETH/USDC` and `$100K start`.
- One neutrality/risk signal such as `Delta-safe`, `Low ETH risk`, or `No liquidation`.
- Downloadable PNG.
- The PNG is generated from public attempt fields only and can be manually attached by the user on X.

## Tests And Review

Add pytest coverage for share formatting, URL behavior, rank/profit/APR, no raw decimals, no automatic posting, and intent URL encoding. Add Playwright coverage for publish-to-modal, card rendering, copy button, X intent button, download card control, mobile modal usability, no overflow, and no console errors.

Write `reports/x-share-modal-review.md` and `reports/x-share-modal-review.json` with hard gates, metrics, screenshots, score, risks, and readiness.
