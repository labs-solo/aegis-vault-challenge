from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SESSION_COOKIE = "aegis_session"
COOLDOWN_SECONDS = 300
COMPETITION_URL = os.environ.get("AEGIS_COMPETITION_URL", "http://127.0.0.1:4173/web/index.html")
_MOCK_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230f1115'/%3E%3Ctext x='32' y='40' text-anchor='middle' font-size='28' fill='%23ff8728' font-family='Arial'%3EX%3C/text%3E%3C/svg%3E"


def state_dir(run_root: str | Path) -> Path:
    path = Path(run_root) / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def auth_state_path(run_root: str | Path) -> Path:
    return state_dir(run_root) / "auth_state.json"


def attempts_path(run_root: str | Path) -> Path:
    return state_dir(run_root) / "attempts.json"


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def parse_session_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    for chunk in cookie_header.split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.strip().split("=", 1)
        if key == SESSION_COOKIE and value:
            return value
    return None


def cookie_header(session_id: str, host: str = "127.0.0.1") -> str:
    secure = "" if host.startswith("127.0.0.1") or host.startswith("localhost") else "; Secure"
    return f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Lax{secure}"


def clear_cookie_header(host: str = "127.0.0.1") -> str:
    secure = "" if host.startswith("127.0.0.1") or host.startswith("localhost") else "; Secure"
    return f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}"


def get_or_create_session(cookie_header_value: str | None, run_root: str | Path) -> tuple[dict[str, Any], str | None]:
    state = read_json(auth_state_path(run_root), {"sessions": {}, "oauth": {}})
    session_id = parse_session_cookie(cookie_header_value)
    if session_id and session_id in state["sessions"]:
        session = state["sessions"][session_id]
        session.setdefault("session_id", session_id)
        return session, None
    session_id = secrets.token_urlsafe(24)
    session = {
        "session_id": session_id,
        "created_at": int(time.time()),
        "anonymous_run_used": False,
        "last_run_started_at": None,
        "user": None,
    }
    state["sessions"][session_id] = session
    write_json(auth_state_path(run_root), state)
    return session, session_id


def save_session(run_root: str | Path, session: dict[str, Any]) -> None:
    state = read_json(auth_state_path(run_root), {"sessions": {}, "oauth": {}})
    state["sessions"][session["session_id"]] = session
    write_json(auth_state_path(run_root), state)


def logout(run_root: str | Path, session_id: str | None) -> None:
    if not session_id:
        return
    state = read_json(auth_state_path(run_root), {"sessions": {}, "oauth": {}})
    state["sessions"].pop(session_id, None)
    write_json(auth_state_path(run_root), state)


def auth_status(run_root: str | Path, session: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    allowed = run_permission(session, now)
    return {
        "authenticated": bool(session.get("user")),
        "user": public_user(session.get("user")),
        "anonymous_run_used": bool(session.get("anonymous_run_used")),
        "cooldown": allowed.get("cooldown"),
        "can_start_run": allowed["allowed"],
        "block_reason": allowed.get("reason"),
        "mock_auth_available": not real_x_configured(),
        "session_security": {
            "cookie": "HttpOnly; SameSite=Lax; Secure outside localhost",
            "tokens_persisted": False,
        },
    }


def real_x_configured() -> bool:
    return bool(os.environ.get("X_CLIENT_ID") and os.environ.get("X_REDIRECT_URI"))


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user["id"],
        "handle": user["handle"],
        "name": user.get("name", user["handle"]),
        "avatar_url": user.get("avatar_url") or _MOCK_AVATAR,
    }


def mock_login(run_root: str | Path, session: dict[str, Any], handle: str = "aegis_builder", name: str | None = None) -> dict[str, Any]:
    clean = "".join(ch for ch in handle.lstrip("@").lower() if ch.isalnum() or ch == "_") or "aegis_builder"
    previous_owner = owner_id(session)
    session["user"] = {
        "id": f"mock:{clean}",
        "handle": clean,
        "name": name or clean.replace("_", " ").title(),
        "avatar_url": _MOCK_AVATAR,
        "provider": "mock_x",
    }
    session["anonymous_run_used"] = True
    migrate_attempts(run_root, previous_owner, owner_id(session), identity_for_attempt(session))
    save_session(run_root, session)
    return {"status": "ok", "mode": "mock", "auth": auth_status(run_root, session), "attempts": list_user_attempts(run_root, session)["attempts"], "leaderboard": public_leaderboard(run_root)}


