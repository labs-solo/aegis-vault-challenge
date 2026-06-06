import json
from decimal import Decimal
from pathlib import Path

from aegis_challenge.leaderboard import (
    CompetitionServer,
    Submission,
    aggregate_submission,
    aggregate_to_public_row,
    append_submission,
    percentile,
    rank_aggregated,
    rank_submissions,
    ranked_score,
    read_submissions,
    write_leaderboard_parity_report,
    write_server_parity_report,
)
from aegis_challenge.runner import run_strategy


def test_rank_submissions_orders_score_desc_and_dq_last():
    ranked = rank_submissions(
        [
            Submission("a", "a.py", Decimal("1"), "public_train", False),
            Submission("b", "b.py", Decimal("2"), "public_train", False),
            Submission("c", "c.py", Decimal("99"), "public_train", True),
        ]
    )

    assert [item.run_id for item in ranked] == ["b", "a", "c"]


def test_append_submission_writes_json_and_markdown(tmp_path):
    one = Submission("run1", "/tmp/alpha.py", Decimal("1.5"), "public_train", False)
    two = Submission("run2", "/tmp/beta.py", Decimal("2.5"), "public_train", False)

    append_submission(tmp_path, one)
    append_submission(tmp_path, two)
    append_submission(tmp_path, one)

    assert len(read_submissions(tmp_path / "submissions.jsonl")) == 2
    leaderboard = json.loads((tmp_path / "leaderboard.json").read_text())["leaderboard"]
    assert leaderboard[0]["run_id"] == "run2"
    assert leaderboard[0]["strategy"] == "beta.py"
    assert "/tmp" not in (tmp_path / "leaderboard.md").read_text()


def test_run_score_strategy_metadata_is_public_filename_only(tmp_path):
    result = run_strategy("examples/00_hold_idle.py", "smoke", 1, tmp_path)
    score = json.loads((Path(result["run_dir"]) / "score.json").read_text())

    assert score["strategy"] == "00_hold_idle.py"
    assert "/" not in score["strategy"]


def test_ranked_score_matches_spec_robust_aggregation_vector():
    hidden_scores = [Decimal("100"), Decimal("80"), Decimal("60"), Decimal("-100")]

    assert percentile(hidden_scores, Decimal("0.50")) == Decimal("70.0")
    assert percentile(hidden_scores, Decimal("0.25")) == Decimal("20.00")
    assert percentile(hidden_scores, Decimal("0.05")) == Decimal("-76.00")
    assert ranked_score(hidden_scores) == Decimal("28.3000")


def test_rank_aggregated_uses_spec_tie_breakers():
    early_low_risk = aggregate_submission(
        "a",
        "a.py",
        [Decimal("0")],
        [Decimal("10"), Decimal("10")],
        max_delta=Decimal("0.01"),
        liquidation_count=0,
        action_cost=Decimal("0.1"),
        submitted_at=2,
    )
    later_high_delta = aggregate_submission(
        "b",
        "b.py",
        [Decimal("0")],
        [Decimal("10"), Decimal("10")],
        max_delta=Decimal("0.02"),
        liquidation_count=0,
        action_cost=Decimal("0.1"),
        submitted_at=1,
    )

    assert [row.run_id for row in rank_aggregated([later_high_delta, early_low_risk])] == ["a", "b"]


def test_public_aggregate_row_omits_hidden_raw_scores_and_paths():
    row = aggregate_submission(
        "run",
        "/tmp/private/strategy.py",
        [Decimal("1")],
        [Decimal("100"), Decimal("-50")],
        max_delta=Decimal("0.02"),
        liquidation_count=0,
        action_cost=Decimal("0.5"),
        submitted_at=1,
    )

    public = aggregate_to_public_row(row, 1)

    assert public["strategy"] == "strategy.py"
    assert "hidden_scores" not in public
    assert "seed" not in json.dumps(public).lower()
    assert "/tmp" not in json.dumps(public)


def test_write_leaderboard_parity_report(tmp_path):
    report = write_leaderboard_parity_report(tmp_path)

    assert report["status"] == "pass"
    assert report["fixture"]["ranked_score"] == "28.3000"
    assert report["privacy"]["hidden_raw_scores_in_public_row"] is False
    assert report["privacy"]["private_seed_fields_in_public_row"] is False
    assert (tmp_path / "parity.json").exists()
    assert (tmp_path / "parity.md").exists()


def test_competition_server_keeps_hidden_scores_private(tmp_path):
    server = CompetitionServer(
        tmp_path,
        public_bundle="smoke",
        hidden_bundle="smoke",
        public_seeds=(1,),
        hidden_seeds=(101, 102),
    )

    result = server.submit_strategy("examples/00_hold_idle.py", submitted_at=7)
    private_doc = json.loads(Path(result.private_path).read_text())
    public_doc = json.loads(Path(result.public_path).read_text())
    public_text = json.dumps(public_doc).lower()

    assert private_doc["submissions"][0]["hidden_scores"]
    assert "hidden_seeds" not in json.dumps(private_doc).lower()
    assert "hidden_scores" not in public_text
    assert "hidden_seeds" not in public_text
    assert str(tmp_path) not in json.dumps(public_doc)
    assert public_doc["leaderboard"][0]["rank"] == 1


def test_write_server_parity_report(tmp_path):
    report = write_server_parity_report(tmp_path)

    assert report["status"] == "pass"
    assert report["public_matches_private_recompute"] is True
    assert report["privacy"]["private_contains_hidden_scores"] is True
    assert report["privacy"]["private_contains_rank_seed_fields"] is False
    assert report["privacy"]["public_contains_hidden_scores"] is False
    assert report["privacy"]["public_contains_rank_seed_fields"] is False
    assert report["privacy"]["public_contains_private_path"] is False
    assert (tmp_path / "server-parity.json").exists()
    assert (tmp_path / "server-parity.md").exists()
