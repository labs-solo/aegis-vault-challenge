from pathlib import Path

from aegis_challenge.sandbox import validate_strategy_source
from aegis_challenge.runner import run_strategy


def test_forbidden_import_fails_closed(tmp_path):
    strategy = tmp_path / "bad.py"
    strategy.write_text("import os\nclass Strategy: pass\n")
    assert validate_strategy_source(strategy) == ["ERR_FORBIDDEN_IMPORT:os"]


def test_forbidden_open_fails_closed(tmp_path):
    strategy = tmp_path / "bad.py"
    strategy.write_text("class Strategy:\n    def on_step(self, state):\n        open('/tmp/x')\n")
    assert validate_strategy_source(strategy) == ["ERR_FORBIDDEN_SIDE_EFFECT:open"]


def test_worker_timeout_fails_closed(tmp_path):
    strategy = tmp_path / "slow.py"
    strategy.write_text(
        "class Strategy:\n"
        "    def on_start(self, state):\n"
        "        pass\n"
        "    def on_step(self, state):\n"
        "        while True:\n"
        "            pass\n"
    )
    result = run_strategy(strategy, "smoke", 1, tmp_path / "runs")
    assert "ERR_TIMEOUT" in result["score"]["errors"]


def test_worker_rejects_environment_access_by_static_policy(tmp_path):
    strategy = tmp_path / "env.py"
    strategy.write_text(
        "import os\n"
        "class Strategy:\n"
        "    def on_step(self, state):\n"
        "        return []\n"
    )
    result = run_strategy(strategy, "smoke", 1, tmp_path / "runs")
    assert result["score"]["disqualified"] is True
    assert result["score"]["errors"] == ["ERR_FORBIDDEN_IMPORT:os"]
