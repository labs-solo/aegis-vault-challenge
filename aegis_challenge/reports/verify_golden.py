from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from aegis_challenge.reports.generate_aegis_vault_vectors import build_vectors as build_aegis_vectors
from aegis_challenge.reports.generate_scoring_vectors import build_vectors as build_scoring_vectors
from aegis_challenge.reports.generate_uniswap_v4_vectors import build_vectors as build_uniswap_vectors


def verify_paths(paths: list[str | Path]) -> dict:
    checked: list[dict] = []
    errors: list[dict] = []
    for raw_path in paths:
        path = Path(raw_path)
        data = json.loads(path.read_text())
        verifier = verifier_for(path.name)
        if verifier is None:
            errors.append({"path": str(path), "error": "no verifier for fixture"})
            continue
        fixture_errors = verifier(data)
        checked.append({
            "path": str(path),
            "fixture_version": data.get("fixture_version"),
            "vectors": len(data.get("vectors", [])),
        })
        errors.extend({"path": str(path), **error} for error in fixture_errors)
    return {"status": "pass" if not errors else "fail", "checked": checked, "errors": errors}


def verifier_for(name: str) -> Callable[[dict], list[dict]] | None:
    return {
        "uniswap_v4_vectors.json": verify_uniswap_v4,
        "aegis_vault_vectors.json": verify_aegis_vault,
        "scoring_vectors.json": verify_scoring,
    }.get(name)


def verify_uniswap_v4(data: dict) -> list[dict]:
    return verify_against_generated(data, build_uniswap_vectors())


def verify_aegis_vault(data: dict) -> list[dict]:
    return verify_against_generated(data, build_aegis_vectors())


def verify_scoring(data: dict) -> list[dict]:
    return verify_against_generated(data, build_scoring_vectors())


def verify_against_generated(data: dict, generated: dict) -> list[dict]:
    expected_vectors = {vector["id"]: vector for vector in generated["vectors"]}
    actual_vectors = {vector["id"]: vector for vector in data.get("vectors", [])}
    errors: list[dict] = []
    if data.get("fixture_version") != generated.get("fixture_version"):
        errors.append({"field": "fixture_version", "expected": generated.get("fixture_version"), "actual": data.get("fixture_version")})
    if data.get("generator") != generated.get("generator"):
        errors.append({"field": "generator", "expected": generated.get("generator"), "actual": data.get("generator")})
    for vector_id, expected in expected_vectors.items():
        actual = actual_vectors.get(vector_id)
        if actual is None:
            errors.append({"vector": vector_id, "error": "missing vector"})
            continue
        if actual != expected:
            errors.append({"vector": vector_id, "error": "mismatch", "expected": expected, "actual": actual})
    extra = sorted(set(actual_vectors) - set(expected_vectors))
    errors.extend({"vector": vector_id, "error": "unexpected vector"} for vector_id in extra)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aegis_challenge.reports.verify_golden")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    result = verify_paths(args.paths)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
