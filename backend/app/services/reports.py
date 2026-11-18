"""PDF (ReportLab) and Excel (OpenPyXL) exports with Arabic support."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import __version__
from ..config import get_settings
from .phone import CURRENT_LOCATION_UNAVAILABLE, CURRENT_LOCATION_UNAVAILABLE_AR
from .timefmt import age_ar, local

FONT = "TahqiqSans"
FONT_BOLD = "TahqiqSans-Bold"
_fonts_ready = False

STATUS_AR = {"open": "مفتوح", "closed": "مغلق"}
RELIABILITY_AR = {"confirmed": "مؤكد", "likely": "مرجّح", "unverified": "غير متحقق"}
INVITE_STATUS_AR = {
    "pending": "بانتظار الفتح",
    "opened": "تم الفتح",
    "shared": "تمت المشاركة",
    "declined": "رفض العميل",
    "revoked": "ملغاة",
    "expired": "منتهية",
}


def _ensure_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    d = get_settings().fonts_dir
    pdfmetrics.registerFont(TTFont(FONT, str(d / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(d / "DejaVuSans-Bold.ttf")))
    _fonts_ready = True


def _visual(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def _wrap_logical(text: str, font: str, size: float, width: float) -> list[str]:
    """Wrap in LOGICAL order first, then convert each line to visual order.

    Converting a whole paragraph and letting ReportLab wrap it would reverse
    the line order for right-to-left text.
    """
    lines: list[str] = []
    for para in (text or "").split("\n"):
        words = para.split()
        current = ""
        for w in words:
            candidate = f"{current} {w}".strip()
            if pdfmetrics.stringWidth(arabic_reshaper.reshape(candidate), font, size) <= width or not current:
                current = candidate
            else:
                lines.append(current)
                current = w
        lines.append(current)
    return lines


def _para(text: str, style: ParagraphStyle, width: float) -> Paragraph:
    lines = _wrap_logical(str(text or ""), style.fontName, style.fontSize, width)
    return Paragraph("<br/>".join(escape(_visual(l)) for l in lines), style)


def _styles():
    _ensure_fonts()
    base = ParagraphStyle("base", fontName=FONT, fontSize=9.5, leading=14, alignment=TA_RIGHT)
    return {
        "base": base,
        "title": ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=16, leading=22, alignment=TA_CENTER),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName=FONT_BOLD, fontSize=12, leading=18, textColor=colors.HexColor("#0f3d5e"),
            spaceBefore=8, spaceAfter=4,
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=12),
        "cellb": ParagraphStyle("cellb", parent=base, fontName=FONT_BOLD, fontSize=8.5, leading=12),
        "warn": ParagraphStyle("warn", parent=base, fontName=FONT_BOLD, textColor=colors.HexColor("#9a1c1c")),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=colors.HexColor("#555555")),
    }


TABLE_STYLE = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4ce")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eef4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
)


def _rtl_table(header: list[str], rows: list[list], widths: list[float], st) -> Table:
    """Build a table whose first logical column is on the RIGHT."""
    data = [[_para(h, st["cellb"], w - 8) for h, w in zip(header, widths)]]
    for r in rows:
        data.append([_para(str(c if c is not None else ""), st["cell"], w - 8) for c, w in zip(r, widths)])
    data = [list(reversed(r)) for r in data]
    t = Table(data, colWidths=list(reversed(widths)), repeatRows=1)
    t.setStyle(TABLE_STYLE)
    return t


def _kv_table(pairs: list[tuple[str, str]], width: float, st) -> Table:
    return _rtl_table(["البند", "القيمة"], [[k, v] for k, v in pairs], [width * 0.3, width * 0.7], st)


def investigation_pdf(inv, sources, locations, invitations, checks, generated_by: str) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Investigation {inv.ref_code}", author="Tahqiq",
    )
    W = doc.width
    now = datetime.now(timezone.utc)
    story: list = [
        _para(f"تقرير تحقيق رقم {inv.ref_code}", st["title"], W),
        _para(f"تاريخ الإصدار: {local(now)} (توقيت القاهرة) – أعدّه: {generated_by}", st["small"], W),
        Spacer(1, 6),
        _para("بيانات التحقيق", st["h2"], W),
    ]
    v = inv.validation or {}
    story.append(
        _kv_table(
            [
                ("العنوان", inv.title),
                ("الرقم المُدخل", inv.phone_raw),
                ("الصيغة الدولية E.164", inv.phone_e164 or "—"),
                ("الغرض المشروع", inv.purpose),
                ("الحالة", STATUS_AR.get(inv.status, inv.status)),
                ("العميل المرتبط", inv.customer.full_name if inv.customer else "—"),
                ("تاريخ الإنشاء", local(inv.created_at)),
                ("ملاحظات", inv.notes or "—"),
            ],
            W,
            st,
        )
    )
    story += [Spacer(1, 6), _para("نتيجة التحقق من الرقم (بيانات خطة الترقيم – دون اتصال)", st["h2"], W)]
    story.append(
        _kv_table(
            [
                ("صالح", "نعم" if v.get("is_valid") else "لا"),
                ("النوع", v.get("number_type_ar", "")),
                ("الصيغة الدولية", v.get("international_format", "")),
                ("المشغّل الأصلي للنطاق", v.get("original_operator_ar") or "—"),
                ("المنطقة (كود)", v.get("geographic_area") or "—"),
                ("تنبيهات", " | ".join(v.get("warnings", [])) or "—"),
                ("لا يمكن استنتاجه من الرقم", "، ".join(v.get("not_derivable", []))),
                ("مصدر البيانات", v.get("data_source", "")),
            ],
            W,
            st,
        )
    )

    story += [Spacer(1, 6), _para("سجلات المصادر العامة", st["h2"], W)]
    if sources:
        story.append(
            _rtl_table(
                ["المصدر", "الرابط", "تاريخ الاطلاع", "الموثوقية", "الملخص"],
                [
                    [s.source_name, s.source_url or "—", local(s.observed_at), RELIABILITY_AR.get(s.reliability, s.reliability), s.summary]
                    for s in sources
                ],
                [W * 0.17, W * 0.23, W * 0.14, W * 0.1, W * 0.36],
                st,
            )
        )
    else:
        story.append(_para("لا توجد سجلات.", st["base"], W))

    story += [Spacer(1, 6), _para("الموقع", st["h2"], W)]
    story.append(Paragraph(escape(CURRENT_LOCATION_UNAVAILABLE), ParagraphStyle("en", parent=st["warn"], alignment=TA_CENTER)))
    story.append(_para(CURRENT_LOCATION_UNAVAILABLE_AR, st["warn"], W))
    if locations:
        story.append(_para("مواقع تمت مشاركتها سابقاً بموافقة صاحب الجهاز – بيانات تاريخية وليست موقعاً حالياً:", st["base"], W))
        story.append(
            _rtl_table(
                ["وقت الجمع (القاهرة)", "العمر", "خط العرض", "خط الطول", "الدقة (م)", "وقت الموافقة"],
                [
                    [local(l.collected_at), age_ar(l.collected_at, now), f"{l.latitude:.6f}", f"{l.longitude:.6f}",
                     f"{l.accuracy_m:.0f}" if l.accuracy_m is not None else "—", local(l.consent_given_at)]
                    for l in locations
                ],
                [W * 0.2, W * 0.15, W * 0.15, W * 0.15, W * 0.1, W * 0.25],
                st,
            )
        )
    if invitations:
        story += [Spacer(1, 4), _para("دعوات مشاركة الموقع", st["h2"], W)]
        story.append(
            _rtl_table(
                ["تاريخ الإنشاء", "تنتهي في", "الحالة", "الغرض"],
                [[local(i.created_at), local(i.expires_at), INVITE_STATUS_AR.get(i.effective_status, i.status), i.purpose] for i in invitations],
                [W * 0.2, W * 0.2, W * 0.15, W * 0.45],
                st,
            )
        )
    if checks:
        story += [Spacer(1, 4), _para("سجل عمليات التحقق من الرقم", st["h2"], W)]
        story.append(
            _rtl_table(
                ["الوقت", "المُدخل", "E.164", "صالح", "بواسطة"],
                [[local(c.checked_at), c.raw_input, c.e164 or "—", "نعم" if c.is_valid else "لا", c.checker.username if c.checker else ""] for c in checks],
                [W * 0.22, W * 0.2, W * 0.22, W * 0.1, W * 0.26],
                st,
            )
        )
    story += [
        Spacer(1, 10),
        _para(
            "تنبيه: هذا التقرير مبني على بيانات خطط الترقيم العامة، وسجلات أدخلها المحقق يدوياً من مصادر عامة، "
            "ومواقع شاركها أصحاب الأجهزة بموافقتهم الصريحة فقط. لا يحتوي على أي بيانات من شبكات الاتصالات.",
            st["small"],
            W,
        ),
        Paragraph(escape(f"Tahqiq {__version__}"), st["small"]),
    ]
    doc.build(story)
    return buf.getvalue()


# ----------------------------------------------------------------- Excel

HEADER_FILL = PatternFill("solid", fgColor="0F3D5E")
HEADER_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="B8C4CE")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title[:31]
    ws.sheet_view.rightToLeft = True
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font, c.border = HEADER_FILL, HEADER_FONT, BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append(["" if v is None else v for v in r])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.border = BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for i, h in enumerate(header, start=1):
        longest = max([len(str(h))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r) and r[i - 1] is not None] or [10])
        ws.column_dimensions[get_column_letter(i)].width = min(max(12, longest + 2), 60)
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    return ws


def investigations_xlsx(investigations, sources, locations, checks) -> bytes:
    wb = Workbook()
    _sheet(
        wb,
        "التحقيقات",
        ["المرجع", "العنوان", "الرقم", "E.164", "صالح", "النوع", "المشغّل الأصلي", "الغرض", "الحالة", "العميل", "تاريخ الإنشاء (القاهرة)"],
        [
            [i.ref_code, i.title, i.phone_raw, i.phone_e164, "نعم" if (i.validation or {}).get("is_valid") else "لا",
             (i.validation or {}).get("number_type_ar", ""), (i.validation or {}).get("original_operator_ar", ""),
             i.purpose, STATUS_AR.get(i.status, i.status), i.customer.full_name if i.customer else "", local(i.created_at)]
            for i in investigations
        ],
        first=True,
    )
    ref = {i.id: i.ref_code for i in investigations}
    _sheet(
        wb,
        "المصادر العامة",
        ["المرجع", "المصدر", "الرابط", "النوع", "تاريخ الاطلاع", "الموثوقية", "الملخص"],
        [[ref.get(s.investigation_id, ""), s.source_name, s.source_url, s.source_type, local(s.observed_at),
          RELIABILITY_AR.get(s.reliability, s.reliability), s.summary] for s in sources],
    )
    _sheet(
        wb,
        "مواقع تاريخية",
        ["المرجع", "وقت الجمع (القاهرة)", "خط العرض", "خط الطول", "الدقة (م)", "وقت الموافقة", "ملاحظة"],
        [[ref.get(l.investigation_id, ""), local(l.collected_at), l.latitude, l.longitude, l.accuracy_m,
          local(l.consent_given_at), "موقع تاريخي تمت مشاركته بموافقة – ليس موقعاً حالياً"] for l in locations],
    )
    _sheet(
        wb,
        "سجل التحقق",
        ["الوقت (القاهرة)", "المُدخل", "E.164", "صالح", "المرجع", "بواسطة"],
        [[local(c.checked_at), c.raw_input, c.e164, "نعم" if c.is_valid else "لا", ref.get(c.investigation_id, ""),
          c.checker.username if c.checker else ""] for c in checks],
    )
    ws = wb.create_sheet("ملاحظات")
    ws.sheet_view.rightToLeft = True
    ws.append([CURRENT_LOCATION_UNAVAILABLE])
    ws.append([CURRENT_LOCATION_UNAVAILABLE_AR])
    ws.append([f"تم الإنشاء: {local(datetime.now(timezone.utc))} – Tahqiq {__version__}"])
    ws.column_dimensions["A"].width = 90
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
