from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Iterable

getcontext().prec = 60

ENGINE_VERSION = "market-engine-v2.0"

CALIBRATION_CONFIG: dict[str, Any] = {
    "source": "reports/base-realism/base-weth-usdc-reference.json",
    "reference_network": "Base",
    "reference_pair": "WETH/USDC",
    "volume_usd_h24_p10": "4829012",
    "volume_usd_h24_p90": "283296773",
    "transactions_h24_p10": "13543",
    "transactions_h24_p90": "179917",
    "price_change_h24_abs_reference_pct": "9.7",
    "fano_min": "1.50",
    "volume_autocorr_lag1_min": "0.10",
    "jump_path_share_min": "0.05",
    "jump_path_share_max": "0.45",
    "dfm_surge_step_share_min": "0.15",
    "dfm_surge_step_share_max": "0.75",
}


def calibration_hash() -> str:
    payload = json.dumps(CALIBRATION_CONFIG, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


CALIBRATION_HASH = calibration_hash()


REGIME_PROFILES: dict[str, dict[str, Decimal]] = {
    "calm": {
        "vol_15m": Decimal("0.0016"),
        "lambda_15m": Decimal("4.5"),
        "median_trade_usd": Decimal("6500"),
        "drift_15m": Decimal("0"),
        "jump_prob_15m": Decimal("0.0004"),
        "jump_size": Decimal("0.010"),
        "whale_prob_15m": Decimal("0.004"),
    },
    "volatile": {
        "vol_15m": Decimal("0.0048"),
        "lambda_15m": Decimal("9.5"),
        "median_trade_usd": Decimal("12000"),
        "drift_15m": Decimal("0"),
        "jump_prob_15m": Decimal("0.0030"),
        "jump_size": Decimal("0.026"),
        "whale_prob_15m": Decimal("0.025"),
    },
    "trend_up": {
        "vol_15m": Decimal("0.0030"),
        "lambda_15m": Decimal("7.5"),
        "median_trade_usd": Decimal("10500"),
        "drift_15m": Decimal("0.00075"),
        "jump_prob_15m": Decimal("0.0012"),
        "jump_size": Decimal("0.018"),
        "whale_prob_15m": Decimal("0.014"),
    },
    "trend_down": {
        "vol_15m": Decimal("0.0032"),
        "lambda_15m": Decimal("8.0"),
        "median_trade_usd": Decimal("11000"),
        "drift_15m": Decimal("-0.00080"),
        "jump_prob_15m": Decimal("0.0014"),
        "jump_size": Decimal("0.019"),
        "whale_prob_15m": Decimal("0.016"),
    },
    "mean_reversion": {
        "vol_15m": Decimal("0.0027"),
        "lambda_15m": Decimal("6.5"),
        "median_trade_usd": Decimal("8500"),
        "drift_15m": Decimal("0"),
        "jump_prob_15m": Decimal("0.0010"),
        "jump_size": Decimal("0.014"),
        "whale_prob_15m": Decimal("0.010"),
    },
    "jump": {
        "vol_15m": Decimal("0.0055"),
        "lambda_15m": Decimal("12.0"),
        "median_trade_usd": Decimal("16000"),
        "drift_15m": Decimal("0"),
        "jump_prob_15m": Decimal("0.0120"),
        "jump_size": Decimal("0.045"),
        "whale_prob_15m": Decimal("0.040"),
    },
    "low_liquidity": {
        "vol_15m": Decimal("0.0042"),
        "lambda_15m": Decimal("5.5"),
        "median_trade_usd": Decimal("9000"),
        "drift_15m": Decimal("0"),
        "jump_prob_15m": Decimal("0.0038"),
        "jump_size": Decimal("0.022"),
        "whale_prob_15m": Decimal("0.018"),
    },
    "borrow_stress": {
        "vol_15m": Decimal("0.0024"),
        "lambda_15m": Decimal("6.2"),
        "median_trade_usd": Decimal("7600"),
        "drift_15m": Decimal("-0.00012"),
        "jump_prob_15m": Decimal("0.0010"),
        "jump_size": Decimal("0.014"),
        "whale_prob_15m": Decimal("0.008"),
    },
}


@dataclass(frozen=True)
class MarketStep:
    path_seed: int
    step: int
    regime: str
    fair_price: Decimal
    log_return: Decimal
    volatility: Decimal
    jump_event: bool
    jump_return_pct: Decimal
    trade_intensity: Decimal
    retail_count: int
    base_lambda: Decimal
    flow_imbalance: Decimal
    whale_count: int
    mean_trade_size_usd: Decimal


def generate_market_path(scen: Any, seed: int) -> tuple[MarketStep, ...]:
    rng = random.Random(_stable_int(f"{ENGINE_VERSION}:{CALIBRATION_HASH}:{scen.bundle}:{seed}:path"))
    fair_price = Decimal(scen.market.initial_price)
    previous_vol = _profile_for_regime(_regime_for_step(scen, 0))["vol_15m"] * _vol_scale(scen.step_length_seconds)
    previous_return = Decimal("0")
    previous_intensity = Decimal("0")
    previous_count = 0
    steps: list[MarketStep] = []
    for step in range(scen.steps):
        regime = _regime_for_step(scen, step)
        profile = _profile_for_regime(regime)
        step_rng = random.Random(_stable_int(f"{seed}:{step}:{ENGINE_VERSION}:{CALIBRATION_HASH}"))
        scale = _time_scale(scen.step_length_seconds)
        base_lambda = max(Decimal("0.35"), profile["lambda_15m"] * scale)
        base_vol = max(Decimal("0.00018"), profile["vol_15m"] * _vol_scale(scen.step_length_seconds))
        seasonality = Decimal(str(1 + 0.18 * math.sin(2 * math.pi * (step % max(1, _steps_per_day(scen))) / max(1, _steps_per_day(scen)))))
        excitation = min(Decimal("6"), Decimal(previous_count) / Decimal("7"))
        cox_noise = Decimal(str(math.exp(step_rng.gauss(-0.08, 0.55))))
        intensity = (
            base_lambda * Decimal("0.42")
            + previous_intensity * Decimal("0.35")
            + excitation * Decimal("0.23")
        ) * seasonality * cox_noise
        intensity = _clamp_decimal(intensity, Decimal("0.20"), max(Decimal("2.5"), base_lambda * Decimal("5")))
        retail_count = max(1, min(32, _poisson(step_rng, intensity)))
        vol_noise = Decimal(str(abs(step_rng.gauss(0, 1)))) * base_vol * Decimal("0.20")
        volatility = _clamp_decimal(
            base_vol * Decimal("0.36") + previous_vol * Decimal("0.48") + abs(previous_return) * Decimal("0.55") + vol_noise,
            base_vol * Decimal("0.55"),
            base_vol * Decimal("4.50"),
        )
        drift = profile["drift_15m"] * scale
        if regime == "mean_reversion":
            drift -= Decimal("0.18") * ((fair_price / Decimal(scen.market.initial_price)) - Decimal("1")) * scale
        jump_probability = _clamp_decimal(profile["jump_prob_15m"] * scale, Decimal("0"), Decimal("0.35"))
        jump_event = step_rng.random() < float(jump_probability)
        jump_return = Decimal("0")
        if jump_event:
            jump_direction = Decimal("1") if step_rng.random() > 0.48 else Decimal("-1")
            jump_return = jump_direction * profile["jump_size"] * Decimal(str(step_rng.lognormvariate(-0.08, 0.42)))
        gaussian_return = Decimal(str(step_rng.gauss(0, 1))) * volatility
        log_return = drift + gaussian_return + jump_return
        fair_price = max(Decimal("0.01"), fair_price * _exp_decimal(log_return))
        whale_count = 0
        whale_probability = _clamp_decimal(profile["whale_prob_15m"] * scale * (Decimal("1") + Decimal(retail_count) / Decimal("16")), Decimal("0"), Decimal("0.80"))
        if step_rng.random() < float(whale_probability):
            whale_count = 1 + (1 if step_rng.random() < 0.08 else 0)
        flow_imbalance = _clamp_decimal(
            Decimal("0.55") * (log_return / max(volatility * Decimal("3"), Decimal("0.000001")))
            + Decimal("0.25") * (drift / max(base_vol, Decimal("0.000001")))
            + Decimal(str(step_rng.gauss(0, 0.18))),
            Decimal("-0.90"),
            Decimal("0.90"),
        )
        mean_trade_size = profile["median_trade_usd"] * (Decimal("0.75") + intensity / max(base_lambda, Decimal("0.000001")) * Decimal("0.25"))
        steps.append(
            MarketStep(
                path_seed=seed,
                step=step,
                regime=regime,
                fair_price=fair_price,
                log_return=log_return,
                volatility=volatility,
                jump_event=jump_event,
                jump_return_pct=jump_return * Decimal("100"),
                trade_intensity=intensity,
                retail_count=retail_count,
                base_lambda=base_lambda,
                flow_imbalance=flow_imbalance,
                whale_count=whale_count,
                mean_trade_size_usd=mean_trade_size,
            )
        )
        previous_vol = volatility
        previous_return = log_return
        previous_intensity = intensity
        previous_count = retail_count
    return tuple(steps)


def trade_notional_usd(step: MarketStep, event_index: int) -> Decimal:
    rng = random.Random(_stable_int(f"{step.path_seed}:{step.step}:{event_index}:notional:{ENGINE_VERSION}"))
    base = step.mean_trade_size_usd * Decimal(str(rng.lognormvariate(-0.20, 0.72)))
    if event_index < step.whale_count:
        base *= Decimal(str(rng.uniform(8.0, 26.0)))
    if step.jump_event:
        base *= Decimal(str(rng.uniform(1.25, 2.75)))
    return max(Decimal("50"), min(Decimal("2500000"), base))


def trade_token_in(step: MarketStep, pool_price: Decimal, event_index: int) -> str:
    rng = random.Random(_stable_int(f"{step.path_seed}:{step.step}:{event_index}:side:{ENGINE_VERSION}"))
    fair_gap = (step.fair_price - pool_price) / max(pool_price * Decimal("0.0125"), Decimal("0.000001"))
    signal = float(_clamp_decimal(fair_gap + step.flow_imbalance, Decimal("-12"), Decimal("12")))
    probability_token1 = 1 / (1 + math.exp(-signal))
    return "token1" if rng.random() < probability_token1 else "token0"


def latency_prefix_count(step: MarketStep, priority_model: str, retail_count: int) -> int:
    if priority_model != "latency_stress":
        return 0
    rng = random.Random(_stable_int(f"{step.path_seed}:{step.step}:latency:{ENGINE_VERSION}"))
    stress_cap = min(4, retail_count)
    return min(stress_cap, int(rng.random() * (stress_cap + 1)))


def public_step_stats(step: MarketStep) -> dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
        "step": step.step,
        "regime": step.regime,
        "stochastic_volatility": step.volatility,
        "jump_event": step.jump_event,
        "jump_return_pct": step.jump_return_pct,
        "trade_intensity": step.trade_intensity,
        "planned_retail_swaps": step.retail_count,
        "base_lambda": step.base_lambda,
        "flow_imbalance": step.flow_imbalance,
        "whale_count": step.whale_count,
        "mean_trade_size_usd": step.mean_trade_size_usd,
    }


