"""Verify initial HTML from an isolated Planora web container."""
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import urlopen


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.robots = []
        self.canonical = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots.append(attrs.get("content"))
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical.append(attrs.get("href"))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


base = sys.argv[1].rstrip("/")
cases = [
    ("/", "Planora | Academic Timetabling and Scheduling", "index,follow", "/"),
    ("/faq", "Planora FAQ | Academic Timetabling", "index,follow", "/faq"),
    ("/privacy", "Privacy | Planora Academic Scheduling", "index,follow", "/privacy"),
    ("/login", "Planora | Sign in and workspace", "noindex,follow", None),
    ("/workspace", "Planora | Sign in and workspace", "noindex,follow", None),
]
for path, title, robots, canonical in cases:
    with urlopen(base + path, timeout=10) as response:
        head = Head()
        head.feed(response.read().decode("utf-8"))
        expected = ["https://planora.elfeel.me" + canonical] if canonical else []
        assert (response.status, head.title, head.robots, head.canonical) == (200, title, [robots], expected), path
        assert response.headers.get("Content-Security-Policy"), path

for path, status in [("/__seo", 404), ("/__seo/faq.html", 404), ("/api/health", 502)]:
    try:
        response = urlopen(base + path, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        assert response.status == status, (path, response.status)
print("Planora initial metadata and isolated API routing verified")
