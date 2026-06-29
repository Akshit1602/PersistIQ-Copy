from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_ui(args) -> None:
    from continum.userui.app import run
    run(host=args.host, port=args.port, data_dir=args.data, debug=args.debug)


def cmd_inspect(args) -> None:
    from continum.runtime.session  import get_session
    from continum.runtime.intelligence import get_bus
    from continum.runtime.memory   import get_memory
    from continum.runtime.inspect  import inspect, print_inspection

    what = args.what
    session = get_session()
    bus     = get_bus()
    memory  = get_memory()

    db = None
    try:
        from continum.app.loader import setup_database
        db = setup_database(args.data)
        session.db = db
    except Exception:
        pass

    report = inspect(what, session=session, db=db, bus=bus, memory=memory)
    print_inspection(what, report)


def cmd_audit(args) -> None:
    from continum.runtime.enterprise import get_audit
    audit = get_audit()
    entries = audit.tail(int(getattr(args, "n", 20)))
    print("\n" + audit.render_table(entries))


def cmd_snapshot(args) -> None:
    from continum.runtime.session    import get_session
    from continum.runtime.intelligence import get_bus
    from continum.runtime.enterprise import get_snapshots, get_audit
    session = get_session()
    bus     = get_bus()
    snaps   = get_snapshots()
    label   = getattr(args, "label", "")
    sid     = snaps.take(session, bus=bus, label=label)
    print(f"\n  ✅ Snapshot taken: {sid}\n")
    get_audit().record("snapshot", sid, {"label": label}, session_id=session.session_id)


def cmd_shell(args) -> None:
    from continum.runtime.shell import run_shell
    run_shell(data_dir=args.data)


def cmd_ask(args) -> None:
    from continum.runtime.session import get_session
    from continum.runtime.intelligence import get_bus
    from continum.runtime.memory import get_memory
    from continum.runtime.ask import ContinumCopilot

    session = get_session()
    bus     = get_bus()
    memory  = get_memory()
    copilot = ContinumCopilot(session=session, bus=bus, memory=memory)

    if hasattr(args, "question") and args.question:
        question = " ".join(args.question)
        response = copilot.ask(question)
        print(f"\n{response}\n")
    else:
        copilot.interactive()


def cmd_session(args) -> None:
    from continum.runtime.session import get_session
    from continum.runtime.intelligence import get_bus
    from continum.runtime.memory import get_memory

    session = get_session()
    bus     = get_bus()
    memory  = get_memory()

    print(f"\n  {'═' * 68}")
    print(f"  SESSION: {session.session_id}  |  Client: {session.client_name}")
    print(f"  Created : {session.created_at[:19]}")
    print(f"  Mode    : {session.mode}")
    print(f"  Experiment: {session.active_experiment or '—'}")
    print(f"  Metrics   : {', '.join(session.active_metrics[:5]) or '—'}")
    print(f"  Runs      : {len(session.execution_history)}")
    print(f"  Memory    : {memory.experiment_count()} experiments stored")

    if session.execution_history:
        print(f"\n  Run history:")
        for rec in session.execution_history[-10:]:
            icon = "✅" if rec.ok else "❌"
            print(f"    {icon}  {rec.module:<28}  {rec.elapsed_s:.2f}s  {rec.summary[:50]}")

    if session.recommendations:
        print(f"\n  Active recommendations:")
        for r in session.recommendations[:5]:
            print(f"    [{r.priority}] {r.action}  — {r.reason}")

    panel = bus.render_panel(max_items=8, width=70)
    if panel:
        print(f"\n{panel}")
    print(f"\n  {'═' * 68}\n")


def cmd_demo(args) -> None:
    from continum.app.workflow import run_demo_workflow
    run_demo_workflow(
        data_dir=args.data,
        experiment_name=getattr(args, "exp", None),
    )


def cmd_analyse(args) -> None:
    from continum.app.loader import setup_database
    from continum.core.orchestration.dags.analysis_dag import run_experiment_analysis_pipeline
    from continum.core.intelligence.narrative import generate_decision_memo

    db = setup_database(args.data)
    result = run_experiment_analysis_pipeline(
        experiment_id=args.experiment,
        experiment_name=args.experiment,
        db=db, llm=None, save_result=True,
    )
    r = result.get("result")
    if r is None:
        print(f"❌ Analysis failed: {result.get('error', 'unknown error')}")
        return

    print("\n" + "=" * 72)
    print(f"  {args.experiment}")
    print("=" * 72)
    print(f"  Verdict       : {r.verdict.value}")
    print(f"  Recommendation: {r.ship_recommendation.value}")
    print(f"  Primary Δ     : {r.primary_delta.delta_pp:+.4f}pp  "
          f"p={r.primary_delta.p_value:.4f}")
    print(f"  SRM           : {'DETECTED ⚠️' if r.srm_detected else 'Clean ✅'}")
    print(f"  Segment slices: {len(r.slice_findings)}")
    print()
    print("  DECISION MEMO")
    print("  " + "-" * 68)
    print(f"  {generate_decision_memo(r)}")
    print()
    if result.get("narrative"):
        print("  NARRATIVE")
        print("  " + "-" * 68)
        print(f"  {result['narrative'][:500]}")