def public_path_summary(path: Iterable[MarketStep]) -> dict[str, Any]:
    rows = [public_step_stats(step) for step in path]
    if not rows:
        return {"engine_version": ENGINE_VERSION, "calibration_hash": CALIBRATION_HASH, "path_steps": 0}
    regime_counts: dict[str, int] = {}
    for row in rows:
        regime_counts[str(row["regime"])] = regime_counts.get(str(row["regime"]), 0) + 1
    payload = json.dumps(_json_ready(rows), sort_keys=True, separators=(",", ":"))
    return {
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
        "path_steps": len(rows),
        "public_path_hash": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "regime_counts": regime_counts,
        "jump_event_count": sum(1 for row in rows if row["jump_event"]),
        "planned_retail_swaps": sum(int(row["planned_retail_swaps"]) for row in rows),
        "avg_trade_intensity": sum(Decimal(str(row["trade_intensity"])) for row in rows) / Decimal(len(rows)),
        "avg_stochastic_volatility": sum(Decimal(str(row["stochastic_volatility"])) for row in rows) / Decimal(len(rows)),
    }


def hidden_seed_pack(count: int = 50, pack_id: str = "ranked-v2-default") -> tuple[int, ...]:
    if count < 20 or count > 100:
        raise ValueError("ERR_RANKED_PATH_COUNT_OUT_OF_RANGE")
    return tuple(2_000_000_000 + _stable_int(f"{ENGINE_VERSION}:{CALIBRATION_HASH}:{pack_id}:{index}") % 1_900_000_000 for index in range(count))


