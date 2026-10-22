from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request
from zipfile import ZipFile

import pytest

from utils import xml_security as XML
from utils.http_security import _CheckedRedirect, _checked_url, read_http


@pytest.mark.parametrize("text", [
    b'<!DOCTYPE root><root/>',
    b'<!DOCTYPE root [<!ENTITY item "expanded">]><root>&item;</root>',
    b'<!DOCTYPE root [<!ENTITY item SYSTEM "file:///not-a-real-file">]><root>&item;</root>',
    b'<!DOCTYPE root SYSTEM "http://127.0.0.1:9/no-fetch"><root/>',
    '<!DOCTYPE root [<!ENTITY item "expanded">]><root>&item;</root>'.encode('utf-16'),
])
@pytest.mark.parametrize("operation", ["parse", "fromstring", "iterparse"])
def test_input_parsers_reject_dtd_and_entities(text, operation):
    with pytest.raises(XML.ParseError):
        if operation == 'parse':
            XML.parse(BytesIO(text))
        elif operation == 'fromstring':
            XML.fromstring(text)
        else:
            list(XML.iterparse(BytesIO(text), events=('end',)))


def test_safe_xml_preserves_construction_and_serialization_golden():
    root = XML.Element('solution')
    XML.SubElement(root, 'class', {'id': '17', 'room': '4'})
    tree = XML.ElementTree(root)
    XML.indent(tree, space='  ')
    output = BytesIO()
    tree.write(output, encoding='utf-8', xml_declaration=True)
    assert output.getvalue() == b'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<solution>\n  <class id="17" room="4" />\n</solution>'
    assert XML.parse(BytesIO(output.getvalue())).getroot()[0].attrib == {'id': '17', 'room': '4'}


def test_active_xml_entry_points_reject_external_entities(tmp_path, monkeypatch):
    from benchmarks.itc2019 import parse_itc2019_xml
    from benchmarks.itc2019_competitor_build_closure import _xml_root, BuildClosureError
    from services.teaching_load_import_service import _parse_xml_root
    from scripts import extract_pdf_schedule
    from benchmarks.itc2019_corpus import _nonpositive_time_anomalies

    attack = b'<!DOCTYPE root [<!ENTITY item SYSTEM "file:///not-a-real-file">]><root>&item;</root>'
    path = tmp_path / 'input.xml'
    path.write_bytes(attack)
    with pytest.raises(XML.ParseError):
        parse_itc2019_xml(path)
    with pytest.raises(XML.ParseError):
        _nonpositive_time_anomalies(path)
    with pytest.raises(BuildClosureError):
        _xml_root(attack, 'fixture')
    archive_path = tmp_path / 'fixture.zip'
    with ZipFile(archive_path, 'w') as archive:
        archive.writestr('data.xml', attack)
    with ZipFile(archive_path) as archive, pytest.raises(ValueError):
        _parse_xml_root(archive, archive.getinfo('data.xml'))
    monkeypatch.setattr(extract_pdf_schedule, '_run_pdftotext', lambda _pdf, output: output.write_bytes(attack))
    with pytest.raises(XML.ParseError):
        extract_pdf_schedule.extract(tmp_path / 'fixture.pdf')


def test_generated_pdf_xhtml_fixed_prologue_is_not_resolved(tmp_path, monkeypatch):
    from scripts import extract_pdf_schedule
    prologue = (b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
                b'"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">')
    document = prologue + b'<html xmlns="http://www.w3.org/1999/xhtml"><doc><page height="600"/></doc></html>'
    monkeypatch.setattr(extract_pdf_schedule, '_run_pdftotext', lambda _pdf, output: output.write_bytes(document))
    cells, summary = extract_pdf_schedule.extract(tmp_path / 'fixture.pdf')
    assert cells == [] and summary['pages'] == 1
    hostile = document.replace(b'xhtml1-transitional.dtd', b'evil.dtd')
    monkeypatch.setattr(extract_pdf_schedule, '_run_pdftotext', lambda _pdf, output: output.write_bytes(hostile))
    with pytest.raises(XML.ParseError):
        extract_pdf_schedule.extract(tmp_path / 'fixture.pdf')


@contextmanager
def server(routes):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            seen.append((self.path, self.headers.get('Authorization')))
            status, headers, body = routes[self.path]
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{instance.server_port}', seen
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join()


def test_real_http_allows_local_and_same_origin_redirect():
    routes = {'/ok': (200, {}, b'{"ok": true}'), '/redirect': (302, {'Location': '/ok'}, b'')}
    with server(routes) as (url, seen):
        payload = read_http(Request(url + '/redirect', headers={'Authorization': 'Bearer fixture'}), timeout=2, maximum=64)
    assert json.loads(payload) == {'ok': True}
    assert seen == [('/redirect', 'Bearer fixture'), ('/ok', 'Bearer fixture')]


