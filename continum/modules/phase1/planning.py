from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from continum.core.experimentation.statistics import (
    compute_sample_size, compute_duration, compute_opportunity,
)
from continum.documents.generator import render_document_pdf, PDF_PALETTE

logger = logging.getLogger("continum.phase1")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _discover_cols(db) -> dict:
    c = {"outcome": "converted_to_order", "value": "order_value",
         "buyer":   "buyer_id",           "segment": "account_segment",
         "platform": "platform"}
    if db is None:
        return c
    try:
        actual = {r[0].lower() for r in db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='silver_inquiries'"
        ).fetchall()}
        for x in ("converted_to_order","is_converted","conversion","ordered","converted"):
            if x in actual: c["outcome"] = x; break
        for x in ("order_value","aov","order_total","revenue","amount","gmv"):
            if x in actual: c["value"]   = x; break
        for x in ("buyer_id","user_id","customer_id","account_id","id"):
            if x in actual: c["buyer"]   = x; break
        for x in ("account_segment","segment","customer_segment","tier","user_segment"):
            if x in actual: c["segment"] = x; break
        for x in ("platform","device","channel","source"):
            if x in actual: c["platform"]= x; break
    except Exception:
        pass
    return c


def _pull_baselines(db=None) -> Dict[str, float]:
    defaults = {
        "ior": 0.18, "aov": 4000.0, "monthly_inquiries": 15000.0,
        "daily_inquiries": 500.0, "monthly_orders": 2700.0,
    }
    if db is None:
        return defaults
    try:
        row = db.execute(f"""
            SELECT
                _dc = _discover_cols(db)
                AVG(CAST({_dc["outcome"]} AS DOUBLE))           AS ior,
                _dc = _discover_cols(db)
                AVG(CASE WHEN {_dc["outcome"]} THEN {_dc["value"]} END)  AS aov,
                COUNT(*) / 3.0                                         AS monthly_inquiries,
                COUNT(*) / 90.0                                        AS daily_inquiries
            FROM (SELECT * FROM silver_inquiries LIMIT 90000)
        """).fetchone()
        if row and row[0] is not None:
            defaults["ior"]               = float(row[0] or 0.18)
            defaults["aov"]               = float(row[1] or 4000)
            defaults["monthly_inquiries"] = float(row[2] or 15000)
            defaults["daily_inquiries"]   = float(row[3] or 500)
            defaults["monthly_orders"]    = defaults["monthly_inquiries"] * defaults["ior"]
    except Exception as e:
        logger.debug("Could not pull baselines: %s", e)
    return defaults


