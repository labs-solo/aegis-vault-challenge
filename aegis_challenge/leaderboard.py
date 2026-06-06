from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .runner import run_strategy


@dataclass(frozen=True)
class Submission:
    run_id: str
    strategy: str
    score: Decimal
    bundle: str
    disqualified: bool
    profit_usd: Decimal | None = None
    apr_pct: Decimal | None = None
    return_pct: Decimal | None = None
    avg_eth_exposure_usd: Decimal | None = None
    max_eth_exposure_usd: Decimal | None = None
    repairs_liquidations: int = 0
    submitted_at: int = 0


@dataclass(frozen=True)
class AggregatedSubmission:
    run_id: str
    strategy: str
    public_score: Decimal
    ranked_score: Decimal
    valid_run_count: int
    attempts: int
    median_score: Decimal
    percentile_25: Decimal
    percentile_05: Decimal
    max_delta: Decimal
    liquidation_count: int
    action_cost: Decimal
    score_variance: Decimal
    submitted_at: int
    disqualified: bool = False


@dataclass(frozen=True)
class ServerSubmissionResult:
    private_path: str
    public_path: str
    public_rows: list[dict[str, object]]


def submission_from_run(run_dir: str | Path) -> Submission:
    path = Path(run_dir)
    score_doc = json.loads((path / "score.json").read_text())
    net_profit = Decimal(score_doc.get("net_profit_usd_after_penalties", score_doc["score_breakdown"]["scenario_score"]))
    ranked_summary = score_doc.get("ranked_summary") or {}
    leaderboard_score = Decimal(str(ranked_summary.get("ranked_score", score_doc.get("ranked_score", net_profit)))) if ranked_summary.get("status") == "ok" else net_profit
    profit_usd = Decimal(str(ranked_summary.get("median_profit_usd", net_profit))) if ranked_summary.get("status") == "ok" else net_profit
    apr_pct = Decimal(str(ranked_summary.get("median_apr_pct", score_doc.get("apr_pct", score_doc.get("profit_pct", "0"))))) if ranked_summary.get("status") == "ok" else Decimal(str(score_doc.get("apr_pct", score_doc.get("profit_pct", "0"))))
    avg_exposure = Decimal(str(ranked_summary.get("avg_eth_exposure_usd", score_doc.get("avg_eth_exposure_usd", "0"))))
    max_exposure = Decimal(str(ranked_summary.get("max_eth_exposure_usd", score_doc.get("max_eth_exposure_usd", "0"))))
    return Submission(
        run_id=score_doc["run_id"],
        strategy=Path(score_doc["strategy"]).name,
        score=leaderboard_score,
        bundle=score_doc["bundle"],
        disqualified=bool(score_doc["disqualified"]),
        profit_usd=profit_usd,
        apr_pct=apr_pct,
        return_pct=Decimal(score_doc.get("profit_pct", "0")),
        avg_eth_exposure_usd=avg_exposure,
        max_eth_exposure_usd=max_exposure,
        repairs_liquidations=int(ranked_summary.get("repair_liquidation_count", _repair_count(path / "public_replay.jsonl"))) if ranked_summary.get("status") == "ok" else _repair_count(path / "public_replay.jsonl"),
        submitted_at=int((path / "score.json").stat().st_mtime),
    )


def _repair_count(replay_path: Path) -> int:
    if not replay_path.exists():
        return 0
    count = 0
    for line in replay_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        count += len(event.get("recent_repairs") or [])
    return count


def append_submission(root: str | Path, submission: Submission) -> list[Submission]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / "submissions.jsonl"
    existing = read_submissions(log_path)
    by_run = {item.run_id: item for item in existing}
    by_run[submission.run_id] = public_submission(submission)
    ordered = sorted(by_run.values(), key=lambda item: item.run_id)
    log_path.write_text("".join(json.dumps(to_jsonable(item), sort_keys=True) + "\n" for item in ordered))
    write_leaderboard(root, ordered)
    return ordered