def cmd_health(args) -> None:
    from continum.app.loader import setup_database
    from continum.core.monitoring.monitors import PipelineHealthMonitor, WatchtowerMonitor

    db = setup_database(args.data)
    print("\n  Pipeline Health Monitor\n  " + "─" * 50)
    monitor  = PipelineHealthMonitor(db=db)
    reports  = monitor.run()
    if not reports:
        print("  ✅ No anomalies detected.")
    for r in reports:
        icon = "🚨" if r.severity.value == "critical" else "⚠️ "
        print(f"  {icon}  [{r.severity.value.upper()}] {r.recommended_action}")

    print("\n  Watchtower Monitor\n  " + "─" * 50)
    wt = WatchtowerMonitor(db=db)
    alerts = wt.run()
    if not alerts:
        print("  ✅ No dimensional anomalies.")
    for a in alerts[:5]:
        icon = "🚨" if a.severity.value == "critical" else "⚠️ "
        print(f"  {icon}  [{a.severity.value.upper()}] {a.recommended_action}")


def cmd_list_experiments(args) -> None:
    from continum.app.loader import setup_database, list_experiments
    db   = setup_database(args.data)
    exps = list_experiments(db)
    print(f"\n  {'Experiment':<40} {'Variants':>8} {'Rows':>8} {'Start':>12} {'End':>12}")
    print("  " + "─" * 82)
    for _, row in exps.iterrows():
        print(f"  {row['experiment_name']:<40} {row['n_variants']:>8} "
              f"{row['n_rows']:>8,} {str(row['start_date']):>12} {str(row['end_date']):>12}")


def cmd_list_modules(args) -> None:
    from continum.toolinterface import list_modules, _build_registry
    _build_registry()
    mods = list_modules()
    print(f"\n  {'Phase':<10} {'Module':<30} {'Description'[:50]}")
    print("  " + "─" * 90)
    for m in mods:
        print(f"  [{m['phase']:<7}] {m['name']:<30} {m['description'][:50]}")


def cmd_replay(args) -> None:
    from continum.core.orchestration.engine import ExecutionRegistry
    reg = ExecutionRegistry()
    records = reg.read_all()
    run_id  = args.run_id
    matches = [r for r in records if r.get("run_id", "").startswith(run_id)]
    if not matches:
        print(f"  No record found for run_id starting with '{run_id}'")
        return
    r = matches[-1]
    print(f"\n  Run ID        : {r['run_id']}")
    print(f"  Experiment    : {r['experiment_name']}")
    print(f"  Status        : {r['status']}")
    print(f"  Started       : {r['started_at']}")
    print(f"  Duration      : {r['elapsed_s']:.2f}s")
    print(f"  Tasks OK/Fail : {r['n_tasks_ok']}/{r['n_tasks_failed']}")
    if r.get("primary_metric"):
        pm = r["primary_metric"]
        print(f"  Primary Δ     : {pm.get('delta_pp', 0):+.4f}pp  "
              f"p={pm.get('p_value', 1):.4f}  sig={pm.get('significant')}")
    print("\n  Task timeline:")
    for t in r.get("task_results", []):
        icon = "✅" if t["ok"] else "❌"
        print(f"    {icon}  {t['task']:<28} {t['elapsed_s']:.3f}s  "
              f"retries={t.get('n_retries', 0)}  "
              f"in={t.get('input_hash', '')[:8]}  out={t.get('output_hash', '')[:8]}")


# ─────────────────────────────────────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="continum",
        description="Continum Experimentation Intelligence CLI",
    )
    parser.add_argument("--data", default="./sample_data",
                        help="Path to CSV data directory (default: ./sample_data)")
    parser.add_argument("--verbose", "-v", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo",             help="Run the full interactive demo")
    sub.add_parser("shell",            help="🚀 CONTINUM OS interactive runtime (CLI)")
    sub.add_parser("health",           help="Pipeline health and Watchtower check")
    sub.add_parser("list-experiments", help="Show available experiments")
    sub.add_parser("list-modules",     help="Show registered modules")
    sub.add_parser("session",          help="Show current session state")

    p_ui = sub.add_parser("ui", help="🌐 Launch Flask visual operator console")
    p_ui.add_argument("--port",  type=int, default=5050)
    p_ui.add_argument("--host",  default="0.0.0.0")
    p_ui.add_argument("--debug", action="store_true")

    p_inspect = sub.add_parser("inspect", help="Inspect runtime state")
    p_inspect.add_argument("what", nargs="?", default="session",
                           choices=["session","semantic","metrics","assumptions","cohorts","lineage"])

    p_audit = sub.add_parser("audit", help="Show audit trail")
    p_audit.add_argument("--n", type=int, default=20)

    p_snap = sub.add_parser("snapshot", help="Take a session snapshot")
    p_snap.add_argument("--label", default="")

    p_analyse = sub.add_parser("analyse", help="Analyse one experiment")
    p_analyse.add_argument("experiment", help="Experiment name")

    p_ask = sub.add_parser("ask", help="Ask Continum a question")
    p_ask.add_argument("question", nargs="*")

    p_replay = sub.add_parser("replay", help="Show lineage for a run")
    p_replay.add_argument("run_id", help="Run ID prefix")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    dispatch = {
        "demo":             cmd_demo,
        "shell":            cmd_shell,
        "ui":               cmd_ui,
        "inspect":          cmd_inspect,
        "audit":            cmd_audit,
        "snapshot":         cmd_snapshot,
        "analyse":          cmd_analyse,
        "health":           cmd_health,
        "list-experiments": cmd_list_experiments,
        "list-modules":     cmd_list_modules,
        "replay":           cmd_replay,
        "ask":              cmd_ask,
        "session":          cmd_session,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
