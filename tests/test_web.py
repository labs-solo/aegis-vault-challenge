from pathlib import Path
import re
import json


def test_web_shell_has_aegis_console_surfaces():
    html = Path("web/index.html").read_text()
    required = [
        "Aegis Vault Challenge",
        "assets/aegis-logo.svg",
        "Aegis logo",
        "Programmable Infrastructure for Uniswap v4 Pools",
        "100,000 USDC",
        "ETH/USDC",
        "USD profit",
        "ETH exposure",
        "Paste one Python strategy",
        "180 simulated days",
        "Win on CL/LO edge without taking ETH direction risk",
        "Edge score",
        "CL/LO edge after costs and gates",
        "Why participate?",
        "Prove USD strategy edge",
        "Learn AEGIS Engine by using it",
        "Stay neutral to ETH",
        "Start",
        "Engine",
        "Leaderboard",
        "USD profit",
        "Current equity",
        "APR",
        "annualized net USD profit over elapsed simulated days",
        "ETH exposure",
        "Delta band",
        "LTV",
        "Replay",
        "Run 6-month ETH/USDC simulation",
        "Cancel run",
        "Publish latest try",
        "Sign in with X",
        "Saved Tries",
        "Share on X",
        "Download card",
        "AEGIS result card",
        "You're ranked",
        "Post copy",
        "Restore starter",
        "Refresh leaderboard",
        "0 CLI commands",
        "0 file loads",
        "Starting balance",
        "Goal",
        "Main risk",
        "Contestant flow",
        "Paste strategy",
        "Run 6 months",
        "Diagnose edge",
        "Submit",
        "Strategy Lab",
        "Six-month ETH/USDC replay: USD edge without ETH exposure",
        "Long horizon simulation progress",
        "Day 0 of 180",
        "Risk Panel",
        "Score Waterfall",
        "Leaderboard score",
        "Neutrality gate cap",
        "score capped",
        "Plain-English Mechanics",
        "Run Checks",
        "Sampled Event Tape",
        "Public Replay Event",
        "score_breakdown",
        "net_profit_usd_after_penalties",
        "apr_pct",
        "elapsed_simulated_days",
        "eth_price_usdc",
        "initial_balance_usdc",
        "leaderboard",
        "/api/run/start",
        "/api/run/progress",
        "/api/run/cancel",
        "/api/attempts/publish",
        "/api/auth/login",
        "/api/starter",
        "#ff8728",
    ]
    for text in required:
        assert text in html
    assert "Return</span>" not in html
    assert "returnMetric" not in html


def test_web_shell_avoids_hidden_seed_language():
    html = Path("web/index.html").read_text().lower()
    assert "hidden seed" not in html
    assert "latent fair" not in html


def test_web_shell_has_interactive_replay_renderer():
    html = Path("web/index.html").read_text()
    required_functions = [
        "parseJsonl",
        "renderChart",
        "renderMetrics",
        "renderWaterfall",
        "renderTape",
        "renderLeaderboard",
        "renderPositions",
        "stepFees",
        "laneSeries",
        "areaPath",
        "updateProgress",
        "applyProgressResult",
        "cancelRun",
        "showShare",
        "closeShareModal",
        "openShareOnX",
        "downloadShareCard",
        "drawShareCard",
        "wrapCanvasText",
    ]
    for name in required_functions:
        assert f"function {name}" in html
    assert 'id="stepRange"' in html
    assert 'id="replayChart"' in html
    assert 'id="strategyEditor"' in html
    assert 'id="commandStatus"' in html
    assert 'id="shareModal"' in html
    assert 'id="shareCardCanvas"' in html
    assert 'id="shareCopy"' in html
    assert 'id="horizonProgress"' in html
    assert 'id="cancelButton"' in html
    assert 'id="scoreMeter"' in html
    assert 'id="deltaMeter"' in html
    assert 'id="ltvMeter"' in html
    assert 'id="audits"' in html
    assert 'waterfallMode' in html
    assert "runFromBrowser" in html
    assert "submitFromBrowser" in html
    assert "twitter.com/intent/tweet" in html
    assert len(re.findall(r"<section class=\"panel\"", html)) >= 8


