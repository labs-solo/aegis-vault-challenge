from decimal import Decimal

from aegis_challenge.api import ERROR_CODES, BorrowL, State
from aegis_challenge.flow import scenario
from aegis_challenge.pool import Pool
from aegis_challenge.runner import make_state
from aegis_challenge.scoring import ScoreBreakdown
from aegis_challenge.vault import Vault


def test_state_does_not_expose_seed():
    state = make_state(0, scenario("smoke", 1), "public", Pool(), Vault(), (), (), ScoreBreakdown())
    assert isinstance(state, State)
    assert not hasattr(state, "seed")
    assert state.config.public_run_id == "public"


def test_required_error_codes_exist():
    assert "ERR_INSUFFICIENT_DEBT" in ERROR_CODES
    assert "ERR_TIMEOUT" in ERROR_CODES


def test_action_dataclass():
    assert BorrowL(amount_l=1).amount_l == 1
    assert Decimal("1") == Decimal("1")
