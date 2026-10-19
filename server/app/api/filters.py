"""GET /api/filters/tiers — exposes the configured company tiers so the client
can render tier menus without hardcoding labels.
"""
from fastapi import APIRouter

from app.filters import get_filter_config

router = APIRouter(prefix="/api/filters", tags=["filters"])


@router.get("/tiers")
async def list_tiers() -> dict:
    cfg = get_filter_config()
    tiers = [
        {
            "key": tier.key,
            "label": tier.label,
            "description": tier.description,
            "company_count": len(tier.companies),
            "companies": list(tier.companies),
        }
        for tier in cfg.company_tiers.values()
    ]
    return {"tiers": tiers}
