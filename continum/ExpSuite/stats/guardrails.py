from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np
from scipy import stats

logger = logging.getLogger("continum.experimentation.guardrails")


class GuardrailStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"  # borderline — watch
    BREACHED = "breached"  # statistically significant violation
    HARD_STOP = "hard_stop"  # absolute threshold crossed — stop immediately


@dataclass(frozen=True)
class GuardrailCheck:
    name: str
    metric: str
    variant: str
    condition: str  # "min" | "max" | "relative_min" | "relative_max"
    threshold: float
    observed: float
    reference: float  # control value (for relative checks)
    p_value: Optional[float]
    ci_lo: Optional[float]
    ci_hi: Optional[float]
    status: GuardrailStatus
    breach_magnitude: float  # how far over the threshold (0 if ok)
    message: str


@dataclass
class GuardrailResult:
    checks: List[GuardrailCheck] = field(default_factory=list)
    any_hard_stop: bool = False
    any_breach: bool = False
    any_warning: bool = False
    stop_experiment: bool = False
    summary_message: str = ""

    def add(self, check: GuardrailCheck) -> None:
        self.checks.append(check)
        if check.status == GuardrailStatus.HARD_STOP:
            self.any_hard_stop = True
            self.stop_experiment = True
        elif check.status == GuardrailStatus.BREACHED:
            self.any_breach = True
            self.stop_experiment = True
        elif check.status == GuardrailStatus.WARNING:
            self.any_warning = True
        self._rebuild_summary()

    def _rebuild_summary(self) -> None:
        n_hard = sum(1 for c in self.checks if c.status == GuardrailStatus.HARD_STOP)
        n_breach = sum(1 for c in self.checks if c.status == GuardrailStatus.BREACHED)
        n_warn = sum(1 for c in self.checks if c.status == GuardrailStatus.WARNING)
        parts = []
        if n_hard:
            parts.append(f"🛑 {n_hard} hard stop(s)")
        if n_breach:
            parts.append(f"❌ {n_breach} breach(es)")
        if n_warn:
            parts.append(f"⚠️  {n_warn} warning(s)")
        if not parts:
            parts.append("✅ All guardrails OK")
        self.summary_message = "  |  ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# GUARDRAIL SPECS
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GuardrailSpec:
    name: str
    metric: str
    condition: str  # "min" | "max" | "relative_min" | "relative_max"
    threshold: float
    severity: str = "breach"
    alpha: float = 0.05


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD GUARDRAIL SPECS (sensible defaults)
# ─────────────────────────────────────────────────────────────────────────────

STANDARD_GUARDRAILS = [
    GuardrailSpec("order_value_floor", "order_value", "min", 500.0, "hard_stop", 0.01),
    GuardrailSpec("aov_no_harm", "order_value", "relative_min", -0.10, "breach", 0.05),
    GuardrailSpec("latency_cap", "page_latency_ms", "max", 3000.0, "breach", 0.05),
    GuardrailSpec("error_rate_cap", "error_rate", "max", 0.02, "hard_stop", 0.01),
    GuardrailSpec("checkout_no_harm", "checkout_rate", "relative_min", -0.05, "breach", 0.05),
    GuardrailSpec("fulfil_no_harm", "fulfil_days", "relative_max", 0.10, "warning", 0.10),
]


# ─────────────────────────────────────────────────────────────────────────────
# ENFORCEMENT
# ─────────────────────────────────────────────────────────────────────────────


def run_guardrail_checks(
    variant: str,
    ctrl_values: Dict[str, np.ndarray],  # {metric_name: array}
    treat_values: Dict[str, np.ndarray],  # {metric_name: array}
    specs: Optional[List[GuardrailSpec]] = None,
) -> GuardrailResult:
    if specs is None:
        specs = STANDARD_GUARDRAILS

    result = GuardrailResult()

    for spec in specs:
        metric = spec.metric
        if metric not in ctrl_values or metric not in treat_values:
            logger.debug("Guardrail %s: metric %s not in data — skipping", spec.name, metric)
            continue

        ctrl = np.asarray(ctrl_values[metric], dtype=float)
        treat = np.asarray(treat_values[metric], dtype=float)
        ctrl = ctrl[~np.isnan(ctrl)]
        treat = treat[~np.isnan(treat)]

        if len(ctrl) < 5 or len(treat) < 5:
            continue

        check = _evaluate_spec(spec, variant, ctrl, treat)
        result.add(check)

    logger.info(
        "Guardrails[%s]: %d checks  |  %s",
        variant,
        len(result.checks),
        result.summary_message,
    )
    return result


