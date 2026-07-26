"""AskData · InsightGenerator — short insights from the SQL result or ContextGraph.

* :func:`insight_node` — the LangGraph node that interprets the query's data
  result (what's happening / why / recommended actions), grounded in the dataset
  schema from :mod:`continum.mapMeta`.
* :func:`describe_result` — a one-line description when a full insight isn't needed.
* :func:`grounded_insight` — a short insight from arbitrary ContextGraph context
  (used when there's no fresh SQL result but there is prior context to interpret).
* :func:`about` / :func:`get_readme_context` — README-grounded self-description
  (folded from the former ``askdata/readme.py``), so the assistant can explain
  what it does. The chat model comes from :func:`continum.get_chat_llm`.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import List

import pandas as pd

from continum import get_chat_llm
from continum.mapMeta import get_metadata

logger = logging.getLogger("continum.AskData.InsightGenerator")


def _llm(passed=None):
    return passed if passed is not None else get_chat_llm()


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT NODE  (interpret the SQL result)
# ─────────────────────────────────────────────────────────────────────────────


def insight_node(state: dict, llm=None) -> dict:
    logger.info("Entering insight_node")
    llm = _llm(llm)
    user_question = state["user_question"]
    df_json = state.get("dataframe_json")
    metadata = get_metadata()
    domain_context = metadata["domain_context"]

    if not df_json:
        return {
            "insight": "No data available.",
            "current_step_index": state.get("current_step_index", 0) + 1,
        }

    df = pd.read_json(StringIO(df_json))
    table_info = metadata["table_info_combined"]
    table_descriptions = metadata.get("table_descriptions", {})

    analysis_focus = ""
    if "experimental" in domain_context.lower():
        analysis_focus = """
        When interpreting results for experimental testing:
        - Compare 'Treatment' vs 'Control' groups.
        - Look for incremental lift in GMV, Household Counts, or Orders.
        - Analyze performance differences across 'Acquisition' and 'Retention' cohorts.
        - Mention if the results suggest the campaign was successful based on the delta between groups.
        """

    insight_prompt = f"""
    You are a senior {domain_context}.
    Interpret the data results based on the User Question and the Database Schema.

    ### DATABASE SCHEMA:
    {table_info}
    {json.dumps(table_descriptions, indent=2)}

    ### USER QUESTION:
    {user_question}

    ### DATA RESULTS:
    {df.to_string()}

    {analysis_focus}

    Provide:
    What's happening
    Why it's happening
    Recommended business actions
    """

    response = llm.invoke(insight_prompt)
    return {
        "insight": response.content,
        "current_step_index": state.get("current_step_index", 0) + 1,
    }


def describe_result(df: pd.DataFrame, user_question: str, llm=None) -> str:
    """One-line description of a result set (used when no full insight is needed)."""
    llm = _llm(llm)
    if df is None or df.empty:
        return "No rows matched that query."
    prompt = f"""
    You are a helpful data assistant. Provide a one-line description of the results for the user's question.
    User Question: {user_question}
    Data:
    {df.head(10).to_string()}

    Return ONLY the one-line description.
    """
    return str(llm.invoke(prompt).content).strip()


def grounded_insight(context: str, user_question: str, llm=None) -> str:
    """A short insight grounded in ContextGraph context (no fresh SQL result)."""
    llm = _llm(llm)
    prompt = (
        "You are a senior analyst. Using ONLY the context below, give a short, direct "
        "answer to the question. If the context is insufficient, say so.\n\n"
        f"=== CONTEXT ===\n{context}\n\n=== QUESTION ===\n{user_question}"
    )
    return str(llm.invoke(prompt).content).strip()


# ─────────────────────────────────────────────────────────────────────────────
# README-GROUNDED SELF-DESCRIPTION  (folded from askdata/readme.py)
# ─────────────────────────────────────────────────────────────────────────────

_PKG = Path(__file__).resolve().parent


def _candidate_paths() -> List[Path]:
    out = [_PKG / "README.md"]
    try:
        repo_root = _PKG.parents[1]  # AskData → continum → <repo root>
        out.append(repo_root / "README.md")
    except Exception:
        pass
    seen, uniq = set(), []
    for p in out:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in seen and p.exists():
            seen.add(rp)
            uniq.append(p)
    return uniq


@lru_cache(maxsize=1)
def get_readme_text() -> str:
    parts = []
    for p in _candidate_paths():
        try:
            label = "AskData assistant" if p.parent == _PKG else "Continum platform"
            parts.append(f"# README — {label}\n\n" + p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n\n---\n\n".join(parts)


def _paragraphs(text: str) -> List[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def get_readme_context(query: str, max_chars: int = 3500) -> str:
    """Return the most relevant README text for ``query`` (simple keyword scoring)."""
    text = get_readme_text()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    terms = {w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 2}
    if not terms:
        return text[:max_chars]
    scored = sorted(
        _paragraphs(text), key=lambda p: sum(p.lower().count(t) for t in terms), reverse=True
    )
    out, total = [], 0
    for p in scored:
        if total + len(p) + 2 > max_chars:
            continue
        out.append(p)
        total += len(p) + 2
    return "\n\n".join(out) if out else text[:max_chars]


def about(question: str, dataset_display: str = "", llm=None) -> str:
    """README-grounded answer to 'what are you / how do I use you' questions."""
    ctx = ""
    try:
        ctx = get_readme_context(question) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("README context unavailable: %s", e)

    if ctx:
        prompt = (
            "You are Continum Copilot, a conversational data assistant embedded in the "
            "Continum experimentation platform. Answer the user's question about yourself "
            "and how to use you, using ONLY the documentation below. Be concise and friendly.\n\n"
            + (
                f"You are currently connected to the '{dataset_display}' dataset.\n\n"
                if dataset_display
                else ""
            )
            + f"Documentation:\n{ctx[:3000]}\n\nQuestion: {question}"
        )
        try:
            return str(_llm(llm).invoke(prompt).content).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM self-answer failed: %s", e)
            return "Here's the most relevant documentation:\n\n" + ctx[:1200]

    return (
        "I'm Continum Copilot, your natural-language data assistant. I translate your "
        "questions into SQL over the connected dataset, return the results, and explain "
        "what they mean."
    )


# Grounded-ask module (ask_v2) lives in ExpSuite; keep a thin proxy so the old
# ``run_ask`` symbol resolves for the registry without an import cycle.
def run_ask(*args, **kwargs):
    from continum.ExpSuite.analysis.ask_engine import run_ask as _f

    return _f(*args, **kwargs)


__all__ = [
    "insight_node",
    "describe_result",
    "grounded_insight",
    "about",
    "get_readme_context",
    "get_readme_text",
    "run_ask",
]