def hidden_pack_public(pack_id: str, count: int) -> dict[str, Any]:
    seeds = hidden_seed_pack(count, pack_id)
    payload = json.dumps({"pack_id": pack_id, "count": count, "seeds": seeds, "engine": ENGINE_VERSION, "calibration": CALIBRATION_HASH}, sort_keys=True)
    return {
        "pack_id": pack_id,
        "pack_hash": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "path_count": count,
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
    }


def random_practice_seed() -> int:
    return 1_000_000 + secrets.randbelow(1_000_000_000)


def audit_distribution(scen_factory: Any, bundle: str = "competition_6m", seeds: Iterable[int] | None = None) -> dict[str, Any]:
    seeds = tuple(range(1, 101)) if seeds is None else tuple(seeds)
    daily_volumes: list[Decimal] = []
    trades_per_day: list[Decimal] = []
    per_step_counts: list[Decimal] = []
    per_step_volumes: list[Decimal] = []
    jump_paths = 0
    surge_steps = 0
    total_steps = 0
    realized_vols: list[Decimal] = []
    for seed in seeds:
        scen = scen_factory(bundle, seed)
        path = generate_market_path(scen, seed)
        days = Decimal(scen.steps * scen.step_length_seconds) / Decimal(86400)
        total_volume = Decimal("0")
        total_child_trades = Decimal("0")
        returns: list[Decimal] = []
        path_jumped = False
        for market_step in path:
            notionals = [trade_notional_usd(market_step, index) for index in range(market_step.retail_count)]
            step_volume = sum(notionals, Decimal("0"))
            child_trades = sum(_planned_child_trades(notional) for notional in notionals)
            total_volume += step_volume
            total_child_trades += Decimal(child_trades)
            per_step_counts.append(Decimal(child_trades))
            per_step_volumes.append(step_volume)
            returns.append(market_step.log_return)
            path_jumped = path_jumped or market_step.jump_event or market_step.regime == "jump"
            surge_steps += 1 if market_step.regime != "calm" else 0
            total_steps += 1
        if path_jumped:
            jump_paths += 1
        daily_volumes.append(total_volume / max(days, Decimal("1")))
        trades_per_day.append(total_child_trades / max(days, Decimal("1")))
        realized_vols.append(_stddev(returns) * Decimal(str(math.sqrt(_steps_per_day(scen)))))
    fano = _variance(per_step_counts) / max(_mean(per_step_counts), Decimal("0.000001"))
    volume_autocorr = _lag1_autocorrelation(per_step_volumes)
    jump_path_share = Decimal(jump_paths) / Decimal(max(1, len(seeds)))
    dfm_surge_share = Decimal(surge_steps) / Decimal(max(1, total_steps))
    bands = CALIBRATION_CONFIG
    gates = {
        "volume_day_in_base_band": _mean(daily_volumes) >= Decimal(str(bands["volume_usd_h24_p10"])) and _mean(daily_volumes) <= Decimal(str(bands["volume_usd_h24_p90"])),
        "trades_day_in_base_band": _mean(trades_per_day) >= Decimal(str(bands["transactions_h24_p10"])) and _mean(trades_per_day) <= Decimal(str(bands["transactions_h24_p90"])),
        "fano_factor": fano > Decimal(str(bands["fano_min"])),
        "volume_autocorrelation": volume_autocorr > Decimal(str(bands["volume_autocorr_lag1_min"])),
        "jump_path_share": jump_path_share >= Decimal(str(bands["jump_path_share_min"])) and jump_path_share <= Decimal(str(bands["jump_path_share_max"])),
        "dfm_surge_share": dfm_surge_share >= Decimal(str(bands["dfm_surge_step_share_min"])) and dfm_surge_share <= Decimal(str(bands["dfm_surge_step_share_max"])),
    }
    return {
        "status": "pass" if all(gates.values()) else "fail",
        "engine_version": ENGINE_VERSION,
        "calibration_hash": CALIBRATION_HASH,
        "bundle": bundle,
        "path_count": len(seeds),
        "metrics": _json_ready(
            {
                "mean_volume_usd_per_day": _mean(daily_volumes),
                "mean_trades_per_day": _mean(trades_per_day),
                "mean_realized_volatility_daily": _mean(realized_vols),
                "trade_count_fano_factor": fano,
                "volume_autocorrelation_lag1": volume_autocorr,
                "jump_path_share": jump_path_share,
                "dfm_surge_step_share": dfm_surge_share,
            }
        ),
        "gates": gates,
        "calibration_bands": bands,
    }


