from __future__ import annotations

import logging
import time
from typing import Any, Optional

from continum.runtime.shell.renderer import (
    bold, dim, cyan, green, yellow, red,
    section_header, divider, menu_item, prompt, W,
)
from continum.runtime.shell.menu import PHASE_MODULES

logger = logging.getLogger("continum.runtime.shell.commands")


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT PICKER (shared by causal + journey)
# ─────────────────────────────────────────────────────────────────────────────

def pick_experiment(db, session) -> Optional[str]:
    if db is None:
        return None
    try:
        from continum.app.loader import list_experiments
        exps = list_experiments(db)
        if exps.empty:
            print("\n  No experiments found in the data.")
            return None
        if session and session.active_experiment:
            print(f"\n  Current experiment: {cyan(session.active_experiment)}")
            if prompt("Keep this? [Y/n]").strip().lower() != "n":
                return session.active_experiment

        section_header("Available Experiments")
        for i, row in exps.iterrows():
            print(f"    [{i+1}]  {row['experiment_name']:<42} "
                  f"{row['n_rows']:>7,} rows  {row['n_variants']} variants")
        divider()
        choice = prompt("Select number").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(exps):
                return exps.iloc[idx]["experiment_name"]
    except Exception as e:
        logger.debug("pick_experiment error: %s", e)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# INTELLIGENCE MENU
# ─────────────────────────────────────────────────────────────────────────────

def cmd_intelligence(session, bus, memory) -> None:
    while True:
        section_header("Intelligence Layer")
        menu_item("1", "Show Intelligence Panel")
        menu_item("2", "Warnings & Anomalies")
        menu_item("3", "Recommendations")
        menu_item("4", "Cross-Experiment Memory")
        menu_item("5", "Export Session")
        print(f"\n    {bold('[B]')}  Back")
        divider()

        choice = prompt("Intelligence").strip().upper()
        if choice in ("B", "Q", "BACK"):
            break

        elif choice == "1":
            panel = bus.render_panel(max_items=20, width=W)
            print(f"\n{panel}" if panel else "\n  No insights yet.")

        elif choice == "2":
            warnings = bus.warnings()
            if not warnings:
                print(f"\n  {green('✅')} No warnings or anomalies.")
            else:
                print(f"\n  {len(warnings)} warning(s):\n")
                for ins in warnings:
                    print(f"  {ins.full_text()}\n")

        elif choice == "3":
            recs = bus.recommendations()
            if not recs:
                print("\n  No recommendations yet.")
            else:
                print(f"\n  {len(recs)} recommendation(s):\n")
                for ins in recs:
                    print(f"  {ins.full_text()}\n")
            if session and session.recommendations:
                print(f"\n  Workflow chain:")
                for r in session.recommendations[:5]:
                    print(f"  [{r.priority}] {r.action}  — {r.reason}")

        elif choice == "4":
            print(f"\n{memory.render_summary()}")
            exp = session.active_experiment if session else None
            similar = memory.search_similar(exp or "conversion", limit=3)
            if similar:
                print(f"\n  Similar past experiments:")
                for r in similar:
                    sig = "✅" if r.get("is_significant") else "—"
                    print(f"    {sig}  {r['experiment_name']:<40}  "
                          f"Δ={r.get('delta_pp', 0):+.3f}pp  {r.get('verdict', '')}")
            good_metrics = memory.get_successful_metrics(limit=5)
            if good_metrics:
                print(f"\n  High-signal metrics:")
                for m in good_metrics:
                    print(f"    📊 {m['metric_name']:<32}  "
                          f"{m['n_experiments']} exps  sig_rate={m['sig_rate']:.0%}")

        elif choice == "5":
            cmd_export(session, bus)


# ─────────────────────────────────────────────────────────────────────────────
# REPLAY / LINEAGE
# ─────────────────────────────────────────────────────────────────────────────

def cmd_replay(session) -> None:
    history = session.execution_history if session else []
    if not history:
        print("\n  No runs in this session yet.")
        return
    section_header("Session Lineage")
    for rec in history:
        icon = green("✅") if rec.ok else red("❌")
        print(f"  {icon}  {rec.run_id}  {rec.module:<28}  {rec.elapsed_s:.2f}s")
        if rec.summary:
            print(f"       {dim(rec.summary[:70])}")
    divider()


# ─────────────────────────────────────────────────────────────────────────────
# SESSION INFO
# ─────────────────────────────────────────────────────────────────────────────

def cmd_session_info(session, bus, memory) -> None:
    section_header("Session State")
    print(f"  Session   : {session.session_id}  |  Client: {session.client_name}")
    print(f"  Created   : {session.created_at[:19]}")
    print(f"  Experiment: {session.active_experiment or '—'}")
    print(f"  Metrics   : {', '.join(session.active_metrics[:5]) or '—'}")
    print(f"  Runs      : {len(session.execution_history)}")
    print(f"  Memory    : {memory.experiment_count()} experiments stored")
    if session.execution_history:
        print(f"\n  Last 5 runs:")
        for rec in session.execution_history[-5:]:
            icon = "✅" if rec.ok else "❌"
            print(f"    {icon}  {rec.module:<28}  {rec.elapsed_s:.2f}s  {dim(rec.summary[:50])}")
    panel = bus.render_panel(max_items=6, width=W)
    if panel:
        print(f"\n{panel}")
    divider()


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def cmd_export(session, bus) -> None:
    import json as _json
    path = f"continum_export_{session.session_id}.json"
    try:
        data = {
            "session": session.to_dict(),
            "insights": [
                {"type": i.insight_type, "severity": i.severity,
                 "source": i.source_module, "message": i.message,
                 "detail": i.detail, "created_at": i.created_at}
                for i in bus.all()
            ],
        }
        with open(path, "w") as f:
            _json.dump(data, f, indent=2, default=str)
        print(f"\n  {green('✅')} Exported → {path}")
    except Exception as e:
        print(f"\n  {red('❌')} Export failed: {e}")


__all__ = [
    "pick_experiment",
    "cmd_intelligence",
    "cmd_replay",
    "cmd_session_info",
    "cmd_export",
]
