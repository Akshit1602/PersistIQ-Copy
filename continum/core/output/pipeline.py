from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("continum.output")

# Windows-safe output directory: ~/continum_outputs (or env override)
_DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "continum_outputs")
OUTPUT_ROOT  = Path(os.environ.get("CONTINUM_OUTPUT_DIR", _DEFAULT_OUT))


def _run_dir(module_name: str, session_id: str = "default") -> Path:
    ts  = str(int(time.time()))[-6:]
    p   = OUTPUT_ROOT / session_id / f"{module_name}_{ts}"
    p.mkdir(parents=True, exist_ok=True)
    return p


class OutputPipeline:

    def __init__(self, module_name: str, session_id: str = "default"):
        self.module_name = module_name
        self.session_id  = session_id
        self.dir         = _run_dir(module_name, session_id)
        self.saved: List[str] = []

    def __enter__(self): return self
    def __exit__(self, *_): pass

    # ── JSON ──────────────────────────────────────────────────────────────────
    def save_json(self, name: str, data: Any) -> str:
        path = self.dir / f"{name}.json"
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=_json_default)
            self.saved.append(str(path))
            logger.debug("Saved JSON: %s", path)
        except Exception as e:
            logger.warning("JSON save failed (%s): %s", name, e)
        return str(path)

    # ── CSV ───────────────────────────────────────────────────────────────────
    def save_csv(self, name: str, df: pd.DataFrame) -> str:
        path = self.dir / f"{name}.csv"
        try:
            df.to_csv(path, index=False)
            self.saved.append(str(path))
        except Exception as e:
            logger.warning("CSV save failed (%s): %s", name, e)
        return str(path)

    # ── Matplotlib figure ─────────────────────────────────────────────────────
    def save_chart(self, fig, name: str, dpi: int = 150) -> str:
        path = self.dir / f"{name}.png"
        try:
            import matplotlib
            matplotlib.use("Agg")
            fig.savefig(str(path), dpi=dpi, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
            self.saved.append(str(path))
            try:
                import matplotlib.pyplot as plt
                plt.close(fig)
            except Exception:
                pass
        except Exception as e:
            logger.warning("Chart save failed (%s): %s", name, e)
        return str(path)

    # ── PDF ───────────────────────────────────────────────────────────────────
    def save_pdf(
        self,
        name:        str,
        title:       str,
        sections:    Dict[str, str],
        subtitle:    str = "",
        metadata:    Optional[Dict] = None,
        accent:      str = "#7c3aed",
    ) -> str:
        path = str(self.dir / f"{name}.pdf")
        try:
            from continum.documents.generator import render_document_pdf
            out = render_document_pdf(
                title=title, sections=sections,
                output_path=path, subtitle=subtitle,
                metadata=metadata or {}, accent_color=accent,
            )
            self.saved.append(out)
            print(f"  📄 Saved → {out}")
        except Exception as e:
            # Fallback: text file
            txt_path = path.replace(".pdf", ".txt")
            try:
                with open(txt_path, "w") as f:
                    f.write(f"{title}\n{'='*len(title)}\n")
                    if subtitle:
                        f.write(f"{subtitle}\n\n")
                    for k, v in sections.items():
                        f.write(f"\n{k}\n{'-'*len(k)}\n{v}\n")
                self.saved.append(txt_path)
                path = txt_path
                print(f"  📄 Saved (text fallback) → {txt_path}")
            except Exception as e2:
                logger.warning("PDF+TXT save failed: %s / %s", e, e2)
        return path

    # ── Text report ───────────────────────────────────────────────────────────
    def save_text(self, name: str, content: str) -> str:
        path = self.dir / f"{name}.txt"
        try:
            path.write_text(content, encoding="utf-8")
            self.saved.append(str(path))
        except Exception as e:
            logger.warning("Text save failed: %s", e)
        return str(path)

    # ── Finalize ──────────────────────────────────────────────────────────────
    def finalize(self, result: Dict) -> Dict:
        result["_outputs"] = self.saved
        result["_output_dir"] = str(self.dir)
        # Print summary
        if self.saved:
            print(f"\n  📁 {len(self.saved)} file(s) saved → {self.dir}")
            for f in self.saved:
                print(f"     {Path(f).name}")
        return result


def _json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return str(obj)
