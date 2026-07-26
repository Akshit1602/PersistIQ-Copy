"""ExpSuite — the experimentation framework.

Mostly-algorithmic modules organised by lifecycle phase (``discovery``,
``planning``, ``monitoring``, ``analysis``, ``learnings_repository``) over a
shared ``stats`` kernel + ``artifacts`` contracts. Modules accept an injected
``llm`` (optional) and ``db`` (DuckDB); they are reached manually from the UI or
as chat tool-calls via the orchestrator. ``registry`` is the single dispatcher
(``run_module`` / ``list_modules``) — folded from the former ``toolinterface``.
"""

from .registry import (
    ModuleSpec,
    get_module,
    list_modules,
    register_module,
    run_module,
)

__all__ = [
    "ModuleSpec",
    "run_module",
    "list_modules",
    "get_module",
    "register_module",
]
