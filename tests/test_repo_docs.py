from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(".")


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _links(markdown: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown)


def test_readme_is_first_class_repo_entrypoint():
    readme = _read("README.md")
    required = [
        "# AEGIS Vault Challenge",
        "100,000 USDC",
        "ETH/USDC",
        "Quickstart",
        "Contestant Flow",
        "Challenge Rules",
        "Strategy API",
        "Raw Simulation Data",
        "Repository Map",
        "Documentation",
        "Verification",
        "Security And Privacy",
        "web/docs.html",
        "docs/participant-guide.md",
        "docs/strategy-api.md",
        "docs/simulation-and-scoring.md",
        "docs/development.md",
    ]
    for text in required:
        assert text in readme


def test_docs_directory_has_core_guides():
    required_files = [
        "docs/README.md",
        "docs/participant-guide.md",
        "docs/strategy-api.md",
        "docs/simulation-and-scoring.md",
        "docs/development.md",
        "docs/x-auth-attempts.md",
    ]
    for path in required_files:
        assert (ROOT / path).exists(), path


def test_strategy_docs_cover_actions_state_and_hidden_info():
    docs = _read("docs/strategy-api.md")
    for action in [
        "BorrowL",
        "RepayL",
        "SwapExactIn",
        "MintRange",
        "IncreaseRange",
        "DecreaseRange",
        "CollectFees",
        "BurnRange",
        "PlaceLimitOrder",
        "CancelLimitOrder",
        "WithdrawLimitOrder",
        "DetachPosition",
    ]:
        assert action in docs
    for state in [
        "state.pool.dfm_surge_fee_pips",
        "state.vault.borrow_index",
        "state.vault.ltv_pips",
        "state.vault.delta_normalized",
        "state.eth_exposure_usd",
        "state.score_breakdown",
    ]:
        assert state in docs
    for boundary in ["Hidden fair price", "Hidden seeds", "Future flow", "Private runner state"]:
        assert boundary.lower() in docs.lower()


def test_simulation_docs_cover_scoring_exports_and_realism():
    docs = _read("docs/simulation-and-scoring.md")
    required = [
        "180 simulated days",
        "15 minutes",
        "seeded randomness",
        "Base-like WETH/USDC",
        "DFM BaseHook",
        "apr_pct",
        "net_profit_usd_after_penalties",
        "public_replay.jsonl",
        "trades.jsonl",
        "actions.jsonl",
        "debt_snapshots.jsonl",
        "period_stats",
    ]
    for text in required:
        assert text in docs


def test_markdown_links_point_to_existing_local_files():
    markdown_files = [
        "README.md",
        "docs/README.md",
        "docs/participant-guide.md",
        "docs/strategy-api.md",
        "docs/simulation-and-scoring.md",
        "docs/development.md",
        "examples/README.md",
    ]
    for path in markdown_files:
        source = ROOT / path
        for link in _links(source.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target = link.split("#", 1)[0]
            if not target:
                continue
            resolved = (source.parent / target).resolve()
            assert resolved.exists(), f"{path} has broken link {link}"
