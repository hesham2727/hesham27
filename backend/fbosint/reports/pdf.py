"""PDF report generator (ReportLab) with correct Arabic shaping and RTL layout."""
from __future__ import annotations

import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .data import ReportModel, field_label, label, value_label

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT, FONT_BOLD = "FBOSans", "FBOSans-Bold"
ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
NAVY = colors.HexColor("#1f3a5f")
LIGHT = colors.HexColor("#eef2f7")
_registered = False


def _register_fonts() -> None:
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, str(ASSETS / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(ASSETS / "DejaVuSans-Bold.ttf")))
        _registered = True


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "")


def _visual_lines(text: str, width: float, font: str, size: float) -> list[str]:
    """Wrap logical text into lines that fit ``width``, then convert each line to visual order."""
    out: list[str] = []
    for para in _clean(text).split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            cand = f"{line} {w}".strip()
            if pdfmetrics.stringWidth(get_display(arabic_reshaper.reshape(cand)), font, size) <= width or not line:
                line = cand
            else:
                out.append(line)
                line = w
            # hard-break very long tokens (URLs)
            while pdfmetrics.stringWidth(line, font, size) > width and len(line) > 1:
                cut = len(line)
                while cut > 1 and pdfmetrics.stringWidth(line[:cut], font, size) > width:
                    cut -= 1
                out.append(line[:cut])
                line = line[cut:]
        out.append(line)
    return [get_display(arabic_reshaper.reshape(line)) if ARABIC_RE.search(line) else line for line in out]


