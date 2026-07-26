from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("continum.userui.pdf")

# ── ReportLab (optional) ──────────────────────────────────────────────────────
try:
    from reportlab.lib.colors import HexColor, black, white  # noqa: F401
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,  # noqa: F401
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _PDF_OK = True
except ImportError:
    _PDF_OK = False

# Default brand palette
PDF_PALETTE = {
    "accent": "#7c3aed",
    "dark_bg": "#0f172a",
    "light_text": "#f1f5f9",
    "mid_text": "#94a3b8",
    "border": "#334155",
    "positive": "#22c55e",
    "negative": "#ef4444",
    "warning": "#f59e0b",
}

PAGE_W, PAGE_H = A4 if _PDF_OK else (595, 842)
MARGIN = 20 * (mm if _PDF_OK else 1)


def render_document_pdf(
    title: str,
    sections: Dict[str, str],
    output_path: Optional[str] = None,
    subtitle: str = "",
    metadata: Optional[Dict[str, str]] = None,
    accent_color: str = PDF_PALETTE["accent"],
) -> str:
    if output_path is None:
        # Defense-in-depth: a caller that forgets output_path must still land
        # under runtime_data/, never in the process's current working directory.
        import os as _os

        from continum.paths import new_run_dir

        output_path = _os.path.join(new_run_dir("report"), "report.pdf")
    if _PDF_OK:
        return _render_pdf(title, subtitle, sections, output_path, metadata, accent_color)
    else:
        return _render_txt(title, subtitle, sections, output_path, metadata)


# ─────────────────────────────────────────────────────────────────────────────
# PDF backend
# ─────────────────────────────────────────────────────────────────────────────


def _render_pdf(title, subtitle, sections, output_path, metadata, accent_color):
    try:
        accent = HexColor(accent_color)
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ContinumTitle",
            parent=styles["Title"],
            fontSize=22,
            leading=28,
            textColor=accent,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        )
        sub_style = ParagraphStyle(
            "ContinumSub",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=HexColor("#64748b"),
            spaceAfter=12,
        )
        h2_style = ParagraphStyle(
            "ContinumH2",
            parent=styles["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=14,
            spaceAfter=4,
            textColor=accent,
            fontName="Helvetica-Bold",
        )
        body_style = ParagraphStyle(
            "ContinumBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=4,
            textColor=HexColor("#1e293b"),
        )
        meta_style = ParagraphStyle(
            "ContinumMeta",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=HexColor("#475569"),
        )

        story = []

        # Title block
        story.append(Paragraph(_safe(title), title_style))
        if subtitle:
            story.append(Paragraph(_safe(subtitle), sub_style))
        story.append(HRFlowable(width="100%", thickness=2, color=accent, spaceAfter=8))

        # Metadata table
        if metadata:
            meta_data = [
                [Paragraph(k, meta_style), Paragraph(str(v), meta_style)]
                for k, v in metadata.items()
            ]
            meta_table = Table(meta_data, colWidths=["35%", "65%"])
            meta_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), HexColor("#f8fafc")),
                        ("TEXTCOLOR", (0, 0), (-1, -1), HexColor("#475569")),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        (
                            "ROWBACKGROUNDS",
                            (0, 0),
                            (-1, -1),
                            [HexColor("#f8fafc"), HexColor("#ffffff")],
                        ),
                        ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, HexColor("#e2e8f0")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(meta_table)
            story.append(Spacer(1, 10))

        # Generated timestamp
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        story.append(Paragraph(f"Generated: {ts}", meta_style))
        story.append(Spacer(1, 8))

        # Sections
        for heading, body in sections.items():
            if not body or not body.strip():
                continue
            story.append(Paragraph(_safe(heading), h2_style))
            story.append(
                HRFlowable(width="100%", thickness=0.5, color=HexColor("#e2e8f0"), spaceAfter=4)
            )
            for line in body.split("\n"):
                stripped = line.strip()
                if not stripped:
                    story.append(Spacer(1, 4))
                    continue
                # Bullet lines
                if stripped.startswith("- ") or stripped.startswith("• "):
                    stripped = "• " + stripped[2:]
                story.append(Paragraph(_safe(stripped), body_style))
            story.append(Spacer(1, 6))

        doc.build(story)
        abs_path = str(Path(output_path).resolve())
        logger.info("PDF written → %s", abs_path)
        return abs_path

    except Exception as e:
        logger.warning("PDF rendering failed (%s) — falling back to TXT", e)
        return _render_txt(title, subtitle, sections, output_path, metadata)


def _safe(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─────────────────────────────────────────────────────────────────────────────
# TXT fallback
# ─────────────────────────────────────────────────────────────────────────────


def _render_txt(title, subtitle, sections, output_path, metadata):
    txt_path = str(output_path).replace(".pdf", ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 72 + "\n")
        f.write(f"  {title}\n")
        if subtitle:
            f.write(f"  {subtitle}\n")
        f.write(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write("=" * 72 + "\n\n")
        if metadata:
            for k, v in metadata.items():
                f.write(f"  {k}: {v}\n")
            f.write("\n")
        for heading, body in sections.items():
            if not body or not body.strip():
                continue
            f.write("\n" + "-" * 72 + "\n")
            f.write(f"  {heading}\n")
            f.write("-" * 72 + "\n")
            f.write(body.strip() + "\n")
        f.write("\n" + "=" * 72 + "\n")
    abs_path = str(Path(txt_path).resolve())
    logger.info("TXT report written → %s", abs_path)
    return abs_path


__all__ = ["render_document_pdf", "PDF_PALETTE"]
