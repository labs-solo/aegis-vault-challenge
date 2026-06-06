from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from .auth_attempts import (
    auth_status,
    auto_save_attempt,
    get_or_create_session,
    list_user_attempts,
    mark_run_started,
    mutate_attempt,
    owner_id,
    public_docs_security_summary,
    public_leaderboard as attempts_leaderboard,
    read_attempts,
    repair_count,
    run_permission,
    write_attempts,
)
from .flow import scenario
from .leaderboard import append_submission, percentile, ranked_score, score_variance, submission_from_run
from .market_engine_v2 import CALIBRATION_HASH, ENGINE_VERSION, hidden_pack_public, hidden_seed_pack, random_practice_seed
from .runner import ensure_raw_export, replay, run_strategy
from .sandbox import validate_strategy_source


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = ROOT / "runs" / "web"
STARTER_PATH = ROOT / "examples" / "starter_strategy.py"
DEFAULT_WEB_BUNDLE = "competition_6m"
DEFAULT_WEB_PACE_SECONDS = float(os.environ.get("AEGIS_WEB_PACE_SECONDS", "35"))
PROGRESS_SAMPLE_LIMIT = 720
RANKED_PACK_ID = os.environ.get("AEGIS_RANKED_PACK_ID", "ranked-v2-default")
RANKED_BUNDLE = os.environ.get("AEGIS_RANKED_BUNDLE", "hidden_ranked")
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_LOCK = threading.Lock()


def starter_strategy() -> dict[str, object]:
    return {"strategy": STARTER_PATH.read_text(), "path": str(STARTER_PATH)}


def public_leaderboard(run_root: str | Path = DEFAULT_RUN_ROOT) -> dict[str, object]:
    social = attempts_leaderboard(run_root)
    if social.get("leaderboard"):
        return social
    path = Path(run_root) / "leaderboard.json"
    if not path.exists():
        return {"leaderboard": []}
    return json.loads(path.read_text())


