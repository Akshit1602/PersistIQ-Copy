from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("continum.dags.analysis")

try:
    from continum.core.experimentation.srm_detector import detect_srm, detect_dimensional_srm
    from continum.core.experimentation.bayesian import beta_binomial_test
    from continum.core.experimentation.sequential import SequentialTester, compute_e_value
    _DEEP_STATS = True
except ImportError:
    _DEEP_STATS = False


# ─────────────────────────────────────────────────────────────────────────────
# TASK / FLOW DECORATORS
# ─────────────────────────────────────────────────────────────────────────────

def task(name: str = "", retries: int = 0, retry_delay_seconds: int = 30):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            logger.info("[TASK] %s starting", name or fn.__name__)
            start = datetime.utcnow()
            for attempt in range(retries + 1):
                try:
                    result = fn(*args, **kwargs)
                    elapsed = (datetime.utcnow() - start).total_seconds()
                    logger.info("[TASK] %s completed in %.2fs", name or fn.__name__, elapsed)
                    return result
                except Exception as e:
                    if attempt < retries:
                        import time
                        logger.warning("[TASK] %s attempt %d/%d failed: %s — retrying",
                                       name or fn.__name__, attempt + 1, retries + 1, e)
                        time.sleep(retry_delay_seconds)
                    else:
                        logger.error("[TASK] %s failed after %d attempts: %s",
                                     name or fn.__name__, retries + 1, e)
                        raise
        wrapper.__name__ = fn.__name__
        wrapper.__doc__  = fn.__doc__
        return wrapper
    return decorator


def flow(name: str = ""):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            logger.info("[FLOW] %s starting", name or fn.__name__)
            start = datetime.utcnow()
            result = fn(*args, **kwargs)
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.info("[FLOW] %s completed in %.2fs", name or fn.__name__, elapsed)
            return result
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# TASK DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

@task(name="load_experiment_data", retries=3, retry_delay_seconds=15)
def load_experiment_data(experiment_id: str, db=None) -> Any:
    import pandas as pd
    if db is None:
        logger.warning("load_experiment_data: no db connection — returning empty DataFrame")
        return pd.DataFrame()
    # Try gold_experiment_analysis first; filter NULL variants produced by LEFT JOINs
    for query in [
        f"SELECT * FROM gold_experiment_analysis WHERE experiment_id = '{experiment_id}' AND variant IS NOT NULL",
        f"SELECT * FROM gold_experiment_analysis WHERE experiment_name = '{experiment_id}' AND variant IS NOT NULL",
        f"SELECT * FROM silver_inquiries WHERE experiment_name = '{experiment_id}' AND variant IS NOT NULL",
        f"SELECT * FROM gold_experiment_analysis WHERE experiment_id = '{experiment_id}'",
        f"SELECT * FROM gold_experiment_analysis WHERE experiment_name = '{experiment_id}'",
    ]:
        try:
            df = db.execute(query).df()
            if len(df) > 0:
                # Drop any remaining NULL-variant rows
                if "variant" in df.columns:
                    df = df[df["variant"].notna()].copy()
                if len(df) > 0:
                    logger.info("Loaded %d rows for experiment %s", len(df), experiment_id)
                    return df
        except Exception:
            continue
    logger.warning("No data found for experiment %s", experiment_id)
    return pd.DataFrame()


@task(name="validate_experiment_data")
def validate_experiment_data_task(df: Any, experiment_id: str) -> Dict[str, Any]:
    import pandas as pd
    report = {"warnings": [], "errors": [], "ok": True}
    if len(df) == 0:
        report["errors"].append("No rows found")
        report["ok"] = False
        return report
    for col in ["converted_to_order", "variant", "created_at"]:
        if col not in df.columns:
            report["errors"].append(f"Required column missing: {col}")
            report["ok"] = False
        else:
            null_pct = df[col].isna().mean() * 100
            if null_pct > 5:
                report["warnings"].append(f"{col}: {null_pct:.1f}% null values")
    if "variant" in df.columns:
        counts = df["variant"].value_counts()
        if len(counts) > 1 and counts.min() / counts.max() < 0.7:
            report["warnings"].append(
                f"Variant imbalance ratio={counts.min()/counts.max():.2f} — possible SRM")
    return report


