from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
sys.path.insert(0, str(ROOT))

from aegis_challenge.flow import scenario  # noqa: E402
from aegis_challenge.market_engine_v2 import audit_distribution  # noqa: E402


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = audit_distribution(scenario, "public_train", range(1, 101))
    json_path = REPORT_DIR / "market-engine-v2-distribution.json"
    md_path = REPORT_DIR / "market-engine-v2-distribution.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    metrics = report["metrics"]
    gates = report["gates"]
    lines = [
        "# Market Engine V2 Distribution Audit",
        "",
        f"Status: {report['status']}",
        f"Engine: {report['engine_version']}",
        f"Calibration hash: {report['calibration_hash']}",
        f"Bundle: {report['bundle']}",
        f"Paths: {report['path_count']}",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Mean volume/day | {metrics['mean_volume_usd_per_day']} |",
        f"| Mean trades/day | {metrics['mean_trades_per_day']} |",
        f"| Mean realized daily volatility | {metrics['mean_realized_volatility_daily']} |",
        f"| Trade-count Fano factor | {metrics['trade_count_fano_factor']} |",
        f"| Volume lag-1 autocorrelation | {metrics['volume_autocorrelation_lag1']} |",
        f"| Jump path share | {metrics['jump_path_share']} |",
        f"| DFM surge step share | {metrics['dfm_surge_step_share']} |",
        "",
        "| Gate | Pass |",
        "|---|---:|",
        *[f"| {name} | {value} |" for name, value in gates.items()],
        "",
        "Calibration source: `reports/base-realism/base-weth-usdc-reference.json`.",
    ]
    md_path.write_text("\n".join(lines) + "\n")
    print(json.dumps({"status": report["status"], "evidence": [str(json_path), str(md_path)]}, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