def _profile_for_regime(regime: str) -> dict[str, Decimal]:
    return REGIME_PROFILES.get(regime, REGIME_PROFILES["volatile"])


def _regime_for_step(scen: Any, step: int) -> str:
    schedule = getattr(scen, "regime_schedule", ()) or ()
    if not schedule:
        return scen.regime
    index = min(len(schedule) - 1, step * len(schedule) // max(1, scen.steps))
    return schedule[index]


def _time_scale(step_length_seconds: int) -> Decimal:
    return Decimal(max(1, step_length_seconds)) / Decimal(900)


def _vol_scale(step_length_seconds: int) -> Decimal:
    return Decimal(str(math.sqrt(max(1, step_length_seconds) / 900)))


def _steps_per_day(scen: Any) -> int:
    return max(1, int(86400 // max(1, scen.step_length_seconds)))


def _poisson(rng: random.Random, lam: Decimal) -> int:
    lam_float = max(0.001, min(40.0, float(lam)))
    limit = math.exp(-lam_float)
    product = 1.0
    count = 0
    while product > limit and count < 64:
        count += 1
        product *= rng.random()
    return max(0, count - 1)


def _exp_decimal(value: Decimal) -> Decimal:
    return Decimal(str(math.exp(float(_clamp_decimal(value, Decimal("-0.50"), Decimal("0.50"))))))


def _clamp_decimal(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))


def _planned_child_trades(notional: Decimal) -> int:
    return max(1, min(250, int(notional / Decimal("350"))))


def _stable_int(payload: str) -> int:
    return int(hashlib.sha256(payload.encode()).hexdigest()[:16], 16)


def _mean(values: Iterable[Decimal]) -> Decimal:
    items = list(values)
    if not items:
        return Decimal("0")
    return sum(items, Decimal("0")) / Decimal(len(items))


def _variance(values: Iterable[Decimal]) -> Decimal:
    items = list(values)
    if not items:
        return Decimal("0")
    avg = _mean(items)
    return sum((item - avg) * (item - avg) for item in items) / Decimal(len(items))


def _stddev(values: Iterable[Decimal]) -> Decimal:
    return Decimal(str(math.sqrt(float(_variance(values)))))


def _lag1_autocorrelation(values: Iterable[Decimal]) -> Decimal:
    items = list(values)
    if len(items) < 3:
        return Decimal("0")
    avg = _mean(items)
    numerator = sum((items[index] - avg) * (items[index - 1] - avg) for index in range(1, len(items)))
    denominator = sum((item - avg) * (item - avg) for item in items)
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