def start_x_login(run_root: str | Path, session: dict[str, Any]) -> dict[str, Any]:
    if not real_x_configured():
        return mock_login(run_root, session)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state_token = secrets.token_urlsafe(24)
    state = read_json(auth_state_path(run_root), {"sessions": {}, "oauth": {}})
    state.setdefault("oauth", {})[state_token] = {
        "session_id": session["session_id"],
        "verifier_hash": hashlib.sha256(verifier.encode()).hexdigest(),
        "verifier": verifier,
        "created_at": int(time.time()),
    }
    write_json(auth_state_path(run_root), state)
    params = {
        "response_type": "code",
        "client_id": os.environ["X_CLIENT_ID"],
        "redirect_uri": os.environ["X_REDIRECT_URI"],
        "scope": os.environ.get("X_AUTH_SCOPES", "users.read tweet.read offline.access"),
        "state": state_token,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {"status": "ok", "mode": "x_oauth", "auth_url": "https://twitter.com/i/oauth2/authorize?" + urllib.parse.urlencode(params)}


def finish_x_callback(run_root: str | Path, code: str, state_token: str) -> tuple[dict[str, Any], str | None]:
    state = read_json(auth_state_path(run_root), {"sessions": {}, "oauth": {}})
    pending = state.get("oauth", {}).pop(state_token, None)
    if not pending:
        write_json(auth_state_path(run_root), state)
        return {"status": "error", "kind": "auth_state_invalid", "message": "Sign in expired. Try again."}, None
    session = state.get("sessions", {}).get(pending["session_id"])
    if not session:
        write_json(auth_state_path(run_root), state)
        return {"status": "error", "kind": "session_missing", "message": "Session expired. Try again."}, None
    try:
        user = exchange_code_for_user(code, pending["verifier"])
    except Exception as exc:  # noqa: BLE001
        write_json(auth_state_path(run_root), state)
        return {"status": "error", "kind": "x_auth_failed", "message": f"X sign in failed: {type(exc).__name__}"}, None
    previous_owner = owner_id(session)
    session["user"] = user
    session["anonymous_run_used"] = True
    migrate_attempts(run_root, previous_owner, owner_id(session), identity_for_attempt(session))
    state["sessions"][session["session_id"]] = session
    write_json(auth_state_path(run_root), state)
    return {"status": "ok", "mode": "x_oauth", "auth": auth_status(run_root, session), "attempts": list_user_attempts(run_root, session)["attempts"], "leaderboard": public_leaderboard(run_root)}, session["session_id"]


def exchange_code_for_user(code: str, verifier: str) -> dict[str, Any]:
    token_payload = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.environ["X_REDIRECT_URI"],
            "client_id": os.environ["X_CLIENT_ID"],
            "code_verifier": verifier,
        }
    ).encode()
    request = urllib.request.Request("https://api.x.com/2/oauth2/token", data=token_payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    if os.environ.get("X_CLIENT_SECRET"):
        basic = base64.b64encode(f"{os.environ['X_CLIENT_ID']}:{os.environ['X_CLIENT_SECRET']}".encode()).decode()
        request.add_header("Authorization", f"Basic {basic}")
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - official X endpoint
        token_doc = json.loads(response.read().decode())
    access_token = token_doc["access_token"]
    user_request = urllib.request.Request("https://api.x.com/2/users/me?user.fields=profile_image_url,name,username")
    user_request.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(user_request, timeout=15) as response:  # noqa: S310 - official X endpoint
        user_doc = json.loads(response.read().decode())
    data = user_doc["data"]
    return {
        "id": f"x:{data['id']}",
        "handle": data.get("username", data["id"]),
        "name": data.get("name", data.get("username", data["id"])),
        "avatar_url": data.get("profile_image_url") or _MOCK_AVATAR,
        "provider": "x",
    }


def run_permission(session: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    if not session.get("user"):
        if session.get("anonymous_run_used"):
            return {"allowed": False, "reason": "auth_required", "message": "Sign in with X to try again."}
        return {"allowed": True}
    last = session.get("last_run_started_at")
    if last is not None:
        remaining = max(0, int(COOLDOWN_SECONDS - (now - float(last))))
        if remaining > 0:
            return {
                "allowed": False,
                "reason": "cooldown_active",
                "message": "Your next simulation unlocks soon.",
                "cooldown": {
                    "remaining_seconds": remaining,
                    "next_run_at": int(float(last) + COOLDOWN_SECONDS),
                    "useful_actions": ["edit strategy", "inspect replay", "rename attempts", "publish", "share"],
                },
            }
    return {"allowed": True, "cooldown": {"remaining_seconds": 0}}


def mark_run_started(run_root: str | Path, session: dict[str, Any], now: float | None = None) -> None:
    now = time.time() if now is None else now
    if session.get("user"):
        session["last_run_started_at"] = float(now)
    else:
        session["anonymous_run_used"] = True
    save_session(run_root, session)


def read_attempts(run_root: str | Path) -> list[dict[str, Any]]:
    return list(read_json(attempts_path(run_root), {"attempts": []}).get("attempts", []))


def write_attempts(run_root: str | Path, attempts: list[dict[str, Any]]) -> None:
    write_json(attempts_path(run_root), {"attempts": attempts})


def owner_id(session: dict[str, Any]) -> str:
    user = session.get("user")
    return user["id"] if user else f"anon:{session['session_id']}"


def identity_for_attempt(session: dict[str, Any]) -> dict[str, Any]:
    user = public_user(session.get("user"))
    if user:
        return user
    return {"id": owner_id(session), "handle": "anonymous", "name": "Anonymous", "avatar_url": _MOCK_AVATAR}


def migrate_attempts(run_root: str | Path, previous_owner: str, new_owner: str, identity: dict[str, Any]) -> None:
    if previous_owner == new_owner:
        return
    attempts = read_attempts(run_root)
    changed = False
    for item in attempts:
        if item.get("owner_id") == previous_owner:
            item["owner_id"] = new_owner
            item["user"] = identity
            item["saved_at"] = int(time.time())
            changed = True
    if changed:
        write_attempts(run_root, attempts)


def default_strategy_name(score_doc: dict[str, Any]) -> str:
    base = Path(str(score_doc.get("strategy", "strategy.py"))).stem.replace("_", " ").strip()
    return base.title() or "Aegis Strategy"


def auto_save_attempt(
    run_root: str | Path,
    session: dict[str, Any],
    run_dir: str | Path,
    strategy_source: str,
    strategy_name: str | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    score_doc = json.loads((run_dir / "score.json").read_text())
    identity = identity_for_attempt(session)
    attempts = read_attempts(run_root)
    existing = next((item for item in attempts if item.get("run_id") == score_doc["run_id"] and item.get("owner_id") == owner_id(session)), None)
    attempt = existing or {}
    attempt.update(
        {
            "attempt_id": attempt.get("attempt_id") or secrets.token_urlsafe(12),
            "owner_id": owner_id(session),
            "user": identity,
            "run_id": score_doc["run_id"],
            "bundle": score_doc.get("bundle"),
            "strategy_name": strategy_name or attempt.get("strategy_name") or default_strategy_name(score_doc),
            "strategy_source": strategy_source,
            "created_at": attempt.get("created_at") or int(time.time()),
            "saved_at": int(time.time()),
            "published": bool(attempt.get("published", False)),
            "published_at": attempt.get("published_at"),
            "score": str(score_doc.get("net_profit_usd_after_penalties", score_doc.get("score_breakdown", {}).get("scenario_score", "0"))),
            "profit_usd": str(score_doc.get("net_profit_usd_after_penalties", "0")),
            "apr_pct": str(score_doc.get("apr_pct", "0")),
            "avg_eth_exposure_usd": str(score_doc.get("avg_eth_exposure_usd", "0")),
            "max_eth_exposure_usd": str(score_doc.get("max_eth_exposure_usd", "0")),
            "repairs_liquidations": repair_count(run_dir / "public_replay.jsonl"),
            "safe_artifacts": {
                "run_id": score_doc["run_id"],
                "score": "score.json",
                "replay": "public_replay.jsonl",
            },
        }
    )
    attempts = [item for item in attempts if item.get("attempt_id") != attempt["attempt_id"]]
    attempts.append(attempt)
    write_attempts(run_root, attempts)
    return public_attempt(attempt, include_strategy=True)


def repair_count(replay_path: Path) -> int:
    if not replay_path.exists():
        return 0
    count = 0
    for line in replay_path.read_text().splitlines():
        if line.strip():
            try:
                count += len(json.loads(line).get("recent_repairs") or [])
            except json.JSONDecodeError:
                pass
    return count


def public_attempt(attempt: dict[str, Any], include_strategy: bool = False) -> dict[str, Any]:
    doc = {
        key: attempt.get(key)
        for key in [
            "attempt_id",
            "run_id",
            "bundle",
            "strategy_name",
            "created_at",
            "saved_at",
            "published",
            "published_at",
            "score",
            "ranked_score",
            "public_profit_usd",
            "profit_usd",
            "apr_pct",
            "avg_eth_exposure_usd",
            "max_eth_exposure_usd",
            "repairs_liquidations",
            "ranked_summary",
            "safe_artifacts",
        ]
    }
    doc["user"] = public_user(attempt.get("user")) or attempt.get("user")
    doc["share"] = share_payload(attempt) if attempt.get("published") else None
    if include_strategy:
        doc["strategy_source"] = attempt.get("strategy_source", "")
    return doc


def list_user_attempts(run_root: str | Path, session: dict[str, Any]) -> dict[str, Any]:
    mine = [public_attempt(item, include_strategy=True) for item in read_attempts(run_root) if item.get("owner_id") == owner_id(session)]
    mine.sort(key=lambda item: item.get("saved_at") or 0, reverse=True)
    return {"status": "ok", "attempts": mine}


def mutate_attempt(run_root: str | Path, session: dict[str, Any], attempt_id: str, action: str, **updates: Any) -> dict[str, Any]:
    attempts = read_attempts(run_root)
    for item in attempts:
        if item.get("attempt_id") != attempt_id or item.get("owner_id") != owner_id(session):
            continue
        if action == "rename":
            name = str(updates.get("strategy_name", "")).strip()
            if not name:
                return {"status": "error", "kind": "invalid_name", "message": "Name this try before saving."}
            item["strategy_name"] = name[:80]
            item["saved_at"] = int(time.time())
        elif action == "publish":
            item["published"] = True
            item["published_at"] = int(time.time())
        elif action == "unpublish":
            item["published"] = False
            item["published_at"] = None
        elif action == "clone":
            clone = dict(item)
            clone["attempt_id"] = secrets.token_urlsafe(12)
            clone["strategy_name"] = f"{item.get('strategy_name', 'Strategy')} copy"[:80]
            clone["created_at"] = int(time.time())
            clone["saved_at"] = int(time.time())
            clone["published"] = False
            clone["published_at"] = None
            attempts.append(clone)
            write_attempts(run_root, attempts)
            return {"status": "ok", "attempt": public_attempt(clone, include_strategy=True), "attempts": list_user_attempts(run_root, session)["attempts"]}
        write_attempts(run_root, attempts)
        leaderboard = public_leaderboard(run_root)
        attempt = public_attempt(item, include_strategy=True)
        ranked = next((row for row in leaderboard["leaderboard"] if row.get("attempt_id") == attempt_id), None)
        if ranked:
            attempt["rank"] = ranked.get("rank")
            attempt["share"] = ranked.get("share")
        return {"status": "ok", "attempt": attempt, "attempts": list_user_attempts(run_root, session)["attempts"], "leaderboard": leaderboard}
    return {"status": "error", "kind": "attempt_not_found", "message": "Attempt not found."}


def public_leaderboard(run_root: str | Path) -> dict[str, Any]:
    rows = [item for item in read_attempts(run_root) if item.get("published")]
    rows.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("published_at") or ""), item.get("attempt_id", "")))
    leaderboard = []
    for rank, item in enumerate(rows, 1):
        row = public_attempt(item)
        row.update(
            {
                "rank": rank,
                "strategy": item.get("strategy_name"),
                "net_profit_usd_after_penalties": item.get("profit_usd"),
                "ranked_score": item.get("ranked_score"),
                "ranked_summary": item.get("ranked_summary"),
                "risk_badges": badges_for_attempt(item, rank),
            }
        )
        row["share"] = share_payload(item, rank)
        leaderboard.append(row)
    return {"leaderboard": leaderboard}