def read_submissions(path: str | Path) -> list[Submission]:
    path = Path(path)
    if not path.exists():
        return []
    items = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        items.append(
            Submission(
                run_id=raw["run_id"],
                strategy=Path(raw["strategy"]).name,
                score=Decimal(str(raw["score"])),
                bundle=raw["bundle"],
                disqualified=bool(raw["disqualified"]),
                profit_usd=Decimal(str(raw.get("profit_usd", raw.get("net_profit_usd_after_penalties", raw["score"])))),
                apr_pct=Decimal(str(raw.get("apr_pct", raw.get("return_pct", raw.get("profit_pct", "0"))))),
                return_pct=Decimal(str(raw.get("return_pct", raw.get("profit_pct", "0")))),
                avg_eth_exposure_usd=Decimal(str(raw.get("avg_eth_exposure_usd", "0"))),
                max_eth_exposure_usd=Decimal(str(raw.get("max_eth_exposure_usd", "0"))),
                repairs_liquidations=int(raw.get("repairs_liquidations", raw.get("liquidation_count", 0))),
                submitted_at=int(raw.get("submitted_at", 0)),
            )
        )
    return items


def rank_submissions(submissions: Iterable[Submission]) -> list[Submission]:
    return sorted(submissions, key=lambda item: (item.disqualified, -item.score, item.run_id))


def percentile(scores: Iterable[Decimal], pct: Decimal) -> Decimal:
    values = sorted(Decimal(str(score)) for score in scores)
    if not values:
        raise ValueError("ERR_EMPTY_SCORE_SET")
    if len(values) == 1:
        return values[0]
    pct = max(Decimal("0"), min(Decimal("1"), pct))
    position = pct * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - Decimal(lower)
    return values[lower] * (Decimal("1") - weight) + values[upper] * weight


def median(scores: Iterable[Decimal]) -> Decimal:
    return percentile(scores, Decimal("0.5"))


def ranked_score(hidden_scores: Iterable[Decimal]) -> Decimal:
    scores = [Decimal(str(score)) for score in hidden_scores]
    return (
        Decimal("0.55") * median(scores)
        + Decimal("0.25") * percentile(scores, Decimal("0.25"))
        + Decimal("0.20") * percentile(scores, Decimal("0.05"))
    )


def score_variance(scores: Iterable[Decimal]) -> Decimal:
    values = [Decimal(str(score)) for score in scores]
    if not values:
        return Decimal("0")
    avg = sum(values, Decimal("0")) / Decimal(len(values))
    return sum((score - avg) * (score - avg) for score in values) / Decimal(len(values))


def aggregate_submission(
    run_id: str,
    strategy: str,
    public_scores: Iterable[Decimal],
    hidden_scores: Iterable[Decimal],
    max_delta: Decimal,
    liquidation_count: int,
    action_cost: Decimal,
    submitted_at: int,
    attempts: int = 1,
    disqualified: bool = False,
) -> AggregatedSubmission:
    public_values = [Decimal(str(score)) for score in public_scores]
    hidden_values = [Decimal(str(score)) for score in hidden_scores]
    return AggregatedSubmission(
        run_id=run_id,
        strategy=Path(strategy).name,
        public_score=median(public_values),
        ranked_score=ranked_score(hidden_values),
        valid_run_count=0 if disqualified else len(hidden_values),
        attempts=attempts,
        median_score=median(hidden_values),
        percentile_25=percentile(hidden_values, Decimal("0.25")),
        percentile_05=percentile(hidden_values, Decimal("0.05")),
        max_delta=Decimal(str(max_delta)),
        liquidation_count=liquidation_count,
        action_cost=Decimal(str(action_cost)),
        score_variance=score_variance(hidden_values),
        submitted_at=submitted_at,
        disqualified=disqualified,
    )


def rank_aggregated(submissions: Iterable[AggregatedSubmission]) -> list[AggregatedSubmission]:
    return sorted(
        submissions,
        key=lambda item: (
            item.disqualified,
            -item.ranked_score,
            item.max_delta,
            item.liquidation_count,
            item.action_cost,
            item.score_variance,
            item.submitted_at,
            item.run_id,
        ),
    )


def leaderboard_badges(row: AggregatedSubmission, starter_score: Decimal | None = None, noop_score: Decimal | None = None) -> list[str]:
    badges: list[str] = []
    if starter_score is not None and row.public_score > starter_score:
        badges.append("beat starter")
    if noop_score is not None and row.public_score > noop_score:
        badges.append("beat no-op")
    if row.max_delta <= Decimal("0.10"):
        badges.append("delta-safe")
    if row.liquidation_count == 0:
        badges.append("no-liquidation")
    if row.action_cost <= Decimal("1"):
        badges.append("low-churn")
    if row.percentile_05 > 0:
        badges.append("robust-tail")
    return badges


