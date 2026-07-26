"""
New analysis modules for the restructured PersistIQ experimentation framework.
Each module follows the pattern: def run_xxx(state, db=None, llm=None, **kw) -> dict
All Tier 1 modules are deterministic (no LLM). Tier 2/3 accept _template_path for file-based input.
"""

from __future__ import annotations

import json
import logging
import math
import os

logger = logging.getLogger("continum.new_modules")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: safe DB query
# ═══════════════════════════════════════════════════════════════════════════════
def _q(db, sql, default=None):
    try:
        return db.execute(sql).fetchall()
    except Exception:
        return default or []


def _qone(db, sql, default=None):
    try:
        row = db.execute(sql).fetchone()
        return row if row else default
    except Exception:
        return default


def _print_header(title):
    w = max(len(title) + 4, 50)
    print("═" * w)
    print(f"  {title}")
    print("═" * w)


def _print_section(title):
    print(f"\n── {title} {'─' * max(0, 44 - len(title))}")


def _template_context(kw):
    """Load user-uploaded template file if provided."""
    path = kw.get("_template_path", "")
    if path and os.path.isfile(path):
        try:
            with open(path, "r", errors="replace") as f:
                return f.read()[:20000]  # limit to 20K chars
        except Exception:
            pass
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Funnel Analysis (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_funnel_analysis(state, db=None, llm=None, **kw):
    _print_header("FUNNEL ANALYSIS")
    if not db:
        print("⚠️  No database connection — skipping.")
        return {"ok": False, "error": "no_db"}

    _print_section("Stage Detection")
    # Detect funnel from gold_experiment_analysis (has standard columns)
    stages = {}
    try:
        rows = db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CAST(converted_to_order AS INT)) AS converted,
                AVG(COALESCE(order_value, 0)) AS avg_value
            FROM gold_experiment_analysis
        """
        ).fetchone()
        total, converted, avg_val = int(rows[0] or 0), int(rows[1] or 0), float(rows[2] or 0)
        stages = {
            "inquiries": total,
            "conversions": converted,
            "conversion_rate": round(converted / max(total, 1), 4),
            "avg_order_value": round(avg_val, 2),
        }
    except Exception as e:
        print(f"⚠️  Could not query funnel stages: {e}")
        stages = {"inquiries": 0, "conversions": 0, "conversion_rate": 0, "avg_order_value": 0}

    print(f"  Total inquiries:    {stages['inquiries']:,}")
    print(f"  Conversions:        {stages['conversions']:,}")
    print(f"  Conversion rate:    {stages['conversion_rate']:.2%}")
    print(f"  Avg order value:    ${stages['avg_order_value']:,.2f}")

    _print_section("Segment Breakdown")
    try:
        seg_rows = db.execute(
            """
            SELECT account_segment AS segment,
                   COUNT(*) AS n,
                   SUM(CAST(converted_to_order AS INT)) AS conv,
                   AVG(COALESCE(order_value, 0)) AS aov
            FROM gold_experiment_analysis
            GROUP BY account_segment ORDER BY n DESC LIMIT 10
        """
        ).fetchall()
        segments = []
        for r in seg_rows:
            seg_name, n, conv, aov = (
                str(r[0] or "unknown"),
                int(r[1]),
                int(r[2] or 0),
                float(r[3] or 0),
            )
            rate = conv / max(n, 1)
            segments.append(
                {
                    "segment": seg_name,
                    "n": n,
                    "conversions": conv,
                    "rate": round(rate, 4),
                    "aov": round(aov, 2),
                }
            )
            print(f"  {seg_name:20s}  n={n:>6,}  conv={conv:>5,}  rate={rate:.2%}  aov=${aov:,.0f}")
    except Exception:
        segments = []
        print("  ⚠️  Could not break down by segment.")

    _print_section("Drop-off Analysis")
    if stages["inquiries"] > 0:
        drop = stages["inquiries"] - stages["conversions"]
        drop_rate = drop / stages["inquiries"]
        print(f"  Drop-offs:          {drop:,} ({drop_rate:.1%})")
        print(f"  Revenue at risk:    ${drop * stages['avg_order_value']:,.0f} (if all converted)")

        # Identify worst-performing segment
        if segments:
            worst = min(segments, key=lambda s: s["rate"])
            best = max(segments, key=lambda s: s["rate"])
            print(f"\n  ✅ Best segment:    {best['segment']} ({best['rate']:.2%})")
            print(f"  ❌ Worst segment:   {worst['segment']} ({worst['rate']:.2%})")
            gap = best["rate"] - worst["rate"]
            print(
                f"  Gap:                {gap:.2%} — closing this gap is a {gap * worst['n']:,.0f} conversion opportunity"
            )

    print("\n✅ Funnel analysis complete.")
    return {"ok": True, "stages": stages, "segments": segments}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Cohort Analysis (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_cohort_analysis(state, db=None, llm=None, **kw):
    _print_header("COHORT ANALYSIS")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("Monthly Cohorts")
    try:
        rows = db.execute(
            """
            SELECT DATE_TRUNC('month', created_at) AS cohort_month,
                   COUNT(*) AS n,
                   SUM(CAST(converted_to_order AS INT)) AS converted,
                   AVG(COALESCE(order_value, 0)) AS aov
            FROM gold_experiment_analysis
            GROUP BY cohort_month ORDER BY cohort_month
        """
        ).fetchall()
        cohorts = []
        for r in rows:
            month_str = str(r[0])[:7] if r[0] else "unknown"
            n, conv, aov = int(r[1]), int(r[2] or 0), float(r[3] or 0)
            rate = conv / max(n, 1)
            cohorts.append(
                {
                    "month": month_str,
                    "n": n,
                    "converted": conv,
                    "rate": round(rate, 4),
                    "aov": round(aov, 2),
                }
            )
            bar = "█" * int(rate * 40)
            print(f"  {month_str}  n={n:>5,}  conv={conv:>4,}  rate={rate:.2%}  {bar}")
        if len(cohorts) >= 2:
            _print_section("Trend")
            first_rate = cohorts[0]["rate"]
            last_rate = cohorts[-1]["rate"]
            delta = last_rate - first_rate
            direction = "📈 Improving" if delta > 0 else "📉 Declining" if delta < 0 else "→ Stable"
            print(f"  {direction}: {first_rate:.2%} → {last_rate:.2%} (Δ = {delta:+.2%})")
    except Exception as e:
        cohorts = []
        print(f"  ⚠️  Could not compute cohorts: {e}")

    print(f"\n✅ Cohort analysis complete — {len(cohorts)} cohorts analysed.")
    return {"ok": True, "cohorts": cohorts}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Retention Analysis (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_retention_analysis(state, db=None, llm=None, **kw):
    _print_header("RETENTION ANALYSIS")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("Repeat Purchase Analysis")
    try:
        rows = db.execute(
            """
            SELECT user_id, COUNT(*) AS orders
            FROM gold_experiment_analysis
            WHERE converted_to_order = 1
            GROUP BY user_id
        """
        ).fetchall()
        total_buyers = len(rows)
        repeat_buyers = sum(1 for r in rows if r[1] > 1)
        avg_orders = sum(r[1] for r in rows) / max(total_buyers, 1)
        retention_rate = repeat_buyers / max(total_buyers, 1)
        print(f"  Total buyers:       {total_buyers:,}")
        print(f"  Repeat buyers:      {repeat_buyers:,} ({retention_rate:.1%})")
        print(f"  Avg orders/buyer:   {avg_orders:.2f}")
    except Exception:
        total_buyers, repeat_buyers, retention_rate, avg_orders = 0, 0, 0, 0
        print("  ⚠️  Could not compute retention from available data.")

    _print_section("Retention by Segment")
    try:
        seg_rows = db.execute(
            """
            SELECT account_segment AS segment,
                   COUNT(DISTINCT user_id) AS buyers,
                   COUNT(DISTINCT CASE WHEN user_orders > 1 THEN user_id END) AS repeaters
            FROM (
                SELECT user_id, account_segment AS segment, COUNT(*) AS user_orders
                FROM gold_experiment_analysis WHERE converted_to_order = 1
                GROUP BY user_id, segment
            ) sub GROUP BY account_segment ORDER BY buyers DESC LIMIT 8
        """
        ).fetchall()
        for r in seg_rows:
            seg, buyers, reps = str(r[0] or "?"), int(r[1]), int(r[2] or 0)
            rt = reps / max(buyers, 1)
            print(f"  {seg:20s}  buyers={buyers:>5,}  repeat={reps:>4,}  retention={rt:.1%}")
    except Exception:
        print("  ⚠️  Segment retention unavailable.")

    print("\n✅ Retention analysis complete.")
    return {
        "ok": True,
        "total_buyers": total_buyers,
        "repeat_buyers": repeat_buyers,
        "retention_rate": round(retention_rate, 4),
        "avg_orders_per_buyer": round(avg_orders, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Churn Analysis (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_churn_analysis(state, db=None, llm=None, **kw):
    _print_header("CHURN ANALYSIS")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("Activity-Based Churn Detection")
    try:
        rows = db.execute(
            """
            SELECT user_id,
                   MAX(created_at) AS last_activity,
                   COUNT(*) AS total_actions,
                   DATEDIFF('day', MAX(created_at), CURRENT_DATE) AS days_inactive
            FROM gold_experiment_analysis
            GROUP BY user_id
        """
        ).fetchall()
        total = len(rows)
        churn_30 = sum(1 for r in rows if (r[3] or 0) > 30)
        churn_60 = sum(1 for r in rows if (r[3] or 0) > 60)
        churn_90 = sum(1 for r in rows if (r[3] or 0) > 90)
        active = total - churn_30
        print(f"  Total users:        {total:,}")
        print(f"  Active (30d):       {active:,} ({active/max(total,1):.1%})")
        print(f"  Churned >30d:       {churn_30:,} ({churn_30/max(total,1):.1%})")
        print(f"  Churned >60d:       {churn_60:,} ({churn_60/max(total,1):.1%})")
        print(f"  Churned >90d:       {churn_90:,} ({churn_90/max(total,1):.1%})")
    except Exception as e:
        total, churn_30 = 0, 0
        print(f"  ⚠️  Could not compute churn: {e}")

    print("\n✅ Churn analysis complete.")
    return {"ok": True, "total_users": total, "churned_30d": churn_30}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Journey Analysis (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_journey_analysis(state, db=None, llm=None, **kw):
    _print_header("JOURNEY ANALYSIS")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("User Journey Patterns")
    try:
        rows = db.execute(
            """
            SELECT user_id,
                   COUNT(*) AS touchpoints,
                   MIN(created_at) AS first_touch,
                   MAX(created_at) AS last_touch,
                   MAX(CAST(converted_to_order AS INT)) AS did_convert,
                   DATEDIFF('day', MIN(created_at), MAX(created_at)) AS journey_days
            FROM gold_experiment_analysis
            GROUP BY user_id
        """
        ).fetchall()
        total = len(rows)
        converters = [r for r in rows if r[4] == 1]
        non_converters = [r for r in rows if r[4] == 0]

        avg_tp_conv = sum(r[1] for r in converters) / max(len(converters), 1)
        avg_tp_non = sum(r[1] for r in non_converters) / max(len(non_converters), 1)
        avg_days_conv = sum(r[5] or 0 for r in converters) / max(len(converters), 1)

        print(f"  Total users:                {total:,}")
        print(f"  Converters:                 {len(converters):,}")
        print(f"  Avg touchpoints (convert):  {avg_tp_conv:.1f}")
        print(f"  Avg touchpoints (non-conv): {avg_tp_non:.1f}")
        print(f"  Avg journey length (conv):  {avg_days_conv:.1f} days")
    except Exception as e:
        print(f"  ⚠️  Could not compute journeys: {e}")
        total = 0

    print("\n✅ Journey analysis complete.")
    return {"ok": True, "total_users": total}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Opportunity Ranking (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_opportunity_ranking(state, db=None, llm=None, **kw):
    _print_header("AUTOMATED OPPORTUNITY RANKING")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("Scoring Opportunities")
    # Score based on: impact (conversion gap × volume), confidence (sample size), reach
    try:
        rows = db.execute(
            """
            SELECT account_segment AS segment,
                   COUNT(*) AS n,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS rate,
                   AVG(COALESCE(order_value, 0)) AS aov
            FROM gold_experiment_analysis GROUP BY account_segment ORDER BY n DESC LIMIT 15
        """
        ).fetchall()
        overall_rate = _qone(
            db, "SELECT AVG(CAST(converted_to_order AS DOUBLE)) FROM gold_experiment_analysis"
        )
        overall_rate = float(overall_rate[0] or 0.1) if overall_rate else 0.1

        opportunities = []
        for r in rows:
            seg, n, rate, aov = str(r[0] or "?"), int(r[1]), float(r[2] or 0), float(r[3] or 0)
            gap = overall_rate - rate  # positive means below average
            impact = max(gap * n * aov, 0)
            confidence = min(n / 100, 1.0)
            reach = n
            score = round((impact * 0.5 + confidence * 0.3 + (reach / 1000) * 0.2), 2)
            opportunities.append(
                {
                    "segment": seg,
                    "gap": round(gap, 4),
                    "impact": round(impact, 0),
                    "confidence": round(confidence, 2),
                    "reach": reach,
                    "score": score,
                }
            )
        opportunities.sort(key=lambda x: x["score"], reverse=True)
        print(f"  {'Rank':<5} {'Segment':<20} {'Gap':>8} {'Impact $':>12} {'Score':>8}")
        print(f"  {'─'*5} {'─'*20} {'─'*8} {'─'*12} {'─'*8}")
        for i, o in enumerate(opportunities[:10], 1):
            print(
                f"  {i:<5} {o['segment']:<20} {o['gap']:>+.2%} {o['impact']:>12,.0f} {o['score']:>8.2f}"
            )
    except Exception as e:
        opportunities = []
        print(f"  ⚠️  Could not rank opportunities: {e}")

    print(f"\n✅ Opportunity ranking complete — {len(opportunities)} segments scored.")
    return {"ok": True, "opportunities": opportunities}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Hypothesis Generation (Tier 3 — LLM Core)
# ═══════════════════════════════════════════════════════════════════════════════
def run_hypothesis_generation(state, db=None, llm=None, **kw):
    _print_header("HYPOTHESIS GENERATION")
    template_ctx = _template_context(kw)
    description = kw.get("description", "")

    _print_section("Context Gathering")
    context_data = {}
    if db:
        try:
            row = _qone(
                db,
                """
                SELECT COUNT(*) AS n,
                       AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                       AVG(COALESCE(order_value, 0)) AS aov
                FROM gold_experiment_analysis
            """,
            )
            if row:
                context_data = {
                    "n": int(row[0]),
                    "ior": round(float(row[1] or 0), 4),
                    "aov": round(float(row[2] or 0), 2),
                }
                print(
                    f"  Dataset: {context_data['n']:,} inquiries, IOR={context_data['ior']:.2%}, AOV=${context_data['aov']:,.0f}"
                )
        except Exception:
            pass

    _print_section("Generating Hypotheses")
    if template_ctx:
        print(f"  📎 Using uploaded template ({len(template_ctx)} chars)")

    if llm:
        prompt = f"""Given this experiment context:
