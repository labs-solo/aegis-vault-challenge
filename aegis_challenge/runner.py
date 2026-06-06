from __future__ import annotations

import hashlib
import json
import zipfile
import csv
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Callable

from .aegis_market import AegisMarket, full_range_amounts_for_liquidity, keeper_fee_pips, liquidity_for_principal, micro_liq_swap_deficit, repay_bridge, repay_fraction_pips
from .api import (
    BorrowL,
    BurnRange,
    CancelLimitOrder,
    ClPosition,
    CollectFees,
    DecreaseRange,
    DetachPosition,
    FillEvent,
    IncreaseRange,
    LimitOrder,
    MintRange,
    PlaceLimitOrder,
    RepayL,
    RepairEvent,
    ScoreBreakdown,
    State,
    SwapExactIn,
    SwapEvent,
    WithdrawLimitOrder,
    to_jsonable,
)
from .dfm import apply_dfm_fee_state, dfm_fee_state
from .flow import regime_at_step, scenario
from .limit_orders import cancel_order, should_fill
from .market_engine_v2 import (
    CALIBRATION_HASH,
    ENGINE_VERSION,
    MarketStep,
    generate_market_path,
    latency_prefix_count as market_latency_prefix_count,
    public_path_summary,
    public_step_stats,
    trade_notional_usd,
    trade_token_in,
)
from .pool import Pool
from .sandbox import StrategyWorker, validate_strategy_source
from .scoring import action_cost, score
from .vault import MAX_LTV_PIPS, Vault
from .v4_math import Q128, amount_delta_for_range_scaled, sqrt_price_x96_to_price

getcontext().prec = 60


