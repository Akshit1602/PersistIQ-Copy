import re
import os
import pandas as pd
import numpy as np
from collections import OrderedDict
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# STRING UTILITIES — available to ALL modules
# ─────────────────────────────────────────────────────────────────────────────

def _strip_decorative_chars(text: str) -> str:
    """
    Remove common emojis and decorative Unicode symbols from generated text
    so saved business documents stay clean. Keeps basic punctuation, letters,
    digits, and standard separators.
    """
    if not text:
        return text
    emoji_pattern = re.compile(
        '['
        '\U0001F300-\U0001FAFF'
        '\U0001F600-\U0001F64F'
        '\U0001F680-\U0001F6FF'
        '\U0001F1E0-\U0001F1FF'
        '\U00002600-\U000027BF'
        '\U0001F900-\U0001F9FF'
        '\U00002B00-\U00002BFF'
        ']+',
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub('', text)
    replacements = {
        '═': '=', '━': '-', '─': '-', '│': '|',
        '╔': '=', '╗': '=', '╚': '=', '╝': '=',
        '╠': '=', '╣': '=', '╦': '=', '╩': '=', '╬': '=',
        '┌': '+', '┐': '+', '└': '+', '┘': '+',
        '├': '+', '┤': '+', '┬': '+', '┴': '+', '┼': '+',
        '•': '-', '·': '-', '◦': '-',
        '►': '>', '▶': '>', '◄': '<', '◀': '<',
        '✅': '[OK]', '✔': '[OK]', '❌': '[X]', '✘': '[X]',
        '⚠': '[!]', '⚠️': '[!]', '🚨': '[ALERT]',
    }
    for src_ch, dst in replacements.items():
        text = text.replace(src_ch, dst)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE-AWARE DOCUMENT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

from collections import OrderedDict
from datetime import datetime

# ── PDF engine (ReportLab) ───────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable, KeepTogether)
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

# ── Optional template readers (pypdf / python-docx) ──────────────────────────
try:
    from pypdf import PdfReader as _PdfReader
    _PDF_READ_OK = True
except ImportError:
    _PDF_READ_OK = False

try:
    import docx as _docx_mod
    _DOCX_READ_OK = True
except ImportError:
    _DOCX_READ_OK = False

DOC_GENERATOR_READY = _PDF_OK

PDF_PALETTE = {
    'primary':    '#1a3a8c',
    'accent':     '#4e9af1',
    'secondary':  '#f97316',
    'success':    '#22c55e',
    'text':       '#1a1a1a',
    'subtle':     '#6b7280',
    'card_bg':    '#f7f9fc',
    'rule':       '#d6dce5',
}


# ─── 1. Template ingestion ───────────────────────────────────────────────────

def _read_template_file(path):
    """Return raw text of a .txt / .md / .pdf / .docx template."""
    path = os.path.expanduser(path.strip().strip('"').strip("'"))
    if not os.path.isfile(path):
        raise FileNotFoundError('Template file not found: ' + path)
    ext = os.path.splitext(path)[1].lower()

    if ext in ('.txt', '.md', '.markdown', ''):
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    if ext == '.pdf':
        if not _PDF_READ_OK:
            raise RuntimeError('pypdf not available — install with: pip install pypdf')
        reader = _PdfReader(path)
        return '\n\n'.join((p.extract_text() or '') for p in reader.pages)

    if ext == '.docx':
        if not _DOCX_READ_OK:
            raise RuntimeError('python-docx not available — install with: pip install python-docx')
        d = _docx_mod.Document(path)
        chunks = []
        for para in d.paragraphs:
            txt = para.text
            style = (para.style.name or '').lower() if para.style else ''
            if 'heading' in style:
                level = 1
                m = re.search(r'(\d+)', style)
                if m:
                    try: level = max(1, min(6, int(m.group(1))))
                    except ValueError: pass
                chunks.append('#' * level + ' ' + txt)
            else:
                chunks.append(txt)
        return '\n'.join(chunks)

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def _extract_section_headers_from_template(raw):
    """Pull section headings out of a user-supplied template."""
    out, seen = [], set()
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            continue
        header = None

        m = re.match(r'^(#{1,3})\s+(.+?)\s*$', stripped)
        if m:
            header = m.group(2).strip().rstrip(':')
        elif (sum(1 for c in stripped if c.isalpha()) >= 3
              and stripped == stripped.upper()
              and any(c.isalpha() for c in stripped)
              and not stripped.startswith(('-', '*', '•'))):
            alpha = [c for c in stripped if c.isalpha()]
            if alpha and len(alpha) / max(len(stripped), 1) > 0.4:
                header = stripped.rstrip(':')
        elif re.match(r'^\d+[.)]\s+[A-Z]', stripped):
            header = re.sub(r'^\d+[.)]\s+', '', stripped).rstrip(':')
        elif (stripped.endswith(':') and stripped.count(':') == 1
              and len(stripped) <= 50 and stripped[0].isalpha()):
            core = stripped.rstrip(':')
            if re.match(r'^[A-Za-z][A-Za-z0-9 \-/&()]+$', core):
                header = core

        if not header:
            continue
        h_clean = re.sub(r'\s+', ' ', header).strip()
        if len(h_clean) < 3:
            continue
        if h_clean.lower() in ('yes', 'no', 'todo', 'tbd', 'example', 'note', 'notes'):
            continue
        key = h_clean.upper()
        if key not in seen:
            seen.add(key)
            out.append(h_clean)
    return out


def ask_for_template(doc_kind, default_sections):
    """
    Interactive prompt. Asks the user if they have a template to follow.
    Returns (sections_or_None, raw_template_text_or_None).
    """
    kind = (doc_kind or 'document').strip()
    print()
    print('  ' + '┄' * 70)
    print('  📐  Template check — ' + kind.upper())
    print('  ' + '┄' * 70)
    print('  Do you have a defined format / template for your ' + kind + '?')
    print('  You can upload a .txt, .md, .pdf, or .docx file and the platform')
    print('  will match its section structure. Press Enter or type N to use')
    print('  the built-in default layout.')
    print()

    preview = ', '.join(default_sections[:4])
    if len(default_sections) > 4:
        preview += f', … (+{len(default_sections) - 4} more)'
    print('  Default sections: ' + preview)
    print()

    ans = input('  ❓ Use a custom template? [y/N]: ').strip().lower()
    if ans not in ('y', 'yes'):
        print('  → Using default layout.')
        return None, None

    while True:
        raw_path = input('  📎 Enter path to template file (or blank to cancel): ').strip()
        if not raw_path:
            print('  → Using default layout.')
            return None, None
        try:
            raw = _read_template_file(raw_path)
        except Exception as e:
            print(f'     ⚠️  Could not read template: {e}')
            retry = input('     Try a different path? [Y/n]: ').strip().lower()
            if retry in ('n', 'no'):
                print('  → Falling back to default layout.')
                return None, None
            continue

        sections = _extract_section_headers_from_template(raw)
        if len(sections) < 2:
            print(f'     ⚠️  Only {len(sections)} section header(s) detected in that file.')
            print('     The template needs 2+ clear headings (markdown #, ALL CAPS, or "Title:")')
            retry = input('     Try a different file? [Y/n]: ').strip().lower()
            if retry in ('n', 'no'):
                print('  → Falling back to default layout.')
                return None, None
            continue

        print(f'\n  ✅ Detected {len(sections)} section(s) from your template:')
        for i, s in enumerate(sections, 1):
            print(f'     {i:>2}. {s}')
        confirm = input('\n  Use these sections? [Y/n]: ').strip().lower()
        if confirm in ('', 'y', 'yes'):
            return sections, raw
        print('  → Falling back to default layout.')
        return None, None


# ─── 2. Prompt builder ───────────────────────────────────────────────────────

def build_llm_prompt_from_template(role, context_block, sections_to_fill,
                                   content_guidance=None, style_notes=None):
    """Build a prompt that asks the LLM to produce exactly the listed sections."""
    header_bullets = '\n'.join('  - ' + s for s in sections_to_fill)

    blank_lines = []
    for s in sections_to_fill:
        blank_lines.append(s.upper())
        blank_lines.append('[Content for this section.]')
        blank_lines.append('')
    blank_template = '\n'.join(blank_lines).rstrip()

    default_style = (
        'Write in plain business language. Do not use emojis, icons, or '
        'decorative symbols. Do not wrap the output in code fences or '
        'markdown. For items with a "Field: value" structure (metrics, '
        'tracking events, etc.) keep each field on its own line — the '
        'renderer will format these as styled cards.'
    )
    style = default_style + ('\n' + style_notes if style_notes else '')

    guidance = ''
    if content_guidance:
        guidance = '\nREFERENCE MATERIAL (use only what fits):\n' + content_guidance.strip() + '\n'

    prompt = (
        role.strip() + '\n\n'
        + 'CONTEXT:\n' + context_block.strip() + '\n'
        + guidance + '\n'
        + 'You must produce a document with EXACTLY these sections, in this order:\n'
        + header_bullets + '\n\n'
        + 'STYLE:\n' + style + '\n\n'
        + 'Each section must start on its own line with its heading in UPPERCASE and\n'
        + 'nothing else on that line. Do not add extra sections. Do not renumber or\n'
        + 'reword the headings. Do not add a preamble before the first heading.\n\n'
        + 'Output the sections using this exact skeleton (replace the bracketed text\n'
        + 'with real content; keep the headings verbatim):\n\n'
        + blank_template + '\n'
    ).strip()
    return prompt


# ─── 3. Output parser ────────────────────────────────────────────────────────

def parse_sections_from_llm_output(raw, expected_sections):
    """Split LLM free-text output into a dict keyed by section name."""
    positions = []
    for header in expected_sections:
        pattern = re.compile(
            r'(?im)^\s*(?:#{1,6}\s+|\d+[.)]\s+|\*+\s*)?'
            + re.escape(header) + r'\s*:?\s*$'
        )
        m = pattern.search(raw)
        if m:
            positions.append((m.start(), m.end(), header))

    found_headers = {h for (_, _, h) in positions}
    for header in expected_sections:
        if header in found_headers:
            continue
        pattern = re.compile(re.escape(header), re.IGNORECASE)
        m = pattern.search(raw)
        if m:
            positions.append((m.start(), m.end(), header))

    positions.sort(key=lambda t: t[0])

    out = OrderedDict((h, '') for h in expected_sections)
    for i, (_, end, header) in enumerate(positions):
        next_start = positions[i+1][0] if i+1 < len(positions) else len(raw)
        content = raw[end:next_start].strip()
        content = '\n'.join(line.rstrip() for line in content.splitlines())
        content = re.sub(r'^\n+', '', content)
        out[header] = content

    if not any(out.values()) and expected_sections:
        out[expected_sections[0]] = raw.strip()

    return out


# ─── 4. PDF renderer ─────────────────────────────────────────────────────────

def _escape_pdf(s):
    if s is None: return ''
    return (str(s).replace('&', '&amp;')
                  .replace('<', '&lt;')
                  .replace('>', '&gt;'))


def _render_section_body(content, styles, accent_hex):
    """Turn section content into a list of ReportLab flowables."""
    style_body   = styles['body']
    style_bullet = styles['bullet']
    flowables    = []
    lines        = (content or '').splitlines()
    card_buffer, bullet_buffer, para_buffer = [], [], []

    def _flush_card():
        if not card_buffer: return
        rows = [
            [Paragraph('<b>' + _escape_pdf(lbl) + '</b>', style_body),
             Paragraph(_escape_pdf(val), style_body)]
            for (lbl, val) in card_buffer
        ]
        tbl = Table(rows, colWidths=[42*mm, 123*mm], hAlign='LEFT')
        tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), HexColor(PDF_PALETTE['card_bg'])),
            ('LINEBEFORE',    (0, 0), (0, -1),  2.2, HexColor(accent_hex)),
            ('BOX',           (0, 0), (-1, -1), 0.3, HexColor(PDF_PALETTE['rule'])),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        flowables.append(tbl)
        flowables.append(Spacer(1, 6))
        card_buffer.clear()

    def _flush_bullets():
        if not bullet_buffer: return
        for b in bullet_buffer:
            flowables.append(Paragraph('• ' + _escape_pdf(b), style_bullet))
        flowables.append(Spacer(1, 4))
        bullet_buffer.clear()

    def _flush_paras():
        if not para_buffer: return
        text = ' '.join(p.strip() for p in para_buffer if p.strip())
        if text:
            flowables.append(Paragraph(_escape_pdf(text), style_body))
        para_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            _flush_paras(); _flush_bullets(); _flush_card()
            continue
        if stripped.startswith(('- ', '* ', '• ')):
            _flush_paras(); _flush_card()
            bullet_buffer.append(stripped[2:].strip())
            continue
        m = re.match(r'^([A-Z][A-Za-z0-9 /()\-]{1,32}):\s+(.+)$', stripped)
        if m:
            _flush_paras(); _flush_bullets()
            card_buffer.append((m.group(1).strip(), m.group(2).strip()))
            continue
        if re.match(r'^[A-Z][A-Za-z0-9 /()\-]{1,32}:\s*$', stripped):
            _flush_paras(); _flush_bullets(); _flush_card()
            continue
        _flush_card(); _flush_bullets()
        para_buffer.append(stripped)

    _flush_card(); _flush_bullets(); _flush_paras()
    return flowables


