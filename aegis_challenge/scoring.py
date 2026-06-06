from __future__ import annotations

from decimal import Decimal

from .api import ScoreBreakdown
from .vault import Vault

AVG_EXPOSURE_GATE = Decimal("0.03")
MAX_EXPOSURE_GATE = Decimal("0.08")
TERMINAL_EXPOSURE_GATE = Decimal("0.03")
TERMINAL_DIRECTIONAL_SHARE_GATE = Decimal("0.25")
TERMINAL_SAFE_LTV_PIPS = 970_000


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
    collected_cl_fees_usd: Decimal = Decimal("0"),
    realized_lo_edge_usd: Decimal = Decimal("0"),
    delta_band_time_pct: Decimal = Decimal("0"),
    is_terminal: bool = False,
) -> ScoreBreakdown:
    terminal = vault.equity(price, amount_scale)
    raw = terminal - initial_equity
    vstate = vault.state(price, amount_scale)
    dpen = delta_penalty(initial_equity, vstate.delta_normalized)
    epen = exposure_penalty(initial_equity, avg_abs_exposure_usd, max_abs_exposure_usd)
    uncollected_cl_fees = sum((p.uncollected_fees0 * price + p.uncollected_fees1 for p in vault.positions), Decimal("0"))
    unrealized_lo_edge = sum((o.claimable0 * price + o.claimable1 - o.deposited0 * price - o.deposited1 for o in vault.limit_orders if o.status == "filled"), Decimal("0"))
    cl_fee_pnl = collected_cl_fees_usd + uncollected_cl_fees
    lo_edge_pnl = realized_lo_edge_usd + unrealized_lo_edge
    cost_total = costs + borrow_interest + liquidation_penalty + invalid_penalty
    edge_profit = cl_fee_pnl + lo_edge_pnl - cost_total
    inventory_pnl = raw - cl_fee_pnl - lo_edge_pnl
    positive_directional_pnl = max(Decimal("0"), inventory_pnl)
    directional_denominator = max(abs(raw), abs(edge_profit), Decimal("1"))
    directional_share = positive_directional_pnl / directional_denominator
    positive_sources = abs(cl_fee_pnl) + abs(lo_edge_pnl) + abs(inventory_pnl)
    edge_share = Decimal("0") if positive_sources == 0 else (abs(cl_fee_pnl) + abs(lo_edge_pnl)) / positive_sources
    scenario_score = edge_profit - dpen - epen
    gate_status = "pass"
    gate_reason = None
    if initial_equity > 0:
        avg_norm = avg_abs_exposure_usd / initial_equity
        max_norm = max_abs_exposure_usd / initial_equity
        if avg_norm > AVG_EXPOSURE_GATE:
            gate_status = "fail"
            gate_reason = "average ETH exposure exceeded 3% of initial equity"
        elif max_norm > MAX_EXPOSURE_GATE:
            gate_status = "fail"
            gate_reason = "max ETH exposure exceeded 8% of initial equity"
    terminal_flattened = True
    if is_terminal:
        terminal_exposure_norm = Decimal("0") if terminal <= 0 else abs(vstate.eth_exposure_usd) / terminal
        terminal_flattened = (
            terminal_exposure_norm <= TERMINAL_EXPOSURE_GATE
            and vstate.ltv_pips <= TERMINAL_SAFE_LTV_PIPS
            and directional_share <= TERMINAL_DIRECTIONAL_SHARE_GATE
        )
        if gate_status == "pass" and not terminal_flattened:
            gate_status = "fail"
            if terminal_exposure_norm > TERMINAL_EXPOSURE_GATE:
                gate_reason = "terminal ETH exposure exceeded 3% of equity"
            elif vstate.ltv_pips > TERMINAL_SAFE_LTV_PIPS:
                gate_reason = "terminal LTV exceeded safe threshold"
            else:
                gate_reason = "directional inventory PnL exceeded 25% terminal share"
    disqualified = gate_status == "fail"
    if disqualified:
        scenario_score = min(scenario_score, Decimal("0"))
    profit_pct = Decimal("0") if initial_equity == 0 else scenario_score * Decimal("100") / initial_equity
    reasons: list[str] = []
    if edge_profit != raw:
        reasons.append("leaderboard score uses neutral CL/LO edge, not raw equity PnL")
    if dpen > 0:
        reasons.append("delta exposure exceeded target band")
    if epen > 0:
        reasons.append("average or max ETH exposure exceeded neutrality band")
    if gate_reason:
        reasons.append(gate_reason)
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
        inventory_mark_pnl=inventory_pnl,
        borrow_interest_attribution=borrow_interest,
        action_costs=costs,
        delta_penalty=dpen,
        liquidation_penalty=liquidation_penalty,
        invalid_action_penalty=invalid_penalty,
        scenario_score=scenario_score,
        disqualified=disqualified,
        disqualification_reason=gate_reason,
        loss_explanations=tuple(reasons),
        equity_usd=terminal,
        profit_usd=raw,
        profit_pct=profit_pct,
        net_profit_usd_after_penalties=scenario_score,
        delta_penalty_usd=dpen,
        exposure_penalty_usd=epen,
        fees_earned_usd=cl_fee_pnl,
        lo_edge_usd=lo_edge_pnl,
        inventory_pnl_usd=inventory_pnl,
        borrow_cost_usd=borrow_interest,
        repair_cost_usd=liquidation_penalty,
        liquidation_cost_usd=liquidation_penalty,
        edge_profit_usd=edge_profit,
        collected_cl_fees_usd=collected_cl_fees_usd,
        uncollected_cl_fees_usd=uncollected_cl_fees,
        realized_lo_edge_usd=realized_lo_edge_usd,
        unrealized_lo_edge_usd=unrealized_lo_edge,
        directional_profit_share=directional_share,
        edge_profit_share=edge_share,
        delta_band_time_pct=delta_band_time_pct,
        neutrality_gate_status=gate_status,
        neutrality_gate_reason=gate_reason,
        mirrored_score_gap_usd=abs(inventory_pnl),
        terminal_eth_exposure_usd=vstate.eth_exposure_usd,
        terminal_ltv_pips=vstate.ltv_pips,
        terminal_flattened=terminal_flattened,
    )
