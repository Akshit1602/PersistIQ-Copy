import sys, os
from core.config import *
from core.state import *
from core.llm import *
from core.db import *
from utils.stats import *
from utils.reporting import *
from data.ingestion import *
from data.synthetic import *
from data.medallion import *
from modules.foundation import *
from modules.planning import *
from modules.live import *
from modules.post_experiment import *
from modules.causal_methods import *
from modules.deploy import *

db = get_db()
narrative_llm = TransformersClient(AGENT_CONFIG)

def run_agent():
    results = {}

    def cleanup_llm():
        try:
            if 'narrative_llm' in globals():
                print("\n🧹 Freeing LLM from memory...")
                narrative_llm.unload()
                print("✔ LLM unloaded.")
        except Exception as e:
            print(f"⚠️ Failed to unload LLM: {e}")

    PHASES = {
        "1": ("🛠️ Foundation (Data + Monitoring)", {
            "1": ("Schema Discovery & Mapping", run_schema_discovery),
            "2": ("Pipeline Health Monitor", run_pipeline_health),
            "3": ("Watchtower", run_watchtower),
        }),

        "2": ("📋 Planning (Experiment Design)", {
            "1": ("Experiment Brief + Method", run_brief_generator),
            "2": ("Opportunity Sizing", run_opportunity_sizing),
            "3": ("Power Calculator", run_power_calculator),
            "4": ("KPI & Tracking Plan", run_metrics_and_tracking),
            "5": ("Audience Selection", run_audience_selection),
        }),

        "3": ("🔴 Live (Monitoring)", {
            "1": ("Health Monitor", run_health_monitor),
            "2": ("Sequential Testing", run_sequential_testing),
        }),

        "4": ("✅ Post-Experiment (Analysis)", {
            "1": ("Causal Analysis", run_causal_analysis),
            "2": ("Simpson's Paradox Detector", run_simpsons_paradox_detector),
            "3": ("ROI Tracker", run_roi_tracker),
            "4": ("Learnings Repository", run_learnings_repository),
        }),

        "5": ("🚀 Deploy (Action Layer)", {
            "1": ("Uplift Modeller", run_uplift_modeller),
            "2": ("Decision Engine", run_decision_engine),
        }),

        "6": ("📐 Advanced Causal Methods", {
            "1": ("A/B Test (Statsig)", run_ab_test_analysis),
            "2": ("Pre-Post Analysis", run_pre_post_analysis),
            "3": ("Diff-in-Differences (TWFE)", run_did_analysis),
            "4": ("Interrupted Time Series", run_its_analysis),
            "5": ("Propensity Score Matching", run_psm_analysis),
            "6": ("Regression Discontinuity", run_rdd_analysis),
            "7": ("Synthetic Control (Enhanced)", run_synthetic_control_analysis),
        }),

        "7": ("📈 Counterfactual Forecasting", {
            "1": ("ARIMA Counterfactual", run_arima_analysis),
            "2": ("SARIMA Counterfactual", run_sarima_analysis),
            "3": ("BSTS Counterfactual", run_bsts_analysis),
            "4": ("Causal Impact Framework", run_causal_impact_analysis),
        }),
    }

    _mode = globals().get('CONTINUM_STATE', {}).get('mode', 'synthetic')
    _use_synth = globals().get('USE_SYNTHETIC_DATA', True)

    if not _use_synth and _mode != 'production_ready':
        print("\n🔌 PRODUCTION MODE DETECTED — BOOTSTRAP REQUIRED\n")
        print("Run bootstrap_from_connection(narrative_llm) first.\n")

        raw = input("Run bootstrap now? [Y/n]: ").strip().lower()
        if raw != 'n':
            bootstrap_from_connection(narrative_llm)

        cleanup_llm()
        return {}

    _required_helpers = (
        'ask_for_template',
        'build_llm_prompt_from_template',
        'parse_sections_from_llm_output',
        'render_document_pdf'
    )

    _missing = [h for h in _required_helpers if h not in globals()]
    if _missing:
        print("⚠️ Missing document helpers:", ", ".join(_missing))
        print("Re-run Cell 7b before PDF modules.\n")

    while True:

        print("\n" + "═"*60)
        print("🔬 CONTINUM PERSISTIQ — GUIDED MODE")
        print("═"*60)

        print("\nSelect a phase:\n")

        for k, (name, _) in PHASES.items():
            print(f"[{k}] {name}")

        print("[0] 🚀 Full Journey (All phases)")
        print("[x] Exit")

        phase = input("\n👉 Enter choice: ").strip().lower()

        if phase == "x":
            cleanup_llm()
            break

        results = {}

        if phase == "0":
            for pk, (pname, modules) in PHASES.items():
                print(f"\n\n━━━ {pname} ━━━\n")

                for mk, (mname, fn) in modules.items():
                    print(f"\n▶ Running: {mname}\n" + "-"*40)
                    results[mname] = fn(narrative_llm)

            cleanup_llm()
            break

        if phase not in PHASES:
            print("⚠️ Invalid phase selected.")
            continue

        phase_name, modules = PHASES[phase]

        while True:

            print("\n" + "─"*60)
            print(f"{phase_name}")
            print("─"*60)

            for k, (name, _) in modules.items():
                print(f"[{k}] {name}")

            print("[b] ⬅ Back to phases")
            print("[x] Exit")

            choice = input("\n👉 Select module: ").strip().lower()

            if choice == "b":
                break

            if choice == "x":
                cleanup_llm()
                return results

            if choice not in modules:
                print("⚠️ Invalid module.")
                continue

            name, fn = modules[choice]

            print("\n▶ Running:", name)
            print("─"*50)

            results[name] = fn(narrative_llm)

            print("\n✔ Completed:", name)

            next_step = input(
                "\nRun another module in this phase? [y/n]: "
            ).strip().lower()

            if next_step != "y":
                break

    print("\n✔ Session complete.")

    if results:
        print("Modules run:", ", ".join(results.keys()))

    return results


