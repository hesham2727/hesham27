"""Phase 2: investigation engine end-to-end against fake Graph API and websites."""
import httpx
import pytest

from fbosint.models import DataPoint, Investigation, MediaItem, Post, Source, User
from fbosint.security.passwords import hash_password
from fbosint.services import engine
from fbosint.services.app_config import store_secret, update_meta_config

from .fakes import FakeGraph, FakeWeb, public_resolver


@pytest.fixture()
def wired(db):
    fg, fw = FakeGraph(), FakeWeb()
    engine.deps = engine.EngineDeps(graph_transport=httpx.MockTransport(lambda r: fg(r)), web_transport=httpx.MockTransport(fw), resolver=public_resolver, sleep=lambda s: None)
    u = User(username="inv1", password_hash=hash_password("x"), role="investigator")
    db.add(u); db.commit()
    yield db, fg, fw, u
    engine.deps = engine.EngineDeps()


def new_inv(db, user, target, ttype="profile_url", extra=None, **opts):
    inv = Investigation(reference=f"INV-T-{target[-6:]}-{ttype[:3]}", target_input=target, target_type=ttype, purpose="Due diligence on supplier", extra_urls=extra or [], options={"collect_comments": True, **opts}, created_by_id=user.id)
    db.add(inv); db.commit()
    return inv


def run(db, inv):
    engine.InvestigationRunner(db, inv).run()
    db.refresh(inv)
    return inv


def dps(db, inv, **flt):
    q = db.query(DataPoint).filter_by(investigation_id=inv.id, **flt)
    return q.all()


def test_page_investigation_full(wired):
    db, fg, fw, u = wired
    update_meta_config(db, "123", "appsecret", "PAGE_TOKEN", "")
    inv = run(db, new_inv(db, u, "https://www.facebook.com/qusoorfacades", "page_url", ["https://directory.example.org/qusoor"]))
    assert inv.status == "completed", inv.limitations
    assert inv.object_type == "page" and inv.graph_object_id == "104958162837"
    name = dps(db, inv, field="name")[0]
    assert (name.value, name.verification_status, name.confidence, name.classification) == ("Qusoor Facades Co.", "verified", "high", "fact")
    # official website auto-followed + directory -> email corroborated by graph & 2 domains
    emails = {d.normalized_value: d for d in dps(db, inv, field="email")}
    assert "info@qusoor.example.sa" in emails and "sales@qusoor.example.sa" in emails
    assert emails["sales@qusoor.example.sa"].verification_status == "unverified"
    assert emails["sales@qusoor.example.sa"].confidence == "medium"
    web_info = [d for d in dps(db, inv, field="email") if d.source_type != "graph_api" and d.normalized_value == "info@qusoor.example.sa"]
    assert web_info and all(d.verification_status == "verified" for d in web_info)  # corroborated by Graph
    text_email = [d for d in dps(db, inv, field="email") if d.extraction_method == "text"][0]
    assert text_email.confidence == "low"
    # undisclosed field (page has no 'founded')
    founded = dps(db, inv, field="founded")[0]
    assert founded.availability == "undisclosed"
    # posts with pagination + comments
    posts = db.query(Post).filter_by(investigation_id=inv.id, kind="post").order_by(Post.created_time).all()
    assert len(posts) == 3 and posts[0].shared_link == "https://news.example.org/project"
    assert db.query(Post).filter_by(investigation_id=inv.id, kind="comment").count() >= 1
    # media: profile pic, cover, photo, og:image ; pic == p1 == logo -> one duplicate group
    media = db.query(MediaItem).filter_by(investigation_id=inv.id).all()
    assert {m.kind for m in media} >= {"profile_picture", "cover_photo", "photo", "web_image"}
    assert all(m.status == "stored" and len(m.phash) == 16 for m in media)
    groups = {m.duplicate_group for m in media if m.duplicate_group}
    assert len(groups) == 1
    # related link recorded but not associated
    rel = dps(db, inv, field="related_link")[0]
    assert rel.notes == "association_with_target_not_verified" and rel.classification == "unverified"
    obs = dps(db, inv, category="observation")
    assert {o.field for o in obs} >= {"activity_summary", "image_reuse", "related_links"}
    assert all(o.classification == "analytical_observation" for o in obs)
    # sources registered; no access token leaked in stored URLs
    srcs = db.query(Source).filter_by(investigation_id=inv.id).all()
    assert any(s.source_type == "official_website" and s.status == "fetched" for s in srcs)
    assert not any("PAGE_TOKEN" in (s.url + s.final_url) for s in srcs)
    assert not any("PAGE_TOKEN" in d.source_url for d in dps(db, inv))
    # robots.txt honoured: requests to website include robots check
    assert any(r.url.path == "/robots.txt" for r in fw.requests)