def run_web_strategy(
    source: str,
    bundle: str = DEFAULT_WEB_BUNDLE,
    seed: int = 1,
    run_root: str | Path = DEFAULT_RUN_ROOT,
    session: dict[str, Any] | None = None,
    strategy_name: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    run_root = Path(run_root)
    if session is not None:
        allowed = run_permission(session)
        if not allowed["allowed"]:
            return _blocked(allowed, started, run_root, session)
    strategy_path = _write_strategy_source(source, run_root)
    try:
        if session is not None:
            mark_run_started(run_root, session)
        result = run_strategy(strategy_path, bundle, seed, run_root, fail_fast_errors=True)
        run_dir = Path(result["run_dir"])
        score_doc = json.loads((run_dir / "score.json").read_text())
        events = replay(run_dir / "public_replay.jsonl")
        calibration = json.loads((run_dir / "calibration.json").read_text())
        status = "error" if score_doc.get("disqualified") else "ok"
        errors = list(score_doc.get("errors") or [])
        attempt = None
        if session is not None and not score_doc.get("disqualified"):
            attempt = auto_save_attempt(run_root, session, run_dir, source, strategy_name)
        return {
            "status": status,
            "kind": _error_kind(errors) if errors else None,
            "message": _error_message(errors) if errors else "Simulation complete.",
            "run_id": result["run_id"],
            "run_dir": str(run_dir),
            "bundle": bundle,
            "seed": seed,
            "score": score_doc,
            "replay": events,
            "calibration": calibration,
            "leaderboard": public_leaderboard(run_root),
            "attempt": attempt,
            "attempts": list_user_attempts(run_root, session)["attempts"] if session is not None else [],
            "auth": auth_status(run_root, session) if session is not None else None,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except SyntaxError as exc:
        return _failure("invalid_python", f"Invalid Python near line {exc.lineno}: {exc.msg}", started)
    except RuntimeError as exc:
        kind = _exception_kind(exc)
        return _failure(kind, _exception_message(kind), started)
    except Exception as exc:  # noqa: BLE001
        return _failure("simulator_error", f"Simulator error: {type(exc).__name__}", started)


def start_progressive_run(
    source: str,
    bundle: str = DEFAULT_WEB_BUNDLE,
    seed: int = 1,
    run_root: str | Path = DEFAULT_RUN_ROOT,
    pace_seconds: float | None = None,
    session: dict[str, Any] | None = None,
    strategy_name: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    run_root = Path(run_root)
    if session is not None:
        allowed = run_permission(session)
        if not allowed["allowed"]:
            return _blocked(allowed, started, run_root, session)
    strategy_path = _write_strategy_source(source, run_root)
    try:
        validation_errors = validate_strategy_source(strategy_path)
    except SyntaxError as exc:
        return _failure("invalid_python", f"Invalid Python near line {exc.lineno}: {exc.msg}", started)
    if validation_errors:
        return _failure(_error_kind(validation_errors), _error_message(validation_errors), started)

    scen = scenario(bundle, seed)
    job_id = uuid.uuid4().hex[:16]
    if session is not None:
        mark_run_started(run_root, session)
    job = {
        "status": "running",
        "job_id": job_id,
        "run_id": _run_id_for_path(strategy_path, bundle, seed),
        "bundle": bundle,
        "seed": seed,
        "message": "Running 180-day simulation.",
        "progress": _progress_doc(0, scen.steps, scen.step_length_seconds, bundle, seed),
        "replay": [],
        "score": None,
        "calibration": _calibration_preview(scen, bundle, seed),
        "leaderboard": public_leaderboard(run_root),
        "session_id": session["session_id"] if session is not None else None,
        "strategy_source": source,
        "strategy_name": strategy_name,
        "attempt": None,
        "attempts": list_user_attempts(run_root, session)["attempts"] if session is not None else [],
        "auth": auth_status(run_root, session) if session is not None else None,
        "duration_ms": 0,
        "started_at": time.perf_counter(),
        "cancel_requested": False,
    }
    with _JOB_LOCK:
        _JOBS[job_id] = job
    thread = threading.Thread(
        target=_run_progressive_job,
        args=(job_id, strategy_path, bundle, seed, run_root, DEFAULT_WEB_PACE_SECONDS if pace_seconds is None else pace_seconds, session, source, strategy_name),
        daemon=True,
    )
    thread.start()
    return _job_snapshot(job_id)


def get_progressive_run(job_id: str) -> dict[str, Any]:
    return _job_snapshot(job_id)


def cancel_progressive_run(job_id: str) -> dict[str, Any]:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {"status": "error", "kind": "missing_job", "message": "Run job not found."}
        if job["status"] == "running":
            job["cancel_requested"] = True
            job["message"] = "Cancelling simulation..."
        return _public_job(job)


def submit_web_run(run_id: str, run_root: str | Path = DEFAULT_RUN_ROOT) -> dict[str, Any]:
    started = time.perf_counter()
    run_root = Path(run_root)
    run_dir = run_root / run_id
    if not (run_dir / "score.json").exists():
        return _failure("missing_run", "Run a successful simulation before submitting.", started)
    score_doc = json.loads((run_dir / "score.json").read_text())
    if score_doc.get("disqualified"):
        return _failure("disqualified", "Fix strategy errors before submitting.", started)
    ranked_summary = evaluate_ranked_run(run_dir, run_root)
    leaderboard = append_submission(run_root, submission_from_run(run_dir))
    return {
        "status": "ok",
        "message": "Submission ranked across hidden market paths and added to the leaderboard.",
        "run_id": run_id,
        "ranked_summary": ranked_summary,
        "leaderboard": {"leaderboard": _leaderboard_rows(leaderboard)},
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def random_practice_path() -> dict[str, Any]:
    seed = random_practice_seed()
    return {
        "status": "ok",
        "bundle": "public_train",
        "seed": seed,
        "label": f"Random public practice path {seed}",
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
    }


def auth_context(cookie_header: str | None, run_root: str | Path = DEFAULT_RUN_ROOT) -> tuple[dict[str, Any], str | None]:
    return get_or_create_session(cookie_header, run_root)


def attempts_for_session(session: dict[str, Any], run_root: str | Path = DEFAULT_RUN_ROOT) -> dict[str, Any]:
    return list_user_attempts(run_root, session)


def attempt_action(session: dict[str, Any], action: str, payload: dict[str, Any], run_root: str | Path = DEFAULT_RUN_ROOT) -> dict[str, Any]:
    if action == "publish":
        _rank_attempt_before_publish(run_root, session, str(payload.get("attempt_id", "")))
    return mutate_attempt(
        run_root,
        session,
        str(payload.get("attempt_id", "")),
        action,
        strategy_name=payload.get("strategy_name"),
    )


def auth_public_status(session: dict[str, Any], run_root: str | Path = DEFAULT_RUN_ROOT) -> dict[str, Any]:
    return {"status": "ok", "auth": auth_status(run_root, session), "attempts": list_user_attempts(run_root, session)["attempts"], "leaderboard": public_leaderboard(run_root)}


def security_summary() -> dict[str, Any]:
    return {"status": "ok", **public_docs_security_summary()}


def raw_export_path(run_id: str, run_root: str | Path = DEFAULT_RUN_ROOT) -> Path | None:
    run_dir = Path(run_root) / run_id
    if not (run_dir / "score.json").exists():
        return None
    return ensure_raw_export(run_dir)


def ranked_path_count() -> int:
    raw = os.environ.get("AEGIS_RANKED_PATH_COUNT", "50")
    try:
        count = int(raw)
    except ValueError:
        count = 50
    return max(20, min(100, count))


def evaluate_ranked_run(run_dir: str | Path, run_root: str | Path = DEFAULT_RUN_ROOT) -> dict[str, Any]:
    run_dir = Path(run_dir)
    run_root = Path(run_root)
    summary_path = run_dir / "ranked_summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text())
    score_path = run_dir / "score.json"
    score_doc = json.loads(score_path.read_text())
    source_path = run_dir / "strategy_source.py"
    if not source_path.exists():
        return _ranked_unavailable("strategy_source_missing", "Strategy source was not saved for hidden ranked evaluation.")
    count = ranked_path_count()
    ranked_bundle = "smoke" if score_doc.get("bundle") == "smoke" else RANKED_BUNDLE
    seeds = hidden_seed_pack(count, RANKED_PACK_ID)
    private_root = run_root / "ranked-private" / score_doc["run_id"]
    private_root.mkdir(parents=True, exist_ok=True)
    per_path: list[dict[str, Any]] = []
    hidden_scores: list[Decimal] = []
    profits: list[Decimal] = []
    aprs: list[Decimal] = []
    avg_exposures: list[Decimal] = []
    max_exposures: list[Decimal] = []
    delta_band_times: list[Decimal] = []
    drawdowns: list[Decimal] = []
    repair_total = 0
    disqualified = 0
    for index, seed in enumerate(seeds):
        try:
            result = run_strategy(source_path, ranked_bundle, seed, private_root, fail_fast_errors=True)
            hidden_run_dir = Path(result["run_dir"])
            hidden_score = json.loads((hidden_run_dir / "score.json").read_text())
            events = replay(hidden_run_dir / "public_replay.jsonl")
            net_profit = Decimal(str(hidden_score.get("net_profit_usd_after_penalties", "0")))
            hidden_scores.append(net_profit)
            profits.append(net_profit)
            aprs.append(Decimal(str(hidden_score.get("apr_pct", "0") or "0")))
            avg_exposures.append(Decimal(str(hidden_score.get("avg_eth_exposure_usd", "0") or "0")))
            max_exposures.append(Decimal(str(hidden_score.get("max_eth_exposure_usd", "0") or "0")))
            delta_band_times.append(_delta_band_time(events))
            drawdowns.append(_max_drawdown_usd(events))
            repairs = repair_count(hidden_run_dir / "public_replay.jsonl")
            repair_total += repairs
            per_path.append(
                {
                    "path_index": index,
                    "seed": seed,
                    "run_id": result["run_id"],
                    "score": str(net_profit),
                    "apr_pct": str(hidden_score.get("apr_pct", "0")),
                    "avg_eth_exposure_usd": str(hidden_score.get("avg_eth_exposure_usd", "0")),
                    "max_eth_exposure_usd": str(hidden_score.get("max_eth_exposure_usd", "0")),
                    "repairs_liquidations": repairs,
                    "disqualified": bool(hidden_score.get("disqualified")),
                }
            )
            if hidden_score.get("disqualified"):
                disqualified += 1
        except Exception as exc:  # noqa: BLE001
            disqualified += 1
            per_path.append({"path_index": index, "seed": seed, "error": type(exc).__name__, "disqualified": True})
    if not hidden_scores:
        summary = _ranked_unavailable("no_valid_hidden_paths", "No hidden ranked paths completed.")
    else:
        rank_score = ranked_score(hidden_scores)
        variance = score_variance(hidden_scores)
        public_pack = hidden_pack_public(RANKED_PACK_ID, count)
        summary = {
            "status": "ok",
            "engine_version": ENGINE_VERSION,
            "calibration_hash": CALIBRATION_HASH,
            "ranked_bundle": ranked_bundle,
            "path_count": count,
            "hidden_pack": public_pack,
            "ranked_score": str(rank_score),
            "mean_score": str(_mean_decimal(hidden_scores)),
            "median_score": str(percentile(hidden_scores, Decimal("0.50"))),
            "p10_score": str(percentile(hidden_scores, Decimal("0.10"))),
            "p90_score": str(percentile(hidden_scores, Decimal("0.90"))),
            "score_variance": str(variance),
            "score_stddev": str(_sqrt_decimal(variance)),
            "score_coefficient_of_variation": str(_sqrt_decimal(variance) / max(abs(_mean_decimal(hidden_scores)), Decimal("1"))),
            "median_profit_usd": str(percentile(profits, Decimal("0.50"))),
            "p10_profit_usd": str(percentile(profits, Decimal("0.10"))),
            "median_apr_pct": str(percentile(aprs, Decimal("0.50"))),
            "p10_apr_pct": str(percentile(aprs, Decimal("0.10"))),
            "max_drawdown_usd": str(max(drawdowns, default=Decimal("0"))),
            "median_delta_band_time": str(percentile(delta_band_times, Decimal("0.50"))),
            "worst_decile_delta_band_time": str(percentile(delta_band_times, Decimal("0.10"))),
            "avg_eth_exposure_usd": str(_mean_decimal(avg_exposures)),
            "max_eth_exposure_usd": str(max(max_exposures, default=Decimal("0"))),
            "repair_liquidation_count": repair_total,
            "disqualification_rate": str(Decimal(disqualified) / Decimal(count)),
            "robustness_rank": "world_class" if percentile(hidden_scores, Decimal("0.10")) > 0 and percentile(delta_band_times, Decimal("0.10")) >= Decimal("0.90") else "needs_review",
        }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    private_doc = {
        "run_id": score_doc["run_id"],
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
        "ranked_bundle": ranked_bundle,
        "hidden_pack_id": RANKED_PACK_ID,
        "hidden_seeds": list(seeds),
        "per_path": per_path,
        "public_summary": summary,
    }
    (run_root / "ranked-private").mkdir(parents=True, exist_ok=True)
    (run_root / "ranked-private" / f"{score_doc['run_id']}.json").write_text(json.dumps(private_doc, indent=2, sort_keys=True) + "\n")
    score_doc["ranked_summary"] = summary
    if summary.get("status") == "ok":
        score_doc["ranked_score"] = summary["ranked_score"]
    score_path.write_text(json.dumps(score_doc, indent=2, sort_keys=True) + "\n")
    return summary


def _rank_attempt_before_publish(run_root: str | Path, session: dict[str, Any], attempt_id: str) -> None:
    run_root = Path(run_root)
    attempts = read_attempts(run_root)
    for item in attempts:
        if item.get("attempt_id") != attempt_id or item.get("owner_id") != owner_id(session):
            continue
        run_id = str(item.get("run_id", ""))
        run_dir = run_root / run_id
        if not (run_dir / "score.json").exists():
            return
        summary = evaluate_ranked_run(run_dir, run_root)
        item["ranked_summary"] = summary
        if summary.get("status") == "ok":
            item["public_profit_usd"] = item.get("profit_usd")
            item["ranked_score"] = summary.get("ranked_score")
            item["score"] = summary.get("ranked_score")
            item["profit_usd"] = summary.get("median_profit_usd")
            item["apr_pct"] = summary.get("median_apr_pct")
            item["avg_eth_exposure_usd"] = summary.get("avg_eth_exposure_usd")
            item["max_eth_exposure_usd"] = summary.get("max_eth_exposure_usd")
            item["repairs_liquidations"] = summary.get("repair_liquidation_count")
        write_attempts(run_root, attempts)
        return


def _ranked_unavailable(kind: str, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "kind": kind,
        "message": message,
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
    }


def _delta_band_time(events: list[dict[str, Any]]) -> Decimal:
    if not events:
        return Decimal("0")
    safe = 0
    for event in events:
        initial = Decimal(str(event.get("initial_balance_usdc", "100000") or "100000"))
        exposure = abs(Decimal(str(event.get("eth_exposure_usd", "0") or "0")))
        if exposure <= initial * Decimal("0.03"):
            safe += 1
    return Decimal(safe) / Decimal(len(events))


def _max_drawdown_usd(events: list[dict[str, Any]]) -> Decimal:
    high = Decimal("0")
    drawdown = Decimal("0")
    for event in events:
        profit = Decimal(str(event.get("net_profit_usd_after_penalties", "0") or "0"))
        high = max(high, profit)
        drawdown = max(drawdown, high - profit)
    return drawdown


def _mean_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _sqrt_decimal(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return Decimal(str(float(value) ** 0.5))


def _run_progressive_job(
    job_id: str,
    strategy_path: Path,
    bundle: str,
    seed: int,
    run_root: Path,
    pace_seconds: float,
    session: dict[str, Any] | None,
    strategy_source: str,
    strategy_name: str | None,
) -> None:
    scen = scenario(bundle, seed)
    samples: list[dict[str, Any]] = []
    chunk_steps = max(1, scen.steps // 180)
    started = time.perf_counter()

    def is_cancelled() -> bool:
        with _JOB_LOCK:
            job = _JOBS.get(job_id)
            return bool(job and job.get("cancel_requested"))

    def progress(event: dict[str, Any], completed_steps: int, total_steps: int, _scen) -> None:
        if is_cancelled():
            raise RuntimeError("ERR_CANCELLED")
        if completed_steps % chunk_steps != 0 and completed_steps != total_steps:
            return
        if pace_seconds > 0:
            target_elapsed = pace_seconds * completed_steps / total_steps
            sleep_for = target_elapsed - (time.perf_counter() - started)
            if sleep_for > 0:
                time.sleep(sleep_for)
        if is_cancelled():
            raise RuntimeError("ERR_CANCELLED")
        samples.append(event)
        if len(samples) > PROGRESS_SAMPLE_LIMIT:
            samples[:] = _sample_events(samples, PROGRESS_SAMPLE_LIMIT)
        with _JOB_LOCK:
            job = _JOBS[job_id]
            job["progress"] = _progress_doc(completed_steps, total_steps, scen.step_length_seconds, bundle, seed)
            job["replay"] = list(samples)
            job["message"] = f"Simulated through day {job['progress']['completed_days']:.1f} of {job['progress']['total_days']:.0f}."
            job["duration_ms"] = int((time.perf_counter() - started) * 1000)

    try:
        result = run_strategy(
            strategy_path,
            bundle,
            seed,
            run_root,
            progress_callback=progress,
            cancel_callback=is_cancelled,
            fail_fast_errors=True,
        )
        run_dir = Path(result["run_dir"])
        score_doc = json.loads((run_dir / "score.json").read_text())
        calibration = json.loads((run_dir / "calibration.json").read_text())
        full_events = replay(run_dir / "public_replay.jsonl")
        attempt = None
        attempts = []
        auth = None
        if session is not None and not score_doc.get("disqualified"):
            attempt = auto_save_attempt(run_root, session, run_dir, strategy_source, strategy_name)
            attempts = list_user_attempts(run_root, session)["attempts"]
            auth = auth_status(run_root, session)
        with _JOB_LOCK:
            job = _JOBS[job_id]
            job.update(
                {
                    "status": "complete",
                    "message": "Run complete. Inspect the six-month replay, then submit when ready.",
                    "run_id": result["run_id"],
                    "run_dir": str(run_dir),
                    "score": score_doc,
                    "replay": _sample_events(full_events, PROGRESS_SAMPLE_LIMIT),
                    "calibration": calibration,
                    "progress": _progress_doc(scen.steps, scen.steps, scen.step_length_seconds, bundle, seed),
                    "leaderboard": public_leaderboard(run_root),
                    "attempt": attempt,
                    "attempts": attempts,
                    "auth": auth,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )
    except RuntimeError as exc:
        kind = _exception_kind(exc)
        with _JOB_LOCK:
            job = _JOBS[job_id]
            job.update(
                {
                    "status": "cancelled" if kind == "cancelled" else "error",
                    "kind": kind,
                    "message": _exception_message(kind),
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )
    except Exception as exc:  # noqa: BLE001
        with _JOB_LOCK:
            job = _JOBS[job_id]
            job.update(
                {
                    "status": "error",
                    "kind": "simulator_error",
                    "message": f"Simulator error: {type(exc).__name__}",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )


def _write_strategy_source(source: str, run_root: Path) -> Path:
    source = source.replace("\r\n", "\n")
    digest = hashlib.sha256(source.encode()).hexdigest()[:16]
    strategy_dir = run_root / "strategies"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    path = strategy_dir / f"strategy_{digest}.py"
    path.write_text(source)
    return path


def _run_id_for_path(path: Path, bundle: str, seed: int) -> str:
    return hashlib.sha256(f"{path}:{bundle}:{seed}:{ENGINE_VERSION}:{CALIBRATION_HASH}".encode()).hexdigest()[:16]


def _calibration_preview(scen, bundle: str, seed: int) -> dict[str, Any]:
    simulated_days = (scen.steps * scen.step_length_seconds) / 86400
    return {
        "bundle": bundle,
        "seed": seed,
        "steps": scen.steps,
        "step_length_seconds": scen.step_length_seconds,
        "simulated_days": simulated_days,
        "hidden_horizon_label": scen.hidden_horizon_label,
        "regime_schedule": list(scen.regime_schedule),
        "market_engine": {
            "engine_version": ENGINE_VERSION,
            "calibration_hash": CALIBRATION_HASH,
        },
        "market": {
            "token0_symbol": scen.market.token0_symbol,
            "token1_symbol": scen.market.token1_symbol,
            "base_token": scen.market.base_token,
            "risk_token": scen.market.risk_token,
            "quote_token": scen.market.quote_token,
            "pool_pair": scen.market.pool_pair,
            "price_convention": scen.market.price_convention,
            "initial_price": str(scen.market.initial_price),
            "initial_price_usdc_per_eth": str(scen.market.initial_price),
            "initial_balance_usdc": str(scen.market.initial_cash_usdc + scen.market.initial_eth * scen.market.initial_price),
            "initial_cash_usdc": str(scen.market.initial_cash_usdc),
            "initial_eth": str(scen.market.initial_eth),
            "horizon_days": simulated_days,
        },
    }


def _progress_doc(completed_steps: int, total_steps: int, step_length_seconds: int, bundle: str, seed: int) -> dict[str, Any]:
    completed_seconds = completed_steps * step_length_seconds
    total_seconds = total_steps * step_length_seconds
    return {
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "step_length_seconds": step_length_seconds,
        "completed_days": completed_seconds / 86400,
        "total_days": total_seconds / 86400,
        "percent": 0 if total_steps <= 0 else completed_steps / total_steps * 100,
        "bundle": bundle,
        "seed": seed,
    }


def _sample_events(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(events) <= limit:
        return list(events)
    indexes = sorted({round(i * (len(events) - 1) / (limit - 1)) for i in range(limit)})
    return [events[index] for index in indexes]


def _job_snapshot(job_id: str) -> dict[str, Any]:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {"status": "error", "kind": "missing_job", "message": "Run job not found."}
        return _public_job(job)


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"cancel_requested", "started_at"}
    }


def _leaderboard_rows(submissions) -> list[dict[str, object]]:
    ranked = sorted(submissions, key=lambda item: (item.disqualified, -item.score, item.run_id))
    return [
        {
            "rank": index + 1,
            "run_id": item.run_id,
            "strategy": item.strategy,
            "score": str(item.score),
            "profit_usd": str(item.profit_usd if item.profit_usd is not None else item.score),
            "net_profit_usd_after_penalties": str(item.score),
            "apr_pct": str(item.apr_pct if item.apr_pct is not None else item.return_pct if item.return_pct is not None else 0),
            "return_pct": str(item.return_pct if item.return_pct is not None else 0),
            "avg_eth_exposure_usd": str(item.avg_eth_exposure_usd if item.avg_eth_exposure_usd is not None else 0),
            "max_eth_exposure_usd": str(item.max_eth_exposure_usd if item.max_eth_exposure_usd is not None else 0),
            "repairs_liquidations": item.repairs_liquidations,
            "submitted_at": item.submitted_at,
            "bundle": item.bundle,
            "disqualified": item.disqualified,
        }
        for index, item in enumerate(ranked)
    ]


def _failure(kind: str, message: str, started: float) -> dict[str, Any]:
    return {
        "status": "error",
        "kind": kind,
        "message": message,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "leaderboard": public_leaderboard(),
    }


def _blocked(allowed: dict[str, Any], started: float, run_root: Path, session: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "error",
        "kind": allowed.get("reason", "blocked"),
        "message": allowed.get("message", "Run blocked."),
        "cooldown": allowed.get("cooldown"),
        "auth": auth_status(run_root, session),
        "attempts": list_user_attempts(run_root, session)["attempts"],
        "leaderboard": public_leaderboard(run_root),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _error_kind(errors: list[str]) -> str:
    joined = " ".join(errors)
    if "ERR_FORBIDDEN" in joined:
        return "unsafe_strategy"
    if "ERR_TIMEOUT" in joined:
        return "timeout"
    if "ERR_STRATEGY_EXCEPTION" in joined:
        return "runtime_failure"
    return "strategy_error"


def _error_message(errors: list[str]) -> str:
    if not errors:
        return "Simulation complete."
    kind = _error_kind(errors)
    if kind == "unsafe_strategy":
        return "Unsafe strategy blocked. Remove forbidden imports or side effects."
    if kind == "timeout":
        return "Strategy timed out. Reduce loops or expensive work in on_step."
    if kind == "runtime_failure":
        return "Strategy raised an exception. Check on_start and on_step."
    return f"Strategy error: {', '.join(errors[:3])}"


def _exception_kind(exc: RuntimeError) -> str:
    text = str(exc)
    if "ERR_CANCELLED" in text:
        return "cancelled"
    if "ERR_FORBIDDEN" in text:
        return "unsafe_strategy"
    if "ERR_TIMEOUT" in text:
        return "timeout"
    if "ERR_STRATEGY_EXCEPTION" in text:
        return "runtime_failure"
    return "simulator_error"


def _exception_message(kind: str) -> str:
    if kind == "cancelled":
        return "Simulation cancelled. No leaderboard or final score was changed."
    if kind == "unsafe_strategy":
        return "Unsafe strategy blocked. Remove forbidden imports or side effects."
    if kind == "timeout":
        return "Strategy timed out. Reduce loops or expensive work in on_step."
    if kind == "runtime_failure":
        return "Strategy raised an exception. Check on_start and on_step."
    return "Simulator error. Review the strategy and try again."
