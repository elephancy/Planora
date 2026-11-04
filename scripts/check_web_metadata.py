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


port = int(sys.argv[1])


def fetch(path):
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
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
for path, title, robots, canonical in cases:
    status, body, headers = fetch(path)
    head = Head()
    head.feed(body.decode("utf-8"))
    expected = ["https://planora.elfeel.me" + canonical] if canonical else []
    assert (status, head.title, head.robots, head.canonical) == (200, title, [robots], expected), path
    assert headers.get("Content-Security-Policy"), path

for path, status in [("/__seo", 404), ("/__seo/faq.html", 404), ("/api/health", 502)]:
    actual_status, _, _ = fetch(path)
    assert actual_status == status, (path, actual_status)
print("Planora initial metadata and isolated API routing verified")