@task(name="run_primary_analysis")
def run_primary_analysis_task(
    df: Any,
    experiment_id: str,
    experiment_name: str,
    control_variant: str = "control",
    alpha: float = 0.05,
    analyst: str = "system",
) -> Any:
    import numpy as np
    from continum.core.experimentation.statistics import proportion_test, means_test, check_srm
    from continum.artifacts.types import (
        MetricDelta, ExperimentResult, SignificanceVerdict, ShipRecommendation,
    )

    if len(df) == 0:
        raise ValueError(f"Empty dataframe for experiment {experiment_id}")

    df = df.copy()
    df["converted_to_order"] = df["converted_to_order"].fillna(0)

    variants   = sorted(df["variant"].dropna().unique().tolist())
    if not variants:
        raise ValueError(f"No variants found for {experiment_id}")

    # Auto-detect control: prefer exact "control", then any variant containing "control",
    # then "no_" prefix, then the lexicographically first variant
    if control_variant not in variants:
        candidates = [v for v in variants if "control" in v.lower()]
        if not candidates:
            candidates = [v for v in variants if v.lower().startswith("no_")]
        control_variant = candidates[0] if candidates else variants[0]
        logger.info("Auto-detected control variant: %s (from %s)", control_variant, variants)

    treatments = [v for v in variants if v != control_variant]
    if not treatments:
        # Only one variant — treat it as treatment against a synthetic empty control
        logger.warning("Only one variant found: %s — cannot run A/B analysis", variants)
        raise ValueError(f"Need ≥ 2 variants, got: {variants}")
    treatment = treatments[0]

    ctrl_df  = df[df["variant"] == control_variant]
    treat_df = df[df["variant"] == treatment]

    variant_counts = {v: int((df["variant"] == v).sum()) for v in variants}
    srm = check_srm(variant_counts)
    # Deep SRM detection (chi2 + G-test + root-cause hints)
    if _DEEP_STATS:
        try:
            srm_deep = detect_srm(variant_counts)
            srm["severity"]         = srm_deep.severity.value
            srm["g_stat"]           = srm_deep.g_stat
            srm["p_value_g"]        = srm_deep.p_value_g
            srm["p_value_combined"] = srm_deep.p_value_combined
            srm["root_cause_hints"] = list(srm_deep.root_cause_hints)
            srm["relative_bias"]    = srm_deep.relative_bias
        except Exception as _e:
            logger.debug("Deep SRM failed (non-fatal): %s", _e)

    n_c = len(ctrl_df);  c_c = int(ctrl_df["converted_to_order"].sum())
    n_t = len(treat_df); c_t = int(treat_df["converted_to_order"].sum())
    pr  = proportion_test(n_c, c_c, n_t, c_t, alpha)

    primary_delta = MetricDelta(
        metric_name="inquiry_order_rate",
        metric_display_name="Inquiry to Order Rate (IOR)",
        control_variant=control_variant,
        treatment_variant=treatment,
        n_control=n_c, n_treatment=n_t,
        rate_control=pr["rate_control"],
        rate_treatment=pr["rate_treatment"],
        delta_pp=pr["delta_pp"], delta_abs=pr["delta_abs"], delta_rel=pr["delta_rel"],
        ci_lo=pr["ci_lo"], ci_hi=pr["ci_hi"],
        p_value=pr["p_value"], effect_size=pr["effect_size_h"],
        is_significant=pr["is_significant"], direction=pr["direction"],
        alpha=alpha, method="z_test",
    )

    secondary_deltas = []
    for val_col in ["order_value", "bookings_with_shipping", "total_etl"]:
        if val_col not in df.columns:
            continue
        ctrl_aov  = ctrl_df[val_col].dropna().values.astype(float)
        treat_aov = treat_df[val_col].dropna().values.astype(float)
        if len(ctrl_aov) < 2 or len(treat_aov) < 2:
            continue
        mr = means_test(ctrl_aov, treat_aov, alpha)
        if "error" not in mr:
            secondary_deltas.append(MetricDelta(
                metric_name=val_col,
                metric_display_name=val_col.replace("_", " ").title(),
                control_variant=control_variant, treatment_variant=treatment,
                n_control=mr["n_control"], n_treatment=mr["n_treatment"],
                mean_control=mr["mean_control"], mean_treatment=mr["mean_treatment"],
                delta_abs=mr["delta_abs"], delta_rel=mr["delta_rel"],
                ci_lo=mr["ci_lo"], ci_hi=mr["ci_hi"],
                p_value=mr["p_value"], effect_size=mr["effect_size_d"],
                is_significant=mr["is_significant"], direction=mr["direction"],
                alpha=alpha, method="t_test",
            ))
        break  # take first available revenue metric only

    if srm["srm_detected"]:
        verdict = SignificanceVerdict.SRM_DETECTED
        ship    = ShipRecommendation.INVESTIGATE
        blockers = [f"SRM detected (χ²={srm['chi2']:.3f}, p={srm['p_value']:.4f})"]
    elif pr["is_significant"]:
        verdict  = SignificanceVerdict.SIGNIFICANT
        ship     = ShipRecommendation.SHIP if pr["direction"] == "positive" else ShipRecommendation.DO_NOT_SHIP
        blockers = [] if pr["direction"] == "positive" else ["Primary metric moved negative"]
    elif (n_c + n_t) < 200:
        verdict  = SignificanceVerdict.UNDERPOWERED
        ship     = ShipRecommendation.EXTEND
        blockers = [f"Only {n_c + n_t} observations — insufficient power"]
    else:
        verdict  = SignificanceVerdict.NOT_SIGNIFICANT
        ship     = ShipRecommendation.DO_NOT_SHIP
        blockers = []

    # Bayesian A/B test
    bayesian = None
    if _DEEP_STATS:
        try:
            bayesian = beta_binomial_test(n_c, c_c, n_t, c_t, alpha=alpha)
            logger.info(
                "Bayesian[%s]: P(T>C)=%.4f  decision=%s  E_loss_ship=%.6f",
                experiment_id,
                bayesian["prob_treat_better"],
                bayesian["decision"],
                bayesian["expected_loss_ship"],
            )
        except Exception as _e:
            logger.debug("Bayesian test failed (non-fatal): %s", _e)

    # Sequential e-value
    e_value_result = None
    if _DEEP_STATS:
        try:
            e_val = compute_e_value(n_c, c_c, n_t, c_t)
            e_value_result = {"e_value": e_val, "p_msprt": min(1.0, 1.0/max(e_val,1e-10)),
                              "boundary_crossed": e_val >= 1.0/alpha}
            logger.info("Sequential[%s]: e_value=%.4f boundary=%s",
                        experiment_id, e_val, e_value_result["boundary_crossed"])
        except Exception as _e:
            logger.debug("Sequential test failed (non-fatal): %s", _e)

        return ExperimentResult(
        experiment_id=experiment_id,
        experiment_name=experiment_name,
        primary_metric="inquiry_order_rate",
        analysis_method="ab_test_z_test",
        analyst=analyst,
        primary_delta=primary_delta,
        secondary_deltas=secondary_deltas,
        srm_detected=srm["srm_detected"],
        srm_p_value=srm["p_value"],
        srm_chi2=srm["chi2"],
        actual_n=n_c + n_t,
        verdict=verdict,
        ship_recommendation=ship,
        ship_blockers=blockers,
    )


