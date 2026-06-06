from __future__ import annotations

import html
import re
from pathlib import Path
from typing import get_args

from aegis_challenge import api


DOC_PATH = Path("web/docs.html")
INDEX_PATH = Path("web/index.html")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(fragment))).strip()


def _ids(markup: str) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', markup))


def test_docs_academy_exists_and_is_linked_from_app():
    docs = _read(DOC_PATH)
    index = _read(INDEX_PATH)
    required_docs_text = [
        "AEGIS Strategy Academy",
        "Win in USD without making an ETH direction bet.",
        "100,000 USDC",
        "0 ETH",
        "ETH/USDC",
        "180 simulated days",
        "DFM BaseHook fees",
        "L-unit borrow/repay",
        "borrow index",
        "collateral floor",
        "LTV",
        "repairs",
        "ranked submissions",
        "hidden seeded paths",
        "What can my strategy do?",
    ]
    for text in required_docs_text:
        assert text in docs
    assert 'href="docs.html"' in index
    assert "Open Strategy Academy" in index
    assert "What can my strategy do?" in index


def test_every_action_has_complete_reference_card():
    docs = _read(DOC_PATH)
    action_names = [cls.__name__ for cls in get_args(api.Action)]
    assert len(action_names) == 12
    for action_name in action_names:
        match = re.search(
            rf'<article class="action-card" data-action="{re.escape(action_name)}".*?</article>',
            docs,
            re.DOTALL,
        )
        assert match, f"missing docs card for {action_name}"
        card_text = _text(match.group(0)).lower()
        for required in ["purpose", "fields", "when to use", "use first", "risk", "common errors"]:
            assert required in card_text, f"{action_name} missing {required}"
        assert action_name.lower() in card_text
    assert "token0` is ETH" in docs
    assert "token1` is USDC" in docs


def test_public_state_coverage_is_complete():
    text = _text(_read(DOC_PATH))
    required_terms = [
        "state.step",
        "state.timestamp",
        "state.config.scenario_steps",
        "state.config.step_length_seconds",
        "state.price",
        "state.eth_price",
        "state.tick",
        "state.twap",
        "state.pool.tick_spacing",
        "state.pool.initialized_ticks",
        "state.pool.fee_pips",
        "dfm_surge_fee_pips",
        "dfm_surge_reason",
        "state.pool.active_liquidity",
        "state.vault.idle0",
        "state.vault.idle1",
        "state.vault.debt_l",
        "state.vault.borrow_index",
        "state.vault.debt_liability_value",
        "state.vault.ltv_pips",
        "state.vault.max_ltv_pips",
        "state.vault.hard_ltv_pips",
        "state.vault.collateral_floor_l",
        "state.vault.delta",
        "state.vault.delta_normalized",
        "state.net_eth_delta",
        "state.eth_exposure_usd",
        "state.cash_usdc",
        "state.eth_inventory",
        "state.equity_usd",
        "state.profit_usd",
        "state.apr_pct",
        "state.positions",
        "state.limit_orders",
        "state.recent_swaps",
        "state.recent_fills",
        "state.recent_repairs",
        "state.score_so_far",
        "state.score_breakdown",
        "fees_earned_usd",
        "lo_edge_usd",
        "borrow_cost_usd",
        "repair_cost_usd",
    ]
    for term in required_terms:
        assert term in text


def test_hidden_info_rules_do_not_promise_private_data():
    text = _text(_read(DOC_PATH)).lower()
    for required in [
        "no hidden fair price",
        "hidden seeds",
        "future flow",
        "private runner state",
        "no external calls",
    ]:
        assert required in text
    banned_promises = [
        "hidden fair price is visible",
        "hidden seeds are exposed",
        "future flow is available",
        "read private runner state",
        "use private runner state",
    ]
    for phrase in banned_promises:
        assert phrase not in text


def test_strategy_recipes_are_practical_and_complete():
    docs = _read(DOC_PATH)
    required_recipes = [
        "Starter delta-neutral vault",
        "Passive wide LP",
        "Narrow fee-capture LP",
        "Limit-order rebalancer",
        "Delta repair bot",
        "DFM surge harvester",
        "Robustness-first ranked strategy",
    ]
    for recipe in required_recipes:
        assert recipe in docs
    assert docs.count("<details class=\"recipe") >= 7
    assert docs.count("Works") >= 7
    assert docs.count("fails") >= 7


def test_all_copyable_python_snippets_compile():
    docs = _read(DOC_PATH)
    snippets = re.findall(r'<code data-snippet="([^"]+)">(.*?)</code>', docs, re.DOTALL)
    assert len(snippets) >= 20
    names = {name for name, _ in snippets}
    for action_name in [cls.__name__ for cls in get_args(api.Action)]:
        assert action_name in names
    for name, raw_code in snippets:
        code = html.unescape(raw_code).strip()
        compile(code, f"web/docs.html:{name}", "exec")


def test_docs_links_and_hashes_are_valid():
    docs = _read(DOC_PATH)
    index = _read(INDEX_PATH)
    ids_by_file = {
        DOC_PATH.name: _ids(docs),
        INDEX_PATH.name: _ids(index),
    }
    for source_name, markup in [(DOC_PATH.name, docs), (INDEX_PATH.name, index)]:
        for href in re.findall(r'\bhref="([^"]+)"', markup):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target, _, fragment = href.partition("#")
            if not target:
                target_name = source_name
            else:
                target_path = (DOC_PATH.parent / target).resolve()
                assert target_path.exists(), f"broken link target {href}"
                target_name = target_path.name
            if fragment:
                assert fragment in ids_by_file.get(target_name, set()), f"broken hash {href}"


def test_docs_ux_has_search_copy_mobile_safe_markup():
    docs = _read(DOC_PATH)
    required = [
        '<html lang="en">',
        'aria-label="Academy navigation"',
        'aria-label="Docs sections"',
        'aria-label="Filter docs"',
        'id="docSearch"',
        'id="resultCount"',
        "function updateFilter",
        "async function copyCode",
        "navigator.clipboard.writeText",
        "@media (max-width: 720px)",
        "grid-template-columns: 1fr",
        "assets/aegis-logo.svg",
    ]
    for item in required:
        assert item in docs
    assert 'class="button primary" href="index.html"' in docs