# ─────────────────────────────────────────────────────────────────────────────
# POWER CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_power_calculator(llm=None, db=None, **kwargs) -> Dict:
    print("\n" + "=" * 72)
    print("  POWER CALCULATOR")
    print("=" * 72)

    baselines = _pull_baselines(db)

    def _ask_float(q, default, min_v=None, max_v=None):
        if q in kwargs:
            return float(kwargs[q])
        while True:
            raw = input(f"  ❓ {q} [{default}]: ").strip()
            if raw == "":
                return float(default)
            try:
                v = float(raw)
                if min_v is not None and v < min_v:
                    print(f"     ⚠️  Must be ≥ {min_v}"); continue
                if max_v is not None and v > max_v:
                    print(f"     ⚠️  Must be ≤ {max_v}"); continue
                return v
            except ValueError:
                print("     ⚠️  Please enter a number")

    def _ask_int(q, default, min_v=2):
        if q in kwargs:
            return int(kwargs[q])
        while True:
            raw = input(f"  ❓ {q} [{default}]: ").strip()
            if raw == "":
                return int(default)
            try:
                v = int(raw)
                if v < min_v:
                    print(f"     ⚠️  Must be ≥ {min_v}"); continue
                return v
            except ValueError:
                print("     ⚠️  Please enter a whole number")

    baseline      = _ask_float("Baseline conversion/IOR rate (0–1)",
                               round(baselines["ior"], 4), 0.001, 0.999)
    mde_pct       = _ask_float("MDE — minimum detectable effect (% relative, e.g. 10)",
                               10.0, 0.1)
    mde_abs       = baseline * mde_pct / 100
    print(f"                              → absolute MDE = {mde_abs * 100:.3f}pp")
    alpha         = _ask_float("Significance level α", 0.05, 0.001, 0.30)
    power         = _ask_float("Statistical power 1-β", 0.80, 0.50, 0.99)
    n_variants    = _ask_int("Number of variants (including control)", 2)
    daily_traffic = _ask_float("Daily eligible traffic", round(baselines["daily_inquiries"], 1), 1)
    traffic_share = _ask_float("Fraction of traffic in experiment (0–1)", 1.0, 0.01, 1.0)

    ss  = compute_sample_size(baseline, mde_abs, alpha, power, n_variants)
    dur = compute_duration(ss["n_total"], daily_traffic, traffic_share)

    print("\n" + "─" * 72)
    print("  RESULTS")
    print("─" * 72)
    print(f"  Baseline rate         : {baseline * 100:.2f}%")
    print(f"  MDE                   : {mde_pct:.1f}% relative = {mde_abs * 100:.3f}pp abs")
    print(f"  Effect size (Cohen h) : {ss['effect_size_h']:.4f}")
    print(f"  α={alpha:.3f}  Power={power:.2f}  Variants={n_variants}")
    print(f"  ─── Sample size ───")
    print(f"  Per variant           : {ss['n_per_variant']:,}")
    print(f"  Total                 : {ss['n_total']:,}")
    print(f"  ─── Duration ───")
    print(f"  Daily eligible        : {dur['daily_eligible']:,.1f}")
    print(f"  Required duration     : {dur['days_required']:,} days ({dur['weeks_required']} weeks)")
    print(f"  Estimated end date    : {dur['end_date']}")
    print("─" * 72)

    if llm is not None:
        narrative = llm.narrate(
            {"sample_size": ss, "duration": dur},
            context=(f"Power calculation: baseline IOR {baseline * 100:.2f}%, "
                     f"MDE {mde_pct:.1f}% rel ({mde_abs * 100:.3f}pp abs). "
                     "Give: (1) what the numbers mean, (2) business risk of running "
                     "shorter/longer, (3) recommendations for the team.")
        )
        print(f"\n  EXPERIMENT DESIGN SUMMARY")
        print("─" * 72)
        print(narrative)
        print("─" * 72)

    return {"sample_size": ss, "duration": dur}


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITY SIZING
# ─────────────────────────────────────────────────────────────────────────────

def run_opportunity_sizing(llm=None, db=None, **kwargs) -> Dict:
    print("\n" + "=" * 72)
    print("  OPPORTUNITY SIZING")
    print("=" * 72)

    baselines = _pull_baselines(db)

    def _ask(q, default, is_pct=False):
        k = q.lower().replace(" ", "_").replace("/", "").replace("-", "_")
        if k in kwargs:
            return float(kwargs[k])
        while True:
            hint = f"[{default:.3f}%]" if is_pct else f"[{default}]"
            raw = input(f"  ❓ {q} {hint}: ").strip()
            if raw == "":
                return float(default)
            try:
                return float(raw)
            except ValueError:
                print("     ⚠️  Please enter a number")

    monthly_inquiries = _ask("Monthly inquiries", round(baselines["monthly_inquiries"], 0))
    current_ior       = _ask("Current IOR (0–1)", round(baselines["ior"], 4))
    target_ior        = _ask("Target IOR after experiment (0–1)",
                              round(min(baselines["ior"] * 1.10, 0.999), 4))
    avg_aov           = _ask("Average order value ($)", round(baselines["aov"], 0))
    gross_margin      = _ask("Gross margin (0–1)", 0.30)
    horizon           = _ask("Time horizon (months)", 12.0)

    result = compute_opportunity(
        monthly_inquiries, current_ior, target_ior,
        avg_aov, gross_margin, horizon,
    )

    print("\n" + "─" * 72)
    print("  RESULTS")
    print("─" * 72)
    print(f"  IOR gap               : {current_ior * 100:.2f}% → {target_ior * 100:.2f}% "
          f"({result['ior_gap_pp']:+.2f}pp)")
    print(f"  Incremental orders/mo : {result['incremental_orders_monthly']:,.1f}")
    print(f"  Incremental revenue/mo: ${result['incremental_revenue_monthly']:,.0f}")
    print(f"  Incremental GM/mo     : ${result['incremental_gm_monthly']:,.0f}")
    h = int(horizon)
    print(f"  {h}-month revenue upside: ${result.get(f'incremental_revenue_{h}mo', result['incremental_revenue_monthly'] * h):,.0f}")
    print(f"  {h}-month GM upside    : ${result.get(f'incremental_gm_{h}mo', result['incremental_gm_monthly'] * h):,.0f}")
    print("─" * 72)

    if llm is not None:
        narrative = llm.narrate(
            result,
            context=f"Opportunity sizing: IOR gap {current_ior*100:.2f}% → {target_ior*100:.2f}%. "
                    "Provide: (1) headline opportunity, (2) key assumptions, "
                    "(3) whether to proceed with an A/B test."
        )
        print(f"\n  EXECUTIVE SUMMARY\n{'─'*72}")
        print(narrative)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# AUDIENCE SELECTION