@task(name="run_segment_slicing")
def run_segment_slicing_task(
    df: Any,
    result: Any,
    alpha: float = 0.05,
) -> Any:
    try:
        from continum.core.analysis.segment import run_segment_analysis
        slices = run_segment_analysis(
            df=df,
            experiment_id=result.experiment_id,
            control_variant=result.primary_delta.control_variant,
            alpha=alpha,
        )
        result.slice_findings.extend(slices)
        logger.info("Segment slicing: %d slices for %s", len(slices), result.experiment_id)
    except Exception as e:
        logger.warning("Segment slicing failed: %s", e)
    return result


@task(name="run_causal_suite", retries=1)
def run_causal_suite_task(
    df: Any,
    result: Any,
    methods: Optional[List[str]] = None,
    analyst: str = "system",
) -> List[Any]:
    from continum.core.causal.methods import run_did, run_psm
    methods = methods or ["did"]
    estimates = []
    for method in methods:
        try:
            if method == "did":
                est = run_did(df, result.experiment_id, analyst=analyst)
                if est:
                    estimates.append(est)
            elif method == "psm":
                est = run_psm(df, result.experiment_id, analyst=analyst)
                if est:
                    estimates.append(est)
        except Exception as e:
            logger.warning("Causal method %s failed: %s", method, e)
    return estimates