def _evaluate_spec(
    spec: GuardrailSpec,
    variant: str,
    ctrl: np.ndarray,
    treat: np.ndarray,
) -> GuardrailCheck:
    ctrl_mean = float(ctrl.mean())
    treat_mean = float(treat.mean())

    # Statistical test
    t_stat, p_val = stats.ttest_ind(ctrl, treat, equal_var=False)
    p_val = float(p_val)

    se = float(np.sqrt(ctrl.var(ddof=1) / len(ctrl) + treat.var(ddof=1) / len(treat)))
    z = float(stats.norm.ppf(1 - spec.alpha / 2))
    ci_lo = treat_mean - ctrl_mean - z * se
    ci_hi = treat_mean - ctrl_mean + z * se

    # Evaluate condition
    if spec.condition == "min":
        breached = treat_mean < spec.threshold
        breach_mag = max(spec.threshold - treat_mean, 0.0)
        observed = treat_mean
        ref = spec.threshold
    elif spec.condition == "max":
        breached = treat_mean > spec.threshold
        breach_mag = max(treat_mean - spec.threshold, 0.0)
        observed = treat_mean
        ref = spec.threshold
    elif spec.condition == "relative_min":
        # treat must not drop by more than |threshold| fraction below control
        rel_change = (treat_mean - ctrl_mean) / abs(ctrl_mean) if ctrl_mean != 0 else 0.0
        breached = rel_change < spec.threshold and p_val < spec.alpha
        breach_mag = max(spec.threshold - rel_change, 0.0) if breached else 0.0
        observed = rel_change
        ref = spec.threshold
        ci_lo = (treat_mean - ctrl_mean - z * se) / abs(ctrl_mean) if ctrl_mean != 0 else ci_lo
        ci_hi = (treat_mean - ctrl_mean + z * se) / abs(ctrl_mean) if ctrl_mean != 0 else ci_hi
    elif spec.condition == "relative_max":
        rel_change = (treat_mean - ctrl_mean) / abs(ctrl_mean) if ctrl_mean != 0 else 0.0
        breached = rel_change > spec.threshold and p_val < spec.alpha
        breach_mag = max(rel_change - spec.threshold, 0.0) if breached else 0.0
        observed = rel_change
        ref = spec.threshold
        ci_lo = (treat_mean - ctrl_mean - z * se) / abs(ctrl_mean) if ctrl_mean != 0 else ci_lo
        ci_hi = (treat_mean - ctrl_mean + z * se) / abs(ctrl_mean) if ctrl_mean != 0 else ci_hi
    else:
        raise ValueError(f"Unknown guardrail condition: {spec.condition!r}")

    # Determine status
    if breached:
        if spec.severity == "hard_stop":
            status = GuardrailStatus.HARD_STOP
        elif spec.severity == "breach":
            status = GuardrailStatus.BREACHED
        else:
            status = GuardrailStatus.WARNING
    elif p_val < spec.alpha * 2:
        # Trending toward a breach but not yet statistically confirmed
        status = GuardrailStatus.WARNING
    else:
        status = GuardrailStatus.OK

    msg = _format_message(spec, status, observed, ref, p_val, breach_mag)

    return GuardrailCheck(
        name=spec.name,
        metric=spec.metric,
        variant=variant,
        condition=spec.condition,
        threshold=spec.threshold,
        observed=round(observed, 6),
        reference=round(ref, 6),
        p_value=round(p_val, 6),
        ci_lo=round(ci_lo, 6),
        ci_hi=round(ci_hi, 6),
        status=status,
        breach_magnitude=round(breach_mag, 6),
        message=msg,
    )


def _format_message(spec, status, observed, ref, p_val, breach_mag) -> str:
    icon = {"ok": "✅", "warning": "⚠️ ", "breached": "❌", "hard_stop": "🛑"}[status.value]
    cond_desc = {
        "min": f"must be ≥ {ref:.4f}",
        "max": f"must be ≤ {ref:.4f}",
        "relative_min": f"must not drop > {abs(ref)*100:.1f}%",
        "relative_max": f"must not rise > {abs(ref)*100:.1f}%",
    }.get(spec.condition, spec.condition)

    if status == GuardrailStatus.OK:
        return f"{icon} {spec.name}: OK (observed={observed:.4f}, {cond_desc})"
    return (
        f"{icon} {spec.name}: {status.value.upper()} — "
        f"observed={observed:.4f} | threshold={ref:.4f} | "
        f"p={p_val:.4f} | breach_by={breach_mag:.4f}"
    )


__all__ = [
    "GuardrailStatus",
    "GuardrailCheck",
    "GuardrailResult",
    "GuardrailSpec",
    "STANDARD_GUARDRAILS",
    "run_guardrail_checks",
]
