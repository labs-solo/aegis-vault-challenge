from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MarketConfig:
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
    initial_cash_usdc: Decimal = Decimal("100000")
    initial_eth: Decimal = Decimal("0")
    vault_initial_token1: Decimal = Decimal("100000")
    vault_initial_token0: Decimal = Decimal("0")
    background_liquidity_l: int = 2_000_000
    borrowable_market_equity_l: int = 1_000_000
    utilization_cap_pips: int = 950_000
    daily_volume_to_tvl_target: Decimal = Decimal("0.45")
    accounting_scale: int = 1_000_000


@dataclass(frozen=True)
class Scenario:
    bundle: str
    seed: int
    steps: int
    step_length_seconds: int
    regime: str
    priority_model: str
    fee_model: str
    market: MarketConfig = MarketConfig()
    retail_lambda_per_step: Decimal = Decimal("3")
    arbitrage_enabled: bool = True
    hidden_horizon_label: str | None = None
    regime_schedule: tuple[str, ...] = ()


def scenario(bundle: str, seed: int) -> Scenario:
    market = MarketConfig()
    if bundle == "smoke":
        return Scenario(bundle, seed, 60, 60, "calm", "baseline_batch", "static", market, Decimal("2"))
    if bundle == "competition_6m":
        schedule = ("calm", "volatile", "trend_up", "mean_reversion", "trend_down", "jump", "borrow_stress", "low_liquidity", "volatile")
        return Scenario(bundle, seed, 180 * 24 * 4, 15 * 60, "six_month", "latency_stress", "aegis_dynamic", market, Decimal("8"), True, "180d", schedule)
    if bundle == "public_train":
        regime = public_regime(seed)
        priority = "backrun_stress" if seed in (11, 12, 18) else "latency_stress" if seed >= 15 else "baseline_batch"
        return Scenario(bundle, seed, 1440, 60, regime, priority, "aegis_dynamic" if seed % 2 == 0 or seed >= 11 else "static")
    if bundle == "stress_train":
        low_liquidity = seed in (103, 104)
        stress_market = MarketConfig(background_liquidity_l=400_000, borrowable_market_equity_l=200_000) if low_liquidity else market
        regime = "volatile" if seed <= 102 else "low_liquidity" if low_liquidity else "borrow_stress" if seed <= 106 else "jump"
        priority = "backrun_stress" if seed in (103, 104, 108) else "latency_stress" if seed in (101, 102, 107) else "baseline_batch"
        return Scenario(bundle, seed, 1440, 60, regime, priority, "aegis_dynamic", stress_market, Decimal("5"))
    if bundle in {"hidden_ranked", "hidden_stress"}:
        horizons = (720, 1440, 2880)
        steps = horizons[seed % len(horizons)]
        hidden_regimes = ("calm", "volatile", "trend_up", "trend_down", "mean_reversion", "jump", "low_liquidity", "borrow_stress")
        regime = hidden_regimes[seed % len(hidden_regimes)]
        hidden_market = MarketConfig(background_liquidity_l=400_000, borrowable_market_equity_l=200_000) if regime == "low_liquidity" else market
        priority = "backrun_stress" if seed % 3 == 0 else "latency_stress" if seed % 3 == 1 else "baseline_batch"
        return Scenario(bundle, seed, steps, 60, regime, priority, "aegis_dynamic", hidden_market, Decimal("5") if bundle == "hidden_stress" else Decimal("3"), hidden_horizon_label=f"{steps // 60}h")
    return Scenario(bundle, seed, 720, 60, "volatile", "latency_stress", "aegis_dynamic")


