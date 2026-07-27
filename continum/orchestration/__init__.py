"""Orchestration — intent analysis + the path decider + LangGraph driver.

Decides, from the intent-analysis output (chatbot path) or a direct UI action
(manual path), which path to run: AskData SQL / Visualization / Insight, or an
ExpSuite tool-call. The AskData multi-agent flow is the LangGraph in
:mod:`.graph`; intent breakdown in :mod:`.intent`; routing + tool-calling in
:mod:`.matchview` / :mod:`.router`; guided flow in :mod:`.flow`; document Q&A
in :mod:`.readout`.

Folds the former ``orchestrator.py`` (MatchView tools), ``askrouter.py`` (LLM
route), ``askdata/engine.py`` (engine), ``askdata/flow.py``, ``askdata/readout.py``,
and ``intentAnalyser.py`` (intent breakdown — used only on the chatbot path;
manual experiment usage routes straight to the relevant ExpSuite module).

Every public function is importable directly from this package — e.g.
``from continum.orchestration import locate, format_question, answer`` — so
callers name a function, not a file; the submodules (``flow``, ``readout``,
``intent``, ``matchview``, ``router``) remain importable too for anything not
re-exported here.
"""

from __future__ import annotations

import logging
import threading
from io import StringIO
from typing import Any, Dict, List, Optional

import pandas as pd

from continum import active_provider
from continum.mapMeta import get_active_dataset_name, get_display_name, get_metadata

from . import flow, intent, readout
from .flow import (
    PHASE_PLAN,
    PhaseStep,
    format_confirm,
    format_question,
    init_slots,
    is_flow_trigger,
    is_no,
    is_restart,
    is_yes,
    locate,
    match_module,
    module_label,
    record_answer,
    render_overview,
    run_fields,
    suggest_next,
)
from .intent import Intent, Turn, analyse, detect_intent, extract_entities
from .matchview import (
    KIND_ANALYSIS,
    KIND_DATA,
    KIND_DEPLOY,
    MATCHVIEW_TOOLS,
    MatchViewTool,
    _summarise,
    _summarise_result,
    confirmation_message,
    deploy_warning,
    detect_tool,
    execute_tool,
    get_tool,
)
from .readout import (
    add_generated,
    add_generated_text,
    add_uploaded,
    answer,
    clear,
    extract_text,
    get_store,
    is_readout_question,
    list_readouts,
    result_to_text,
)
from .router import _extract_json, _validate, llm_route

logger = logging.getLogger("continum.orchestration")

_META_KEYWORDS = (
    "what can you do",
    "what do you do",
    "who are you",
    "what are you",
    "how do you work",
    "how do i use",
    "how to use",
    "what is askdata",
    "what is this",
    "what is continum",
    "what is persist",
    "help me",
    "your capabilities",
    "capabilities",
    "about you",
    "about yourself",
    "what dataset",
    "which dataset",
    "what data do you",
    "what tables",
    "explain yourself",
    "getting started",
    "how does this work",
)


def _is_meta_question(q: str) -> bool:
    ql = q.lower().strip()
    return any(k in ql for k in _META_KEYWORDS)


def _df_to_table(df: pd.DataFrame, limit: int = 50):
    if df is None or df.empty:
        return list(df.columns) if df is not None else [], []
    safe = df.head(limit).astype(object).where(pd.notnull(df.head(limit)), None)
    return list(df.columns), safe.to_dict(orient="records")


