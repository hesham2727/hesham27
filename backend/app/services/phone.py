"""Offline phone-number analysis using Google's libphonenumber metadata.

Important limitations (shown to the user in the result):
* The operator returned is the ORIGINAL allocation of the number range.
  Egypt supports Mobile Number Portability, so the current operator may differ.
* No subscriber identity, address or live location can be derived from a number.
"""
from __future__ import annotations

from datetime import datetime, timezone

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType, carrier, geocoder, timezone as pn_timezone

from .. import __version__

NUMBER_TYPE_AR = {
    PhoneNumberType.MOBILE: "هاتف محمول",
    PhoneNumberType.FIXED_LINE: "خط أرضي",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "أرضي أو محمول",
    PhoneNumberType.TOLL_FREE: "رقم مجاني",
    PhoneNumberType.PREMIUM_RATE: "رقم بتعرفة مميزة",
    PhoneNumberType.SHARED_COST: "تكلفة مشتركة",
    PhoneNumberType.VOIP: "اتصال عبر الإنترنت (VoIP)",
    PhoneNumberType.PERSONAL_NUMBER: "رقم شخصي",
    PhoneNumberType.PAGER: "جهاز نداء",
    PhoneNumberType.UAN: "رقم موحد",
    PhoneNumberType.VOICEMAIL: "بريد صوتي",
    PhoneNumberType.UNKNOWN: "غير معروف",
}

NUMBER_TYPE_CODE = {v: k for k, v in vars(PhoneNumberType).items() if isinstance(v, int)}

# Arabic display names for Egyptian mobile operators (range allocation).
EG_OPERATOR_AR = {
    "Vodafone": "فودافون مصر",
    "Etisalat": "اتصالات مصر (e&)",
    "Orange": "أورنج مصر",
    "TE": "WE – المصرية للاتصالات",
}

NOT_DERIVABLE = [
    "اسم صاحب الخط أو هويته",
    "العنوان السكني",
    "الموقع الجغرافي الحالي أو السابق",
    "المشغّل الحالي بعد نقل الرقم (MNP)",
    "حالة الخط (نشط / موقوف)",
]

CURRENT_LOCATION_UNAVAILABLE = "CURRENT LOCATION UNAVAILABLE – NO AUTHORIZED LOCATION SOURCE."
CURRENT_LOCATION_UNAVAILABLE_AR = "الموقع الحالي غير متاح – لا يوجد مصدر موقع مُصرَّح به."


def normalize_digits(raw: str) -> str:
    """Convert Arabic-Indic / Persian digits to ASCII and strip spaces."""
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return raw.translate(trans).strip()


def analyze_number(raw: str, default_region: str = "EG") -> dict:
    cleaned = normalize_digits(raw or "")
    result: dict = {
        "input": raw,
        "normalized_input": cleaned,
        "default_region": default_region,
        "parsed": False,
        "is_possible": False,
        "is_valid": False,
        "e164": "",
        "international_format": "",
        "national_format": "",
        "country_code": None,
        "region_code": "",
        "number_type": "UNKNOWN",
        "number_type_ar": NUMBER_TYPE_AR[PhoneNumberType.UNKNOWN],
        "original_operator": "",
        "original_operator_ar": "",
        "geographic_area": "",
        "time_zones": [],
        "warnings": [],
        "not_derivable": NOT_DERIVABLE,
        "current_location": CURRENT_LOCATION_UNAVAILABLE,
        "current_location_ar": CURRENT_LOCATION_UNAVAILABLE_AR,
        "data_source": f"libphonenumber metadata via python 'phonenumbers' {phonenumbers.__version__}",
        "engine_version": __version__,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not cleaned:
        result["warnings"].append("لم يتم إدخال رقم")
        return result
    try:
        num = phonenumbers.parse(cleaned, default_region)
    except NumberParseException as exc:
        result["warnings"].append(f"تعذر تحليل الرقم: {exc}")
        return result

    result["parsed"] = True
    result["is_possible"] = phonenumbers.is_possible_number(num)
    result["is_valid"] = phonenumbers.is_valid_number(num)
    result["country_code"] = num.country_code
    result["region_code"] = phonenumbers.region_code_for_number(num) or ""
    ntype = phonenumbers.number_type(num)
    result["number_type"] = NUMBER_TYPE_CODE.get(ntype, "UNKNOWN")
    result["number_type_ar"] = NUMBER_TYPE_AR.get(ntype, NUMBER_TYPE_AR[PhoneNumberType.UNKNOWN])

    if result["is_possible"]:
        # E.164 is only reported for VALID numbers to avoid implying the number exists.
        if result["is_valid"]:
            result["e164"] = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        result["international_format"] = phonenumbers.format_number(
            num, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        result["national_format"] = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.NATIONAL)

    if not result["is_valid"]:
        result["warnings"].append("الرقم غير صالح وفق خطة الترقيم المعتمدة لهذه الدولة")
        return result

    op = carrier.name_for_number(num, "en")
    result["original_operator"] = op
    result["original_operator_ar"] = EG_OPERATOR_AR.get(op, op)
    area = geocoder.description_for_number(num, "ar") or geocoder.description_for_number(num, "en")
    result["geographic_area"] = area
    result["time_zones"] = list(pn_timezone.time_zones_for_number(num))

    if ntype in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE) and op:
        result["warnings"].append(
            "المشغّل المعروض هو المشغّل الأصلي لنطاق الرقم فقط؛ قد يكون الرقم منقولاً لمشغّل آخر (MNP)."
        )
    if ntype == PhoneNumberType.FIXED_LINE and area:
        result["warnings"].append("المنطقة المعروضة هي منطقة كود الخط الأرضي وليست موقع المشترك.")
    if result["region_code"] and result["region_code"] != default_region:
        result["warnings"].append(f"الرقم تابع لدولة أخرى ({result['region_code']}).")
    return result


def to_e164_or_empty(raw: str, default_region: str = "EG") -> str:
    try:
        num = phonenumbers.parse(normalize_digits(raw or ""), default_region)
    except NumberParseException:
        return ""
    if not phonenumbers.is_possible_number(num):
        return ""
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
