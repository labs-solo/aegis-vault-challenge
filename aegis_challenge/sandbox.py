from __future__ import annotations

import ast
import importlib.util
import multiprocessing as mp
import os
from pathlib import Path
from typing import Any

FORBIDDEN_NAMES = {
    "__import__",
    "__builtins__",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}

FORBIDDEN_IMPORTS = {
    "builtins",
    "os",
    "subprocess",
    "socket",
    "pathlib",
    "importlib",
    "inspect",
    "ctypes",
    "multiprocessing",
    "threading",
    "time",
    "datetime",
    "requests",
    "urllib",
}


def validate_strategy_source(path: str | Path) -> list[str]:
    tree = ast.parse(Path(path).read_text())
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    errors.append(f"ERR_FORBIDDEN_IMPORT:{root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                errors.append(f"ERR_FORBIDDEN_IMPORT:{root}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            errors.append(f"ERR_FORBIDDEN_SIDE_EFFECT:{node.func.id}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            errors.append(f"ERR_FORBIDDEN_SIDE_EFFECT:{node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            errors.append(f"ERR_FORBIDDEN_DUNDER:{node.attr}")
    return list(dict.fromkeys(errors))


class StrategyWorker:
    def __init__(self, path: str | Path, timeout_seconds: float = 0.1):
        self.path = str(Path(path).resolve())
        self.timeout_seconds = timeout_seconds
        self.parent_conn, child_conn = mp.Pipe()
        self.process = mp.Process(target=_worker_main, args=(self.path, child_conn), daemon=True)
        self.process.start()
        status, payload = self._recv()
        if status != "ready":
            self.close()
            raise RuntimeError(str(payload))

    def on_start(self, state: Any) -> None:
        status, payload = self._call("on_start", state)
        if status != "ok":
            raise RuntimeError(str(payload))

    def on_step(self, state: Any) -> list[Any]:
        status, payload = self._call("on_step", state)
        if status == "ok":
            return payload or []
        raise RuntimeError(str(payload))

    def close(self) -> None:
        if self.process.is_alive():
            try:
                self.parent_conn.send(("close", None))
            except (BrokenPipeError, EOFError):
                pass
            self.process.join(timeout=0.2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=0.2)

    def _call(self, method: str, state: Any) -> tuple[str, Any]:
        self.parent_conn.send((method, state))
        if not self.parent_conn.poll(self.timeout_seconds):
            self.process.terminate()
            self.process.join(timeout=0.2)
            return "error", "ERR_TIMEOUT"
        return self._recv()

    def _recv(self) -> tuple[str, Any]:
        if not self.parent_conn.poll(2):
            return "error", "ERR_TIMEOUT"
        return self.parent_conn.recv()


def _worker_main(path: str, conn) -> None:
    os.environ.clear()
    try:
        spec = importlib.util.spec_from_file_location("contestant_strategy_worker", path)
        if spec is None or spec.loader is None:
            conn.send(("error", "ERR_INVALID_SCHEMA:cannot_load_strategy"))
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        strategy = module.Strategy()
        conn.send(("ready", None))
        while True:
            method, state = conn.recv()
            if method == "close":
                return
            if method == "on_start":
                result = strategy.on_start(state)
                conn.send(("ok", result))
            elif method == "on_step":
                result = strategy.on_step(state)
                conn.send(("ok", result or []))
            else:
                conn.send(("error", "ERR_INVALID_SCHEMA:unknown_worker_method"))
    except Exception as exc:  # noqa: BLE001
        try:
            conn.send(("error", f"ERR_STRATEGY_EXCEPTION:{type(exc).__name__}"))
        except (BrokenPipeError, EOFError):
            pass