def _write_plain_text_fallback(title, subtitle, sections, metadata, path):
    lines = ['=' * 72, title]
    if subtitle: lines.append(subtitle)
    lines += ['=' * 72, '']
    if metadata:
        for k, v in metadata.items(): lines.append(str(k) + ': ' + str(v))
        lines.append('')
    for sec_name, content in sections.items():
        lines.append('-' * 60)
        lines.append(sec_name.upper())
        lines.append('-' * 60)
        lines.append(content or '(no content)')
        lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def render_document_pdf(title, subtitle, sections, output_path,
                        metadata=None, accent_color=None):
    """Render a designed PDF document. Falls back to .txt if ReportLab missing."""
    if not _PDF_OK:
        fallback = os.path.splitext(output_path)[0] + '.txt'
        _write_plain_text_fallback(title, subtitle, sections, metadata, fallback)
        print('     (ReportLab not installed; wrote plain text fallback)')
        return fallback

    accent  = accent_color or PDF_PALETTE['accent']
    primary = PDF_PALETTE['primary']

    if not isinstance(sections, OrderedDict):
        sections = OrderedDict(sections.items() if hasattr(sections, 'items') else sections)

    def _draw_chrome(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFillColor(HexColor(accent))
        canvas_obj.rect(0, A4[1] - 6*mm, A4[0], 6*mm, stroke=0, fill=1)
        if doc.page > 1:
            canvas_obj.setFont('Helvetica', 9)
            canvas_obj.setFillColor(HexColor(PDF_PALETTE['subtle']))
            canvas_obj.drawString(18*mm, A4[1] - 13*mm, title[:80])
            canvas_obj.setStrokeColor(HexColor(PDF_PALETTE['rule']))
            canvas_obj.setLineWidth(0.4)
            canvas_obj.line(18*mm, A4[1] - 16*mm, A4[0] - 18*mm, A4[1] - 16*mm)
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.setFillColor(HexColor(PDF_PALETTE['subtle']))
        canvas_obj.drawString(18*mm, 12*mm,
                              'Generated by Continum PersistIQ')
        canvas_obj.drawRightString(A4[0] - 18*mm, 12*mm, 'Page ' + str(doc.page))
        canvas_obj.setStrokeColor(HexColor(PDF_PALETTE['rule']))
        canvas_obj.setLineWidth(0.4)
        canvas_obj.line(18*mm, 15*mm, A4[0] - 18*mm, 15*mm)
        canvas_obj.restoreState()

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=22*mm, bottomMargin=22*mm,
                            title=title, author='Continum PersistIQ')

    ss = getSampleStyleSheet()
    styles = {
        'title': ParagraphStyle('DocTitle', parent=ss['Heading1'],
                                fontName='Helvetica-Bold', fontSize=22,
                                textColor=HexColor(primary),
                                spaceAfter=4, leading=26),
        'subtitle': ParagraphStyle('DocSubtitle', parent=ss['Normal'],
                                   fontName='Helvetica', fontSize=11,
                                   textColor=HexColor(PDF_PALETTE['subtle']),
                                   spaceAfter=12, leading=14),
        'section': ParagraphStyle('SectionHead', parent=ss['Heading2'],
                                  fontName='Helvetica-Bold', fontSize=13,
                                  textColor=HexColor(accent),
                                  spaceBefore=16, spaceAfter=6, leading=16),
        'body': ParagraphStyle('Body', parent=ss['BodyText'],
                               fontName='Helvetica', fontSize=10,
                               textColor=HexColor(PDF_PALETTE['text']),
                               leading=14, spaceAfter=6),
        'bullet': ParagraphStyle('Bullet', parent=ss['BodyText'],
                                 fontName='Helvetica', fontSize=10,
                                 textColor=HexColor(PDF_PALETTE['text']),
                                 leading=14, leftIndent=14,
                                 bulletIndent=4, spaceAfter=3),
        'meta_key': ParagraphStyle('MetaKey', parent=ss['Normal'],
                                   fontName='Helvetica-Bold', fontSize=9,
                                   textColor=HexColor(PDF_PALETTE['subtle']),
                                   leading=12),
        'meta_val': ParagraphStyle('MetaVal', parent=ss['Normal'],
                                   fontName='Helvetica', fontSize=10,
                                   textColor=HexColor(PDF_PALETTE['text']),
                                   leading=13),
    }

    story = [Paragraph(_escape_pdf(title), styles['title'])]
    if subtitle:
        story.append(Paragraph(_escape_pdf(subtitle), styles['subtitle']))
    story.append(HRFlowable(width='100%', thickness=1.4,
                            color=HexColor(accent),
                            spaceBefore=2, spaceAfter=10))

    meta = dict(metadata or {})
    meta.setdefault('Generated', datetime.now().strftime('%d %b %Y · %H:%M'))
    meta_rows = [
        [Paragraph(_escape_pdf(str(k).upper()), styles['meta_key']),
         Paragraph(_escape_pdf(str(v)),         styles['meta_val'])]
        for (k, v) in meta.items()
    ]
    if meta_rows:
        meta_table = Table(meta_rows, colWidths=[35*mm, 130*mm], hAlign='LEFT')
        meta_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), HexColor(PDF_PALETTE['card_bg'])),
            ('BOX',           (0, 0), (-1, -1), 0.4, HexColor(PDF_PALETTE['rule'])),
            ('INNERGRID',     (0, 0), (-1, -1), 0.25, HexColor(PDF_PALETTE['rule'])),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 14))

    for sec_name, content in sections.items():
        content = (content or '').strip() or '(No content generated for this section.)'
        header_block = [
            Paragraph(_escape_pdf(sec_name.upper()), styles['section']),
            HRFlowable(width=60*mm, thickness=1.2,
                       color=HexColor(accent),
                       spaceBefore=-2, spaceAfter=6),
        ]
        body_flowables = _render_section_body(content, styles, accent)
        if body_flowables:
            story.append(KeepTogether(header_block + body_flowables[:1]))
            story.extend(body_flowables[1:])
        else:
            story.extend(header_block)
        story.append(Spacer(1, 6))

    doc.build(story, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)
    return output_path


if DOC_GENERATOR_READY:
    print('✅ Template-aware document generator ready')
    print('   helpers : ask_for_template · build_llm_prompt_from_template')
    print('             parse_sections_from_llm_output · render_document_pdf')
    print('   readers : pypdf={}  python-docx={}'.format(_PDF_READ_OK, _DOCX_READ_OK))
else:
    print('⚠️  ReportLab not installed — PDFs will fall back to .txt')
    print('   pip install reportlab pypdf python-docx   to enable full functionality')