@task(name="check_guardrails")
def check_guardrails_task(
    result: Any,
    guardrail_specs: Optional[List[Dict]] = None,
) -> List[Any]:
    from continum.artifacts.types import GuardrailViolation
    violations = []
    if not guardrail_specs:
        return violations
    for spec in guardrail_specs:
        metric    = spec.get("metric", "")
        condition = spec.get("condition", "min")
        threshold = spec.get("threshold", 0.0)
        name      = spec.get("name", metric)
        severity  = spec.get("severity", "warning")

        observed = None
        if metric == result.primary_metric:
            observed = result.primary_delta.rate_treatment
        else:
            for d in result.secondary_deltas:
                if d.metric_name == metric:
                    observed = d.mean_treatment
                    break

        if observed is None:
            continue

        breached = (condition == "min" and observed < threshold) or \
                   (condition == "max" and observed > threshold)
        if breached:
            violations.append(GuardrailViolation(
                experiment_id=result.experiment_id,
                guardrail_name=name, metric_name=metric,
                severity=severity, condition=condition,
                threshold=threshold, observed_value=observed,
                violation_magnitude=abs(observed - threshold),
            ))
    return violations


@task(name="write_to_knowledge_graph")
def write_to_graph_task(
    result: Any,
    causal_estimates: List[Any],
    violations: List[Any],
    knowledge_graph=None,
) -> None:
    if knowledge_graph is None:
        logger.debug("No knowledge graph — skipping graph write")
        return
    try:
        knowledge_graph.record_experiment_result(result, causal_estimates, violations)
        logger.info("Experiment %s written to knowledge graph", result.experiment_id)
    except Exception as e:
        logger.error("Knowledge graph write failed: %s", e)


@task(name="generate_narrative")
def generate_narrative_task(
    result: Any,
    causal_estimates: List[Any],
    violations: List[Any],
    llm=None,
) -> str:
    if llm is None:
        return _build_template_narrative(result, causal_estimates, violations)
    try:
        context = result.to_llm_context()
        if causal_estimates:
            context += "\n\nCAUSAL ESTIMATES:\n" + "\n".join(
                e.to_llm_context() for e in causal_estimates)
        prompt = (
            "You are a senior product analytics expert providing an experiment readout.\n"
            "Based on the following typed analysis output, write a 4-6 sentence executive "
            "summary covering: (1) the key result and significance, "
            "(2) the ship recommendation and why, (3) any guardrail concerns, "
            "(4) the most important segment finding if any.\n"
            "Be specific. Use numbers. No generic advice.\n\n"
            f"{context}"
        )
        return llm.ask(prompt)
    except Exception as e:
        logger.warning("LLM narrative failed: %s — using template", e)
        return _build_template_narrative(result, causal_estimates, violations)


