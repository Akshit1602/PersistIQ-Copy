---
name: output-rendering
description: Use when changing where Copilot results render — module/tool output, the execution console, chat bubbles, or dashboard panes in continum/userui/templates/dashboard.py. Enforces one contract for result placement so module output shows as inline text and the console lives in the right pane.
---

# One contract for where results render

The dashboard (`continum/userui/templates/dashboard.py`) has multiple surfaces:
the Ask/chat pane, module config modals, the execution console, and dashboard
panes. Results must land in a predictable place.

## The contract

1. **Module / tool output renders as inline text in the dialog.** When a user
   clicks "Run module" for an Intelligence or Tools item, the result text appears
   in the chat/dialog flow — not only in a side console or a toast (issue #6).
   The execution console is for run *logs/progress*, not the final answer.
2. **The execution console lives in the RIGHT pane** (issue #3). Don't render run
   output in the left/Ask pane or full-width.
3. **Chat bubbles stay constrained** (`.chat-bubble` is `inline-block`,
   `max-width:85%`) — never full-width in the Ask history pane.
4. **Same render path for every module.** A new module reuses the existing
   result-rendering function; it must not invent its own placement.

## When wiring a new module result
- [ ] Final answer text → dialog/chat flow (inline), via the shared render helper.
- [ ] Progress/logs → right-pane execution console only.
- [ ] No full-width bubbles; no answer-only-in-console.
- [ ] Verify with `preview_screenshot` that output appears where the contract says.
