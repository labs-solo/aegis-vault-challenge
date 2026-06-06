from __future__ import annotations

from decimal import Decimal

from .api import ScoreBreakdown
from .vault import Vault


def action_cost(action_name: str, ticks_crossed: int = 0) -> Decimal:
    gas = {
        "BorrowL": 280_000,
        "RepayL": 320_000,
        "SwapExactIn": 180_000 + 18_000 * ticks_crossed,
        "MintRange": 280_000,
        "IncreaseRange": 210_000,
        "DecreaseRange": 210_000,
        "CollectFees": 110_000,
        "BurnRange": 220_000,
        "PlaceLimitOrder": 340_000,
        "CancelLimitOrder": 220_000,
        "WithdrawLimitOrder": 190_000,
        "DetachPosition": 160_000,
    }.get(action_name, 100_000)
    return Decimal(gas) * Decimal("0.00000002")


def delta_penalty(initial_equity: Decimal, delta_normalized: Decimal) -> Decimal:
    excess = max(Decimal("0"), delta_normalized - Decimal("0.03"))
    return initial_equity * Decimal(25) * excess * excess


def exposure_penalty(initial_equity: Decimal, avg_abs_exposure_usd: Decimal, max_abs_exposure_usd: Decimal) -> Decimal:
    if initial_equity <= 0:
        return Decimal("0")
    avg_norm = avg_abs_exposure_usd / initial_equity
    max_norm = max_abs_exposure_usd / initial_equity
    avg_excess = max(Decimal("0"), avg_norm - Decimal("0.03"))
    max_excess = max(Decimal("0"), max_norm - Decimal("0.08"))
    return initial_equity * (Decimal("18") * avg_excess * avg_excess + Decimal("7") * max_excess * max_excess)


def score(
    vault: Vault,
    price: Decimal,
    initial_equity: Decimal,
    costs: Decimal,
    invalid_penalty: Decimal,
    borrow_interest: Decimal,
    liquidation_penalty: Decimal = Decimal("0"),
    amount_scale: int = 1,
    avg_abs_exposure_usd: Decimal = Decimal("0"),
    max_abs_exposure_usd: Decimal = Decimal("0"),
) -> ScoreBreakdown:
    terminal = vault.equity(price, amount_scale)
    raw = terminal - initial_equity
    vstate = vault.state(price, amount_scale)
    dpen = delta_penalty(initial_equity, vstate.delta_normalized)
    epen = exposure_penalty(initial_equity, avg_abs_exposure_usd, max_abs_exposure_usd)
    scenario_score = raw - costs - dpen - epen - invalid_penalty
    cl_fee_pnl = sum((p.uncollected_fees0 * price + p.uncollected_fees1 for p in vault.positions), Decimal("0"))
    lo_edge_pnl = sum((o.claimable0 * price + o.claimable1 for o in vault.limit_orders), Decimal("0"))
    profit_pct = Decimal("0") if initial_equity == 0 else scenario_score * Decimal("100") / initial_equity
    reasons: list[str] = []
    if dpen > 0:
        reasons.append("delta exposure exceeded target band")
    if epen > 0:
        reasons.append("average or max ETH exposure exceeded neutrality band")
    if costs > 0:
        reasons.append("action costs reduced score")
    if borrow_interest > 0:
        reasons.append("borrow interest increased debt liability")
    if liquidation_penalty > 0:
        reasons.append("keeper repair reduced score")
    return ScoreBreakdown(
        raw_pnl=raw,
        cl_fee_pnl=cl_fee_pnl,
        lo_edge_pnl=lo_edge_pnl,
        inventory_mark_pnl=terminal,
        borrow_interest_attribution=borrow_interest,
        action_costs=costs,
        delta_penalty=dpen,
        liquidation_penalty=liquidation_penalty,
        invalid_action_penalty=invalid_penalty,
        scenario_score=scenario_score,
        loss_explanations=tuple(reasons),
        equity_usd=terminal,
        profit_usd=raw,
        profit_pct=profit_pct,
        net_profit_usd_after_penalties=scenario_score,
        delta_penalty_usd=dpen,
        exposure_penalty_usd=epen,
        fees_earned_usd=cl_fee_pnl,
        lo_edge_usd=lo_edge_pnl,
        inventory_pnl_usd=raw - cl_fee_pnl - lo_edge_pnl,
        borrow_cost_usd=borrow_interest,
        repair_cost_usd=liquidation_penalty,
        liquidation_cost_usd=liquidation_penalty,
    )