def badges_for_attempt(attempt: dict[str, Any], rank: int) -> list[str]:
    badges = ["published"]
    if rank == 1:
        badges.append("current leader")
    try:
        if abs(float(attempt.get("max_eth_exposure_usd") or 0)) <= 3000:
            badges.append("delta-safe")
        if int(attempt.get("repairs_liquidations") or 0) == 0:
            badges.append("no-liquidation")
        if float(attempt.get("profit_usd") or 0) > 0:
            badges.append("profitable")
    except ValueError:
        pass
    return badges


def share_payload(attempt: dict[str, Any], rank: int | None = None) -> dict[str, Any]:
    url = share_url()
    local = is_local_url(url)
    missing_production_url = not url
    rank_label = f"#{rank}" if rank else "published"
    strategy = str(attempt.get("strategy_name") or "AEGIS vault strategy").strip() or "AEGIS vault strategy"
    user = public_user(attempt.get("user")) or attempt.get("user") or {}
    handle = user.get("handle") or "aegis_builder"
    profit = format_signed_usd(attempt.get("profit_usd"))
    apr = format_signed_pct(attempt.get("apr_pct"))
    risk_badge = share_risk_badge(attempt)
    text_without_url = "\n".join(
        [
            f"Ranked {rank_label} in the Aegis Vault Challenge.",
            "",
            f"{profit} on $100K | {apr} APR",
            f"Strategy: {strategy}",
            "",
            "Make USD profit in ETH/USDC while staying delta-neutral.",
        ]
    )
    if url:
        link_line = f"Local dev link: {url}" if local else url
    else:
        link_line = "Challenge URL pending public launch."
    text = f"{text_without_url}\n{link_line}"
    intent_params = {"text": text_without_url}
    if url:
        intent_params["url"] = url
    params = urllib.parse.urlencode(intent_params)
    return {
        "text": text,
        "intent_text": text_without_url,
        "intent_url": f"https://twitter.com/intent/tweet?{params}",
        "url": url,
        "is_local": local,
        "url_missing": missing_production_url,
        "local_warning": local_warning(local, missing_production_url),
        "rank_label": rank_label,
        "handle": handle,
        "strategy_name": strategy,
        "profit_label": profit,
        "apr_label": apr,
        "pair_label": "ETH/USDC",
        "starting_balance_label": "$100K start",
        "risk_badge": risk_badge,
    }


