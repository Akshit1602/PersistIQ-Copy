"""
Flask-friendly wrapper around the AskData LangGraph workflow.

This replaces the upstream Streamlit ``app.py`` UI layer with a single
:class:`AskDataGraphEngine` that Continum's ``/api/copilot/ask`` endpoint can
call.  It:

  * builds an in-memory SQLite database from the active dataset's files,
  * compiles the LangGraph once and reuses it,
  * maintains multi-turn ``history`` / ``structured_context`` like the upstream
    Streamlit ``session_state``,
  * answers "about itself" / how-to questions from the bundled README(s) so the
    assistant can describe its own capabilities (README access), and
  * maps the graph's ``final_output`` to the JSON shape the Copilot pane renders
    (``response`` / ``sql`` / ``table`` / ``columns``).

Thread-safety: the in-memory SQLite connection is shared with
``check_same_thread=False`` and graph invocations are serialized with a lock
(LLM latency dominates, so this is not a throughput concern).
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from io import StringIO
from typing import Any, Dict, List, Optional

import pandas as pd

from .metadata import get_metadata, get_active_dataset_name
from . import llm as _llm

logger = logging.getLogger("continum.askdata.engine")

# Questions about the assistant itself / how to use the tool -> answer from README.
_META_KEYWORDS = (
    "what can you do", "what do you do", "who are you", "what are you",
    "how do you work", "how do i use", "how to use", "what is askdata",
    "what is this", "what is continum", "what is persist", "help me",
    "your capabilities", "capabilities", "about you", "about yourself",
    "what dataset", "which dataset", "what data do you", "what tables",
    "explain yourself", "getting started", "how does this work",
)


def _is_meta_question(q: str) -> bool:
    ql = q.lower().strip()
    return any(k in ql for k in _META_KEYWORDS)


def _df_to_table(df: pd.DataFrame, limit: int = 50):
    """Return (columns, rows) JSON-safe (NaN -> None)."""
    if df is None or df.empty:
        return list(df.columns) if df is not None else [], []
    safe = df.head(limit).astype(object).where(pd.notnull(df.head(limit)), None)
    return list(df.columns), safe.to_dict(orient="records")


class AskDataGraphEngine:
    def __init__(self, dataset: Optional[str] = None, db=None):
        import os
        # Make the chosen dataset authoritative for every graph node.
        self.dataset = dataset or get_active_dataset_name()
        os.environ["ACTIVE_DATASET"] = self.dataset

        self._duckdb = db          # DuckDB handle for source="duckdb" datasets (else None)
        self._conn: Optional[sqlite3.Connection] = None
        self._graph = None
        self._lock = threading.Lock()

        # Multi-turn conversation state (mirrors upstream Streamlit session_state).
        self.history = ""
        self.structured_context = "{}"
        self.last_dataframe_json: Optional[str] = None

        self.provider = _llm.active_provider()

    # ── Lazy setup ───────────────────────────────────────────────────────────

    def _build_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        meta = get_metadata(self.dataset)
        logger.info("Building AskData SQLite for dataset '%s' (%s)",
                    self.dataset, meta.get("domain_context"))
        # DuckDB-backed dataset: snapshot the Layer-1 view(s) into this SQLite so the
        # existing NL -> SQLite -> insight -> chart path works unchanged.
        if meta.get("source") == "duckdb":
            if self._duckdb is None:
                raise RuntimeError("Experiment data isn't ready yet (DuckDB still booting).")
            for table_name, sql in (meta.get("queries") or {}).items():
                df = self._duckdb.cursor().execute(sql).df()      # DuckDB -> DataFrame
                df.to_sql(table_name, conn, if_exists="replace", index=False)
            logger.info("Snapshotted %d DuckDB table(s) into AskData SQLite",
                        len(meta.get("queries") or {}))
            return conn
        for file_info in meta["files"]:
            path = file_info["path"]
            table_name = file_info["table"]
            fmt = file_info["format"]
            if fmt == "csv":
                df = pd.read_csv(path)
                if "date_col" in file_info:
                    date_col = file_info["date_col"]
                    date_format = file_info.get("date_format")
                    df[date_col] = pd.to_datetime(
                        df[date_col], format=date_format).dt.strftime("%Y-%m-%d")
            elif fmt == "excel":
                sheet_name = file_info.get("sheet_name", 0)
                df = pd.read_excel(path, sheet_name=sheet_name)
            else:
                logger.warning("Unsupported file format: %s", fmt)
                continue
            df.to_sql(table_name, conn, if_exists="replace", index=False)
        return conn

    def _ensure(self):
        if self._graph is not None:
            return
        with self._lock:
            if self._graph is not None:
                return
            from .graph_logic import create_graph
            self._conn = self._build_db()
            self._graph = create_graph(self._conn)
            logger.info("AskData graph compiled (provider=%s)", self.provider)

    # ── Introspection ──────────────────────────────────────────────────────────

    def list_tables(self) -> List[str]:
        self._ensure()
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [r[0] for r in cur.fetchall()]

    def preview(self, limit: int = 5) -> Dict[str, Any]:
        """Sample a few rows from every table — powers the data-view UI."""
        self._ensure()
        meta = get_metadata(self.dataset)
        tables: List[dict] = []
        for t in self.list_tables():
            try:
                df = pd.read_sql_query('SELECT * FROM "%s" LIMIT %d' % (t, int(limit)), self._conn)
                n = self._conn.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                cols, rows = _df_to_table(df, limit)
                tables.append({"table": t, "columns": cols, "rows": rows, "n_rows": n})
            except Exception as e:
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

    # ── README / self-description ────────────────────────────────────────────

    def about(self, q: str) -> Dict[str, Any]:
        """Public entry for 'about itself' / how-to questions (README-grounded)."""
        return self._answer_about_self(q)

    def _answer_about_self(self, q: str) -> Dict[str, Any]:
        meta = get_metadata(self.dataset)
        # Torch-free README reader (works even when the ML stack is unavailable).
        try:
            from .readme import get_readme_context
            ctx = get_readme_context(q) or ""
        except Exception as e:
            logger.warning("README context unavailable: %s", e)
            ctx = ""

        if ctx:
            prompt = (
                "You are Continum Copilot, a conversational data assistant embedded in the "
                "Continum experimentation platform. Answer the user's question about "
                "yourself and how to use you, using ONLY the documentation below. "
                "Be concise and friendly.\n\n"
                f"You are currently connected to the '{self.dataset}' dataset: "
                f"{meta.get('domain_context')}.\n\n"
                f"Documentation:\n{ctx[:3000]}\n\nQuestion: {q}"
            )
            try:
                text = str(_llm.get_chat_llm().invoke(prompt).content).strip()
            except Exception as e:
                logger.warning("LLM self-answer failed: %s", e)
                text = "Here's the most relevant documentation:\n\n" + ctx[:1200]
        else:
            text = (
                "I'm Continum Copilot, your natural-language data assistant. I translate your "
                "questions into SQL over the connected dataset, return the results, "
                "and explain what they mean. I'm currently connected to the "
                f"'{self.dataset}' dataset ({meta.get('domain_context')})."
            )
        return {
            "response": text, "sql": None, "table": [], "columns": [],
            "visualizations": [], "error": None, "mode": "about",
            "provider": self.provider,
        }

    # ── Main entry point ───────────────────────────────────────────────────────

    def ask(self, question: str, ui_context: Optional[dict] = None) -> Dict[str, Any]:
        question = (question or "").strip()
        if not question:
            return {"response": "Ask me a question about the data.", "sql": None,
                    "table": [], "columns": [], "error": None, "mode": "askdata",
                    "provider": self.provider}

        if _is_meta_question(question):
            return self._answer_about_self(question)

        if _llm.active_provider() == "unconfigured":
            return {
                "response": ("I need an OpenAI API key to query the data. Add "
                             "OPENAI_API_KEY to .streamlit/secrets.toml or .env and ask again."),
                "sql": None, "table": [], "columns": [], "error": "unconfigured",
                "mode": "askdata", "provider": "unconfigured",
            }

        self._ensure()

        # Per-experiment auto-scoping: when the experiments dataset is active and an
        # experiment is selected in the UI, softly bias SQL to it (cross-experiment
        # questions still work because the instruction is conditional).
        exp = (ui_context or {}).get("active_experiment")
        if self.dataset == "experiments" and exp:
            question = (question + "  (Unless I explicitly ask to compare across experiments, "
                        f"only consider rows where experiment_name = '{exp}'.)")

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
            except Exception as e:
                logger.exception("AskData graph invocation failed")
                return {"response": f"Sorry — I hit an error answering that: {e}",
                        "sql": None, "table": [], "columns": [], "error": str(e),
                        "mode": "askdata", "provider": self.provider}

            # Persist multi-turn state.
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
            except Exception as e:
                logger.warning("Failed to parse result dataframe: %s", e)

        # The chart spec is returned in `visualizations` and rendered client-side
        # by the Copilot pane (Plotly.js). No need to fold it into the text.

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


# ─────────────────────────────────────────────────────────────────────────────
# Flask app-scoped singleton helper
# ─────────────────────────────────────────────────────────────────────────────

def get_askdata_engine(app=None, dataset: Optional[str] = None) -> AskDataGraphEngine:
    """Return a cached engine. If ``app`` is given, cache it on the app object."""
    if app is not None:
        eng = getattr(app, "_askdata_graph", None)
        if eng is None:
            eng = AskDataGraphEngine(dataset=dataset, db=getattr(app, "db", None))
            app._askdata_graph = eng
        return eng
    return AskDataGraphEngine(dataset=dataset)


__all__ = ["AskDataGraphEngine", "get_askdata_engine"]
