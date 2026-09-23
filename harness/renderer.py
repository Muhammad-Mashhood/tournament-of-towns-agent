"""
renderer.py — Render translated problem sets as PDFs.

Two backends, tried in order:
  1. pdflatex (MiKTeX / TeX Live) — best math fidelity
  2. WeasyPrint with MathJax-style HTML — zero-dependency fallback

Output: PDF file written to output/<level>/<variant>/<filename>.pdf
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path("prompts/v1")
TEMPLATE_FILE = "latex_template.tex.jinja"
OUTPUT_BASE = Path("output")
PROMPT_VERSION = "v1"

# Ordinal suffixes
_ORDINAL = {1:"1st",2:"2nd",3:"3rd"}
_ORDINAL.update({n: f"{n}th" for n in list(range(4,21)) + list(range(24,31)) + list(range(34,100))})
_ORDINAL[21]="21st"; _ORDINAL[22]="22nd"; _ORDINAL[23]="23rd"
_ORDINAL[31]="31st"; _ORDINAL[32]="32nd"; _ORDINAL[33]="33rd"

_ROUND_LABELS = {"fall": "Fall (Autumn)", "spring": "Spring"}
_LEVEL_LABELS = {"junior": "Junior (Grades 8–9)", "senior": "Senior (Grades 10–11)"}
_VARIANT_LABELS = {"basic": "Basic (O-Level)", "advanced": "Advanced (A-Level)"}

_MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}


def _format_date(date_iso: str) -> str:
    """'2009-10-18' → '18 October 2009'"""
    parts = date_iso.split("-")
    if len(parts) == 3:
        return f"{int(parts[2])} {_MONTH_NAMES.get(parts[1], parts[1])} {parts[0]}"
    return date_iso


def _academic_year(tournament: int) -> str:
    start = 2009 + (tournament - 31)
    return f"{start}–{start+1}"


def _latex_safe_filter(text: str) -> str:
    """
    Escape LaTeX special characters in plain text, while preserving
    already-escaped math mode sections ($...$, $$...$$).
    
    Strategy: split on math delimiters, escape only non-math parts.
    """
    # Split by $...$ patterns (simple single-$ delimited inline math)
    # Use a regex that captures math regions
    parts = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    result_parts = []
    for i, part in enumerate(parts):
        if part.startswith("$"):
            # Math mode — pass through unchanged
            result_parts.append(part)
        else:
            # Plain text — escape LaTeX special chars
            # Order matters: backslash must be first
            escaped = part
            escaped = escaped.replace("\\", r"\textbackslash{}")
            escaped = escaped.replace("&", r"\&")
            escaped = escaped.replace("%", r"\%")
            escaped = escaped.replace("#", r"\#")
            escaped = escaped.replace("_", r"\_")
            escaped = escaped.replace("{", r"\{")
            escaped = escaped.replace("}", r"\}")
            escaped = escaped.replace("~", r"\textasciitilde{}")
            escaped = escaped.replace("^", r"\^{}")
            escaped = escaped.replace("<", r"\textless{}")
            escaped = escaped.replace(">", r"\textgreater{}")
            # Restore linebreaks as LaTeX paragraph breaks
            escaped = escaped.replace("\n\n", "\n\n\\noindent ")
            result_parts.append(escaped)
    return "".join(result_parts)


def _build_context(translated: Dict[str, Any], source_record) -> Dict[str, Any]:
    """Build the Jinja2 template context dict."""
    hdr = translated.get("header", {})
    tournament = hdr.get("tournament", source_record.tournament)
    round_name = hdr.get("round", source_record.round_name)
    date = hdr.get("date", source_record.date)
    level = source_record.level
    variant = source_record.variant
    scoring_note_raw = hdr.get("scoring_note", "")

    # Convert Russian scoring note to English if needed
    scoring_note = _translate_scoring_note(scoring_note_raw, level, variant)

    return {
        "tournament": tournament,
        "tournament_ordinal": _ORDINAL.get(tournament, f"{tournament}th"),
        "academic_year": _academic_year(tournament),
        "round_label": _ROUND_LABELS.get(round_name, round_name.title()),
        "date_display": _format_date(date),
        "level_label": _LEVEL_LABELS.get(level, level.title()),
        "variant_label": _VARIANT_LABELS.get(variant, variant.title()),
        "level_raw": hdr.get("level_raw", ""),
        "variant_raw": hdr.get("variant_raw", ""),
        "scoring_note": scoring_note,
        "source_url": source_record.source_url,
        "translation_model": translated.get("translation_model", "N/A"),
        "prompt_version": PROMPT_VERSION,
        "problems": translated.get("problems", []),
    }


def _translate_scoring_note(note: str, level: str, variant: str) -> str:
    """Convert Russian scoring note to English, or generate a default."""
    if not note:
        if variant == "basic":
            return "Score is based on the three problems with the best results."
        else:
            return "Score is based on the three problems with the best results; points for sub-parts of a problem are summed."
    # If Russian Cyrillic is detected, return clean idiomatic English
    if bool(re.search(r'[\u0400-\u04FF]', note)):
        if "пункт" in note or "суммир" in note:
            return "Score is based on the three problems with the best results; points for sub-parts of a problem are summed."
        return "Score is based on the three problems with the best results."
    return note


def _render_latex(context: Dict, out_path: Path) -> bool:
    """
    Render LaTeX template → compile to PDF via pdflatex.
    Returns True on success, False if pdflatex not available.
    """
    if not shutil.which("pdflatex"):
        return False

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
    )
    env.filters["latex_safe"] = _latex_safe_filter

    template = env.get_template(TEMPLATE_FILE)
    latex_source = template.render(**context)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "problem_set.tex"
        tex_path.write_text(latex_source, encoding="utf-8")

        # Run pdflatex twice (for cross-references like LastPage)
        for run in range(2):
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-output-directory", tmpdir,
                 str(tex_path)],
                capture_output=True, timeout=60, cwd=tmpdir
            )
            if result.returncode != 0 and run == 1:
                err_log = Path("logs/errors") / f"{out_path.stem}_pdflatex.log"
                err_log.parent.mkdir(parents=True, exist_ok=True)
                err_log.write_bytes(result.stdout + result.stderr)
                raise RuntimeError(
                    f"pdflatex failed for {out_path.stem}. "
                    f"Log: {err_log}"
                )

        pdf_tmp = Path(tmpdir) / "problem_set.pdf"
        if pdf_tmp.exists():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(pdf_tmp), str(out_path))
            return True

    return False


def _render_weasyprint(context: Dict, out_path: Path) -> bool:
    """
    Fallback: render HTML with MathML (via latex2mathml) → PDF via WeasyPrint.
    Returns True on success.
    """
    try:
        import weasyprint
        from latex2mathml import converter as l2m
    except ImportError as e:
        raise RuntimeError(f"WeasyPrint fallback not available: {e}")

    problems_html = ""
    for p in context["problems"]:
        pts_str = f" <span class='points'>[{p['points']} point{'s' if p['points'] != 1 else ''}]</span>" if p.get("points") else ""
        text_html = _text_to_html_with_math(p.get("text", ""), l2m)
        author_html = f"<div class='author'>({p['author']})</div>" if p.get("author") else ""
        note_html = f"<div class='note'>{p.get('note', '')}</div>" if p.get("note") else ""
        problems_html += f"""
        <div class="problem">
          <p><strong>Problem {p['number']}{pts_str}.</strong> {text_html}</p>
          {author_html}{note_html}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4; margin: 2.5cm 2.5cm 3cm; }}
  body {{ font-family: "Linux Libertine", Georgia, serif; font-size: 12pt; line-height: 1.5; }}
  h1 {{ font-size: 18pt; text-align: center; margin-bottom: 4pt; }}
  h2 {{ font-size: 14pt; text-align: center; margin-top: 2pt; }}
  .subtitle {{ text-align: center; font-style: italic; margin-bottom: 16pt; }}
  .problem {{ margin-bottom: 18pt; }}
  .problem strong {{ font-size: 12pt; }}
  .points {{ font-weight: normal; color: #444; }}
  .author {{ text-align: right; font-style: italic; font-size: 10pt; margin-top: -6pt; }}
  .note {{ color: #c00; font-size: 10pt; }}
  .footer {{ font-size: 9pt; color: #666; border-top: 1px solid #ccc; margin-top: 24pt; padding-top: 8pt; }}
  math {{ font-size: 110%; }}
</style>
</head>
<body>
<h1>Tournament of Towns</h1>
<h2>{context['tournament_ordinal']} Tournament, {context['academic_year']}</h2>
<div class="subtitle">
  {context['round_label']} Round &bull; {context['date_display']}<br>
  <strong>{context['level_label']}</strong> &bull; <strong>{context['variant_label']}</strong>
</div>
<p><em>{context['scoring_note']}</em></p>
<hr>
{problems_html}
<div class="footer">
  Source: {context['source_url']}<br>
  Translation: machine translation via {context['translation_model']} (prompt {context['prompt_version']}).
  Not an official edition. Solutions not included.
</div>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(str(out_path))
    return True


def _text_to_html_with_math(text: str, l2m_converter) -> str:
    """Convert inline $...$ math to MathML for WeasyPrint rendering."""
    parts = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    html_parts = []
    for part in parts:
        if part.startswith("$$") and part.endswith("$$"):
            latex = part[2:-2]
            try:
                mathml = l2m_converter.convert(latex, display="block")
                html_parts.append(mathml)
            except Exception:
                html_parts.append(f"<code>{part}</code>")
        elif part.startswith("$") and part.endswith("$"):
            latex = part[1:-1]
            try:
                mathml = l2m_converter.convert(latex, display="inline")
                html_parts.append(mathml)
            except Exception:
                html_parts.append(f"<code>{part}</code>")
        else:
            # Escape HTML chars in plain text
            import html as html_mod
            html_parts.append(html_mod.escape(part).replace("\n\n", "<br><br>"))
    return "".join(html_parts)


def _clean_unicode_for_pdf(text: str) -> str:
    """
    Clean up typographic ligatures, TeX extracted glyphs, and non-WinAnsi symbols
    so ReportLab renders them natively without ZapfDingbats box/tofu fallback ('■').
    """
    if not text:
        return ""
    
    # 1. TeX typographic ligatures -> standard ASCII letters
    ligatures = {
        '\ufb00': 'ff',
        '\ufb01': 'fi',
        '\ufb02': 'fl',
        '\ufb03': 'ffi',
        '\ufb04': 'ffl',
        '\ufb05': 'ft',
        '\ufb06': 'st',
    }
    for k, v in ligatures.items():
        text = text.replace(k, v)

    # 2. Math comparison and operators
    math_symbols = {
        '\u2a7d': '≤',  # ⩽ (slanted less-than-or-equal)
        '\u2a7e': '≥',  # ⩾ (slanted greater-than-or-equal)
        '\u2212': '-',  # mathematical minus
        '\u25e6': '°',  # white bullet (TeX \circ)
        '\u2218': '°',  # ring operator
    }
    for k, v in math_symbols.items():
        text = text.replace(k, v)
        
    return text


def _format_text_for_reportlab(text: str) -> str:
    """
    Convert text with LaTeX inline math into ReportLab Paragraph-compatible XML markup.
    """
    import html as html_mod
    if not text:
        return ""
    text = _clean_unicode_for_pdf(text)
    parts = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    out = []
    for part in parts:
        if part.startswith("$") and part.endswith("$"):
            raw_math = part.strip("$")
            out.append(_convert_latex_to_rl(raw_math))
        else:
            escaped = html_mod.escape(part)
            escaped = escaped.replace("\n\n", "<br/><br/>").replace("\n", " ")
            out.append(escaped)
    return "".join(out)


def _convert_latex_to_rl(math_str: str) -> str:
    import html as html_mod
    m = math_str
    replacements = [
        (r"\\times", "×"), (r"\\cdot", "·"),
        (r"\\le\b", "≤"), (r"\\leq\b", "≤"), (r"\\leqslant\b", "≤"),
        (r"\\ge\b", "≥"), (r"\\geq\b", "≥"), (r"\\geqslant\b", "≥"),
        (r"\\ne\b", "≠"), (r"\\neq\b", "≠"),
        (r"\\pm\b", "±"), (r"\\infty\b", "∞"),
        (r"\\approx\b", "≈"), (r"\\dots\b", "..."),
        (r"\\ldots\b", "..."), (r"\\cdots\b", "..."),
        (r"\\in\b", "∈"), (r"\\subset\b", "⊂"),
        (r"\\pi\b", "π"), (r"\\alpha\b", "α"),
        (r"\\beta\b", "β"), (r"\\gamma\b", "γ"),
        (r"\\circ\b", "°"),
    ]
    for pat, rep in replacements:
        m = re.sub(pat, rep, m)
    m = re.sub(r"\\underbrace\{([^{}]+)\}_\{([^{}]+)\}", r"\1 (\2)", m)
    m = re.sub(r"\\text\{([^{}]+)\}", r"\1", m)
    m = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1/\2)", m)
    m = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", m)
    m = html_mod.escape(m)
    m = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", m)
    m = re.sub(r"\^([a-zA-Z0-9+-])", r"<sup>\1</sup>", m)
    m = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", m)
    m = re.sub(r"_([a-zA-Z0-9+-])", r"<sub>\1</sub>", m)
    return f"<i>{m}</i>"


def _render_reportlab(context: Dict, out_path: Path) -> bool:
    """
    Native ReportLab PDF renderer — zero external system dependencies.
    Produces clean, publication-ready contest sheets with exact page numbering.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_decorations(num_pages)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def draw_page_decorations(self, page_count):
            self.saveState()
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            width, height = A4
            # Footer rule
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(2 * cm, 1.5 * cm, width - 2 * cm, 1.5 * cm)

            # Footer metadata
            meta = (
                f"Tournament of Towns Archive | {context['tournament_ordinal']} Tournament "
                f"({context['academic_year']}) | Unofficial English Edition | Solutions Omitted"
            )
            self.drawString(2 * cm, 1.1 * cm, meta)
            self.drawRightString(width - 2 * cm, 1.1 * cm, f"Page {self._pageNumber} of {page_count}")
            self.restoreState()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2.2 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        alignment=1,
        textColor=colors.HexColor('#334155'),
        spaceAfter=3,
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        alignment=1,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=12,
    )

    scoring_style = ParagraphStyle(
        'ScoringNote',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9.5,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#475569'),
    )

    prob_num_style = ParagraphStyle(
        'ProbNum',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4,
    )

    prob_body_style = ParagraphStyle(
        'ProbBody',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=4,
    )

    author_style = ParagraphStyle(
        'ProbAuthor',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=9.5,
        leading=13,
        alignment=2,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=12,
    )

    note_style = ParagraphStyle(
        'ProbNote',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#b91c1c'),
        spaceAfter=4,
    )

    elements = []

    # Headers
    elements.append(Paragraph("TOURNAMENT OF TOWNS", title_style))
    elements.append(Paragraph(f"{context['tournament_ordinal']} Tournament &bull; Academic Year {context['academic_year']}", subtitle_style))
    elements.append(Paragraph(
        f"{context['round_label']} Round &bull; {context['date_display']} &bull; "
        f"{context['level_label']} &bull; {context['variant_label']}",
        meta_style
    ))

    # Scoring Box
    scoring_text = _clean_unicode_for_pdf(context.get('scoring_note', ''))
    if scoring_text:
        scoring_p = Paragraph(f"<i>{scoring_text}</i>", scoring_style)
        scoring_table = Table([[scoring_p]], colWidths=[A4[0] - 4 * cm])
        scoring_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        elements.append(scoring_table)
        elements.append(Spacer(1, 14))

    # Problems
    for p in context.get("problems", []):
        prob_el = []
        pts_str = f" <font color='#64748b'>[{p['points']} point{'s' if p['points'] != 1 else ''}]</font>" if p.get("points") else ""
        prob_el.append(Paragraph(f"<b>Problem {p['number']}.</b>{pts_str}", prob_num_style))

        raw_body = p.get("text", "").strip()
        auth_str = p.get("author", "").strip()
        if auth_str:
            clean_auth = auth_str.strip("()")
            # If body text ends with (Author) or Author, remove it
            raw_body = re.sub(r'\s*\(' + re.escape(clean_auth) + r'\)\s*$', '', raw_body, flags=re.IGNORECASE)
            raw_body = re.sub(r'\s*' + re.escape(clean_auth) + r'\s*$', '', raw_body, flags=re.IGNORECASE)

        body_html = _format_text_for_reportlab(raw_body)
        prob_el.append(Paragraph(body_html, prob_body_style))

        if auth_str:
            clean_auth = _clean_unicode_for_pdf(clean_auth)
            auth_str = f"({clean_auth})"
            prob_el.append(Paragraph(auth_str, author_style))

        if p.get("note"):
            clean_note = _clean_unicode_for_pdf(p['note'])
            prob_el.append(Paragraph(clean_note, note_style))

        prob_el.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor('#e2e8f0'), spaceBefore=2, spaceAfter=8))
        elements.append(KeepTogether(prob_el))

    doc.build(elements, canvasmaker=NumberedCanvas)
    return True


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def render(translated: Dict[str, Any], source_record) -> Path:
    """
    Render the translated problem set to a PDF.
    Tries pdflatex first, then WeasyPrint, then native ReportLab.
    Returns the Path to the generated PDF.
    """
    context = _build_context(translated, source_record)

    out_dir = OUTPUT_BASE / source_record.level / source_record.variant
    filename = (
        f"{source_record.tournament}-{source_record.round_name}"
        f"-{source_record.date}"
        f"-{source_record.level}-{source_record.variant}.pdf"
    )
    out_path = out_dir / filename

    print(f"  [renderer] Rendering {out_path}")

    # Try pdflatex first
    try:
        if _render_latex(context, out_path):
            print(f"  [renderer] pdflatex OK -> {out_path}")
            return out_path
    except Exception as e:
        print(f"  [renderer] pdflatex error ({e}), trying fallback")

    # Try WeasyPrint second
    try:
        if _render_weasyprint(context, out_path):
            print(f"  [renderer] WeasyPrint OK -> {out_path}")
            return out_path
    except Exception as e:
        print(f"  [renderer] WeasyPrint not usable ({e}), using ReportLab")

    # Pure Python ReportLab
    if _render_reportlab(context, out_path):
        print(f"  [renderer] ReportLab OK -> {out_path}")
        return out_path

    raise RuntimeError(f"All rendering backends failed for {source_record.key}")