def share_url() -> str:
    url = os.environ.get("AEGIS_COMPETITION_URL", COMPETITION_URL)
    if production_share_mode() and is_local_url(url):
        return ""
    return url


def production_share_mode() -> bool:
    mode = os.environ.get("AEGIS_SHARE_MODE") or os.environ.get("AEGIS_ENV") or ""
    return mode.lower() in {"prod", "production"}


def is_local_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def local_warning(is_local: bool, url_missing: bool = False) -> str:
    if url_missing:
        return "Set AEGIS_COMPETITION_URL before production sharing. The X post can still be copied without a public link."
    if is_local:
        return "This link only works on your machine. Configure AEGIS_COMPETITION_URL before public sharing."
    return ""


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def format_signed_usd(value: Any) -> str:
    amount = decimal_value(value).quantize(Decimal("1"))
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):,}"


def format_signed_pct(value: Any) -> str:
    pct = decimal_value(value).quantize(Decimal("0.01"))
    sign = "+" if pct >= 0 else "-"
    return f"{sign}{abs(pct):,.2f}%"


def share_risk_badge(attempt: dict[str, Any]) -> str:
    try:
        repairs = int(attempt.get("repairs_liquidations") or 0)
        max_exposure = abs(decimal_value(attempt.get("max_eth_exposure_usd")))
        if repairs == 0 and max_exposure <= Decimal("3000"):
            return "Delta-safe"
        if repairs == 0:
            return "No liquidation"
        return "Risk-managed"
    except ValueError:
        return "Delta-aware"


def public_docs_security_summary() -> dict[str, Any]:
    return {
        "auth": "OAuth 2.0 Authorization Code with PKCE; mock provider for local dev",
        "share": "X web intent by default; no auto-post",
        "secrets": "env only; tokens not persisted",
        "cookies": "HttpOnly SameSite=Lax; Secure outside localhost",
    }
