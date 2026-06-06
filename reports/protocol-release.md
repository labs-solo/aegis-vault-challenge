# Protocol Release

Status: `pass`
Fixture version: `aegis-vault-challenge-v1`

| Check | Status | Evidence |
|---|---|---|
| `uniswap_v4_vectors.json` | pass | tests/golden/uniswap_v4_vectors.json |
| `aegis_vault_vectors.json` | pass | tests/golden/aegis_vault_vectors.json |
| `scoring_vectors.json` | pass | tests/golden/scoring_vectors.json |
| `golden_regeneration` | pass | tests/golden/uniswap_v4_vectors.json, tests/golden/aegis_vault_vectors.json, tests/golden/scoring_vectors.json |
| `foundry_snapshot_parity` | pass | reports/golden/foundry-uniswap-v4-reference.json, reports/golden/foundry-aegis-vault-reference.json |
