from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from aegis_challenge.auth_attempts import (
    COOLDOWN_SECONDS,
    auth_status,
    cookie_header,
    get_or_create_session,
    list_user_attempts,
    mock_login,
    mutate_attempt,
    public_leaderboard,
    run_permission,
    save_session,
    share_payload,
    start_x_login,
)
from aegis_challenge.web_app import run_web_strategy


STARTER = Path("examples/starter_strategy.py").read_text()


def test_mock_x_auth_and_session_cookie_are_passwordless(tmp_path):
    session, new_session_id = get_or_create_session(None, tmp_path)
    assert new_session_id
    header = cookie_header(new_session_id, "127.0.0.1:4173")
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header
    assert "Secure" not in header

    login = mock_login(tmp_path, session, "@Aegis_Tester")
    assert login["status"] == "ok"
    assert login["auth"]["authenticated"] is True
    assert login["auth"]["user"]["handle"] == "aegis_tester"
    assert "password" not in json.dumps(login).lower()


def test_anonymous_user_gets_exactly_one_run_and_keeps_attempt(tmp_path):
    session, _ = get_or_create_session(None, tmp_path)
    first = run_web_strategy(STARTER, "smoke", 1, tmp_path, session=session, strategy_name="First Try")
    assert first["status"] == "ok"
    assert first["auth"]["anonymous_run_used"] is True
    assert first["attempt"]["strategy_name"] == "First Try"
    assert first["attempt"]["strategy_source"] == STARTER

    second = run_web_strategy("# edited strategy stays in the editor\n" + STARTER, "smoke", 1, tmp_path, session=session, strategy_name="Edited")
    assert second["status"] == "error"
    assert second["kind"] == "auth_required"
    assert "Sign in with X" in second["message"]
    assert second["attempts"][0]["strategy_name"] == "First Try"

    login = mock_login(tmp_path, session, "aegis_tester")
    assert login["attempts"][0]["strategy_name"] == "First Try"
    assert login["attempts"][0]["user"]["handle"] == "aegis_tester"
    assert list_user_attempts(tmp_path, session)["attempts"][0]["run_id"] == first["run_id"]


def test_authenticated_cooldown_is_server_side_and_expirable(tmp_path):
    session, _ = get_or_create_session(None, tmp_path)
    mock_login(tmp_path, session, "aegis_tester")

    first = run_web_strategy(STARTER, "smoke", 1, tmp_path, session=session, strategy_name="Cooldown Try")
    assert first["status"] == "ok"
    blocked = run_web_strategy(STARTER, "smoke", 2, tmp_path, session=session, strategy_name="Too Soon")
    assert blocked["status"] == "error"
    assert blocked["kind"] == "cooldown_active"
    assert blocked["cooldown"]["remaining_seconds"] <= COOLDOWN_SECONDS
    assert {"edit strategy", "inspect replay", "rename attempts", "publish", "share"}.issubset(set(blocked["cooldown"]["useful_actions"]))

    session["last_run_started_at"] = time.time() - COOLDOWN_SECONDS - 1
    save_session(tmp_path, session)
    allowed = run_permission(session)
    assert allowed["allowed"] is True


def test_attempt_lifecycle_public_leaderboard_and_share_privacy(tmp_path):
    session, _ = get_or_create_session(None, tmp_path)
    mock_login(tmp_path, session, "aegis_tester")
    run = run_web_strategy(STARTER, "smoke", 1, tmp_path, session=session, strategy_name="Starter Edge")
    attempt_id = run["attempt"]["attempt_id"]

    assert public_leaderboard(tmp_path)["leaderboard"] == []

    renamed = mutate_attempt(tmp_path, session, attempt_id, "rename", strategy_name="Tight Delta Edge")
    assert renamed["status"] == "ok"
    assert renamed["attempt"]["strategy_name"] == "Tight Delta Edge"

    cloned = mutate_attempt(tmp_path, session, attempt_id, "clone")
    assert cloned["status"] == "ok"
    assert cloned["attempt"]["published"] is False
    assert cloned["attempt"]["strategy_source"] == STARTER

    published = mutate_attempt(tmp_path, session, attempt_id, "publish")
    assert published["status"] == "ok"
    row = published["leaderboard"]["leaderboard"][0]
    assert row["rank"] == 1
    assert row["user"]["handle"] == "aegis_tester"
    assert row["strategy_name"] == "Tight Delta Edge"
    assert row["avatar_url"] if "avatar_url" in row else row["user"]["avatar_url"]
    assert {"attempt_id", "run_id", "strategy_name", "apr_pct", "profit_usd", "max_eth_exposure_usd"}.issubset(row)
    assert row["share"]["text"].startswith("Ranked #1 in the Aegis Vault Challenge.")
    assert not re.search(r"\d+\.\d{4,}", row["share"]["text"])
    assert "Aegis Vault Challenge" in row["share"]["text"]
    assert "Strategy: Tight Delta Edge" in row["share"]["text"]
    assert "Make USD profit in ETH/USDC while staying delta-neutral." in row["share"]["text"]
    assert row["share"]["profit_label"].startswith(("+$", "-$"))
    assert row["share"]["apr_label"].endswith("%")
    assert row["share"]["risk_badge"]
    assert row["share"]["intent_url"].startswith("https://twitter.com/intent/tweet?")
    query = parse_qs(urlparse(row["share"]["intent_url"]).query)
    assert query["text"][0] == row["share"]["intent_text"]
    assert query["url"] == ["http://127.0.0.1:4173/web/index.html"]
    assert "http://127.0.0.1:4173/web/index.html" in row["share"]["text"]
    assert row["share"]["is_local"] is True
    assert "only works on your machine" in row["share"]["local_warning"]

    public_blob = json.dumps(public_leaderboard(tmp_path))
    assert "strategy_source" not in public_blob
    assert str(tmp_path) not in public_blob
    assert "access_token" not in public_blob
    assert "refresh_token" not in public_blob
    assert "aegis_session" not in public_blob

    unpublished = mutate_attempt(tmp_path, session, attempt_id, "unpublish")
    assert unpublished["status"] == "ok"
    assert public_leaderboard(tmp_path)["leaderboard"] == []


