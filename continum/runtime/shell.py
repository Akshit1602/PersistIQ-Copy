from __future__ import annotations

import logging
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("continum.runtime.shell")

# ─────────────────────────────────────────────────────────────────────────────
# ANSI COLOUR HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _tty() -> bool:
    return sys.stdout.isatty()


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _tty() else s


def _dim(s: str) -> str:
    return f"\033[2m{s}\033[0m" if _tty() else s


def _cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m" if _tty() else s


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _tty() else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _tty() else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _tty() else s


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

# Menu structure: key → (label, phase_key, sub-items)
MAIN_MENU: List[Tuple[str, str, str]] = [
    ("0", "Full Journey (End-to-End)",       "journey"),
    ("1", "Discovery",                        "discovery"),
    ("2", "Planning",                         "planning"),
    ("3", "Audience Selection",               "audience"),
    ("4", "Live Monitoring",                  "monitoring"),
    ("5", "Causal & Post-Experiment",        "causal"),
    ("6", "Intelligence Layer",              "intelligence"),
    ("A", "Ask Continum",                    "ask"),
    ("R", "Replay / Lineage",               "replay"),
    ("S", "Session Info",                    "session"),
]

PHASE_MODULES: Dict[str, List[Tuple[str, str, str]]] = {
    "discovery": [
        ("1", "Schema Discovery & Mapping",     "schema_discovery"),
        ("2", "Data Validation",                "data_validation"),
        ("3", "Dimension Setup",               "dimension_setup"),
        ("4", "Pipeline Health Monitor",        "pipeline_health"),
        ("5", "Watchtower Anomaly Scan",        "watchtower"),
    ],
    "planning": [
        ("1", "Experiment Brief Generator",     "brief_generator"),
        ("2", "Opportunity Sizing",             "opportunity_sizing"),
        ("3", "Power Calculator",               "power_calculator"),
        ("4", "KPI & Tracking Plan",            "metrics_and_tracking"),
        ("5", "Audience Selection",             "audience_selection"),
    ],
    "audience": [
        ("1", "Audience Selection",             "audience_selection"),
        ("2", "Opportunity Sizing",             "opportunity_sizing"),
    ],
    "monitoring": [
        ("1", "Experiment Health Monitor",      "health_monitor"),
        ("2", "Sequential Testing (mSPRT)",     "sequential_testing"),
        ("3", "Pipeline Health",                "pipeline_health"),
    ],
    "causal": [
        ("1", "Full A/B Readout",               "experiment_analysis"),
        ("2", "Causal Analysis (7-method)",     "causal_analysis"),
        ("3", "Pre-Post Analysis",              "pre_post_analysis"),
        ("4", "Simpson's Paradox Detector",     "simpsons_paradox"),
        ("5", "ROI Tracker",                    "roi_tracker"),
        ("6", "Learnings Repository",           "learnings_repository"),
        ("7", "Uplift Modeller",                "uplift_modeller"),
        ("8", "Decision Engine",                "decision_engine"),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# THE SHELL
# ─────────────────────────────────────────────────────────────────────────────

class ContinumShell:

    W = 72  # console width

    def __init__(self, data_dir: str = "./sample_data", session=None, verbose: bool = True):
        self.data_dir  = data_dir
        self.verbose   = verbose
        self.db        = None
        self.state     = None
        self.datasets  = {}

        # Runtime layers
        from continum.runtime.session      import get_session
        from continum.runtime.intelligence import get_bus
        from continum.runtime.memory       import get_memory
        from continum.runtime.console      import reset_console

        self.session  = session or get_session()
        self.bus      = get_bus()
        self.memory   = get_memory()
        self.console  = reset_console("shell")

    # ── Boot ───────────────────────────────────────────────────────────────────

    def boot(self) -> bool:
        self._os_banner()
        print(f"  {_dim('Booting Continum OS...')}\n")

        try:
            from continum.app.loader import load_csvs, register_bronze, build_silver_layer, build_gold_layer
            from continum.api.bootstrap import bootstrap_from_connection
            import duckdb

            self.console.info("Initialising analytical engine")
            self.db    = duckdb.connect(":memory:")
            self.state = bootstrap_from_connection(mode="duckdb", client_name=self.session.client_name, db=self.db)
            self.session.db    = self.db
            self.session.state = self.state

            self.console.info("Loading data from: " + self.data_dir)
            self.datasets = load_csvs(self.data_dir)
            register_bronze(self.db, self.datasets)
            build_silver_layer(self.db)
            build_gold_layer(self.db)

            # Publish boot success
            self.bus.success("shell", f"Continum OS ready — {len(self.datasets)} datasets loaded")

            print(f"\n  {_green('✅')} Ready. {len(self.datasets)} tables loaded.")
            self._show_intelligence_panel()
            return True

        except Exception as e:
            print(f"\n  {_red('❌')} Boot failed: {e}")
            logger.exception("Shell boot error")
            return False

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        if not self.boot():
            return

        while True:
            self._show_main_menu()
            choice = self._prompt("Select").strip().upper()

            if choice in ("Q", "QUIT", "EXIT"):
                self._shutdown()
                break

            elif choice == "0":
                self._run_journey()

            elif choice == "1":
                self._run_phase_menu("Discovery", "discovery")

            elif choice == "2":
                self._run_phase_menu("Planning", "planning")

            elif choice == "3":
                self._run_module("audience_selection", "Audience Selection")

            elif choice == "4":
                self._run_phase_menu("Live Monitoring", "monitoring")

            elif choice == "5":
                self._run_causal_menu()

            elif choice == "6":
                self._run_intelligence_menu()

            elif choice == "A":
                self._run_ask_continum()

            elif choice == "R":
                self._run_replay()

            elif choice == "S":
                self._show_session_info()

            else:
                print(f"  {_yellow('?')} Unknown option: {choice!r}")

    # ── OS Banner ──────────────────────────────────────────────────────────────

    def _os_banner(self) -> None:
        w = self.W
        print(f"\n{'═' * w}")
        print(f"{'CONTINUM OS':^{w}}")
        print(f"{'Experimentation Intelligence Platform':^{w}}")
        print(f"{'═' * w}\n")

    # ── Main Menu ──────────────────────────────────────────────────────────────

    def _show_main_menu(self) -> None:
        w = self.W
        exp   = self.session.active_experiment or "—"
        n_run = len(self.session.execution_history)
        intel = self.bus.render_summary()

        print(f"\n  {'─' * (w - 4)}")
        print(f"  {_bold('CONTINUM OS')}  |  Experiment: {_cyan(exp)}  |  Runs: {n_run}")
        if intel:
            print(intel)
        print(f"  {'─' * (w - 4)}\n")

        for key, label, _ in MAIN_MENU:
            bullet = _bold(f"[{key}]")
            print(f"    {bullet}  {label}")

        print(f"\n    {_bold('[Q]')}  Quit")
        print(f"\n  {'─' * (w - 4)}")

    # ── Phase sub-menus ────────────────────────────────────────────────────────

    def _run_phase_menu(self, phase_name: str, phase_key: str) -> None:
        modules = PHASE_MODULES.get(phase_key, [])
        if not modules:
            print(f"  No modules defined for phase: {phase_key}")
            return

        while True:
            print(f"\n  {'─' * 68}")
            print(f"  {_bold(phase_name.upper())}")
            print(f"  {'─' * 68}")
            for key, label, module_key in modules:
                last = self.session.last_run(module_key)
                tag  = f"  {_dim('✓')}" if last and last.ok else ""
                print(f"    [{key}]  {label}{tag}")
            print(f"\n    [B]  Back")
            print(f"  {'─' * 68}")

            choice = self._prompt(phase_name).strip().upper()
            if choice in ("B", "BACK", "Q"):
                break

            # Match by number
            matched = next((m for m in modules if m[0] == choice), None)
            if matched:
                _, label, module_key = matched
                self._run_module(module_key, label)
            else:
                print(f"  {_yellow('?')} Unknown: {choice!r}")

    # ── Module execution with context wiring ───────────────────────────────────

    def _run_module(self, module_key: str, label: str, **kwargs) -> Optional[Any]:
        from continum.api.dispatcher import run_module, get_module, _build_registry
        from continum.runtime.intelligence import publish_next_steps
        from continum.runtime.console import reset_console

        _build_registry()
        spec = get_module(module_key)
        if spec is None:
            print(f"\n  {_yellow('⚠️')}  Module '{module_key}' not available in this installation.")
            self.bus.warn("shell", f"Module '{module_key}' not available")
            return None

        w = self.W
        print(f"\n  {'═' * w}")
        print(f"  {_bold('▶ ' + label.upper())}")
        print(f"  {'═' * w}")

        con = reset_console(module_key)
        t0  = time.monotonic()

        try:
            result = run_module(
                module_key,
                state=self.state,
                llm=None,
                db=self.db,
                **kwargs,
            )
            elapsed = time.monotonic() - t0

            # Store in session context
            self.session.set(f"{module_key}_result", result)
            self.session.set("experiment_result", result)   # generic slot

            # Record run
            summary = self._summarise_result(result, module_key)
            self.session.record_run(
                module=module_key,
                phase=spec.phase,
                elapsed_s=elapsed,
                ok=True,
                summary=summary,
            )

            # Store in memory if it's an experiment result
            if module_key == "experiment_analysis" and result:
                exp_name = self.session.active_experiment or "unknown"
                self.memory.record_experiment(exp_name, exp_name, result)

            # Publish intelligence
            self.bus.success(module_key, f"{label} completed in {elapsed:.2f}s")
            publish_next_steps(module_key, self.bus)

            # Add workflow recommendations to session
            from continum.runtime.intelligence import WORKFLOW_CHAIN
            for next_mod, reason, priority in WORKFLOW_CHAIN.get(module_key, [])[:2]:
                self.session.add_recommendation(
                    source=module_key,
                    action=f"Run {next_mod}",
                    reason=reason,
                    module_key=next_mod,
                    priority=priority,
                )

            self.session.save()

            # Show next-step prompt
            self._show_next_steps(module_key)
            return result

        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"\n  {_red('❌')} {label} failed: {e}")
            logger.exception("Module %s failed", module_key)
            self.bus.warn(module_key, f"{label} failed: {str(e)[:80]}")
            self.session.record_run(module_key, spec.phase, elapsed, ok=False, error=str(e))
            self.session.save()
            return None

    def _summarise_result(self, result: Any, module_key: str) -> str:
        if result is None:
            return ""
        try:
            # ExperimentResult
            if hasattr(result, "verdict") and hasattr(result, "primary_delta"):
                d = result.primary_delta
                return (f"Δ={d.delta_pp:+.3f}pp  p={d.p_value:.4f}  "
                        f"{'✅' if d.is_significant else '—'}  {result.verdict.value}")
            # Dict result from modules
            if isinstance(result, dict):
                r = result.get("result")
                if r and hasattr(r, "verdict"):
                    d = r.primary_delta
                    return f"Δ={d.delta_pp:+.3f}pp  p={d.p_value:.4f}  {r.verdict.value}"
                if "error" in result:
                    return f"Error: {result['error']}"
                return str(list(result.keys()))[:60]
            return str(result)[:60]
        except Exception:
            return ""

    # ── Next-step prompt ────────────────────────────────────────────────────────

    def _show_next_steps(self, module_key: str) -> None:
        from continum.runtime.intelligence import WORKFLOW_CHAIN
        chain = WORKFLOW_CHAIN.get(module_key, [])
        if not chain:
            return
        print(f"\n  {'─' * 68}")
        print(f"  {_bold('Recommended Next Steps:')}")
        for next_mod, reason, _ in chain[:3]:
            print(f"    {_cyan('▶')} {reason}  {_dim('(' + next_mod + ')')}")
        print(f"  {'─' * 68}")

    # ── Intelligence panel ─────────────────────────────────────────────────────

    def _show_intelligence_panel(self) -> None:
        panel = self.bus.render_panel(max_items=8, width=self.W)
        if panel:
            print(f"\n{panel}")

    # ── Causal deep-dive menu ──────────────────────────────────────────────────

    def _run_causal_menu(self) -> None:
        # First, pick an experiment
        exp = self._pick_experiment()
        if exp:
            self.session.select_experiment(exp)
            self.bus.emit("shell", f"Experiment selected: {exp}",
                          "info", "info", experiment_id=exp)

        self._run_phase_menu("Causal & Post-Experiment Analysis", "causal")

    def _pick_experiment(self) -> Optional[str]:
        if self.db is None:
            return None
        try:
            from continum.app.loader import list_experiments
            exps = list_experiments(self.db)
            if exps.empty:
                return None
            if self.session.active_experiment:
                print(f"\n  Current experiment: {_cyan(self.session.active_experiment)}")
                if input("  Keep this? [Y/n]: ").strip().lower() == "n":
                    pass
                else:
                    return self.session.active_experiment

            print(f"\n  {'─' * 68}")
            print(f"  {_bold('Available Experiments:')}")
            for i, row in exps.iterrows():
                print(f"    [{i+1}] {row['experiment_name']}  "
                      f"({row['n_rows']:,} rows  {row['n_variants']} variants)")
            print(f"  {'─' * 68}")

            choice = self._prompt("Select experiment number").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(exps):
                    return exps.iloc[idx]["experiment_name"]
        except Exception as e:
            logger.debug("Experiment picker error: %s", e)
        return None

    # ── Intelligence menu ──────────────────────────────────────────────────────

    def _run_intelligence_menu(self) -> None:
        while True:
            print(f"\n  {'─' * 68}")
            print(f"  {_bold('INTELLIGENCE LAYER')}")
            print(f"  {'─' * 68}")
            print(f"    [1]  Show Intelligence Panel (all insights)")
            print(f"    [2]  Show Warnings & Anomalies")
            print(f"    [3]  Show Recommendations")
            print(f"    [4]  Cross-Experiment Memory")
            print(f"    [5]  Export Session Summary")
            print(f"\n    [B]  Back")
            print(f"  {'─' * 68}")

            choice = self._prompt("Intelligence").strip().upper()
            if choice in ("B", "Q", "BACK"):
                break
            elif choice == "1":
                panel = self.bus.render_panel(max_items=20, width=self.W)
                print(f"\n{panel}" if panel else "\n  No insights yet.")
            elif choice == "2":
                warnings = self.bus.warnings()
                if not warnings:
                    print("\n  ✅ No warnings or anomalies.")
                else:
                    print(f"\n  {len(warnings)} warning(s):\n")
                    for ins in warnings:
                        print(f"  {ins.full_text()}\n")
            elif choice == "3":
                recs = self.bus.recommendations()
                if not recs:
                    print("\n  No recommendations yet. Run some modules first.")
                else:
                    print(f"\n  {len(recs)} recommendation(s):\n")
                    for ins in recs:
                        print(f"  {ins.full_text()}\n")
                # Session recommendations
                if self.session.recommendations:
                    print(f"\n  Workflow chain suggestions:\n")
                    for r in self.session.recommendations[:5]:
                        print(f"  [{r.priority}] {r.action}  — {r.reason}")
            elif choice == "4":
                print(f"\n{self.memory.render_summary()}")
                recent = self.memory.search_similar(
                    self.session.active_experiment or "conversion", limit=3
                )
                if recent:
                    print(f"\n  Similar past experiments:")
                    for r in recent:
                        sig = "✅" if r.get("is_significant") else "—"
                        print(f"  {sig} {r['experiment_name']}  Δ={r.get('delta_pp', 0):+.3f}pp  {r.get('verdict', '')}")
                metrics = self.memory.get_successful_metrics(limit=5)
                if metrics:
                    print(f"\n  Most successful metrics:")
                    for m in metrics:
                        print(f"  📊 {m['metric_name']}  ({m['n_experiments']} exps  sig_rate={m['sig_rate']:.0%})")
            elif choice == "5":
                self._export_session()

    # ── Ask Continum ───────────────────────────────────────────────────────────

    def _run_ask_continum(self) -> None:
        from continum.runtime.ask import ContinumCopilot
        copilot = ContinumCopilot(session=self.session, bus=self.bus, memory=self.memory)
        copilot.interactive()

    # ── Full end-to-end journey ────────────────────────────────────────────────

    def _run_journey(self) -> None:
        w = self.W
        print(f"\n  {'═' * w}")
        print(f"  {_bold('END-TO-END EXPERIMENTATION JOURNEY')}")
        print(f"  {'═' * w}")
        print(f"""
  This guided workflow replicates the notebook's natural flow:

    1  Data Discovery    — understand your data
    2  Opportunity Sizing — quantify the prize
    3  Power Calculation — design the experiment
    4  Experiment Brief  — generate the spec
    5  Health Monitoring — watch the live experiment
    6  Full A/B Readout  — analyse results
    7  Causal Deep-Dive  — validate causality
    8  ROI Tracking      — measure incremental revenue

  Each step's output feeds the next automatically.
""")

        if input("  Start the journey? [Y/n]: ").strip().lower() == "n":
            return

        # Stage 1: Discovery
        self.bus.next_step("journey", "Starting: Data Discovery")
        self._run_module("schema_discovery", "Schema Discovery")

        # Stage 2: Opportunity
        cont = input("\n  Continue to Opportunity Sizing? [Y/n]: ").strip().lower()
        if cont != "n":
            self._run_module("opportunity_sizing", "Opportunity Sizing")

        # Stage 3: Power
        cont = input("\n  Continue to Power Calculator? [Y/n]: ").strip().lower()
        if cont != "n":
            self._run_module("power_calculator", "Power Calculator")

        # Stage 4: Brief
        cont = input("\n  Continue to Experiment Brief? [Y/n]: ").strip().lower()
        if cont != "n":
            self._run_module("brief_generator", "Experiment Brief Generator")

        # Stage 5: Pick experiment and analyse
        print(f"\n  {'─' * 68}")
        print(f"  Now let's analyse a running/concluded experiment.")
        exp = self._pick_experiment()
        if exp:
            self.session.select_experiment(exp)
            cont = input(f"\n  Run full A/B readout for '{exp}'? [Y/n]: ").strip().lower()
            if cont != "n":
                self._run_module("experiment_analysis", "Full A/B Readout", experiment_name=exp)

        # Stage 6: Causal
        cont = input("\n  Run causal analysis? [Y/n]: ").strip().lower()
        if cont != "n":
            self._run_module("causal_analysis", "Causal Analysis")

        # Stage 7: Store learnings
        cont = input("\n  Open Learnings Repository? [Y/n]: ").strip().lower()
        if cont != "n":
            self._run_module("learnings_repository", "Learnings Repository")

        # Final intelligence summary
        print(f"\n  {'═' * w}")
        print(f"  {_bold('JOURNEY COMPLETE')}")
        print(f"  {'═' * w}")
        self._show_intelligence_panel()
        print(f"\n  Session saved. {len(self.session.execution_history)} modules run.")

    # ── Replay / Lineage ───────────────────────────────────────────────────────

    def _run_replay(self) -> None:
        history = self.session.execution_history
        if not history:
            print("\n  No runs in this session yet.")
            return
        print(f"\n  {'─' * 68}")
        print(f"  {_bold('SESSION LINEAGE')}")
        print(f"  {'─' * 68}")
        for rec in history:
            icon = "✅" if rec.ok else "❌"
            print(f"  {icon}  {rec.run_id}  {rec.module:<28}  {rec.elapsed_s:.2f}s")
            if rec.summary:
                print(f"       {_dim(rec.summary[:70])}")
        print(f"  {'─' * 68}")

    # ── Session info ───────────────────────────────────────────────────────────

    def _show_session_info(self) -> None:
        s = self.session
        print(f"\n  {'─' * 68}")
        print(f"  {_bold('SESSION')}: {s.session_id}  |  Client: {s.client_name}")
        print(f"  Created : {s.created_at[:19]}")
        print(f"  Active  : {s.last_active[:19]}")
        print(f"  Experiment: {s.active_experiment or '—'}")
        print(f"  Metrics   : {', '.join(s.active_metrics[:5]) or '—'}")
        print(f"  Runs      : {len(s.execution_history)}")
        print(f"  Memory    : {self.memory.experiment_count()} experiments stored")
        panel = self.bus.render_panel(max_items=6, width=self.W)
        if panel:
            print(f"\n{panel}")
        print(f"  {'─' * 68}")

    # ── Export ─────────────────────────────────────────────────────────────────

    def _export_session(self) -> None:
        import json as _json
        path = f"continum_session_export_{self.session.session_id}.json"
        try:
            data = {
                "session":  self.session.to_dict(),
                "insights": [
                    {"type": i.insight_type, "severity": i.severity,
                     "source": i.source_module, "message": i.message,
                     "detail": i.detail, "created_at": i.created_at}
                    for i in self.bus.all()
                ],
            }
            with open(path, "w") as f:
                _json.dump(data, f, indent=2, default=str)
            print(f"\n  ✅ Session exported → {path}")
        except Exception as e:
            print(f"\n  ❌ Export failed: {e}")

    # ── Shutdown ───────────────────────────────────────────────────────────────

    def _shutdown(self) -> None:
        self.session.save()
        print(f"\n  {_dim('Session saved. Goodbye.')}\n")

    # ── Prompt ─────────────────────────────────────────────────────────────────

    def _prompt(self, label: str = "") -> str:
        prefix = f"  {_cyan('CONTINUM')}"
        if label:
            prefix += f"/{label}"
        try:
            return input(f"{prefix} › ")
        except (KeyboardInterrupt, EOFError):
            return "Q"


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_shell(data_dir: str = "./sample_data") -> None:
    shell = ContinumShell(data_dir=data_dir)
    shell.run()


__all__ = [
    "ContinumShell",
    "run_shell",
    "MAIN_MENU",
    "PHASE_MODULES",
]
