---
name: module-registry
description: Use when adding, renaming, suggesting, or displaying any Continum analysis module or MatchView tool — when touching module names, phases, suggestions, the tool router, or copilot reply text. Enforces that the registry is the single source of truth for module names and phases.
---

# The registry is the only source of truth for module identity

Two registries define every runnable thing in Continum. Read names from them —
never hardcode a display name in a prompt, suggestion string, reply, or UI label.

- **MatchView tools** (the 6 primary, confirm-gated tools): `continum/orchestrator.py`
  → `MATCHVIEW_TOOLS` list of `MatchViewTool(key, module_name, description, target)`.
- **Specialised modules** (form-driven analysis): `continum/toolinterface.py`
  → `list_modules()` returns `{name, description, ...}`.
- The router (`continum/askrouter.py`) already builds its catalog from both via
  `_matchview_tools()` and `_module_catalog()`. Follow that pattern.

## Rules

1. **Renaming a module = edit the registry entry only.** After any rename, grep
   the codebase for the OLD literal and confirm zero stray copies:
   `grep -rniE "<old name>" continum --include=*.py` (and `dashboard.py`).
2. **Every suggestion names the exact module AND its phase.** Format:
   `Run **<module_name>** (<Phase> phase)`. The phase is the module's `group`
   in `continum/userui/templates/dashboard.py` (e.g. `group:'intelligence'`,
   `'planning'`, `'discovery'`, `'analysis'`). Never emit a generic fallback
   label.
3. **Never let a suggestion collapse to a single name.** If suggestion/reply
   code can output a fixed string like `"Campaign Insights"` regardless of the
   matched target, that's the bug — pull `module_name` from the matched
   `MatchViewTool`/module dict instead. `"Campaign Insights"` is the legitimate
   name of exactly ONE tool (`key="causal"`); seeing it everywhere means a
   hardcoded fallback, not a real match.
4. **A new module is not registered until it appears in `list_modules()` /
   `MATCHVIEW_TOOLS`** and the router can therefore select it. Adding a function
   without registering it creates an orphan (the codebase already carries ~19).

## Checklist before committing a name change
- [ ] Display name lives only in the registry entry.
- [ ] No stray literal of the old name (grep clean).
- [ ] Suggestions/replies read the name from the matched entry, not a constant.
- [ ] Phase label is derived from the dashboard `group`, shown alongside the name.
