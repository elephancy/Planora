"""Verify initial HTML from an isolated Planora web container."""
import sys
from http.client import HTTPConnection
from html.parser import HTMLParser


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.robots = []
        self.canonical = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots.append(attrs.get("content"))
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical.append(attrs.get("href"))
        if tag == "script" and attrs.get("src"):
            self.assets.append((attrs["src"], ("text/javascript", "application/javascript")))
        if tag == "link" and attrs.get("rel") == "stylesheet" and attrs.get("href"):
            self.assets.append((attrs["href"], ("text/css",)))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


port = int(sys.argv[1])


def fetch(path, method="GET"):
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read(), response.headers
    finally:
        connection.close()


cases = [
    ("/", "Planora | Academic Timetabling and Scheduling", "index,follow", "/"),
    ("/faq", "Planora FAQ | Academic Timetabling", "index,follow", "/faq"),
    ("/privacy", "Privacy | Planora Academic Scheduling", "index,follow", "/privacy"),
    ("/login", "Planora | Sign in and workspace", "noindex,follow", None),
    ("/workspace", "Planora | Sign in and workspace", "noindex,follow", None),
]
assets = set()
for path, title, robots, canonical in cases:
    status, body, headers = fetch(path)
    head = Head()
    head.feed(body.decode("utf-8"))
    expected = ["https://planora.elfeel.me" + canonical] if canonical else []
    assert (status, head.title, head.robots, head.canonical) == (200, title, [robots], expected), path
    assert headers.get("Content-Security-Policy"), path
    assets.update(head.assets)

assert assets, "Built HTML contains no bundled assets"
for path, content_types in assets:
    assert path.startswith("/assets/"), path
    for method in ("GET", "HEAD"):
        status, _, headers = fetch(path, method)
        assert status == 200, (path, method, status)
        assert headers.get("Content-Type", "").split(";", 1)[0] in content_types, (path, method, headers)

for path, status in [("/__seo", 404), ("/__seo/faq.html", 404), ("/api/health", 502)]:
    actual_status, _, _ = fetch(path)
    assert actual_status == status, (path, actual_status)

for path in ("/assets/seo-missing.js", "/assets/seo-missing.css", "/assets/seo-missing.png"):
    for method in ("GET", "HEAD"):
        status, body, headers = fetch(path, method)
        assert status == 404, (path, method, status)
        assert headers.get("Cache-Control") == "no-store", (path, method, headers)
        assert headers.get("Content-Security-Policy"), (path, method)
        assert b"<html" not in body.lower(), (path, method)

for path, content_type in (("/app-icon.png", "image/png"), ("/robots.txt", "text/plain"), ("/sitemap.xml", "text/xml")):
    for method in ("GET", "HEAD"):
        status, _, headers = fetch(path, method)
        assert status == 200, (path, method, status)
        assert headers.get("Content-Type", "").startswith(content_type), (path, method, headers)

status, body, _ = fetch("/projects/release.v1")
assert status == 200, status
fallback = Head()
fallback.feed(body.decode("utf-8"))
assert fallback.robots == ["noindex,follow"], fallback.robots
print("Planora initial metadata, static resources and isolated API routing verified")
