# Market Engine V2 Distribution Audit

Status: pass
Engine: market-engine-v2.0
Calibration hash: dafa0f6baf925861
Bundle: public_train
Paths: 100

| Metric | Value |
|---|---:|
| Mean volume/day | 16258128.8919721514558241301811724174981884422657301725577579 |
| Mean trades/day | 45100.77 |
| Mean realized daily volatility | 0.10076573507185617381251714811688625 |
| Trade-count Fano factor | 36.4682242276434526505866751277195489123578156204428438789635 |
| Volume lag-1 autocorrelation | 0.111449848542080787283309415484671495589862239633886302684437 |
| Jump path share | 0.15 |
| DFM surge step share | 0.64 |

| Gate | Pass |
|---|---:|
| volume_day_in_base_band | True |
| trades_day_in_base_band | True |
| fano_factor | True |
| volume_autocorrelation | True |
| jump_path_share | True |
| dfm_surge_share | True |

Calibration source: `reports/base-realism/base-weth-usdc-reference.json`.
