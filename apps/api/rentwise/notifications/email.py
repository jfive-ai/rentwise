"""Email notifier — stdlib smtplib over a configurable SMTP relay.

The :class:`Notifier` Protocol is the only surface :mod:`runner.py`
depends on, so tests can substitute an in-memory recorder. Hosted
relays (Postmark / SES / Mailgun / Resend) all speak SMTP, so adding
a backend later is a settings change, not a code change.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import structlog

from rentwise.models import NormalizedListing

log = structlog.get_logger(__name__)


class NotifierError(Exception):
    """Raised when an outbound dispatch fails. Propagates to the runner so
    it can decide whether to record the dedup row (it must NOT)."""


@dataclass(frozen=True)
class EmailAlert:
    """One alert payload — independent of the underlying transport."""

    to: str
    subject: str
    text_body: str
    html_body: str


class Notifier(Protocol):
    async def send_alert(self, alert: EmailAlert) -> None: ...


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int = 587
    starttls: bool = True
    username: str | None = None
    password: str | None = None
    from_addr: str = "RentWise <noreply@rentwise.local>"


class SmtpEmailNotifier:
    """Production notifier. ``send_alert`` performs the SMTP handshake
    in a worker thread (smtplib is blocking) so the FastAPI loop stays free.
    """

    def __init__(self, config: SmtpConfig) -> None:
        self._cfg = config

    async def send_alert(self, alert: EmailAlert) -> None:
        import asyncio

        try:
            await asyncio.to_thread(self._send_blocking, alert)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("email.smtp_failed", to=alert.to, error=str(exc))
            raise NotifierError(str(exc)) from exc

    def _send_blocking(self, alert: EmailAlert) -> None:
        msg = EmailMessage()
        msg["From"] = self._cfg.from_addr
        msg["To"] = alert.to
        msg["Subject"] = alert.subject
        msg.set_content(alert.text_body)
        msg.add_alternative(alert.html_body, subtype="html")
        with smtplib.SMTP(self._cfg.host, self._cfg.port, timeout=10) as smtp:
            if self._cfg.starttls:
                smtp.starttls()
            if self._cfg.username and self._cfg.password:
                smtp.login(self._cfg.username, self._cfg.password)
            smtp.send_message(msg)


# ---------------------------------------------------------------------------
# Body composition
# ---------------------------------------------------------------------------


def compose_alert(
    *,
    label: str | None,
    listings: list[NormalizedListing],
    app_base_url: str,
    cache_key: str,
    to: str,
) -> EmailAlert:
    """Render an :class:`EmailAlert` for ``listings`` under a saved search.

    Issue #126 — adds a Digest narrative paragraph at the top before the
    bare list. Both text and HTML bodies include it so non-HTML mail
    clients still get the summary.

    Pure / deterministic — tested directly without smtplib.
    """
    # Local import to avoid a cycle at module-load time.
    from rentwise.notifications.digest import build_digest

    n = len(listings)
    title = label or "your saved search"
    subject = f"RentWise: {n} new listing{'s' if n != 1 else ''} for {title}"
    digest = build_digest(listings)

    lines: list[str] = []
    if digest is not None:
        lines.append(digest.narrative)
        lines.append("")
    lines.append(f"{n} new match{'es' if n != 1 else ''} for: {title}")
    lines.append("")
    html_rows: list[str] = []
    for li in listings:
        price = f"${li.price_cad:,}" if li.price_cad is not None else "—"
        beds = f"{li.bedrooms} bd" if li.bedrooms is not None else ""
        addr = li.address or ""
        url = str(li.source_url)
        plain = " · ".join(filter(None, [li.title, beds, price, addr]))
        lines.append(f"- {plain}")
        lines.append(f"  {url}")
        lines.append("")
        html_rows.append(
            "<li>"
            f'<a href="{url}">{_html_escape(li.title)}</a>'
            f" — {beds} · {price} · {_html_escape(addr)}"
            "</li>"
        )

    saved_link = f"{app_base_url.rstrip('/')}/?saved={cache_key}"
    lines.append(f"View on RentWise: {saved_link}")

    digest_html = ""
    if digest is not None:
        digest_html = (
            '<div style="background:#f8fafc;border-left:4px solid #16a34a;'
            'padding:12px 16px;margin-bottom:16px;border-radius:4px;">'
            f"<p style=\"margin:0;font-size:15px;line-height:1.4;\">"
            f"{_html_escape(digest.narrative)}"
            "</p></div>"
        )

    html_body = (
        f"{digest_html}"
        f"<p>{n} new match{'es' if n != 1 else ''} for "
        f"<strong>{_html_escape(title)}</strong>:</p>"
        f"<ul>{''.join(html_rows)}</ul>"
        f'<p><a href="{saved_link}">View on RentWise</a></p>'
    )

    return EmailAlert(
        to=to,
        subject=subject,
        text_body="\n".join(lines),
        html_body=html_body,
    )


def _html_escape(s: str) -> str:
    # Tiny escaper — we don't ship Jinja or anything heavyweight here.
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