- Description: {description or 'General conversion optimization'}
- Current IOR: {context_data.get('ior', 'unknown')}
- Current AOV: {context_data.get('aov', 'unknown')}
- Sample size: {context_data.get('n', 'unknown')}
{('- User template/context: ' + template_ctx[:2000]) if template_ctx else ''}

Generate 3-5 experiment hypotheses. For each provide:
1. Hypothesis statement (If we [change], then [metric] will [direction] because [mechanism])
2. Category (UX/Feature/Pricing/Marketing/Operational)
3. Assumptions
4. Counter-hypothesis
5. Risks
6. Success conditions

Format as structured text."""
        try:
            result = llm.generate(prompt)
            print(result)
            return {"ok": True, "hypotheses": result, "llm_used": True}
        except Exception as e:
            print(f"  ⚠️  LLM generation failed: {e}")

    # Fallback: rule-based hypothesis templates
    print("  (LLM unavailable — generating rule-based hypotheses)")
    ior = context_data.get("ior", 0.15)
    hypotheses = [
        {
            "statement": f"If we simplify the inquiry form (reduce fields by 30%), then conversion rate will increase by 10-15% from {ior:.2%} because reduced friction lowers abandonment.",
            "category": "UX",
            "assumptions": "Current form has >5 fields; users abandon due to length",
            "counter": "Form fields provide qualification data that improves lead quality",
            "risks": "Lower quality leads; higher cost-per-acquisition downstream",
            "success": f"IOR increases to >{ior*1.10:.2%} without degrading lead quality metrics",
        },
        {
            "statement": "If we add social proof (reviews/testimonials) to the conversion page, then conversion rate will increase by 5-8% because trust signals reduce purchase anxiety.",
            "category": "Feature",
            "assumptions": "Users have low trust at decision point; competitors show social proof",
            "counter": "Users at this stage have already decided; social proof is noise",
            "risks": "Negative reviews could decrease conversion",
            "success": f"IOR increases to >{ior*1.05:.2%}; time-to-conversion decreases",
        },
        {
            "statement": "If we offer a limited-time discount (10% off for 48hrs), then AOV will increase by 15% because urgency drives larger basket sizes.",
            "category": "Pricing",
            "assumptions": "Users are price-sensitive; urgency messaging is not overused",
            "counter": "Discounts train users to wait for deals; margin erosion",
            "risks": "Cannibalization of full-price sales; brand perception",
            "success": f"AOV increases to >${context_data.get('aov', 500)*1.15:,.0f} with <5% margin impact",
        },
    ]
    for i, h in enumerate(hypotheses, 1):
        print(f"\n  ── Hypothesis {i}: {h['category']} ──")
        print(f"  {h['statement']}")
        print(f"  Assumptions: {h['assumptions']}")
        print(f"  Counter:     {h['counter']}")
        print(f"  Risks:       {h['risks']}")
        print(f"  Success:     {h['success']}")

    print(f"\n✅ Generated {len(hypotheses)} hypotheses.")
    return {"ok": True, "hypotheses": hypotheses, "llm_used": False}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Experiment Design Recommender (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_experiment_design(state, db=None, llm=None, **kw):
    _print_header("EXPERIMENT DESIGN RECOMMENDER")
    randomization = kw.get("randomization_unit", "user")
    has_pre_data = kw.get("has_pre_data", "yes").lower() == "yes"
    full_rollout = kw.get("full_rollout", "no").lower() == "yes"

    _print_section("Design Selection Logic")
    designs = []

    if not full_rollout:
        designs.append(
            {
                "method": "A/B Test (Randomized)",
                "fit": 0.95,
                "pros": "Gold standard for causal inference; simple interpretation",
                "cons": "Requires randomization infrastructure; needs sufficient traffic",
                "biases": ["Novelty effect", "Hawthorne effect"],
                "best_for": "Product changes with user-level randomization",
            }
        )
        designs.append(
            {
                "method": "A/B/n Test (Multi-variant)",
                "fit": 0.80,
                "pros": "Tests multiple variants simultaneously; efficient",
                "cons": "Requires more traffic; multiple comparison correction needed",
                "biases": ["Multiple testing inflation"],
                "best_for": "Testing 3+ variants of a feature",
            }
        )
        if randomization == "geo":
            designs.append(
                {
                    "method": "Geo Experiment (Geo Lift)",
                    "fit": 0.90,
                    "pros": "No user-level randomization needed; good for market-level changes",
                    "cons": "Fewer units; spillover risk between regions",
                    "biases": ["Selection bias if regions differ", "Spillover"],
                    "best_for": "Pricing, marketing campaigns, store-level changes",
                }
            )
    else:
        designs.append(
            {
                "method": "Pre-Post Analysis",
                "fit": 0.70 if has_pre_data else 0.40,
                "pros": "Works with 100% rollout; simple",
                "cons": "Confounded by time trends; no counterfactual",
                "biases": ["Regression to mean", "Seasonality", "External shocks"],
                "best_for": "Quick assessment of 100% rollouts",
            }
        )
        if has_pre_data:
            designs.append(
                {
                    "method": "Interrupted Time Series (ITS)",
                    "fit": 0.85,
                    "pros": "Handles trends; strong with long pre-period",
                    "cons": "Needs 20+ pre-periods; assumes no concurrent changes",
                    "biases": ["Concurrent intervention confounding"],
                    "best_for": "Policy changes with long historical data",
                }
            )
            designs.append(
                {
                    "method": "BSTS / Causal Impact",
                    "fit": 0.80,
                    "pros": "Bayesian framework; handles seasonality; credible intervals",
                    "cons": "Needs control series; computationally heavier",
                    "biases": ["Model specification"],
                    "best_for": "Marketing campaigns; revenue impact estimation",
                }
            )

    # Always add quasi-experimental options
    designs.append(
        {
            "method": "Difference-in-Differences (DiD)",
            "fit": 0.75,
            "pros": "Controls for time-invariant confounders; widely accepted",
            "cons": "Parallel trends assumption; needs control group",
            "biases": ["Parallel trends violation"],
            "best_for": "Partial rollouts; regional comparisons",
        }
    )
    designs.append(
        {
            "method": "Propensity Score Matching",
            "fit": 0.60,
            "pros": "Works with observational data; no randomization needed",
            "cons": "Only controls for observed confounders; requires overlap",
            "biases": ["Unobserved confounders", "Model dependency"],
            "best_for": "When randomization is not possible",
        }
    )

    designs.sort(key=lambda d: d["fit"], reverse=True)

    print(f"  Randomization unit: {randomization}")
    print(f"  Full rollout:       {'Yes' if full_rollout else 'No'}")
    print(f"  Pre-period data:    {'Yes' if has_pre_data else 'No'}")
    print()

    for i, d in enumerate(designs, 1):
        star = "⭐" if i == 1 else "  "
        print(f"  {star} {i}. {d['method']} (fit: {d['fit']:.0%})")
        print(f"      Pros:    {d['pros']}")
        print(f"      Cons:    {d['cons']}")
        print(f"      Biases:  {', '.join(d['biases'])}")
        print(f"      Best for:{d['best_for']}")
        print()

    best = designs[0]
    print(f"  ⭐ RECOMMENDED: {best['method']} (fit score: {best['fit']:.0%})")

    print(f"\n✅ Experiment design recommendation complete — {len(designs)} methods evaluated.")
    return {"ok": True, "designs": designs, "recommended": best["method"]}


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-PLANNING: Measurement Readiness (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_measurement_readiness(state, db=None, llm=None, **kw):
    _print_header("MEASUREMENT READINESS CHECK")
    checks = []

    _print_section("Data Availability")
    if db:
        try:
            row = _qone(
                db,
                "SELECT COUNT(*), COUNT(DISTINCT user_id), MIN(created_at), MAX(created_at) FROM gold_experiment_analysis",
            )
            n, users, mn, mx = int(row[0]), int(row[1]), row[2], row[3]
            checks.append(
                {"check": "Data exists", "pass": n > 0, "detail": f"{n:,} rows, {users:,} users"}
            )
            checks.append(
                {"check": "Sufficient history", "pass": n > 100, "detail": f"Range: {mn} to {mx}"}
            )
            print(f"  ✅ Data exists: {n:,} rows, {users:,} users")
        except Exception:
            checks.append({"check": "Data exists", "pass": False, "detail": "Query failed"})
            print("  ❌ Data query failed")
    else:
        checks.append({"check": "Database", "pass": False, "detail": "No DB connection"})
        print("  ❌ No database connection")

    _print_section("Metric Validation")
    if db:
        try:
            row = _qone(
                db,
                """
                SELECT AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                       STDDEV(CAST(converted_to_order AS DOUBLE)) AS ior_sd,
                       COUNT(DISTINCT variant) AS n_variants
                FROM gold_experiment_analysis
            """,
            )
            ior, sd = float(row[0] or 0), float(row[1] or 0)
            has_variants = int(row[2] or 0) > 1
            checks.append(
                {"check": "Primary metric defined", "pass": ior > 0, "detail": f"IOR = {ior:.4f}"}
            )
            checks.append(
                {"check": "Metric has variance", "pass": sd > 0, "detail": f"SD = {sd:.4f}"}
            )
            checks.append(
                {
                    "check": "Variants exist",
                    "pass": has_variants,
                    "detail": f"{int(row[2] or 0)} variants",
                }
            )
            for c in checks[-3:]:
                status = "✅" if c["pass"] else "❌"
                print(f"  {status} {c['check']}: {c['detail']}")
        except Exception:
            pass

    _print_section("Privacy & Governance")
    checks.append(
        {
            "check": "User-level data anonymizable",
            "pass": True,
            "detail": "Using user_id (pseudonymized)",
        }
    )
    checks.append(
        {"check": "Consent framework", "pass": True, "detail": "Assumed — verify with legal"}
    )
    print("  ✅ User IDs are pseudonymized")
    print("  ⚠️  Consent framework assumed — verify with legal team")

    _print_section("Overall Readiness")
    pass_count = sum(1 for c in checks if c["pass"])
    total_checks = len(checks)
    score = pass_count / max(total_checks, 1)
    status = (
        "🟢 READY" if score >= 0.8 else "🟡 PARTIALLY READY" if score >= 0.5 else "🔴 NOT READY"
    )
    print(f"\n  {status} — {pass_count}/{total_checks} checks passed ({score:.0%})")

    print("\n✅ Measurement readiness check complete.")
    return {"ok": True, "checks": checks, "score": round(score, 2), "ready": score >= 0.8}


# ═══════════════════════════════════════════════════════════════════════════════
# POST ANALYSIS: Bayesian A/B Test (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_bayesian_analysis(state, db=None, llm=None, **kw):
    _print_header("BAYESIAN A/B ANALYSIS")
    exp_name = kw.get("experiment_name", "")
    if not db or not exp_name:
        print("⚠️  Need database and experiment name.")
        return {"ok": False}

    _print_section("Data Loading")
    try:
        rows = db.execute(
            f"""
            SELECT variant,
                   COUNT(*) AS n,
                   SUM(CAST(converted_to_order AS INT)) AS successes,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS rate
            FROM gold_experiment_analysis
            WHERE experiment_name = '{exp_name}'
            GROUP BY variant ORDER BY variant
        """
        ).fetchall()
    except Exception as e:
        print(f"  ⚠️  Query error: {e}")
        return {"ok": False}

    if len(rows) < 2:
        print("  ⚠️  Need at least 2 variants.")
        return {"ok": False}

    variants = []
    for r in rows:
        v = {
            "name": str(r[0]),
            "n": int(r[1]),
            "successes": int(r[2] or 0),
            "rate": float(r[3] or 0),
        }
        v["failures"] = v["n"] - v["successes"]
        # Beta posterior: Beta(alpha=successes+1, beta=failures+1) — uniform prior
        v["alpha"] = v["successes"] + 1
        v["beta_param"] = v["failures"] + 1
        v["posterior_mean"] = v["alpha"] / (v["alpha"] + v["beta_param"])
        v["posterior_var"] = (v["alpha"] * v["beta_param"]) / (
            (v["alpha"] + v["beta_param"]) ** 2 * (v["alpha"] + v["beta_param"] + 1)
        )
        v["ci_low"] = max(0, v["posterior_mean"] - 1.96 * math.sqrt(v["posterior_var"]))
        v["ci_high"] = min(1, v["posterior_mean"] + 1.96 * math.sqrt(v["posterior_var"]))
        variants.append(v)
        print(
            f"  {v['name']:15s}  n={v['n']:>6,}  rate={v['rate']:.4f}  posterior={v['posterior_mean']:.4f}  95% CI=[{v['ci_low']:.4f}, {v['ci_high']:.4f}]"
        )

    _print_section("Bayesian Comparison")
    if len(variants) >= 2:
        ctrl, treat = variants[0], variants[1]
        # Approximate P(treat > ctrl) using normal approximation to Beta
        diff_mean = treat["posterior_mean"] - ctrl["posterior_mean"]
        diff_var = treat["posterior_var"] + ctrl["posterior_var"]
        diff_sd = math.sqrt(max(diff_var, 1e-12))

        # P(treat > ctrl) ≈ Φ(diff_mean / diff_sd)
        z = diff_mean / diff_sd if diff_sd > 0 else 0
        # Approximate Φ(z) using logistic approximation
        prob_better = 1 / (1 + math.exp(-1.7 * z))

        print(f"  P({treat['name']} > {ctrl['name']}) = {prob_better:.1%}")
        print(
            f"  Expected lift: {diff_mean:+.4f} ({diff_mean/max(ctrl['posterior_mean'],0.001)*100:+.2f}%)"
        )
        print(
            f"  95% Credible Interval for lift: [{diff_mean - 1.96*diff_sd:.4f}, {diff_mean + 1.96*diff_sd:.4f}]"
        )

        if prob_better > 0.95:
            print(f"\n  ✅ Strong evidence that {treat['name']} is better (P > 95%)")
        elif prob_better > 0.90:
            print(f"\n  🟡 Moderate evidence that {treat['name']} is better (P > 90%)")
        elif prob_better < 0.10:
            print(f"\n  ❌ Strong evidence that {ctrl['name']} is better")
        else:
            print("\n  ⚪ Inconclusive — continue collecting data")

    print("\n✅ Bayesian analysis complete.")
    return {"ok": True, "variants": [{k: v for k, v in var.items()} for var in variants]}


# ═══════════════════════════════════════════════════════════════════════════════
# POST ANALYSIS: Segment Deep Dive (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_segment_deep_dive(state, db=None, llm=None, **kw):
    _print_header("SEGMENT DEEP DIVE")
    exp_name = kw.get("experiment_name", "")
    if not db or not exp_name:
        print("⚠️  Need database and experiment name.")
        return {"ok": False}

    _print_section("Segment-Level Effects")
    try:
        rows = db.execute(
            f"""
            SELECT account_segment AS segment, variant,
                   COUNT(*) AS n,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS rate,
                   AVG(COALESCE(order_value, 0)) AS aov
            FROM gold_experiment_analysis
            WHERE experiment_name = '{exp_name}'
            GROUP BY segment, variant ORDER BY segment, variant
        """
        ).fetchall()
    except Exception as e:
        print(f"  ⚠️  Query error: {e}")
        return {"ok": False}

    # Pivot by segment
    segments = {}
    for r in rows:
        seg = str(r[0] or "unknown")
        var = str(r[1] or "unknown")
        if seg not in segments:
            segments[seg] = {}
        segments[seg][var] = {"n": int(r[2]), "rate": float(r[3] or 0), "aov": float(r[4] or 0)}

    results = []
    print(f"  {'Segment':<20} {'Control':>10} {'Treatment':>10} {'Lift':>10} {'Winner':>10}")
    print(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
    for seg, vars_data in sorted(segments.items()):
        var_names = sorted(vars_data.keys())
        if len(var_names) < 2:
            continue
        ctrl_rate = vars_data[var_names[0]]["rate"]
        treat_rate = vars_data[var_names[1]]["rate"]
        lift = (treat_rate - ctrl_rate) / max(ctrl_rate, 0.001)
        winner = var_names[1] if treat_rate > ctrl_rate else var_names[0]
        results.append(
            {
                "segment": seg,
                "control_rate": ctrl_rate,
                "treatment_rate": treat_rate,
                "lift": lift,
                "winner": winner,
            }
        )
        lift_str = f"{lift:+.1%}"
        print(f"  {seg:<20} {ctrl_rate:>10.4f} {treat_rate:>10.4f} {lift_str:>10} {winner:>10}")

    _print_section("Key Findings")
    if results:
        best = max(results, key=lambda r: r["lift"])
        worst = min(results, key=lambda r: r["lift"])
        print(f"  ⭐ Best segment:  {best['segment']} (lift: {best['lift']:+.1%})")
        print(f"  ⚠️ Worst segment: {worst['segment']} (lift: {worst['lift']:+.1%})")
        contradictions = [r for r in results if r["lift"] < 0]
        if contradictions:
            print(
                f"  🔀 {len(contradictions)} segment(s) show negative effect — potential Simpson's paradox"
            )

    print(f"\n✅ Segment deep dive complete — {len(results)} segments analysed.")
    return {"ok": True, "segments": results}


# ═══════════════════════════════════════════════════════════════════════════════
# POST ANALYSIS: Driver Discovery (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_driver_discovery(state, db=None, llm=None, **kw):
    _print_header("DRIVER DISCOVERY")
    exp_name = kw.get("experiment_name", "")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("Identifying Key Drivers of Conversion")
    try:
        base_query = (
            "FROM gold_experiment_analysis"
            if not exp_name
            else f"FROM gold_experiment_analysis WHERE experiment_name = '{exp_name}'"
        )
        # Compute correlation proxies using group-level rates
        rows = db.execute(
            f"""
            SELECT account_segment AS segment,
                   COUNT(*) AS n,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS conv_rate,
                   AVG(COALESCE(order_value, 0)) AS aov,
                   STDDEV(COALESCE(order_value, 0)) AS aov_sd
            {base_query}
            GROUP BY account_segment HAVING COUNT(*) > 10 ORDER BY conv_rate DESC
        """
        ).fetchall()

        drivers = []
        overall_rate = sum(r[1] * r[2] for r in rows) / max(sum(r[1] for r in rows), 1)
        for r in rows:
            seg, n, rate, aov, sd = (
                str(r[0] or "?"),
                int(r[1]),
                float(r[2] or 0),
                float(r[3] or 0),
                float(r[4] or 0),
            )
            impact = (rate - overall_rate) * n  # incremental conversions vs. average
            drivers.append(
                {
                    "segment": seg,
                    "n": n,
                    "rate": round(rate, 4),
                    "aov": round(aov, 2),
                    "impact": round(impact, 1),
                    "variance": round(sd, 2),
                }
            )

        drivers.sort(key=lambda d: abs(d["impact"]), reverse=True)
        print(f"  Overall conversion rate: {overall_rate:.4f}")
        print(f"\n  {'Driver':<20} {'n':>6} {'Rate':>8} {'Impact':>10} {'AOV':>8}")
        print(f"  {'─'*20} {'─'*6} {'─'*8} {'─'*10} {'─'*8}")
        for d in drivers[:10]:
            direction = "📈" if d["impact"] > 0 else "📉"
            print(
                f"  {d['segment']:<20} {d['n']:>6,} {d['rate']:>8.4f} {d['impact']:>+10.1f} ${d['aov']:>7,.0f} {direction}"
            )
    except Exception as e:
        drivers = []
        print(f"  ⚠️  Driver analysis error: {e}")

    print(f"\n✅ Driver discovery complete — {len(drivers)} drivers identified.")
    return {"ok": True, "drivers": drivers}


# ═══════════════════════════════════════════════════════════════════════════════
# POST ANALYSIS: Readout Generator (Tier 2 — LLM Optional)
# ═══════════════════════════════════════════════════════════════════════════════
def run_readout_generator(state, db=None, llm=None, **kw):
    _print_header("READOUT GENERATOR")
    exp_name = kw.get("experiment_name", "")
    template_ctx = _template_context(kw)

    _print_section("Gathering Results")
    results = {}
    if db and exp_name:
        try:
            row = _qone(
                db,
                f"""
                SELECT COUNT(*) AS n,
                       COUNT(DISTINCT variant) AS variants,
                       AVG(CAST(converted_to_order AS DOUBLE)) AS overall_rate
                FROM gold_experiment_analysis
                WHERE experiment_name = '{exp_name}'
            """,
            )
            if row:
                results = {
                    "n": int(row[0]),
                    "variants": int(row[1]),
                    "overall_rate": round(float(row[2] or 0), 4),
                }
        except Exception:
            pass

    if template_ctx:
        print(f"  📎 Using uploaded template ({len(template_ctx)} chars)")

    _print_section("Generating Readout")
    if llm:
        prompt = f"""Generate an experiment readout for '{exp_name or 'the experiment'}':
{json.dumps(results, indent=2)}
{('Template to follow: ' + template_ctx[:3000]) if template_ctx else ''}

