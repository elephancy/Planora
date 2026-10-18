from __future__ import annotations

import json

import pytest

from api import server


def _handler(path="/ready", method="GET", request_id="request_12345678"):
    handler = server.PlanoraApiHandler.__new__(server.PlanoraApiHandler)
    handler.path = path
    handler.command = method
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler._request_id = request_id
    handler.client_address = ("192.0.2.4", 4567)
    return handler


@pytest.mark.parametrize(("status", "level"), [(200, "info"), (404, "warn"), (503, "error")])
def test_request_logs_use_application_severity_and_stdout(monkeypatch, capsys, status, level):
    monkeypatch.setattr(server, "production_mode", lambda: True)
    _handler().log_request(status)
    captured = capsys.readouterr()
    assert captured.err == ""
    record = json.loads(captured.out)
    assert record["schema_version"] == "ops.log.v1"
    assert record["event"] == "request.completed"
    assert record["level"] == level
    assert record["project"] == "planora"
    assert record["service"] == "api"
    assert record["http"] == {"method": "GET", "route": "/ready", "status_code": status}


@pytest.mark.parametrize(("path", "route"), [
    ("/auth/verify?token=private-value", "/auth/verify"),
    ("/sessions/private-value/solve?email=test@example.invalid", "/sessions/{session_id}/{action}"),
    ("/unknown/test@example.invalid/private-value", "/unknown"),
])
def test_logs_omit_private_request_data(monkeypatch, capsys, path, route):
    monkeypatch.setattr(server, "production_mode", lambda: True)
    _handler(path, request_id="test@example.invalid").log_request(200)
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["http"]["route"] == route
    assert len(record["event_id"]) == 32
    assert len(record["request_id"]) == 32
    for private in ["test@example.invalid", "private-value", "192.0.2.4", "?token=", "?email="]:
        assert private not in output


def test_unknown_messages_do_not_render_untrusted_format_arguments(monkeypatch, capsys):
    monkeypatch.setattr(server, "production_mode", lambda: True)
    _handler().log_message("request body=%s", "private-value")
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["level"] == "unknown"
    assert record["event"] == "server.message"
    assert "private-value" not in output


def test_logging_failure_does_not_interrupt_requests(monkeypatch):
    monkeypatch.setattr(server, "production_mode", lambda: True)
    monkeypatch.setattr(server, "print", lambda *args, **kwargs: (_ for _ in ()).throw(BrokenPipeError()), raising=False)
    _handler().log_request(200)
