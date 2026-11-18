"""Fake Meta Graph API and fake public websites (httpx MockTransport)."""
import io
import json

import httpx
from PIL import Image, ImageDraw


def make_image(seed: int = 0, size=(200, 150), fmt="PNG", exif: bytes | None = None) -> bytes:
    img = Image.new("RGB", size, (240, 240, 240))
    d = ImageDraw.Draw(img)
    for i in range(6):
        x = (seed * 37 + i * 53) % size[0]
        y = (seed * 71 + i * 29) % size[1]
        d.rectangle([x, y, x + 40, y + 30], fill=((seed * 50 + i * 40) % 255, (i * 90) % 255, (seed * 20) % 255))
    buf = io.BytesIO()
    kw = {"exif": exif} if exif else {}
    img.save(buf, fmt, **kw)
    return buf.getvalue()


PAGE = {
    "id": "104958162837",
    "name": "Qusoor Facades Co.",
    "username": "qusoorfacades",
    "link": "https://www.facebook.com/qusoorfacades",
    "about": "Aluminium & glass facades",
    "category": "Construction Company",
    "category_list": [{"id": "1", "name": "Construction Company"}, {"id": "2", "name": "Glass Manufacturer"}],
    "website": "https://qusoor.example.sa",
    "emails": ["info@qusoor.example.sa"],
    "phone": "+966 12 555 0100",
    "single_line_address": "Makkah, Saudi Arabia",
    "location": {"city": "Makkah", "country": "Saudi Arabia"},
    "followers_count": 1200,
    "picture": {"data": {"url": "https://scontent.xx.fbcdn.net/pic.jpg", "is_silhouette": False}},
    "cover": {"source": "https://scontent.xx.fbcdn.net/cover.jpg", "id": "55"},
}

POSTS = [
    {"id": "104958162837_1", "message": "New curtain wall project in Jeddah", "created_time": "2026-03-01T10:00:00+0000", "permalink_url": "https://www.facebook.com/qusoorfacades/posts/1", "attachments": {"data": [{"type": "share", "unshimmed_url": "https://news.example.org/project"}]}},
    {"id": "104958162837_2", "message": "Structural glazing installation", "created_time": "2026-03-15T10:00:00+0000", "permalink_url": "https://www.facebook.com/qusoorfacades/posts/2"},
    {"id": "104958162837_3", "message": "Skylight delivered", "created_time": "2026-04-02T10:00:00+0000", "permalink_url": "https://www.facebook.com/qusoorfacades/posts/3"},
]

SITE_HTML = """<!doctype html><html><head><title>Qusoor Facades — Contact</title>
<meta name="description" content="Aluminium and glass facade contractor in Makkah">
<meta property="og:image" content="https://qusoor.example.sa/logo.png">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"Qusoor Facades","telephone":"+966 12 555 0100","email":"sales@qusoor.example.sa","address":{"streetAddress":"King Fahd Rd","addressLocality":"Makkah","addressCountry":"SA"},"sameAs":["https://www.linkedin.com/company/qusoor-example"]}</script>
</head><body><a href="mailto:info@qusoor.example.sa">Email us</a> <a href="tel:+966125550100">Call</a>
<p>Careers: jobs@qusoor.example.sa</p><script>var x="hidden@tracker.example.net";</script></body></html>"""

DIRECTORY_HTML = """<html><head><title>Directory listing</title></head><body>
<a href="mailto:info@qusoor.example.sa">info</a><a href="tel:00966125550100">phone</a></body></html>"""


class FakeGraph:
    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "graph.facebook.com"
        assert request.url.params.get("access_token")
        path = request.url.path.split("/", 2)[-1]
        usage = {"x-app-usage": json.dumps({"call_count": 5, "total_time": 1, "total_cputime": 1})}
        err = lambda code, msg, status=400, sub=None: httpx.Response(status, json={"error": {"message": msg, "type": "OAuthException", "code": code, "error_subcode": sub}}, headers=usage)
        if self.mode == "rate_limited":
            return err(4, "Application request limit reached", 400)
        if self.mode == "bad_token":
            return err(190, "Error validating access token: Session has expired")
        if path == "me":
            return httpx.Response(200, json={"id": "777", "name": "Authorized Person", "link": "https://www.facebook.com/app_scoped_user_id/777/", "picture": {"data": {"url": "https://scontent.xx.fbcdn.net/me.jpg", "is_silhouette": False}}}, headers=usage)
        if path in ("me/posts",):
            if self.mode == "no_user_posts":
                return err(10, "Requires user_posts permission")
            return httpx.Response(200, json={"data": POSTS[:1]})
        if path == "me/photos":
            return httpx.Response(200, json={"data": []})
        if path in ("qusoorfacades", "104958162837"):
            fields = request.url.params.get("fields", "")
            if "verification_status" in fields:
                return err(100, "(#100) Tried accessing nonexisting field (verification_status) on node type (Page)")
            return httpx.Response(200, json=PAGE, headers=usage)
        if path.endswith("/posts"):
            if self.mode == "posts_forbidden":
                return err(10, "(#10) This endpoint requires the 'pages_read_engagement' permission or the 'Page Public Content Access' feature")
            after = request.url.params.get("after")
            if after == "c2":
                return httpx.Response(200, json={"data": POSTS[2:]})
            return httpx.Response(200, json={"data": POSTS[:2], "paging": {"next": "https://graph.facebook.com/v23.0/104958162837/posts?after=c2&limit=2"}})
        if path.endswith("/photos"):
            return httpx.Response(200, json={"data": [{"id": "p1", "name": "Facade", "created_time": "2026-03-01T10:00:00+0000", "images": [{"source": "https://scontent.xx.fbcdn.net/p1.jpg", "width": 200}]}]})
        if path.endswith("/comments"):
            return httpx.Response(200, json={"data": [{"id": "c1", "message": "Great work", "created_time": "2026-03-02T10:00:00+0000"}]})
        # personal profile / unknown object
        return err(100, "(#100) Unsupported get request. Object with ID 'john.doe.123' does not exist, cannot be loaded due to missing permissions, or does not support this operation", sub=33)


class FakeWeb:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.img_a = make_image(1)
        self.img_b = make_image(2)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if path == "/robots.txt":
            if host == "blocked.example.com":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            return httpx.Response(404)
        if host.endswith("fbcdn.net"):
            # profile pic and p1 are the same image -> duplicate group
            return httpx.Response(200, content=self.img_a if path in ("/pic.jpg", "/p1.jpg", "/me.jpg") else self.img_b, headers={"content-type": "image/png"})
        if host == "qusoor.example.sa":
            if path == "/logo.png":
                return httpx.Response(200, content=self.img_a, headers={"content-type": "image/png"})
            if path == "/old":
                return httpx.Response(301, headers={"location": "https://qusoor.example.sa/"})
            return httpx.Response(200, text=SITE_HTML, headers={"content-type": "text/html; charset=utf-8"})
        if host == "directory.example.org":
            return httpx.Response(200, text=DIRECTORY_HTML, headers={"content-type": "text/html"})
        if host == "redirect-internal.example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        if host == "huge.example.com":
            return httpx.Response(200, content=b"x" * 3_000_000, headers={"content-type": "text/html"})
        return httpx.Response(404, text="not found")


def public_resolver(host: str) -> list[str]:
    if host in ("localhost",):
        return ["127.0.0.1"]
    if host == "intranet.example.com":
        return ["10.0.0.5"]
    return ["93.184.216.34"]
