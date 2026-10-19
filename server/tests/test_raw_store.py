from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.raw_store import compute_content_hash, save_raw_document
from app.models.enums import SourceType
from app.models.raw_source_document import RawSourceDocument
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo


async def test_save_raw_document_persists_and_hashes(db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    await db_session.commit()

    content = '{"jobs": []}'
    doc = await save_raw_document(
        db_session,
        source_id=source.id,
        company_id=company.id,
        content=content,
        content_type="application/json",
        http_status=200,
    )
    await db_session.commit()

    fetched = (
        await db_session.execute(select(RawSourceDocument).where(RawSourceDocument.id == doc.id))
    ).scalar_one()
    assert fetched.content == content
    assert fetched.content_hash == compute_content_hash(content)
    assert fetched.content_type == "application/json"
    assert fetched.http_status == 200
