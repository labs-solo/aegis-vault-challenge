from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Iterable

from aegis_challenge.flow import scenario
from aegis_challenge.runner import run_strategy

BENCHMARKS = [
    "benchmarks/00_noop.py",
    "examples/starter_strategy.py",
    "benchmarks/01_directional_long_eth.py",
    "benchmarks/02_directional_short_eth.py",
    "benchmarks/03_passive_wide_lp.py",
    "benchmarks/04_passive_narrow_lp.py",
    "benchmarks/05_lo_only_rebalancer.py",
    "benchmarks/06_borrow_heavy.py",
    "benchmarks/07_delta_neutral_heuristic.py",
]

CATEGORY_WEIGHTS = {
    "protocol_correctness": 15,
    "aegis_vault_correctness": 15,
    "market_realism_and_scenario_completeness": 15,
    "delta_neutral_strategy_validity": 15,
    "scoring_replay_and_leaderboard_integrity": 15,
    "contestant_workflow_and_ux": 15,
    "security_privacy_and_abuse_resistance": 10,
}


@dataclass(frozen=True)
class RunArtifacts:
    strategy: str
    bundle: str
    seed: int | None
    run_dir: Path
    replay_path: Path
    score_path: Path
    calibration_path: Path


def generate_metrics_v2(root: str | Path = ".", run_benchmarks: bool = True) -> dict:
    root = Path(root)
    benchmark_artifacts = run_benchmark_suite(root) if run_benchmarks else discover_benchmark_artifacts(root)
    scenario_artifacts = write_scenario_matrix(root)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)

    gates = hard_gates(root, benchmark_artifacts, scenario_artifacts)
    groups = category_scores(root, benchmark_artifacts, scenario_artifacts, gates)
    blockers = [gate["blocker"] for gate in gates if gate["status"] != "pass"]
    blockers.extend(group["blocker"] for group in groups if group["score"] < group["minimum_score"])
    weighted_score = sum(Decimal(group["score"]) * Decimal(CATEGORY_WEIGHTS[group["name"]]) for group in groups) / Decimal(sum(CATEGORY_WEIGHTS.values()))
    market_score = group_score(groups, "market_realism_and_scenario_completeness")
    delta_score = group_score(groups, "delta_neutral_strategy_validity")
    predictive_score = predictive_power_score(root, benchmark_artifacts)["score"]
    ux_score = group_score(groups, "contestant_workflow_and_ux")
    if weighted_score < Decimal("95"):
        blockers.append("weighted V2 score below 95")
    if market_score < 90:
        blockers.append("market realism score below 90")
    if delta_score < 90:
        blockers.append("delta strategy validity score below 90")
    if predictive_score < 90:
        blockers.append("predictive power score below 90")
    if ux_score < 90:
        blockers.append("UX score below 90")
    status = (
        "world_class_ready"
        if all(gate["status"] == "pass" for gate in gates)
        and weighted_score >= Decimal("95")
        and market_score >= 90
        and delta_score >= 90
        and predictive_score >= 90
        and ux_score >= 90
        and all(group["score"] >= 80 for group in groups)
        and not blockers
        else "not_ready"
    )
    report = {
        "status": status,
        "weighted_score": str(weighted_score.quantize(Decimal("0.01"))),
        "market_realism_score": market_score,
        "delta_strategy_validity_score": delta_score,
        "predictive_power_score": predictive_score,
        "ux_score": ux_score,
        "hard_gates": gates,
        "category_scores": groups,
        "benchmark_runs": [artifact_doc(a) for a in benchmark_artifacts],
        "scenario_matrix": [str(path) for path in scenario_artifacts],
        "predictive_power": predictive_power_score(root, benchmark_artifacts),
        "blockers": sorted(set(blockers)),
        "evidence_paths": evidence_paths(root, benchmark_artifacts),
    }
    (reports / "metrics-v2.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (reports / "metrics-v2.md").write_text(markdown(report))
    return report


def run_benchmark_suite(root: Path) -> list[RunArtifacts]:
    artifacts: list[RunArtifacts] = []
    out_root = root / "reports/benchmarks/v2"
    for strategy in BENCHMARKS:
        for bundle, seed in [("smoke", 1), ("public_train", 1), ("hidden_ranked", 101)]:
            result = run_strategy(root / strategy, bundle, seed, out_root / Path(strategy).stem)
            run_dir = Path(result["run_dir"])
            artifacts.append(RunArtifacts(strategy, bundle, seed, run_dir, run_dir / "public_replay.jsonl", run_dir / "score.json", run_dir / "calibration.json"))
    return artifacts


def discover_benchmark_artifacts(root: Path) -> list[RunArtifacts]:
    artifacts = []
    for calibration in (root / "reports/benchmarks/v2").glob("*/*/calibration.json"):
        run_dir = calibration.parent
        score = json.loads((run_dir / "score.json").read_text())
        calib = json.loads(calibration.read_text())
        artifacts.append(RunArtifacts(score.get("strategy", "unknown"), calib.get("bundle", "unknown"), calib.get("seed"), run_dir, run_dir / "public_replay.jsonl", run_dir / "score.json", calibration))
    return artifacts


def write_scenario_matrix(root: Path) -> list[Path]:
    scenario_dir = root / "reports/scenarios/v2"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    targets = [
        *[("public_train", seed) for seed in (1, 7, 11, 13, 15, 18)],
        *[("stress_train", seed) for seed in (101, 103, 105, 107)],
        *[("hidden_ranked", seed) for seed in (96, 97, 98, 99, 100, 101, 102, 103)],
    ]
    paths = []
    for bundle, seed in targets:
        scen = scenario(bundle, seed)
        path = scenario_dir / f"{bundle}-{seed}.json"
        path.write_text(json.dumps({
            "bundle": bundle,
            "seed": None if bundle == "hidden_ranked" else seed,
            "steps": scen.steps,
            "step_length_seconds": scen.step_length_seconds,
            "regime": scen.regime,
            "priority_model": scen.priority_model,
            "fee_model": scen.fee_model,
            "retail_lambda_per_step": str(scen.retail_lambda_per_step),
            "arbitrage_enabled": scen.arbitrage_enabled,
            "hidden_horizon_label": scen.hidden_horizon_label,
            "market": {
                "token0_symbol": scen.market.token0_symbol,
                "token1_symbol": scen.market.token1_symbol,
                "token0_decimals": scen.market.token0_decimals,
                "token1_decimals": scen.market.token1_decimals,
                "price_convention": scen.market.price_convention,
                "initial_price": str(scen.market.initial_price),
                "vault_initial_token0": str(scen.market.vault_initial_token0),
                "vault_initial_token1": str(scen.market.vault_initial_token1),
                "background_liquidity_l": scen.market.background_liquidity_l,
                "borrowable_market_equity_l": scen.market.borrowable_market_equity_l,
                "utilization_cap_pips": scen.market.utilization_cap_pips,
                "daily_volume_to_tvl_target": str(scen.market.daily_volume_to_tvl_target),
            },
        }, indent=2, sort_keys=True) + "\n")
        paths.append(path)
    return paths


def hard_gates(root: Path, artifacts: list[RunArtifacts], scenario_artifacts: list[Path]) -> list[dict]:
    protocol_release = read_json(root / "reports/protocol-release.json")
    pytest_xml = root / "reports/ci/pytest.xml"
    server_parity = root / "reports/leaderboard/server-parity.json"
    ux_trial = root / "reports/ux/participant-trial.md"
    a11y = root / "reports/ux/accessibility-audit.md"
    sample_calibrations = [read_json(a.calibration_path) for a in artifacts if a.calibration_path.exists()]
    scenario_calibrations = [read_json(path) for path in scenario_artifacts]
    all_calibrations = sample_calibrations + scenario_calibrations
    market_ok = any(canonical_market_ok(c) for c in all_calibrations)
    scenario_ok = scenario_coverage(all_calibrations)["hard_gate_pass"]
    replay_ok = bool(artifacts) and all(a.replay_path.exists() and a.score_path.exists() and score_matches_replay(a) for a in artifacts)
    hidden_ok = bool(artifacts) and all(not public_artifact_leaks(a) for a in artifacts)
    sandbox_ok = pytest_xml.exists() and "test_worker_timeout_fails_closed" in pytest_xml.read_text()
    ux_ok = ux_trial.exists() and "Status: pass" in ux_trial.read_text() and a11y.exists() and "Status: pass" in a11y.read_text()
    return [
        gate("canonical_real_market", market_ok, "canonical ETH/USDC market evidence missing", [str(a.calibration_path) for a in artifacts] + [str(p) for p in scenario_artifacts]),
        gate("uniswap_v4_parity", protocol_release.get("status") == "pass", "Uniswap v4 release parity missing", [str(root / "reports/protocol-release.json")]),
        gate("aegis_vault_parity", protocol_release.get("status") == "pass", "AEGIS vault release parity missing", [str(root / "reports/protocol-release.json")]),
        gate("full_scenario_engine", scenario_ok, "full scenario engine evidence incomplete", [str(a.calibration_path) for a in artifacts] + [str(p) for p in scenario_artifacts]),
        gate("replay_determinism_and_independent_scoring", replay_ok, "score/replay recomputation evidence incomplete", [str(a.replay_path) for a in artifacts]),
        gate("hidden_info_isolation", hidden_ok, "public artifact leaks hidden/private state", [str(a.replay_path) for a in artifacts]),
        gate("sandbox", sandbox_ok, "sandbox fail-closed evidence missing", [str(pytest_xml)]),
        gate("ux_critical_path", ux_ok, "UX critical path evidence missing", [str(ux_trial), str(a11y)]),
        gate("leaderboard_parity", server_parity.exists(), "server/local leaderboard parity evidence missing", [str(server_parity)]),
    ]


def category_scores(root: Path, artifacts: list[RunArtifacts], scenario_artifacts: list[Path], gates: list[dict]) -> list[dict]:
    protocol_score = 100 if gate_status(gates, "uniswap_v4_parity") else 60
    vault_score = 100 if gate_status(gates, "aegis_vault_parity") else 60
    market_detail = scenario_coverage([read_json(a.calibration_path) for a in artifacts if a.calibration_path.exists()] + [read_json(p) for p in scenario_artifacts])
    delta_detail = delta_validity(artifacts)
    scoring_score = 100 if gate_status(gates, "replay_determinism_and_independent_scoring") and gate_status(gates, "leaderboard_parity") else 70
    ux_score = ux_evidence_score(root)
    security_score = 100 if gate_status(gates, "sandbox") and gate_status(gates, "hidden_info_isolation") else 70
    return [
        group("protocol_correctness", protocol_score, "protocol evidence below release bar"),
        group("aegis_vault_correctness", vault_score, "AEGIS vault evidence below release bar"),
        group("market_realism_and_scenario_completeness", market_detail["score"], "market/scenario realism below V2 bar"),
        group("delta_neutral_strategy_validity", delta_detail["score"], "delta-neutral validity below V2 bar", delta_detail),
        group("scoring_replay_and_leaderboard_integrity", scoring_score, "scoring/replay/leaderboard integrity below V2 bar"),
        group("contestant_workflow_and_ux", ux_score, "contestant workflow or UX evidence below V2 bar"),
        group("security_privacy_and_abuse_resistance", security_score, "security/privacy evidence below V2 bar"),
    ]


def scenario_coverage(calibrations: list[dict]) -> dict:
    regimes = {c.get("regime") for c in calibrations}
    horizons = {c.get("steps") for c in calibrations if c.get("bundle") == "hidden_ranked"}
    fee_models = {c.get("fee_model") for c in calibrations}
    priority_models = {c.get("priority_model") for c in calibrations}
    required_regimes = {"calm", "volatile", "trend_up", "trend_down", "mean_reversion", "jump", "low_liquidity", "borrow_stress"}
    score = 40
    score += int(25 * len(regimes & required_regimes) / len(required_regimes))
    score += 15 if {720, 1440, 2880}.issubset(horizons) else int(15 * len(horizons & {720, 1440, 2880}) / 3)
    score += 10 if "aegis_dynamic" in fee_models else 0
    score += 10 if {"baseline_batch", "backrun_stress", "latency_stress"}.issubset(priority_models) else int(10 * len(priority_models & {"baseline_batch", "backrun_stress", "latency_stress"}) / 3)
    return {
        "score": min(100, score),
        "regimes": sorted(str(r) for r in regimes if r),
        "hidden_horizons": sorted(int(h) for h in horizons if h),
        "fee_models": sorted(str(f) for f in fee_models if f),
        "priority_models": sorted(str(p) for p in priority_models if p),
        "hard_gate_pass": required_regimes.issubset(regimes) and {720, 1440, 2880}.issubset(horizons) and "aegis_dynamic" in fee_models,
    }


def delta_validity(artifacts: list[RunArtifacts]) -> dict:
    rows = []
    for artifact in artifacts:
        events = read_replay(artifact.replay_path)
        if not events:
            continue
        deltas = [Decimal(str(e["vault"]["delta_normalized"])) for e in events if "vault" in e]
        prices = [Decimal(str(e["price"])) for e in events]
        scores = [Decimal(str(e["score"])) for e in events]
        beta = price_beta(prices, scores)
        rows.append({
            "strategy": artifact.strategy,
            "bundle": artifact.bundle,
            "max_delta": str(max(deltas) if deltas else Decimal("0")),
            "mean_delta": str(sum(deltas) / Decimal(len(deltas)) if deltas else Decimal("0")),
            "time_above_soft": sum(1 for d in deltas if d > Decimal("0.05")),
            "price_beta": str(beta),
            "final_score": str(scores[-1] if scores else Decimal("0")),
        })
    directional = [r for r in rows if "directional" in r["strategy"]]
    neutral = [r for r in rows if "delta_neutral" in r["strategy"] or "starter" in r["strategy"]]
    directional_penalized = all(Decimal(r["final_score"]) < Decimal("0") or abs(Decimal(r["price_beta"])) > Decimal("0.5") for r in directional) if directional else False
    neutral_delta_ok = all(Decimal(r["mean_delta"]) < Decimal("0.08") for r in neutral) if neutral else False
    score = 60 + (20 if directional_penalized else 0) + (20 if neutral_delta_ok else 0)
    return {"score": score, "rows": rows, "directional_penalized": directional_penalized, "neutral_delta_ok": neutral_delta_ok}


def predictive_power_score(root: Path, artifacts: list[RunArtifacts]) -> dict:
    by_strategy: dict[str, dict[str, Decimal]] = {}
    for artifact in artifacts:
        score_doc = read_json(artifact.score_path)
        value = Decimal(str(score_doc.get("score_breakdown", {}).get("scenario_score", "0")))
        by_strategy.setdefault(artifact.strategy, {})[artifact.bundle] = value
    paired = [(v.get("public_train"), v.get("hidden_ranked")) for v in by_strategy.values() if "public_train" in v and "hidden_ranked" in v]
    corr = spearman([p[0] for p in paired], [p[1] for p in paired]) if len(paired) >= 3 else Decimal("0")
    baseline_ok = baseline_order_ok(by_strategy)
    score = 60 + (20 if corr > 0 else 0) + (20 if baseline_ok else 0)
    return {"score": score, "spearman_public_hidden": str(corr), "baseline_order_ok": baseline_ok, "paired_strategy_count": len(paired)}


def independent_review(root: str | Path = ".") -> dict:
    root = Path(root)
    metrics_path = root / "reports/metrics-v2.json"
    metrics = read_json(metrics_path)
    artifacts = discover_benchmark_artifacts(root)
    scenario_artifacts = sorted((root / "reports/scenarios/v2").glob("*.json"))
    gates = hard_gates(root, artifacts, scenario_artifacts)
    groups = category_scores(root, artifacts, scenario_artifacts, gates)
    weighted_score = sum(Decimal(group["score"]) * Decimal(CATEGORY_WEIGHTS[group["name"]]) for group in groups) / Decimal(sum(CATEGORY_WEIGHTS.values()))
    market_score = group_score(groups, "market_realism_and_scenario_completeness")
    delta_score = group_score(groups, "delta_neutral_strategy_validity")
    predictive = predictive_power_score(root, artifacts)
    predictive_score = predictive["score"]
    ux_score = group_score(groups, "contestant_workflow_and_ux")
    blockers = [gate["blocker"] for gate in gates if gate["status"] != "pass"]
    blockers.extend(group["blocker"] for group in groups if group["score"] < group["minimum_score"])
    if not metrics_path.exists():
        blockers.append("reports/metrics-v2.json missing")
    if len(artifacts) < len(BENCHMARKS) * 3:
        blockers.append("benchmark evidence incomplete")
    if len(scenario_artifacts) < 18:
        blockers.append("scenario matrix evidence incomplete")
    if weighted_score < Decimal("95"):
        blockers.append("weighted V2 score below 95")
    if market_score < 90:
        blockers.append("market realism score below 90")
    if delta_score < 90:
        blockers.append("delta strategy validity score below 90")
    if predictive_score < 90:
        blockers.append("predictive power score below 90")
    if ux_score < 90:
        blockers.append("UX score below 90")
    if metrics:
        if metrics.get("weighted_score") != str(weighted_score.quantize(Decimal("0.01"))):
            blockers.append("metrics-v2 weighted score inconsistent with independent recomputation")
        if metrics.get("predictive_power_score") != predictive_score:
            blockers.append("metrics-v2 predictive score inconsistent with independent recomputation")
        if metrics.get("status") == "world_class_ready" and blockers:
            blockers.append("metrics-v2 status overclaims readiness")
    status = (
        "world_class_ready"
        if all(gate["status"] == "pass" for gate in gates)
        and weighted_score >= Decimal("95")
        and market_score >= 90
        and delta_score >= 90
        and predictive_score >= 90
        and ux_score >= 90
        and all(group["score"] >= 80 for group in groups)
        and not blockers
        else "not_ready"
    )
    report = {
        "status": status,
        "source_metrics": str(metrics_path),
        "review_method": "recomputed_from_persisted_artifacts",
        "hard_gates": gates,
        "category_scores": groups,
        "weighted_score": str(weighted_score.quantize(Decimal("0.01"))),
        "predictive_power": predictive,
        "blockers": sorted(set(blockers)),
        "evidence_paths": evidence_paths(root, artifacts),
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "independent-metrics-review.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (reports / "independent-metrics-review.md").write_text(review_markdown(report))
    return report


def gate(name: str, ok: bool, blocker: str, evidence_paths: list[str]) -> dict:
    return {"name": name, "status": "pass" if ok else "fail", "blocker": "" if ok else blocker, "evidence_paths": evidence_paths}


def group(name: str, score: int, blocker: str, detail: dict | None = None) -> dict:
    return {"name": name, "score": score, "minimum_score": 80, "blocker": "" if score >= 80 else blocker, "detail": detail or {}}


def gate_status(gates: list[dict], name: str) -> bool:
    return any(g["name"] == name and g["status"] == "pass" for g in gates)


def group_score(groups: list[dict], name: str) -> int:
    return next((int(g["score"]) for g in groups if g["name"] == name), 0)


def canonical_market_ok(calibration: dict) -> bool:
    market = calibration.get("market", {})
    return (
        market.get("token0_symbol") == "ETH"
        and market.get("token1_symbol") == "USDC"
        and market.get("token0_decimals") == 18
        and market.get("token1_decimals") == 6
        and Decimal(str(market.get("initial_price", "0"))) > Decimal("100")
        and int(market.get("background_liquidity_l", 0)) > 0
        and int(market.get("borrowable_market_equity_l", 0)) > 0
    )


def score_matches_replay(artifact: RunArtifacts) -> bool:
    events = read_replay(artifact.replay_path)
    score_doc = read_json(artifact.score_path)
    if not events or not score_doc:
        return False
    return Decimal(str(events[-1]["score"])) == Decimal(str(score_doc.get("score_breakdown", {}).get("scenario_score", "NaN")))


def public_artifact_leaks(artifact: RunArtifacts) -> bool:
    text = artifact.replay_path.read_text() if artifact.replay_path.exists() else ""
    return any(token in text.lower() for token in ["hidden_fair", "hidden_seed", '"seed"', "future_flow", "private"])


def ux_evidence_score(root: Path) -> int:
    checks = [
        root / "reports/ux/participant-trial.md",
        root / "reports/ux/accessibility-audit.md",
        root / "reports/ux/playwright-smoke.md",
        root / "reports/screenshots/desktop-console.png",
        root / "reports/screenshots/mobile-console.png",
    ]
    return int(100 * sum(1 for path in checks if path.exists()) / len(checks))


def read_replay(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def price_beta(prices: list[Decimal], scores: list[Decimal]) -> Decimal:
    if len(prices) < 3 or len(prices) != len(scores):
        return Decimal("0")
    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] != 0]
    pnl = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
    if len(returns) != len(pnl) or not returns:
        return Decimal("0")
    mean_r = sum(returns) / Decimal(len(returns))
    mean_p = sum(pnl) / Decimal(len(pnl))
    var = sum((r - mean_r) * (r - mean_r) for r in returns)
    if var == 0:
        return Decimal("0")
    cov = sum((returns[i] - mean_r) * (pnl[i] - mean_p) for i in range(len(returns)))
    return cov / var


def spearman(left: Iterable[Decimal | None], right: Iterable[Decimal | None]) -> Decimal:
    pairs = [(l, r) for l, r in zip(left, right) if l is not None and r is not None]
    if len(pairs) < 3:
        return Decimal("0")
    lr = ranks([p[0] for p in pairs])
    rr = ranks([p[1] for p in pairs])
    return pearson(lr, rr)


def ranks(values: list[Decimal]) -> list[Decimal]:
    order = sorted((value, idx) for idx, value in enumerate(values))
    out = [Decimal("0")] * len(values)
    for rank, (_, idx) in enumerate(order, start=1):
        out[idx] = Decimal(rank)
    return out


def pearson(left: list[Decimal], right: list[Decimal]) -> Decimal:
    ml = Decimal(str(mean(left)))
    mr = Decimal(str(mean(right)))
    cov = sum((left[i] - ml) * (right[i] - mr) for i in range(len(left)))
    vl = sum((v - ml) * (v - ml) for v in left)
    vr = sum((v - mr) * (v - mr) for v in right)
    if vl == 0 or vr == 0:
        return Decimal("0")
    return cov / (vl.sqrt() * vr.sqrt())


def baseline_order_ok(by_strategy: dict[str, dict[str, Decimal]]) -> bool:
    by_name = {Path(strategy).name: bundles for strategy, bundles in by_strategy.items()}
    noop = by_name.get("00_noop.py", {}).get("public_train")
    starter = by_name.get("starter_strategy.py", {}).get("public_train")
    strong = by_name.get("07_delta_neutral_heuristic.py", {}).get("public_train")
    return noop is not None and starter is not None and strong is not None and noop <= starter <= strong


def artifact_doc(artifact: RunArtifacts) -> dict:
    return {
        "strategy": artifact.strategy,
        "bundle": artifact.bundle,
        "seed": artifact.seed,
        "run_dir": str(artifact.run_dir),
        "replay_path": str(artifact.replay_path),
        "score_path": str(artifact.score_path),
        "calibration_path": str(artifact.calibration_path),
    }


def evidence_paths(root: Path, artifacts: list[RunArtifacts]) -> list[str]:
    paths = [
        root / "reports/protocol-release.json",
        root / "reports/leaderboard/server-parity.json",
        root / "reports/ux/participant-trial.md",
        root / "reports/ux/accessibility-audit.md",
    ]
    paths.extend(a.replay_path for a in artifacts)
    paths.extend(a.score_path for a in artifacts)
    paths.extend(a.calibration_path for a in artifacts)
    return [str(path) for path in paths if path.exists()]


def markdown(report: dict) -> str:
    lines = [
        "# Metrics V2",
        "",
        f"Status: `{report['status']}`",
        f"Weighted score: `{report['weighted_score']}`",
        "",
        "## Hard Gates",
        "",
        "| Gate | Status | Blocker |",
        "|---|---|---|",
    ]
    for gate_doc in report["hard_gates"]:
        lines.append(f"| `{gate_doc['name']}` | {gate_doc['status']} | {gate_doc['blocker']} |")
    lines.extend(["", "## Category Scores", "", "| Category | Score |", "|---|---:|"])
    for group_doc in report["category_scores"]:
        lines.append(f"| `{group_doc['name']}` | {group_doc['score']} |")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {b}" for b in report["blockers"])
    return "\n".join(lines) + "\n"


def review_markdown(report: dict) -> str:
    lines = [
        "# Independent Metrics Review",
        "",
        f"Status: `{report['status']}`",
        f"Source metrics: `{report['source_metrics']}`",
        f"Weighted score: `{report['weighted_score']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {b}" for b in report["blockers"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    generate_metrics_v2(".")
    independent_review(".")
