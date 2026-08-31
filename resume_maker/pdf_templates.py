"""ReportLab resume renderers — five templates, all self-contained.

Why raw ``canvas`` and not Platypus flowables: the visually distinctive
templates (Modern's navy sidebar, Creative's gradient header) need absolute
placement — a coloured band that bleeds to the page edge, a sidebar that
repeats on page two. Platypus fights you on that; the canvas gives pixel
control. The cost is that WE own text wrapping and page overflow, which every
generator here handles explicitly through the shared helpers below.

Deliberately no external font files. Deployment to Agent Engine ships this
module as source; a missing ``.ttf`` fails only at render time, in production,
on a path no local test exercises. The 14 standard PDF fonts (Helvetica,
Times, Courier and their variants) are guaranteed present in every PDF viewer,
so every template is built from those. Colour, weight and layout carry the
visual difference instead.

Every generator takes a normalised ``dict`` (see ``normalize_resume``) and an
output path, and returns that path. They never raise on thin data: a resume
with no projects simply omits the section.
"""

from __future__ import annotations

from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ── Geometry ────────────────────────────────────────────────────────────────
# ReportLab's unit is the point (1/72 inch). A4 is 595.3 x 841.9 pt.
MM = 72.0 / 25.4


# ── Data normalisation ───────────────────────────────────────────────────────
def normalize_resume(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce loose model output into the shape the generators expect.

    The model assembles ``resume_json`` from a conversation, so fields drift:
    ``skills`` arrives as a flat list one turn and a grouped dict the next;
    ``bullets`` may be missing; a contact field may be ``None``. Rather than
    scatter ``.get(... ) or []`` through five renderers, every messy shape is
    flattened here once. Renderers below can then trust the structure.
    """
    d = dict(data or {})

    def clean_str(v: Any) -> str:
        return str(v).strip() if v not in (None, "") else ""

    def clean_list(v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            # A comma/newline-separated string is a common model shortcut.
            return [s.strip() for s in v.replace("\n", ",").split(",") if s.strip()]
        return [clean_str(x) for x in v if clean_str(x)]

    out: dict[str, Any] = {
        "name": clean_str(d.get("name")) or "Your Name",
        "role": clean_str(d.get("role") or d.get("title")),
        "email": clean_str(d.get("email")),
        "phone": clean_str(d.get("phone")),
        "location": clean_str(d.get("location")),
        "linkedin": clean_str(d.get("linkedin")),
        "github": clean_str(d.get("github")),
        "website": clean_str(d.get("website") or d.get("portfolio")),
        "summary": clean_str(d.get("summary") or d.get("objective")),
    }

    # Skills: accept a flat list OR a grouped dict. Keep the grouping when it's
    # given (Minimal/Classic render groups), but always expose a flat list too
    # (Modern's pills, ATS's line don't care about groups).
    raw_skills = d.get("skills")
    groups: dict[str, list[str]] = {}
    flat: list[str] = []
    if isinstance(raw_skills, dict):
        for key, val in raw_skills.items():
            items = clean_list(val)
            if items:
                groups[str(key).strip().title()] = items
                flat.extend(items)
    else:
        flat = clean_list(raw_skills)
    out["skill_groups"] = groups
    out["skills"] = flat

    def norm_entries(key: str, fields: dict[str, tuple[str, ...]]) -> list[dict]:
        entries = []
        for raw in d.get(key) or []:
            if not isinstance(raw, dict):
                continue
            entry: dict[str, Any] = {}
            for out_field, aliases in fields.items():
                value = ""
                for alias in aliases:
                    if raw.get(alias):
                        value = clean_str(raw.get(alias))
                        break
                entry[out_field] = value
            entry["bullets"] = clean_list(raw.get("bullets") or raw.get("highlights"))
            entries.append(entry)
        return entries

    out["experience"] = norm_entries(
        "experience",
        {
            "role": ("role", "title", "position"),
            "company": ("company", "employer", "organization"),
            "location": ("location",),
            "duration": ("duration", "dates", "date"),
        },
    )
    out["education"] = norm_entries(
        "education",
        {
            "degree": ("degree", "qualification", "title"),
            "school": ("school", "institution", "college", "university"),
            "location": ("location",),
            "duration": ("duration", "dates", "date", "year"),
            "details": ("details", "gpa", "score"),
        },
    )
    out["projects"] = norm_entries(
        "projects",
        {
            "name": ("name", "title"),
            "tech": ("tech", "stack", "technologies"),
            "link": ("link", "url"),
            "duration": ("duration", "date"),
        },
    )
    # Project descriptions live in bullets; fold a scalar "description" in.
    for proj, raw in zip(out["projects"], d.get("projects") or []):
        if isinstance(raw, dict) and raw.get("description") and not proj["bullets"]:
            proj["bullets"] = [clean_str(raw["description"])]

    out["certifications"] = clean_list(d.get("certifications"))
    out["achievements"] = clean_list(d.get("achievements") or d.get("awards"))
    return out


# ── Shared drawing helpers ───────────────────────────────────────────────────
def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedy word-wrap using real glyph widths, not a character estimate."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if stringWidth(trial, font, size) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class _Cursor:
    """A canvas plus a vertical position, with automatic page breaks.

    Generators draw top-down and lose track of when they've run off the page;
    routing every text write through ``text``/``space`` keeps ``y`` honest and
    calls ``showPage`` exactly when needed. ``on_new_page`` lets a template
    repaint per-page furniture (Modern's sidebar) after a break.
    """

    def __init__(self, c: canvas.Canvas, page_h: float, top: float, bottom: float):
        self.c = c
        self.page_h = page_h
        self.top = top
        self.bottom = bottom
        self.y = top
        self.on_new_page = None  # optional callable() -> None

    def _break_if_needed(self, need: float) -> None:
        if self.y - need < self.bottom:
            self.c.showPage()
            self.y = self.top
            if self.on_new_page:
                self.on_new_page()

    def space(self, amount: float) -> None:
        self.y -= amount

    def text(
        self,
        text: str,
        x: float,
        font: str,
        size: float,
        color,
        max_width: float,
        leading: float | None = None,
        align: str = "left",
        right_x: float | None = None,
    ) -> None:
        """Write wrapped text, breaking pages line by line as required."""
        leading = leading or size * 1.3
        for line in _wrap(text, font, size, max_width):
            self._break_if_needed(leading)
            self.c.setFillColor(color)
            self.c.setFont(font, size)
            if align == "right" and right_x is not None:
                self.c.drawRightString(right_x, self.y - size, line)
            elif align == "center":
                self.c.drawCentredString(x, self.y - size, line)
            else:
                self.c.drawString(x, self.y - size, line)
            self.y -= leading


def _clip(text: str, font: str, size: float, max_width: float) -> str:
    """Truncate a single line to fit, with an ellipsis. For pills/one-liners."""
    if stringWidth(text, font, size) <= max_width:
        return text
    while text and stringWidth(text + "…", font, size) > max_width:
        text = text[:-1]
    return text + "…"


def _contact_line(d: dict, sep: str = "  |  ") -> str:
    parts = [d[k] for k in ("email", "phone", "location", "linkedin", "github", "website") if d.get(k)]
    return sep.join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 1 — CLASSIC  (serif, black on white, centred header, ATS ~95)
# ═══════════════════════════════════════════════════════════════════════════
def generate_classic(data: dict, output_path: str) -> str:
    d = normalize_resume(data)
    W, H = A4
    margin = 18 * MM
    c = canvas.Canvas(output_path, pagesize=A4)
    content_w = W - 2 * margin
    cur = _Cursor(c, H, H - margin, margin)

    # Header — centred name / role / contact.
    cur.text(d["name"], W / 2, "Times-Bold", 24, colors.black, content_w, align="center", leading=26)
    if d["role"]:
        cur.text(d["role"], W / 2, "Times-Roman", 12, colors.black, content_w, align="center", leading=15)
    contact = _contact_line(d, sep="  •  ")
    if contact:
        cur.text(contact, W / 2, "Times-Roman", 10, colors.black, content_w, align="center", leading=13)
    cur.space(6)

    def rule() -> None:
        cur._break_if_needed(6)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(margin, cur.y, W - margin, cur.y)
        cur.space(10)

    def header(title: str) -> None:
        cur.space(4)
        rule()
        cur.text(title.upper(), margin, "Times-Bold", 11, colors.black, content_w, leading=15)
        cur.space(2)

    if d["summary"]:
        header("Summary")
        cur.text(d["summary"], margin, "Times-Roman", 10, colors.black, content_w, leading=13.5)

    if d["experience"]:
        header("Experience")
        for exp in d["experience"]:
            title = " — ".join(p for p in (exp["role"], exp["company"]) if p)
            cur.text(title, margin, "Times-Bold", 10.5, colors.black, content_w * 0.72, leading=13)
            if exp["duration"]:
                # Draw the date on the same visual line as the title just written.
                c.setFont("Times-Italic", 9.5)
                c.setFillColor(colors.HexColor("#333333"))
                c.drawRightString(W - margin, cur.y + 13 - 9.5, exp["duration"])
            for b in exp["bullets"]:
                cur.text(f"—  {b}", margin + 8, "Times-Roman", 10, colors.black, content_w - 8, leading=13)
            cur.space(6)

    if d["skill_groups"] or d["skills"]:
        header("Skills")
        if d["skill_groups"]:
            for group, items in d["skill_groups"].items():
                cur.text(f"{group}: {', '.join(items)}", margin, "Times-Roman", 10, colors.black, content_w, leading=13.5)
        else:
            cur.text(", ".join(d["skills"]), margin, "Times-Roman", 10, colors.black, content_w, leading=13.5)

    if d["projects"]:
        header("Projects")
        for p in d["projects"]:
            head = p["name"] + (f"  ({p['tech']})" if p["tech"] else "")
            cur.text(head, margin, "Times-Bold", 10.5, colors.black, content_w, leading=13)
            for b in p["bullets"]:
                cur.text(f"—  {b}", margin + 8, "Times-Roman", 10, colors.black, content_w - 8, leading=13)
            cur.space(4)

    if d["education"]:
        header("Education")
        for e in d["education"]:
            line = " — ".join(p for p in (e["degree"], e["school"]) if p)
            cur.text(line, margin, "Times-Bold", 10.5, colors.black, content_w * 0.72, leading=13)
            if e["duration"]:
                c.setFont("Times-Italic", 9.5)
                c.setFillColor(colors.HexColor("#333333"))
                c.drawRightString(W - margin, cur.y + 13 - 9.5, e["duration"])
            if e["details"]:
                cur.text(e["details"], margin + 8, "Times-Roman", 9.5, colors.HexColor("#333333"), content_w - 8, leading=12)
            cur.space(3)

    if d["certifications"]:
        header("Certifications")
        for cert in d["certifications"]:
            cur.text(f"—  {cert}", margin + 8, "Times-Roman", 10, colors.black, content_w - 8, leading=13)

    if d["achievements"]:
        header("Achievements")
        for a in d["achievements"]:
            cur.text(f"—  {a}", margin + 8, "Times-Roman", 10, colors.black, content_w - 8, leading=13)

    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 2 — MODERN SIDEBAR  (navy sidebar + white content, ATS ~80)
# ═══════════════════════════════════════════════════════════════════════════
def generate_modern_sidebar(data: dict, output_path: str) -> str:
    d = normalize_resume(data)
    W, H = A4
    SIDEBAR_W = 70 * MM
    NAVY = colors.HexColor("#1B2A4A")
    BLUE = colors.HexColor("#4A90D9")
    PILL = colors.HexColor("#2D3F60")
    DARK = colors.HexColor("#1A1A2E")
    GRAY = colors.HexColor("#4A4A4A")
    c = canvas.Canvas(output_path, pagesize=A4)

    def paint_sidebar_bg() -> None:
        c.setFillColor(NAVY)
        c.rect(0, 0, SIDEBAR_W, H, fill=1, stroke=0)

    # ---- Sidebar (drawn once; it's short enough to live on page 1) ----------
    paint_sidebar_bg()
    pad = 16
    sx = pad
    sw = SIDEBAR_W - 2 * pad
    sy = H - 44

    def s_wrap(text, font, size, color, leading):
        nonlocal sy
        for line in _wrap(text, font, size, sw):
            c.setFillColor(color)
            c.setFont(font, size)
            c.drawString(sx, sy - size, line)
            sy -= leading

    s_wrap(d["name"], "Helvetica-Bold", 18, colors.white, 21)
    if d["role"]:
        sy -= 2
        s_wrap(d["role"], "Helvetica", 10.5, BLUE, 14)
    sy -= 12

    def sidebar_header(title):
        nonlocal sy
        c.setFillColor(BLUE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(sx, sy - 8, title.upper())
        sy -= 16

    contact_items = [(k, d[k]) for k in ("email", "phone", "location", "linkedin", "github", "website") if d.get(k)]
    if contact_items:
        sidebar_header("Contact")
        for _, val in contact_items:
            s_wrap(val, "Helvetica", 8, colors.white, 12.5)
        sy -= 10

    if d["skills"]:
        sidebar_header("Skills")
        # Pills that wrap within the sidebar.
        px, py = sx, sy
        line_h = 17
        for skill in d["skills"]:
            label = _clip(skill, "Helvetica", 7.5, sw - 12)
            w = stringWidth(label, "Helvetica", 7.5) + 12
            if px + w > sx + sw and px > sx:
                px = sx
                py -= line_h
            c.setFillColor(PILL)
            c.roundRect(px, py - 12, w, 13, 3, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica", 7.5)
            c.drawString(px + 6, py - 9, label)
            px += w + 5
        sy = py - line_h - 4

    if d["certifications"]:
        sidebar_header("Certifications")
        for cert in d["certifications"]:
            s_wrap(f"• {cert}", "Helvetica", 8, colors.white, 12.5)
        sy -= 6

    if d["achievements"]:
        sidebar_header("Achievements")
        for a in d["achievements"]:
            s_wrap(f"• {a}", "Helvetica", 8, colors.white, 12.5)

    # ---- Main content area (page-break aware) -------------------------------
    cx = SIDEBAR_W + 18
    cw = W - cx - 22
    cur = _Cursor(c, H, H - 40, 40)
    cur.on_new_page = paint_sidebar_bg  # keep the navy band on overflow pages

    def content_header(title):
        cur._break_if_needed(24)
        c.setFillColor(BLUE)
        c.rect(cx - 6, cur.y - 12, 3, 13, fill=1, stroke=0)
        cur.text(title.upper(), cx, "Helvetica-Bold", 10.5, DARK, cw, leading=17)
        cur.space(3)

    if d["summary"]:
        content_header("Profile")
        cur.text(d["summary"], cx, "Helvetica", 9, GRAY, cw, leading=13)
        cur.space(6)

    if d["experience"]:
        content_header("Experience")
        for exp in d["experience"]:
            cur.text(exp["role"], cx, "Helvetica-Bold", 9.5, DARK, cw * 0.68, leading=12.5)
            if exp["duration"]:
                c.setFont("Helvetica", 8)
                c.setFillColor(BLUE)
                c.drawRightString(W - 22, cur.y + 12.5 - 8, exp["duration"])
            sub = " · ".join(p for p in (exp["company"], exp["location"]) if p)
            if sub:
                cur.text(sub, cx, "Helvetica-Oblique", 8.5, GRAY, cw, leading=12)
            for b in exp["bullets"]:
                cur._break_if_needed(12)
                c.setFillColor(BLUE)
                c.circle(cx + 3, cur.y - 6, 1.6, fill=1, stroke=0)
                cur.text(b, cx + 10, "Helvetica", 8.5, colors.HexColor("#333333"), cw - 10, leading=12)
            cur.space(7)

    if d["projects"]:
        content_header("Projects")
        for p in d["projects"]:
            head = p["name"] + (f"  ·  {p['tech']}" if p["tech"] else "")
            cur.text(head, cx, "Helvetica-Bold", 9.5, DARK, cw, leading=12.5)
            for b in p["bullets"]:
                cur._break_if_needed(12)
                c.setFillColor(BLUE)
                c.circle(cx + 3, cur.y - 6, 1.6, fill=1, stroke=0)
                cur.text(b, cx + 10, "Helvetica", 8.5, colors.HexColor("#333333"), cw - 10, leading=12)
            cur.space(6)

    if d["education"]:
        content_header("Education")
        for e in d["education"]:
            cur.text(e["degree"] or e["school"], cx, "Helvetica-Bold", 9.5, DARK, cw * 0.68, leading=12.5)
            if e["duration"]:
                c.setFont("Helvetica", 8)
                c.setFillColor(BLUE)
                c.drawRightString(W - 22, cur.y + 12.5 - 8, e["duration"])
            line = " · ".join(p for p in (e["school"] if e["degree"] else "", e["details"]) if p)
            if line:
                cur.text(line, cx, "Helvetica", 8.5, GRAY, cw, leading=12)
            cur.space(5)

    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 3 — MINIMAL  (left-aligned, greys, whitespace-heavy, ATS ~90)
# ═══════════════════════════════════════════════════════════════════════════
def generate_minimal(data: dict, output_path: str) -> str:
    d = normalize_resume(data)
    W, H = A4
    ml = 25 * MM
    mt = 20 * MM
    BLACK = colors.HexColor("#111111")
    GRAY = colors.HexColor("#888888")
    LINE = colors.HexColor("#E8E8E8")
    c = canvas.Canvas(output_path, pagesize=A4)
    cw = W - 2 * ml
    cur = _Cursor(c, H, H - mt, mt)

    cur.text(d["name"], ml, "Helvetica-Bold", 26, BLACK, cw, leading=29)
    if d["role"]:
        cur.text(d["role"], ml, "Helvetica", 13, GRAY, cw, leading=17)
    contact = _contact_line(d, sep="   |   ")
    if contact:
        cur.space(2)
        cur.text(contact, ml, "Helvetica", 9, GRAY, cw, leading=13)
    cur.space(14)

    def header(title):
        cur.space(6)
        cur.text(title.upper(), ml, "Helvetica", 10, GRAY, cw, leading=13)
        cur._break_if_needed(6)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.75)
        c.line(ml, cur.y + 2, W - ml, cur.y + 2)
        cur.space(8)

    if d["summary"]:
        header("Profile")
        cur.text(d["summary"], ml, "Helvetica", 10, BLACK, cw, leading=14.5)

    if d["experience"]:
        header("Experience")
        for exp in d["experience"]:
            cur.text(exp["role"], ml, "Helvetica-Bold", 11, BLACK, cw * 0.7, leading=14)
            if exp["duration"]:
                c.setFont("Helvetica", 9)
                c.setFillColor(GRAY)
                c.drawRightString(W - ml, cur.y + 14 - 9, exp["duration"])
            sub = " · ".join(p for p in (exp["company"], exp["location"]) if p)
            if sub:
                cur.text(sub, ml, "Helvetica", 9.5, GRAY, cw, leading=13)
            for b in exp["bullets"]:
                cur.text(b, ml, "Helvetica", 10, BLACK, cw, leading=14)
            cur.space(10)

    if d["projects"]:
        header("Projects")
        for p in d["projects"]:
            cur.text(p["name"], ml, "Helvetica-Bold", 11, BLACK, cw * 0.7, leading=14)
            if p["tech"]:
                c.setFont("Helvetica", 9)
                c.setFillColor(GRAY)
                c.drawRightString(W - ml, cur.y + 14 - 9, _clip(p["tech"], "Helvetica", 9, cw * 0.3))
            for b in p["bullets"]:
                cur.text(b, ml, "Helvetica", 10, BLACK, cw, leading=14)
            cur.space(8)

    if d["skill_groups"] or d["skills"]:
        header("Skills")
        if d["skill_groups"]:
            for group, items in d["skill_groups"].items():
                cur._break_if_needed(14)
                c.setFont("Helvetica-Bold", 9.5)
                c.setFillColor(GRAY)
                c.drawString(ml, cur.y - 9.5, f"{group}")
                cur.text(", ".join(items), ml + 70, "Helvetica", 10, BLACK, cw - 70, leading=14)
        else:
            cur.text(" · ".join(d["skills"]), ml, "Helvetica", 10, BLACK, cw, leading=14.5)

    if d["education"]:
        header("Education")
        for e in d["education"]:
            cur.text(e["degree"] or e["school"], ml, "Helvetica-Bold", 11, BLACK, cw * 0.7, leading=14)
            if e["duration"]:
                c.setFont("Helvetica", 9)
                c.setFillColor(GRAY)
                c.drawRightString(W - ml, cur.y + 14 - 9, e["duration"])
            line = " · ".join(p for p in (e["school"] if e["degree"] else "", e["details"]) if p)
            if line:
                cur.text(line, ml, "Helvetica", 9.5, GRAY, cw, leading=13)
            cur.space(8)

    if d["certifications"]:
        header("Certifications")
        cur.text(" · ".join(d["certifications"]), ml, "Helvetica", 10, BLACK, cw, leading=14.5)

    if d["achievements"]:
        header("Achievements")
        for a in d["achievements"]:
            cur.text(a, ml, "Helvetica", 10, BLACK, cw, leading=14)

    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 4 — CREATIVE BOLD  (gradient header band, amber accents, ATS ~70)
# ═══════════════════════════════════════════════════════════════════════════
def generate_creative_bold(data: dict, output_path: str) -> str:
    d = normalize_resume(data)
    W, H = A4
    margin = 15 * MM
    BAND_H = 52 * MM
    PURPLE = colors.HexColor("#4C1D95")
    INDIGO = colors.HexColor("#3730A3")
    AMBER = colors.HexColor("#F59E0B")
    DARK = colors.HexColor("#1A1A2E")
    GRAY = colors.HexColor("#444444")
    c = canvas.Canvas(output_path, pagesize=A4)

    # Gradient header — many thin horizontal strips fading purple→indigo.
    strips = 120
    for i in range(strips):
        t = i / (strips - 1)
        r = PURPLE.red + (INDIGO.red - PURPLE.red) * t
        g = PURPLE.green + (INDIGO.green - PURPLE.green) * t
        b = PURPLE.blue + (INDIGO.blue - PURPLE.blue) * t
        c.setFillColorRGB(r, g, b)
        y0 = H - BAND_H + (BAND_H * i / strips)
        c.rect(0, y0, W, BAND_H / strips + 1, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(20 * MM, H - 26 * MM, _clip(d["name"], "Helvetica-Bold", 30, W - 40 * MM))
    if d["role"]:
        c.setFont("Helvetica", 14)
        c.setFillColor(colors.HexColor("#E5E0F5"))
        c.drawString(20 * MM, H - 33 * MM, _clip(d["role"], "Helvetica", 14, W - 40 * MM))
    contact = _contact_line(d, sep="    ")
    if contact:
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.white)
        c.drawString(20 * MM, H - 42 * MM, _clip(contact, "Helvetica", 9, W - 40 * MM))

    cw = W - 2 * margin
    cur = _Cursor(c, H, H - BAND_H - 14, margin)

    def header(title):
        cur.space(6)
        cur._break_if_needed(20)
        c.setFillColor(AMBER)
        c.rect(margin, cur.y - 13, 4, 15, fill=1, stroke=0)
        cur.text(title.upper(), margin + 10, "Helvetica-Bold", 12, DARK, cw - 10, leading=17)
        cur.space(3)

    if d["summary"]:
        header("Profile")
        cur.text(d["summary"], margin, "Helvetica", 9.5, GRAY, cw, leading=13.5)

    if d["skills"]:
        header("Skills")
        # Visual skill bars — filled amber portion over a light track.
        bar_w = cw * 0.55
        for skill in d["skills"][:12]:
            cur._break_if_needed(15)
            c.setFillColor(DARK)
            c.setFont("Helvetica", 9)
            c.drawString(margin, cur.y - 9, _clip(skill, "Helvetica", 9, cw * 0.4 - 6))
            track_x = margin + cw * 0.42
            c.setFillColor(colors.HexColor("#EDEBF7"))
            c.roundRect(track_x, cur.y - 9, bar_w, 6, 2, fill=1, stroke=0)
            c.setFillColor(AMBER)
            # No real proficiency data — show a strong, consistent fill rather
            # than inventing per-skill levels the user never gave.
            c.roundRect(track_x, cur.y - 9, bar_w * 0.85, 6, 2, fill=1, stroke=0)
            cur.space(15)

    if d["experience"]:
        header("Experience")
        for exp in d["experience"]:
            c.setFillColor(INDIGO)
            cur.text(exp["company"] or exp["role"], margin, "Helvetica-Bold", 10.5, INDIGO, cw * 0.68, leading=13.5)
            if exp["duration"]:
                c.setFont("Helvetica-Bold", 9)
                c.setFillColor(AMBER)
                c.drawRightString(W - margin, cur.y + 13.5 - 9, exp["duration"])
            if exp["company"] and exp["role"]:
                cur.text(exp["role"], margin, "Helvetica-Oblique", 9.5, DARK, cw, leading=12.5)
            for b in exp["bullets"]:
                cur._break_if_needed(12.5)
                c.setFillColor(AMBER)
                c.circle(margin + 3, cur.y - 6, 1.8, fill=1, stroke=0)
                cur.text(b, margin + 11, "Helvetica", 9.5, GRAY, cw - 11, leading=12.5)
            cur.space(7)

    if d["projects"]:
        header("Projects")
        for p in d["projects"]:
            head = p["name"] + (f"  ·  {p['tech']}" if p["tech"] else "")
            cur.text(head, margin, "Helvetica-Bold", 10.5, INDIGO, cw, leading=13.5)
            for b in p["bullets"]:
                cur._break_if_needed(12.5)
                c.setFillColor(AMBER)
                c.circle(margin + 3, cur.y - 6, 1.8, fill=1, stroke=0)
                cur.text(b, margin + 11, "Helvetica", 9.5, GRAY, cw - 11, leading=12.5)
            cur.space(6)

    if d["education"]:
        header("Education")
        for e in d["education"]:
            cur.text(e["degree"] or e["school"], margin, "Helvetica-Bold", 10.5, DARK, cw * 0.68, leading=13.5)
            if e["duration"]:
                c.setFont("Helvetica-Bold", 9)
                c.setFillColor(AMBER)
                c.drawRightString(W - margin, cur.y + 13.5 - 9, e["duration"])
            line = " · ".join(p for p in (e["school"] if e["degree"] else "", e["details"]) if p)
            if line:
                cur.text(line, margin, "Helvetica", 9, GRAY, cw, leading=12)
            cur.space(5)

    if d["certifications"] or d["achievements"]:
        header("Highlights")
        for item in d["certifications"] + d["achievements"]:
            cur._break_if_needed(12.5)
            c.setFillColor(AMBER)
            c.circle(margin + 3, cur.y - 6, 1.8, fill=1, stroke=0)
            cur.text(item, margin + 11, "Helvetica", 9.5, GRAY, cw - 11, leading=12.5)

    c.save()
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 5 — ATS-SAFE  (single column, no colour, hyphen bullets, ATS ~99)
# ═══════════════════════════════════════════════════════════════════════════
def generate_ats_safe(data: dict, output_path: str) -> str:
    d = normalize_resume(data)
    W, H = LETTER  # US default; scanners are typically US-configured.
    margin = 20 * MM
    BLACK = colors.black
    c = canvas.Canvas(output_path, pagesize=LETTER)
    cw = W - 2 * margin
    cur = _Cursor(c, H, H - margin, margin)

    cur.text(d["name"], margin, "Helvetica-Bold", 16, BLACK, cw, leading=20)
    contact = _contact_line(d, sep="  |  ")
    if d["role"]:
        cur.text(d["role"], margin, "Helvetica", 11, BLACK, cw, leading=14)
    if contact:
        cur.text(contact, margin, "Helvetica", 10, BLACK, cw, leading=13)
    cur.space(8)

    def header(title):
        cur.space(4)
        cur.text(title.upper(), margin, "Helvetica-Bold", 11, BLACK, cw, leading=14)
        # A line of dashes — the ATS-friendly divider, not a drawn rule.
        dash = "-" * int(cw / stringWidth("-", "Helvetica", 9))
        cur.text(dash, margin, "Helvetica", 9, BLACK, cw, leading=11)

    if d["summary"]:
        header("Summary")
        cur.text(d["summary"], margin, "Helvetica", 10, BLACK, cw, leading=13.5)

    if d["skill_groups"] or d["skills"]:
        header("Skills")
        if d["skill_groups"]:
            for group, items in d["skill_groups"].items():
                cur.text(f"{group}: {', '.join(items)}", margin, "Helvetica", 10, BLACK, cw, leading=13.5)
        else:
            cur.text(", ".join(d["skills"]), margin, "Helvetica", 10, BLACK, cw, leading=13.5)

    if d["experience"]:
        header("Experience")
        for exp in d["experience"]:
            title = ", ".join(p for p in (exp["role"], exp["company"]) if p)
            cur.text(title, margin, "Helvetica-Bold", 10.5, BLACK, cw * 0.72, leading=13.5)
            if exp["duration"]:
                c.setFont("Helvetica", 10)
                c.setFillColor(BLACK)
                c.drawRightString(W - margin, cur.y + 13.5 - 10, exp["duration"])
            for b in exp["bullets"]:
                cur.text(f"- {b}", margin, "Helvetica", 10, BLACK, cw, leading=13.5)
            cur.space(6)

    if d["projects"]:
        header("Projects")
        for p in d["projects"]:
            head = p["name"] + (f" ({p['tech']})" if p["tech"] else "")
            cur.text(head, margin, "Helvetica-Bold", 10.5, BLACK, cw, leading=13.5)
            for b in p["bullets"]:
                cur.text(f"- {b}", margin, "Helvetica", 10, BLACK, cw, leading=13.5)
            cur.space(4)

    if d["education"]:
        header("Education")
        for e in d["education"]:
            line = ", ".join(p for p in (e["degree"], e["school"]) if p)
            cur.text(line, margin, "Helvetica-Bold", 10.5, BLACK, cw * 0.72, leading=13.5)
            if e["duration"]:
                c.setFont("Helvetica", 10)
                c.setFillColor(BLACK)
                c.drawRightString(W - margin, cur.y + 13.5 - 10, e["duration"])
            if e["details"]:
                cur.text(e["details"], margin, "Helvetica", 10, BLACK, cw, leading=13.5)
            cur.space(4)

    if d["certifications"]:
        header("Certifications")
        for cert in d["certifications"]:
            cur.text(f"- {cert}", margin, "Helvetica", 10, BLACK, cw, leading=13.5)

    if d["achievements"]:
        header("Achievements")
        for a in d["achievements"]:
            cur.text(f"- {a}", margin, "Helvetica", 10, BLACK, cw, leading=13.5)

    c.save()
    return output_path


# ── Dispatcher ───────────────────────────────────────────────────────────────
GENERATORS = {
    "classic": generate_classic,
    "modern": generate_modern_sidebar,
    "minimal": generate_minimal,
    "creative": generate_creative_bold,
    "ats": generate_ats_safe,
}


def render(resume_data: dict, template: str, output_path: str) -> str:
    """Render ``resume_data`` with ``template`` to ``output_path``.

    Unknown templates fall back to Classic rather than erroring — a slightly
    wrong style still ships a usable resume, whereas an exception mid-turn
    leaves the user with nothing.
    """
    gen = GENERATORS.get((template or "").strip().lower(), generate_classic)
    return gen(resume_data, output_path)
