"""Excel report (openpyxl): one sheet per section, filters, frozen headers,
formula-driven summary, RTL sheets for Arabic, and formula-injection protection."""
from __future__ import annotations

import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .data import ReportModel, field_label, label, value_label

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="C5CFDB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
DANGEROUS_PREFIX = ("=", "@")  # "+"/"-" are kept (phone numbers); cells are also typed as text


def _safe(value):
    """Neutralise spreadsheet formula injection in untrusted text."""
    if isinstance(value, str):
        value = ILLEGAL.sub("", value)[:32000]
        if value.startswith(DANGEROUS_PREFIX):
            value = "'" + value
    return value


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list], widths: list[int], rtl: bool) -> Worksheet:
    ws = wb.create_sheet(title[:31])
    ws.sheet_view.rightToLeft = rtl
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font, c.border = HEADER_FILL, HEADER_FONT, BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append([_safe(v) for v in r])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.border = BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
            if isinstance(c.value, str):
                c.data_type = "s"  # never interpret collected text as a formula
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
    return ws


def render_xlsx(m: ReportModel) -> bytes:
    lang, inv, rtl = m.lang, m.inv, m.lang == "ar"
    L = lambda k: label(lang, k)  # noqa: E731
    V = lambda v: value_label(lang, v)  # noqa: E731
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary" if lang == "en" else "الملخص"
    ws.sheet_view.rightToLeft = rtl
    ws["A1"] = L("title")
    ws["A1"].font = Font(bold=True, size=14, color="1F3A5F")
    info = [
        (L("reference"), inv.reference), (L("date"), inv.created_at.strftime("%Y-%m-%d %H:%M UTC")),
        (L("generated"), m.generated_at.strftime("%Y-%m-%d %H:%M UTC")), (L("target"), inv.normalized_url or inv.target_input),
        (L("object_type"), V(inv.object_type)), (L("status"), V(inv.status)), (L("purpose"), inv.purpose),
        (L("legal_basis"), inv.legal_basis or "-"), (L("investigator"), m.investigator),
    ]
    for i, (k, v) in enumerate(info, start=3):
        ws.cell(i, 1, k).font = Font(bold=True)
        c = ws.cell(i, 2, _safe(v))
        c.data_type = "s"
        c.alignment = Alignment(wrap_text=True)

    dp_header = [L("category"), L("field"), L("value"), L("source"), L("method"), L("collected"), L("verification"), L("confidence"), L("notes")]
    dp_w = [12, 18, 40, 45, 12, 18, 14, 12, 30]

    def dp_rows(items):
        return [[d.category, field_label(lang, d.field), d.value, d.source_url, d.extraction_method, d.collected_at.strftime("%Y-%m-%d %H:%M"), V(d.verification_status), V(d.confidence), d.notes] for d in items]

    names = {
        "facts": "Facts" if lang == "en" else "حقائق",
        "unverified": "Unverified" if lang == "en" else "غير موثق",
        "obs": "Observations" if lang == "en" else "ملاحظات",
        "avail": "Availability" if lang == "en" else "التوفر",
        "contacts": "Contacts" if lang == "en" else "الاتصال",
        "posts": "Posts" if lang == "en" else "المنشورات",
        "activity": "Activity" if lang == "en" else "النشاط",
        "media": "Media" if lang == "en" else "الوسائط",
        "sources": "Sources" if lang == "en" else "المصادر",
        "limits": "Limitations" if lang == "en" else "القيود",
    }
    _sheet(wb, names["facts"], dp_header, dp_rows(m.facts), dp_w, rtl)
    _sheet(wb, names["unverified"], dp_header, dp_rows(m.unverified), dp_w, rtl)
    _sheet(wb, names["obs"], [L("field"), L("value")], [[field_label(lang, d.field), d.value] for d in m.observations], [22, 100], rtl)
    _sheet(wb, names["avail"], [L("category"), L("field"), L("status"), L("notes"), L("source")], [[d.category, field_label(lang, d.field), V(d.availability), d.notes, d.source_url] for d in m.unavailable], [12, 20, 16, 30, 45], rtl)
    _sheet(wb, names["contacts"], dp_header, dp_rows(m.contacts), dp_w, rtl)
    _sheet(wb, names["posts"], [L("date_col"), L("kind"), L("message"), L("link"), L("source")], [[p.created_time.strftime("%Y-%m-%d %H:%M") if p.created_time else "", p.kind, p.message, p.permalink, p.shared_link] for p in m.posts], [18, 8, 80, 45, 45], rtl)
    _sheet(wb, names["activity"], [L("month"), L("count")], [[a, b] for a, b in m.monthly], [14, 10], rtl)
    _sheet(wb, names["media"], [L("kind"), L("url"), "SHA-256", "pHash", "dHash", "W×H", L("dup"), L("status"), "EXIF"], [[x.kind, x.source_url, x.sha256, x.phash, x.dhash, f"{x.width}×{x.height}", x.duplicate_group or "", V(x.status), "; ".join(f"{k}={v}" for k, v in (x.metadata_json or {}).items())] for x in m.media], [14, 50, 66, 18, 18, 11, 10, 12, 40], rtl)
    _sheet(wb, names["sources"], [L("url"), L("kind"), L("status"), "HTTP", L("fetched"), L("title_col"), "SHA-256", L("notes")], [[s.url, V(s.source_type), V(s.status), s.http_status or "", s.fetched_at.strftime("%Y-%m-%d %H:%M"), s.title, s.content_sha256, s.error_message] for s in m.sources], [50, 16, 16, 8, 18, 30, 66, 30], rtl)
    _sheet(wb, names["limits"], [L("field"), L("notes")], [[x.get("code", ""), x.get("message", "")] for x in (inv.limitations or [])], [28, 100], rtl)

    # Formula-driven KPIs (recalculate automatically if analysts edit the sheets)
    r0 = len(info) + 5
    ws.cell(r0 - 1, 1, L("summary")).font = Font(bold=True, color="1F3A5F")
    c = names["contacts"]
    kpis = [
        (names["facts"], f"=MAX(COUNTA('{names['facts']}'!A:A)-1,0)"),
        (names["unverified"], f"=MAX(COUNTA('{names['unverified']}'!A:A)-1,0)"),
        (names["obs"], f"=MAX(COUNTA('{names['obs']}'!A:A)-1,0)"),
        (names["contacts"], f"=MAX(COUNTA('{c}'!A:A)-1,0)"),
        (f"{names['contacts']} - {V('verified')}", f"=COUNTIF('{c}'!G:G,\"{V('verified')}\")"),
        (f"{names['contacts']} - {V('high')}", f"=COUNTIF('{c}'!H:H,\"{V('high')}\")"),
        (names["posts"], f"=MAX(COUNTA('{names['posts']}'!A:A)-1,0)"),
        (names["media"], f"=MAX(COUNTA('{names['media']}'!A:A)-1,0)"),
        (names["sources"], f"=MAX(COUNTA('{names['sources']}'!A:A)-1,0)"),
    ]
    for i, (k, f) in enumerate(kpis):
        ws.cell(r0 + i, 1, k).font = Font(bold=True)
        ws.cell(r0 + i, 2, f)
    ws.cell(r0 + len(kpis) + 1, 1, L("disclaimer")).alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=r0 + len(kpis) + 1, start_column=1, end_row=r0 + len(kpis) + 1, end_column=2)
    ws.row_dimensions[r0 + len(kpis) + 1].height = 75
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 90
    wb.properties.title = inv.reference
    wb.properties.creator = m.app
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