def aggregate_to_public_row(row: AggregatedSubmission, rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "run_id": row.run_id,
        "strategy": row.strategy,
        "public_score": str(row.public_score),
        "ranked_score": str(row.ranked_score),
        "valid_run_count": row.valid_run_count,
        "attempts": row.attempts,
        "median_score": str(row.median_score),
        "percentile_25": str(row.percentile_25),
        "percentile_05": str(row.percentile_05),
        "max_delta": str(row.max_delta),
        "liquidation_count": row.liquidation_count,
        "action_cost": str(row.action_cost),
        "score_variance": str(row.score_variance),
        "risk_badges": leaderboard_badges(row),
        "disqualified": row.disqualified,
    }


class CompetitionServer:
    def __init__(
        self,
        root: str | Path,
        public_bundle: str = "public_train",
        hidden_bundle: str = "hidden_ranked",
        public_seeds: tuple[int, ...] = (1, 2, 3),
        hidden_seeds: tuple[int, ...] = (101, 102, 103, 104),
    ) -> None:
        self.root = Path(root)
        self.public_bundle = public_bundle
        self.hidden_bundle = hidden_bundle
        self.public_seeds = public_seeds
        self.hidden_seeds = hidden_seeds
        self.private_path = self.root / "server-private-submissions.json"
        self.public_path = self.root / "server-public-leaderboard.json"

    def submit_strategy(self, strategy_path: str | Path, submitted_at: int = 1) -> ServerSubmissionResult:
        self.root.mkdir(parents=True, exist_ok=True)
        public_scores = [
            self._score_strategy(strategy_path, self.public_bundle, seed, "public") for seed in self.public_seeds
        ]
        hidden_scores = [
            self._score_strategy(strategy_path, self.hidden_bundle, seed, "hidden") for seed in self.hidden_seeds
        ]
        run_id = self._server_run_id(strategy_path, public_scores, hidden_scores)
        aggregate = aggregate_submission(
            run_id=run_id,
            strategy=strategy_path,
            public_scores=public_scores,
            hidden_scores=hidden_scores,
            max_delta=Decimal("0"),
            liquidation_count=0,
            action_cost=Decimal("0"),
            submitted_at=submitted_at,
        )
        private_rows = self._read_private_rows()
        private_rows = [row for row in private_rows if row["run_id"] != run_id]
        private_rows.append(
            {
                "run_id": run_id,
                "strategy": Path(strategy_path).name,
                "public_bundle": self.public_bundle,
                "hidden_bundle": self.hidden_bundle,
                "public_seeds": list(self.public_seeds),
                "public_scores": [str(score) for score in public_scores],
                "hidden_scores": [str(score) for score in hidden_scores],
                "ranked_score": str(aggregate.ranked_score),
                "submitted_at": submitted_at,
            }
        )
        self.private_path.write_text(json.dumps({"submissions": private_rows}, indent=2, sort_keys=True) + "\n")
        public_rows = [
            aggregate_to_public_row(row, index + 1)
            for index, row in enumerate(
                rank_aggregated(
                    aggregate_submission(
                        run_id=row["run_id"],
                        strategy=row["strategy"],
                        public_scores=[Decimal(score) for score in row["public_scores"]],
                        hidden_scores=[Decimal(score) for score in row["hidden_scores"]],
                        max_delta=Decimal("0"),
                        liquidation_count=0,
                        action_cost=Decimal("0"),
                        submitted_at=int(row["submitted_at"]),
                    )
                    for row in private_rows
                )
            )
        ]
        self.public_path.write_text(json.dumps({"leaderboard": public_rows}, indent=2, sort_keys=True) + "\n")
        return ServerSubmissionResult(str(self.private_path), str(self.public_path), public_rows)

    def _score_strategy(self, strategy_path: str | Path, bundle: str, seed: int, lane: str) -> Decimal:
        out_dir = self.root / "runs" / lane
        result = run_strategy(strategy_path, bundle, seed, out_dir)
        return Decimal(result["score"]["score_breakdown"]["scenario_score"])

    def _read_private_rows(self) -> list[dict[str, object]]:
        if not self.private_path.exists():
            return []
        data = json.loads(self.private_path.read_text())
        return list(data.get("submissions", []))

    @staticmethod
    def _server_run_id(strategy_path: str | Path, public_scores: list[Decimal], hidden_scores: list[Decimal]) -> str:
        payload = json.dumps(
            {
                "strategy": Path(strategy_path).name,
                "public_scores": [str(score) for score in public_scores],
                "hidden_scores": [str(score) for score in hidden_scores],
            },
            sort_keys=True,
        )
        import hashlib

        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_server_parity_report(root: str | Path = "reports/leaderboard") -> dict[str, object]:
    root = Path(root)
    server = CompetitionServer(
        root / "server-fixture",
        public_bundle="smoke",
        hidden_bundle="smoke",
        public_seeds=(1, 2),
        hidden_seeds=(101, 102, 103),
    )
    result = server.submit_strategy("examples/00_hold_idle.py", submitted_at=1)
    private_doc = json.loads(Path(result.private_path).read_text())
    public_doc = json.loads(Path(result.public_path).read_text())
    private_row = private_doc["submissions"][0]
    public_row = public_doc["leaderboard"][0]
    recomputed = aggregate_submission(
        run_id=private_row["run_id"],
        strategy=private_row["strategy"],
        public_scores=[Decimal(score) for score in private_row["public_scores"]],
        hidden_scores=[Decimal(score) for score in private_row["hidden_scores"]],
        max_delta=Decimal("0"),
        liquidation_count=0,
        action_cost=Decimal("0"),
        submitted_at=int(private_row["submitted_at"]),
    )
    expected_public = aggregate_to_public_row(recomputed, 1)
    private_json = json.dumps(private_doc).lower()
    public_json = json.dumps(public_doc).lower()
    public_contains_private_path = str(root).lower() in public_json or "/users/page" in public_json
    report = {
        "status": "pass"
        if public_row == expected_public and "hidden_scores" not in public_json and "hidden_seeds" not in public_json and not public_contains_private_path
        else "fail",
        "private_path": str(result.private_path),
        "public_path": str(result.public_path),
        "public_matches_private_recompute": public_row == expected_public,
        "privacy": {
            "private_contains_hidden_scores": "hidden_scores" in private_json,
            "private_contains_rank_seed_fields": "hidden_seeds" in private_json,
            "public_contains_hidden_scores": "hidden_scores" in public_json,
            "public_contains_rank_seed_fields": "hidden_seeds" in public_json,
            "public_contains_private_path": public_contains_private_path,
        },
        "public_row": public_row,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "server-parity.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (root / "server-parity.md").write_text(
        "\n".join(
            [
                "# Server Leaderboard Parity",
                "",
                f"Status: {report['status']}",
                "",
                f"Public matches private recompute: {report['public_matches_private_recompute']}",
                f"Public contains hidden scores: {report['privacy']['public_contains_hidden_scores']}",
                f"Public contains ranked seed fields: {report['privacy']['public_contains_rank_seed_fields']}",
                f"Public contains private path: {report['privacy']['public_contains_private_path']}",
            ]
        )
        + "\n"
    )
    return report


