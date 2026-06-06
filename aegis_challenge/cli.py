from __future__ import annotations

import argparse
import json
from pathlib import Path

from .leaderboard import append_submission, submission_from_run
from .reports import generate_launch_readiness
from .reports.metrics_v2 import generate_metrics_v2, independent_review
from .runner import replay, run_strategy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aegis-vault")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("strategy")
    run_p.add_argument("--bundle", default="smoke")
    run_p.add_argument("--seed", type=int, default=1)
    run_p.add_argument("--out-dir", default="runs")
    replay_p = sub.add_parser("replay")
    replay_p.add_argument("path")
    explain_p = sub.add_parser("explain")
    explain_p.add_argument("path")
    explain_p.add_argument("--step", type=int, default=0)
    submit_p = sub.add_parser("submit")
    submit_p.add_argument("strategy")
    sub.add_parser("report")
    metrics_p = sub.add_parser("metrics-v2")
    metrics_p.add_argument("--run-benchmarks", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        result = run_strategy(args.strategy, args.bundle, args.seed, args.out_dir)
        print(json.dumps({"run_id": result["run_id"], "run_dir": result["run_dir"], "score": result["score"]["score_breakdown"]["scenario_score"]}, indent=2))
    elif args.cmd == "replay":
        events = replay(args.path)
        print(json.dumps({"events": len(events), "first_step": events[0]["step"] if events else None, "last_step": events[-1]["step"] if events else None}, indent=2))
    elif args.cmd == "explain":
        events = replay(args.path)
        event = next((e for e in events if e["step"] == args.step), None)
        print(json.dumps(event or {"error": "step not found"}, indent=2))
    elif args.cmd == "submit":
        result = run_strategy(args.strategy, "public_train", 1, "runs")
        submission = submission_from_run(result["run_dir"])
        leaderboard = append_submission(Path("runs"), submission)
        print(json.dumps({"submitted": True, "run_id": result["run_id"], "leaderboard_entries": len(leaderboard)}, indent=2))
    elif args.cmd == "report":
        print(json.dumps(generate_launch_readiness("."), indent=2))
    elif args.cmd == "metrics-v2":
        metrics = generate_metrics_v2(".", run_benchmarks=args.run_benchmarks)
        review = independent_review(".")
        print(json.dumps({"metrics": metrics["status"], "review": review["status"], "weighted_score": metrics["weighted_score"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
