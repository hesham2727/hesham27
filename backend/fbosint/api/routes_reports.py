"""PDF / Excel report export."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Investigation, ReportExport, User
from ..reports.data import build_report
from ..reports.excel import render_xlsx
from ..reports.pdf import render_pdf
from ..services.audit import audit
from .deps import client_ip, current_user

router = APIRouter(prefix="/api", tags=["reports"])
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def generate(db: Session, inv: Investigation, fmt: str, lang: str) -> bytes:
    model = build_report(db, inv, lang)
    return render_pdf(model) if fmt == "pdf" else render_xlsx(model)


@router.get("/investigations/{inv_id}/report")
def export_report(
    inv_id: int,
    request: Request,
    format: str = Query("pdf", pattern=r"^(pdf|xlsx)$"),
    lang: str = Query("ar", pattern=r"^(ar|en)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(404, "investigation_not_found")
    if inv.status in ("pending", "running"):
        raise HTTPException(409, "investigation_not_finished")
    data = generate(db, inv, format, lang)
    digest = hashlib.sha256(data).hexdigest()
    db.add(ReportExport(investigation_id=inv.id, format=format, language=lang, sha256=digest, size_bytes=len(data), created_by_id=user.id))
    db.commit()
    audit(db, "report_exported", user, "investigation", inv.reference, client_ip(request), details={"format": format, "lang": lang, "sha256": digest})
    filename = f"{inv.reference}-{lang}.{format}"
    return Response(data, media_type=MIME[format], headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Report-SHA256": digest})