def run_strategy(
    strategy_path: str | Path,
    bundle: str = "smoke",
    seed: int = 1,
    out_dir: str | Path = "runs",
    progress_callback: Callable[[dict[str, Any], int, int, Any], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    fail_fast_errors: bool = False,
) -> dict[str, Any]:
    path = Path(strategy_path)
    errors = validate_strategy_source(path)
    if errors and fail_fast_errors:
        raise RuntimeError(" ".join(errors))
    run_id = hashlib.sha256(f"{path}:{bundle}:{seed}:{ENGINE_VERSION}:{CALIBRATION_HASH}".encode()).hexdigest()[:16]
    run_dir = Path(out_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "strategy_source.py").write_text(path.read_text())
    replay_path = run_dir / "public_replay.jsonl"
    scen = scenario(bundle, seed)
    market_path = generate_market_path(scen, seed)
    market_summary = public_path_summary(market_path)
    pool = Pool(price=scen.market.initial_price, active_liquidity=scen.market.background_liquidity_l, amount_scale=scen.market.accounting_scale)
    apply_dfm_fee_state(pool, scen, market_path[0].regime if market_path else regime_at_step(scen, 0), 0)
    vault = Vault(idle0=scen.market.vault_initial_token0, idle1=scen.market.vault_initial_token1)
    market = AegisMarket(lender_equity_l=scen.market.borrowable_market_equity_l, utilization_cap_pips=scen.market.utilization_cap_pips)
    initial_equity = vault.equity(pool.price, pool.amount_scale)
    exposure_abs_usd_values: list[Decimal] = []
    costs = Decimal("0")
    invalid_penalty = Decimal("0")
    borrow_interest = Decimal("0")
    recent_swaps = ()
    recent_fills = ()
    recent_repairs = ()
    breakdown = ScoreBreakdown()
    liquidation_penalty = Decimal("0")
    worker = None if errors else StrategyWorker(path)
    events: list[dict[str, Any]] = []
    state = make_state(0, scen, run_id, pool, vault, recent_swaps, recent_fills, breakdown, recent_repairs, market_path[0].regime if market_path else regime_at_step(scen, 0))
    try:
        if worker:
            worker.on_start(state)
        with replay_path.open("w") as replay:
            for step in range(scen.steps):
                if cancel_callback and cancel_callback():
                    raise RuntimeError("ERR_CANCELLED")
                market_step = market_path[step]
                active_regime = market_step.regime
                dfm_state = apply_dfm_fee_state(pool, scen, active_regime, step)
                step_open_price = pool.price
                borrow_interest += market.accrue(scen.step_length_seconds)
                vault.borrow_index = market.borrow_index_wad
                hidden_fair = market_step.fair_price
                state = make_state(step, scen, run_id, pool, vault, recent_swaps, recent_fills, breakdown, recent_repairs, active_regime)
                actions = []
                step_errors = list(errors)
                step_swaps: list[SwapEvent] = []
                step_fills: list[FillEvent] = []
                step_repairs: list[RepairEvent] = []
                step_actions: list[dict[str, Any]] = []
                retail_count = market_step.retail_count
                prefix_count = market_latency_prefix_count(market_step, scen.priority_model, retail_count)
                for external_index in range(prefix_count):
                    swap = execute_retail_swap(pool, market_step, external_index)
                    fills = settle_limit_order_fills(vault, pool, swap)
                    step_swaps.append(swap)
                    step_fills.extend(fills)
                if worker and not errors:
                    try:
                        actions = worker.on_step(state) or []
                    except RuntimeError as exc:
                        step_errors.append(str(exc))
                        invalid_penalty += initial_equity * Decimal("0.001")
                        errors.append(str(exc))
                        if fail_fast_errors:
                            raise
                if len(actions) > 32:
                    step_errors.append("ERR_ACTION_LIMIT")
                    actions = []
                for index, action in enumerate(actions):
                    vault_before = deepcopy(vault)
                    pool_before = deepcopy(pool)
                    market_before = deepcopy(market)
                    action_record: dict[str, Any] = {
                        "step": step,
                        "action_index": index,
                        "action_type": type(action).__name__,
                        "payload": to_jsonable(action),
                        "status": "pending",
                        "action_cost_usd": "0",
                        "swap_event_indices": [],
                        "fill_event_indices": [],
                    }
                    try:
                        action_cost_delta, swaps, fills = apply_action(action, vault, pool, market, step)
                        costs += action_cost_delta
                        step_swaps.extend(swaps)
                        step_fills.extend(fills)
                        action_record.update(
                            {
                                "status": "executed",
                                "action_cost_usd": str(action_cost_delta),
                                "swap_event_indices": [swap.event_index for swap in swaps],
                                "fill_event_indices": [fill.event_index for fill in fills],
                            }
                        )
                    except ValueError as exc:
                        vault.__dict__.update(vault_before.__dict__)
                        pool.__dict__.update(pool_before.__dict__)
                        market.__dict__.update(market_before.__dict__)
                        step_errors.append(str(exc))
                        invalid_penalty += initial_equity * Decimal("0.001")
                        action_record.update({"status": "rejected", "error": str(exc)})
                        step_actions.append(action_record)
                        break
                    step_actions.append(action_record)
                if scen.priority_model == "backrun_stress" and step_swaps and any(s.actor == "strategy" for s in step_swaps):
                    swap = execute_arbitrage_swap(pool, step, hidden_fair)
                    if swap is not None:
                        fills = settle_limit_order_fills(vault, pool, swap)
                        step_swaps.append(swap)
                        step_fills.extend(fills)
                for external_index in range(prefix_count, retail_count):
                    swap = execute_retail_swap(pool, market_step, external_index)
                    fills = settle_limit_order_fills(vault, pool, swap)
                    step_swaps.append(swap)
                    step_fills.extend(fills)
                swap = execute_arbitrage_swap(pool, step, hidden_fair)
                if swap is not None:
                    fills = settle_limit_order_fills(vault, pool, swap)
                    step_swaps.append(swap)
                    step_fills.extend(fills)
                settle_position_fees(vault, pool)
                repair = repair_vault(vault, pool, market, step)
                if repair is not None:
                    step_repairs.append(repair)
                    liquidation_penalty += repair.keeper_fee0 * pool.price + repair.keeper_fee1
                recent_swaps = tuple(step_swaps)
                recent_fills = tuple(step_fills)
                recent_repairs = tuple(step_repairs)
                instant_state = vault.state(pool.price, pool.amount_scale)
                exposure_abs_usd_values.append(abs(instant_state.eth_exposure_usd))
                avg_abs_exposure = sum(exposure_abs_usd_values, Decimal("0")) / Decimal(len(exposure_abs_usd_values))
                max_abs_exposure = max(exposure_abs_usd_values)
                breakdown = score(
                    vault,
                    pool.price,
                    initial_equity,
                    costs,
                    invalid_penalty,
                    borrow_interest,
                    liquidation_penalty,
                    pool.amount_scale,
                    avg_abs_exposure,
                    max_abs_exposure,
                )
                elapsed_days = simulated_days_for_steps(step + 1, scen.step_length_seconds)
                money = money_metrics(
                    scen,
                    vault,
                    pool,
                    breakdown,
                    initial_equity,
                    borrow_interest,
                    liquidation_penalty,
                    avg_abs_exposure,
                    max_abs_exposure,
                    elapsed_days,
                )
                event = {
                    "step": step,
                    "timestamp": step * scen.step_length_seconds,
                    "simulated_day": str((Decimal(step * scen.step_length_seconds) / Decimal(86400)).quantize(Decimal("0.0001"))),
                    "elapsed_simulated_days": str(elapsed_days.quantize(Decimal("0.0001"))),
                    "regime": active_regime,
                    "public_run_id": run_id,
                    "price": str(pool.price),
                    "eth_price_usdc": str(pool.price),
                    "tick": pool.tick,
                    "score": str(breakdown.scenario_score),
                    "avg_eth_exposure_usd": str(avg_abs_exposure),
                    "max_eth_exposure_usd": str(max_abs_exposure),
                    **to_jsonable(money),  # type: ignore[arg-type]
                    "pool": to_jsonable(pool.state()),
                    "vault": to_jsonable(vault.state(pool.price, pool.amount_scale)),
                    "recent_swaps": to_jsonable(recent_swaps),
                    "recent_fills": to_jsonable(recent_fills),
                    "recent_repairs": to_jsonable(recent_repairs),
                    "strategy_actions": step_actions,
                    "dfm": to_jsonable(dfm_state),
                    "market_path": to_jsonable(public_step_stats(market_step)),
                    "market_stats": to_jsonable(market_stats_for_step(scen, step, active_regime, step_open_price, pool, step_swaps, step_actions, market_step)),
                    "strategy_stats": to_jsonable(strategy_stats_for_step(vault, pool, breakdown, initial_equity)),
                    "errors": step_errors,
                }
                replay.write(json.dumps(event, sort_keys=True) + "\n")
                events.append(event)
                if progress_callback:
                    progress_callback(event, step + 1, scen.steps, scen)
    finally:
        if worker:
            worker.close()
    avg_exposure = sum(exposure_abs_usd_values, Decimal("0")) / Decimal(len(exposure_abs_usd_values)) if exposure_abs_usd_values else Decimal("0")
    max_exposure = max(exposure_abs_usd_values) if exposure_abs_usd_values else Decimal("0")
    final_elapsed_days = simulated_days_for_steps(scen.steps, scen.step_length_seconds)
    final_money = money_metrics(
        scen,
        vault,
        pool,
        breakdown,
        initial_equity,
        borrow_interest,
        liquidation_penalty,
        avg_exposure,
        max_exposure,
        final_elapsed_days,
    )
    score_doc = {
        "run_id": run_id,
        "strategy": path.name,
        "bundle": bundle,
        "public_seed": seed if not bundle.startswith("hidden") else None,
        "score_breakdown": to_jsonable(breakdown),
        **to_jsonable(final_money),  # type: ignore[arg-type]
        "avg_eth_exposure_usd": str(avg_exposure),
        "max_eth_exposure_usd": str(max_exposure),
        "disqualified": bool(errors),
        "errors": errors,
        "market": market_metadata(scen, initial_equity),
        "market_engine": to_jsonable(market_summary),
    }
    (run_dir / "score.json").write_text(json.dumps(score_doc, indent=2, sort_keys=True) + "\n")
    (run_dir / "comparison.json").write_text(json.dumps({"current": run_id, "starter": None, "noop": None, "personal_best": run_id}, indent=2) + "\n")
    calibration_doc = {
        "bundle": bundle,
        "seed": seed if not bundle.startswith("hidden") else None,
        "steps": scen.steps,
        "step_length_seconds": scen.step_length_seconds,
        "regime": scen.regime,
        "priority_model": scen.priority_model,
        "fee_model": scen.fee_model,
        "hidden_horizon_label": scen.hidden_horizon_label,
        "simulated_days": str((Decimal(scen.steps * scen.step_length_seconds) / Decimal(86400)).quantize(Decimal("0.0001"))),
        "regime_schedule": list(scen.regime_schedule),
        "market_engine": to_jsonable(market_summary),
        "market": {
            "token0_symbol": scen.market.token0_symbol,
            "token1_symbol": scen.market.token1_symbol,
            "base_token": scen.market.base_token,
            "risk_token": scen.market.risk_token,
            "quote_token": scen.market.quote_token,
            "pool_pair": scen.market.pool_pair,
            "token0_decimals": scen.market.token0_decimals,
            "token1_decimals": scen.market.token1_decimals,
            "price_convention": scen.market.price_convention,
            "initial_price": str(scen.market.initial_price),
            "initial_price_usdc_per_eth": str(scen.market.initial_price),
            "initial_balance_usdc": str(initial_equity),
            "initial_cash_usdc": str(scen.market.initial_cash_usdc),
            "initial_eth": str(scen.market.initial_eth),
            "vault_initial_token0": str(scen.market.vault_initial_token0),
            "vault_initial_token1": str(scen.market.vault_initial_token1),
            "background_liquidity_l": scen.market.background_liquidity_l,
            "borrowable_market_equity_l": scen.market.borrowable_market_equity_l,
            "utilization_cap_pips": scen.market.utilization_cap_pips,
            "daily_volume_to_tvl_target": str(scen.market.daily_volume_to_tvl_target),
            "accounting_scale": scen.market.accounting_scale,
        },
    }
    (run_dir / "calibration.json").write_text(json.dumps(calibration_doc, indent=2, sort_keys=True) + "\n")
    write_raw_exports(run_dir, score_doc, calibration_doc, events)
    return {"run_id": run_id, "run_dir": str(run_dir), "score": score_doc, "events": events}


def make_state(step, scen, run_id, pool, vault, recent_swaps, recent_fills, breakdown, recent_repairs=(), active_regime=None):
    initial_equity = scen.market.initial_cash_usdc + scen.market.initial_eth * scen.market.initial_price
    vstate = vault.state(pool.price, pool.amount_scale)
    profit_usd = breakdown.net_profit_usd_after_penalties or breakdown.scenario_score
    apr_pct = annualized_apr_pct(profit_usd, initial_equity, simulated_days_for_steps(step, scen.step_length_seconds))
    return State(
        step=step,
        timestamp=step * scen.step_length_seconds,
        price=pool.price,
        tick=pool.tick,
        twap=pool.price,
        recent_swaps=recent_swaps,
        recent_fills=recent_fills,
        recent_repairs=recent_repairs,
        pool=pool.state(),
        vault=vault.state(pool.price, pool.amount_scale),
        positions=marked_positions(vault, pool),
        limit_orders=tuple(vault.limit_orders),
        score_so_far=breakdown.scenario_score,
        score_breakdown=breakdown,
        config=__import__("aegis_challenge.api", fromlist=["PublicConfig"]).PublicConfig(
            scenario_name=scen.bundle,
            public_run_id=run_id,
            step_length_seconds=scen.step_length_seconds,
            token0_symbol=scen.market.token0_symbol,
            token1_symbol=scen.market.token1_symbol,
            base_token=scen.market.base_token,
            risk_token=scen.market.risk_token,
            quote_token=scen.market.quote_token,
            pool_pair=scen.market.pool_pair,
            token0_decimals=scen.market.token0_decimals,
            token1_decimals=scen.market.token1_decimals,
            price_convention=scen.market.price_convention,
            initial_price=scen.market.initial_price,
            initial_balance_usdc=initial_equity,
            initial_cash_usdc=scen.market.initial_cash_usdc,
            initial_eth=scen.market.initial_eth,
            accounting_scale=scen.market.accounting_scale,
            scenario_steps=scen.steps,
            regime=active_regime or scen.regime,
            priority_model=scen.priority_model,
            fee_model=scen.fee_model,
        ),
        cash_usdc=vstate.cash_usdc,
        eth_inventory=vstate.eth_inventory,
        eth_price=pool.price,
        equity_usd=vstate.equity_usd,
        profit_usd=profit_usd,
        apr_pct=apr_pct or Decimal("0"),
        net_eth_delta=vstate.net_eth_delta,
        eth_exposure_usd=vstate.eth_exposure_usd,
        borrow_cost_usd=breakdown.borrow_cost_usd,
        fees_earned_usd=breakdown.fees_earned_usd,
    )


def market_metadata(scen, initial_equity: Decimal) -> dict[str, Any]:
    return {
        "base_token": scen.market.base_token,
        "risk_token": scen.market.risk_token,
        "quote_token": scen.market.quote_token,
        "pool_pair": scen.market.pool_pair,
        "price_quote": scen.market.price_convention,
        "token0_symbol": scen.market.token0_symbol,
        "token1_symbol": scen.market.token1_symbol,
        "initial_balance_usdc": str(initial_equity),
        "initial_cash_usdc": str(scen.market.initial_cash_usdc),
        "initial_eth": str(scen.market.initial_eth),
        "initial_price_usdc_per_eth": str(scen.market.initial_price),
        "horizon_days": str((Decimal(scen.steps * scen.step_length_seconds) / Decimal(86400)).quantize(Decimal("0.0001"))),
    }


def simulated_days_for_steps(steps: int, step_length_seconds: int) -> Decimal:
    return Decimal(max(0, steps) * step_length_seconds) / Decimal(86400)


def annualized_apr_pct(net_profit: Decimal, initial_equity: Decimal, elapsed_days: Decimal | None) -> Decimal | None:
    if initial_equity <= 0 or elapsed_days is None or elapsed_days <= 0:
        return None
    return (net_profit / initial_equity) * (Decimal("365") / elapsed_days) * Decimal("100")


def money_metrics(
    scen,
    vault: Vault,
    pool: Pool,
    breakdown: ScoreBreakdown,
    initial_equity: Decimal,
    borrow_interest: Decimal,
    liquidation_penalty: Decimal,
    avg_abs_exposure_usd: Decimal = Decimal("0"),
    max_abs_exposure_usd: Decimal = Decimal("0"),
    elapsed_simulated_days: Decimal | None = None,
) -> dict[str, Decimal | None]:
    vstate = vault.state(pool.price, pool.amount_scale)
    net_profit = breakdown.net_profit_usd_after_penalties or breakdown.scenario_score
    raw_profit = breakdown.profit_usd or breakdown.raw_pnl
    apr_pct = annualized_apr_pct(net_profit, initial_equity, elapsed_simulated_days)
    return {
        "initial_balance_usdc": initial_equity,
        "equity_usd": vstate.equity_usd,
        "profit_usd": raw_profit,
        "profit_pct": Decimal("0") if initial_equity == 0 else net_profit * Decimal("100") / initial_equity,
        "apr_pct": apr_pct,
        "elapsed_simulated_days": elapsed_simulated_days,
        "net_profit_usd_after_penalties": net_profit,
        "eth_price_usdc": pool.price,
        "net_eth_delta": vstate.net_eth_delta,
        "eth_exposure_usd": vstate.eth_exposure_usd,
        "avg_eth_exposure_usd": avg_abs_exposure_usd,
        "max_eth_exposure_usd": max_abs_exposure_usd,
        "delta_penalty_usd": breakdown.delta_penalty_usd or breakdown.delta_penalty,
        "exposure_penalty_usd": breakdown.exposure_penalty_usd,
        "fees_earned_usd": breakdown.fees_earned_usd,
        "lo_edge_usd": breakdown.lo_edge_usd,
        "inventory_pnl_usd": breakdown.inventory_pnl_usd,
        "borrow_cost_usd": borrow_interest,
        "repair_cost_usd": liquidation_penalty,
        "liquidation_cost_usd": liquidation_penalty,
    }


def market_stats_for_step(
    scen,
    step: int,
    regime: str,
    opening_price: Decimal,
    pool: Pool,
    swaps: list[SwapEvent],
    actions: list[dict[str, Any]],
    market_step: MarketStep | None = None,
) -> dict[str, Any]:
    execution_swap_count = len(swaps)
    trade_count = sum(swap_child_trade_count(swap) for swap in swaps)
    strategy_trade_count = sum(swap_child_trade_count(swap) for swap in swaps if swap.actor == "strategy")
    retail_trade_count = sum(swap_child_trade_count(swap) for swap in swaps if swap.actor == "retail")
    arbitrage_trade_count = sum(swap_child_trade_count(swap) for swap in swaps if swap.actor == "arbitrage")
    keeper_trade_count = sum(swap_child_trade_count(swap) for swap in swaps if swap.actor == "keeper")
    volume_usd = sum(swap_notional_usd(swap) for swap in swaps)
    lp_fees_usd = sum(swap_fee_usd(swap, "lp_fee_paid") for swap in swaps)
    base_lp_fees_usd = sum(base_lp_fee_usd(swap, pool.dfm_base_fee_pips, pool.lp_fee_pips) for swap in swaps)
    dfm_lp_fee_lift_usd = max(Decimal("0"), lp_fees_usd - base_lp_fees_usd)
    protocol_fees_usd = sum(swap_fee_usd(swap, "protocol_fee_paid") for swap in swaps)
    hook_fees_usd = sum(swap_fee_usd(swap, "hook_fee_paid") for swap in swaps)
    slippages = [swap_price_change_pct(swap) for swap in swaps]
    average_trade_size = Decimal("0") if trade_count == 0 else volume_usd / Decimal(trade_count)
    price_change_pct = Decimal("0") if opening_price <= 0 else (pool.price - opening_price) * Decimal("100") / opening_price
    stats = {
        "period_step": step,
        "period_seconds": scen.step_length_seconds,
        "simulated_day": simulated_days_for_steps(step + 1, scen.step_length_seconds),
        "regime": regime,
        "price_open_usdc_per_eth": opening_price,
        "price_close_usdc_per_eth": pool.price,
        "price_change_pct": price_change_pct,
        "trade_count": trade_count,
        "execution_swap_count": execution_swap_count,
        "retail_trade_count": retail_trade_count,
        "strategy_trade_count": strategy_trade_count,
        "arbitrage_trade_count": arbitrage_trade_count,
        "keeper_trade_count": keeper_trade_count,
        "volume_usd": volume_usd,
        "average_trade_size_usd": average_trade_size,
        "max_trade_size_usd": max([swap_notional_usd(swap) for swap in swaps], default=Decimal("0")),
        "lp_fees_usd": lp_fees_usd,
        "base_lp_fees_usd": base_lp_fees_usd,
        "dfm_lp_fee_lift_usd": dfm_lp_fee_lift_usd,
        "dfm_lp_fee_lift_share": Decimal("0") if lp_fees_usd == 0 else dfm_lp_fee_lift_usd / lp_fees_usd,
        "protocol_fees_usd": protocol_fees_usd,
        "dfm_hook_fees_usd": hook_fees_usd,
        "total_input_fees_usd": lp_fees_usd + protocol_fees_usd + hook_fees_usd,
        "average_price_impact_pct": Decimal("0") if not slippages else sum(slippages, Decimal("0")) / Decimal(len(slippages)),
        "max_price_impact_pct": max(slippages, default=Decimal("0")),
        "ticks_crossed": sum(len(swap.ticks_crossed) for swap in swaps),
        "active_liquidity_l": pool.active_liquidity,
        "strategy_action_count": len(actions),
        "executed_strategy_action_count": sum(1 for action in actions if action.get("status") == "executed"),
    }
    if market_step is not None:
        stats.update(
            {
                "market_engine_version": ENGINE_VERSION,
                "market_calibration_hash": CALIBRATION_HASH,
                "planned_retail_swaps": market_step.retail_count,
                "trade_intensity": market_step.trade_intensity,
                "base_lambda": market_step.base_lambda,
                "stochastic_volatility": market_step.volatility,
                "jump_event": market_step.jump_event,
                "jump_return_pct": market_step.jump_return_pct,
                "flow_imbalance": market_step.flow_imbalance,
                "whale_count": market_step.whale_count,
                "mean_trade_size_usd": market_step.mean_trade_size_usd,
            }
        )
    return stats


def strategy_stats_for_step(vault: Vault, pool: Pool, breakdown: ScoreBreakdown, initial_equity: Decimal) -> dict[str, Any]:
    vstate = vault.state(pool.price, pool.amount_scale)
    cl_liquidity = sum(position.liquidity for position in vault.positions)
    active_cl_liquidity = sum(position.liquidity for position in vault.positions if position.lower_tick <= pool.tick < position.upper_tick)
    lo_liquidity = sum(order.liquidity for order in vault.limit_orders if order.status == "open")
    safe_band_usd = initial_equity * Decimal("0.03")
    exposure_abs = abs(vstate.eth_exposure_usd)
    net_profit = breakdown.net_profit_usd_after_penalties or breakdown.scenario_score
    inventory_pnl = breakdown.inventory_pnl_usd
    fees_and_lo = breakdown.fees_earned_usd + breakdown.lo_edge_usd
    return {
        "uses_aegis_borrow": vault.debt_l > 0,
        "uses_concentrated_liquidity": cl_liquidity > 0,
        "uses_limit_orders": bool(vault.limit_orders),
        "cl_liquidity_l": cl_liquidity,
        "active_cl_liquidity_l": active_cl_liquidity,
        "active_cl_liquidity_share": Decimal("0") if cl_liquidity == 0 else Decimal(active_cl_liquidity) / Decimal(cl_liquidity),
        "limit_order_liquidity_l": lo_liquidity,
        "delta_band_safe": exposure_abs <= safe_band_usd,
        "delta_band_usage": Decimal("0") if safe_band_usd <= 0 else exposure_abs / safe_band_usd,
        "hedge_efficiency": max(Decimal("0"), Decimal("1") - (Decimal("0") if safe_band_usd <= 0 else exposure_abs / safe_band_usd)),
        "inventory_pnl_share_of_profit": Decimal("0") if net_profit == 0 else abs(inventory_pnl) / max(abs(net_profit), Decimal("1")),
        "fee_edge_share_of_profit": Decimal("0") if net_profit == 0 else fees_and_lo / max(abs(net_profit), Decimal("1")),
        "net_eth_delta": vstate.net_eth_delta,
        "eth_exposure_usd": vstate.eth_exposure_usd,
    }


def swap_notional_usd(swap: SwapEvent) -> Decimal:
    pre_price = sqrt_price_x96_to_price(swap.pre_sqrt_price_x96)
    return Decimal(swap.amount_in) * pre_price if swap.token_in == "token0" else Decimal(swap.amount_in)


def swap_child_trade_count(swap: SwapEvent) -> int:
    if swap.actor == "retail":
        return max(1, min(250, int(swap_notional_usd(swap) / Decimal("350"))))
    if swap.actor == "arbitrage":
        return max(1, min(20, int(swap_notional_usd(swap) / Decimal("2500"))))
    return 1


def swap_fee_usd(swap: SwapEvent, attr: str) -> Decimal:
    fee = Decimal(getattr(swap, attr))
    pre_price = sqrt_price_x96_to_price(swap.pre_sqrt_price_x96)
    return fee * pre_price if swap.token_in == "token0" else fee


def base_lp_fee_usd(swap: SwapEvent, base_fee_pips: int, lp_fee_pips: int) -> Decimal:
    return split_base_lp_fee(swap_fee_usd(swap, "lp_fee_paid"), Decimal(base_fee_pips), Decimal(lp_fee_pips))


def split_base_lp_fee(actual_lp_fee_usd: Decimal, base_fee_pips: Decimal, lp_fee_pips: Decimal) -> Decimal:
    if actual_lp_fee_usd <= 0 or lp_fee_pips <= 0:
        return Decimal("0")
    if base_fee_pips >= lp_fee_pips:
        return actual_lp_fee_usd
    return actual_lp_fee_usd * base_fee_pips / lp_fee_pips


def swap_price_change_pct(swap: SwapEvent) -> Decimal:
    pre_price = sqrt_price_x96_to_price(swap.pre_sqrt_price_x96)
    post_price = sqrt_price_x96_to_price(swap.post_sqrt_price_x96)
    if pre_price <= 0:
        return Decimal("0")
    return abs(post_price - pre_price) * Decimal("100") / pre_price


def write_raw_exports(run_dir: Path, score_doc: dict[str, Any], calibration_doc: dict[str, Any], events: list[dict[str, Any]]) -> Path:
    periods = period_rows(events)
    market_path = market_path_rows(events)
    write_jsonl(run_dir / "trades.jsonl", trade_rows(events))
    write_jsonl(run_dir / "actions.jsonl", action_rows(events))
    write_jsonl(run_dir / "fills.jsonl", fill_rows(events))
    write_jsonl(run_dir / "repairs.jsonl", repair_rows(events))
    write_jsonl(run_dir / "debt_snapshots.jsonl", debt_rows(events))
    write_jsonl(run_dir / "period_stats.jsonl", periods)
    write_jsonl(run_dir / "market_path_stats.jsonl", market_path)
    (run_dir / "period_stats.json").write_text(json.dumps(to_jsonable(periods), indent=2, sort_keys=True) + "\n")
    (run_dir / "market_path_stats.json").write_text(json.dumps(to_jsonable(market_path), indent=2, sort_keys=True) + "\n")
    write_period_csv(run_dir / "period_stats.csv", periods)
    write_manifest(run_dir, score_doc, calibration_doc)
    return zip_raw_export(run_dir)


def trade_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        dfm = event.get("dfm", {})
        for swap in event.get("recent_swaps", []):
            row = {
                "run_id": event.get("public_run_id"),
                "step": event.get("step"),
                "simulated_day": event.get("elapsed_simulated_days"),
                "regime": event.get("regime"),
                "price_usdc_per_eth": event.get("price"),
                **swap,
                "notional_usd": str(swap_notional_usd_from_json(swap)),
                "child_trade_count": swap_child_trade_count_from_json(swap),
                "lp_fee_usd": str(swap_fee_usd_from_json(swap, "lp_fee_paid")),
                "base_lp_fee_usd": str(base_lp_fee_usd_from_json(swap, dfm)),
                "dfm_lp_fee_lift_usd": str(dfm_lp_fee_lift_usd_from_json(swap, dfm)),
                "protocol_fee_usd": str(swap_fee_usd_from_json(swap, "protocol_fee_paid")),
                "dfm_hook_fee_usd": str(swap_fee_usd_from_json(swap, "hook_fee_paid")),
                "price_impact_pct": str(swap_price_change_pct_from_json(swap)),
                **dfm,
            }
            rows.append(row)
    return rows


def action_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        for action in event.get("strategy_actions", []):
            rows.append({"run_id": event.get("public_run_id"), "step": event.get("step"), **action})
    return rows


def fill_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        for fill in event.get("recent_fills", []):
            rows.append({"run_id": event.get("public_run_id"), "step": event.get("step"), "simulated_day": event.get("elapsed_simulated_days"), **fill})
    return rows


def repair_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        for repair in event.get("recent_repairs", []):
            rows.append({"run_id": event.get("public_run_id"), "step": event.get("step"), "simulated_day": event.get("elapsed_simulated_days"), **repair})
    return rows


def debt_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": event.get("public_run_id"),
            "step": event.get("step"),
            "simulated_day": event.get("elapsed_simulated_days"),
            "debt_l": event.get("vault", {}).get("debt_l"),
            "borrow_index": event.get("vault", {}).get("borrow_index"),
            "debt_liability0": event.get("vault", {}).get("debt_liability0"),
            "debt_liability1": event.get("vault", {}).get("debt_liability1"),
            "debt_liability_value": event.get("vault", {}).get("debt_liability_value"),
            "ltv_pips": event.get("vault", {}).get("ltv_pips"),
            "collateral_floor_l": event.get("vault", {}).get("collateral_floor_l"),
            "equity_usd": event.get("equity_usd"),
            "net_eth_delta": event.get("net_eth_delta"),
            "eth_exposure_usd": event.get("eth_exposure_usd"),
        }
        for event in events
    ]