def test_share_payload_uses_clean_public_url_and_no_raw_decimals(monkeypatch):
    monkeypatch.setenv("AEGIS_COMPETITION_URL", "https://aegis.markets/vault-challenge")
    attempt = {
        "strategy_name": "Breakout Delta Net",
        "profit_usd": "7785.4497335493754814699420",
        "apr_pct": "15.78716195969734472631404906",
        "max_eth_exposure_usd": "280",
        "repairs_liquidations": 0,
        "user": {"id": "x:1", "handle": "aegis_builder", "name": "Aegis Builder", "avatar_url": ""},
    }
    share = share_payload(attempt, 2)
    assert share["text"].startswith("Ranked #2 in the Aegis Vault Challenge.")
    assert "+$7,785 on $100K | +15.79% APR" in share["text"]
    assert "7785.449" not in share["text"]
    assert "15.787" not in share["text"]
    assert "127.0.0.1" not in share["text"]
    assert "https://aegis.markets/vault-challenge" in share["text"]
    assert "https://aegis.markets/vault-challenge" not in share["intent_text"]
    assert share["url"] == "https://aegis.markets/vault-challenge"
    assert share["is_local"] is False
    assert share["url_missing"] is False
    assert share["local_warning"] == ""
    assert share["rank_label"] == "#2"
    assert share["profit_label"] == "+$7,785"
    assert share["apr_label"] == "+15.79%"
    assert share["risk_badge"] == "Delta-safe"
    query = parse_qs(urlparse(share["intent_url"]).query)
    assert query["url"] == ["https://aegis.markets/vault-challenge"]
    assert query["text"][0] == share["intent_text"]


def test_share_payload_does_not_emit_local_url_in_production_mode(monkeypatch):
    monkeypatch.delenv("AEGIS_COMPETITION_URL", raising=False)
    monkeypatch.setenv("AEGIS_SHARE_MODE", "production")
    share = share_payload(
        {
            "strategy_name": "Launch Safe",
            "profit_usd": "7785.4497335493754814699420",
            "apr_pct": "15.78716195969734472631404906",
            "max_eth_exposure_usd": "280",
            "repairs_liquidations": 0,
            "user": {"id": "x:1", "handle": "aegis_builder", "name": "Aegis Builder", "avatar_url": ""},
        },
        2,
    )
    assert "127.0.0.1" not in share["text"]
    assert "localhost" not in share["text"]
    assert share["url"] == ""
    assert share["url_missing"] is True
    assert "AEGIS_COMPETITION_URL" in share["local_warning"]
    query = parse_qs(urlparse(share["intent_url"]).query)
    assert query["text"] == [share["intent_text"]]
    assert "url" not in query


def test_real_x_login_path_uses_pkce_state_and_minimal_read_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("X_CLIENT_ID", "client-id")
    monkeypatch.setenv("X_REDIRECT_URI", "https://example.com/api/auth/callback")
    monkeypatch.setenv("X_AUTH_SCOPES", "users.read tweet.read")
    session, _ = get_or_create_session(None, tmp_path)

    result = start_x_login(tmp_path, session)
    assert result["status"] == "ok"
    assert result["mode"] == "x_oauth"
    parsed = urlparse(result["auth_url"])
    assert parsed.netloc in {"twitter.com", "x.com"}
    query = parse_qs(parsed.query)
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["https://example.com/api/auth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["state"][0]) >= 20
    assert query["scope"] == ["users.read tweet.read"]

    state_doc = json.loads((tmp_path / "state" / "auth_state.json").read_text())
    pending = state_doc["oauth"][query["state"][0]]
    assert pending["session_id"] == session["session_id"]
    assert pending["verifier_hash"]
