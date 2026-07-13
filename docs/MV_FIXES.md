# MatchView (MV) Copilot — Fix Tracker

Branch: `feat/llm-tool-router`  ·  Started: 2026-06-29  ·  **DO NOT PUSH** (per request)

Canonical tracker for the MV bug/cleanup list. The dashboard UI lives in
`continum/userui/templates/dashboard.py` (self-contained HTML/JS) and the backend
routes in `continum/userui/routes/api.py`. Run: `python -m continum.userui --port 5050 --data ./sample_data`.

Right-panel tabs (`#right-panel`): **Insights · Narrative · Ask AI · Evidence**.
Separate full-page **AI Copilot** section (`#section-copilot`). Both chat surfaces share
ONE conversation (`CHAT` state, `renderChat()` writes `#copilot-chat` + `#ask-history`).

## Status legend: ✅ done · 🔧 in progress · 🔎 investigated/documented · ⏳ queued (needs decision/large)

### A. MV Bugs (UI / UX — dashboard.py + small backend)
| # | Issue | Root cause | Status |
|---|-------|-----------|--------|
| A1 | Chat conversation bleeds into Insights/Narrative/Evidence tabs; "Ask AI" must be the only chat-enabled tab | `#tab-ask` has inline `style="display:flex"` which overrides `.rp-panel{display:none}` → the Ask pane is visible on EVERY tab | ✅ |
| A2 | Insights & Narrative very slow to update | only refreshed at bootstrap (+insights every 20s); not refreshed on tab switch | ✅ |
| A3 | Evidence original functionality lost | `renderEvidence()` is a no-op; copilot/ask doesn't surface a grounding/evidence chain to the tab | ✅ |
| A4 | Ask AI needs the UI elements the AI Copilot tab has | side pane lacked quick-action chips / parity | ✅ |
| A5 | Chat bubble spacing & margins | spacing tweaks in `.chat-msg`/`.chat-bubble` | ✅ |
| A6 | Visualizations + SQL + table must display (collapsible) | `_cpMsgHtml` rendered only `table`+`next_steps`, never `sql`/`visualizations` (backend already returns them) | ✅ |
| A7 | If experiment not selected → callout | no guard when a query needs an active experiment | ✅ |
| A8 | If call takes too long → error message | no client timeout on `/api/copilot/ask` fetch | ✅ |
| A9 | If tool calling enabled, describe what it will do | `confirmation_message()` didn't include the tool's `description` | ✅ |
| A10 | For every module, include a description when clicked | modules not in hardcoded `CONFIGS` fell back to "Run this module." | ✅ |
| A11 | Rein in info per question + faster pathing | extra `askrouter.llm_route` round-trip before answering; verbose AskData synthesis | ✅ pathing (LLM-route skipped on keyword tool match); answer-verbosity still open |

**Verification (A1–A10):** server booted clean (`/health` ok, db_ready, llm_loaded); browser-driven:
- A1: `#tab-ask` computed `display:none` on Insights/Narrative/Evidence, `flex` only on Ask AI.
- A6: a real data query rendered collapsibles **Result table (2 rows) · Visualization (Plotly bar) · SQL**; chart rendered, no console errors.
- A3: Evidence tab shows Question → Resolution path → SQL executed → Data grounded on (table) → Answer.
- A9: confirm card reads "It will **campaign / email performance analytics over the dataset**".
- A7: helper unit-tested (callout for scoped tool w/o experiment; none otherwise).
- A10: `/api/module-config/anomaly_synthesis` → real registry description (not "Run this module.").
- Guard: `continum/tests/test_mv_copilot_ui.py` (5 tests) + existing `test_routes.py` (47) all green.

**A11 note (why not done this pass):** the two latency sources are (1) the per-query LLM routing
call and (2) AskData's verbose final synthesis. Both are *behaviour* changes that can silently
regress routing/answer quality — per the one-change-with-eval rule they should land behind an
eval slice (route-accuracy + answer-length), not as a blind prompt edit. Recommended: add a
fast-path that skips `llm_route` when `detect_tool`/`_auto_mode` classify with high confidence,
and add a "concise vs full" answer length control to the AskData synthesis prompt — gated by evals.

### B. Investigations (answer + document)
| # | Question | Status |
|---|----------|--------|
| B1 | What are the intelligence-layer tools & other algorithmic tools; do they work; how | 🔎 (see `MV_INTELLIGENCE_LAYER.md`) |
| B2 | Where is the copilot library; where does module-run output save; surface into UI | 🔎 |
| B3 | Data view not in line with original data | 🔎 |
| B4 | Make any tool call run → open console / display output / save to output tab | ✅ |

