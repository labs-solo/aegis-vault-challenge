from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .auth_attempts import clear_cookie_header, cookie_header, finish_x_callback, logout, mock_login, start_x_login
from .web_app import (
    ROOT,
    attempt_action,
    attempts_for_session,
    auth_context,
    auth_public_status,
    cancel_progressive_run,
    get_progressive_run,
    public_leaderboard,
    random_practice_path,
    raw_export_path,
    run_web_strategy,
    security_summary,
    start_progressive_run,
    starter_strategy,
    submit_web_run,
)


class ChallengeHandler(SimpleHTTPRequestHandler):
    server_version = "AegisVaultChallenge/0.1"

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        self._extra_headers: dict[str, str] = {}
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/web/index.html"
            return super().do_GET()
        if parsed.path == "/api/health":
            return self._json({"status": "ok"})
        if parsed.path == "/api/auth/status":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            return self._json(auth_public_status(session))
        if parsed.path == "/api/auth/callback":
            query = parse_qs(parsed.query)
            result, session_id = finish_x_callback(ROOT / "runs" / "web", query.get("code", [""])[0], query.get("state", [""])[0])
            self._set_session_cookie(session_id)
            if result.get("status") == "ok":
                return self._redirect("/web/index.html?auth=x")
            return self._json(result, HTTPStatus.UNAUTHORIZED)
        if parsed.path == "/api/attempts":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            return self._json(attempts_for_session(session))
        if parsed.path == "/api/security":
            return self._json(security_summary())
        if parsed.path == "/api/starter":
            return self._json(starter_strategy())
        if parsed.path == "/api/leaderboard":
            return self._json(public_leaderboard())
        if parsed.path == "/api/practice/random-seed":
            return self._json(random_practice_path())
        if parsed.path == "/api/run/progress":
            job_id = parse_qs(parsed.query).get("job_id", [""])[0]
            return self._json(get_progressive_run(job_id))
        if parsed.path == "/api/run/export":
            run_id = parse_qs(parsed.query).get("run_id", [""])[0]
            export_path = raw_export_path(run_id)
            if export_path is None:
                return self._json({"status": "error", "message": "Run export not found."}, HTTPStatus.NOT_FOUND)
            return self._file(export_path, f"aegis-vault-{run_id}-raw.zip")
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._extra_headers: dict[str, str] = {}
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/api/auth/login":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            result = start_x_login(ROOT / "runs" / "web", session)
            return self._json(result)
        if parsed.path == "/api/auth/mock-login":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            result = mock_login(ROOT / "runs" / "web", session, str(payload.get("handle", "aegis_builder")), payload.get("name"))
            return self._json(result)
        if parsed.path == "/api/auth/logout":
            session_id = self._session_id_from_cookie()
            logout(ROOT / "runs" / "web", session_id)
            self._extra_headers["Set-Cookie"] = clear_cookie_header(self.headers.get("Host", "127.0.0.1"))
            return self._json({"status": "ok", "auth": {"authenticated": False}})
        if parsed.path == "/api/attempts/rename":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            return self._json(attempt_action(session, "rename", payload))
        if parsed.path == "/api/attempts/clone":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            return self._json(attempt_action(session, "clone", payload))
        if parsed.path == "/api/attempts/publish":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            return self._json(attempt_action(session, "publish", payload))
        if parsed.path == "/api/attempts/unpublish":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            return self._json(attempt_action(session, "unpublish", payload))
        if parsed.path == "/api/run/start":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            result = start_progressive_run(
                str(payload.get("strategy", "")),
                str(payload.get("bundle", "competition_6m")),
                int(payload.get("seed", 1)),
                pace_seconds=float(payload["pace_seconds"]) if "pace_seconds" in payload else None,
                session=session,
                strategy_name=str(payload.get("strategy_name", "")).strip() or None,
            )
            return self._json(result, _status_for_result(result))
        if parsed.path == "/api/run/cancel":
            result = cancel_progressive_run(str(payload.get("job_id", "")))
            return self._json(result)
        if parsed.path == "/api/run":
            session, new_session_id = self._session()
            self._set_session_cookie(new_session_id)
            result = run_web_strategy(
                str(payload.get("strategy", "")),
                str(payload.get("bundle", "competition_6m")),
                int(payload.get("seed", 1)),
                session=session,
                strategy_name=str(payload.get("strategy_name", "")).strip() or None,
            )
            return self._json(result, _status_for_result(result))
        if parsed.path == "/api/submit":
            result = submit_web_run(str(payload.get("run_id", "")))
            return self._json(result)
        return self._json({"status": "error", "message": "Unknown endpoint."}, HTTPStatus.NOT_FOUND)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in getattr(self, "_extra_headers", {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        for key, value in getattr(self, "_extra_headers", {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _file(self, path: Path, filename: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        for key, value in getattr(self, "_extra_headers", {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _session_id_from_cookie(self) -> str | None:
        from .auth_attempts import parse_session_cookie

        return parse_session_cookie(self.headers.get("Cookie"))

    def _session(self):
        session, new_session_id = auth_context(self.headers.get("Cookie"))
        return session, new_session_id

    def _set_session_cookie(self, session_id: str | None) -> None:
        if session_id:
            self._extra_headers["Set-Cookie"] = cookie_header(session_id, self.headers.get("Host", "127.0.0.1"))


def _status_for_result(result: dict[str, Any]) -> HTTPStatus:
    if result.get("status") != "error":
        return HTTPStatus.OK
    if result.get("kind") == "auth_required":
        return HTTPStatus.UNAUTHORIZED
    if result.get("kind") == "cooldown_active":
        return HTTPStatus.TOO_MANY_REQUESTS
    return HTTPStatus.BAD_REQUEST


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aegis-vault-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), ChallengeHandler)
    print(f"Aegis Vault Challenge running at http://{args.host}:{args.port}/web/index.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