class ContinumEngine:
    """Drives the AskData LangGraph over the shared DuckDB (``app.db``).

    Replaces the former ``AskDataGraphEngine`` — DuckDB-native (no SQLite
    snapshot). The active dataset is chosen via ``ACTIVE_DATASET`` and read live
    by the graph nodes through :func:`continum.mapMeta.get_metadata`, so one
    compiled graph serves every dataset.
    """

    def __init__(self, app=None, dataset: Optional[str] = None, db=None):
        self.app = app
        self.dataset = dataset or get_active_dataset_name()
        self._db = db if db is not None else getattr(app, "db", None)
        self._graph = None
        self._lock = threading.Lock()
        self.history = ""
        self.structured_context = "{}"
        self.last_dataframe_json: Optional[str] = None
        self.provider = active_provider()

    # ── lazy graph compile ────────────────────────────────────────────────────
    def _ensure(self):
        if self._graph is not None:
            return
        with self._lock:
            if self._graph is not None:
                return
            if self._db is None:
                self._db = getattr(self.app, "db", None)
            if self._db is None:
                raise RuntimeError("Data warehouse isn't ready yet (DuckDB still booting).")
            from .graph import create_graph

            self._graph = create_graph(self._db)
            logger.info("Orchestrator AskData graph compiled (provider=%s)", self.provider)

    # ── introspection ──────────────────────────────────────────────────────────
    def list_tables(self) -> List[str]:
        if self._db is None:
            self._db = getattr(self.app, "db", None)
        try:
            return [r[0] for r in self._db.execute("SHOW TABLES").fetchall()]
        except Exception:  # noqa: BLE001
            return []

    def preview(self, limit: int = 5) -> Dict[str, Any]:
        meta = get_metadata(self.dataset)
        wanted = set(meta.get("tables", []))
        tables: List[dict] = []
        for t in self.list_tables():
            if wanted and t not in wanted:
                continue
            try:
                df = self._db.execute('SELECT * FROM "%s" LIMIT %d' % (t, int(limit))).df()
                n = self._db.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                cols, rows = _df_to_table(df, limit)
                tables.append({"table": t, "columns": cols, "rows": rows, "n_rows": n})
            except Exception as e:  # noqa: BLE001
                logger.warning("preview failed for table %s: %s", t, e)
        return {
            "dataset": self.dataset,
            "domain_context": meta.get("domain_context"),
            "tables": tables,
            "suggested_questions": meta.get("suggested_questions", []),
        }

    def reset_conversation(self):
        self.history = ""
        self.structured_context = "{}"
        self.last_dataframe_json = None

    # ── self-description ────────────────────────────────────────────────────────
    def about(self, q: str) -> Dict[str, Any]:
        from continum.AskData import about as _about

        text = _about(q, get_display_name(self.dataset))
        return {
            "response": text,
            "sql": None,
            "table": [],
            "columns": [],
            "visualizations": [],
            "error": None,
            "mode": "about",
            "provider": self.provider,
        }

    # ── main entry ──────────────────────────────────────────────────────────────
    def ask(self, question: str, ui_context: Optional[dict] = None) -> Dict[str, Any]:
        question = (question or "").strip()
        if not question:
            return {
                "response": "Ask me a question about the data.",
                "sql": None,
                "table": [],
                "columns": [],
                "error": None,
                "mode": "askdata",
                "provider": self.provider,
            }

        if _is_meta_question(question):
            return self.about(question)

        if active_provider() == "unconfigured":
            return {
                "response": "LLM not configured — please set GEMINI_API_KEY or Azure credentials in .env.",
                "sql": None,
                "table": [],
                "columns": [],
                "error": "unconfigured",
                "mode": "askdata",
                "provider": "unconfigured",
            }

        self._ensure()

        exp = (ui_context or {}).get("active_experiment")
        if self.dataset == "experiments" and exp:
            question = (
                question + "  (Unless I explicitly ask to compare across experiments, "
                f"only consider rows where experiment_name = '{exp}'.)"
            )

        initial_state = {
            "user_question": question,
            "refined_question": None,
            "history": self.history,
            "structured_context": self.structured_context,
            "plan": [],
            "current_step_index": 0,
            "sql_query": None,
            "dataframe_json": self.last_dataframe_json,
            "visualizations": None,
            "insight": None,
            "retry_count": 0,
            "error": None,
            "final_output": None,
        }

        with self._lock:
            try:
                result = self._graph.invoke(initial_state)
            except Exception as e:  # noqa: BLE001
                logger.exception("AskData graph invocation failed")
                return {
                    "response": f"Sorry — I hit an error answering that: {e}",
                    "sql": None,
                    "table": [],
                    "columns": [],
                    "error": str(e),
                    "mode": "askdata",
                    "provider": self.provider,
                }
            self.history = result.get("history", self.history)
            self.structured_context = result.get("structured_context", self.structured_context)

        final_output = result.get("final_output", {}) or {}
        sql_query = final_output.get("sql")
        dataframe_json = final_output.get("dataframe")
        viz = final_output.get("visualizations") or []
        insight = final_output.get("insight") or "No insight generated."

        columns, table = [], []
        if dataframe_json:
            self.last_dataframe_json = dataframe_json
            try:
                df = pd.read_json(StringIO(dataframe_json))
                columns, table = _df_to_table(df)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to parse result dataframe: %s", e)

        return {
            "response": insight,
            "sql": sql_query,
            "table": table,
            "columns": columns,
            "visualizations": viz,
            "error": None,
            "mode": "askdata",
            "provider": self.provider,
        }


def get_orchestrator(
    app=None, *, dataset: Optional[str] = None, rebuild: bool = False
) -> ContinumEngine:
    """Return the app-scoped orchestrator engine (cached on the Flask app)."""
    if app is not None:
        eng = getattr(app, "_orchestrator", None)
        if eng is None or rebuild:
            eng = ContinumEngine(app=app, dataset=dataset, db=getattr(app, "db", None))
            app._orchestrator = eng
        return eng
    return ContinumEngine(dataset=dataset)


# Backward-compatible name used across the UI (was continum.askdata.get_askdata_engine).
def get_askdata_engine(app=None, dataset: Optional[str] = None) -> ContinumEngine:
    return get_orchestrator(app, dataset=dataset)


__all__ = [
    # engine
    "ContinumEngine",
    "get_orchestrator",
    "get_askdata_engine",
    # intent (chatbot path only)
    "Intent",
    "Turn",
    "analyse",
    "detect_intent",
    "extract_entities",
    # matchview
    "MatchViewTool",
    "MATCHVIEW_TOOLS",
    "detect_tool",
    "get_tool",
    "confirmation_message",
    "deploy_warning",
    "execute_tool",
    "_summarise",
    "_summarise_result",
    "KIND_DATA",
    "KIND_ANALYSIS",
    "KIND_DEPLOY",
    # router
    "llm_route",
    "_extract_json",
    "_validate",
    # guided flow
    "PhaseStep",
    "PHASE_PLAN",
    "module_label",
    "is_flow_trigger",
    "is_restart",
    "is_yes",
    "is_no",
    "locate",
    "suggest_next",
    "render_overview",
    "match_module",
    "init_slots",
    "record_answer",
    "format_question",
    "format_confirm",
    "run_fields",
    # readout (document Q&A)
    "extract_text",
    "get_store",
    "add_uploaded",
    "add_generated",
    "add_generated_text",
    "result_to_text",
    "list_readouts",
    "clear",
    "is_readout_question",
    "answer",
    # sub-modules (still importable for anything not re-exported above)
    "flow",
    "readout",
    "intent",
]