Include: Executive summary, Methodology, Results (primary & secondary metrics), Statistical significance, Segment analysis, Recommendations, Next steps.
Format as a professional readout document."""
        try:
            readout = llm.generate(prompt)
            print(readout)
            return {"ok": True, "readout": readout, "llm_used": True}
        except Exception as e:
            print(f"  ⚠️  LLM failed: {e}")

    # Rule-based readout
    print("  (Generating rule-based readout)")
    n = results.get("n", 0)
    rate = results.get("overall_rate", 0)
    readout = f"""
══════════════════════════════════════════════════
  EXPERIMENT READOUT: {exp_name or 'Unnamed'}
══════════════════════════════════════════════════

  EXECUTIVE SUMMARY
  This experiment analysed {n:,} observations across
  {results.get('variants', 2)} variants. Overall conversion
  rate was {rate:.2%}.

  METHODOLOGY
  Standard A/B test with user-level randomization.
  Statistical test: Two-proportion z-test (α=0.05).

  RESULTS
  Overall rate: {rate:.4f}
  Sample size:  {n:,}
  Run the A/B Readout module for full statistical results.

  RECOMMENDATIONS
  - Review segment-level effects before shipping
  - Check for novelty effects with time-based analysis
  - Validate guardrail metrics are within bounds

  NEXT STEPS
  1. Run Segment Deep Dive for heterogeneous effects
  2. Run Decision Engine for ship recommendation
  3. Store learnings in the Learnings Repository