def test_personal_profile_is_unavailable(wired):
    db, fg, fw, u = wired
    update_meta_config(db, None, None, "PAGE_TOKEN", None)
    inv = run(db, new_inv(db, u, "https://www.facebook.com/john.doe.123"))
    assert inv.status == "partial"
    assert any(l["code"] == "graph_not_found" for l in inv.limitations)
    fields = dps(db, inv, category="profile")
    assert fields and all(d.availability == "unavailable" for d in fields if d.source_type == "graph_api")
    ident = dps(db, inv, field="username")[0]
    assert ident.value == "john.doe.123" and ident.classification == "fact"
    assert db.query(Post).filter_by(investigation_id=inv.id).count() == 0


def test_no_token_configured(wired):
    db, fg, fw, u = wired
    inv = run(db, new_inv(db, u, "qusoorfacades", "username"))
    assert inv.status == "partial" and inv.limitations[0]["code"] == "graph_not_configured"
    assert not fg.requests  # Graph never contacted without a token


@pytest.mark.parametrize("mode,code", [("rate_limited", "graph_rate_limited"), ("bad_token", "graph_auth_error")])
def test_graph_failures_recorded(wired, mode, code):
    db, fg, fw, u = wired
    fg.mode = mode
    update_meta_config(db, None, None, "PAGE_TOKEN", None)
    inv = run(db, new_inv(db, u, "https://www.facebook.com/qusoorfacades", "page_url"))
    assert inv.status == "partial" and inv.limitations[0]["code"] == code
    src = db.query(Source).filter_by(investigation_id=inv.id, source_type="graph_api").one()
    assert src.status == mode.replace("bad_token", "auth_error")


def test_posts_permission_error_keeps_profile(wired):
    db, fg, fw, u = wired
    fg.mode = "posts_forbidden"
    update_meta_config(db, None, None, "PAGE_TOKEN", None)
    inv = run(db, new_inv(db, u, "https://www.facebook.com/qusoorfacades", "page_url"))
    assert inv.status == "partial"
    assert any(l["code"] == "graph_posts_not_permitted" for l in inv.limitations)
    assert dps(db, inv, field="name")[0].value == "Qusoor Facades Co."


def test_authorized_account(wired):
    db, fg, fw, u = wired
    store_secret(db, "meta_user_token", "USER_TOKEN", u.id)
    inv = run(db, new_inv(db, u, "me", "authorized_account"))
    assert inv.object_type == "user" and inv.graph_object_id == "777"
    assert dps(db, inv, field="name")[0].value == "Authorized Person"
    work = dps(db, inv, field="workplace")[0]
    assert work.availability == "unavailable" and work.notes == "removed_from_graph_api"
    assert db.query(Post).filter_by(investigation_id=inv.id, kind="post").count() == 1


def test_authorized_account_not_connected(wired):
    db, fg, fw, u = wired
    inv = run(db, new_inv(db, u, "me", "authorized_account"))
    assert inv.status == "partial"


def test_facebook_urls_not_enriched_and_rerun_keeps_manual(wired):
    db, fg, fw, u = wired
    inv = new_inv(db, u, "qusoorfacades", "username", ["https://www.facebook.com/qusoorfacades/about", "http://localhost/x"])
    db.add(DataPoint(investigation_id=inv.id, category="observation", field="note", value="manual", source_url="https://x.example/", source_type="manual"))
    db.commit()
    run(db, inv)
    statuses = {s.url: s.status for s in db.query(Source).filter_by(investigation_id=inv.id)}
    assert statuses["https://www.facebook.com/qusoorfacades/about"] == "blocked_policy"
    assert statuses["http://localhost/x"] == "blocked_policy"
    assert not any(r.url.host.endswith("facebook.com") for r in fw.requests)
    run(db, inv)  # re-run
    assert len(dps(db, inv, source_type="manual")) == 1
    assert len(dps(db, inv, field="username", source_type="input_url")) == 1
