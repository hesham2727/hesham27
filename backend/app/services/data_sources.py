"""Built-in catalogue of documented, free data sources.

Every external source the application touches (or that operators are guided to
consult manually) is listed here with URL, content, limitations, update
frequency and license/attribution. The application performs NO automated
scraping of any website.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import DataSource

BUILTIN_SOURCES: list[dict] = [
    {
        "key": "libphonenumber",
        "name": "Google libphonenumber (Python 'phonenumbers' package)",
        "url": "https://github.com/google/libphonenumber",
        "information": "صلاحية الرقم، نوعه (محمول/أرضي)، الصيغة الدولية E.164، المشغّل الأصلي لنطاق الرقم، منطقة كود الخط الأرضي، المنطقة الزمنية.",
        "limitations": "بيانات وصفية لخطط الترقيم فقط. لا تحتوي على أسماء المشتركين أو عناوينهم أو مواقعهم. المشغّل هو المشغّل الأصلي للنطاق وقد يختلف بعد نقل الرقم (MNP).",
        "update_frequency": "تُحدَّث مع إصدارات المكتبة (عادة عدة مرات سنوياً) – التحديث بترقية الحزمة.",
        "license": "Apache License 2.0. لا يشترط إسناداً داخل الواجهة.",
        "access_method": "bundled",
    },
    {
        "key": "ntra_egypt",
        "name": "الجهاز القومي لتنظيم الاتصالات (NTRA) – مصر",
        "url": "https://www.tra.gov.eg/",
        "information": "معلومات تنظيمية عامة: المشغّلون المرخّصون، خطة الترقيم الوطنية، القرارات والإعلانات.",
        "limitations": "لا يوفر استعلاماً عن بيانات المشتركين. يُستخدم للمراجعة اليدوية فقط؛ لا يقوم التطبيق بأي جمع آلي من الموقع.",
        "update_frequency": "غير محدد – حسب نشر الجهاز.",
        "license": "محتوى موقع حكومي؛ لا توجد رخصة بيانات مفتوحة معلنة. يُذكر المصدر عند الاقتباس، ويُراجع إشعار الاستخدام بالموقع.",
        "access_method": "manual",
    },
    {
        "key": "osm_tiles",
        "name": "OpenStreetMap Standard Tile Layer",
        "url": "https://operations.osmfoundation.org/policies/tiles/",
        "information": "صور خرائط الأساس المعروضة في الخريطة التفاعلية.",
        "limitations": "مخصص للاستخدام الخفيف؛ يُمنع التحميل المسبق الجماعي أو الاستخدام الكثيف. يتطلب إسناداً ظاهراً ومُعرّف تطبيق صحيح. يمكن استبدال مزوّد البلاطات من الإعدادات.",
        "update_frequency": "البيانات تُحدَّث باستمرار من مجتمع OSM.",
        "license": "البيانات: ODbL 1.0 – الإسناد إلزامي: © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).",
        "access_method": "api",
    },
    {
        "key": "nominatim",
        "name": "OpenStreetMap Nominatim (عكس الإحداثيات إلى عنوان) – اختياري",
        "url": "https://operations.osmfoundation.org/policies/nominatim/",
        "information": "عنوان تقريبي لنقطة موقع شاركها العميل بموافقته.",
        "limitations": "معطّل افتراضياً. حد أقصى طلب واحد في الثانية، يُمنع الاستخدام الجماعي، يتطلب مُعرّف تطبيق صحيح. يتم الطلب يدوياً لكل نقطة فقط.",
        "update_frequency": "مستمر (بيانات OSM).",
        "license": "ODbL 1.0 – الإسناد إلزامي: © OpenStreetMap contributors.",
        "access_method": "api",
    },
    {
        "key": "browser_geolocation_consent",
        "name": "موقع يشاركه صاحب الجهاز بموافقته (W3C Geolocation API)",
        "url": "https://www.w3.org/TR/geolocation/",
        "information": "إحداثيات لحظة المشاركة فقط مع دقة تقديرية، بعد موافقة صريحة من صاحب الجهاز.",
        "limitations": "يتطلب HTTPS وموافقة المستخدم في المتصفح. لقطة لحظية وليست تتبعاً مستمراً. الدقة تعتمد على الجهاز (GPS/Wi-Fi/الشبكة).",
        "update_frequency": "عند كل مشاركة جديدة فقط.",
        "license": "بيانات شخصية – تخضع لقانون حماية البيانات الشخصية المصري رقم 151 لسنة 2020 وسياسة الاحتفاظ بالتطبيق.",
        "access_method": "api",
    },
    {
        "key": "manual_public_web",
        "name": "مواقع ويب عامة (مراجعة يدوية)",
        "url": "",
        "information": "أي معلومة عامة يطّلع عليها المحقق يدوياً (موقع شركة، دليل أعمال، إعلان منشور...).",
        "limitations": "يُسجَّل يدوياً مع الرابط وتاريخ الاطلاع. يجب احترام شروط استخدام كل موقع وملف robots.txt. لا يقوم التطبيق بأي جمع آلي (Scraping).",
        "update_frequency": "حسب المصدر.",
        "license": "حسب شروط كل موقع؛ يُحفظ الرابط كإسناد.",
        "access_method": "manual",
    },
]


def seed_data_sources(db: Session) -> None:
    existing = {ds.key: ds for ds in db.query(DataSource).all()}
    for item in BUILTIN_SOURCES:
        row = existing.get(item["key"])
        if row is None:
            db.add(DataSource(is_builtin=True, **item))
        elif row.is_builtin:
            for k, v in item.items():
                setattr(row, k, v)
    db.commit()
