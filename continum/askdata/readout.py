"""
Readout library for the Continum Copilot — the "clean post-analysis flow".

Two sources feed a per-app library the Copilot can reference:
  * uploaded   — a PDF/DOCX/text the user drops in       (``add_uploaded``)
  * generated  — the PDF/text an analysis module produces (``add_generated``)

The Copilot answers questions grounded ONLY in these readouts (``answer``) and
can list/cite them. Text extraction is best-effort: PDF via ``pypdf``, DOCX via
``python-docx``, everything else decoded as UTF-8. Scanned/image-only PDFs (no
text layer) extract to empty text and are reported as such — OCR is a future
enhancement, not wired here.

State lives on the Flask ``app`` (``app._readouts``) like the AskData engine, so
it is process-scoped and survives across turns without a database.
"""
from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.askdata.readout")

_MAX_CHARS = 20000        # cap stored text per readout
_PROMPT_BUDGET = 12000    # total readout text folded into one answer prompt

# Extensions we treat as text-bearing readouts when auto-registering module output.
_GENERATED_EXTS = (".pdf", ".txt", ".md")


def extract_text(filename: str, data: bytes) -> str:
    """Best-effort text extraction from an uploaded/generated file's bytes."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            parts = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    pass
            return "\n".join(parts).strip()
        except Exception as e:
            logger.warning("PDF extract failed (%s): %s", filename, e)
            return ""
    if name.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except Exception as e:
            logger.warning("DOCX extract failed (%s): %s", filename, e)
            return ""
    # Plain-text-ish (txt/md/csv/json/log/vtt/srt/...).
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


# ── Store ────────────────────────────────────────────────────────────────────

def get_store(app) -> List[Dict[str, Any]]:
    s = getattr(app, "_readouts", None)
    if s is None:
        s = []
        app._readouts = s
    return s


def _add(app, name: str, text: str, source: str, **meta) -> Dict[str, Any]:
    store = get_store(app)
    text = (text or "")[:_MAX_CHARS]
    item: Dict[str, Any] = {
        "id": f"r{len(store) + 1}_{int(time.time()) % 100000}",
        "name": name,
        "source": source,                 # "uploaded" | "generated"
        "n_chars": len(text),
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "text": text,
    }
    item.update(meta)
    store.append(item)
    return item


def add_uploaded(app, filename: str, data: bytes) -> Dict[str, Any]:
    return _add(app, filename or "readout", extract_text(filename, data), "uploaded")


def add_generated(app, path: str, *, module: str = "", run_id: str = "") -> Optional[Dict[str, Any]]:
    """Register a module-generated output file (PDF/text) as a readout. Skips
    non-text artefacts (png/csv/json) and files already registered by path."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _GENERATED_EXTS:
        return None
    for it in get_store(app):
        if it.get("path") == path:
            return it
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:
        logger.warning("readout register read failed (%s): %s", path, e)
        return None
    text = extract_text(path, data)
    if not text:
        return None
    return _add(app, os.path.basename(path), text, "generated",
                path=path, module=module, run_id=run_id)


def add_generated_text(app, name: str, text: str, **meta) -> Optional[Dict[str, Any]]:
    """Register module-produced text (a run's result/narrative) as a readout —
    used when a run writes no PDF but still produces a referenceable result."""
    text = (text or "").strip()
    if len(text) < 20:
        return None
    return _add(app, name, text, "generated", **meta)


def result_to_text(result: Any, summary: str = "", module: str = "") -> str:
    """Render a module run's result into readable readout text (best-effort:
    dataclass / dict / object → 'key: value' lines, with nested scalars)."""
    import dataclasses
    lines: List[str] = []
    if module:
        lines.append(f"{module} readout")
    if summary and not summary.lstrip().startswith("["):   # skip bare key-list summaries
        lines.append(f"Summary: {summary}")
    d = None
    try:
        if dataclasses.is_dataclass(result) and not isinstance(result, type):
            d = dataclasses.asdict(result)
        elif isinstance(result, dict):
            d = result
        elif hasattr(result, "__dict__"):
            d = {k: v for k, v in vars(result).items() if not k.startswith("_")}
    except Exception:
        d = None
    if d:
        for k, v in d.items():
            if str(k).startswith("_"):
                continue
            if isinstance(v, (str, int, float, bool)) and str(v).strip():
                lines.append(f"- {k}: {v}")
            elif isinstance(v, dict):
                sub = {kk: vv for kk, vv in v.items() if isinstance(vv, (str, int, float, bool))}
                if sub:
                    lines.append(f"- {k}: " + ", ".join(f"{kk}={vv}" for kk, vv in list(sub.items())[:10]))
    elif result is not None:
        lines.append(str(result)[:1500])
    return "\n".join(lines).strip()