def regime_at_step(scen: Scenario, step: int) -> str:
    if not scen.regime_schedule:
        return scen.regime
    index = min(len(scen.regime_schedule) - 1, step * len(scen.regime_schedule) // max(1, scen.steps))
    return scen.regime_schedule[index]


def public_regime(seed: int) -> str:
    seed = ((seed - 1) % 18) + 1
    if seed <= 6:
        return "calm"
    if seed <= 10:
        return "volatile"
    if seed <= 12:
        return "trend_up"
    if seed <= 14:
        return "trend_down"
    if seed <= 17:
        return "mean_reversion"
    return "jump"


def latent_price(seed: int, step: int, current: Decimal, regime: str, initial_price: Decimal = Decimal("2000")) -> Decimal:
    rng = random.Random((seed << 32) + step)
    vol = {
        "calm": Decimal("0.00045"),
        "volatile": Decimal("0.0012"),
        "trend": Decimal("0.00075"),
        "trend_up": Decimal("0.00075"),
        "trend_down": Decimal("0.00075"),
        "mean_reversion": Decimal("0.0008"),
        "jump": Decimal("0.001"),
        "low_liquidity": Decimal("0.0009"),
        "borrow_stress": Decimal("0.00065"),
    }.get(regime, Decimal("0.0007"))
    drift = Decimal("0.00010") if regime in {"trend", "trend_up"} else Decimal("-0.00010") if regime == "trend_down" else Decimal("0")
    if regime == "mean_reversion":
        drift -= Decimal("0.08") * ((current / initial_price) - Decimal("1")) / Decimal("1440")
    shock = Decimal(str(rng.gauss(0, 1))) * vol + drift
    if regime == "jump" and rng.random() < 0.002:
        shock += Decimal("0.015") * (Decimal(1) if rng.random() > 0.5 else Decimal(-1))
    return max(Decimal("0.01"), current * (Decimal("1") + shock))


def retail_notional(seed: int, step: int, regime: str = "calm") -> Decimal:
    rng = random.Random((seed << 16) + step)
    median = {
        "calm": Decimal("2500"),
        "volatile": Decimal("5000"),
        "trend": Decimal("4000"),
        "trend_up": Decimal("4000"),
        "trend_down": Decimal("4000"),
        "mean_reversion": Decimal("3500"),
        "jump": Decimal("7500"),
        "low_liquidity": Decimal("4000"),
        "borrow_stress": Decimal("3000"),
    }.get(regime, Decimal("3500"))
    return median * Decimal(str(rng.lognormvariate(0, 0.65)))


def retail_event_count(seed: int, step: int, lam: Decimal) -> int:
    rng = random.Random((seed << 20) + step)
    # Knuth inversion is overkill for the small configured lambdas, but deterministic.
    limit = Decimal(str(rng.random()))
    probability = (-lam).exp()
    cumulative = probability
    count = 0
    while limit > cumulative and count < 12:
        count += 1
        probability *= lam / Decimal(count)
        cumulative += probability
    return max(1, count)


def latency_prefix_count(seed: int, step: int, priority_model: str, retail_count: int) -> int:
    if priority_model != "latency_stress":
        return 0
    rng = random.Random((seed << 24) + step)
    return int(rng.random() * min(3, retail_count))


def retail_token_in(seed: int, step: int, event_index: int, hidden_fair: Decimal, pool_price: Decimal) -> str:
    rng = random.Random((seed << 28) + step * 97 + event_index)
    skew = (hidden_fair - pool_price) / max(pool_price * Decimal("0.01"), Decimal("0.000001"))
    probability_token1 = Decimal("1") / (Decimal("1") + (-skew).exp())
    return "token1" if Decimal(str(rng.random())) < probability_token1 else "token0"


def dynamic_fee_pips(regime: str, fee_model: str, base_fee_pips: int = 3000) -> int:
    if fee_model != "aegis_dynamic":
        return base_fee_pips
    surge = {
        "calm": 0,
        "volatile": 1200,
        "trend": 800,
        "trend_up": 800,
        "trend_down": 800,
        "mean_reversion": 900,
        "jump": 3000,
        "low_liquidity": 2000,
        "borrow_stress": 1000,
    }.get(regime, 700)
    return min(10_000, base_fee_pips + surge)
