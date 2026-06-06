from __future__ import annotations

import json
from decimal import Decimal

from aegis_challenge.leaderboard import percentile, ranked_score
from aegis_challenge.scoring import action_cost, delta_penalty, score
from aegis_challenge.vault import Vault


FIXTURE_VERSION = "aegis-vault-challenge-v1"


def build_vectors() -> dict:
    idle_unhedged_score = score(
        Vault(idle0=Decimal("100"), idle1=Decimal("100")),
        Decimal("1"),
        Decimal("200"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )
    hidden_scores = [Decimal("100"), Decimal("80"), Decimal("60"), Decimal("-100")]
    return {
        "fixture_version": FIXTURE_VERSION,
        "generator": {
            "name": "aegis_challenge.reports.generate_scoring_vectors",
            "rounding_policy": "python-decimal-reference-subset",
        },
        "vectors": [
            {
                "id": "SCORE-AGG-001",
                "input": {"hidden_scores": ["100", "80", "60", "-100"]},
                "expected": {
                    "median": str(percentile(hidden_scores, Decimal("0.50"))),
                    "percentile_25": str(percentile(hidden_scores, Decimal("0.25"))),
                    "percentile_05": str(percentile(hidden_scores, Decimal("0.05"))),
                    "ranked_score": str(ranked_score(hidden_scores)),
                },
                "source": "aegis_challenge.leaderboard.ranked_score robust aggregation",
            },
            {
                "id": "SCORE-DELTA-001",
                "input": {"initial_equity": "100000", "delta_normalized": "0.03"},
                "expected": {"delta_penalty": str(delta_penalty(Decimal("100000"), Decimal("0.03")))},
                "source": "aegis_challenge.scoring.delta_penalty neutral band",
            },
            {
                "id": "SCORE-DELTA-002",
                "input": {"initial_equity": "100000", "delta_normalized": "0.08"},
                "expected": {"delta_penalty": str(delta_penalty(Decimal("100000"), Decimal("0.08")))},
                "source": "aegis_challenge.scoring.delta_penalty quadratic excess",
            },
            {
                "id": "SCORE-COST-001",
                "input": {"action_name": "SwapExactIn", "ticks_crossed": 3},
                "expected": {"action_cost": str(action_cost("SwapExactIn", 3))},
                "source": "aegis_challenge.scoring.action_cost tick crossing",
            },
            {
                "id": "SCORE-COST-002",
                "input": {"action_name": "PlaceLimitOrder", "ticks_crossed": 0},
                "expected": {"action_cost": str(action_cost("PlaceLimitOrder", 0))},
                "source": "aegis_challenge.scoring.action_cost limit order",
            },
            {
                "id": "SCORE-UNHEDGED-001",
                "input": {"idle0": "100", "idle1": "100", "price": "1", "initial_equity": "200"},
                "expected": {
                    "raw_pnl": str(idle_unhedged_score.raw_pnl),
                    "scenario_score": str(idle_unhedged_score.scenario_score),
                    "delta_penalty": str(idle_unhedged_score.delta_penalty),
                    "action_costs": str(idle_unhedged_score.action_costs),
                },
                "source": "aegis_challenge.scoring.score idle inventory delta penalty",
            },
        ],
    }


def main() -> int:
    print(json.dumps(build_vectors(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
