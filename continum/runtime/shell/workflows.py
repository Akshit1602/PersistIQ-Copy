from __future__ import annotations

import logging
from typing import Any, Optional

from continum.runtime.shell.menu import JOURNEY_STEPS
from continum.runtime.shell.renderer import bold, cyan, dim, green, W

logger = logging.getLogger("continum.runtime.shell.workflows")


def run_journey(db, state, session, bus, memory, executor_fn, pick_fn) -> None:
    print(f"\n  {'═' * W}")
    print(f"  {bold('END-TO-END EXPERIMENTATION JOURNEY')}")
    print(f"  {'═' * W}")
    print(f"""
  Guided flow that mirrors the notebook's natural reasoning chain:

    Data Discovery    →   understand your data
    Opportunity Sizing →  quantify the revenue prize
    Power Calculation →   design the experiment correctly
    Experiment Brief  →   generate the hypothesis + spec
    A/B Readout       →   analyse the concluded experiment
    Causal Deep-Dive  →   validate and explain causality
    Learnings         →   store insights for the future

  Each step's output feeds the next automatically.
  You can skip any step.
""")

    if input("  Start the journey? [Y/n]: ").strip().lower() == "n":
        return

    for step_label, module_key, optional in JOURNEY_STEPS:
        print(f"\n  {'─' * 68}")

        # Experiment-selection gate before analysis steps
        if module_key in ("experiment_analysis", "causal_analysis") and not session.active_experiment:
            print(f"  {cyan('→')} Select an experiment for this step.")
            exp = pick_fn()
            if exp:
                session.select_experiment(exp)
                bus.emit("journey", f"Experiment selected: {exp}", "info", "info")
            else:
                print(f"  {dim('Skipping — no experiment selected.')}")
                continue

        cont = input(f"  Run: {bold(step_label)}? [Y/n]: ").strip().lower()
        if cont == "n":
            continue

        kw = {}
        if module_key in ("experiment_analysis",) and session.active_experiment:
            kw["experiment_name"] = session.active_experiment

        executor_fn(module_key, step_label, **kw)

    # Journey complete — show intelligence summary
    print(f"\n  {'═' * W}")
    print(f"  {bold('JOURNEY COMPLETE')}")
    print(f"  {'═' * W}")
    n = len(session.execution_history)
    print(f"  {green('✅')} {n} module(s) run.  Session saved.")

    panel = bus.render_panel(max_items=10, width=W)
    if panel:
        print(f"\n{panel}")


__all__ = ["run_journey"]
