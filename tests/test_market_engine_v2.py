import hashlib
import json
from pathlib import Path

from aegis_challenge.export_verifier import verify_run_export
from aegis_challenge.flow import scenario
from aegis_challenge.market_engine_v2 import audit_distribution, generate_market_path, hidden_seed_pack, random_practice_seed
from aegis_challenge.runner import run_strategy
from aegis_challenge.web_app import run_web_strategy, submit_web_run


STARTER = Path("examples/starter_strategy.py").read_text()


def test_market_engine_path_is_deterministic():
    first = generate_market_path(scenario("public_train", 7), 7)
    second = generate_market_path(scenario("public_train", 7), 7)
    assert first == second


def test_random_practice_seed_has_no_collision_in_100_attempts():
    seeds = [random_practice_seed() for _ in range(100)]
    assert len(set(seeds)) == 100
    assert all(seed >= 1_000_000 for seed in seeds)


def test_hidden_seed_pack_count_bounds_and_determinism():
    first = hidden_seed_pack(20, "test-pack")
    second = hidden_seed_pack(20, "test-pack")
    assert first == second
    assert len(first) == 20
    assert min(first) >= 2_000_000_000


def test_distribution_audit_passes_100_public_training_paths():
    report = audit_distribution(scenario, "public_train", range(1, 101))
    assert report["status"] == "pass", report
    assert report["gates"]["fano_factor"]
    assert report["gates"]["volume_autocorrelation"]
    assert report["gates"]["volume_day_in_base_band"]
    assert report["gates"]["trades_day_in_base_band"]


def test_run_export_includes_public_market_path_stats_without_fair_price(tmp_path):
    result = run_strategy("examples/00_hold_idle.py", "smoke", 1, tmp_path)
    run_dir = Path(result["run_dir"])
    verification = verify_run_export(run_dir)
    assert verification["status"] == "pass"
    assert (run_dir / "market_path_stats.json").exists()
    assert (run_dir / "market_path_stats.jsonl").exists()
    text = (run_dir / "market_path_stats.json").read_text().lower()
    assert "fair_price" not in text
    assert "hidden_fair" not in text
    rows = json.loads((run_dir / "market_path_stats.json").read_text())
    assert rows[0]["engine_version"].startswith("market-engine-v2")
    assert "trade_intensity" in rows[0]
    assert "stochastic_volatility" in rows[0]


def test_three_same_seed_reruns_have_identical_replay_and_market_hashes(tmp_path):
    hashes = []
    for index in range(3):
        result = run_strategy("examples/00_hold_idle.py", "smoke", 2, tmp_path / str(index))
        run_dir = Path(result["run_dir"])
        replay_hash = hashlib.sha256((run_dir / "public_replay.jsonl").read_bytes()).hexdigest()
        path_hash = hashlib.sha256((run_dir / "market_path_stats.jsonl").read_bytes()).hexdigest()
        zip_hash = hashlib.sha256((run_dir / "raw_simulation_export.zip").read_bytes()).hexdigest()
        hashes.append((replay_hash, path_hash, zip_hash))
    assert hashes[0] == hashes[1] == hashes[2]


def test_ranked_submission_reports_robustness_and_hides_seeds(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_RANKED_PATH_COUNT", "20")
    run = run_web_strategy(STARTER, "smoke", 1, tmp_path)
    submitted = submit_web_run(run["run_id"], tmp_path)
    assert submitted["status"] == "ok"
    summary = submitted["ranked_summary"]
    assert summary["status"] == "ok"
    assert summary["path_count"] == 20
    for field in [
        "ranked_score",
        "mean_score",
        "median_score",
        "p10_score",
        "p90_score",
        "max_drawdown_usd",
        "score_variance",
        "median_delta_band_time",
        "repair_liquidation_count",
        "disqualification_rate",
        "robustness_rank",
    ]:
        assert field in summary
    public_text = json.dumps(summary).lower()
    assert "hidden_seeds" not in public_text
    assert '"seed"' not in public_text
    private_path = tmp_path / "ranked-private" / f"{run['run_id']}.json"
    assert private_path.exists()
