import pytest

from app.services.phone import CURRENT_LOCATION_UNAVAILABLE, analyze_number, to_e164_or_empty


@pytest.mark.parametrize(
    "raw,e164,op",
    [
        ("01001234567", "+201001234567", "Vodafone"),
        ("01112345678", "+201112345678", "Etisalat"),
        ("01212345678", "+201212345678", "Orange"),
        ("01512345678", "+201512345678", "TE"),
        ("+20 100 123 4567", "+201001234567", "Vodafone"),
        ("٠١٠٠١٢٣٤٥٦٧", "+201001234567", "Vodafone"),  # Arabic-Indic digits
    ],
)
def test_egypt_mobile(raw, e164, op):
    r = analyze_number(raw)
    assert r["is_valid"] is True
    assert r["e164"] == e164
    assert r["number_type"] == "MOBILE"
    assert r["original_operator"] == op
    assert any("MNP" in w for w in r["warnings"])  # portability caveat always shown


def test_landline_area():
    r = analyze_number("0223456789")
    assert r["is_valid"] and r["number_type"] == "FIXED_LINE"
    assert "Cairo" in r["geographic_area"]


@pytest.mark.parametrize("raw", ["0100123", "abc", "", "0000000000"])
def test_invalid(raw):
    r = analyze_number(raw)
    assert r["is_valid"] is False
    assert r["warnings"]


def test_never_claims_location():
    r = analyze_number("01001234567")
    assert r["current_location"] == CURRENT_LOCATION_UNAVAILABLE
    assert any("الموقع" in x for x in r["not_derivable"])


def test_foreign_number_flagged():
    r = analyze_number("+966501234567")
    assert r["is_valid"] and r["region_code"] == "SA"
    assert any("دولة أخرى" in w for w in r["warnings"])


def test_to_e164():
    assert to_e164_or_empty("01001234567") == "+201001234567"
    assert to_e164_or_empty("xx") == ""