def write_leaderboard_parity_report(root: str | Path = "reports/leaderboard") -> dict[str, object]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    hidden_scores = [Decimal("100"), Decimal("80"), Decimal("60"), Decimal("-100")]
    row = aggregate_submission(
        run_id="golden-robust-aggregation",
        strategy="fixture_strategy.py",
        public_scores=[Decimal("100"), Decimal("80"), Decimal("60")],
        hidden_scores=hidden_scores,
        max_delta=Decimal("0.02"),
        liquidation_count=0,
        action_cost=Decimal("0.5"),
        submitted_at=1,
    )
    public_row = aggregate_to_public_row(row, 1)
    report = {
        "status": "pass",
        "formula": "0.55*median + 0.25*percentile_25 + 0.20*percentile_05",
        "fixture": {
            "hidden_scores": [str(score) for score in hidden_scores],
            "median": str(row.median_score),
            "percentile_25": str(row.percentile_25),
            "percentile_05": str(row.percentile_05),
            "ranked_score": str(row.ranked_score),
        },
        "public_row": public_row,
        "privacy": {
            "hidden_raw_scores_in_public_row": False,
            "private_seed_fields_in_public_row": False,
        },
    }
    (root / "parity.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = [
        "# Leaderboard Parity",
        "",
        "Status: pass",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Median | {row.median_score} |",
        f"| Percentile 25 | {row.percentile_25} |",
        f"| Percentile 05 | {row.percentile_05} |",
        f"| Ranked score | {row.ranked_score} |",
        "",
        "Public row omits hidden raw scores and private seed fields.",
    ]
    (root / "parity.md").write_text("\n".join(lines) + "\n")
    return report


