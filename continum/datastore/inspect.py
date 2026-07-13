from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger("continum.datastore.inspect")


# ─────────────────────────────────────────────────────────────────────────────
# INSPECTOR REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

INSPECTORS = {}  # name → fn(session, db, bus, memory) → dict


def inspector(name: str):
    def decorator(fn):
        INSPECTORS[name] = fn
        return fn

    return decorator


def inspect(what: str, session=None, db=None, bus=None, memory=None) -> Dict:
    fn = INSPECTORS.get(what)
    if fn is None:
        return {"error": f"Unknown inspector: {what!r}. Available: {list(INSPECTORS)}"}
    try:
        return fn(session=session, db=db, bus=bus, memory=memory)
    except Exception as e:
        logger.warning("Inspector %s failed: %s", what, e)
        return {"error": str(e), "inspector": what}


def inspect_all(session=None, db=None, bus=None, memory=None) -> Dict[str, Dict]:
    return {
        name: inspect(name, session=session, db=db, bus=bus, memory=memory) for name in INSPECTORS
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. SESSION INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────


@inspector("session")
def inspect_session(session=None, db=None, bus=None, memory=None) -> Dict:
    if session is None:
        return {"status": "no session"}

    history = [
        {
            "run_id": r.run_id,
            "module": r.module,
            "phase": r.phase,
            "ok": r.ok,
            "elapsed_s": round(r.elapsed_s, 3),
            "summary": r.summary[:120] if r.summary else "",
            "started_at": r.started_at[:19] if r.started_at else "",
            "error": r.error[:100] if r.error else "",
        }
        for r in session.execution_history
    ]

    # Context keys with type hints (not values — could be large DataFrames)
    ctx_types = {}
    for k, v in session._context.items():
        t = type(v).__name__
        if hasattr(v, "__len__"):
            try:
                t += f"[{len(v)}]"
            except Exception:
                pass
        ctx_types[k] = t

    # Fork info
    fork_info = {}
    if hasattr(session, "_parent_id"):
        fork_info["parent_id"] = session._parent_id
        fork_info["description"] = getattr(session, "fork_description", "")

    recs = [
        {"action": r.action, "reason": r.reason, "priority": r.priority, "source": r.source}
        for r in session.recommendations
    ]

    return {
        "session_id": session.session_id,
        "client_name": session.client_name,
        "mode": session.mode,
        "created_at": session.created_at[:19],
        "last_active": session.last_active[:19],
        "active_experiment": session.active_experiment,
        "active_metrics": session.active_metrics,
        "n_runs": len(session.execution_history),
        "n_recommendations": len(session.recommendations),
        "context_keys": ctx_types,
        "history": history,
        "recommendations": recs,
        "fork_info": fork_info,
        "semantic_mappings": session.semantic_mappings,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. SEMANTIC CONTEXT INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────


@inspector("semantic")
def inspect_semantic(session=None, db=None, bus=None, memory=None) -> Dict:
    metrics = {}
    try:
        from continum.datastore.semantic_layer import METRIC_REGISTRY

        for name, m in METRIC_REGISTRY.items():
            metrics[name] = {
                "display_name": m.display_name,
                "type": m.metric_type.value,
                "direction": m.direction.value,
                "unit": m.unit,
                "owner": m.owner,
                "guardrail_min": m.guardrail_min,
                "dimensions": m.dependent_dimensions,
            }
    except Exception as e:
        metrics = {"error": str(e)}

    dimensions = {}
    try:
        from continum.datastore.semantic_layer import DIMENSION_CATALOG

        for name, d in DIMENSION_CATALOG.items():
            dimensions[name] = {
                "display_name": d.display_name,
                "type": d.dimension_type.value,
                "allowed_values": d.allowed_values,
                "n_aliases": len(d.value_aliases) if d.value_aliases else 0,
                "owner": d.owner,
            }
    except Exception as e:
        dimensions = {"error": str(e)}

    # Session column mappings (if schema discovery was run)
    col_mappings = {}
    if session:
        col_mappings = session.semantic_mappings or {}
        if not col_mappings:
            # Try to pull from session context
            mapping = session.get("schema_discovery_result")
            if mapping and isinstance(mapping, dict):
                col_mappings = mapping.get("column_mapping", {})

    # DB tables (if connected)
    tables = []
    if db is not None:
        try:
            rows = db.execute("SHOW TABLES").fetchall()
            tables = [r[0] for r in rows]
        except Exception:
            pass

    return {
        "metrics": metrics,
        "dimensions": dimensions,
        "column_mappings": col_mappings,
        "db_tables": tables,
        "n_metrics": len(metrics),
        "n_dimensions": len(dimensions),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. DERIVED METRICS INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────


@inspector("metrics")
def inspect_metrics(session=None, db=None, bus=None, memory=None) -> Dict:
    computed = []

    # Pull from session context
    if session:
        result = session.get("experiment_result") or session.get("experiment_analysis_result")
        if result:
            r = getattr(result, "result", None) or result
            primary = getattr(r, "primary_delta", None)
            if primary:
                computed.append(
                    {
                        "metric": getattr(primary, "metric_display_name", "—"),
                        "type": "primary",
                        "delta_pp": float(getattr(primary, "delta_pp", 0) or 0),
                        "p_value": float(getattr(primary, "p_value", 1) or 1),
                        "is_sig": bool(getattr(primary, "is_significant", False)),
                        "n_control": int(getattr(primary, "n_control", 0) or 0),
                        "n_treatment": int(getattr(primary, "n_treatment", 0) or 0),
                        "rate_control": float(getattr(primary, "rate_control", 0) or 0),
                        "rate_treat": float(getattr(primary, "rate_treatment", 0) or 0),
                    }
                )
            for s in getattr(r, "secondary_deltas", None) or []:
                computed.append(
                    {
                        "metric": getattr(s, "metric_display_name", "—"),
                        "type": "secondary",
                        "delta_pp": float(getattr(s, "delta_pp", 0) or 0),
                        "p_value": float(getattr(s, "p_value", 1) or 1),
                        "is_sig": bool(getattr(s, "is_significant", False)),
                    }
                )

    # Baselines from DB
    baselines = {}
    if db is not None:
        try:
            row = db.execute("""
                SELECT
                  COUNT(*) AS n_total,
                  COUNT(CASE WHEN converted_to_order = '1' OR converted_to_order = 1 THEN 1 END) * 1.0
                    / NULLIF(COUNT(*), 0) AS ior_baseline
                FROM gold_experiment_analysis
            """).fetchone()
            if row:
                baselines["n_total"] = int(row[0] or 0)
                baselines["ior_baseline"] = round(float(row[1] or 0), 4)
        except Exception:
            pass

    # KPI suggestions from bus
    kpi_suggestions = []
    if bus:
        for ins in bus.kpi_suggestions():
            kpi_suggestions.append(
                {
                    "message": ins.message,
                    "metric": ins.metric,
                    "source": ins.source_module,
                }
            )

    return {
        "computed_metrics": computed,
        "baselines": baselines,
        "kpi_suggestions": kpi_suggestions,
        "active_metrics": session.active_metrics if session else [],
        "n_computed": len(computed),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. ACTIVE ASSUMPTIONS INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────


@inspector("assumptions")
def inspect_assumptions(session=None, db=None, bus=None, memory=None) -> Dict:
    # Pull from session context
    power_result = session.get("power_calculator_result") if session else None
    experiment_config = (session.experiment_configs or {}) if session else {}

    assumptions = {
        "statistical": {
            "alpha": 0.05,
            "power": 0.80,
            "mde_rel": None,
            "mde_abs": None,
            "n_required": None,
            "days_required": None,
            "test_type": "two-sided z-test (proportions)",
        },
        "design": {
            "control_variant": "control",
            "randomisation": "user-level",
            "min_detectable": "2% relative lift (default)",
            "srm_threshold": 0.01,
            "max_experiment_days": 90,
        },
        "guardrails": {
            "ior_floor": 0.10,
            "srm_alpha": 0.01,
            "max_regression": -0.005,
        },
        "cuped": {
            "enabled": True,
            "covariate": "pre_experiment_ior",
            "variance_reduction_expected": "15–40%",
        },
    }

    # Overlay from power analysis result if available
    if power_result:
        try:
            pr = power_result
            if isinstance(pr, dict):
                pr = pr.get("result") or pr
            if hasattr(pr, "alpha"):
                assumptions["statistical"]["alpha"] = float(pr.alpha)
                assumptions["statistical"]["power"] = float(pr.power)
                assumptions["statistical"]["n_required"] = int(pr.n_total)
                assumptions["statistical"]["days_required"] = int(pr.days_required)
                assumptions["statistical"]["mde_rel"] = float(pr.mde_rel)
                assumptions["statistical"]["mde_abs"] = float(pr.mde_abs)
        except Exception:
            pass

    # Overlay from experiment config
    if experiment_config:
        exp = session.active_experiment if session else None
        cfg = experiment_config.get(exp, {}) if exp else {}
        if cfg.get("alpha"):
            assumptions["statistical"]["alpha"] = cfg["alpha"]
        if cfg.get("control_variant"):
            assumptions["design"]["control_variant"] = cfg["control_variant"]

    return assumptions


# ─────────────────────────────────────────────────────────────────────────────
# 5. COHORT / VARIANT INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────


@inspector("cohorts")
def inspect_cohorts(session=None, db=None, bus=None, memory=None) -> Dict:
    if db is None:
        return {"status": "no database connected"}

    exp = session.active_experiment if session else None
    if not exp:
        return {"status": "no active experiment — select one first"}

    cohorts = []
    srm_flag = False
    srm_p = None
    total = 0

    try:
        rows = db.execute(
            """
            SELECT variant,
                   COUNT(DISTINCT user_id) AS n_users,
                   COUNT(*) AS n_rows,
                   MIN(created_at)::DATE AS first_seen,
                   MAX(created_at)::DATE AS last_seen
            FROM gold_experiment_analysis
            WHERE experiment_name = ?
              AND variant IS NOT NULL
            GROUP BY variant
            ORDER BY n_users DESC
        """,
            [exp],
        ).fetchall()

        total = sum(r[1] for r in rows)
        for r in rows:
            pct = round(100.0 * r[1] / total, 2) if total > 0 else 0
            cohorts.append(
                {
                    "variant": r[0],
                    "n_users": int(r[1]),
                    "n_rows": int(r[2]),
                    "pct": pct,
                    "first_seen": str(r[3]),
                    "last_seen": str(r[4]),
                    "balanced": abs(pct - (100.0 / len(rows))) < 3.0,
                }
            )
    except Exception as e:
        return {"status": f"DB query failed: {e}"}

    # SRM check
    try:
        from continum.experimentation.stats.srm_detector import detect_srm

        if len(cohorts) >= 2:
            variant_names = [c["variant"] for c in cohorts]  # noqa: F841
            observed_counts = [c["n_users"] for c in cohorts]
            srm_result = detect_srm(observed_counts)
            srm_flag = bool(srm_result.get("srm_detected", False))
            srm_p = float(srm_result.get("p_value", 1.0))
    except Exception:
        pass

    # Daily distribution (last 14 days)
    daily = []
    try:
        rows = db.execute(
            """
            SELECT created_at::DATE AS day,
                   variant,
                   COUNT(DISTINCT user_id) AS n
            FROM gold_experiment_analysis
            WHERE experiment_name = ?
            GROUP BY day, variant
            ORDER BY day DESC
            LIMIT 60
        """,
            [exp],
        ).fetchall()
        daily = [{"day": str(r[0]), "variant": r[1], "n": int(r[2])} for r in rows]
    except Exception:
        pass

    # Segment breakdown for the largest two segments
    segments = []
    try:
        rows = db.execute(
            """
            SELECT account_segment, variant, COUNT(DISTINCT user_id) AS n
            FROM gold_experiment_analysis
            WHERE experiment_name = ? AND account_segment IS NOT NULL
            GROUP BY account_segment, variant
            ORDER BY n DESC
            LIMIT 20
        """,
            [exp],
        ).fetchall()
        segments = [{"segment": r[0], "variant": r[1], "n": int(r[2])} for r in rows]
    except Exception:
        pass

    return {
        "experiment": exp,
        "total_users": total,
        "cohorts": cohorts,
        "srm_detected": srm_flag,
        "srm_p_value": srm_p,
        "daily_assignments": daily[:30],
        "segment_breakdown": segments,
        "n_variants": len(cohorts),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. LINEAGE INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────


@inspector("lineage")
def inspect_lineage(session=None, db=None, bus=None, memory=None) -> Dict:
    session_runs = []
    if session:
        session_runs = [
            {
                "run_id": r.run_id,
                "module": r.module,
                "phase": r.phase,
                "ok": r.ok,
                "elapsed_s": round(r.elapsed_s, 3),
                "summary": r.summary[:100] if r.summary else "",
                "started_at": r.started_at[:19] if r.started_at else "",
            }
            for r in session.execution_history
        ]

    # Persistent registry (from orchestration engine)
    registry_runs = []
    try:
        from continum.datastore.lineage import ExecutionRegistry

        reg = ExecutionRegistry()
        records = reg.read_all()
        for r in records[-20:]:
            pm = r.get("primary_metric") or {}
            registry_runs.append(
                {
                    "run_id": r.get("run_id", "")[:8],
                    "experiment": r.get("experiment_name", ""),
                    "status": r.get("status", ""),
                    "started_at": r.get("started_at", "")[:19],
                    "elapsed_s": round(r.get("elapsed_s", 0), 2),
                    "n_tasks_ok": r.get("n_tasks_ok", 0),
                    "n_tasks_failed": r.get("n_tasks_failed", 0),
                    "verdict": r.get("verdict", ""),
                    "delta_pp": pm.get("delta_pp", None),
                    "p_value": pm.get("p_value", None),
                }
            )
    except Exception:
        pass

    return {
        "session_runs": session_runs,
        "registry_runs": registry_runs,
        "total_session": len(session_runs),
        "total_registry": len(registry_runs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI DISPLAY
# ─────────────────────────────────────────────────────────────────────────────


def print_inspection(what: str, report: Dict, width: int = 72) -> None:

    def _row(label, value, indent=2):
        label_s = str(label)
        value_s = str(value)
        if len(label_s) + len(value_s) > width - indent - 4:
            value_s = value_s[: width - indent - len(label_s) - 7] + "…"
        print(f"  {'  ' * indent}{label_s:<28}  {value_s}")

    def _section(title):
        print(f"\n  {'─' * 64}\n  {title.upper()}\n  {'─' * 64}")

    if "error" in report:
        print(f"\n  ❌ {report['error']}")
        return

    print(f"\n  {'═' * width}")
    print(f"  INSPECTION: {what.upper()}")
    print(f"  {'═' * width}")

    if what == "session":
        _row("Session ID", report.get("session_id", "—"))
        _row("Client", report.get("client_name", "—"))
        _row("Mode", report.get("mode", "—"))
        _row("Experiment", report.get("active_experiment") or "—")
        _row("Metrics", ", ".join(report.get("active_metrics", [])) or "—")
        _row("Runs", report.get("n_runs", 0))
        _row("Recs", report.get("n_recommendations", 0))
        _section("Context Keys")
        for k, t in (report.get("context_keys") or {}).items():
            _row(k, t)
        _section("Execution History")
        for r in report.get("history", [])[-8:]:
            icon = "✅" if r["ok"] else "❌"
            print(f"    {icon}  {r['module']:<28}  {r['elapsed_s']:.2f}s  {r['summary'][:40]}")

    elif what == "semantic":
        _row("Known Metrics", report.get("n_metrics", 0))
        _row("Known Dimensions", report.get("n_dimensions", 0))
        _row("DB Tables", len(report.get("db_tables", [])))
        _section("Metric Registry")
        for name, m in list((report.get("metrics") or {}).items())[:8]:
            print(f"    {name:<32}  {m.get('display_name', '')[:35]}")
        _section("Dimension Catalog")
        for name, d in (report.get("dimensions") or {}).items():
            vals = len(d.get("allowed_values") or [])
            print(f"    {name:<24}  {d.get('type',''):<14}  {vals} values")

    elif what == "metrics":
        _row("Computed Metrics", report.get("n_computed", 0))
        for m in report.get("computed_metrics", []):
            sig = "✅" if m.get("is_sig") else "—"
            print(
                f"    {sig}  {m['metric']:<36}  Δ={m.get('delta_pp',0):+.4f}pp  p={m.get('p_value',1):.4f}"
            )
        if report.get("baselines"):
            _section("Baselines")
            for k, v in report["baselines"].items():
                _row(k, v)

    elif what == "assumptions":
        _section("Statistical")
        for k, v in (report.get("statistical") or {}).items():
            _row(k, v if v is not None else "—")
        _section("Design")
        for k, v in (report.get("design") or {}).items():
            _row(k, v)
        _section("Guardrails")
        for k, v in (report.get("guardrails") or {}).items():
            _row(k, v)

    elif what == "cohorts":
        _row("Experiment", report.get("experiment", "—"))
        _row("Total Users", f"{report.get('total_users', 0):,}")
        _row("Variants", report.get("n_variants", 0))
        srm = report.get("srm_detected", False)
        srm_p = report.get("srm_p_value")
        _row("SRM", f"⚠️  DETECTED (p={srm_p:.4f})" if srm else "✅ Clean")
        _section("Variant Breakdown")
        for c in report.get("cohorts", []):
            bal = "✅" if c.get("balanced") else "⚠️ "
            print(f"    {bal}  {c['variant']:<24}  {c['n_users']:>8,} users  {c['pct']:.1f}%")

    elif what == "lineage":
        _row("Session runs", report.get("total_session", 0))
        _row("Registry runs", report.get("total_registry", 0))
        _section("Session History")
        for r in report.get("session_runs", [])[-10:]:
            icon = "✅" if r["ok"] else "❌"
            print(f"    {icon}  {r['module']:<28}  {r['elapsed_s']:.2f}s")
        _section("Registry (persistent)")
        for r in report.get("registry_runs", [])[-8:]:
            dp = f"Δ={r['delta_pp']:+.3f}pp" if r.get("delta_pp") is not None else ""
            print(f"    {r['run_id']}  {r['experiment']:<30}  {r['status']}  {dp}")

    print(f"\n  {'═' * width}\n")


__all__ = [
    "inspect",
    "inspect_all",
    "print_inspection",
    "INSPECTORS",
    "inspector",
]
