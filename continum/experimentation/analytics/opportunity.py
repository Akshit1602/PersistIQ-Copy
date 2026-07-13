from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger("continum.analytics.opportunity")


# ─────────────────────────────────────────────────────────────────────────────
# FUNNEL TAXONOMY
# ─────────────────────────────────────────────────────────────────────────────

FUNNEL_TAXONOMY: Dict[str, Dict] = {
    "acquisition": {
        "label": "Traffic & Sign-Up (Acquisition)",
        "primary_metric": "signup_rate",
        "keywords": [
            "login",
            "sign",
            "auth",
            "oauth",
            "register",
            "onboard",
            "traffic",
            "landing",
            "seo",
            "ad",
            "referral",
            "invite",
        ],
        "mde_benchmarks": {
            "min_rel": 0.10,
            "max_rel": 0.30,
            "label": "10–30% relative lift on sign-up rate",
        },
        "tracking_events": [
            "page_view",
            "signup_start",
            "signup_complete",
            "verification_email_sent",
            "signup_abandoned",
        ],
        "guardrail_pool": [
            "email_verification_rate",
            "page_load_time_p95",
            "backend_error_rate",
            "signup_error_rate",
        ],
        "questions": [
            ("monthly_visitors", "Monthly unique visitors", "visitors/mo", False),
            ("signup_rate", "Current sign-up rate (%)", "rate %", True),
            ("activation_rate", "% new sign-ups who submit first inquiry in 30d", "rate %", True),
            ("ior", "Average IOR for activated users (%)", "rate %", True),
            ("aov", "Average order value ($)", "dollars", False),
            ("gross_margin", "Gross margin (%)", "rate %", True),
            ("horizon", "Time horizon (months)", "months", False),
        ],
    },
    "activation": {
        "label": "Activation & Onboarding",
        "primary_metric": "activation_rate",
        "keywords": [
            "onboard",
            "first",
            "welcome",
            "setup",
            "profile",
            "wizard",
            "activation",
            "tutorial",
            "nudge",
            "email",
        ],
        "mde_benchmarks": {
            "min_rel": 0.05,
            "max_rel": 0.20,
            "label": "5–20% relative lift on activation rate",
        },
        "tracking_events": [
            "onboarding_step_completed",
            "onboarding_completed",
            "first_action",
            "profile_completed",
            "nudge_sent",
        ],
        "guardrail_pool": [
            "onboarding_abandonment_rate",
            "time_to_activation",
            "error_rate_onboarding",
        ],
        "questions": [
            ("monthly_signups", "Monthly new sign-ups", "users/mo", False),
            ("activation_rate", "Current activation rate (%)", "rate %", True),
            ("ior", "IOR for activated users (%)", "rate %", True),
            ("aov", "Average order value ($)", "dollars", False),
            ("gross_margin", "Gross margin (%)", "rate %", True),
            ("horizon", "Time horizon (months)", "months", False),
        ],
    },
    "conversion": {
        "label": "Conversion Rate (Checkout / Lead-to-Sale)",
        "primary_metric": "ior",
        "keywords": [
            "checkout",
            "funnel",
            "cart",
            "billing",
            "payment",
            "order",
            "quote",
            "ior",
            "conversion",
            "buy",
            "purchase",
            "accept",
            "submit",
            "lead",
            "sale",
        ],
        "mde_benchmarks": {
            "min_rel": 0.05,
            "max_rel": 0.15,
            "label": "5–15% relative IOR lift (0.5–2pp absolute)",
        },
        "tracking_events": [
            "checkout_initiated",
            "checkout_step_completed",
            "checkout_completed",
            "checkout_abandoned",
            "payment_submitted",
            "payment_failed",
            "order_confirmed",
            "quote_viewed",
            "quote_accepted",
        ],
        "guardrail_pool": [
            "payment_failure_rate",
            "checkout_error_rate",
            "page_load_p95",
            "support_ticket_rate",
        ],
        "questions": [
            ("monthly_inquiries", "Monthly inquiries / leads / carts", "units/mo", False),
            ("ior", "Current conversion rate (%)", "rate %", True),
            ("aov", "Average order value ($)", "dollars", False),
            ("gross_margin", "Gross margin (%)", "rate %", True),
            ("horizon", "Time horizon (months)", "months", False),
        ],
    },
    "retention": {
        "label": "Repeat Orders & Retention",
        "primary_metric": "repeat_order_rate",
        "keywords": [
            "repeat",
            "retention",
            "return",
            "reorder",
            "post.order",
            "ltv",
            "churn",
            "re-engage",
            "loyalty",
            "upsell",
        ],
        "mde_benchmarks": {
            "min_rel": 0.05,
            "max_rel": 0.15,
            "label": "5–15% relative lift on repeat order rate",
        },
        "tracking_events": [
            "reorder_initiated",
            "repeat_order_confirmed",
            "reengagement_email_opened",
            "loyalty_action",
        ],
        "guardrail_pool": ["unsubscribe_rate", "churn_rate", "support_ticket_rate"],
        "questions": [
            ("monthly_orders", "Monthly completed orders", "orders/mo", False),
            ("repeat_rate", "Current repeat order rate (%)", "rate %", True),
            ("aov", "Average order value ($)", "dollars", False),
            ("gross_margin", "Gross margin (%)", "rate %", True),
            ("horizon", "Time horizon (months)", "months", False),
        ],
    },
    "engagement": {
        "label": "UI / UX & Engagement",
        "primary_metric": "ior",
        "keywords": [
            "ui",
            "ux",
            "design",
            "layout",
            "search",
            "recommend",
            "notification",
            "banner",
            "modal",
            "tooltip",
            "button",
            "cta",
            "page",
        ],
        "mde_benchmarks": {
            "min_rel": 0.03,
            "max_rel": 0.10,
            "label": "3–10% relative lift (UX changes tend to be smaller)",
        },
        "tracking_events": [
            "feature_clicked",
            "feature_viewed",
            "cta_clicked",
            "notification_opened",
            "scroll_depth_reached",
        ],
        "guardrail_pool": ["page_load_p95", "error_rate", "bounce_rate"],
        "questions": [
            ("monthly_users", "Monthly active users who see this feature", "users/mo", False),
            ("current_ctr", "Current engagement / click-through rate (%)", "rate %", True),
            ("ctr_to_ior_rate", "% of engaged users who eventually convert (%)", "rate %", True),
            ("aov", "Average order value ($)", "dollars", False),
            ("gross_margin", "Gross margin (%)", "rate %", True),
            ("horizon", "Time horizon (months)", "months", False),
        ],
    },
    "pricing": {
        "label": "Pricing & Monetisation",
        "primary_metric": "ior",
        "keywords": [
            "price",
            "pricing",
            "discount",
            "fee",
            "rate",
            "tier",
            "plan",
            "monetis",
            "anchor",
            "promo",
            "coupon",
            "revenue",
        ],
        "mde_benchmarks": {
            "min_rel": 0.03,
            "max_rel": 0.12,
            "label": "3–12% relative lift (pricing changes have mixed effects)",
        },
        "tracking_events": [
            "pricing_page_viewed",
            "plan_selected",
            "discount_applied",
            "price_compared",
            "upsell_accepted",
        ],
        "guardrail_pool": ["gross_margin", "refund_rate", "churn_rate"],
        "questions": [
            (
                "monthly_inquiries",
                "Monthly quotes that see the pricing change",
                "inquiries/mo",
                False,
            ),
            ("ior", "Current IOR (%)", "rate %", True),
            ("aov", "Current average order value ($)", "dollars", False),
            ("aov_delta_pct", "Expected % change in AOV from pricing (%)", "rate %", True),
            ("gross_margin", "Gross margin (%)", "rate %", True),
            ("horizon", "Time horizon (months)", "months", False),
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────


def classify_feature(description: str, llm=None) -> str:
    desc_lower = description.lower()

    scores: Dict[str, int] = {}
    for cat, meta in FUNNEL_TAXONOMY.items():
        hits = sum(1 for kw in meta["keywords"] if kw in desc_lower)
        if hits > 0:
            scores[cat] = hits

    if scores:
        top_score = max(scores.values())
        top_cats = [c for c, s in scores.items() if s == top_score]
        if len(top_cats) == 1 and top_score >= 2:
            return top_cats[0]

    if llm is None and scores:
        return max(scores, key=scores.get)

    if llm is not None:
        all_cats = list(FUNNEL_TAXONOMY.keys()) + ["other"]
        cat_text = "\n".join(f"  {k}: {v['label']}" for k, v in FUNNEL_TAXONOMY.items())
        prompt = (
            f"Classify this product feature into exactly one category.\n"
            f'Feature: "{description}"\n\nCategories:\n{cat_text}\n'
            f"  other: Does not fit any category above\n\n"
            f'Return ONLY the category key (one of: {", ".join(all_cats)}).\n'
            f"No explanation. Just the key."
        )
        try:
            resp = str(llm.ask(prompt)).strip().lower().split()[0]
            for k in all_cats:
                if k in resp:
                    return k
        except Exception as e:
            logger.debug("LLM classify failed: %s", e)

    return max(scores, key=scores.get) if scores else "conversion"


# ─────────────────────────────────────────────────────────────────────────────
# BASELINES
# ─────────────────────────────────────────────────────────────────────────────


def pull_baselines(db=None) -> Dict[str, Any]:
    defaults = {
        "monthly_visitors": 15000.0,
        "monthly_signups": 450.0,
        "monthly_signins": 6000.0,
        "signup_rate": 0.030,
        "monthly_inquiries": 15000.0,
        "ior": 0.18,
        "ior_stddev": 0.02,
        "aov": 4000.0,
        "monthly_orders": 2700.0,
        "repeat_rate": 0.40,
        "activation_rate": 0.20,
        "segment_baselines": {},
    }
    if db is None:
        return defaults

    try:
        row = db.execute(
            """
            SELECT
                COUNT(DISTINCT inquiry_id) / NULLIF(DATEDIFF('day',MIN(created_at),MAX(created_at))+1,0) * 30.4 AS monthly_inq,
                AVG(CAST(converted_to_order AS DOUBLE))          AS ior,
                STDDEV(CAST(converted_to_order AS DOUBLE))       AS ior_std,
                AVG(CASE WHEN converted_to_order THEN order_value END) AS aov,
                COUNT(CASE WHEN converted_to_order THEN 1 END)
                    / NULLIF(DATEDIFF('month',MIN(created_at),MAX(created_at))+1,0) AS monthly_ord
            FROM silver_inquiries WHERE converted_to_order IS NOT NULL
        """
        ).fetchone()
        if row and row[0] is not None:
            defaults["monthly_inquiries"] = float(row[0] or defaults["monthly_inquiries"])
            defaults["ior"] = float(row[1] or defaults["ior"])
            defaults["ior_stddev"] = float(row[2] or defaults["ior_stddev"])
            defaults["aov"] = float(row[3] or defaults["aov"])
            defaults["monthly_orders"] = float(row[4] or defaults["monthly_orders"])
    except Exception as e:
        logger.debug("Baseline query failed: %s", e)

    try:
        seg_rows = db.execute(
            """
            SELECT account_segment, AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                   COUNT(*) AS n,
                   AVG(CASE WHEN converted_to_order THEN order_value END) AS aov
            FROM silver_inquiries WHERE account_segment IS NOT NULL
            GROUP BY account_segment HAVING COUNT(*) >= 30
        """
        ).fetchall()
        for row in seg_rows:
            defaults["segment_baselines"][str(row[0])] = {
                "ior": float(row[1] or defaults["ior"]),
                "n": int(row[2]),
                "aov": float(row[3] or defaults["aov"]),
            }
    except Exception as e:
        logger.debug("Segment baseline query failed: %s", e)

    try:
        row = db.execute(
            """
            SELECT
                SUM(total_sessions)/NULLIF(COUNT(DISTINCT date),0)*30.4 AS monthly_vis,
                SUM(new_signups)/NULLIF(COUNT(DISTINCT date),0)*30.4    AS monthly_su,
                SUM(signed_in)/NULLIF(COUNT(DISTINCT date),0)*30.4      AS monthly_si
            FROM silver_traffic
            WHERE date >= (SELECT MAX(date) - INTERVAL 3 MONTH FROM silver_traffic)
        """
        ).fetchone()
        if row and row[0]:
            defaults["monthly_visitors"] = float(row[0])
            defaults["monthly_signups"] = float(row[1] or defaults["monthly_signups"])
            defaults["monthly_signins"] = float(row[2] or defaults["monthly_signins"])
            vis = max(defaults["monthly_visitors"], 1)
            defaults["signup_rate"] = defaults["monthly_signups"] / vis
    except Exception as e:
        logger.debug("Traffic baseline query failed: %s", e)

    return defaults


# ─────────────────────────────────────────────────────────────────────────────
# MDE RECOMMENDER
# ─────────────────────────────────────────────────────────────────────────────


def recommend_mde(
    baseline_rate: float,
    category: str,
    baselines: Dict,
    alpha: float = 0.05,
    power: float = 0.80,
) -> Dict:
    from scipy.stats import norm as _norm

    cat_vol_map = {
        "acquisition": baselines.get("monthly_visitors", 10000) / 30.4 / 2,
        "activation": baselines.get("monthly_signups", 500) / 30.4 / 2,
        "conversion": baselines.get("monthly_inquiries", 500) / 30.4 / 2,
        "retention": baselines.get("monthly_orders", 300) / 30.4 / 2,
        "engagement": baselines.get("monthly_signins", 500) / 30.4 / 2,
        "pricing": baselines.get("monthly_inquiries", 500) / 30.4 / 2,
    }
    daily_n = cat_vol_map.get(category, baselines.get("monthly_inquiries", 500) / 30.4 / 2)
    n_4weeks = daily_n * 28

    p = baseline_rate
    z_a = _norm.ppf(1 - alpha / 2)
    z_b = _norm.ppf(power)
    # Exact formula for two-proportion test
    se = np.sqrt(2 * p * (1 - p) / n_4weeks) if n_4weeks > 0 else 0.01  # noqa: F841
    stat_min_abs = (z_a + z_b) * np.sqrt(2 * p * (1 - p) / n_4weeks) if n_4weeks > 0 else p * 0.10

    biz_min_abs = p * 0.01
    bench = FUNNEL_TAXONOMY.get(category, {}).get("mde_benchmarks", {})
    bench_mid = p * (bench.get("min_rel", 0.05) + bench.get("max_rel", 0.15)) / 2

    recommended = max(stat_min_abs, biz_min_abs)

    return {
        "stat_min_abs": round(stat_min_abs, 5),
        "stat_min_rel_pct": round(stat_min_abs / p * 100, 2) if p > 0 else 10.0,
        "biz_min_abs": round(biz_min_abs, 5),
        "biz_min_rel_pct": 1.0,
        "bench_range": bench.get("label", ""),
        "bench_mid_abs": round(bench_mid, 5),
        "bench_mid_rel_pct": round(bench_mid / p * 100, 1) if p > 0 else 10.0,
        "recommended_abs": round(recommended, 5),
        "recommended_rel_pct": round(recommended / p * 100, 1) if p > 0 else 10.0,
        "n_4weeks": int(n_4weeks),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC OPPORTUNITY COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────


def compute_dynamic_opportunity(
    category: str,
    answers: Dict[str, Any],
) -> Dict:
    mde_info = answers.get("_mde", {})
    rec_abs = mde_info.get("recommended_abs", 0.01)
    horizon = int(answers.get("horizon", 12))
    gm = float(answers.get("gross_margin", 0.30))
    aov = float(answers.get("aov", 4000))

    funnel_chain: List[Tuple[str, str, str, str]] = []
    incremental: float = 0.0

    if category == "acquisition":
        visitors = float(answers.get("monthly_visitors", 10000))
        curr_su = float(answers.get("signup_rate", 0.03))
        target_su = curr_su + rec_abs
        act_rate = float(answers.get("activation_rate", 0.20))
        ior = float(answers.get("ior", 0.18))
        extra_su = visitors * (target_su - curr_su)
        extra_inq = extra_su * act_rate
        incremental = extra_inq * ior
        funnel_chain = [
            ("Visitors", f"{visitors:,.0f}/mo", "", ""),
            (
                "Sign-up rate",
                f"{curr_su*100:.2f}%",
                f"{target_su*100:.2f}%",
                f"+{(target_su-curr_su)*100:.3f}pp",
            ),
            ("Extra sign-ups", f"{extra_su:,.1f}/mo", "", ""),
            ("Activation", f"{act_rate*100:.1f}%", "", f"→ {extra_inq:,.1f} extra inquiries"),
            ("IOR", f"{ior*100:.2f}%", "", f"→ {incremental:,.1f} extra orders/mo"),
        ]

    elif category == "activation":
        monthly_su = float(answers.get("monthly_signups", 500))
        curr_act = float(answers.get("activation_rate", 0.20))
        target_act = curr_act + rec_abs
        ior = float(answers.get("ior", 0.18))
        extra_act = monthly_su * (target_act - curr_act)
        incremental = extra_act * ior
        funnel_chain = [
            ("Monthly sign-ups", f"{monthly_su:,.0f}/mo", "", ""),
            (
                "Activation rate",
                f"{curr_act*100:.2f}%",
                f"{target_act*100:.2f}%",
                f"+{(target_act-curr_act)*100:.3f}pp",
            ),
            ("Extra activated", f"{extra_act:,.1f}/mo", "", ""),
            ("IOR", f"{ior*100:.2f}%", "", f"→ {incremental:,.1f} extra orders/mo"),
        ]

    elif category in ("conversion", "pricing"):
        monthly_inq = float(answers.get("monthly_inquiries", 10000))
        curr_ior = float(answers.get("ior", 0.18))
        target_ior = curr_ior + rec_abs
        aov_mult = 1 + float(answers.get("aov_delta_pct", 0))
        eff_aov = aov * aov_mult
        extra_orders = monthly_inq * (target_ior - curr_ior)
        incremental = extra_orders
        funnel_chain = [
            ("Monthly inquiries", f"{monthly_inq:,.0f}/mo", "", ""),
            (
                "IOR",
                f"{curr_ior*100:.2f}%",
                f"{target_ior*100:.2f}%",
                f"+{(target_ior-curr_ior)*100:.3f}pp",
            ),
            ("Extra orders/mo", f"{extra_orders:,.1f}", "", ""),
        ]
        if category == "pricing" and abs(aov_mult - 1) > 0.001:
            aov_gmv = monthly_inq * curr_ior * (eff_aov - aov)
            funnel_chain.append(
                ("AOV uplift", f"${aov:,.0f}", f"${eff_aov:,.0f}", f"+${aov_gmv:,.0f} GMV/mo")
            )
            aov = eff_aov

    elif category == "retention":
        monthly_ord = float(answers.get("monthly_orders", 2700))
        curr_rep = float(answers.get("repeat_rate", 0.40))
        target_rep = curr_rep + rec_abs
        incremental = monthly_ord * (target_rep - curr_rep)
        funnel_chain = [
            ("Monthly orders", f"{monthly_ord:,.0f}/mo", "", ""),
            (
                "Repeat rate",
                f"{curr_rep*100:.2f}%",
                f"{target_rep*100:.2f}%",
                f"+{(target_rep-curr_rep)*100:.3f}pp",
            ),
            ("Extra repeat/mo", f"{incremental:,.1f}", "", ""),
        ]

    elif category == "engagement":
        monthly_u = float(answers.get("monthly_users", 6000))
        curr_ctr = float(answers.get("current_ctr", 0.025))
        target_ctr = curr_ctr + rec_abs
        c2o = float(answers.get("ctr_to_ior_rate", 0.18))
        extra_eng = monthly_u * (target_ctr - curr_ctr)
        incremental = extra_eng * c2o
        funnel_chain = [
            ("Monthly users", f"{monthly_u:,.0f}/mo", "", ""),
            (
                "Engagement rate",
                f"{curr_ctr*100:.2f}%",
                f"{target_ctr*100:.2f}%",
                f"+{(target_ctr-curr_ctr)*100:.3f}pp",
            ),
            ("Extra engaged", f"{extra_eng:,.1f}/mo", "", ""),
            ("Engage→Order", f"{c2o*100:.1f}%", "", f"→ {incremental:,.1f} extra orders/mo"),
        ]

    monthly_gmv = incremental * aov
    monthly_gm = monthly_gmv * gm

    return {
        "category": category,
        "label": FUNNEL_TAXONOMY[category]["label"],
        "funnel_chain": funnel_chain,
        "mde_info": mde_info,
        "incremental_orders_mo": round(incremental, 1),
        "incremental_gmv_mo": round(monthly_gmv, 0),
        "incremental_gm_mo": round(monthly_gm, 0),
        "cumulative_gmv": [round(monthly_gmv * m, 0) for m in range(1, horizon + 1)],
        "cumulative_gm": [round(monthly_gm * m, 0) for m in range(1, horizon + 1)],
        "time_horizon_months": horizon,
        "aov": round(aov, 0),
        "gross_margin": gm,
        "12m_gmv": round(monthly_gmv * horizon, 0),
        "12m_gm": round(monthly_gm * horizon, 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINT INFERENCE
# ─────────────────────────────────────────────────────────────────────────────

EXPERIMENT_TYPE_CATALOGUE: Dict[str, Dict] = {
    "ab_test": {
        "label": "A/B Test (Randomised Controlled Trial)",
        "causal_strength": "High — randomisation eliminates confounding",
        "when_to_use": "Can randomise users; enough traffic; clear binary assignment.",
        "keywords": [
            "ui",
            "feature",
            "checkout",
            "button",
            "flow",
            "onboarding",
            "pricing",
            "copy",
        ],
    },
    "pre_post": {
        "label": "Pre-Post Analysis",
        "causal_strength": "Low — confounded by seasonality and concurrent changes",
        "when_to_use": "100% rollout; no control group possible.",
        "keywords": ["before", "after", "shipped", "100%", "rollout", "pre", "post"],
    },
    "did": {
        "label": "Difference-in-Differences",
        "causal_strength": "High if parallel-trends assumption holds",
        "when_to_use": "Partial rollout with a natural control group.",
        "keywords": ["rollout", "partial", "region", "tier", "segment", "launched"],
    },
    "its": {
        "label": "Interrupted Time Series",
        "causal_strength": "Medium — controls for trend and seasonality",
        "when_to_use": "100% rollout; long pre-period available; no control group.",
        "keywords": ["time", "series", "trend", "seasonality", "daily", "weekly"],
    },
    "synthetic_control": {
        "label": "Synthetic Control",
        "causal_strength": "High with good donor fit",
        "when_to_use": "One treated unit; multiple similar donor units.",
        "keywords": ["region", "market", "city", "one", "single"],
    },
    "psm": {
        "label": "Propensity Score Matching",
        "causal_strength": "Medium — observable confounders only",
        "when_to_use": "Observational data; users self-selected.",
        "keywords": ["observational", "self-select", "adopted", "opted in"],
    },
    "rdd": {
        "label": "Regression Discontinuity",
        "causal_strength": "High locally — near-random at the threshold",
        "when_to_use": "Treatment assigned by a threshold (score ≥ cutoff).",
        "keywords": ["score", "threshold", "cutoff", "tier", "qualification", "eligibility"],
    },
    "mediation": {
        "label": "Causal Mediation Analysis",
        "causal_strength": "High — if mediator correctly specified",
        "when_to_use": "Want to understand HOW the feature causes the outcome.",
        "keywords": ["mechanism", "why", "through", "mediator", "pathway"],
    },
}


def recommend_experiment_type(
    description: str,
    constraints: Dict,
    llm: Any = None,
) -> List[Dict]:
    scores = {k: 0 for k in EXPERIMENT_TYPE_CATALOGUE}
    reasons = {k: [] for k in EXPERIMENT_TYPE_CATALOGUE}
    desc_l = description.lower()

    can_rand = constraints.get("can_randomise", True)
    rollout = constraints.get("rollout_pct", 50)
    has_ctrl = constraints.get("has_control_group", False)
    has_ts = constraints.get("has_time_series", True)
    pre_days = constraints.get("pre_period_days", 180)
    obs = constraints.get("observational", False)
    thresh = constraints.get("has_threshold", False)

    if can_rand and rollout <= 70:
        scores["ab_test"] += 5
        reasons["ab_test"].append("Randomisation possible")
    else:
        scores["ab_test"] -= 3

    if rollout == 100 and not can_rand:
        scores["pre_post"] += 3
        if has_ts and pre_days >= 90:
            scores["its"] += 4
            reasons["its"].append("Rich time series available")

    if has_ctrl and not can_rand:
        scores["did"] += 4
        reasons["did"].append("Control group available")

    if obs:
        scores["psm"] += 4
        reasons["psm"].append("Observational data")

    if thresh:
        scores["rdd"] += 5
        reasons["rdd"].append("Assignment threshold detected")

    if has_ts and pre_days >= 180:
        scores["synthetic_control"] += 2

    for method, meta in EXPERIMENT_TYPE_CATALOGUE.items():
        kw_hits = sum(1 for kw in meta["keywords"] if kw in desc_l)
        scores[method] += kw_hits

    top_3 = sorted(scores, key=lambda k: scores[k], reverse=True)[:3]

    if llm is not None:
        try:
            import json

            ctx = "\n".join(f"  {k}: score={scores[k]}" for k in top_3)
            prompt = (
                f'Feature: "{description}"\nConstraints: {constraints}\n\n'
                f"Top candidates by rule scoring:\n{ctx}\n\n"
                "Return JSON array of top-3 method keys with 1-sentence reason each:\n"
                '[{"method":"ab_test","reason":"..."},...]'
            )
            resp = str(llm.ask(prompt))
            m = re.search(r"\[.*\]", resp, re.DOTALL)
            if m:
                ranked = json.loads(m.group())
                return ranked[:3]
        except Exception as e:
            logger.debug("recommend_experiment_type LLM failed: %s", e)

    return [
        {
            "method": k,
            "reason": "; ".join(reasons[k][:2]) or EXPERIMENT_TYPE_CATALOGUE[k]["when_to_use"],
        }
        for k in top_3
    ]


__all__ = [
    "FUNNEL_TAXONOMY",
    "EXPERIMENT_TYPE_CATALOGUE",
    "classify_feature",
    "pull_baselines",
    "recommend_mde",
    "compute_dynamic_opportunity",
    "recommend_experiment_type",
]
