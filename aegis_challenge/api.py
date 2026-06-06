from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from typing import Literal, Union


def D(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class InitializedTick:
    tick: int
    liquidity_gross: int
    liquidity_net: int
    fee_growth_outside0_x128: int = 0
    fee_growth_outside1_x128: int = 0


@dataclass(frozen=True)
class SwapEvent:
    event_index: int
    step: int
    actor: Literal["strategy", "retail", "arbitrage", "keeper"]
    token_in: Literal["token0", "token1"]
    amount_in: Decimal
    amount_out: Decimal
    pre_tick: int
    post_tick: int
    pre_sqrt_price_x96: int
    post_sqrt_price_x96: int
    ticks_crossed: tuple[int, ...]
    lp_fee_paid: Decimal
    protocol_fee_paid: Decimal
    hook_fee_paid: Decimal


@dataclass(frozen=True)
class FillEvent:
    event_index: int
    step: int
    order_id: int
    side: Literal["sell0", "sell1"]
    tick: int
    liquidity_filled: int
    amount_in: Decimal
    amount_out: Decimal
    claimable0: Decimal
    claimable1: Decimal


@dataclass(frozen=True)
class RepairEvent:
    event_index: int
    step: int
    kind: Literal["micro_liquidation", "peel"]
    initial_ltv_pips: int
    repay_pips: int
    keeper_fee_pips: int
    principal_repaid_l: int
    idle0_consumed: Decimal
    idle1_consumed: Decimal
    keeper_fee0: Decimal
    keeper_fee1: Decimal
    debt_l_after: int
    ltv_pips_after: int
    idle0_credited: Decimal = Decimal("0")
    idle1_credited: Decimal = Decimal("0")
    peeled_kind: Literal["CL", "LO"] | None = None
    peeled_id: int | None = None
    peeled_liquidity: int | None = None
    swap_token_in: Literal["token0", "token1"] | None = None
    swap_amount_in: Decimal = Decimal("0")
    swap_amount_out: Decimal = Decimal("0")
    swap_ticks_crossed: tuple[int, ...] = ()


@dataclass(frozen=True)
class ClPosition:
    position_id: int
    lower_tick: int
    upper_tick: int
    liquidity: int
    amount0_current: Decimal
    amount1_current: Decimal
    uncollected_fees0: Decimal = Decimal("0")
    uncollected_fees1: Decimal = Decimal("0")
    fee_growth_inside0_last_x128: int = 0
    fee_growth_inside1_last_x128: int = 0


@dataclass(frozen=True)
class LimitOrder:
    order_id: int
    side: Literal["sell0", "sell1"]
    tick: int
    liquidity: int
    status: Literal["open", "filled"]
    deposited0: Decimal
    deposited1: Decimal
    claimable0: Decimal = Decimal("0")
    claimable1: Decimal = Decimal("0")
    filled_step: int | None = None
    fee_growth_inside0_last_x128: int = 0
    fee_growth_inside1_last_x128: int = 0


@dataclass(frozen=True)
class ScoreBreakdown:
    raw_pnl: Decimal = Decimal("0")
    cl_fee_pnl: Decimal = Decimal("0")
    lo_edge_pnl: Decimal = Decimal("0")
    inventory_mark_pnl: Decimal = Decimal("0")
    borrow_interest_attribution: Decimal = Decimal("0")
    action_costs: Decimal = Decimal("0")
    delta_penalty: Decimal = Decimal("0")
    liquidation_penalty: Decimal = Decimal("0")
    invalid_action_penalty: Decimal = Decimal("0")
    scenario_score: Decimal = Decimal("0")
    disqualified: bool = False
    disqualification_reason: str | None = None
    loss_explanations: tuple[str, ...] = ()
    equity_usd: Decimal = Decimal("0")
    profit_usd: Decimal = Decimal("0")
    profit_pct: Decimal = Decimal("0")
    apr_pct: Decimal = Decimal("0")
    net_profit_usd_after_penalties: Decimal = Decimal("0")
    delta_penalty_usd: Decimal = Decimal("0")
    exposure_penalty_usd: Decimal = Decimal("0")
    fees_earned_usd: Decimal = Decimal("0")
    lo_edge_usd: Decimal = Decimal("0")
    inventory_pnl_usd: Decimal = Decimal("0")
    borrow_cost_usd: Decimal = Decimal("0")
    repair_cost_usd: Decimal = Decimal("0")
    liquidation_cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class PoolState:
    sqrt_price_x96: int
    tick: int
    tick_spacing: int
    full_range_min_tick: int
    full_range_max_tick: int
    active_liquidity: int
    initialized_ticks: tuple[InitializedTick, ...]
    fee_pips: int
    lp_fee_pips: int
    protocol_fee_pips: int
    pool_swap_fee_pips: int
    hook_fee_ppm: int
    hook_fee_pips_estimate: int
    all_in_input_fee_pips_estimate: int
    dynamic_fee_active: bool
    fee_surge_active: bool
    dfm_base_fee_pips: int = 3000
    dfm_lp_fee_pips: int = 3000
    dfm_surge_fee_pips: int = 0
    dfm_hook_fee_pips_estimate: int = 0
    dfm_total_fee_pips_estimate: int = 3000
    dfm_fee_multiplier: Decimal = Decimal("1")
    dfm_surge_reason: str | None = None
    dfm_surge_start_step: int | None = None
    dfm_surge_end_step: int | None = None
    fee_growth_global0_x128: int = 0
    fee_growth_global1_x128: int = 0
    pending_hook_fees0: Decimal = Decimal("0")
    pending_hook_fees1: Decimal = Decimal("0")
    hook_reinvested_liquidity: int = 0
    hook_reinvested0: Decimal = Decimal("0")
    hook_reinvested1: Decimal = Decimal("0")
    accounting_scale: int = 1


@dataclass(frozen=True)
class VaultState:
    idle0: Decimal
    idle1: Decimal
    debt_l: int
    borrow_index: int
    debt_liability0: Decimal
    debt_liability1: Decimal
    debt_liability_value: Decimal
    ltv_pips: int
    max_ltv_pips: int
    hard_ltv_pips: int
    delta: Decimal
    delta_normalized: Decimal
    equity: Decimal
    collateral_floor_l: int
    unlocked: bool = False
    cash_usdc: Decimal = Decimal("0")
    eth_inventory: Decimal = Decimal("0")
    equity_usd: Decimal = Decimal("0")
    net_eth_delta: Decimal = Decimal("0")
    eth_exposure_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class PublicConfig:
    scenario_name: str
    public_run_id: str
    step_length_seconds: int
    token0_symbol: str = "ETH"
    token1_symbol: str = "USDC"
    base_token: str = "USDC"
    risk_token: str = "ETH"
    quote_token: str = "USDC"
    pool_pair: str = "ETH/USDC"
    token0_decimals: int = 18
    token1_decimals: int = 6
    price_convention: str = "USDC per ETH"
    initial_price: Decimal = Decimal("2000")
    initial_balance_usdc: Decimal = Decimal("100000")
    initial_cash_usdc: Decimal = Decimal("100000")
    initial_eth: Decimal = Decimal("0")
    accounting_scale: int = 1
    scenario_steps: int = 0
    regime: str = "calm"
    market_flow_model: Literal["stylized_calibrated"] = "stylized_calibrated"
    priority_model: Literal["baseline_batch", "backrun_stress", "latency_stress"] = "baseline_batch"
    fee_model: Literal["static", "aegis_dynamic"] = "static"
    action_cost_model: Literal["gas_calibrated"] = "gas_calibrated"


@dataclass(frozen=True)
class State:
    step: int
    timestamp: int
    price: Decimal
    tick: int
    twap: Decimal
    recent_swaps: tuple[SwapEvent, ...]
    recent_fills: tuple[FillEvent, ...]
    pool: PoolState
    vault: VaultState
    positions: tuple[ClPosition, ...]
    limit_orders: tuple[LimitOrder, ...]
    score_so_far: Decimal
    score_breakdown: ScoreBreakdown
    config: PublicConfig
    recent_repairs: tuple[RepairEvent, ...] = ()
    cash_usdc: Decimal = Decimal("0")
    eth_inventory: Decimal = Decimal("0")
    eth_price: Decimal = Decimal("0")
    equity_usd: Decimal = Decimal("0")
    profit_usd: Decimal = Decimal("0")
    apr_pct: Decimal = Decimal("0")
    net_eth_delta: Decimal = Decimal("0")
    eth_exposure_usd: Decimal = Decimal("0")
    borrow_cost_usd: Decimal = Decimal("0")
    fees_earned_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class ActionError:
    code: str
    action_index: int | None
    message: str
    fix_hint: str
    state_excerpt: dict[str, object]


@dataclass(frozen=True)
class BorrowL:
    amount_l: int


@dataclass(frozen=True)
class RepayL:
    amount_l: int | Literal["all"]


@dataclass(frozen=True)
class SwapExactIn:
    token_in: Literal["token0", "token1"]
    amount_in: Decimal
    max_slippage_pips: int = 5000


@dataclass(frozen=True)
class MintRange:
    lower_tick: int
    upper_tick: int
    liquidity: int


@dataclass(frozen=True)
class IncreaseRange:
    position_id: int
    liquidity: int


@dataclass(frozen=True)
class DecreaseRange:
    position_id: int
    liquidity: int


@dataclass(frozen=True)
class CollectFees:
    position_id: int


@dataclass(frozen=True)
class BurnRange:
    position_id: int


@dataclass(frozen=True)
class PlaceLimitOrder:
    side: Literal["sell0", "sell1"]
    tick: int
    liquidity: int


@dataclass(frozen=True)
class CancelLimitOrder:
    order_id: int


@dataclass(frozen=True)
class WithdrawLimitOrder:
    order_id: int


@dataclass(frozen=True)
class DetachPosition:
    kind: Literal["CL", "LO"]
    id: int


Action = Union[
    BorrowL,
    RepayL,
    SwapExactIn,
    MintRange,
    IncreaseRange,
    DecreaseRange,
    CollectFees,
    BurnRange,
    PlaceLimitOrder,
    CancelLimitOrder,
    WithdrawLimitOrder,
    DetachPosition,
]


ERROR_CODES = {
    "ERR_INVALID_SCHEMA",
    "ERR_ACTION_LIMIT",
    "ERR_NEGATIVE_OR_ZERO_AMOUNT",
    "ERR_INSUFFICIENT_IDLE",
    "ERR_INSUFFICIENT_DEBT",
    "ERR_INVALID_TICK",
    "ERR_CROSSED_LIMIT_ORDER",
    "ERR_POSITION_NOT_FOUND",
    "ERR_MAX_NFTS_EXCEEDED",
    "ERR_UTILIZATION_CAP",
    "ERR_MAX_LTV",
    "ERR_ZERO_COLLATERAL_FLOOR",
    "ERR_DELTA_HARD_LIMIT",
    "ERR_SLIPPAGE",
    "ERR_REPLAY_NONDETERMINISTIC",
    "ERR_RESOURCE_LIMIT",
    "ERR_TIMEOUT",
    "ERR_FORBIDDEN_IMPORT",
    "ERR_FORBIDDEN_SIDE_EFFECT",
    "ERR_STRATEGY_EXCEPTION",
    "ERR_SANDBOX_VIOLATION",
}


def to_jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value
