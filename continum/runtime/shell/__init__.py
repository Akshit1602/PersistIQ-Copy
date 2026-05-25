from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("continum.runtime.shell")


class ContinumShell:

    def __init__(self, data_dir: str = "./sample_data", session=None, verbose: bool = True):
        self.data_dir = data_dir
        self.verbose  = verbose
        self.db       = None
        self.state    = None
        self.datasets = {}

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
        from continum.runtime.shell.renderer import os_banner, W, green, red, dim
        from continum.runtime.recommendations import auto_recommend

        os_banner()
        print(f"  {dim('Booting Continum OS...')}\n")

        try:
            import duckdb
            from continum.app.loader import load_csvs, register_bronze, build_silver_layer, build_gold_layer
            from continum.api.bootstrap import bootstrap_from_connection

            self.console.info("Initialising analytical engine")
            self.db    = duckdb.connect(":memory:")
            self.state = bootstrap_from_connection(
                mode="duckdb", client_name=self.session.client_name, db=self.db
            )
            self.session.db    = self.db
            self.session.state = self.state

            self.console.info(f"Loading data from: {self.data_dir}")
            self.datasets = load_csvs(self.data_dir)
            register_bronze(self.db, self.datasets)
            build_silver_layer(self.db)
            build_gold_layer(self.db)

            self.bus.success("shell", f"Continum OS ready — {len(self.datasets)} datasets loaded")
            auto_recommend(session=self.session, bus=self.bus, memory=self.memory)

            # Narrative opening — makes the session feel alive from the start
            try:
                from continum.runtime.narrative import get_narrative
                nr = get_narrative(bus=self.bus, session=self.session, memory=self.memory)
                opening = nr.open_session()
                if opening:
                    print(f"\n  💭 {opening}")
            except Exception:
                pass

            print(f"\n  {green('✅')} Ready. {len(self.datasets)} tables loaded.")
            panel = self.bus.render_panel(max_items=6, width=72)
            if panel:
                print(f"\n{panel}")
            return True

        except Exception as e:
            print(f"\n  {red('❌')} Boot failed: {e}")
            logger.exception("Shell boot error")
            return False

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        if not self.boot():
            return

        from continum.runtime.shell.menu import MAIN_MENU
        from continum.runtime.shell.renderer import (
            bold, cyan, dim, W, menu_item, status_bar, divider, prompt
        )
        from continum.runtime.shell.commands import (
            pick_experiment, cmd_intelligence, cmd_replay, cmd_session_info,
        )
        from continum.runtime.shell.workflows import run_journey
        from continum.runtime.compare import run_compare

        def _exec(module_key, label, **kw):
            from continum.runtime.shell.executor import run_module
            return run_module(
                module_key, label,
                db=self.db, state=self.state,
                session=self.session, bus=self.bus, memory=self.memory,
                **kw,
            )

        def _pick():
            return pick_experiment(self.db, self.session)

        while True:
            exp    = self.session.active_experiment or "—"
            n_runs = len(self.session.execution_history)
            status_bar(exp, n_runs, self.bus.render_summary())

            for key, label, _ in MAIN_MENU:
                done = any(
                    r.ok for r in self.session.execution_history
                    if _ in (r.module, "")
                )
                menu_item(key, label)

            print(f"\n    {bold('[Q]')}  Quit")
            divider()

            choice = prompt().strip().upper()

            if choice in ("Q", "QUIT", "EXIT"):
                self._shutdown()
                break
            elif choice == "0":
                run_journey(self.db, self.state, self.session, self.bus,
                            self.memory, _exec, _pick)
            elif choice == "1":
                self._phase_menu("Discovery", "discovery", _exec)
            elif choice == "2":
                self._phase_menu("Planning", "planning", _exec)
            elif choice == "3":
                _exec("audience_selection", "Audience Selection")
            elif choice == "4":
                self._phase_menu("Live Monitoring", "monitoring", _exec)
            elif choice == "5":
                exp = _pick()
                if exp:
                    self.session.select_experiment(exp)
                self._phase_menu("Causal & Post-Experiment Analysis", "causal", _exec)
            elif choice == "6":
                cmd_intelligence(self.session, self.bus, self.memory)
            elif choice == "C":
                run_compare(self.db, self.session, self.bus)
            elif choice == "F":
                self._fork_session()
            elif choice == "A":
                self._ask_continum()
            elif choice == "R":
                cmd_replay(self.session)
            elif choice == "S":
                cmd_session_info(self.session, self.bus, self.memory)
            else:
                from continum.runtime.shell.renderer import yellow
                print(f"  {yellow('?')} Unknown option: {choice!r}")

    # ── Phase sub-menu ─────────────────────────────────────────────────────────

    def _phase_menu(self, phase_name: str, phase_key: str, executor_fn) -> None:
        from continum.runtime.shell.menu import PHASE_MODULES
        from continum.runtime.shell.renderer import bold, dim, divider, menu_item, prompt, W

        modules = PHASE_MODULES.get(phase_key, [])
        if not modules:
            return

        while True:
            print(f"\n  {'─' * 68}")
            print(f"  {bold(phase_name.upper())}")
            print(f"  {'─' * 68}")
            for key, label, module_key in modules:
                last = self.session.last_run(module_key)
                menu_item(key, label, done=bool(last and last.ok))

            print(f"\n    {bold('[B]')}  Back")
            print(f"  {'─' * 68}")

            choice = prompt(phase_name).strip().upper()
            if choice in ("B", "BACK", "Q"):
                break
            matched = next((m for m in modules if m[0] == choice), None)
            if matched:
                _, label, module_key = matched
                kw = {}
                if module_key in ("experiment_analysis",) and self.session.active_experiment:
                    kw["experiment_name"] = self.session.active_experiment
                executor_fn(module_key, label, **kw)
            else:
                from continum.runtime.shell.renderer import yellow
                print(f"  {yellow('?')} Unknown: {choice!r}")

    # ── Session fork ───────────────────────────────────────────────────────────

    def _fork_session(self) -> None:
        from continum.runtime.session import ExperimentSession
        from continum.runtime.shell.renderer import bold, cyan, dim, green, prompt, divider

        print(f"\n  {'─' * 68}")
        print(f"  {bold('FORK SESSION')}")
        print(f"  {'─' * 68}")
        print(f"  Creates a new session branch from the current state.")
        print(f"  The current session is preserved unchanged.")
        print(f"  Use this to explore an alternative analysis path.\n")

        name = prompt("Fork label (or Enter for auto)").strip()
        fork = self.session.fork(label=name or None)

        # Switch to the fork
        old_id = self.session.session_id
        self.session = fork
        self.session.db    = self.db
        self.session.state = self.state

        print(f"\n  {green('✅')} Forked from {dim(old_id)} → new session {cyan(fork.session_id)}")
        print(f"  {dim(fork.fork_description)}")
        divider()

    # ── Ask Continum ───────────────────────────────────────────────────────────

    def _ask_continum(self) -> None:
        from continum.runtime.ask import ContinumCopilot
        copilot = ContinumCopilot(session=self.session, bus=self.bus, memory=self.memory)
        copilot.interactive()

    # ── Shutdown ───────────────────────────────────────────────────────────────

    def _shutdown(self) -> None:
        from continum.runtime.shell.renderer import dim
        self.session.save()
        print(f"\n  {dim('Session saved. Goodbye.')}\n")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_shell(data_dir: str = "./sample_data") -> None:
    ContinumShell(data_dir=data_dir).run()


__all__ = ["ContinumShell", "run_shell"]