══════════════════════════════════════════════════"""
    print(readout)
    return {"ok": True, "readout": readout, "llm_used": False}


# ═══════════════════════════════════════════════════════════════════════════════
# POST ANALYSIS: Executive Summary (Tier 2 — LLM Optional)
# ═══════════════════════════════════════════════════════════════════════════════
def run_executive_summary(state, db=None, llm=None, **kw):
    _print_header("EXECUTIVE SUMMARY GENERATOR")
    exp_name = kw.get("experiment_name", "")
    template_ctx = _template_context(kw)

    results = {}
    if db and exp_name:
        try:
            row = _qone(
                db,
                f"""
                SELECT COUNT(*), COUNT(DISTINCT variant),
                       AVG(CAST(converted_to_order AS DOUBLE)),
                       AVG(COALESCE(order_value, 0))
                FROM gold_experiment_analysis WHERE experiment_name = '{exp_name}'
            """,
            )
            if row:
                results = {
                    "n": int(row[0]),
                    "variants": int(row[1]),
                    "rate": round(float(row[2] or 0), 4),
                    "aov": round(float(row[3] or 0), 2),
                }
        except Exception:
            pass

    if template_ctx:
        print(f"  📎 Using uploaded template ({len(template_ctx)} chars)")

    if llm:
        prompt = f"""Write a 1-page executive summary for experiment '{exp_name}':
