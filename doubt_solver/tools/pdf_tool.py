import re

import markdown
from fpdf import FPDF
from fpdf.fonts import FontFace
from pygments import lex
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.lexers.special import TextLexer
from pygments.token import Token
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# ---- prose styling (write_html) -------------------------------------------
# Dark-slate headings (vs write_html's default red) + monospace inline code.
_TAG_STYLES = {
    "h1": FontFace(color=(30, 41, 59), size_pt=17, emphasis="BOLD"),
    "h2": FontFace(color=(30, 41, 59), size_pt=14, emphasis="BOLD"),
    "h3": FontFace(color=(51, 65, 85), size_pt=12, emphasis="BOLD"),
    "code": FontFace(family="courier", size_pt=10),
}

# ---- code-block styling (custom render) -----------------------------------
# Dracula-ish palette so fenced code renders like an IDE card.
_CODE_BG = (40, 42, 54)
_HEADER_BG = (33, 34, 44)
_CODE_DEFAULT = (248, 248, 242)
_GUTTER = (98, 114, 164)
_PALETTE = {
    Token.Comment: (98, 114, 164),
    Token.Keyword: (255, 121, 198),
    Token.Keyword.Constant: (189, 147, 249),
    Token.Name.Function: (80, 250, 123),
    Token.Name.Class: (139, 233, 253),
    Token.Name.Builtin: (139, 233, 253),
    Token.Name.Decorator: (80, 250, 123),
    Token.Name.Tag: (255, 121, 198),
    Token.Name.Attribute: (80, 250, 123),
    Token.String: (241, 250, 140),
    Token.Number: (189, 147, 249),
    Token.Operator: (255, 121, 198),
    Token.Literal: (241, 250, 140),
}

_FENCE = re.compile(r"(?ms)^[ \t]*`{3,}[ \t]*([\w+#.\-]*)[ \t]*\n(.*?)^[ \t]*`{3,}[ \t]*$")

# Unicode -> latin-1 fallbacks (fpdf core fonts are latin-1 only).
_REPLACEMENTS = {
    "'": "'", "'": "'", '"': '"', '"': '"',
    '—': '-', '–': '-', '…': '...', '•': '-',
    '©': '(c)', '®': '(r)', '™': '(tm)',
    'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'ε': 'epsilon',
    'ζ': 'zeta', 'η': 'eta', 'θ': 'theta', 'ι': 'iota', 'κ': 'kappa',
    'λ': 'lambda', 'μ': 'mu', 'ν': 'nu', 'ξ': 'xi', 'ο': 'omicron',
    'π': 'pi', 'ρ': 'rho', 'σ': 'sigma', 'τ': 'tau', 'υ': 'upsilon',
    'φ': 'phi', 'χ': 'chi', 'ψ': 'psi', 'ω': 'omega',
    'Δ': 'Delta', 'Θ': 'Theta', 'Λ': 'Lambda', 'Σ': 'Sigma',
    'Φ': 'Phi', 'Ψ': 'Psi', 'Ω': 'Omega', 'Π': 'Pi',
    '±': '+/-', '×': 'x', '÷': '/', '≈': 'approx', '≠': '!=',
    '≤': '<=', '≥': '>=', '∞': 'infinity', '√': 'sqrt',
    '∑': 'sum', '∏': 'product', '∂': 'partial', '∫': 'integral',
    '°': 'deg', '²': '^2', '³': '^3', '→': '->', '←': '<-',
}


def _sanitize(text: str) -> str:
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    # Anything still outside latin-1 would crash rendering; drop it safely.
    return text.encode("latin-1", "replace").decode("latin-1")


def _repair_fences(md: str) -> str:
    """Force sloppy LLM code fences onto their own lines so they parse as blocks.

    Models often jam code onto the fence line (```js console.log()) or stick the
    closing fence at the end of a code line; without this the whole block
    degrades to inline text in a justified paragraph.
    """
    md = re.sub(r"(\S)[ \t]*(`{3,})", r"\1\n\2", md)  # code before a fence
    md = re.sub(r"(?m)^([ \t]*`{3,}[A-Za-z0-9+#._-]*)[ \t]+(\S.*)$", r"\1\n\2", md)  # opener
    return md


def _token_color(t):
    while t is not Token:
        if t in _PALETTE:
            return _PALETTE[t]
        t = t.parent
    return _CODE_DEFAULT


def _lexer(lang, code):
    if lang:
        try:
            return get_lexer_by_name(lang)
        except Exception:
            pass
    try:
        return guess_lexer(code)
    except Exception:
        return TextLexer()


def _colored_lines(code, lexer):
    """code -> list of logical lines, each a list of (char, rgb)."""
    lines, cur = [], []
    for ttype, val in lex(code, lexer):
        col = _token_color(ttype)
        for ch in val:
            if ch == "\n":
                lines.append(cur)
                cur = []
            elif ch == "\t":
                cur.extend((" ", col) for _ in range(4))
            else:
                cur.append((ch, col))
    lines.append(cur)
    return lines