class Builder:
    def __init__(self, model: ReportModel) -> None:
        _register_fonts()
        self.m = model
        self.rtl = model.lang == "ar"
        self.align = TA_RIGHT if self.rtl else TA_LEFT
        self.page_w = A4[0] - 30 * mm
        self.s_body = ParagraphStyle("b", fontName=FONT, fontSize=8.5, leading=11.5, alignment=self.align)
        self.s_cell = ParagraphStyle("c", fontName=FONT, fontSize=7.5, leading=9.5, alignment=self.align)
        self.s_h1 = ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=16, leading=21, alignment=self.align, textColor=NAVY)
        self.s_h2 = ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=11.5, leading=15, alignment=self.align, textColor=NAVY, spaceBefore=8, spaceAfter=4)
        self.s_small = ParagraphStyle("s", fontName=FONT, fontSize=7, leading=9, alignment=self.align, textColor=colors.HexColor("#555555"))

    def p(self, text: str, style: ParagraphStyle | None = None, width: float | None = None) -> Paragraph:
        style = style or self.s_body
        lines = _visual_lines(str(text), (width or self.page_w) - 6, style.fontName, style.fontSize)
        return Paragraph("<br/>".join(escape(line) for line in lines) or "&nbsp;", style)

    def L(self, key: str) -> str:  # noqa: N802
        return label(self.m.lang, key)

    def V(self, v: str) -> str:  # noqa: N802
        return value_label(self.m.lang, v)

    def table(self, header: list[str], rows: list[list[str]], widths: list[float]) -> Table:
        total = sum(widths)
        widths = [w * self.page_w / total for w in widths]
        if self.rtl:
            header, widths = header[::-1], widths[::-1]
            rows = [r[::-1] for r in rows]
        hstyle = ParagraphStyle("th", parent=self.s_cell, fontName=FONT_BOLD, textColor=colors.white)
        data = [[self.p(h, hstyle, w) for h, w in zip(header, widths)]]
        data += [[self.p(c, self.s_cell, w) for c, w in zip(r, widths)] for r in rows]
        if len(data) == 1:
            empty = [""] * len(widths)
            idx = len(widths) - 1 if self.rtl else 0
            empty[idx] = self.p(self.L("none"), self.s_cell, widths[idx])
            data.append(empty)
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5cfdb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    def dp_rows(self, items, with_source=True):
        rows = []
        for d in items:
            r = [field_label(self.m.lang, d.field), d.value]
            if with_source:
                r += [d.source_url or self.V(d.source_type), d.collected_at.strftime("%Y-%m-%d"), self.V(d.verification_status), self.V(d.confidence)]
            rows.append(r)
        return rows

    def build(self) -> bytes:
        m, inv, L, V = self.m, self.m.inv, self.L, self.V
        story: list = [self.p(L("title"), self.s_h1), Spacer(1, 4)]
        meta = [
            [L("reference"), inv.reference], [L("date"), inv.created_at.strftime("%Y-%m-%d %H:%M UTC")],
            [L("generated"), m.generated_at.strftime("%Y-%m-%d %H:%M UTC")], [L("target"), inv.normalized_url or inv.target_input],
            [L("target_input"), inv.target_input], [L("object_type"), V(inv.object_type)], [L("status"), V(inv.status)],
            [L("purpose"), inv.purpose], [L("legal_basis"), inv.legal_basis or "-"], [L("investigator"), m.investigator],
        ]
        story += [self.table([L("field"), L("value")], meta, [1, 3]), Spacer(1, 6)]
        story += [self.p(L("summary"), self.s_h2), self.p(m.summary), Spacer(1, 3), self.p(L("disclaimer"), self.s_small)]
        cols = [L("field"), L("value"), L("source"), L("collected"), L("verification"), L("confidence")]
        widths = [1.35, 2.3, 2.2, 1.05, 0.9, 0.85]
        story += [self.p(L("facts"), self.s_h2), self.table(cols, self.dp_rows(m.facts), widths)]
        story += [self.p(L("unverified"), self.s_h2), self.table(cols, self.dp_rows(m.unverified), widths)]
        story += [self.p(L("observations"), self.s_h2), self.table([L("field"), L("value")], self.dp_rows(m.observations, False), [1, 4])]
        av_rows = [[field_label(m.lang, d.field), V(d.availability), d.notes] for d in m.unavailable]
        story += [self.p(L("availability"), self.s_h2), self.table([L("field"), L("status"), L("notes")], av_rows, [1.3, 1, 2.5])]
        c_rows = [[field_label(m.lang, d.field), d.value, d.source_url, d.collected_at.strftime("%Y-%m-%d"), V(d.verification_status), V(d.confidence)] for d in m.contacts]
        story += [self.p(L("contacts"), self.s_h2), self.table(cols, c_rows, widths)]
        story += [self.p(L("activity"), self.s_h2), self.table([L("month"), L("count")], [[a, str(b)] for a, b in m.monthly], [1, 1])]
        p_rows = [[p.created_time.strftime("%Y-%m-%d") if p.created_time else "-", (p.message or "")[:400], p.permalink] for p in m.posts[:50]]
        story += [Spacer(1, 4), self.p(L("posts"), self.s_body), self.table([L("date_col"), L("message"), L("link")], p_rows, [0.8, 3.2, 2])]
        md_rows = [[field_label(m.lang, x.kind), x.source_url, f"{x.sha256[:16]}… / {x.phash}" if x.sha256 else V(x.status), str(x.duplicate_group or "-")] for x in m.media]
        story += [self.p(L("media"), self.s_h2), self.table([L("kind"), L("url"), L("hash"), L("dup")], md_rows, [0.9, 3, 1.8, 0.7])]
        s_rows = [[s.url, V(s.source_type), V(s.status), s.fetched_at.strftime("%Y-%m-%d %H:%M"), s.title or s.error_message] for s in m.sources]
        story += [self.p(L("sources"), self.s_h2), self.table([L("url"), L("kind"), L("status"), L("fetched"), L("title_col")], s_rows, [2.8, 1, 1, 1, 1.6])]
        lim_rows = [[x.get("code", ""), x.get("message", "")] for x in (inv.limitations or [])]
        story += [self.p(L("limitations"), self.s_h2), self.table([L("field"), L("notes")], lim_rows, [1.3, 3.5])]

        buf = io.BytesIO()

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFont(FONT, 7)
            canvas.setFillColor(colors.HexColor("#777777"))
            txt = f"{inv.reference}  ·  {m.app}  ·  {doc.page}"
            canvas.drawCentredString(A4[0] / 2, 10 * mm, txt)
            canvas.restoreState()

        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm, title=f"{inv.reference}", author=m.app, subject=label(m.lang, "title"))
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        return buf.getvalue()


def render_pdf(model: ReportModel) -> bytes:
    return Builder(model).build()