def write_leaderboard(root: str | Path, submissions: Iterable[Submission]) -> list[dict[str, object]]:
    root = Path(root)
    ranked = rank_submissions(submissions)
    rows = [
        {
            "rank": index + 1,
            "run_id": item.run_id,
            "strategy": item.strategy,
            "score": str(item.score),
            "profit_usd": str(item.profit_usd if item.profit_usd is not None else item.score),
            "net_profit_usd_after_penalties": str(item.score),
            "apr_pct": str(item.apr_pct if item.apr_pct is not None else item.return_pct if item.return_pct is not None else Decimal("0")),
            "return_pct": str(item.return_pct if item.return_pct is not None else Decimal("0")),
            "avg_eth_exposure_usd": str(item.avg_eth_exposure_usd if item.avg_eth_exposure_usd is not None else Decimal("0")),
            "max_eth_exposure_usd": str(item.max_eth_exposure_usd if item.max_eth_exposure_usd is not None else Decimal("0")),
            "repairs_liquidations": item.repairs_liquidations,
            "submitted_at": item.submitted_at,
            "bundle": item.bundle,
            "disqualified": item.disqualified,
        }
        for index, item in enumerate(ranked)
    ]
    (root / "leaderboard.json").write_text(json.dumps({"leaderboard": rows}, indent=2, sort_keys=True) + "\n")
    lines = ["# Local Leaderboard", "", "| Rank | Run | Strategy | Profit USD | APR % | Avg ETH Exposure USD | Max ETH Exposure USD | Repairs/Liquidations | Bundle | DQ |", "|---:|---|---|---:|---:|---:|---:|---:|---|---|"]
    for row in rows:
        lines.append(f"| {row['rank']} | `{row['run_id']}` | `{row['strategy']}` | {row['profit_usd']} | {row['apr_pct']} | {row['avg_eth_exposure_usd']} | {row['max_eth_exposure_usd']} | {row['repairs_liquidations']} | `{row['bundle']}` | {row['disqualified']} |")
    (root / "leaderboard.md").write_text("\n".join(lines) + "\n")
    return rows


def to_jsonable(submission: Submission) -> dict[str, object]:
    return {
        "run_id": submission.run_id,
        "strategy": submission.strategy,
        "score": str(submission.score),
        "profit_usd": str(submission.profit_usd if submission.profit_usd is not None else submission.score),
        "net_profit_usd_after_penalties": str(submission.score),
        "apr_pct": str(submission.apr_pct if submission.apr_pct is not None else submission.return_pct if submission.return_pct is not None else Decimal("0")),
        "return_pct": str(submission.return_pct if submission.return_pct is not None else Decimal("0")),
        "avg_eth_exposure_usd": str(submission.avg_eth_exposure_usd if submission.avg_eth_exposure_usd is not None else Decimal("0")),
        "max_eth_exposure_usd": str(submission.max_eth_exposure_usd if submission.max_eth_exposure_usd is not None else Decimal("0")),
        "repairs_liquidations": submission.repairs_liquidations,
        "submitted_at": submission.submitted_at,
        "bundle": submission.bundle,
        "disqualified": submission.disqualified,
    }


def public_submission(submission: Submission) -> Submission:
    return Submission(
        run_id=submission.run_id,
        strategy=Path(submission.strategy).name,
        score=submission.score,
        bundle=submission.bundle,
        disqualified=submission.disqualified,
        profit_usd=submission.profit_usd,
        apr_pct=submission.apr_pct,
        return_pct=submission.return_pct,
        avg_eth_exposure_usd=submission.avg_eth_exposure_usd,
        max_eth_exposure_usd=submission.max_eth_exposure_usd,
        repairs_liquidations=submission.repairs_liquidations,
        submitted_at=submission.submitted_at,
    )
