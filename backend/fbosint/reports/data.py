"""Assemble the report model shared by the PDF and Excel generators."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import APP_NAME, __version__
from ..models import DataPoint, Investigation, MediaItem, Post, Source, utcnow

LABELS = {
    "en": {
        "title": "Public Source Intelligence Report",
        "reference": "Reference", "date": "Investigation date", "generated": "Report generated", "target": "Profile URL",
        "target_input": "Input", "object_type": "Object type", "status": "Status", "purpose": "Purpose", "legal_basis": "Legal basis",
        "investigator": "Investigator", "summary": "Executive summary",
        "facts": "1. Verified facts", "unverified": "2. Unverified information", "observations": "3. Analytical observations",
        "availability": "4. Field availability", "contacts": "5. Public contact information", "activity": "6. Public activity summary",
        "posts": "Public posts (most recent)", "media": "7. Media references", "sources": "8. Sources", "limitations": "9. Data limitations",
        "field": "Field", "value": "Value", "source": "Source", "collected": "Collected", "verification": "Verification", "confidence": "Confidence",
        "method": "Method", "month": "Month", "count": "Posts", "date_col": "Date", "message": "Message", "link": "Link",
        "kind": "Type", "hash": "SHA-256 / pHash", "dup": "Duplicate group", "url": "URL", "fetched": "Fetched", "title_col": "Title",
        "none": "None", "notes": "Notes", "category": "Category",
        "disclaimer": "This report contains only information obtained through Meta's official Graph API with an authorised token, public URLs supplied by the investigator, and manual observations recorded with their source. Facts, unverified information and analytical observations are listed separately. No facial recognition was performed and no association between profiles is assumed.",
        "summary_tpl": "{facts} verified facts, {unverified} unverified items, {obs} analytical observations, {contacts} public contact items, {posts} public posts, {media} media items and {sources} sources.",
        "page": "Page",
    },
    "ar": {
        "title": "تقرير استخبارات المصادر العامة",
        "reference": "الرقم المرجعي", "date": "تاريخ التحقيق", "generated": "تاريخ إصدار التقرير", "target": "رابط الملف",
        "target_input": "المدخل", "object_type": "نوع الكيان", "status": "الحالة", "purpose": "الغرض", "legal_basis": "الأساس النظامي",
        "investigator": "المحقق", "summary": "الملخص التنفيذي",
        "facts": "1. حقائق موثقة", "unverified": "2. معلومات غير موثقة", "observations": "3. ملاحظات تحليلية",
        "availability": "4. حالة توفر الحقول", "contacts": "5. معلومات الاتصال العامة", "activity": "6. ملخص النشاط العام",
        "posts": "المنشورات العامة (الأحدث)", "media": "7. مراجع الوسائط", "sources": "8. المصادر", "limitations": "9. قيود البيانات",
        "field": "الحقل", "value": "القيمة", "source": "المصدر", "collected": "تاريخ الجمع", "verification": "التحقق", "confidence": "الثقة",
        "method": "الطريقة", "month": "الشهر", "count": "المنشورات", "date_col": "التاريخ", "message": "النص", "link": "الرابط",
        "kind": "النوع", "hash": "SHA-256 / pHash", "dup": "مجموعة التكرار", "url": "الرابط", "fetched": "تاريخ الجلب", "title_col": "العنوان",
        "none": "لا يوجد", "notes": "ملاحظات", "category": "الفئة",
        "disclaimer": "يحتوي هذا التقرير فقط على معلومات تم الحصول عليها عبر واجهة Meta Graph API الرسمية باستخدام رمز وصول مصرح به، وروابط عامة قدمها المحقق، وملاحظات يدوية مسجلة مع مصدرها. تم فصل الحقائق والمعلومات غير الموثقة والملاحظات التحليلية. لم يتم إجراء أي تعرف على الوجوه ولا يُفترض أي ارتباط بين الحسابات.",
        "summary_tpl": "{facts} حقيقة موثقة، {unverified} معلومة غير موثقة، {obs} ملاحظة تحليلية، {contacts} معلومة اتصال عامة، {posts} منشور عام، {media} عنصر وسائط، {sources} مصدر.",
        "page": "صفحة",
    },
}

VALUE_LABELS = {
    "ar": {
        "verified": "موثق", "unverified": "غير موثق", "conflicting": "متعارض", "high": "عالية", "medium": "متوسطة", "low": "منخفضة",
        "available": "متاح", "undisclosed": "غير مُفصح عنه", "unavailable": "غير متاح", "completed": "مكتمل", "partial": "جزئي",
        "failed": "فشل", "running": "قيد التنفيذ", "pending": "قيد الانتظار", "page": "صفحة", "user": "مستخدم", "unknown": "غير معروف",
        "fetched": "تم الجلب", "blocked_policy": "محظور بالسياسة", "blocked_robots": "محظور بـ robots.txt", "not_permitted": "غير مسموح",
        "rate_limited": "تجاوز حد الطلبات", "not_found": "غير موجود/غير متاح", "error": "خطأ", "not_configured": "غير مُعد", "auth_error": "خطأ مصادقة",
        "graph_api": "Graph API", "user_supplied_url": "رابط مقدم من المحقق", "official_website": "الموقع الرسمي", "manual": "إدخال يدوي",
        "input_url": "رابط المدخل", "analysis": "تحليل", "investigator_upload": "رفع المحقق",
    },
    "en": {},
}

FIELD_LABELS_AR = {
    "name": "الاسم", "username": "اسم المستخدم", "link": "الرابط", "about": "نبذة", "description": "الوصف", "biography": "السيرة",
    "category": "التصنيف", "website": "الموقع الإلكتروني", "email": "البريد الإلكتروني", "phone": "الهاتف", "address": "العنوان",
    "location": "الموقع", "hometown": "المدينة الأصلية", "founded": "سنة التأسيس", "followers_count": "عدد المتابعين", "fan_count": "عدد المعجبين",
    "profile_picture": "صورة الملف", "cover_photo": "صورة الغلاف", "workplace": "جهة العمل", "education": "التعليم", "page_id": "معرّف الصفحة",
    "user_id": "معرّف المستخدم", "profile_url": "رابط الملف", "numeric_id": "المعرّف الرقمي", "related_link": "رابط ذو صلة",
    "shared_link": "رابط تمت مشاركته", "organization_name": "اسم المنشأة", "web_description": "وصف الموقع", "activity_summary": "ملخص النشاط",
    "image_reuse": "إعادة استخدام الصور", "photo": "صورة", "web_image": "صورة من موقع", "uploaded": "مرفوعة من المحقق", "video": "فيديو", "related_links": "روابط ذات صلة", "verification_status": "حالة التوثيق",
}


def label(lang: str, key: str) -> str:
    return LABELS.get(lang, LABELS["en"]).get(key, key)


def value_label(lang: str, v: str) -> str:
    return VALUE_LABELS.get(lang, {}).get(v, v)


def field_label(lang: str, f: str) -> str:
    return FIELD_LABELS_AR.get(f, f) if lang == "ar" else f.replace("_", " ").capitalize()


@dataclass
class ReportModel:
    lang: str
    inv: Investigation
    investigator: str
    generated_at: datetime
    facts: list[DataPoint] = field(default_factory=list)
    unverified: list[DataPoint] = field(default_factory=list)
    observations: list[DataPoint] = field(default_factory=list)
    unavailable: list[DataPoint] = field(default_factory=list)
    contacts: list[DataPoint] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)
    monthly: list[tuple[str, int]] = field(default_factory=list)
    media: list[MediaItem] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    app: str = f"{APP_NAME} {__version__}"

    @property
    def summary(self) -> str:
        return label(self.lang, "summary_tpl").format(
            facts=len(self.facts), unverified=len(self.unverified), obs=len(self.observations), contacts=len(self.contacts),
            posts=len(self.posts), media=len(self.media), sources=len(self.sources),
        )


def build_report(db: Session, inv: Investigation, lang: str = "ar") -> ReportModel:
    points = list(db.scalars(select(DataPoint).where(DataPoint.investigation_id == inv.id).order_by(DataPoint.category, DataPoint.field, DataPoint.id)))
    posts = list(db.scalars(select(Post).where(Post.investigation_id == inv.id, Post.kind == "post").order_by(Post.created_time.desc())))
    m = ReportModel(lang=lang, inv=inv, investigator=inv.created_by.username if inv.created_by else "", generated_at=utcnow())
    for p in points:
        if p.availability != "available":
            m.unavailable.append(p)
            continue
        if p.category == "contact":
            m.contacts.append(p)
        if p.classification == "analytical_observation":
            m.observations.append(p)
        elif p.classification == "fact":
            m.facts.append(p)
        else:
            m.unverified.append(p)
    m.posts = posts
    m.monthly = sorted(Counter(p.created_time.strftime("%Y-%m") for p in posts if p.created_time).items())
    m.media = list(db.scalars(select(MediaItem).where(MediaItem.investigation_id == inv.id).order_by(MediaItem.id)))
    m.sources = list(db.scalars(select(Source).where(Source.investigation_id == inv.id).order_by(Source.id)))
    return m