# ─────────────────────────────────────────────────────────────────────────────

PROPENSITY_RULES = {
    "conversion": {
        "description": "Users likely to respond to checkout/funnel changes",
        "target_segments": ["Core", "Growth"],
        "ior_range": (0.10, 0.30),
        "min_inquiries": 3,
    },
    "acquisition": {
        "description": "Users likely to respond to sign-up / onboarding changes",
        "target_segments": ["Growth", "Individuals"],
        "ior_range": (0.0, 0.20),
        "min_inquiries": 0,
    },
    "retention": {
        "description": "Users likely to respond to repeat order nudges",
        "target_segments": ["Core", "Enterprise"],
        "ior_range": (0.05, 0.40),
        "min_inquiries": 5,
    },
    "engagement": {
        "description": "Users likely to respond to UI/UX changes",
        "target_segments": ["Core", "Growth", "Enterprise"],
        "ior_range": (0.05, 0.35),
        "min_inquiries": 2,
    },
}


def run_audience_selection(llm=None, db=None, **kwargs) -> Dict:
    print("\n" + "╔" + "═" * 70 + "╗")
    print("║" + "  AUDIENCE SELECTION".ljust(70) + "║")
    print("║" + "  Who goes into control and treatment?".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    category = kwargs.get("category", "")
    if not category:
        print("\n  Experiment categories:")
        for i, (k, v) in enumerate(PROPENSITY_RULES.items()):
            print(f"  [{i+1}] {k:<15}  {v['description']}")
        while True:
            raw = input("\n  ❓ Experiment category [1-4]: ").strip()
            try:
                idx = int(raw) - 1
                category = list(PROPENSITY_RULES.keys())[idx]
                break
            except (ValueError, IndexError):
                print("     ⚠️  Enter 1-4")

    rules = PROPENSITY_RULES.get(category, PROPENSITY_RULES["engagement"])

    # Pull user features if DB available
    if db is not None:
        try:
            df = db.execute(f"""
                SELECT
                    user_id,
                    COUNT(*)                                      AS n_inquiries,
                    _dc = _discover_cols(db)
                    AVG(CAST({_dc["outcome"]} AS DOUBLE))       AS personal_ior,
                    _dc = _discover_cols(db)
                    AVG(CASE WHEN {_dc["outcome"]}
                        _dc = _discover_cols(db)
                        THEN {_dc["value"]} END)                     AS avg_aov,
                    MAX(created_at)                               AS last_activity
                FROM silver_inquiries
                GROUP BY user_id
            """).df()
            lo, hi = rules["ior_range"]
            eligible = df[
                (df["personal_ior"].fillna(0) >= lo) &
                (df["personal_ior"].fillna(0) <= hi) &
                (df["n_inquiries"] >= rules["min_inquiries"])
            ]
            pct = len(eligible) / max(1, len(df)) * 100
            print(f"\n  Category          : {category}")
            print(f"  Total users       : {len(df):,}")
            print(f"  Eligible users    : {len(eligible):,} ({pct:.1f}%)")
            print(f"  IOR range         : {lo:.0%} – {hi:.0%}")
            print(f"  Min inquiries     : {rules['min_inquiries']}")
            print(f"  Target segments   : {rules['target_segments']}")
            result = {
                "category": category, "n_total": len(df),
                "n_eligible": len(eligible), "eligible_pct": pct,
                "criteria": {"ior_range": rules["ior_range"],
                             "min_inquiries": rules["min_inquiries"],
                             "target_segments": rules["target_segments"]},
            }
        except Exception as e:
            logger.warning("Could not score users: %s", e)
            result = {"category": category, "error": str(e)}
    else:
        print(f"\n  Category       : {category}")
        print(f"  Target segments: {rules['target_segments']}")
        print(f"  IOR range      : {rules['ior_range'][0]:.0%} – {rules['ior_range'][1]:.0%}")
        print(f"  Min inquiries  : {rules['min_inquiries']}")
        result = {"category": category, "rules": rules}

    if llm is not None:
        narrative = llm.narrate(
            result,
            context=f"Audience selection for a '{category}' experiment. "
                    "Explain: (1) who to include and exclude, "
                    "(2) the business rationale, (3) risks of the inclusion criteria."
        )
        print(f"\n  {narrative}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# BRIEF GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_brief_generator(llm, db=None, **kwargs) -> Dict:
    print("\n" + "╔" + "═" * 70 + "╗")
    print("║" + "  EXPERIMENT BRIEF GENERATOR".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    desc  = kwargs.get("description") or input("\n  ❓ Feature / change description: ").strip()
    hyp   = kwargs.get("hypothesis")  or input("  ❓ Hypothesis (if X then Y because Z): ").strip()
    team  = kwargs.get("team")         or input("  ❓ Team: ").strip()
    owner = kwargs.get("owner")        or input("  ❓ Experiment owner: ").strip()

    baselines = _pull_baselines(db)

    context = (
        f"Feature: {desc}\nHypothesis: {hyp}\nTeam: {team}\nOwner: {owner}\n"
        f"Baseline IOR: {baselines['ior']:.3%}\n"
        f"Monthly inquiries: {baselines['monthly_inquiries']:,.0f}"
    )

    sections_raw: Dict[str, str] = {}
    section_prompts = {
        "EXPERIMENT OVERVIEW": (
            f"Write a 2-paragraph experiment overview for: {context}. "
            "Include: (1) what is being tested and why now, (2) expected mechanism of action."
        ),
        "HYPOTHESIS": (
            f"Write a precise, testable hypothesis for: {context}. "
            "Format: 'If [change], then [metric] will [increase/decrease] by [~amount] because [mechanism].'"
        ),
        "PRIMARY & GUARDRAIL METRICS": (
            f"List the primary KPI (with current baseline from: IOR={baselines['ior']:.3%}), "
            f"2-3 secondary metrics, and 1-2 guardrail metrics. Context: {context}"
        ),
        "AUDIENCE & VARIANT DESIGN": (
            f"Describe the target audience, variant design, and expected sample split. Context: {context}"
        ),
        "RISKS & OPEN QUESTIONS": (
            f"List 3-4 risks and 2-3 open questions that must be resolved before launch. Context: {context}"
        ),
    }

    if llm is not None:
        print("\n  Generating brief (5 LLM calls)...")
        for i, (section, prompt) in enumerate(section_prompts.items()):
            print(f"  [{i+1}/{len(section_prompts)}] {section}...", end=" ", flush=True)
            try:
                sections_raw[section] = llm.ask(prompt)
                print("done")
            except Exception as e:
                sections_raw[section] = f"(Could not generate: {e})"
                print(f"failed ({e})")
    else:
        for section in section_prompts:
            sections_raw[section] = "(LLM not available — add manually)"

    # Display
    exp_name = desc[:40].lower().replace(" ", "_")
    print("\n" + "=" * 72)
    print("  EXPERIMENT BRIEF")
    for section, body in sections_raw.items():
        print(f"\n  {section}")
        print("  " + "─" * 68)
        for line in body.split("\n"):
            if line.strip():
                print(f"  {line.strip()}")

    # PDF
    out = render_document_pdf(
        title="Experiment Brief",
        subtitle=f"Feature: {desc[:80]}",
        sections=OrderedDict(sections_raw),
        output_path=f"brief_{exp_name[:30]}.pdf",
        metadata={
            "Feature":  desc[:80],
            "Team":     team,
            "Owner":    owner,
            "Created":  datetime.utcnow().strftime("%Y-%m-%d"),
            "Baseline IOR": f"{baselines['ior']:.3%}",
        },
        accent_color=PDF_PALETTE["accent"],
    )
    print(f"\n  📁 Brief saved → {out}")

    return {"description": desc, "hypothesis": hyp, "sections": sections_raw,
            "output_file": out}


# ─────────────────────────────────────────────────────────────────────────────
# METRICS & TRACKING PLAN
# ─────────────────────────────────────────────────────────────────────────────

def run_metrics_and_tracking(llm, db=None, **kwargs) -> Dict:
    print("\n" + "=" * 72)
    print("  KPI METRICS & DATA TRACKING PLANNER")
    print("=" * 72)

    desc  = kwargs.get("description") or input("\n  ❓ Feature description: ").strip()
    maturity = kwargs.get("maturity", "mvp")
    if "maturity" not in kwargs:
        raw = input("  ❓ Maturity [mvp/iteration/critical]: ").strip().lower()
        maturity = raw if raw in ("mvp", "iteration", "critical") else "mvp"

    baselines = _pull_baselines(db)

    section_prompts = {
        "PRIMARY METRICS": (
            f"List 1-2 primary KPIs for '{desc}'. For each: Metric name, definition, "
            f"current baseline (IOR={baselines['ior']:.3%}, AOV=${baselines['aov']:,.0f}), "
            f"target, direction (higher/lower better), and why it's the north-star."
        ),
        "SECONDARY METRICS": (
            f"List 3-4 secondary metrics for '{desc}'. "
            "Format each as: Metric:, Why:, Baseline:, Target:"
        ),
        "GUARDRAIL METRICS": (
            f"List 2-3 guardrail/no-harm metrics for '{desc}'. "
            "These are red lines — if they breach, stop the experiment immediately. "
            "Include thresholds."
        ),
        "DATA TRACKING REQUIREMENTS": (
            f"List the tracking events engineering must instrument for '{desc}' "
            f"(maturity={maturity}). Format: Track: event_name | Trigger: | Properties: | "
            "Owner:"
        ),
        "OPEN QUESTIONS & ASSUMPTIONS": (
            f"List 4-5 open questions and key assumptions that must be validated before "
            f"launching '{desc}'."
        ),
    }

    sections: Dict[str, str] = {}
    if llm is not None:
        print("\n  Generating measurement plan...")
        for i, (section, prompt) in enumerate(section_prompts.items()):
            print(f"  [{i+1}/{len(section_prompts)}] {section}...", end=" ", flush=True)
            try:
                sections[section] = llm.ask(prompt)
                print("done")
            except Exception as e:
                sections[section] = f"(Error: {e})"
                print(f"failed")
    else:
        for section in section_prompts:
            sections[section] = "(LLM not available)"

    # Display
    print("\n" + "=" * 72)
    for section, body in sections.items():
        print(f"\n  {section}")
        print("  " + "─" * 68)
        for line in body.split("\n"):
            if line.strip():
                print(f"  {line.strip()}")

    # PDF
    out = render_document_pdf(
        title="KPI & Data Tracking Plan",
        subtitle=f"Feature: {desc[:80]}",
        sections=OrderedDict(sections),
        output_path="metrics_tracking_plan.pdf",
        metadata={"Feature": desc[:80], "Maturity": maturity,
                  "Created": datetime.utcnow().strftime("%Y-%m-%d")},
        accent_color=PDF_PALETTE["accent"],
    )
    print(f"\n  📁 Measurement plan saved → {out}")
    return {**sections, "output_file": out}


__all__ = [
    "run_power_calculator",
    "run_opportunity_sizing",
    "run_audience_selection",
    "run_brief_generator",
    "run_metrics_and_tracking",
]
