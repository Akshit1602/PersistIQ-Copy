"""
Guards the module registry contract.

The frontend and backend each carry a module list, joined by module id. These
tests exist because a silent divergence between them is invisible at runtime:
the UI would show one name while the API reported another, and a module whose
execution_handler pointed at nothing would simply do nothing when run.
"""

import re
from pathlib import Path

import pytest
from continum.orchestration.tools.registry import all_experimentation_tools
from continum.registry import MODULE_REGISTRY, get_module, list_modules

FRONTEND_REGISTRY = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "moduleRegistry.ts"
)

# Matches both quote styles: label: 'Forecasting' and label: "Simpson's Paradox Checker"
_ENTRY = re.compile(r"""id: '([a-z-]+)', label: (?:'([^']*)'|"([^"]*)")""")

VALID_PHASES = {"foundation", "preplanning", "monitoring", "causal"}


def _frontend_modules() -> dict[str, str]:
    source = FRONTEND_REGISTRY.read_text(encoding="utf-8")
    return {m.group(1): (m.group(2) or m.group(3)) for m in _ENTRY.finditer(source)}


def test_registry_has_21_unique_modules():
    ids = [module.id for module in MODULE_REGISTRY]
    assert len(ids) == 21
    assert len(set(ids)) == 21, "duplicate module ids in the registry"


def test_every_phase_is_a_known_phase():
    # Catches the 'pre-planning' vs 'preplanning' class of typo, which would
    # silently drop a module out of any phase-filtered view.
    for module in MODULE_REGISTRY:
        assert module.phase in VALID_PHASES, f"{module.id} has unknown phase {module.phase!r}"


def test_module_ids_match_the_frontend_registry():
    frontend = _frontend_modules()
    backend = {module.id: module.title for module in MODULE_REGISTRY}
    assert set(backend) == set(
        frontend
    ), "module id sets diverged — the join key between UI and API is broken"


def test_module_titles_match_the_frontend_registry():
    frontend = _frontend_modules()
    drift = {
        module.id: (module.title, frontend[module.id])
        for module in MODULE_REGISTRY
        if module.id in frontend and module.title != frontend[module.id]
    }
    assert not drift, f"title drift between backend and frontend registries: {drift}"


def test_every_execution_handler_resolves_or_is_explicitly_unimplemented():
    """
    The gate that keeps a module from silently doing nothing: a handler must
    either name a tool the agent can really call, or say not_implemented out loud.
    """
    tool_names = {tool.name for tool in all_experimentation_tools}
    broken = [
        (module.id, module.execution_handler)
        for module in MODULE_REGISTRY
        if module.execution_handler != "not_implemented"
        and module.execution_handler not in tool_names
    ]
    assert not broken, f"execution_handler resolves to no registered tool: {broken}"


def test_list_modules_filters_by_phase():
    assert len(list_modules()) == 21
    causal = list_modules("causal")
    assert causal and all(module.phase == "causal" for module in causal)


@pytest.mark.parametrize("module_id", ["causal-did", "power-calculator", "simpsons-paradox"])
def test_get_module_round_trips(module_id):
    module = get_module(module_id)
    assert module is not None
    assert module.to_dict()["id"] == module_id


def test_get_module_returns_none_for_unknown_id():
    assert get_module("no-such-module") is None
