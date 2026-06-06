# Examples

These strategies are intentionally small. They are meant to teach the mechanics before you build something more robust.

## Files

- `00_hold_idle.py`: does nothing. Useful as a scoring/control baseline.
- `01_basic_delta_neutral_cl.py`: borrows AEGIS L-units and mints one ETH/USDC range.
- `02_limit_order_rebalancer.py`: places a simple limit order and withdraws filled proceeds.
- `starter_strategy.py`: a fuller starter with borrow, range minting, fee collection, LTV repair, delta repair, and an early exit so the full six-month run passes the hardened neutrality gates.

The leaderboard score is edge-first. Raw inventory gains from ETH moving are diagnostic only; robust examples should earn CL fees or LO edge, stay inside exposure gates, and finish with safe terminal inventory/LTV.

## Run

```text
python -m aegis_challenge.cli run examples/starter_strategy.py --bundle smoke --seed 1
python -m aegis_challenge.cli run examples/00_hold_idle.py --bundle smoke --seed 1
python -m aegis_challenge.cli run examples/01_basic_delta_neutral_cl.py --bundle smoke --seed 1
python -m aegis_challenge.cli run examples/02_limit_order_rebalancer.py --bundle smoke --seed 1
```

Use `--bundle competition_6m` for a full 180-day local run.

## Learn More

- Repository guide: `../README.md`
- Participant guide: `../docs/participant-guide.md`
- Strategy API: `../docs/strategy-api.md`
- In-app academy: `../web/docs.html`