def _draw_code_block(pdf, lang, code):
    """Render a fenced block as a dark IDE-style card: gutter line numbers,
    syntax highlighting, soft-wrap of long lines, page-break aware."""
    code = code.rstrip("\n")
    logical = _colored_lines(code, _lexer(lang, code))

    line_h = 4.1
    pad = 3.0
    pdf.set_font("courier", size=8)
    char_w = pdf.get_string_width("0")  # monospace: every glyph same width

    x0, x1 = pdf.l_margin, pdf.w - pdf.r_margin
    n_digits = max(2, len(str(len(logical))))
    gutter_w = pad + n_digits * char_w + 2
    code_x = x0 + gutter_w
    code_w = x1 - code_x - pad
    max_chars = max(4, int(code_w / char_w))
    bottom = pdf.h - pdf.b_margin

    def strip(y, bg):
        pdf.set_fill_color(*bg)
        pdf.rect(x0, y, x1 - x0, line_h, style="F")

    def fits(y):
        if y + line_h > bottom:
            pdf.add_page()
            return pdf.t_margin
        return y

    y = pdf.get_y() + 2
    # header bar with language label
    y = fits(y)
    strip(y, _HEADER_BG)
    if lang:
        pdf.set_text_color(*_GUTTER)
        pdf.text(code_x, y + line_h - 1.2, lang.lower())
    y += line_h
    y = fits(y); strip(y, _CODE_BG); y += line_h * 0.5  # top padding

    for i, line in enumerate(logical, 1):
        chunks = [line[j:j + max_chars] for j in range(0, len(line), max_chars)] or [[]]
        for k, chunk in enumerate(chunks):
            y = fits(y)
            strip(y, _CODE_BG)
            baseline = y + line_h - 1.2
            if k == 0:
                pdf.set_text_color(*_GUTTER)
                num = str(i)
                pdf.text(code_x - pad - len(num) * char_w, baseline, num)
            x = code_x
            run, run_col = "", None
            for ch, col in chunk:
                if col != run_col and run:
                    pdf.set_text_color(*run_col)
                    pdf.text(x, baseline, run)
                    x += len(run) * char_w
                    run = ""
                run_col = col
                run += ch
            if run:
                pdf.set_text_color(*run_col)
                pdf.text(x, baseline, run)
            y += line_h

    y = fits(y); strip(y, _CODE_BG); y += line_h * 0.5  # bottom padding
    pdf.set_y(y + 2)
    pdf.set_text_color(0)


def _write_prose(pdf, text):
    if not text.strip():
        return
    pdf.set_font("helvetica", size=12)
    pdf.set_text_color(0)
    html = markdown.markdown(text, extensions=["tables", "sane_lists"])
    pdf.write_html(html, tag_styles=_TAG_STYLES)


def _render_body(pdf, md):
    """Prose via write_html; fenced code via the custom IDE-card renderer."""
    pos = 0
    for m in _FENCE.finditer(md):
        _write_prose(pdf, md[pos:m.start()])
        _draw_code_block(pdf, m.group(1), m.group(2))
        pos = m.end()
    _write_prose(pdf, md[pos:])


async def generate_pdf(title: str, content: str, tool_context: ToolContext) -> dict:
    """Renders a Markdown explanation into a styled, downloadable PDF artifact.

    Use this only when the student explicitly asks for downloadable notes, a
    PDF, or something to save/print. Pass `content` as Markdown — the tool
    formats it into a clean A4 document: ## headings become section headings,
    fenced ```code``` blocks render as dark IDE-style cards with line numbers
    and syntax highlighting, `| tables |` become real tables, and - / 1. lists
    render as proper bulleted/numbered lists.

    Args:
        title: Short title for the PDF (shown centered on the first page,
            and used as the filename).
        content: The full explanation as Markdown. For code, use fenced blocks
            with a language, e.g. ```python ... ``` — the fence must be on its
            own line.

    Returns:
        dict with 'status' and the artifact 'filename' the student can download.
    """
    safe_title = _sanitize(title)
    body_md = _repair_fences(_sanitize(content))

    pdf = FPDF(format="A4")
    pdf.set_margins(left=25, top=20, right=25)  # ~1 inch
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Centered title + rule.
    pdf.set_font("helvetica", "B", 22)
    pdf.multi_cell(0, 10, safe_title, align="C")
    pdf.ln(3)
    y = pdf.get_y()
    pdf.set_draw_color(180)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(6)

    _render_body(pdf, body_md)

    pdf_bytes = bytes(pdf.output())

    safe_name = "".join(c if c.isalnum() else "_" for c in safe_title)[:50] or "notes"
    filename = f"{safe_name}.pdf"

    await tool_context.save_artifact(
        filename,
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
    )

    return {"status": "success", "filename": filename}
