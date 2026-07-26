from __future__ import annotations

import logging
from typing import Dict, List

import pandas as pd

logger = logging.getLogger("continum.intelligence.synthesis")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _bus():
    try:
        from continum.ContextGraph.insight_bus import get_bus

        return get_bus()
    except Exception:
        return None


def _publish(source: str, insight_type: str, severity: str, message: str, detail: str = "", **kw):
    bus = _bus()
    if bus is None:
        return
    try:
        from continum.ContextGraph.insight_bus import InsightSeverity, InsightType

        bus.emit(
            source=source,
            insight_type=InsightType(insight_type),
            severity=InsightSeverity(severity),
            message=message,
            detail=detail,
            **kw,
        )
    except Exception as e:
        logger.debug("publish failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# 1. KPI SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────


def run_kpi_synthesis(
    db=None,
    llm=None,
    experiment_type: str = "conversion",
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  KPI SYNTHESIS")
    print("=" * 72)

    from continum.ExpSuite.planning.metric_planner import METRICS_KB, gen_metrics_bundle

    # Pull live baselines
    baselines: Dict[str, float] = {}
    if db is not None:
        try:
            row = db.execute("""
                SELECT
                    AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                    AVG(CASE WHEN converted_to_order THEN order_value END) AS aov,
                    COUNT(*) / 90.0 AS daily_inq
                FROM silver_inquiries
            """).fetchone()
            if row and row[0] is not None:
                baselines = {
                    "ior": float(row[0] or 0.18),
                    "aov": float(row[1] or 4000),
                    "daily_inquiries": float(row[2] or 500),
                }
        except Exception as e:
            logger.debug("KPI baselines query failed: %s", e)

    kb = METRICS_KB.get(experiment_type, METRICS_KB.get("conversion", {}))  # noqa: F841

    plan = gen_metrics_bundle(
        desc=kwargs.get("description", ""),
        category=experiment_type,
        maturity=kwargs.get("maturity", "mvp"),
        llm=llm,
    )

    # Augment with baselines
    plan["baselines"] = baselines
    plan["experiment_type"] = experiment_type

    # Publish to bus
    _publish(
        source="kpi_synthesis",
        insight_type="kpi_suggestion",
        severity="info",
        message=f"Primary KPI: {plan.get('primary_metric', 'IOR')}",
        detail=f"{len(plan.get('secondary_metrics', []))} secondary, "
        f"{len(plan.get('guardrail_metrics', []))} guardrails identified",
    )

    # Print summary
    print(f"\n  Experiment type  : {experiment_type}")
    print(f"  Primary KPI      : {plan.get('primary_metric', 'IOR')}")
    print("\n  Secondary metrics:")
    for m in plan.get("secondary_metrics", [])[:4]:
        print(f"    • {m}")
    print("\n  Guardrail metrics:")
    for g in plan.get("guardrail_metrics", [])[:4]:
        print(f"    🛡  {g}")
    if baselines:
        print("\n  Live baselines:")
        for k, v in baselines.items():
            print(f"    {k}: {v:.4f}" if isinstance(v, float) else f"    {k}: {v}")

    return plan


# ─────────────────────────────────────────────────────────────────────────────
# 2. GUARDRAIL GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def run_guardrail_generation(
    db=None,
    llm=None,
    experiment_name: str = "",
    sensitivity: float = 2.0,  # z-score threshold (2.0 = 95th percentile)
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  GUARDRAIL GENERATION")
    print("=" * 72)

    guardrails: List[Dict] = []

    if db is None:
        print("  ⚠️  No DB — returning default guardrails")
        guardrails = _default_guardrails(sensitivity)
    else:
        # Pull metric distributions from silver layer
        metric_queries = {
            "ior": "SELECT AVG(CAST(converted_to_order AS DOUBLE)), STDDEV(CAST(converted_to_order AS DOUBLE)) FROM silver_inquiries",
            "aov": "SELECT AVG(order_value), STDDEV(order_value) FROM silver_inquiries WHERE order_value > 0",
            "daily_vol": "SELECT AVG(daily_count), STDDEV(daily_count) FROM (SELECT DATE_TRUNC('day', created_at) AS d, COUNT(*) AS daily_count FROM silver_inquiries GROUP BY d)",
        }

        for metric, q in metric_queries.items():
            try:
                row = db.execute(q).fetchone()
                if row and row[0] is not None:
                    mean_val = float(row[0])
                    std_val = float(row[1] or mean_val * 0.1)
                    guardrails.append(
                        {
                            "metric": metric,
                            "baseline_mean": round(mean_val, 6),
                            "baseline_std": round(std_val, 6),
                            "threshold_lo": round(mean_val - sensitivity * std_val, 6),
                            "threshold_hi": round(mean_val + sensitivity * std_val, 6),
                            "sensitivity_z": sensitivity,
                            "auto_detected": True,
                        }
                    )
            except Exception as e:
                logger.debug("Guardrail query for %s failed: %s", metric, e)

        if not guardrails:
            guardrails = _default_guardrails(sensitivity)

    # LLM narrative
    if llm is not None and guardrails:
        try:
            ctx = "\n".join(
                f"  {g['metric']}: mean={g['baseline_mean']:.4f} ±{g['baseline_std']:.4f}"
                for g in guardrails
            )
            narrative = llm.ask(
                f"You are an experimentation analyst. Given these guardrail baselines:\n{ctx}\n"
                f"Write a 2-3 sentence explanation of what these guardrails protect against "
                f"and when to pause an experiment. Be concise and specific."
            )
            print(f"\n  💡 {narrative}")
        except Exception:
            pass

    # Publish guardrails to bus
    for g in guardrails:
        _publish(
            source="guardrail_generation",
            insight_type="guardrail",
            severity="info",
            message=f"Guardrail: {g['metric']} [{g['threshold_lo']:.4f}, {g['threshold_hi']:.4f}]",
            metric=g["metric"],
        )

    print(f"\n  {len(guardrails)} guardrail(s) generated\n")
    for g in guardrails:
        print(
            f"  🛡  {g['metric']:<18}  "
            f"baseline={g['baseline_mean']:.4f}  "
            f"lo={g['threshold_lo']:.4f}  hi={g['threshold_hi']:.4f}"
        )

    return {"guardrails": guardrails, "sensitivity_z": sensitivity, "experiment": experiment_name}


def _default_guardrails(sensitivity: float = 2.0) -> List[Dict]:
    return [
        {
            "metric": "ior",
            "baseline_mean": 0.18,
            "baseline_std": 0.02,
            "threshold_lo": 0.18 - sensitivity * 0.02,
            "threshold_hi": 0.18 + sensitivity * 0.02,
            "sensitivity_z": sensitivity,
            "auto_detected": False,
        },
        {
            "metric": "aov",
            "baseline_mean": 4000,
            "baseline_std": 800,
            "threshold_lo": 4000 - sensitivity * 800,
            "threshold_hi": 4000 + sensitivity * 800,
            "sensitivity_z": sensitivity,
            "auto_detected": False,
        },
        {
            "metric": "daily_vol",
            "baseline_mean": 500,
            "baseline_std": 80,
            "threshold_lo": 500 - sensitivity * 80,
            "threshold_hi": 500 + sensitivity * 80,
            "sensitivity_z": sensitivity,
            "auto_detected": False,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRACKING PLAN
# ─────────────────────────────────────────────────────────────────────────────


def run_tracking_plan(
    db=None,
    llm=None,
    description: str = "",
    experiment_type: str = "conversion",
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  TRACKING PLAN GENERATOR")
    print("=" * 72)

    from continum.ExpSuite.planning.metric_planner import METRICS_KB

    kb = METRICS_KB.get(experiment_type, METRICS_KB.get("conversion", {}))
    events = kb.get("tracking_event_types", [])

    # Build the plan
    plan_events = []
    for evt in events:
        plan_events.append(
            {
                "event_name": evt,
                "trigger": f"When user performs action: {evt.replace('_', ' ')}",
                "properties": _default_event_properties(evt),
                "validation": f"SELECT COUNT(*), COUNT(DISTINCT user_id) FROM events WHERE event_name = '{evt}'",
                "expected_volume": "~daily_traffic × conversion_rate",
            }
        )

    # LLM enhancement
    if llm is not None and description:
        try:
            prompt = (
                f"Feature: {description}\nExperiment type: {experiment_type}\n"
                f"Existing events: {', '.join(events[:6])}\n\n"
                "Suggest 2-3 additional specific tracking events for this feature. "
                "Return as a JSON list of objects with event_name, trigger, properties keys."
            )
            resp = llm.ask(prompt)
            import json
            import re

            m = re.search(r"\[.*\]", str(resp), re.DOTALL)
            if m:
                extra = json.loads(m.group())
                plan_events.extend(extra[:3])
        except Exception:
            pass

    _publish(
        source="tracking_plan",
        insight_type="recommendation",
        severity="info",
        message=f"Tracking plan: {len(plan_events)} events for {experiment_type}",
        detail=f"Events: {', '.join(e['event_name'] for e in plan_events[:4])}…",
    )

    print(f"\n  Experiment type  : {experiment_type}")
    print(f"  Events in plan   : {len(plan_events)}\n")
    for e in plan_events:
        print(f"  📍 {e['event_name']}")
        print(f"     Trigger   : {e['trigger']}")
        print(f"     Properties: {', '.join(str(p) for p in e.get('properties', [])[:4])}")
        print()

    return {
        "experiment_type": experiment_type,
        "description": description,
        "events": plan_events,
        "validation_suite": [e["validation"] for e in plan_events],
    }


def _default_event_properties(event_name: str) -> List[str]:
    common = ["user_id", "session_id", "timestamp", "variant", "experiment_name"]
    specific = {
        "checkout_initiated": ["cart_value", "item_count"],
        "checkout_completed": ["order_id", "revenue", "payment_method"],
        "payment_submitted": ["payment_type", "amount"],
        "sign_up_completed": ["sign_up_method", "referral_source"],
        "quote_viewed": ["quote_id", "quote_value", "category"],
        "quote_accepted": ["quote_id", "quote_value"],
    }
    return common + specific.get(event_name, ["page_url", "element_id"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. HISTORICAL LEARNING RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────


def run_historical_learning_retrieval(
    db=None,
    llm=None,
    query: str = "",
    experiment_name: str = "",
    top_k: int = 5,
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  HISTORICAL LEARNING RETRIEVAL")
    print("=" * 72)

    if db is None:
        return {"error": "no_db", "matches": [], "synthesis": ""}

    # Ensure table exists
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS experiment_learnings (
                id VARCHAR, experiment_name VARCHAR, ship_decision VARCHAR,
                outcome TEXT, key_learning TEXT, what_worked TEXT,
                what_didnt TEXT, recommendation TEXT, follow_ups TEXT,
                tags TEXT, recorded_at VARCHAR, recorded_by VARCHAR
            )
        """)
    except Exception:
        pass

    # Pull all learnings
    try:
        df = db.execute("SELECT * FROM experiment_learnings ORDER BY recorded_at DESC").df()
    except Exception as e:
        return {"error": str(e), "matches": [], "synthesis": ""}

    if len(df) == 0:
        print("  No learnings recorded yet. Run the learnings_repository module to add some.")
        return {"matches": [], "synthesis": "No prior learnings found.", "total": 0}

    # Build effective query
    search_q = query or experiment_name or "conversion experiment lift"
    search_q = search_q.lower()

    # Simple keyword + score ranking (LLM semantic if available)
    df["_score"] = df.apply(
        lambda r: sum(
            w
            for token in search_q.split()
            for w, col in [(3, "experiment_name"), (2, "key_learning"), (1, "outcome"), (1, "tags")]
            if token in str(r.get(col, "")).lower()
        ),
        axis=1,
    )
    df_sorted = df.sort_values("_score", ascending=False)
    top_rows = df_sorted.head(top_k)

    matches = top_rows.to_dict("records")

    # LLM synthesis
    synthesis = ""
    if llm is not None and len(matches) > 0:
        context = "\n\n".join(
            f"[{r['id']}] {r['experiment_name']}: {r.get('key_learning', '')} "
            f"(decision: {r.get('ship_decision', '?')}, tags: {r.get('tags', '')})"
            for r in matches
        )
        try:
            synthesis = str(
                llm.ask(
                    f'Query: "{search_q}"\n\nRelevant experiments:\n{context}\n\n'
                    "Synthesise the 2-3 most important actionable learnings in 3 sentences. "
                    "Be specific about what worked and what didn't."
                )
            )
        except Exception as e:
            logger.debug("LLM synthesis failed: %s", e)

    if not synthesis:
        parts = [
            f"{r.get('key_learning', r.get('outcome', '')[:80])}"
            for r in matches[:3]
            if r.get("key_learning")
        ]
        synthesis = " | ".join(parts) if parts else "No learnings match this query."

    _publish(
        source="historical_learning",
        insight_type="recommendation",
        severity="info",
        message=f"Found {len(matches)} relevant learning(s) for: '{search_q[:50]}'",
        detail=synthesis[:200],
    )

    print(f"\n  Query: '{search_q}'")
    print(f"  Found {len(matches)} / {len(df)} learning(s)\n")
    for r in matches[:5]:
        icon = {"ship": "✅", "no_ship": "❌", "partial_ship": "⚠️"}.get(
            r.get("ship_decision", ""), "⬜"
        )
        print(
            f"  {icon}  [{r.get('id','?')}] {r.get('experiment_name','')}  ({r.get('recorded_at','')[:10]})"
        )
        kl = str(r.get("key_learning", r.get("outcome", "")))[:120]
        if kl:
            print(f"     {kl}")
        print()

    if synthesis:
        print(f"  💡 Synthesis:\n     {synthesis}\n")

    return {
        "query": search_q,
        "matches": matches,
        "synthesis": synthesis,
        "total": len(df),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. NEXT-STEP GENERATION
# ─────────────────────────────────────────────────────────────────────────────

_PHASE_TRANSITIONS: Dict[str, List[Dict]] = {
    "schema_discovery": [
        {"module": "data_validation", "reason": "Validate schema is complete before analysis"}
    ],
    "data_validation": [
        {
            "module": "dimension_setup",
            "reason": "Auto-detect segments and platforms from clean data",
        }
    ],
    "dimension_setup": [
        {
            "module": "power_calculator",
            "reason": "Now that baselines are set, calculate required sample size",
        }
    ],
    "power_calculator": [
        {
            "module": "opportunity_sizing",
            "reason": "Size the revenue opportunity for the experiment",
        }
    ],
    "opportunity_sizing": [
        {
            "module": "brief_generator",
            "reason": "Generate experiment brief with sizing and power inputs",
        }
    ],
    "brief_generator": [
        {"module": "metrics_and_tracking", "reason": "Define KPIs and tracking plan"}
    ],
    "metrics_and_tracking": [
        {"module": "audience_selection", "reason": "Define treatment and control segments"}
    ],
    "audience_selection": [
        {
            "module": "health_monitor",
            "reason": "Monitor the live experiment for SRM and guardrail violations",
        }
    ],
    "health_monitor": [
        {"module": "sequential_testing", "reason": "Check always-valid p-values for early stopping"}
    ],
    "sequential_testing": [
        {"module": "experiment_analysis", "reason": "Run full post-experiment statistical analysis"}
    ],
    "experiment_analysis": [
        {"module": "causal_analysis", "reason": "Strengthen causal claim with DiD/PSM/ITS"},
        {"module": "simpsons_paradox", "reason": "Check for Simpson's paradox in segment effects"},
    ],
    "causal_analysis": [{"module": "roi_tracker", "reason": "Quantify post-ship incremental GMV"}],
    "roi_tracker": [
        {
            "module": "uplift_modeller",
            "reason": "Model per-user treatment effect for targeted rollout",
        }
    ],
    "simpsons_paradox": [
        {
            "module": "causal_analysis",
            "reason": "Re-run causal analysis stratified by confounding dimension",
        }
    ],
    "uplift_modeller": [
        {
            "module": "decision_engine",
            "reason": "Optimise budget-constrained targeting from uplift scores",
        }
    ],
    "learnings_repository": [
        {
            "module": "cross_experiment_learning",
            "reason": "Synthesise patterns across all recorded learnings",
        }
    ],
}


def run_next_step_generation(
    db=None,
    llm=None,
    last_module: str = "",
    session=None,
    context: Dict = None,
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  NEXT-STEP RECOMMENDATIONS")
    print("=" * 72)

    steps = []
    ctx = context or {}

    # Phase-based transitions
    if last_module and last_module in _PHASE_TRANSITIONS:
        steps.extend(_PHASE_TRANSITIONS[last_module])

    # Data-driven signals
    if db is not None:
        try:
            # Check if any running experiments are significant
            df = db.execute("""
                SELECT experiment_name, COUNT(DISTINCT variant) AS n_variants,
                       COUNT(*) AS n_obs
                FROM gold_experiment_analysis
                GROUP BY experiment_name
            """).df()
            if len(df) > 0 and not any(last_module == m for m in ["experiment_analysis"]):
                steps.append(
                    {
                        "module": "experiment_analysis",
                        "reason": f"{len(df)} experiment(s) in data — run full analysis",
                        "priority": 2,
                    }
                )
        except Exception:
            pass

    # Session-based signals
    if session is not None:
        history = getattr(session, "execution_history", [])
        run_modules = {r["module"] for r in history} if history else set()
        if "power_calculator" not in run_modules and "experiment_analysis" not in run_modules:
            steps.insert(
                0,
                {
                    "module": "power_calculator",
                    "reason": "No power calculation yet — start here for a new experiment",
                    "priority": 1,
                },
            )

    # Deduplicate
    seen = set()
    deduped = []
    for s in steps:
        if s["module"] not in seen:
            seen.add(s["module"])
            deduped.append(s)

    # LLM enhancement
    if llm is not None and last_module:
        try:
            prompt = (
                f"An experimentation analyst just ran: {last_module}\n"
                f"Context: {ctx}\n"
                f"Proposed next steps: {[s['module'] for s in deduped[:3]]}\n\n"
                "Suggest ONE additional next step not in the list above, with a 1-sentence reason. "
                "Format: module_key: reason"
            )
            resp = str(llm.ask(prompt))
            if ":" in resp:
                parts = resp.strip().split(":", 1)
                m_key = parts[0].strip().lower().replace(" ", "_")
                reason = parts[1].strip() if len(parts) > 1 else ""
                if m_key and reason and m_key not in seen:
                    deduped.append({"module": m_key, "reason": reason, "llm_suggested": True})
        except Exception:
            pass

    # Publish to bus
    for step in deduped[:3]:
        _publish(
            source="next_step_generation",
            insight_type="next_step",
            severity="info",
            message=f"Next: {step['module']}",
            detail=step.get("reason", ""),
        )

    print(f"\n  Last module: {last_module or '(none)'}\n")
    for i, s in enumerate(deduped[:5], 1):
        flag = " [LLM]" if s.get("llm_suggested") else ""
        print(f"  {i}. {s['module']}{flag}")
        print(f"     {s.get('reason', '')}\n")

    return {"last_module": last_module, "next_steps": deduped}


# ─────────────────────────────────────────────────────────────────────────────
# 6. ANOMALY SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────


def run_anomaly_synthesis(
    db=None,
    llm=None,
    experiment_name: str = "",
    z_threshold: float = 2.5,
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  ANOMALY DETECTION")
    print("=" * 72)

    anomalies: List[Dict] = []

    if db is None:
        print("  ⚠️  No DB available")
        return {"anomalies": [], "synthesis": "No DB"}

    checks = {
        "ior_anomaly": """
            SELECT
                AVG(CAST(converted_to_order AS DOUBLE))    AS mean_ior,
                STDDEV(CAST(converted_to_order AS DOUBLE)) AS std_ior,
                COUNT(*) AS n
            FROM silver_inquiries
            WHERE created_at >= CURRENT_DATE - INTERVAL 7 DAY
        """,
        "volume_anomaly": """
            SELECT
                AVG(daily_count) AS mean_vol,
                STDDEV(daily_count) AS std_vol
            FROM (
                SELECT DATE_TRUNC('day', created_at) AS d, COUNT(*) AS daily_count
                FROM silver_inquiries
                GROUP BY d
            )
        """,
        "null_variant": ("""
            SELECT
                SUM(CASE WHEN variant IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS null_pct
            FROM gold_experiment_analysis
            WHERE experiment_name = '{exp}'
        """.format(exp=experiment_name) if experiment_name else None),
    }

    for check_name, q in checks.items():
        if q is None:
            continue
        try:
            row = db.execute(q).fetchone()
            if row and row[0] is not None:
                mean_v = float(row[0])
                std_v = float(row[1] or mean_v * 0.1) if len(row) > 1 else mean_v * 0.1

                # Pull recent value for comparison
                if check_name == "ior_anomaly":
                    recent = db.execute("""
                        SELECT AVG(CAST(converted_to_order AS DOUBLE))
                        FROM silver_inquiries
                        WHERE created_at >= CURRENT_DATE - INTERVAL 1 DAY
                    """).fetchone()
                    if recent and recent[0] is not None:
                        recent_val = float(recent[0])
                        z = (recent_val - mean_v) / std_v if std_v > 0 else 0
                        if abs(z) > z_threshold:
                            direction = "spike" if z > 0 else "drop"
                            anomalies.append(
                                {
                                    "metric": "IOR (24h)",
                                    "type": direction,
                                    "z_score": round(z, 2),
                                    "value": round(recent_val, 4),
                                    "baseline": round(mean_v, 4),
                                    "severity": "critical" if abs(z) > 4 else "warning",
                                }
                            )
        except Exception as e:
            logger.debug("Anomaly check %s failed: %s", check_name, e)

    # Cross-variant imbalance check
    if experiment_name and db is not None:
        try:
            df = db.execute(f"""
                SELECT variant, COUNT(*) AS n
                FROM gold_experiment_analysis
                WHERE experiment_name = '{experiment_name}'
                GROUP BY variant
            """).df()
            if len(df) > 1:
                counts = df["n"].values
                ratio = float(counts.min() / counts.max())
                if ratio < 0.85:
                    anomalies.append(
                        {
                            "metric": "Variant balance",
                            "type": "srm_proxy",
                            "value": round(ratio, 3),
                            "baseline": 1.0,
                            "severity": "critical" if ratio < 0.70 else "warning",
                            "detail": f"Min/max variant ratio = {ratio:.2%}",
                        }
                    )
        except Exception:
            pass

    # Synthesise with LLM
    synthesis = ""
    if llm is not None and anomalies:
        ctx = "\n".join(
            f"  {a['metric']}: {a['type']} z={a.get('z_score','n/a')} value={a.get('value','?')} severity={a['severity']}"
            for a in anomalies
        )
        try:
            synthesis = str(
                llm.ask(
                    f"These anomalies were detected in the live experiment data:\n{ctx}\n\n"
                    "In 2-3 sentences, explain what these anomalies suggest and what action to take. "
                    "Be direct and specific."
                )
            )
        except Exception:
            pass

    if not synthesis and anomalies:
        parts = [f"{a['metric']} {a['type']} (z={a.get('z_score','?')})" for a in anomalies]
        synthesis = "Anomalies detected: " + "; ".join(parts)
    elif not anomalies:
        synthesis = "No anomalies detected across monitored metrics."

    # Publish each anomaly
    for a in anomalies:
        _publish(
            source="anomaly_synthesis",
            insight_type="anomaly",
            severity=a.get("severity", "warning"),
            message=f"{a['metric']}: {a['type']}  z={a.get('z_score','?')}",
            detail=a.get("detail", ""),
        )

    print(f"\n  Experiment      : {experiment_name or '(all)'}")
    print(f"  Anomalies found : {len(anomalies)}\n")
    for a in anomalies:
        icon = "🚨" if a["severity"] == "critical" else "⚠️ "
        print(f"  {icon}  {a['metric']:<22}  {a['type']:<15}  z={a.get('z_score','n/a')}")
    print(f"\n  Synthesis: {synthesis}\n")

    return {"anomalies": anomalies, "synthesis": synthesis, "experiment": experiment_name}


# ─────────────────────────────────────────────────────────────────────────────
# 7. CROSS-EXPERIMENT LEARNING
# ─────────────────────────────────────────────────────────────────────────────


def run_cross_experiment_learning(
    db=None,
    llm=None,
    min_experiments: int = 3,
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  CROSS-EXPERIMENT LEARNING")
    print("=" * 72)

    if db is None:
        return {"error": "no_db"}

    try:
        df = db.execute("""
            SELECT
                experiment_name,
                variant,
                COUNT(*) AS n,
                AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                AVG(COALESCE(order_value, 0)) AS aov
            FROM gold_experiment_analysis
            GROUP BY experiment_name, variant
        """).df()
    except Exception as e:
        return {"error": str(e)}

    if len(df) == 0 or df["experiment_name"].nunique() < min_experiments:
        n = df["experiment_name"].nunique() if len(df) else 0
        print(f"  ℹ️  {n} experiment(s) found (min {min_experiments} required for cross-learning)")
        return {"experiments": n, "patterns": [], "synthesis": "Insufficient experiments"}

    # Compute per-experiment treatment effect
    exps = df["experiment_name"].unique()
    results = []
    for exp in exps:
        sub = df[df["experiment_name"] == exp]
        ctrl = sub[sub["variant"].str.lower().isin(["control", "ctrl", "baseline"])]
        trt = sub[~sub["variant"].str.lower().isin(["control", "ctrl", "baseline"])]
        if ctrl.empty or trt.empty:
            continue
        ior_ctrl = float(ctrl["ior"].mean())
        ior_trt = float(trt["ior"].mean())
        delta = ior_trt - ior_ctrl
        n_total = int(sub["n"].sum())
        results.append(
            {
                "experiment_name": exp,
                "ior_ctrl": round(ior_ctrl, 4),
                "ior_trt": round(ior_trt, 4),
                "delta_ior": round(delta, 4),
                "direction": "positive" if delta > 0 else "negative",
                "n": n_total,
            }
        )

    if not results:
        return {"experiments": len(exps), "patterns": [], "synthesis": "No comparable experiments"}

    results_df = pd.DataFrame(results)
    win_rate = float((results_df["direction"] == "positive").mean())
    mean_delta = float(results_df["delta_ior"].mean())
    std_delta = float(results_df["delta_ior"].std())
    best_exp = results_df.loc[results_df["delta_ior"].idxmax(), "experiment_name"]
    worst_exp = results_df.loc[results_df["delta_ior"].idxmin(), "experiment_name"]

    patterns = [
        f"Win rate across {len(results)} experiments: {win_rate:.0%}",
        f"Mean effect: {mean_delta:+.4f}pp IOR  (σ = {std_delta:.4f}pp)",
        f"Best experiment: {best_exp}",
        f"Worst experiment: {worst_exp}",
    ]

    # LLM synthesis
    synthesis = ""
    if llm is not None:
        ctx = "\n".join(
            f"  {r['experiment_name']}: Δ={r['delta_ior']:+.4f}pp  ({r['direction']})"
            for r in sorted(results, key=lambda x: x["delta_ior"], reverse=True)
        )
        try:
            synthesis = str(
                llm.ask(
                    f"Portfolio of {len(results)} experiments:\n{ctx}\n\n"
                    "In 3-4 sentences, identify the most important patterns: "
                    "what consistently works, what consistently fails, and one hypothesis "
                    "for the next highest-value experiment to run."
                )
            )
        except Exception:
            pass

    if not synthesis:
        synthesis = " | ".join(patterns)

    # Publish
    _publish(
        source="cross_experiment_learning",
        insight_type="recommendation",
        severity="info",
        message=f"Portfolio win rate: {win_rate:.0%} across {len(results)} experiments",
        detail=synthesis[:200],
    )

    print(f"\n  Experiments analysed : {len(results)}")
    print(f"  Win rate             : {win_rate:.0%}")
    print(f"  Mean effect          : {mean_delta:+.4f}pp IOR\n")
    for r in sorted(results, key=lambda x: x["delta_ior"], reverse=True)[:8]:
        icon = "📈" if r["direction"] == "positive" else "📉"
        print(f"  {icon}  {r['experiment_name']:<40}  Δ={r['delta_ior']:+.4f}pp")
    if synthesis:
        print(f"\n  💡 Synthesis:\n     {synthesis}\n")

    return {
        "experiments": len(results),
        "win_rate": round(win_rate, 3),
        "mean_delta": round(mean_delta, 4),
        "std_delta": round(std_delta, 4),
        "best_experiment": best_exp,
        "worst_experiment": worst_exp,
        "patterns": patterns,
        "synthesis": synthesis,
        "results": results,
    }


__all__ = [
    "run_kpi_synthesis",
    "run_guardrail_generation",
    "run_tracking_plan",
    "run_historical_learning_retrieval",
    "run_next_step_generation",
    "run_anomaly_synthesis",
    "run_cross_experiment_learning",
]
