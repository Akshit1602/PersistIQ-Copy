from __future__ import annotations
from typing import Dict, List, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────────────────────────────────────

# (key, label, route_key)
MAIN_MENU: List[Tuple[str, str, str]] = [
    ("0", "Full Journey  — end-to-end guided flow",   "journey"),
    ("1", "Discovery     — schema, validation, dims",  "discovery"),
    ("2", "Planning      — brief, sizing, power, KPIs","planning"),
    ("3", "Audience      — propensity scoring",        "audience"),
    ("4", "Monitoring    — health, sequential testing","monitoring"),
    ("5", "Analysis      — A/B, causal, post-exp",    "causal"),
    ("6", "Intelligence  — insights, memory, compare","intelligence"),
    ("C", "Compare       — side-by-side experiments", "compare"),
    ("F", "Fork Session  — branch from current state","fork"),
    ("A", "Ask Continum  — conversational reasoning", "ask"),
    ("R", "Replay        — lineage + execution log",  "replay"),
    ("S", "Session Info  — context + state",         "session"),
]

# ─────────────────────────────────────────────────────────────────────────────
# PHASE → MODULE MAPPING
# ─────────────────────────────────────────────────────────────────────────────

# (key, label, module_registry_key)
PHASE_MODULES: Dict[str, List[Tuple[str, str, str]]] = {
    "discovery": [
        ("1", "Schema Discovery & Mapping",    "schema_discovery"),
        ("2", "Data Validation",               "data_validation"),
        ("3", "Dimension Setup",               "dimension_setup"),
        ("4", "Pipeline Health Monitor",       "pipeline_health"),
        ("5", "Watchtower Anomaly Scan",       "watchtower"),
    ],
    "planning": [
        ("1", "Experiment Brief Generator",    "brief_generator"),
        ("2", "Opportunity Sizing",            "opportunity_sizing"),
        ("3", "Power Calculator",              "power_calculator"),
        ("4", "KPI & Tracking Plan",           "metrics_and_tracking"),
        ("5", "Audience Selection",            "audience_selection"),
    ],
    "audience": [
        ("1", "Audience Selection",            "audience_selection"),
        ("2", "Opportunity Sizing",            "opportunity_sizing"),
    ],
    "monitoring": [
        ("1", "Experiment Health Monitor",     "health_monitor"),
        ("2", "Sequential Testing (mSPRT)",    "sequential_testing"),
        ("3", "Pipeline Health",               "pipeline_health"),
    ],
    "causal": [
        ("1", "Full A/B Readout",              "experiment_analysis"),
        ("2", "Causal Analysis (7-method)",    "causal_analysis"),
        ("3", "Pre-Post Analysis",             "pre_post_analysis"),
        ("4", "Simpson's Paradox Detector",    "simpsons_paradox"),
        ("5", "ROI Tracker",                   "roi_tracker"),
        ("6", "Learnings Repository",          "learnings_repository"),
        ("7", "Uplift Modeller",               "uplift_modeller"),
        ("8", "Decision Engine",               "decision_engine"),
    ],
    "intelligence": [
        ("1", "Show Intelligence Panel",       "_panel"),
        ("2", "Warnings & Anomalies",          "_warnings"),
        ("3", "Recommendations",               "_recommendations"),
        ("4", "Cross-Experiment Memory",       "_memory"),
        ("5", "Export Session",                "_export"),
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# GUIDED JOURNEY STEPS
# ─────────────────────────────────────────────────────────────────────────────

# Ordered list of (step_label, module_key, optional)
JOURNEY_STEPS: List[Tuple[str, str, bool]] = [
    ("Data Discovery",        "schema_discovery",    True),
    ("Opportunity Sizing",    "opportunity_sizing",  True),
    ("Power Calculation",     "power_calculator",    True),
    ("Experiment Brief",      "brief_generator",     True),
    ("Full A/B Readout",      "experiment_analysis", True),
    ("Causal Deep-Dive",      "causal_analysis",     True),
    ("Learnings Repository",  "learnings_repository",True),
]

__all__ = ["MAIN_MENU", "PHASE_MODULES", "JOURNEY_STEPS"]
