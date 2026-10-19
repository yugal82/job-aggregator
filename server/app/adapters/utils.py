"""Small helpers shared by every adapter's normalize() implementation."""
import hashlib
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from io import StringIO


def content_hash(*parts: str | None) -> str:
    """Stable SHA-256 over a tuple of string parts.

    A U+241F unit-separator delimiter guards against `title="A|B"` colliding
    with `title="A", location="B"` style collisions.
    """
    joined = "␟".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def sanitize_requisition_id(value: str | None) -> str | None:
    """Reject placeholder text (whitespace-containing / suspiciously long).

    Real requisition IDs are short opaque tokens ("REQ-1234"). Fields like
    "See Opening ID" or "N/A - contact HR" are ATS placeholders and would
    collapse unrelated jobs under dedup Level 2 if allowed through.
    """
    if not value:
        return None
    text = str(value).strip()
    if not text or " " in text or len(text) > 64:
        return None
    return text


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def parse_epoch_millis(value: int | float | None) -> datetime | None:
    """Convert JS-style milliseconds-since-epoch into an aware datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_epoch_seconds(value: int | float | None) -> datetime | None:
    """Convert Unix-style seconds-since-epoch into an aware datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf = StringIO()

    def handle_data(self, data: str) -> None:
        self._buf.write(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "li", "div", "tr"}:
            self._buf.write("\n")

    def text(self) -> str:
        return self._buf.getvalue()


def strip_html(text: str | None) -> str | None:
    """Extract readable text from HTML. Collapses blank lines."""
    if not text:
        return None
    extractor = _HTMLTextExtractor()
    extractor.feed(unescape(text))
    lines = [line.strip() for line in extractor.text().splitlines()]
    return "\n".join(line for line in lines if line) or None
