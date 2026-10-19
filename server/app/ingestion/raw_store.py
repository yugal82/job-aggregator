import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_source_document import RawSourceDocument


def compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def save_raw_document(
    session: AsyncSession,
    *,
    source_id: int,
    company_id: int | None,
    content: str,
    content_type: str | None = None,
    http_status: int | None = None,
    response_headers: dict[str, Any] | None = None,
) -> RawSourceDocument:
    doc = RawSourceDocument(
        source_id=source_id,
        company_id=company_id,
        content=content,
        content_type=content_type,
        http_status=http_status,
        response_headers=response_headers,
        content_hash=compute_content_hash(content),
    )
    session.add(doc)
    await session.flush()
    return doc
