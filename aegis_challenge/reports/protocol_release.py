from __future__ import annotations

import json
from pathlib import Path

from aegis_challenge.reports.verify_foundry_snapshots import verify_snapshot_paths
from aegis_challenge.reports.verify_golden import verify_paths


RELEASE_VERSION = "aegis-vault-challenge-v1"

REQUIRED_UNISWAP_IDS = {
    "UV4-TICK-000",
    "UV4-SWAP-001",
    "UV4-SWAP-002",
    "UV4-TICK-001",
    "UV4-TICK-002",
    "UV4-FEE-001",
    "UV4-FEE-002",
}

REQUIRED_AEGIS_IDS = {
    "AE-BORROW-001",
    "AE-REPAY-001",
    "AE-LTV-001",
    "AE-LTV-002",
    "AE-LOCK-001",
    "AE-INTEREST-001",
    "AE-LO-001",
    "AE-LO-002",
    "AE-LO-EPOCH-001",
    "AE-HOOK-FEE-001",
    "AE-HOOK-REINVEST-001",
    "AE-NFT-CAP-001",
    "AE-DEBT-MARK-001",
    "AE-REPAIR-001",
    "AE-PEEL-001",
    "AE-REPAIR-SWAP-001",
}

REQUIRED_SCORING_IDS = {
    "SCORE-AGG-001",
    "SCORE-DELTA-001",
    "SCORE-DELTA-002",
    "SCORE-COST-001",
    "SCORE-COST-002",
    "SCORE-UNHEDGED-001",
}


def generate_protocol_release(root: str | Path = ".") -> dict:
    root = Path(root)
    fixture_paths = [
        root / "tests/golden/uniswap_v4_vectors.json",
        root / "tests/golden/aegis_vault_vectors.json",
        root / "tests/golden/scoring_vectors.json",
    ]
    golden = verify_paths(fixture_paths)
    foundry = verify_snapshot_paths(
        uniswap_fixture_path=root / "tests/golden/uniswap_v4_vectors.json",
        aegis_fixture_path=root / "tests/golden/aegis_vault_vectors.json",
        uniswap_snapshot_path=root / "reports/golden/foundry-uniswap-v4-reference.json",
        aegis_snapshot_path=root / "reports/golden/foundry-aegis-vault-reference.json",
    )
    checks = [
        _fixture_check(root / "tests/golden/uniswap_v4_vectors.json", REQUIRED_UNISWAP_IDS),
        _fixture_check(root / "tests/golden/aegis_vault_vectors.json", REQUIRED_AEGIS_IDS),
        _fixture_check(root / "tests/golden/scoring_vectors.json", REQUIRED_SCORING_IDS),
        {
            "name": "golden_regeneration",
            "status": golden["status"],
            "evidence_paths": [str(path) for path in fixture_paths],
            "errors": golden["errors"],
        },
        {
            "name": "foundry_snapshot_parity",
            "status": foundry["status"],
            "evidence_paths": foundry["checked"],
            "errors": foundry["errors"],
        },
    ]
    status = "pass" if all(check["status"] == "pass" for check in checks) else "fail"
    report = {
        "status": status,
        "fixture_version": RELEASE_VERSION,
        "checks": checks,
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "protocol-release.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (reports / "protocol-release.md").write_text(_markdown(report))
    return report


def _fixture_check(path: Path, required_ids: set[str]) -> dict:
    data = json.loads(path.read_text())
    ids = {vector["id"] for vector in data.get("vectors", [])}
    missing = sorted(required_ids - ids)
    extra = sorted(ids - required_ids)
    errors = []
    if data.get("fixture_version") != RELEASE_VERSION:
        errors.append({"field": "fixture_version", "expected": RELEASE_VERSION, "actual": data.get("fixture_version")})
    if missing:
        errors.append({"field": "vectors", "missing": missing})
    return {
        "name": path.name,
        "status": "pass" if not errors else "fail",
        "fixture_version": data.get("fixture_version"),
        "vector_count": len(ids),
        "required_vector_count": len(required_ids),
        "extra_vectors": extra,
        "evidence_paths": [str(path)],
        "errors": errors,
    }


def _markdown(report: dict) -> str:
    lines = ["# Protocol Release", "", f"Status: `{report['status']}`", f"Fixture version: `{report['fixture_version']}`", "", "| Check | Status | Evidence |", "|---|---|---|"]
    for check in report["checks"]:
        lines.append(f"| `{check['name']}` | {check['status']} | {', '.join(check.get('evidence_paths', []))} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    print(json.dumps(generate_protocol_release("."), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
