from html.parser import HTMLParser

import pytest

from services.password_auth_service import build_password_reset_email, build_verification_email


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


@pytest.mark.parametrize("builder,path,subject", [
    (build_verification_email, "/auth/verify?token=", "Confirm your Planora account"),
    (build_password_reset_email, "/login?reset_token=", "Reset your Planora password"),
])
def test_readable_email_preserves_identity_exact_auth_links_and_alternative(builder, path, subject):
    message = builder("https://planora.example.invalid", "recipient@example.invalid", "sample-token", "123456")
    url = f"https://planora.example.invalid{path}sample-token"
    links = Links()
    links.feed(message.html_body)
    assert links.hrefs == [url, url]
    assert message.to_email == "recipient@example.invalid"
    assert message.subject == subject
    for value in (url, "123456", "Next step", "only be used once", "Do not share"):
        assert value in message.body
    for value in ('lang="en"', 'name="viewport"', "Next step", "123456", "If the button does not work"):
        assert value in message.html_body
    assert len(message.inline_images) == 1
    assert message.inline_images[0].content_id == "planora-elephant"


def test_code_and_auth_link_cannot_inject_html():
    message = build_verification_email("https://planora.example.invalid", "recipient@example.invalid",
                                       'sample&key="<script>', '<script>alert(1)</script>')
    assert "<script>" not in message.html_body
    assert "&lt;script&gt;" in message.html_body
    links = Links()
    links.feed(message.html_body)
    assert links.hrefs == ['https://planora.example.invalid/auth/verify?token=sample&key="<script>'] * 2