def test_live_apr_uses_elapsed_event_time_not_fixed_horizon():
    html = Path("web/index.html").read_text()
    assert "const eventElapsedDays = event.elapsed_simulated_days ?? event.simulated_day" in html
    assert "const elapsedDays = Number(hasLiveEventMoney ? eventElapsedDays : scoreElapsedDays)" in html
    assert "const computedApr = initial > 0 && elapsedDays > 0 ? (netProfit / initial) * (365 / elapsedDays) * 100 : NaN" in html
    assert "hasLiveEventMoney && Number.isFinite(computedApr)" in html
    assert "event.elapsed_simulated_days ?? event.simulated_day ?? score.elapsed_simulated_days ?? totalDays()" not in html


def test_web_shell_accessibility_basics():
    html = Path("web/index.html").read_text()
    assert '<html lang="en">' in html
    assert 'aria-label="Primary"' in html
    assert 'aria-label="Run details"' in html
    assert 'aria-label="Run metrics"' in html
    assert 'aria-label="Why participate"' in html
    assert 'aria-label="Run controls"' in html
    assert 'aria-label="Challenge objective"' in html
    assert 'aria-label="Contestant flow"' in html
    assert 'aria-label="Chart legend"' in html
    assert 'aria-label="USD profit, ETH price, ETH exposure, and LTV timeline"' in html
    assert 'aria-label="Replay step"' in html
    assert 'aria-label="Share your Aegis result"' in html
    assert 'aria-label="Editable X post copy"' in html
    assert 'aria-label="Attempt-specific AEGIS share card"' in html
    assert 'role="status"' in html
    assert 'role="dialog"' in html
    assert 'aria-live="polite"' in html
    assert 'role="img"' in html
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'aria-selected="true"' in html
    assert "focus-visible" in html
    assert 'type="file"' not in html


def test_web_shell_uses_aegis_brand_without_casino_language():
    html = Path("web/index.html").read_text().lower()
    assert "aegis - programmable infrastructure for uniswap v4 pools" in html
    assert '<div class="mark">a</div>' not in html
    assert 'class="brand-logo"' in html
    assert 'href="assets/aegis-logo.svg"' in html
    banned = ["casino", "sports-book", "arcade", "mascot", "sci-fi"]
    for word in banned:
        assert word not in html


def test_playwright_smoke_script_and_evidence_exist():
    package = json.loads(Path("package.json").read_text())
    assert package["devDependencies"]["playwright"]
    assert package["scripts"]["ui:smoke"] == "node scripts/ui-smoke.js"
    assert package["scripts"]["ui:a11y"] == "node scripts/ui-a11y.js"
    assert package["scripts"]["ui:flow"] == "node scripts/ui-flow.js"
    assert package["scripts"]["ui:auth-attempts"] == "node scripts/ui-auth-attempts.js"
    assert package["scripts"]["ui:progressive"] == "node scripts/ui-progressive.js"
    script = Path("scripts/ui-smoke.js").read_text()
    assert "screenshotDir" in script
    assert "horizontal overflow" in script
    a11y_script = Path("scripts/ui-a11y.js").read_text()
    assert "WCAG AA" in a11y_script
    assert "accessible names" in a11y_script
    flow_script = Path("scripts/ui-flow.js").read_text()
    assert "happy_path_actions_after_load" in flow_script
    assert "normal_path_file_pickers" in flow_script
    assert "login_required_preserved_strategy" in flow_script
    assert "cooldown_visible" in flow_script
    progressive_script = Path("scripts/ui-progressive.js").read_text()
    assert "competition_6m" in progressive_script
    assert "progressive-metrics" in progressive_script
    assert Path("reports/screenshots/desktop-console.png").exists()
    assert Path("reports/screenshots/mobile-console.png").exists()
    report = Path("reports/ux/playwright-smoke.md").read_text()
    assert "Status: smoke pass." in report
    assert "desktop-console.png" in report
    assert "mobile-console.png" in report
    a11y_report = Path("reports/ux/accessibility-audit.md").read_text()
    a11y_json = json.loads(Path("reports/ux/accessibility-audit.json").read_text())
    assert "Status: pass." in a11y_report
    assert a11y_json["status"] == "pass"
