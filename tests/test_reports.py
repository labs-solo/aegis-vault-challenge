import json
from pathlib import Path

from aegis_challenge.reports import generate_launch_readiness
from aegis_challenge.reports.generate_aegis_vault_vectors import build_vectors as build_aegis_vectors
from aegis_challenge.reports.generate_scoring_vectors import build_vectors
from aegis_challenge.reports.generate_uniswap_v4_vectors import build_vectors as build_uniswap_vectors
from aegis_challenge.reports.verify_foundry_snapshots import verify_snapshot_paths
from aegis_challenge.reports.verify_golden import verify_paths


def test_report_status_derives_from_v2_metrics_and_review():
    report = generate_launch_readiness(".")
    metrics = json.loads(Path("reports/metrics-v2.json").read_text())
    review = json.loads(Path("reports/independent-metrics-review.json").read_text())
    expected = "world_class_ready" if metrics["status"] == "world_class_ready" and review["status"] == "world_class_ready" else "not_ready"
    assert report["status"] == expected
    assert report["metrics_version"] == "v2"
    assert any(gate["name"] == "full_scenario_engine" for gate in report["hard_gates"])


def test_scoring_vector_generator_matches_checked_in_fixture():
    generated = build_vectors()
    checked_in = json.loads(Path("tests/golden/scoring_vectors.json").read_text())
    assert generated == checked_in


def test_protocol_vector_generators_match_checked_in_fixtures():
    assert build_uniswap_vectors() == json.loads(Path("tests/golden/uniswap_v4_vectors.json").read_text())
    assert build_aegis_vectors() == json.loads(Path("tests/golden/aegis_vault_vectors.json").read_text())


def test_golden_verifier_accepts_current_reference_subset():
    result = verify_paths([
        "tests/golden/uniswap_v4_vectors.json",
        "tests/golden/aegis_vault_vectors.json",
        "tests/golden/scoring_vectors.json",
    ])
    assert result["status"] == "pass"
    assert not result["errors"]


def test_foundry_reference_snapshots_match_checked_in_fixture_subset():
    result = verify_snapshot_paths()
    assert result["status"] == "pass"
    assert not result["errors"]