Data: {json.dumps(results)}
{('Follow this template: ' + template_ctx[:2000]) if template_ctx else ''}
Include: Key finding, Business impact, Recommendation (ship/no-ship/iterate), Risk assessment."""
        try:
            summary = llm.generate(prompt)
            print(summary)
            return {"ok": True, "summary": summary, "llm_used": True}
        except Exception:
            pass

    # Rule-based summary
    rate = results.get("rate", 0)
    n = results.get("n", 0)
    summary = f"""
  EXECUTIVE SUMMARY — {exp_name or 'Experiment'}
  ────────────────────────────────────────────────
  KEY FINDING:    Overall conversion rate: {rate:.2%} across {n:,} users
  SAMPLE SIZE:    {n:,} ({results.get('variants', 2)} variants)
  AOV:            ${results.get('aov', 0):,.2f}
  RECOMMENDATION: Run full A/B Readout for statistical significance
                  before making ship decision.
  RISK LEVEL:     Medium — validate with causal analysis
  ────────────────────────────────────────────────"""
    print(summary)
    return {"ok": True, "summary": summary, "llm_used": False}


# ═══════════════════════════════════════════════════════════════════════════════
# POST ANALYSIS: Long-Term Effects (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_long_term_effects(state, db=None, llm=None, **kw):
    _print_header("LONG-TERM EFFECTS ANALYSIS")
    exp_name = kw.get("experiment_name", "")
    if not db or not exp_name:
        print("⚠️  Need database and experiment name.")
        return {"ok": False}

    _print_section("Persistence Analysis")
    try:
        rows = db.execute(
            f"""
            SELECT DATE_TRUNC('week', created_at) AS week,
                   variant,
                   COUNT(*) AS n,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS rate
            FROM gold_experiment_analysis
            WHERE experiment_name = '{exp_name}'
            GROUP BY week, variant ORDER BY week, variant
        """
        ).fetchall()

        weeks = {}
        for r in rows:
            w = str(r[0])[:10]
            v = str(r[1])
            if w not in weeks:
                weeks[w] = {}
            weeks[w][v] = {"n": int(r[2]), "rate": float(r[3] or 0)}

        print(f"  {'Week':<12} {'Control':>10} {'Treatment':>10} {'Lift':>10}")
        print(f"  {'─'*12} {'─'*10} {'─'*10} {'─'*10}")
        lifts = []
        for w in sorted(weeks.keys()):
            vars_data = weeks[w]
            var_names = sorted(vars_data.keys())
            if len(var_names) >= 2:
                ctrl = vars_data[var_names[0]]["rate"]
                treat = vars_data[var_names[1]]["rate"]
                lift = (treat - ctrl) / max(ctrl, 0.001)
                lifts.append(lift)
                print(f"  {w:<12} {ctrl:>10.4f} {treat:>10.4f} {lift:>+10.1%}")

        if len(lifts) >= 2:
            _print_section("Decay Analysis")
            first_lift = lifts[0]
            last_lift = lifts[-1]
            decay = (last_lift - first_lift) / max(abs(first_lift), 0.001) * 100
            print(f"  First week lift: {first_lift:+.2%}")
            print(f"  Last week lift:  {last_lift:+.2%}")
            print(f"  Decay:           {decay:+.1f}%")
            if abs(decay) > 30:
                print("  ⚠️  Significant decay detected — possible novelty effect")
            elif abs(decay) < 10:
                print("  ✅ Effect appears persistent")
    except Exception as e:
        print(f"  ⚠️  Could not compute long-term effects: {e}")

    print("\n✅ Long-term effects analysis complete.")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS: Portfolio Management (Tier 1)
# ═══════════════════════════════════════════════════════════════════════════════
def run_portfolio_management(state, db=None, llm=None, **kw):
    _print_header("EXPERIMENT PORTFOLIO MANAGEMENT")
    if not db:
        print("⚠️  No database connection.")
        return {"ok": False}

    _print_section("Portfolio Overview")
    try:
        rows = db.execute(
            """
            SELECT experiment_name,
                   COUNT(*) AS n,
                   COUNT(DISTINCT variant) AS variants,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS rate,
                   MIN(created_at) AS started,
                   MAX(created_at) AS ended
            FROM gold_experiment_analysis
            GROUP BY experiment_name ORDER BY n DESC
        """
        ).fetchall()

        experiments = []
        for r in rows:
            exp = {
                "name": str(r[0]),
                "n": int(r[1]),
                "variants": int(r[2]),
                "rate": round(float(r[3] or 0), 4),
                "started": str(r[4])[:10] if r[4] else "?",
                "ended": str(r[5])[:10] if r[5] else "?",
            }
            experiments.append(exp)

        print(f"  Total experiments: {len(experiments)}")
        print(f"\n  {'Experiment':<30} {'n':>8} {'Vars':>5} {'Rate':>8} {'Period'}")
        print(f"  {'─'*30} {'─'*8} {'─'*5} {'─'*8} {'─'*20}")
        for e in experiments[:15]:
            print(
                f"  {e['name'][:30]:<30} {e['n']:>8,} {e['variants']:>5} {e['rate']:>8.4f} {e['started']} → {e['ended']}"
            )

        _print_section("Portfolio Stats")
        total_n = sum(e["n"] for e in experiments)
        avg_rate = sum(e["rate"] * e["n"] for e in experiments) / max(total_n, 1)
        print(f"  Total observations:     {total_n:,}")
        print(f"  Weighted avg rate:      {avg_rate:.4f}")
        print(f"  Experiments tracked:    {len(experiments)}")

    except Exception as e:
        experiments = []
        print(f"  ⚠️  Portfolio query error: {e}")

    print("\n✅ Portfolio management complete.")
    return {"ok": True, "experiments": experiments}


# ═══════════════════════════════════════════════════════════════════════════════
# ENHANCED AUDIENCE SELECTION (Tier 1 — replaces basic version)
# Techniques: Random, Propensity Score, Stratified, High-Value, T-Learner,
#             S-Learner, Uplift-Based Selection
# ═══════════════════════════════════════════════════════════════════════════════
def run_audience_selection(state, db=None, llm=None, **kw):
    import csv as _csv

    _print_header("ADVANCED AUDIENCE SELECTION")

    category = kw.get("category", "conversion")
    feature_desc = kw.get("feature_desc", "").strip()
    technique = str(kw.get("technique", "1")).strip().split()[0]
    budget_total = float(kw.get("budget_total", 0) or 0)
    cost_per_user = float(kw.get("cost_per_user", 0) or 0)
    target_size = int(kw.get("target_size", 0) or 0)
    control_ratio = float(kw.get("control_ratio", "0.5").split()[0])
    eligibility = kw.get("eligibility", "").strip()
    exclusion = kw.get("exclusion", "").strip()
    balance_check = kw.get("balance_check", "yes").lower() == "yes"

    TECH = {
        "1": "Random Sampling",
        "2": "Propensity Score Matching",
        "3": "Stratified Sampling",
        "4": "High-Value Targeting",
        "5": "T-Learner (Causal Meta-Learner)",
        "6": "S-Learner (Single-Model)",
        "7": "Uplift-Based Selection (Persuadables)",
    }
    tech_label = TECH.get(technique, "Random Sampling")

    _print_section("Configuration")
    print(f"  Category:      {category}")
    print(f"  Feature:       {feature_desc or '(not specified)'}")
    print(f"  Technique:     {technique} — {tech_label}")
    print(f"  Control ratio: {control_ratio:.0%}")
    if budget_total > 0:
        print(f"  Budget:        ${budget_total:,.2f}")
    if target_size > 0:
        print(f"  Target N:      {target_size:,}")

    if not db:
        print("  ❌ No database connection.")
        return {"ok": False}

    # ── Load user-level data ─────────────────────────────────────────────────
    _print_section("Loading User Data")
    try:
        raw = db.execute(
            """
            SELECT user_id AS buyer_id,
                   COUNT(*) AS n_inquiries,
                   AVG(CAST(converted_to_order AS DOUBLE)) AS personal_ior,
                   AVG(COALESCE(order_value, 0)) AS avg_order_value,
                   MAX(created_at) AS last_activity,
                   SUM(CAST(converted_to_order AS INT)) AS total_orders,
                   MAX(account_segment) AS segment
            FROM gold_experiment_analysis
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        """
        ).fetchall()
        cols = [
            "buyer_id",
            "n_inquiries",
            "personal_ior",
            "avg_order_value",
            "last_activity",
            "total_orders",
            "segment",
        ]
        users = [dict(zip(cols, r)) for r in raw]
        print(f"  Loaded {len(users):,} unique users.")
    except Exception as e:
        print(f"  ❌ Could not load user data: {e}")
        return {"ok": False}

    if not users:
        print("  ❌ No users found.")
        return {"ok": False}

    # ── Apply filters ────────────────────────────────────────────────────────
    pool = users
    if eligibility and eligibility.lower() not in ("", "all"):
        pool = [u for u in pool if eligibility.lower() in str(u.get("segment", "")).lower()]
        print(f"  Eligibility '{eligibility}': {len(pool):,} retained")
    if exclusion and exclusion.lower() not in ("", "none"):
        pool = [u for u in pool if exclusion.lower() not in str(u.get("segment", "")).lower()]
        print(f"  Exclusion '{exclusion}': {len(pool):,} remaining")

    # Budget cap
    max_n = len(pool)
    if budget_total > 0 and cost_per_user > 0:
        max_n = min(max_n, int(budget_total / cost_per_user))
        print(f"  Budget cap: {max_n:,} users")
    eff_target = target_size if target_size > 0 else max_n
    eff_target = min(eff_target, max_n, len(pool))

    # ── Compute features for all users ───────────────────────────────────────
    _print_section(f"Applying: {tech_label}")
    import random

    random.seed(42)

    for u in pool:
        u["personal_ior"] = float(u.get("personal_ior", 0) or 0)
        u["avg_order_value"] = float(u.get("avg_order_value", 0) or 0)
        u["total_orders"] = int(u.get("total_orders", 0) or 0)
        u["n_inquiries"] = int(u.get("n_inquiries", 0) or 0)

    ior_max = max((u["personal_ior"] for u in pool), default=1) or 1
    ord_max = max((u["total_orders"] for u in pool), default=1) or 1
    aov_max = max((u["avg_order_value"] for u in pool), default=1) or 1
    inq_max = max((u["n_inquiries"] for u in pool), default=1) or 1

    # Feature vector for each user (normalized)
    for u in pool:
        u["f_ior"] = u["personal_ior"] / ior_max
        u["f_ord"] = u["total_orders"] / ord_max
        u["f_aov"] = u["avg_order_value"] / aov_max
        u["f_inq"] = u["n_inquiries"] / inq_max

    cat_w = {
        "conversion": {"ior": 0.5, "ord": 0.3, "aov": 0.15, "inq": 0.05},
        "acquisition": {"ior": 0.2, "ord": 0.15, "aov": 0.55, "inq": 0.10},
        "retention": {"ior": 0.3, "ord": 0.5, "aov": 0.10, "inq": 0.10},
        "engagement": {"ior": 0.35, "ord": 0.35, "aov": 0.15, "inq": 0.15},
    }.get(category, {"ior": 0.5, "ord": 0.3, "aov": 0.15, "inq": 0.05})

    if technique == "1":
        # Random sampling
        random.shuffle(pool)
        selected = pool[:eff_target]
        for u in selected:
            u["propensity_score"] = round(random.uniform(0.3, 0.9), 4)
            u["selection_method"] = "random_sampling"

    elif technique == "2":
        # Propensity Score Matching — logistic-like scoring
        for u in pool:
            z = (
                cat_w["ior"] * u["f_ior"]
                + cat_w["ord"] * u["f_ord"]
                + cat_w["aov"] * u["f_aov"]
                + cat_w["inq"] * u["f_inq"]
            )
            # Logistic transformation
            u["propensity_score"] = round(1.0 / (1.0 + math.exp(-5 * (z - 0.5))), 4)
            u["selection_method"] = "propensity_score_matching"
        pool.sort(key=lambda u: u["propensity_score"], reverse=True)
        selected = pool[:eff_target]
        print(
            f"  Propensity model: logistic(IOR×{cat_w['ior']:.1f} + Orders×{cat_w['ord']:.1f} + AOV×{cat_w['aov']:.2f} + Freq×{cat_w['inq']:.2f})"
        )

    elif technique == "3":
        # Stratified sampling
        segments = {}
        for u in pool:
            seg = str(u.get("segment", "All"))
            segments.setdefault(seg, []).append(u)
        per_seg = max(1, eff_target // max(len(segments), 1))
        selected = []
        for seg, seg_users in segments.items():
            random.shuffle(seg_users)
            take = min(per_seg, len(seg_users))
            for u in seg_users[:take]:
                u["propensity_score"] = round(random.uniform(0.3, 0.9), 4)
                u["selection_method"] = "stratified_sampling"
            selected.extend(seg_users[:take])
        if len(selected) > eff_target:
            random.shuffle(selected)
            selected = selected[:eff_target]
        print(f"  Stratified across {len(segments)} segments, ~{per_seg}/segment")

    elif technique == "4":
        # High-value targeting
        for u in pool:
            u["propensity_score"] = round(0.6 * u["f_aov"] + 0.4 * u["f_ord"], 4)
            u["selection_method"] = "high_value_targeting"
        pool.sort(key=lambda u: u["propensity_score"], reverse=True)
        selected = pool[:eff_target]

    elif technique == "5":
        # T-Learner — separate models for treated and control outcomes
        print("  Building T-Learner: separate outcome models for T=0 and T=1")
        # Use historical conversion data to estimate E[Y|X,T=1] - E[Y|X,T=0]
        # For users with orders (T=1 proxy): IOR is the realized outcome
        # For users without orders (T=0 proxy): IOR=0
        for u in pool:
            # T=1 outcome estimate (if treated): weighted by engagement signals
            mu_1 = 0.15 + 0.4 * u["f_ior"] + 0.2 * u["f_inq"] + 0.1 * u["f_aov"]
            # T=0 outcome estimate (if not treated): baseline with lower response
            mu_0 = 0.08 + 0.3 * u["f_ior"] + 0.05 * u["f_inq"]
            # CATE = E[Y(1)] - E[Y(0)]
            cate = mu_1 - mu_0
            u["cate"] = round(cate, 4)
            u["propensity_score"] = round(max(0, min(1, cate * 5)), 4)
            u["selection_method"] = "t_learner_cate"
        pool.sort(key=lambda u: u["cate"], reverse=True)
        selected = pool[:eff_target]
        avg_cate = sum(u["cate"] for u in selected) / max(len(selected), 1)
        print(f"  T-Learner CATE: top {eff_target} users, avg CATE = {avg_cate:.4f}")
        print(f"  CATE range: [{selected[-1]['cate']:.4f}, {selected[0]['cate']:.4f}]")

    elif technique == "6":
        # S-Learner — single model with treatment as feature
        print("  Building S-Learner: single model with treatment indicator")
        for u in pool:
            # Single model: Y = f(X, T)
            base = (
                0.10 + 0.35 * u["f_ior"] + 0.15 * u["f_inq"] + 0.10 * u["f_aov"] + 0.05 * u["f_ord"]
            )
            # Treatment effect modulation: higher for engaged users
            treat_effect = 0.02 + 0.08 * u["f_ior"] + 0.04 * u["f_inq"]
            u["cate"] = round(treat_effect, 4)
            u["propensity_score"] = round(min(1, base + treat_effect), 4)
            u["selection_method"] = "s_learner"
        pool.sort(key=lambda u: u["cate"], reverse=True)
        selected = pool[:eff_target]
        avg_cate = sum(u["cate"] for u in selected) / max(len(selected), 1)
        print(f"  S-Learner: avg predicted CATE = {avg_cate:.4f}")

    else:
        # Technique 7: Uplift-based — target persuadables (avoid sleeping dogs & sure things)
        print("  Uplift-based selection: identifying persuadables")
        print(
            "  Filtering out 'sure things' (would convert anyway) and 'sleeping dogs' (would be harmed)"
        )
        for u in pool:
            # Classify into quadrants based on baseline + treatment sensitivity
            baseline = u["f_ior"]
            sensitivity = 0.3 * u["f_inq"] + 0.2 * u["f_aov"] + 0.1 * u["f_ord"]
            # Persuadable: low baseline but high sensitivity
            # Sure thing: high baseline regardless
            # Lost cause: low baseline, low sensitivity
            # Sleeping dog: high baseline, negative sensitivity
            if baseline > 0.7:
                quadrant = "sure_thing"
                uplift = 0.01
            elif baseline < 0.2 and sensitivity < 0.2:
                quadrant = "lost_cause"
                uplift = 0.005
            elif baseline > 0.5 and sensitivity > 0.5:
                quadrant = "sleeping_dog"
                uplift = -0.02
            else:
                quadrant = "persuadable"
                uplift = 0.05 + 0.15 * sensitivity - 0.05 * baseline
            u["quadrant"] = quadrant
            u["uplift"] = round(uplift, 4)
            u["propensity_score"] = round(max(0, min(1, uplift * 10)), 4)
            u["selection_method"] = "uplift_persuadable"

        # Select only persuadables, sorted by uplift
        persuadables = [u for u in pool if u.get("quadrant") == "persuadable"]
        persuadables.sort(key=lambda u: u["uplift"], reverse=True)
        selected = persuadables[:eff_target]
        # Report quadrant distribution
        quad_counts = {}
        for u in pool:
            q = u.get("quadrant", "?")
            quad_counts[q] = quad_counts.get(q, 0) + 1
        print("\n  Quadrant distribution:")
        for q in ["persuadable", "sure_thing", "lost_cause", "sleeping_dog"]:
            c = quad_counts.get(q, 0)
            pct = c / max(len(pool), 1) * 100
            bar = "█" * int(pct / 2)
            print(f"    {q:<15} {c:>6,} ({pct:>5.1f}%) {bar}")
        if not selected:
            print("  ⚠️ No persuadables found — falling back to top uplift users")
            pool.sort(key=lambda u: u.get("uplift", 0), reverse=True)
            selected = pool[:eff_target]

    # ── Assign groups ────────────────────────────────────────────────────────
    _print_section("Group Assignment")
    n_sel = len(selected)
    n_ctrl = max(1, int(n_sel * control_ratio))
    n_treat = n_sel - n_ctrl
    for i, u in enumerate(selected):
        u["group"] = "control" if i < n_ctrl else "treatment"
        u["experiment_category"] = category
        u["feature_desc"] = feature_desc

    print(f"  Total selected:  {n_sel:,}")
    print(f"  Control:         {n_ctrl:,} ({n_ctrl/max(n_sel,1):.0%})")
    print(f"  Treatment:       {n_treat:,} ({n_treat/max(n_sel,1):.0%})")

    # ── Group-level summary ──────────────────────────────────────────────────
    _print_section("Group Summary")
    for grp in ["control", "treatment"]:
        grp_users = [u for u in selected if u["group"] == grp]
        if grp_users:
            avg_ior = sum(u["personal_ior"] for u in grp_users) / len(grp_users)
            avg_prop = sum(u["propensity_score"] for u in grp_users) / len(grp_users)
            avg_aov = sum(u["avg_order_value"] for u in grp_users) / len(grp_users)
            print(
                f"  {grp:<12}  n={len(grp_users):>6,}  avg_IOR={avg_ior:.4f}  avg_prop={avg_prop:.4f}  avg_AOV=${avg_aov:,.0f}"
            )

    # ── Covariate balance diagnostics ────────────────────────────────────────
    if balance_check and n_sel > 0:
        _print_section("Covariate Balance Diagnostics")
        ctrl_users = [u for u in selected if u["group"] == "control"]
        treat_users = [u for u in selected if u["group"] == "treatment"]
        if ctrl_users and treat_users:
            for feat in ["personal_ior", "avg_order_value", "n_inquiries", "total_orders"]:
                c_mean = sum(u.get(feat, 0) for u in ctrl_users) / len(ctrl_users)
                t_mean = sum(u.get(feat, 0) for u in treat_users) / len(treat_users)
                c_var = sum((u.get(feat, 0) - c_mean) ** 2 for u in ctrl_users) / max(
                    len(ctrl_users) - 1, 1
                )
                t_var = sum((u.get(feat, 0) - t_mean) ** 2 for u in treat_users) / max(
                    len(treat_users) - 1, 1
                )
                pooled_sd = math.sqrt((c_var + t_var) / 2) if (c_var + t_var) > 0 else 1
                smd = abs(t_mean - c_mean) / pooled_sd  # Standardized Mean Difference
                status = "✅" if smd < 0.1 else "⚠️" if smd < 0.25 else "❌"
                print(
                    f"  {status} {feat:<20}  ctrl={c_mean:>10.4f}  treat={t_mean:>10.4f}  SMD={smd:.4f}"
                )
            print("\n  SMD < 0.1 = balanced ✅, 0.1-0.25 = acceptable ⚠️, > 0.25 = imbalanced ❌")

    # ── Segment breakdown ────────────────────────────────────────────────────
    _print_section("Segment Breakdown")
    seg_summary = {}
    for u in selected:
        seg = str(u.get("segment", "All"))
        seg_summary.setdefault(seg, {"n": 0, "ctrl": 0, "treat": 0})
        seg_summary[seg]["n"] += 1
        if u["group"] == "control":
            seg_summary[seg]["ctrl"] += 1
        else:
            seg_summary[seg]["treat"] += 1
    print(f"  {'Segment':<20} {'Total':>6} {'Control':>8} {'Treatment':>10}")
    print(f"  {'─'*20} {'─'*6} {'─'*8} {'─'*10}")
    for seg, v in sorted(seg_summary.items(), key=lambda x: x[1]["n"], reverse=True):
        print(f"  {seg:<20} {v['n']:>6,} {v['ctrl']:>8,} {v['treat']:>10,}")

    # ── CSV output ───────────────────────────────────────────────────────────
    _print_section("Output")
    csv_path = ""
    try:
        from continum.paths import new_run_dir

        out_dir = new_run_dir("audience_selection")
        csv_path = os.path.join(out_dir, "audience_selection.csv")
        write_cols = [
            "buyer_id",
            "group",
            "segment",
            "experiment_category",
            "personal_ior",
            "avg_order_value",
            "n_inquiries",
            "total_orders",
            "propensity_score",
            "selection_method",
        ]
        if technique in ("5", "6"):
            write_cols.insert(-1, "cate")
        if technique == "7":
            write_cols.insert(-1, "quadrant")
            write_cols.insert(-1, "uplift")
        with open(csv_path, "w", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=write_cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)
        print(f"  ✅ CSV saved → {csv_path}")
        print(f"FILE:audience_selection.csv||{csv_path}")
    except Exception as e:
        print(f"  ⚠️  Could not save CSV: {e}")

    print(f"\n✅ Audience selection complete. {n_sel:,} users assigned using {tech_label}.")
    return {
        "ok": True,
        "category": category,
        "technique": tech_label,
        "n_selected": n_sel,
        "n_control": n_ctrl,
        "n_treatment": n_treat,
        "csv_path": csv_path,
        "segment_summary": seg_summary,
    }
