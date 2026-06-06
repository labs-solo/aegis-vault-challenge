from __future__ import annotations

import json
from pathlib import Path

from .metrics_v2 import generate_metrics_v2, independent_review


def generate_launch_readiness(root: str | Path = ".", run_benchmarks: bool = False) -> dict:
    root = Path(root)
    metrics = generate_metrics_v2(root, run_benchmarks=run_benchmarks)
    review = independent_review(root)
    weighted = metrics.get("weighted_score", "0")
    report = {
        "status": "world_class_ready" if metrics["status"] == "world_class_ready" and review["status"] == "world_class_ready" else "not_ready",
        "score": float(weighted),
        "engine_version": "0.2.0-v2",
        "scenario_bundle_version": "v2-real-market",
        "metrics_version": "v2",
        "hard_gates": metrics["hard_gates"],
        "metric_groups": metrics["category_scores"],
        "blockers": sorted(set(metrics.get("blockers", []) + review.get("blockers", []))),
        "non_blocking_risks": [],
        "source_reports": [
            str(root / "reports/metrics-v2.json"),
            str(root / "reports/independent-metrics-review.json"),
        ],
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "launch-readiness.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (reports / "launch-readiness.md").write_text(markdown(report))
    return report


def markdown(report: dict) -> str:
    lines = [
        "# Launch Readiness",
        "",
        f"Status: `{report['status']}`",
        f"Score: `{report['score']}`",
        "Metric source: `V2`",
        "",
        "## Hard Gates",
        "",
        "| Gate | Status | Blocker |",
        "|---|---|---|",
    ]
    for gate_doc in report["hard_gates"]:
        lines.append(f"| `{gate_doc['name']}` | {gate_doc['status']} | {gate_doc.get('blocker', '')} |")
    lines.extend(["", "## Metric Groups", "", "| Group | Score |", "|---|---:|"])
    for group in report["metric_groups"]:
        lines.append(f"| `{group['name']}` | {group['score']} |")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {b}" for b in report["blockers"])
    lines.extend(["", "## Source Reports", ""])
    lines.extend(f"- `{p}`" for p in report["source_reports"])
    return "\n".join(lines) + "\n"