import os as _os

if _os.environ.get('CONTINUM_AUTORUN', '').lower() == 'true':
    results = run_agent()
else:
    print("✅ Dispatcher ready (guided mode).")
    print("Call run_agent() to start.")
    print("Or set CONTINUM_AUTORUN=true to auto-run.")

import difflib

def run_agent():

    results = {}


    MODULE_INDEX = {
        "schema discovery": run_schema_discovery,
        "pipeline health": run_pipeline_health,
        "watchtower": run_watchtower,

        "experiment brief": run_brief_generator,
        "opportunity sizing": run_opportunity_sizing,
        "power calculator": run_power_calculator,
        "kpi tracking": run_metrics_and_tracking,
        "audience selection": run_audience_selection,

        "health monitor": run_health_monitor,
        "sequential testing": run_sequential_testing,

        "causal analysis": run_causal_analysis,
        "simpson paradox": run_simpsons_paradox_detector,
        "roi tracker": run_roi_tracker,
        "learnings": run_learnings_repository,

        "uplift model": run_uplift_modeller,
        "decision engine": run_decision_engine,

        "ab test": run_ab_test_analysis,
        "pre post": run_pre_post_analysis,
        "diff in diff": run_did_analysis,
        "interrupted time series": run_its_analysis,
        "psm": run_psm_analysis,
        "rdd": run_rdd_analysis,
        "synthetic control": run_synthetic_control_analysis,

        "arima": run_arima_analysis,
        "sarima": run_sarima_analysis,
        "bsts": run_bsts_analysis,
        "causal impact": run_causal_impact_analysis,
    }

    HELP_TEXT = """
🔬 CONTINUM PERSISTIQ — SEARCH MODE

Type what you want to do:

Examples:
  • power calculator
  • roi analysis
  • synthetic control
  • experiment brief
  • causal impact

Commands:
  help  → show this message
  list  → show all modules
  exit  → quit
"""

    print(HELP_TEXT)

    while True:

        query = input("\n🔎 Search module: ").strip().lower()

        if query == "exit":
            break

        if query == "help":
            print(HELP_TEXT)
            continue

        if query == "list":
            print("\n📦 Available modules:\n")
            for k in sorted(MODULE_INDEX.keys()):
                print(" •", k)
            continue

        matches = difflib.get_close_matches(
            query,
            MODULE_INDEX.keys(),
            n=3,
            cutoff=0.4
        )


        if not matches:
            print("\n⚠️ No match found.")
            print("Try: 'power', 'roi', 'causal', 'synthetic control'")
            continue


        if len(matches) > 1:
            print("\n🤔 Multiple matches found:\n")
            for i, m in enumerate(matches, 1):
                print(f"[{i}] {m}")

            choice = input("\nSelect number or refine search: ").strip()

            if choice.isdigit() and 1 <= int(choice) <= len(matches):
                selected = matches[int(choice) - 1]
            else:
                continue
        else:
            selected = matches[0]

        print("\n▶ Running:", selected)
        print("─" * 50)

        fn = MODULE_INDEX[selected]
        results[selected] = fn(narrative_llm)

        print("\n✔ Completed:", selected)


        nxt = input("\nRun another? [y/n]: ").strip().lower()
        if nxt != "y":
            break

    print("\n✔ Session complete.")

    if results:
        print("\nModules executed:")
        for k in results:
            print(" •", k)

    free = input("\nFree LLM memory? [y/N]: ").strip().lower()
    if free == "y":
        narrative_llm.unload()

    return results



import os as _os

if _os.environ.get('CONTINUM_AUTORUN', '').lower() == 'true':
    results = run_agent()
else:
    print("✅ Search CLI ready.")
    print("Call run_agent() to start.")
    print("Or set CONTINUM_AUTORUN=true to auto-run.")