@task(name="save_result_json")
def save_result_json_task(
    result: Any,
    causal_estimates: List[Any],
    narrative: str,
    output_path: Optional[str] = None,
) -> str:
    import json
    from pathlib import Path

    exp_id     = result.experiment_id.replace(" ", "_")
    ts         = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path   = output_path or f"result_{exp_id}_{ts}.json"

    payload = {
        "experiment_id":      result.experiment_id,
        "experiment_name":    result.experiment_name,
        "analysed_at":        result.analysed_at.isoformat(),
        "verdict":            result.verdict.value,
        "ship_recommendation": result.ship_recommendation.value,
        "ship_blockers":      result.ship_blockers,
        "primary_metric": {
            "name":           result.primary_delta.metric_name,
            "rate_control":   result.primary_delta.rate_control,
            "rate_treatment": result.primary_delta.rate_treatment,
            "delta_pp":       result.primary_delta.delta_pp,
            "p_value":        result.primary_delta.p_value,
            "is_significant": result.primary_delta.is_significant,
            "direction":      result.primary_delta.direction,
            "ci_lo":          result.primary_delta.ci_lo,
            "ci_hi":          result.primary_delta.ci_hi,
        },
        "srm_detected":   result.srm_detected,
        "srm_p_value":    result.srm_p_value,
        "n_slices":       len(result.slice_findings),
        "n_violations":   len(result.guardrail_violations),
        "n_causal":       len(causal_estimates),
        "narrative":      narrative,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Result saved → %s", out_path)
    return out_path


def _build_template_narrative(result: Any, causal_estimates: List, violations: List) -> str:
    d     = result.primary_delta
    sig   = "statistically significant" if d.is_significant else "not statistically significant"
    delta = f"{d.delta_pp:+.2f}pp" if d.delta_pp is not None else f"Δ={d.delta_abs:+.4f}"
    ship  = result.ship_recommendation.value.replace("_", " ").title()

    lines = [
        f"Experiment '{result.experiment_name}': {d.metric_display_name} "
        f"moved {delta} ({sig}, p={d.p_value:.4f}).",
        f"Recommendation: {ship}.",
    ]
    if violations:
        lines.append(f"{len(violations)} guardrail violation(s): "
                     + "; ".join(v.guardrail_name for v in violations) + ".")
    if result.srm_detected:
        lines.append(f"WARNING: SRM detected (p={result.srm_p_value:.4f}) — results may be unreliable.")
    if causal_estimates:
        est = causal_estimates[0]
        lines.append(f"Causal estimate ({est.method}): {est.estimate:+.4f} "
                     f"[{est.ci_lo:+.4f}, {est.ci_hi:+.4f}].")
    if result.slice_findings:
        sig_slices = [s for s in result.slice_findings if s.is_heterogeneous]
        if sig_slices:
            s = sig_slices[0]
            lines.append(f"Notable segment: {s.dimension_name}={s.dimension_value} "
                         f"Δ={s.delta.delta_pp:+.2f}pp (p={s.delta.p_value:.4f}).")
    return " ".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# FULL PIPELINE FLOW
# ─────────────────────────────────────────────────────────────────────────────

@flow(name="experiment_analysis_pipeline")
def run_experiment_analysis_pipeline(
    experiment_id: str,
    experiment_name: str,
    db=None,
    llm=None,
    knowledge_graph=None,
    causal_methods: Optional[List[str]] = None,
    guardrail_specs: Optional[List[Dict]] = None,
    control_variant: str = "control",
    alpha: float = 0.05,
    analyst: str = "system",
    save_result: bool = True,
) -> Dict[str, Any]:
    run_id = f"analysis_{experiment_id}_{uuid4().hex[:8]}"
    logger.info("[PIPELINE] Starting analysis for %s (run_id=%s)", experiment_id, run_id)

    pipeline_log = {
        "run_id": run_id, "experiment_id": experiment_id,
        "started_at": datetime.utcnow().isoformat(),
        "tasks": {}, "status": "running",
    }

    try:
        # T1: Load data
        df = load_experiment_data(experiment_id, db=db)
        pipeline_log["tasks"]["load"] = {"status": "ok", "rows": len(df)}

        # T2: Validate
        validation = validate_experiment_data_task(df, experiment_id)
        pipeline_log["tasks"]["validate"] = validation
        if not validation["ok"]:
            raise ValueError(f"Data validation failed: {validation['errors']}")

        # T3: Primary analysis
        result = run_primary_analysis_task(
            df, experiment_id, experiment_name,
            control_variant=control_variant, alpha=alpha, analyst=analyst,
        )
        pipeline_log["tasks"]["primary_analysis"] = {
            "status": "ok", "verdict": result.verdict.value,
            "ship": result.ship_recommendation.value,
        }

        # T4: Segment slicing (NEW — populates slice_findings)
        result = run_segment_slicing_task(df, result, alpha=alpha)
        pipeline_log["tasks"]["segment_slicing"] = {
            "status": "ok", "n_slices": len(result.slice_findings)
        }

        # T5: Causal suite
        causal_estimates = run_causal_suite_task(
            df, result, methods=causal_methods or [], analyst=analyst)
        pipeline_log["tasks"]["causal_suite"] = {
            "status": "ok", "n_estimates": len(causal_estimates)}

        # T6: Guardrails
        violations = check_guardrails_task(result, guardrail_specs or [])
        result.guardrail_violations.extend(violations)
        for v in violations:
            if v.severity == "blocker" and v.guardrail_name not in result.ship_blockers:
                result.ship_blockers.append(f"Guardrail violation: {v.guardrail_name}")
        pipeline_log["tasks"]["guardrails"] = {"status": "ok", "violations": len(violations)}

        # T7: Knowledge graph
        write_to_graph_task(result, causal_estimates, violations, knowledge_graph=knowledge_graph)
        pipeline_log["tasks"]["graph_write"] = {"status": "ok"}

        # T8: Narrative
        narrative = generate_narrative_task(result, causal_estimates, violations, llm=llm)
        pipeline_log["tasks"]["narrative"] = {"status": "ok"}

        # T9: Save result JSON
        result_file = None
        if save_result:
            try:
                result_file = save_result_json_task(result, causal_estimates, narrative)
                pipeline_log["tasks"]["save_result"] = {"status": "ok", "path": result_file}
            except Exception as e:
                logger.warning("Could not save result JSON: %s", e)

        pipeline_log.update({"status": "completed",
                              "completed_at": datetime.utcnow().isoformat()})

        return {
            "run_id":           run_id,
            "result":           result,
            "primary_metric":   result.primary_delta,   # convenience accessor
            "causal_estimates": causal_estimates,
            "violations":       violations,
            "narrative":        narrative,
            "pipeline_log":     pipeline_log,
            "result_file":      result_file,
        }

    except Exception as e:
        pipeline_log.update({
            "status":    "failed",
            "failed_at": datetime.utcnow().isoformat(),
            "error":     str(e),
            "traceback": traceback.format_exc(),
        })
        logger.error("[PIPELINE] Analysis failed for %s: %s", experiment_id, e)
        return {
            "run_id":       run_id,
            "result":       None,
            "primary_metric": None,
            "error":        str(e),
            "pipeline_log": pipeline_log,
        }


__all__ = [
    "load_experiment_data",
    "validate_experiment_data_task",
    "run_primary_analysis_task",
    "run_segment_slicing_task",
    "run_causal_suite_task",
    "check_guardrails_task",
    "write_to_graph_task",
    "generate_narrative_task",
    "save_result_json_task",
    "run_experiment_analysis_pipeline",
]
