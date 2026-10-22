"""HTTP(S)-only I/O with bounded bodies and explicit redirect authority."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def _checked_url(url: str, *, https_only: bool, allowed_hosts):
    if not isinstance(url, str) or not url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise ValueError("Invalid HTTP URL")
    parsed = urlsplit(url)
    schemes = ("https",) if https_only else ("http", "https")
    if (parsed.scheme not in schemes or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or "\\" in url
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
            or (allowed_hosts is not None and (parsed.hostname not in allowed_hosts
                                               or parsed.port not in (None, 443)))):
        raise ValueError("HTTP URL authority rejected")
    return parsed


def _origin(parsed):
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


class _CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, initial, *, https_only, allowed_hosts, same_origin):
        self.initial = initial
        self.https_only = https_only
        self.allowed_hosts = allowed_hosts
        self.same_origin = same_origin

    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = _checked_url(newurl, https_only=self.https_only, allowed_hosts=self.allowed_hosts)
        if self.same_origin and _origin(target) != _origin(self.initial):
            raise ValueError("Cross-origin HTTP redirect rejected")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def read_http(request: Request | str, *, timeout: float, maximum: int,
              https_only: bool = False, allowed_hosts=None,
              same_origin_redirects: bool = True) -> bytes:
    """Read HTTP(S), preserving local endpoints; credentials never cross origins.

    Corpus callers may allow redirects between a finite set of public HTTPS
    hosts. Such requests must not contain authentication headers.
    """
    url = request.full_url if isinstance(request, Request) else request
    hosts = frozenset(allowed_hosts) if allowed_hosts is not None else None
    initial = _checked_url(url, https_only=https_only, allowed_hosts=hosts)
    if type(maximum) is not int or maximum < 1:
        raise ValueError("HTTP response limit rejected")
    if not same_origin_redirects:
        if not https_only or not hosts:
            raise ValueError("Public redirect policy must pin HTTPS hosts")
        if isinstance(request, Request) and any(
                name.lower() in ("authorization", "cookie", "proxy-authorization")
                for name, _value in request.header_items()):
            raise ValueError("Authenticated requests require same-origin redirects")
    opener = build_opener(_CheckedRedirect(initial, https_only=https_only,
                                          allowed_hosts=hosts, same_origin=same_origin_redirects))
    with opener.open(request, timeout=timeout) as response:
        body = response.read(maximum + 1)
    if len(body) > maximum:
        raise ValueError("HTTP response exceeds byte limit")
    return body
