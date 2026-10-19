"""Application semantics and the real mounted Ops contract, without sending mail."""
import importlib.util
import json
import os
from html.parser import HTMLParser
from pathlib import Path

import pytest

from services import password_auth_service as auth


@pytest.mark.parametrize("builder,kind,path", [
    (auth.build_verification_email, "verify-email", "/auth/verify?token=sample-token"),
    (auth.build_password_reset_email, "reset-password", "/login?reset_token=sample-token"),
])
def test_auth_events_keep_recipient_token_code_and_do_not_invent_expiry(monkeypatch, builder, kind, path):
    calls = []

    class Notifier:
        def action_url(self, action_path):
            calls.append(action_path)
            return "https://central.example.invalid" + action_path

        def send_account(self, event):
            calls.append(event)

    monkeypatch.setattr(auth, "_notifier", lambda: Notifier())
    message = builder("https://request-host.example.invalid", "user@example.invalid", "sample-token", "123456")
    assert calls == []  # Construction does not require runtime mounts, including dev auth.
    auth.send_email(message)
    assert calls == [path, {"kind": kind, "to": "user@example.invalid",
                           "actionUrl": "https://central.example.invalid" + path, "code": "123456"}]


def test_missing_bundle_never_uses_old_smtp_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANORA_SMTP_HOST", "must-not-be-used.invalid")
    monkeypatch.setattr(auth, "_NOTIFICATIONS_MODULE", tmp_path / "absent.py")
    auth._notifier.cache_clear()
    try:
        assert auth.smtp_configured() is False
        message = auth.build_verification_email("", "user@example.invalid", "token", "123456")
        with pytest.raises(RuntimeError, match="Ops notifications are unavailable"):
            auth.send_email(message)
    finally:
        auth._notifier.cache_clear()


def test_delivery_errors_propagate_without_local_fallback(monkeypatch):
    class Notifier:
        def action_url(self, path):
            return "https://planora.example.invalid" + path

        def send_account(self, event):
            raise RuntimeError("central delivery failed")

    monkeypatch.setattr(auth, "_notifier", lambda: Notifier())
    with pytest.raises(RuntimeError, match="central delivery failed"):
        auth.send_email(auth.build_password_reset_email("", "user@example.invalid", "token", "123456"))


@pytest.mark.parametrize("status,expected", [
    ({"configured": False, "mode": None}, False),
    ({"configured": True, "mode": "outbox"}, False),
    ({"configured": True, "mode": "smtp"}, True),
])
def test_production_delivery_availability_comes_from_ops(monkeypatch, status, expected):
    monkeypatch.setattr(auth, "_notifier", lambda: type("Notifier", (), {"status": lambda self: status})())
    assert auth.smtp_configured() is expected


@pytest.fixture
def ops_bundle(tmp_path, monkeypatch):
    configured = os.environ.get("OPS_NOTIFICATION_TEST_BUNDLE")
    if not configured:
        pytest.skip("Real Ops bundle contract requires explicit OPS_NOTIFICATION_TEST_BUNDLE fixture")
    root = Path(configured)
    spec = importlib.util.spec_from_file_location("fixture_ops_notifications", root / "python" / "ops_notifications.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile_path = tmp_path / "profile.json"
    profile = {"schemaVersion": 1, "project": "planora", "mode": "smtp",
               "publicBaseUrl": "https://planora.example.invalid",
               "smtp": {"host": "smtp.example.invalid", "port": 2525,
                        "username": "fixture-user", "password": "fixture-only",
                        "from": "fixture@example.invalid", "tlsMode": "starttls"}}
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    profile_path.chmod(0o600)
    notifier = module.Notifier(profile_path=profile_path)
    monkeypatch.setattr(auth, "_notifier", lambda: notifier)
    return notifier, module, profile, profile_path


@pytest.mark.parametrize("builder,path", [
    (auth.build_verification_email, "/auth/verify?token="),
    (auth.build_password_reset_email, "/login?reset_token="),
])
def test_real_ops_bundle_preserves_exact_auth_links_code_and_alternatives(ops_bundle, builder, path):
    notifier, _, _, _ = ops_bundle
    message = builder("https://ignored.example.invalid", "user@example.invalid", "token-123", "123456")
    rendered = notifier.render_account(message.event())
    url = "https://planora.example.invalid" + path + "token-123"

    class Links(HTMLParser):
        hrefs = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.hrefs.extend(value for key, value in attrs if key == "href")

    parser = Links()
    parser.hrefs = []
    parser.feed(rendered["html"])
    assert parser.hrefs == [url, url]
    assert rendered["to"] == "user@example.invalid"
    assert url in rendered["text"]
    assert "123456" in rendered["text"] and "123456" in rendered["html"]
    assert "Do not share" in rendered["text"]
    assert "minutes" not in rendered["text"]  # Actual expiry is not supplied by this flow.
    assert rendered["attachments"][0]["content"].startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("tls_mode,expected_tls", [("starttls", True), ("plain", False)])
def test_real_ops_delivery_preserves_tls_and_multipart_without_network(ops_bundle, monkeypatch, tls_mode, expected_tls):
    _, module, profile, profile_path = ops_bundle
    profile["smtp"]["tlsMode"] = tls_mode
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    sent, operations = [], []

    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("smtp.example.invalid", 2525)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def ehlo(self):
            operations.append("ehlo")
        def starttls(self, context):
            assert context.check_hostname
            operations.append("tls")
        def login(self, user, password):
            assert (user, password) == ("fixture-user", "fixture-only")
            operations.append("login")
        def send_message(self, mail):
            sent.append(mail)

    monkeypatch.setattr(module.smtplib, "SMTP", SMTP)
    auth.send_email(auth.build_verification_email("", "user@example.invalid", "token", "123456"))
    assert ("tls" in operations) is expected_tls
    if expected_tls:
        assert operations.index("tls") < operations.index("login")
    assert len(sent) == 1
    assert sent[0]["To"] == "user@example.invalid"
    assert sent[0]["From"] == profile["smtp"]["from"]
    content_types = [part.get_content_type() for part in sent[0].walk()]
    assert {"text/plain", "text/html", "image/png"} <= set(content_types)


def test_real_ops_bundle_refuses_cross_origin_actions_and_hides_transport_errors(ops_bundle, monkeypatch):
    notifier, module, _, _ = ops_bundle
    with pytest.raises(module.NotificationError):
        notifier.action_url("//attacker.example.invalid/auth/verify?token=secret")
    def fail(*args, **kwargs):
        raise OSError("smtp-password and recipient must not escape")
    monkeypatch.setattr(module.smtplib, "SMTP", fail)
    with pytest.raises(module.NotificationError) as error:
        auth.send_email(auth.build_password_reset_email("", "user@example.invalid", "secret", "123456"))
    assert "smtp-password" not in str(error.value)
    assert "recipient" not in str(error.value)