def list_readouts(app) -> List[Dict[str, Any]]:
    """Public, text-free view of the library (for the UI / list endpoint)."""
    return [{k: v for k, v in it.items() if k != "text"} for it in get_store(app)]


def clear(app) -> int:
    store = get_store(app)
    n = len(store)
    store.clear()
    return n


# ── Q&A grounding ──────────────────────────────────────────────────────────────

_QA_NOUNS = ("readout", "report", "the document", "this document", "the pdf",
             "uploaded", "the doc", "the analysis", "the writeup", "write-up")
_QA_VERBS = ("summar", "what ", "why ", "explain", "finding", "takeaway",
             "recap", "overview", "tl;dr", "tldr", "insight", "key point",
             "compare", "tell me about", "describe", "highlight", "conclu",
             "what's in", "whats in")
_ACTIONS = ("run ", "launch", "generate", "create", "produce", "build ",
            "activate", "deploy", "re-run", "rerun", "kick off")

# Report-language that implies a readout even without an explicit noun (these
# rarely describe a raw SQL dataset), so "what were the key findings?" routes to
# the readout. Deliberately excludes "summar"/"compare" — too data-ish.
_STRONG = ("finding", "takeaway", "tl;dr", "tldr", "conclusion", "conclude", "recap")


def is_readout_question(q: str) -> bool:
    """True when the question is asking ABOUT a readout (not asking to run one).
    Callers should also require a non-empty store before routing here."""
    ql = (q or "").lower()
    if any(a in ql for a in _ACTIONS):
        return False
    if any(s in ql for s in _STRONG):            # report-language -> readout
        return True
    return any(n in ql for n in _QA_NOUNS) and any(v in ql for v in _QA_VERBS)


def answer(app, question: str) -> Dict[str, Any]:
    """Answer a question grounded ONLY in the readout library."""
    store = get_store(app)
    if not store:
        return {"response": ("No readouts yet. Upload a readout (PDF/DOCX/text) or run an "
                             "analysis module, then ask me about it."),
                "mode": "readout", "used": []}

    # Most-recent-first, within the prompt budget.
    blocks: List[str] = []
    used: List[str] = []
    budget = _PROMPT_BUDGET
    for it in reversed(store):
        if budget <= 0:
            break
        chunk = it["text"][:budget]
        if not chunk:
            continue
        blocks.append(f"### Readout: {it['name']} ({it['source']})\n{chunk}")
        used.append(it["name"])
        budget -= len(chunk)

    if not blocks:
        return {"response": ("The readout(s) I have don't contain extractable text "
                             "(they may be scanned images). Try a text-based PDF or DOCX."),
                "mode": "readout", "used": []}

    context = "\n\n".join(blocks)
    prompt = (
        "You are Continum Copilot, embedded in an experimentation platform. Answer the "
        "user's question using ONLY the readout(s) below. Be concise and specific, and "
        "cite concrete figures/metrics (lift, p-values, segments, ROI) where present. "
        "If the answer is not in the readout(s), say so plainly. Format with markdown.\n\n"
        f"{context}\n\n---\nQuestion: {question}"
    )
    try:
        from continum.askdata.llm import get_chat_llm
        text = str(get_chat_llm().invoke(prompt).content).strip()
    except Exception as e:
        logger.warning("readout answer LLM failed: %s", e)
        text = ("I found the readout(s) but couldn't reach the language model to read them "
                "just now. Try again in a moment.")
    if used:
        text += "\n\n_Grounded in: " + ", ".join(used) + "_"
    return {"response": text, "mode": "readout", "used": used}


__all__ = [
    "extract_text", "get_store", "add_uploaded", "add_generated",
    "add_generated_text", "result_to_text",
    "list_readouts", "clear", "is_readout_question", "answer",
]
