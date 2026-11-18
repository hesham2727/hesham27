"""Phase 2: URL parsing, Graph client, safe fetcher, extraction, media, verification."""
import httpx
import pytest

from fbosint.services.extraction import extract_page, normalize
from fbosint.services.graph_client import (
    GraphAuthError, GraphError, GraphNotConfigured, GraphNotFoundError, GraphPermissionError,
    GraphRateLimitError, MetaGraphClient,
)
from fbosint.services.media import MediaError, analyse_image, group_duplicates, hamming
from fbosint.services.safe_fetch import FetchBlocked, SafeFetcher
from fbosint.services.url_parser import InvalidTargetError, parse_target

from .fakes import SITE_HTML, FakeGraph, FakeWeb, make_image, public_resolver


# ---------------- URL parser ----------------
@pytest.mark.parametrize("raw,ident,kind,tt", [
    ("https://www.facebook.com/qusoorfacades", "qusoorfacades", "username", "profile_url"),
    ("facebook.com/qusoorfacades/about", "qusoorfacades", "username", "profile_url"),
    ("https://m.facebook.com/profile.php?id=100012345678", "100012345678", "numeric_id", "profile_url"),
    ("https://www.facebook.com/people/John-Doe/100012345678/", "100012345678", "numeric_id", "profile_url"),
    ("https://www.facebook.com/pages/Some-Page/123456789", "123456789", "numeric_id", "page_url"),
    ("https://www.facebook.com/pg/qusoorfacades/posts/", "qusoorfacades", "username", "profile_url"),
    ("https://fb.com/john.doe.5", "john.doe.5", "username", "profile_url"),
    ("@qusoor.facades", "qusoor.facades", "username", "username"),
    ("100012345678", "100012345678", "numeric_id", "numeric_id"),
    ("me", "me", "me", "authorized_account"),
])
def test_parse_valid(raw, ident, kind, tt):
    t = parse_target(raw)
    assert (t.identifier, t.id_kind, t.target_type) == (ident, kind, tt)


@pytest.mark.parametrize("raw,code", [
    ("", "empty_target"),
    ("https://evil.com/qusoor", "not_a_facebook_url"),
    ("https://www.facebook.com/groups/12345", "unsupported_facebook_url"),
    ("https://www.facebook.com/share/abc", "unsupported_facebook_url"),
    ("https://www.facebook.com/", "no_profile_in_url"),
    ("https://www.facebook.com/profile.php", "profile_id_missing"),
    ("javascript:alert(1)", "invalid_username"),
    ("ftp://facebook.com/x", "invalid_scheme"),
    ("https://user:pw@facebook.com/x", "invalid_url"),
    ("<script>", "invalid_characters"),
    ("a b c", "invalid_username"),
    ("https://facebook.com.evil.com/x", "not_a_facebook_url"),
])
def test_parse_invalid(raw, code):
    with pytest.raises(InvalidTargetError) as e:
        parse_target(raw)
    assert e.value.code == code


def test_parse_page_hint():
    assert parse_target("https://www.facebook.com/qusoorfacades", "page_url").hint == "page"


# ---------------- Graph client ----------------
def gclient(mode="ok", **kw):
    fg = FakeGraph(mode)
    return MetaGraphClient("TOKEN123", app_secret="s3cr3t", transport=httpx.MockTransport(fg), sleep=lambda s: None, **kw), fg


def test_graph_page_drops_bad_fields_and_sends_proof():
    c, fg = gclient()
    res, dropped = c.get_page("qusoorfacades")
    assert res.data["name"] == "Qusoor Facades Co." and dropped == ["verification_status"]
    assert all(r.url.params.get("appsecret_proof") for r in fg.requests)
    assert "access_token" not in res.url and "appsecret_proof" not in res.url
    assert res.usage["x-app-usage"]["call_count"] == 5


def test_graph_pagination_validated():
    c, _ = gclient()
    items, _ = c.page_posts("104958162837", 10)
    assert [i["id"][-1] for i in items] == ["1", "2", "3"]
    with pytest.raises(GraphError):
        c._request("https://evil.example.com/v23.0/x")


@pytest.mark.parametrize("mode,exc", [("rate_limited", GraphRateLimitError), ("bad_token", GraphAuthError)])
def test_graph_error_mapping(mode, exc):
    c, _ = gclient(mode)
    with pytest.raises(exc):
        c.get_page("qusoorfacades")


