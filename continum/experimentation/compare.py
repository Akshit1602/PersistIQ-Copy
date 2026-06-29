from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("continum.experimentation.compare")


# ─────────────────────────────────────────────────────────────────────────────
# RESULT EXTRACTOR  (works with ExperimentResult pydantic or dict)
# ─────────────────────────────────────────────────────────────────────────────

def _safe(obj, *attrs, default=None):
    for a in attrs:
        try:
            v = getattr(obj, a, None)
            if v is not None:
                return v
        except Exception:
            pass
        if isinstance(obj, dict):
            v = obj.get(a)
            if v is not None:
                return v
    return default


def _extract_metrics(result: Any) -> Dict:
    if result is None:
        return {}
    r = _safe(result, "result") or result
    primary = _safe(r, "primary_delta")
    return {
        "metric":      _safe(primary, "metric_display_name", "metric_name", default="—"),
        "delta_pp":    float(_safe(primary, "delta_pp", default=0) or 0),
        "p_value":     float(_safe(primary, "p_value", default=1) or 1),
        "is_sig":      bool(_safe(primary, "is_significant", default=False)),
        "direction":   _safe(primary, "direction", default="—"),
        "n_control":   int(_safe(primary, "n_control", default=0) or 0),
        "n_treatment": int(_safe(primary, "n_treatment", default=0) or 0),
        "verdict":     str(_safe(r, "verdict", default="—") or "—"),
        "ship":        str(_safe(r, "ship_recommendation", default="—") or "—"),
        "srm":         bool(_safe(r, "srm_detected", default=False)),
        "slices":      _safe(r, "slice_findings", default=[]) or [],
        "guardrails":  _safe(r, "guardrail_violations", default=[]) or [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIDE-BY-SIDE RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def _render_comparison(name_a: str, m_a: Dict, name_b: str, m_b: Dict) -> None:
    W  = 76
    CW = 28  # column width per experiment

    def _sig(m): return "✅ Yes" if m.get("is_sig") else "❌ No"
    def _srm(m): return "⚠️  Detected" if m.get("srm") else "✅ Clean"
    def _ship(m):
        s = str(m.get("ship", "—")).replace("_", " ").upper()
        return s
    def _trunc(s, n=CW): return str(s)[:n]

    rows = [
        ("Metric",          _trunc(m_a.get("metric", "—")), _trunc(m_b.get("metric", "—"))),
        ("Δ (pp)",          f"{m_a.get('delta_pp', 0):+.4f}",f"{m_b.get('delta_pp', 0):+.4f}"),
        ("p-value",         f"{m_a.get('p_value', 1):.4f}",  f"{m_b.get('p_value', 1):.4f}"),
        ("Significant",     _sig(m_a),                        _sig(m_b)),
        ("Direction",       m_a.get("direction", "—"),        m_b.get("direction", "—")),
        ("N (ctrl/treat)",  f"{m_a.get('n_control',0):,}/{m_a.get('n_treatment',0):,}",
                            f"{m_b.get('n_control',0):,}/{m_b.get('n_treatment',0):,}"),
        ("Verdict",         str(m_a.get("verdict", "—")),     str(m_b.get("verdict", "—"))),
        ("Ship Decision",   _ship(m_a),                       _ship(m_b)),
        ("SRM",             _srm(m_a),                        _srm(m_b)),
        ("Guardrail Viols", str(len(m_a.get("guardrails",[]))), str(len(m_b.get("guardrails",[])))),
    ]

    # Header
    print(f"\n  {'═' * W}")
    print(f"  {'COMPARATIVE ANALYSIS':^{W}}")
    print(f"  {'═' * W}")
    print(f"  {'A: ' + name_a[:CW]:<{CW+4}}  │  {'B: ' + name_b[:CW]}")
    print(f"  {'─' * W}")

    for label, val_a, val_b in rows:
        print(f"  {label:<18}  {val_a:<{CW}}  │  {val_b}")

    # Segment divergence
    slices_a = {f"{s.dimension_name}={s.dimension_value}": s for s in m_a.get("slices", [])}
    slices_b = {f"{s.dimension_name}={s.dimension_value}": s for s in m_b.get("slices", [])}
    common   = set(slices_a) & set(slices_b)

    if common:
        print(f"\n  {'─' * W}")
        print(f"  {'SEGMENT COMPARISON (shared slices)':^{W}}")
        print(f"  {'─' * W}")
        print(f"  {'Slice':<28}  {'Δ (A)':>10}  {'Δ (B)':>10}  {'Diverge?':>10}")
        print(f"  {'─' * W}")
        for key in sorted(common)[:8]:
            sa = slices_a[key]
            sb = slices_b[key]
            da = float(getattr(getattr(sa, "delta", None), "delta_pp", 0) or 0)
            db = float(getattr(getattr(sb, "delta", None), "delta_pp", 0) or 0)
            diverge = "⚠️  Yes" if (da * db < 0 and abs(da - db) > 0.005) else "—"
            print(f"  {key:<28}  {da:>+10.4f}  {db:>+10.4f}  {diverge:>10}")

    print(f"  {'═' * W}\n")


# ─────────────────────────────────────────────────────────────────────────────
# NARRATIVE SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────

def _synthesise(name_a: str, m_a: Dict, name_b: str, m_b: Dict) -> str:
    lines = ["📝 Synthesis:\n"]

    da, db = m_a.get("delta_pp", 0), m_b.get("delta_pp", 0)
    sig_a, sig_b = m_a.get("is_sig"), m_b.get("is_sig")

    if sig_a and sig_b:
        if da * db > 0:
            lines.append(f"  Both experiments moved in the same direction. "
                         f"{name_a}: {da:+.3f}pp, {name_b}: {db:+.3f}pp. "
                         f"Consistent signal suggests a real effect.")
        else:
            lines.append(f"  ⚠️  Experiments moved in OPPOSITE directions. "
                         f"{name_a}: {da:+.3f}pp, {name_b}: {db:+.3f}pp. "
                         f"Investigate confounds or audience differences.")
    elif sig_a and not sig_b:
        lines.append(f"  Only {name_a} reached significance (Δ={da:+.3f}pp). "
                     f"{name_b} was inconclusive (Δ={db:+.3f}pp). "
                     f"Consider whether {name_b} was underpowered.")
    elif not sig_a and sig_b:
        lines.append(f"  Only {name_b} reached significance (Δ={db:+.3f}pp). "
                     f"{name_a} was inconclusive (Δ={da:+.3f}pp).")
    else:
        lines.append(f"  Neither experiment reached significance. "
                     f"Both may be underpowered or testing a null hypothesis.")

    if m_a.get("srm") or m_b.get("srm"):
        lines.append(f"\n  ⚠️  SRM detected in {'A' if m_a.get('srm') else 'B'}. "
                     f"Interpret affected results with caution.")

    ship_a = str(m_a.get("ship", "")).lower()
    ship_b = str(m_b.get("ship", "")).lower()
    if "ship" in ship_a and "ship" in ship_b:
        lines.append(f"\n  ✅ Both experiments recommend shipping.")
    elif "not" in ship_a or "not" in ship_b:
        lines.append(f"\n  ⛔ At least one experiment recommends NOT shipping.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MEMORY-BACKED COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

def compare_from_memory(name_a: str, name_b: str, memory) -> bool:
    r_a = memory.search_similar(name_a, limit=1)
    r_b = memory.search_similar(name_b, limit=1)
    if not r_a or not r_b:
        print("  One or both experiments not found in memory.")
        return False

    # Build synthetic metric dicts from memory records
    def _mem_to_metrics(r):
        return {
            "metric":      r.get("primary_metric", "—"),
            "delta_pp":    float(r.get("delta_pp", 0) or 0),
            "p_value":     float(r.get("p_value", 1) or 1),
            "is_sig":      bool(r.get("is_significant", False)),
            "direction":   "positive" if r.get("delta_pp", 0) > 0 else "negative",
            "verdict":     r.get("verdict", "—"),
            "ship":        r.get("ship_recommendation", "—"),
            "srm":         False,
            "slices":      [],
            "guardrails":  [],
        }

    m_a = _mem_to_metrics(r_a[0])
    m_b = _mem_to_metrics(r_b[0])
    _render_comparison(r_a[0]["experiment_name"], m_a, r_b[0]["experiment_name"], m_b)
    print(_synthesise(r_a[0]["experiment_name"], m_a, r_b[0]["experiment_name"], m_b))
    return True


__all__ = [
    "compare_from_memory",
    "_extract_metrics",
    "_render_comparison",
    "_synthesise",
]
