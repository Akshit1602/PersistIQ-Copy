"""
Lightweight README access for the AskData assistant — no torch / embeddings.

Earlier the project indexed READMEs with FAISS + sentence-transformers, whose
import chain pulls in ``torch``.  On machines without the right native runtime
(e.g. missing MS Visual C++ Redistributable on Windows) that import fails, which
would make "answer questions about yourself" impossible.

The bundled README(s) are small, so this module just reads them directly and
does simple keyword retrieval.  It always works, with or without the ML stack,
and with or without an LLM (it can return README text verbatim).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import List

_PKG = Path(__file__).resolve().parent


def _candidate_paths() -> List[Path]:
    # Bundled AskData README (about the assistant) first, then the platform README.
    out = [_PKG / "README.md"]
    try:
        repo_root = _PKG.parents[1]  # askdata → continum → <repo root>
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
    scored = sorted(_paragraphs(text),
                    key=lambda p: sum(p.lower().count(t) for t in terms),
                    reverse=True)
    out, total = [], 0
    for p in scored:
        if total + len(p) + 2 > max_chars:
            continue
        out.append(p)
        total += len(p) + 2
    return "\n\n".join(out) if out else text[:max_chars]


__all__ = ["get_readme_text", "get_readme_context"]