def market_path_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        rows.append(
            {
                "run_id": event.get("public_run_id"),
                "step": event.get("step"),
                "simulated_day": event.get("elapsed_simulated_days"),
                **(event.get("market_path") or {}),
            }
        )
    return rows


def period_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        row = {
            "run_id": event.get("public_run_id"),
            "step": event.get("step"),
            "simulated_day": event.get("elapsed_simulated_days"),
            "price_usdc_per_eth": event.get("price"),
            "net_profit_usd_after_penalties": event.get("net_profit_usd_after_penalties"),
            "apr_pct": event.get("apr_pct"),
            "eth_exposure_usd": event.get("eth_exposure_usd"),
            **(event.get("market_stats") or {}),
            **(event.get("strategy_stats") or {}),
            **(event.get("dfm") or {}),
        }
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(to_jsonable(row), sort_keys=True) + "\n")


def write_period_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = sorted({field for row in rows for field in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: to_jsonable(row.get(key, "")) for key in fieldnames})


def write_manifest(run_dir: Path, score_doc: dict[str, Any], calibration_doc: dict[str, Any]) -> None:
    files = [
        "public_replay.jsonl",
        "score.json",
        "calibration.json",
        "comparison.json",
        "trades.jsonl",
        "actions.jsonl",
        "fills.jsonl",
        "repairs.jsonl",
        "debt_snapshots.jsonl",
        "period_stats.jsonl",
        "period_stats.json",
        "period_stats.csv",
        "market_path_stats.jsonl",
        "market_path_stats.json",
    ]
    manifest = {
        "schema": "aegis-vault-raw-simulation-export/v1",
        "run_id": score_doc.get("run_id"),
        "bundle": score_doc.get("bundle"),
        "public_seed": score_doc.get("public_seed"),
        "pool_pair": score_doc.get("market", {}).get("pool_pair"),
        "horizon_days": score_doc.get("market", {}).get("horizon_days"),
        "steps": calibration_doc.get("steps"),
        "step_length_seconds": calibration_doc.get("step_length_seconds"),
        "files": {
            file_name: {
                "bytes": (run_dir / file_name).stat().st_size,
                "sha256": hashlib.sha256((run_dir / file_name).read_bytes()).hexdigest(),
            }
            for file_name in files
            if (run_dir / file_name).exists()
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def zip_raw_export(run_dir: Path) -> Path:
    zip_path = run_dir / "raw_simulation_export.zip"
    files = [
        "manifest.json",
        "public_replay.jsonl",
        "score.json",
        "calibration.json",
        "comparison.json",
        "trades.jsonl",
        "actions.jsonl",
        "fills.jsonl",
        "repairs.jsonl",
        "debt_snapshots.jsonl",
        "period_stats.jsonl",
        "period_stats.json",
        "period_stats.csv",
        "market_path_stats.jsonl",
        "market_path_stats.json",
    ]
    fixed_timestamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_name in files:
            path = run_dir / file_name
            if path.exists():
                info = zipfile.ZipInfo(file_name, date_time=fixed_timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    return zip_path


def ensure_raw_export(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    zip_path = run_dir / "raw_simulation_export.zip"
    score_doc = json.loads((run_dir / "score.json").read_text())
    calibration_doc = json.loads((run_dir / "calibration.json").read_text())
    events = replay(run_dir / "public_replay.jsonl")
    return write_raw_exports(run_dir, score_doc, calibration_doc, events)


def swap_notional_usd_from_json(swap: dict[str, Any]) -> Decimal:
    pre_price = sqrt_price_x96_to_price(int(swap.get("pre_sqrt_price_x96", 0)))
    amount_in = Decimal(str(swap.get("amount_in", "0")))
    return amount_in * pre_price if swap.get("token_in") == "token0" else amount_in


def swap_child_trade_count_from_json(swap: dict[str, Any]) -> int:
    notional = swap_notional_usd_from_json(swap)
    actor = swap.get("actor")
    if actor == "retail":
        return max(1, min(250, int(notional / Decimal("350"))))
    if actor == "arbitrage":
        return max(1, min(20, int(notional / Decimal("2500"))))
    return 1


def swap_fee_usd_from_json(swap: dict[str, Any], attr: str) -> Decimal:
    pre_price = sqrt_price_x96_to_price(int(swap.get("pre_sqrt_price_x96", 0)))
    fee = Decimal(str(swap.get(attr, "0")))
    return fee * pre_price if swap.get("token_in") == "token0" else fee


def base_lp_fee_usd_from_json(swap: dict[str, Any], dfm: dict[str, Any]) -> Decimal:
    return split_base_lp_fee(
        swap_fee_usd_from_json(swap, "lp_fee_paid"),
        Decimal(str(dfm.get("dfm_base_fee_pips", "3000") or "3000")),
        Decimal(str(dfm.get("dfm_lp_fee_pips", dfm.get("dfm_pool_swap_fee_pips", "3000")) or "3000")),
    )


def dfm_lp_fee_lift_usd_from_json(swap: dict[str, Any], dfm: dict[str, Any]) -> Decimal:
    actual = swap_fee_usd_from_json(swap, "lp_fee_paid")
    return max(Decimal("0"), actual - base_lp_fee_usd_from_json(swap, dfm))


def swap_price_change_pct_from_json(swap: dict[str, Any]) -> Decimal:
    pre_price = sqrt_price_x96_to_price(int(swap.get("pre_sqrt_price_x96", 0)))
    post_price = sqrt_price_x96_to_price(int(swap.get("post_sqrt_price_x96", 0)))
    if pre_price <= 0:
        return Decimal("0")
    return abs(post_price - pre_price) * Decimal("100") / pre_price


def execute_retail_swap(pool: Pool, market_step: MarketStep, event_index: int) -> SwapEvent:
    notional_token1 = trade_notional_usd(market_step, event_index)
    token_in = trade_token_in(market_step, pool.price, event_index)
    amount_in = notional_token1 if token_in == "token1" else notional_token1 / max(pool.price, Decimal("0.000001"))
    return pool.swap_exact_in("retail", token_in, amount_in, market_step.step)


def execute_arbitrage_swap(pool: Pool, step: int, hidden_fair: Decimal) -> SwapEvent | None:
    if hidden_fair <= 0 or pool.price <= 0:
        return None
    divergence = abs(pool.price / hidden_fair - Decimal("1"))
    band = Decimal(pool.all_in_fee_pips()) / Decimal("1000000") + Decimal("0.00005")
    if divergence <= band:
        return None
    notional_token1 = min(Decimal("25000"), Decimal(pool.active_liquidity) * pool.price * Decimal("0.005"))
    token_in = "token1" if hidden_fair > pool.price else "token0"
    amount_in = notional_token1 if token_in == "token1" else notional_token1 / max(pool.price, Decimal("0.000001"))
    return pool.swap_exact_in("arbitrage", token_in, amount_in, step)


def apply_action(action, vault: Vault, pool: Pool, market: AegisMarket, step: int) -> tuple[Decimal, tuple[SwapEvent, ...], tuple[FillEvent, ...]]:
    name = type(action).__name__
    swaps: list[SwapEvent] = []
    fills: list[FillEvent] = []
    if isinstance(action, BorrowL):
        if action.amount_l <= 0:
            raise ValueError("ERR_NEGATIVE_OR_ZERO_AMOUNT")
        market.borrow(action.amount_l)
        vault.borrow_index = market.borrow_index_wad
        vault.debt_l += action.amount_l
        removed_liquidity = liquidity_for_principal(action.amount_l, market.borrow_index_wad)
        amount0, amount1 = full_range_amounts_for_liquidity(removed_liquidity, pool.price, pool.tick_spacing, pool.amount_scale)
        vault.idle0 += Decimal(amount0)
        vault.idle1 += Decimal(amount1)
    elif isinstance(action, RepayL):
        requested = vault.debt_l if action.amount_l == "all" else int(action.amount_l)
        if requested <= 0 or vault.debt_l <= 0 or requested > vault.debt_l:
            raise ValueError("ERR_INSUFFICIENT_DEBT")
        bridge = repay_bridge(requested, vault.idle0, vault.idle1, market.borrow_index_wad, pool.price, pool.tick_spacing, pool.amount_scale)
        if bridge["actual_repaid_l"] <= 0:
            raise ValueError("ERR_INSUFFICIENT_IDLE")
        idle0_consumed = Decimal(bridge["idle0_consumed"])
        idle1_consumed = Decimal(bridge["idle1_consumed"])
        if vault.idle0 < idle0_consumed or vault.idle1 < idle1_consumed:
            raise ValueError("ERR_INSUFFICIENT_IDLE")
        vault.idle0 -= idle0_consumed
        vault.idle1 -= idle1_consumed
        vault.debt_l -= bridge["actual_repaid_l"]
        market.repay(bridge["actual_repaid_l"])
        vault.borrow_index = market.borrow_index_wad
    elif isinstance(action, SwapExactIn):
        amount = Decimal(action.amount_in)
        if action.token_in == "token0":
            if vault.idle0 < amount:
                raise ValueError("ERR_INSUFFICIENT_IDLE")
            swap = pool.swap_exact_in("strategy", "token0", amount, step)
            vault.idle0 -= amount
            vault.idle1 += swap.amount_out
        else:
            if vault.idle1 < amount:
                raise ValueError("ERR_INSUFFICIENT_IDLE")
            swap = pool.swap_exact_in("strategy", "token1", amount, step)
            vault.idle1 -= amount
            vault.idle0 += swap.amount_out
        action_fills = settle_limit_order_fills(vault, pool, swap)
        settle_position_fees(vault, pool)
        swaps.append(swap)
        fills.extend(action_fills)
    elif isinstance(action, MintRange):
        if len(vault.positions) + len(vault.limit_orders) >= 4:
            raise ValueError("ERR_MAX_NFTS_EXCEEDED")
        if action.lower_tick >= action.upper_tick or action.lower_tick % pool.tick_spacing or action.upper_tick % pool.tick_spacing:
            raise ValueError("ERR_INVALID_TICK")
        amount0, amount1 = amount_delta_for_range_scaled(action.liquidity, pool.price, action.lower_tick, action.upper_tick, pool.amount_scale)
        if vault.idle0 < amount0 or vault.idle1 < amount1:
            raise ValueError("ERR_INSUFFICIENT_IDLE")
        vault.idle0 -= amount0
        vault.idle1 -= amount1
        seed = ClPosition(vault.next_position_id, action.lower_tick, action.upper_tick, action.liquidity, amount0, amount1)
        vault.positions.append(
            replace(
                seed,
                fee_growth_inside0_last_x128=fee_growth_inside(pool, seed, "token0"),
                fee_growth_inside1_last_x128=fee_growth_inside(pool, seed, "token1"),
            )
        )
        add_range_liquidity(pool, action.lower_tick, action.upper_tick, action.liquidity)
        vault.next_position_id += 1
    elif isinstance(action, IncreaseRange):
        if action.liquidity <= 0:
            raise ValueError("ERR_NEGATIVE_OR_ZERO_AMOUNT")
        settle_position_fees(vault, pool)
        pos = find_position(vault, action.position_id)
        current0, current1 = position_amounts(pool, pos)
        amount0, amount1 = amount_delta_for_range_scaled(action.liquidity, pool.price, pos.lower_tick, pos.upper_tick, pool.amount_scale)
        if vault.idle0 < amount0 or vault.idle1 < amount1:
            raise ValueError("ERR_INSUFFICIENT_IDLE")
        vault.idle0 -= amount0
        vault.idle1 -= amount1
        replace_position(
            vault,
            replace(
                pos,
                liquidity=pos.liquidity + action.liquidity,
                amount0_current=current0 + amount0,
                amount1_current=current1 + amount1,
                fee_growth_inside0_last_x128=fee_growth_inside(pool, pos, "token0"),
                fee_growth_inside1_last_x128=fee_growth_inside(pool, pos, "token1"),
            ),
        )
        add_range_liquidity(pool, pos.lower_tick, pos.upper_tick, action.liquidity)
    elif isinstance(action, DecreaseRange):
        if action.liquidity <= 0:
            raise ValueError("ERR_NEGATIVE_OR_ZERO_AMOUNT")
        settle_position_fees(vault, pool)
        pos = find_position(vault, action.position_id)
        if action.liquidity > pos.liquidity:
            raise ValueError("ERR_INSUFFICIENT_IDLE")
        share = Decimal(action.liquidity) / Decimal(pos.liquidity)
        current0, current1 = position_amounts(pool, pos)
        amount0 = current0 * share
        amount1 = current1 * share
        vault.idle0 += amount0
        vault.idle1 += amount1
        remove_range_liquidity(pool, pos.lower_tick, pos.upper_tick, action.liquidity)
        if action.liquidity == pos.liquidity:
            vault.positions = [p for p in vault.positions if p.position_id != pos.position_id]
        else:
            replace_position(
                vault,
                replace(
                pos,
                liquidity=pos.liquidity - action.liquidity,
                amount0_current=current0 - amount0,
                amount1_current=current1 - amount1,
                    fee_growth_inside0_last_x128=fee_growth_inside(pool, pos, "token0"),
                    fee_growth_inside1_last_x128=fee_growth_inside(pool, pos, "token1"),
                ),
            )
    elif isinstance(action, CollectFees):
        settle_position_fees(vault, pool)
        pos = find_position(vault, action.position_id)
        vault.idle0 += pos.uncollected_fees0
        vault.idle1 += pos.uncollected_fees1
        replace_position(vault, replace(pos, uncollected_fees0=Decimal("0"), uncollected_fees1=Decimal("0")))
    elif isinstance(action, BurnRange):
        settle_position_fees(vault, pool)
        pos = find_position(vault, action.position_id)
        current0, current1 = position_amounts(pool, pos)
        vault.idle0 += current0 + pos.uncollected_fees0
        vault.idle1 += current1 + pos.uncollected_fees1
        vault.positions = [p for p in vault.positions if p.position_id != action.position_id]
        remove_range_liquidity(pool, pos.lower_tick, pos.upper_tick, pos.liquidity)
    elif isinstance(action, PlaceLimitOrder):
        if len(vault.positions) + len(vault.limit_orders) >= 4:
            raise ValueError("ERR_MAX_NFTS_EXCEEDED")
        if action.liquidity <= 0:
            raise ValueError("ERR_NEGATIVE_OR_ZERO_AMOUNT")
        if action.tick % pool.tick_spacing:
            raise ValueError("ERR_INVALID_TICK")
        if action.side == "sell0" and action.tick <= pool.tick:
            raise ValueError("ERR_CROSSED_LIMIT_ORDER")
        if action.side == "sell1" and action.tick >= pool.tick:
            raise ValueError("ERR_CROSSED_LIMIT_ORDER")
        deposit0, deposit1 = amount_delta_for_range_scaled(action.liquidity, pool.price, action.tick, action.tick + pool.tick_spacing, pool.amount_scale)
        if action.side == "sell0":
            if deposit0 <= 0 or deposit1 != 0:
                raise ValueError("ERR_CROSSED_LIMIT_ORDER")
            if vault.idle0 < deposit0:
                raise ValueError("ERR_INSUFFICIENT_IDLE")
            vault.idle0 -= deposit0
        else:
            if deposit1 <= 0 or deposit0 != 0:
                raise ValueError("ERR_CROSSED_LIMIT_ORDER")
            if vault.idle1 < deposit1:
                raise ValueError("ERR_INSUFFICIENT_IDLE")
            vault.idle1 -= deposit1
        vault.limit_orders.append(
            LimitOrder(
                vault.next_order_id,
                action.side,
                action.tick,
                action.liquidity,
                "open",
                deposit0,
                deposit1,
                fee_growth_inside0_last_x128=fee_growth_inside_range(pool, action.tick, action.tick + pool.tick_spacing, "token0"),
                fee_growth_inside1_last_x128=fee_growth_inside_range(pool, action.tick, action.tick + pool.tick_spacing, "token1"),
            )
        )
        add_range_liquidity(pool, action.tick, action.tick + pool.tick_spacing, action.liquidity)
        vault.next_order_id += 1
    elif isinstance(action, CancelLimitOrder):
        order = find_order(vault, action.order_id)
        if order.status == "open":
            remove_range_liquidity(pool, order.tick, order.tick + pool.tick_spacing, order.liquidity)
        amount0, amount1 = cancel_order(order)
        vault.idle0 += amount0
        vault.idle1 += amount1
        vault.limit_orders = [o for o in vault.limit_orders if o.order_id != action.order_id]
    elif isinstance(action, WithdrawLimitOrder):
        order = find_order(vault, action.order_id)
        if order.status != "filled":
            raise ValueError("ERR_POSITION_NOT_FOUND")
        vault.idle0 += order.claimable0
        vault.idle1 += order.claimable1
        vault.limit_orders = [o for o in vault.limit_orders if o.order_id != action.order_id]
    elif isinstance(action, DetachPosition):
        if action.kind == "CL":
            pos = find_position(vault, action.id)
            vault.positions = [p for p in vault.positions if p.position_id != pos.position_id]
            remove_range_liquidity(pool, pos.lower_tick, pos.upper_tick, pos.liquidity)
        else:
            order = find_order(vault, action.id)
            vault.limit_orders = [o for o in vault.limit_orders if o.order_id != order.order_id]
    if vault.ltv_pips(pool.price, pool.amount_scale) > MAX_LTV_PIPS:
        raise ValueError("ERR_MAX_LTV")
    return action_cost(name), tuple(swaps), tuple(fills)


def repair_vault(vault: Vault, pool: Pool, market: AegisMarket, step: int) -> RepairEvent | None:
    initial_ltv = vault.ltv_pips(pool.price, pool.amount_scale)
    repay_pips = repay_fraction_pips(initial_ltv, MAX_LTV_PIPS, vault.state(pool.price, pool.amount_scale).hard_ltv_pips)
    if repay_pips <= 0 or vault.debt_l <= 0:
        return None
    peel = peel_attached_nft(vault, pool, initial_ltv, repay_pips, step)
    if peel is not None:
        return peel
    requested_l = vault.debt_l * repay_pips // 1_000_000
    if requested_l <= 0:
        return None
    swap = swap_for_repair_deficit(vault, pool, market, requested_l, step)
    bridge = repay_bridge(requested_l, vault.idle0, vault.idle1, market.borrow_index_wad, pool.price, pool.tick_spacing, pool.amount_scale)
    actual_repaid_l = int(bridge["actual_repaid_l"])
    if actual_repaid_l <= 0:
        return None

    idle0_consumed = Decimal(bridge["idle0_consumed"])
    idle1_consumed = Decimal(bridge["idle1_consumed"])
    if vault.idle0 < idle0_consumed or vault.idle1 < idle1_consumed:
        return None

    vault.idle0 -= idle0_consumed
    vault.idle1 -= idle1_consumed
    vault.debt_l -= actual_repaid_l
    market.repay(actual_repaid_l)
    vault.borrow_index = market.borrow_index_wad

    fee_pips = keeper_fee_pips(initial_ltv, MAX_LTV_PIPS, vault.state(pool.price, pool.amount_scale).hard_ltv_pips)
    keeper_fee0 = fee_amount(idle0_consumed, fee_pips, pool)
    keeper_fee1 = fee_amount(idle1_consumed, fee_pips, pool)
    keeper_fee0 = min(keeper_fee0, vault.idle0)
    keeper_fee1 = min(keeper_fee1, vault.idle1)
    vault.idle0 -= keeper_fee0
    vault.idle1 -= keeper_fee1

    return RepairEvent(
        event_index=pool.event_index,
        step=step,
        kind="micro_liquidation",
        initial_ltv_pips=initial_ltv,
        repay_pips=repay_pips,
        keeper_fee_pips=fee_pips,
        principal_repaid_l=actual_repaid_l,
        idle0_consumed=idle0_consumed,
        idle1_consumed=idle1_consumed,
        keeper_fee0=keeper_fee0,
        keeper_fee1=keeper_fee1,
        debt_l_after=vault.debt_l,
        ltv_pips_after=vault.ltv_pips(pool.price, pool.amount_scale),
        swap_token_in=swap.token_in if swap else None,
        swap_amount_in=swap.amount_in if swap else Decimal("0"),
        swap_amount_out=swap.amount_out if swap else Decimal("0"),
        swap_ticks_crossed=swap.ticks_crossed if swap else (),
    )


def swap_for_repair_deficit(vault: Vault, pool: Pool, market: AegisMarket, requested_l: int, step: int) -> SwapEvent | None:
    target_liquidity = liquidity_for_principal(requested_l, market.borrow_index_wad)
    amount0_required, amount1_required = full_range_amounts_for_liquidity(target_liquidity, pool.price, pool.tick_spacing, pool.amount_scale)
    zero_for_one, exact_out = micro_liq_swap_deficit(vault.idle0, vault.idle1, amount0_required, amount1_required)
    if exact_out <= 0:
        return None
    token_in = "token0" if zero_for_one else "token1"
    available_in = vault.idle0 if zero_for_one else vault.idle1
    if available_in <= 0:
        return None
    amount_in = find_exact_in_for_min_out(pool, token_in, Decimal(exact_out), Decimal(available_in))
    if amount_in <= 0:
        return None
    if zero_for_one:
        if vault.idle0 < amount_in:
            return None
        swap = pool.swap_exact_in("keeper", "token0", amount_in, step)
        vault.idle0 -= amount_in
        vault.idle1 += swap.amount_out
    else:
        if vault.idle1 < amount_in:
            return None
        swap = pool.swap_exact_in("keeper", "token1", amount_in, step)
        vault.idle1 -= amount_in
        vault.idle0 += swap.amount_out
    return swap


def find_exact_in_for_min_out(pool: Pool, token_in: str, target_out: Decimal, max_input: Decimal) -> Decimal:
    if target_out <= 0 or max_input <= 0:
        return Decimal("0")
    scale = max(1, pool.amount_scale)
    lo = 1
    hi = max(1, int(max_input * Decimal(scale)))
    feasible = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        probe = deepcopy(pool)
        out = probe.swap_exact_in("keeper", token_in, Decimal(mid) / Decimal(scale), -1).amount_out
        if out >= target_out:
            feasible = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return Decimal(feasible) / Decimal(scale)


def peel_attached_nft(vault: Vault, pool: Pool, initial_ltv: int, repay_pips: int, step: int) -> RepairEvent | None:
    fee_pips = 100
    if vault.positions:
        pos = vault.positions[0]
        current0, current1 = position_amounts(pool, pos)
        gross0 = current0 + pos.uncollected_fees0
        gross1 = current1 + pos.uncollected_fees1
        keeper_fee0 = fee_amount(gross0, fee_pips, pool)
        keeper_fee1 = fee_amount(gross1, fee_pips, pool)
        credit0 = gross0 - keeper_fee0
        credit1 = gross1 - keeper_fee1
        vault.idle0 += credit0
        vault.idle1 += credit1
        vault.positions = [p for p in vault.positions if p.position_id != pos.position_id]
        remove_range_liquidity(pool, pos.lower_tick, pos.upper_tick, pos.liquidity)
        return RepairEvent(
            event_index=pool.event_index,
            step=step,
            kind="peel",
            initial_ltv_pips=initial_ltv,
            repay_pips=repay_pips,
            keeper_fee_pips=fee_pips,
            principal_repaid_l=0,
            idle0_consumed=Decimal("0"),
            idle1_consumed=Decimal("0"),
            keeper_fee0=keeper_fee0,
            keeper_fee1=keeper_fee1,
            debt_l_after=vault.debt_l,
            ltv_pips_after=vault.ltv_pips(pool.price, pool.amount_scale),
            idle0_credited=credit0,
            idle1_credited=credit1,
            peeled_kind="CL",
            peeled_id=pos.position_id,
            peeled_liquidity=pos.liquidity,
        )
    if vault.limit_orders:
        order = vault.limit_orders[0]
        gross0, gross1 = cancel_order(order)
        keeper_fee0 = fee_amount(gross0, fee_pips, pool)
        keeper_fee1 = fee_amount(gross1, fee_pips, pool)
        credit0 = gross0 - keeper_fee0
        credit1 = gross1 - keeper_fee1
        vault.idle0 += credit0
        vault.idle1 += credit1
        if order.status == "open":
            remove_range_liquidity(pool, order.tick, order.tick + pool.tick_spacing, order.liquidity)
        vault.limit_orders = [o for o in vault.limit_orders if o.order_id != order.order_id]
        return RepairEvent(
            event_index=pool.event_index,
            step=step,
            kind="peel",
            initial_ltv_pips=initial_ltv,
            repay_pips=repay_pips,
            keeper_fee_pips=fee_pips,
            principal_repaid_l=0,
            idle0_consumed=Decimal("0"),
            idle1_consumed=Decimal("0"),
            keeper_fee0=keeper_fee0,
            keeper_fee1=keeper_fee1,
            debt_l_after=vault.debt_l,
            ltv_pips_after=vault.ltv_pips(pool.price, pool.amount_scale),
            idle0_credited=credit0,
            idle1_credited=credit1,
            peeled_kind="LO",
            peeled_id=order.order_id,
            peeled_liquidity=order.liquidity,
        )
    return None


def find_position(vault: Vault, position_id: int) -> ClPosition:
    pos = next((p for p in vault.positions if p.position_id == position_id), None)
    if pos is None:
        raise ValueError("ERR_POSITION_NOT_FOUND")
    return pos


def fee_amount(amount: Decimal, fee_pips: int, pool: Pool) -> Decimal:
    if pool.amount_scale <= 1:
        return Decimal(int(amount) * fee_pips // 1_000_000)
    raw = int(amount * Decimal(pool.amount_scale))
    return Decimal(raw * fee_pips // 1_000_000) / Decimal(pool.amount_scale)


def find_order(vault: Vault, order_id: int) -> LimitOrder:
    order = next((o for o in vault.limit_orders if o.order_id == order_id), None)
    if order is None:
        raise ValueError("ERR_POSITION_NOT_FOUND")
    return order


def replace_position(vault: Vault, updated: ClPosition) -> None:
    vault.positions = [updated if p.position_id == updated.position_id else p for p in vault.positions]


def marked_positions(vault: Vault, pool: Pool) -> tuple[ClPosition, ...]:
    marked = []
    for pos in vault.positions:
        amount0, amount1 = position_amounts(pool, pos)
        marked.append(replace(pos, amount0_current=amount0, amount1_current=amount1))
    return tuple(marked)


def position_amounts(pool: Pool, pos: ClPosition) -> tuple[Decimal, Decimal]:
    return amount_delta_for_range_scaled(pos.liquidity, pool.price, pos.lower_tick, pos.upper_tick, pool.amount_scale)


def add_range_liquidity(pool: Pool, lower_tick: int, upper_tick: int, liquidity: int) -> None:
    pool.initialized_ticks[lower_tick] = pool.initialized_ticks.get(lower_tick, 0) + liquidity
    pool.initialized_ticks[upper_tick] = pool.initialized_ticks.get(upper_tick, 0) - liquidity
    if lower_tick <= pool.tick < upper_tick:
        pool.active_liquidity += liquidity


def remove_range_liquidity(pool: Pool, lower_tick: int, upper_tick: int, liquidity: int) -> None:
    pool.initialized_ticks[lower_tick] = pool.initialized_ticks.get(lower_tick, 0) - liquidity
    pool.initialized_ticks[upper_tick] = pool.initialized_ticks.get(upper_tick, 0) + liquidity
    if lower_tick <= pool.tick < upper_tick:
        pool.active_liquidity = max(1, pool.active_liquidity - liquidity)


def settle_limit_order_fills(vault: Vault, pool: Pool, swap: SwapEvent) -> tuple[FillEvent, ...]:
    fillable = [order for order in vault.limit_orders if should_fill(order, swap)]
    if not fillable:
        return ()
    by_epoch: dict[tuple[int, str], list[LimitOrder]] = {}
    for order in fillable:
        by_epoch.setdefault((order.tick, order.side), []).append(order)

    filled_by_id: dict[int, LimitOrder] = {}
    fills: list[FillEvent] = []
    for (tick, side), orders in by_epoch.items():
        total_liquidity = sum(order.liquidity for order in orders)
        principal0, principal1 = amount_delta_for_range_scaled(total_liquidity, pool.price, tick, tick + pool.tick_spacing, pool.amount_scale)
        fee_growth0_end = fee_growth_inside_range(pool, tick, tick + pool.tick_spacing, "token0")
        fee_growth1_end = fee_growth_inside_range(pool, tick, tick + pool.tick_spacing, "token1")
        scale = Decimal(max(1, pool.amount_scale))
        bucket0 = int(principal0 * scale)
        bucket1 = int(principal1 * scale)
        fee0_by_order = {
            order.order_id: max(0, fee_growth0_end - order.fee_growth_inside0_last_x128) * order.liquidity * pool.amount_scale // Q128
            for order in orders
        }
        fee1_by_order = {
            order.order_id: max(0, fee_growth1_end - order.fee_growth_inside1_last_x128) * order.liquidity * pool.amount_scale // Q128
            for order in orders
        }
        remaining0 = bucket0 + sum(fee0_by_order.values())
        remaining1 = bucket1 + sum(fee1_by_order.values())
        for index, order in enumerate(orders):
            if index == len(orders) - 1:
                claimable0 = Decimal(remaining0) / scale
                claimable1 = Decimal(remaining1) / scale
            else:
                claim0_int = bucket0 * order.liquidity // total_liquidity + fee0_by_order[order.order_id]
                claim1_int = bucket1 * order.liquidity // total_liquidity + fee1_by_order[order.order_id]
                claimable0 = Decimal(claim0_int) / scale
                claimable1 = Decimal(claim1_int) / scale
                remaining0 -= claim0_int
                remaining1 -= claim1_int
            filled = replace(
                order,
                status="filled",
                deposited0=Decimal("0"),
                deposited1=Decimal("0"),
                claimable0=claimable0,
                claimable1=claimable1,
                filled_step=swap.step,
            )
            filled_by_id[order.order_id] = filled
            amount_in = order.deposited0 if side == "sell0" else order.deposited1
            amount_out = claimable1 if side == "sell0" else claimable0
            fills.append(
                FillEvent(
                    event_index=swap.event_index,
                    step=swap.step,
                    order_id=order.order_id,
                    side=side,  # type: ignore[arg-type]
                    tick=tick,
                    liquidity_filled=order.liquidity,
                    amount_in=amount_in,
                    amount_out=amount_out,
                    claimable0=claimable0,
                    claimable1=claimable1,
                )
            )
        remove_range_liquidity(pool, tick, tick + pool.tick_spacing, total_liquidity)

    vault.limit_orders = [filled_by_id.get(order.order_id, order) for order in vault.limit_orders]
    return tuple(fills)


def fee_growth_inside(pool: Pool, pos: ClPosition, token: str) -> int:
    return fee_growth_inside_range(pool, pos.lower_tick, pos.upper_tick, token)


def fee_growth_inside_range(pool: Pool, lower_tick: int, upper_tick: int, token: str) -> int:
    if token == "token0":
        global_growth = pool.fee_growth_global0_x128
        lower_outside = pool.fee_growth_outside0_x128.get(lower_tick, 0)
        upper_outside = pool.fee_growth_outside0_x128.get(upper_tick, 0)
    else:
        global_growth = pool.fee_growth_global1_x128
        lower_outside = pool.fee_growth_outside1_x128.get(lower_tick, 0)
        upper_outside = pool.fee_growth_outside1_x128.get(upper_tick, 0)
    below = lower_outside if pool.tick >= lower_tick else global_growth - lower_outside
    above = upper_outside if pool.tick < upper_tick else global_growth - upper_outside
    return max(0, global_growth - below - above)


def settle_position_fees(vault: Vault, pool: Pool) -> None:
    updated: list[ClPosition] = []
    for pos in vault.positions:
        inside0 = fee_growth_inside(pool, pos, "token0")
        inside1 = fee_growth_inside(pool, pos, "token1")
        delta0 = max(0, inside0 - pos.fee_growth_inside0_last_x128)
        delta1 = max(0, inside1 - pos.fee_growth_inside1_last_x128)
        scale = Decimal(max(1, pool.amount_scale))
        owed0 = Decimal(pos.liquidity * pool.amount_scale * delta0 // Q128) / scale
        owed1 = Decimal(pos.liquidity * pool.amount_scale * delta1 // Q128) / scale
        updated.append(
            replace(
                pos,
                uncollected_fees0=pos.uncollected_fees0 + owed0,
                uncollected_fees1=pos.uncollected_fees1 + owed1,
                fee_growth_inside0_last_x128=inside0,
                fee_growth_inside1_last_x128=inside1,
            )
        )
    vault.positions = updated


def replay(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    RepairEvent,