def test_graph_not_found_and_permission():
    c, _ = gclient("posts_forbidden")
    with pytest.raises(GraphNotFoundError):
        c.get_page("john.doe.123")
    with pytest.raises(GraphPermissionError):
        c.page_posts("104958162837", 5)
    with pytest.raises(GraphNotConfigured):
        MetaGraphClient("")
    with pytest.raises(GraphError):
        c.get("../../etc/passwd?x=1")


def test_graph_retries_server_errors():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(500) if calls["n"] < 2 else httpx.Response(200, json={"id": "1"})
    c = MetaGraphClient("T", transport=httpx.MockTransport(h), sleep=lambda s: None)
    assert c.get("1").data == {"id": "1"} and calls["n"] == 2


# ---------------- Safe fetcher ----------------
def fetcher(**kw):
    return SafeFetcher("TestUA", transport=httpx.MockTransport(FakeWeb()), resolver=public_resolver, **kw)


def test_fetch_ok_and_redirect():
    r = fetcher().fetch("https://qusoor.example.sa/old")
    assert r.status_code == 200 and r.final_url == "https://qusoor.example.sa/" and len(r.sha256) == 64


@pytest.mark.parametrize("url,status", [
    ("http://localhost/admin", "blocked_policy"),
    ("http://127.0.0.1/", "blocked_policy"),
    ("http://[::1]/", "blocked_policy"),
    ("http://169.254.169.254/latest/meta-data", "blocked_policy"),
    ("https://intranet.example.com/", "blocked_policy"),
    ("https://www.facebook.com/someone", "blocked_policy"),
    ("https://scontent.xx.fbcdn.net/a.jpg", "blocked_policy"),
    ("file:///etc/passwd", "blocked_policy"),
    ("https://x.example.com:22/", "blocked_policy"),
    ("https://redirect-internal.example.com/", "blocked_policy"),
    ("https://blocked.example.com/page", "blocked_robots"),
    ("https://huge.example.com/", "error"),
])
def test_fetch_blocked(url, status):
    with pytest.raises(FetchBlocked) as e:
        fetcher().fetch(url)
    assert e.value.status == status


# ---------------- Extraction ----------------
def test_extract_contacts():
    ex = extract_page(SITE_HTML, "https://qusoor.example.sa/")
    got = {(i.kind, normalize(i.kind, i.value), i.method) for i in ex.items}
    assert ("email", "sales@qusoor.example.sa", "json_ld") in got
    assert ("email", "info@qusoor.example.sa", "mailto") in got
    assert ("email", "jobs@qusoor.example.sa", "text") in got
    assert ("phone", "+966125550100", "json_ld") in got
    assert not any(i.value == "hidden@tracker.example.net" for i in ex.items)  # inside <script>
    assert any(i.kind == "address" and "Makkah" in i.value for i in ex.items)
    assert any(i.kind == "social_link" and "linkedin" in i.value for i in ex.items)
    assert ex.title.startswith("Qusoor Facades")


def test_extract_malformed_is_safe():
    ex = extract_page("<html><script type='application/ld+json'>{bad json</script><a href='mailto:not-an-email'>", "https://x/")
    assert not [i for i in ex.items if i.kind == "email"]


def test_normalize_phone():
    assert normalize("phone", "00966 12-555 0100") == normalize("phone", "+966125550100")


# ---------------- Media ----------------
def test_media_hash_duplicates_and_exif():
    from PIL import Image
    a = make_image(1)
    a_jpg = make_image(1, fmt="JPEG")
    b = make_image(7)
    ia, ij, ib = analyse_image(a), analyse_image(a_jpg), analyse_image(b)
    assert ia.mime_type == "image/png" and ij.mime_type == "image/jpeg"
    assert hamming(ia.phash, ij.phash) <= 8           # same picture, different encoding
    assert hamming(ia.phash, ib.phash) > 8
    groups = group_duplicates([(1, ia.sha256, ia.phash), (2, ij.sha256, ij.phash), (3, ib.sha256, ib.phash)])
    assert groups[1] == groups[2] == 1 and groups[3] is None
    exif = Image.Exif(); exif[0x010F] = "Canon"; exif[0x8825] = {1: "N"}
    ie = analyse_image(make_image(3, fmt="JPEG", exif=exif.tobytes()))
    assert ie.metadata.get("Make") == "Canon" and ie.metadata.get("gps_extracted") is False
    with pytest.raises(MediaError):
        analyse_image(b"<svg onload=alert(1)>")
