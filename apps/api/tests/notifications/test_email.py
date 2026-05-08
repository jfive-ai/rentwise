"""Email notifier + body composition tests (Phase 5 PR-B)."""

from __future__ import annotations

import smtplib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from rentwise.models import NormalizedListing, SchoolCatchments
from rentwise.notifications.email import (
    NotifierError,
    SmtpConfig,
    SmtpEmailNotifier,
    compose_alert,
)


def _listing(idx: int, price: int = 2800) -> NormalizedListing:
    nid = uuid4()
    now = datetime.now(UTC)
    return NormalizedListing(
        id=nid,
        canonical_id=nid,
        source="craigslist",
        source_url=HttpUrl(f"https://example.com/listing/{idx}"),
        source_listing_id=str(idx),
        title=f"Listing {idx}",
        address="1234 W 4th Ave",
        address_normalized=None,
        lat=None,
        lon=None,
        bedrooms=2.0,
        bathrooms=None,
        price_cad=price,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet=None,
        school_catchments=SchoolCatchments(),
        raw_metadata={},
    )


# ---------------------------------------------------------------------------
# compose_alert (pure)
# ---------------------------------------------------------------------------


class TestComposeAlert:
    def test_subject_singularizes_for_one_listing(self) -> None:
        out = compose_alert(
            label="Kits 2br",
            listings=[_listing(1)],
            app_base_url="https://app.example",
            cache_key="k1",
            to="me@example.com",
        )
        assert "1 new listing for Kits 2br" in out.subject

    def test_subject_pluralizes_for_many(self) -> None:
        out = compose_alert(
            label=None,
            listings=[_listing(1), _listing(2)],
            app_base_url="https://app.example",
            cache_key="k1",
            to="me@example.com",
        )
        assert "2 new listings" in out.subject
        assert "your saved search" in out.subject  # label fallback

    def test_text_body_includes_each_listing_url(self) -> None:
        listings = [_listing(1), _listing(2)]
        out = compose_alert(
            label="x",
            listings=listings,
            app_base_url="https://app.example",
            cache_key="k1",
            to="me@example.com",
        )
        for li in listings:
            assert str(li.source_url) in out.text_body

    def test_html_body_links_to_saved_search(self) -> None:
        out = compose_alert(
            label="x",
            listings=[_listing(1)],
            app_base_url="https://app.example/",
            cache_key="k1",
            to="me@example.com",
        )
        assert 'href="https://app.example/?saved=k1"' in out.html_body
        assert "View on RentWise" in out.text_body

    def test_html_escapes_dangerous_titles(self) -> None:
        evil = _listing(1)
        evil = evil.model_copy(update={"title": '<script>alert("x")</script>'})
        out = compose_alert(
            label="x",
            listings=[evil],
            app_base_url="https://app.example",
            cache_key="k1",
            to="me@example.com",
        )
        assert "<script>" not in out.html_body
        assert "&lt;script&gt;" in out.html_body


# ---------------------------------------------------------------------------
# SmtpEmailNotifier — patched smtplib
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_alert_uses_starttls_and_login() -> None:
    cfg = SmtpConfig(
        host="smtp.example",
        port=587,
        starttls=True,
        username="me",
        password="hunter2",
        from_addr="RentWise <noreply@x>",
    )
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = None
    with patch("rentwise.notifications.email.smtplib.SMTP", return_value=fake_smtp) as ctor:
        notifier = SmtpEmailNotifier(cfg)
        await notifier.send_alert(
            compose_alert(
                label="x",
                listings=[_listing(1)],
                app_base_url="https://app.example",
                cache_key="k1",
                to="user@example.com",
            )
        )

    ctor.assert_called_once_with("smtp.example", 587, timeout=10)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("me", "hunter2")
    fake_smtp.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_alert_skips_starttls_and_login_when_unconfigured() -> None:
    cfg = SmtpConfig(host="smtp.example", port=25, starttls=False, username=None, password=None)
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = None
    with patch("rentwise.notifications.email.smtplib.SMTP", return_value=fake_smtp):
        notifier = SmtpEmailNotifier(cfg)
        await notifier.send_alert(
            compose_alert(
                label="x",
                listings=[_listing(1)],
                app_base_url="https://app.example",
                cache_key="k1",
                to="user@example.com",
            )
        )
    fake_smtp.starttls.assert_not_called()
    fake_smtp.login.assert_not_called()
    fake_smtp.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_alert_wraps_smtp_errors_as_notifier_error() -> None:
    cfg = SmtpConfig(host="smtp.example")
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = None
    fake_smtp.send_message.side_effect = smtplib.SMTPAuthenticationError(535, b"nope")
    with patch("rentwise.notifications.email.smtplib.SMTP", return_value=fake_smtp):
        notifier = SmtpEmailNotifier(cfg)
        with pytest.raises(NotifierError):
            await notifier.send_alert(
                compose_alert(
                    label="x",
                    listings=[_listing(1)],
                    app_base_url="https://app.example",
                    cache_key="k1",
                    to="user@example.com",
                )
            )


@pytest.mark.asyncio
async def test_send_alert_wraps_oserror_as_notifier_error() -> None:
    cfg = SmtpConfig(host="smtp.example")
    with patch(
        "rentwise.notifications.email.smtplib.SMTP",
        side_effect=OSError("connection refused"),
    ):
        notifier = SmtpEmailNotifier(cfg)
        with pytest.raises(NotifierError):
            await notifier.send_alert(
                compose_alert(
                    label="x",
                    listings=[_listing(1)],
                    app_base_url="https://app.example",
                    cache_key="k1",
                    to="user@example.com",
                )
            )