def test_backend_and_benchmark_clients_preserve_loopback_http():
    from ui.backend_client import HttpBackendClient
    from scripts.benchmark_end_to_end_performance import _http_json
    routes = {'/capabilities': (200, {}, b'{"ok": true}')}
    with server(routes) as (url, seen):
        assert HttpBackendClient(url, bearer_token='fixture').capabilities() == {'ok': True}
        result, byte_count = _http_json('GET', url + '/capabilities', timeout=2)
        assert result == {'ok': True} and byte_count == len(b'{"ok": true}')
    assert seen[0] == ('/capabilities', 'Bearer fixture')


@pytest.mark.parametrize('module', ['benchmarks.cbctt_corpus', 'benchmarks.itc2019_corpus'])
@pytest.mark.parametrize('url', ['file:///not-a-real-file', 'http://api.github.com/file',
                                'https://not-an-approved-corpus.example/file'])
def test_actual_corpus_fetchers_reject_unapproved_network_sources(module, url):
    import importlib
    with pytest.raises(ValueError):
        importlib.import_module(module)._default_fetch_bytes(url, 1)


def test_real_http_blocks_cross_origin_before_credentials_forwarded():
    with server({'/target': (200, {}, b'not reached')}) as (other, other_seen):
        with server({'/redirect': (302, {'Location': other + '/target'}, b'')}) as (url, _seen):
            with pytest.raises(ValueError, match='Cross-origin'):
                read_http(Request(url + '/redirect', headers={'Authorization': 'Bearer fixture'}), timeout=2, maximum=64)
    assert other_seen == []


@pytest.mark.parametrize('target', ['file:///not-a-real-file', 'ftp://127.0.0.1/payload',
                                   'http://user:password@127.0.0.1/payload'])
def test_real_redirect_rejects_non_http_and_embedded_credentials(target):
    with server({'/redirect': (302, {'Location': target}, b'')}) as (url, _seen):
        with pytest.raises((ValueError, HTTPError)):
            read_http(url + '/redirect', timeout=2, maximum=64)


@pytest.mark.parametrize('url', ['file:///not-a-real-file', 'ftp://example.com/file',
    'http://user:password@example.com/', 'https://example.com/#fragment',
    'http://example.com:99999/', 'http://example.com/\r\nheader', 'http://example.com\\evil'])
def test_non_http_or_ambiguous_initial_authority_rejected(url):
    with pytest.raises(ValueError):
        read_http(url, timeout=1, maximum=64)


def test_real_http_response_bound():
    with server({'/large': (200, {}, b'x' * 65)}) as (url, _seen):
        with pytest.raises(ValueError, match='byte limit'):
            read_http(url + '/large', timeout=2, maximum=64)


def test_corpus_exact_https_authority_and_controlled_redirect():
    policy = dict(https_only=True, allowed_hosts=frozenset({'api.github.com', 'raw.githubusercontent.com'}))
    initial = _checked_url('https://api.github.com/repos/example/corpus', **policy)
    handler = _CheckedRedirect(initial, same_origin=False, **policy)
    redirected = handler.redirect_request(Request(initial.geturl()), None, 302, '', {}, 'https://raw.githubusercontent.com/example/data')
    assert redirected.full_url == 'https://raw.githubusercontent.com/example/data'
    for target in ('http://api.github.com/file', 'https://evil.example/file', 'https://api.github.com:444/file',
                   'https://api.github.com@evil.example/file'):
        with pytest.raises(ValueError):
            handler.redirect_request(Request(initial.geturl()), None, 302, '', {}, target)
    with pytest.raises(ValueError, match='Authenticated'):
        read_http(Request(initial.geturl(), headers={'Authorization': 'Bearer fixture'}), timeout=1, maximum=64,
                  same_origin_redirects=False, **policy)


def test_update_manifest_local_file_and_remote_scheme_validation(tmp_path):
    from services.runtime_ops_service import load_update_manifest
    path = tmp_path / 'manifest.json'
    path.write_text('{"version":"fixture"}')
    assert load_update_manifest(path) == {'version': 'fixture'}
    with server({'/manifest': (200, {}, b'{"version":"local-http"}')}) as (url, _seen):
        assert load_update_manifest(url + '/manifest') == {'version': 'local-http'}
    for scheme in ('file', 'ftp', 'data'):
        with pytest.raises(ValueError):
            load_update_manifest(scheme + ':///not-a-real-file')