### C. Restructure / Incremental (large — queued, several need decisions)
| # | Item | Status / note |
|---|------|---------------|
| C1 | More descriptive file naming | ⏳ |
| C2 | Statsig API connector | ⏳ needs Statsig API key + scope |
| C3 | Unstructured data support | ⏳ needs scope (PDF/doc ingestion vs free-text) |
| C4 | Move to Gemini models | ⏳ needs Gemini API key + provider decision |
| C5 | All panes collapsible (Snowflake-style) | ✅ (sidebar + right panel collapse/expand, persisted) |

### D. Follow-up round (2026-06-29, post-commit) — all ✅ verified
| # | Ask | What changed | Verified |
|---|-----|--------------|----------|
| D1 | Don't make a visualization when it doesn't make sense; prompt accordingly | `askdata/graph_logic.py visualization_node`: deterministic guard skips charts for empty / <2 rows / <2 cols / no-numeric results; LLM prompt now lists when to return `[]` (single value, yes/no, ID dump, table-is-enough) | scalar query "current overall IOR" → **0 charts** (only Result table + SQL); 2-row comparison still charts |
| D2 | Make generated output files accessible from an output folder | New canonical `OUTPUTS_DIR` (`runtime_data/outputs`, override `CONTINUM_OUTPUT_DIR`); execute worker copies every run's `_outputs` there (and writes a `.md` for text-only results); new `GET /api/outputs` lists the folder; `/api/file` whitelists it via `commonpath`; Output tab lists files with working **Open/download** links | ran health_monitor → `runtime_data/outputs/health_monitor_*.md` written; `/api/outputs` lists it; `/api/file` serves it (HTTP 200, text/markdown); Output tab shows it |
| D3 | Remove all "copilot library" references; use the outputs folder | Renamed user-facing strings + comments + docstrings across `api.py`, `dashboard.py`, `readout.py` ("Copilot library"/"to the library"/"readout library" → "outputs folder" / "saved outputs"). Internal `readout.py` module kept (still the chat-grounding store) but no longer surfaced as a "library" | grep: **no** "copilot library / to the library / readout library" left; only unrelated "Plotly.js library" remains |

## Discovered issue (feeds B4)
- Running an analysis module **from the chat** that uses a blocking `input()` (e.g. `causal_analysis`'s
  "Choose method [1-10]") raises `EOF when reading a line` in the request thread — it then falls back to
  AskData. Chat-invoked modules must run headless (no `input()`), or be wired through the SSE run/console
  (which already has the interactive `input()` modal). This is the core of B4 and should be done together.

## Momentum queues
- **now:** ✅ A1–A10, A11 (pathing), B4, C5 DONE + verified in-browser (DO NOT PUSH yet).
- **next:** A11 answer-verbosity ("concise vs full" control on AskData synthesis, behind an answer-length eval).
- **blocked (need a decision/key from you):** C2 Statsig API key + scope; C4 Gemini API key (you chose HOLD);
  C3 unstructured-data scope (you chose WAIT for scope).
- **improve:** ✅ `continum/tests/test_mv_copilot_ui.py`; consider persisting the readout library
  (`app._readouts`) to `runtime_data/` so Output survives restarts.
- **recurring:** boot + `/health` + `pytest continum/tests` after each change.

### B4 verification (in-browser)
- Confirming an **analysis/deploy** tool in chat (e.g. "is the experiment healthy?") now routes to the
  live execution console via `startModuleRun()` (shared with module cards): console showed
  `Running: Health Monitor` → `✅ health_monitor completed in 6.88s` → "📄 Readout added to the Copilot
  library"; the generated readout then appeared in the new **Output** nav tab. **Data** tools (e.g. Email
  Analytics) still answer inline in chat (table + chart + SQL). Fixes the silent in-request execution that
  hit `EOF when reading a line` on modules using `input()` (the console has the interactive input modal).

### C5 verification
- `togglePane('sb'|'rp')` sets `--sb-w`/`--rp-w` to `0px`, persists to localStorage, and shows a thin
  edge expander; restoring removes the class and the pane returns to its width.
- **Fix (post-review):** the collapse silently no-opped because `#app` had
  `transition:grid-template-columns` — Chromium won't interpolate a `var()`-driven track change next to a
  `1fr` track, so the column stuck at its old px width. Removed the transition (collapse is instant).
  Re-verified with real button clicks: sidebar 226↔1px, right panel 312↔1px; edge expanders restore.
