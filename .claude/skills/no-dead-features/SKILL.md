---
name: no-dead-features
description: Use when adding or reviewing a UI button, control, model variant, or toggle in the Continum dashboard, or when asked to remove dead/non-functional features. Enforces wire-it-or-don't-ship-it and gives a safe removal checklist for orphans like ask_v2 and the "No, just answer" button.
---

# A control isn't done until it does observable work

The dashboard (`continum/userui/templates/dashboard.py`) registers buttons,
intelligence cards, and model variants. A control that no-ops, re-invokes
itself, or has no live handler must be **removed, not committed**.

Known live offenders (issues #2, #4):
- **"No, just answer"** button — `dashboard.py` ~line 1532 (`copilotDecline()`),
  pushes `'No — just answer'` into `CHAT.history` (~line 1627) but doesn't
  actually short-circuit to a plain answer. Either wire it to a real
  "answer-without-running" path or delete the button.
- **`ask_v2`** — registered as an intelligence card (`dashboard.py` ~line 774)
  and in `continum/toolinterface.py` ~line 582. If it does nothing distinct from
  `ask`, remove it.

## Rules

1. **Wire-or-cut.** Before committing a new control, confirm its handler produces
   an observable result (a reply, a rendered module, a state change). A button
   whose only effect is to call itself or append a chat line is dead.
2. **Removal is safe only after a reference sweep.** Before deleting a control:
   - `grep -rniE "<handler or key>" continum --include=*.py` and in `dashboard.py`
   - confirm no route in `continum/userui/routes/api.py` depends on it
   - confirm the router (`askrouter.py` / `toolinterface.list_modules`) doesn't
     select it as a target
3. **Prefer deletion over a disabled stub.** A greyed-out or self-calling control
   reads as "coming soon" and accumulates. Cut it; reintroduce when real.

## Removal checklist
- [ ] Handler/key grep returns only the definition you're deleting.
- [ ] No `api.py` route references it.
- [ ] Router can't route to it (`_module_catalog` / `MATCHVIEW_TOOLS`).
- [ ] App still boots and `/health` is ok after removal.
