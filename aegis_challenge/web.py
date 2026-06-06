from __future__ import annotations

from pathlib import Path


def web_root() -> Path:
    return Path(__file__).resolve().parents[1] / "web"


def index_html() -> Path:
    return web_root() / "index.html"


def brand_smoke_check() -> list[str]:
    html = index_html().read_text()
    required = [
        "Aegis Vault Challenge",
        "assets/aegis-logo.svg",
        "Build a market-maker that wins without betting on price",
        "Compete on neutral liquidity and order-flow edge",
        "Why participate?",
        "Prove real strategy edge",
        "Learn AEGIS Engine by using it",
        "AEGIS Engine",
        "Plain-English Mechanics",
        "Replay: edge without exposure",
        "Run Checks",
        "Run simulation",
        "Submit run",
        "Leaderboard",
        "Replay",
        "#ff8728",
    ]
    return [item for item in required if item not in html]
