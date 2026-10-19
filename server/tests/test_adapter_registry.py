import pytest

from app.adapters import GreenhouseAdapter, HTTPClient, build_adapter, register, registered_providers
from app.adapters.base import JobSourceAdapter
from app.adapters.registry import AdapterNotRegisteredError


def test_greenhouse_registered_by_default() -> None:
    assert "greenhouse" in registered_providers()


async def test_build_adapter_returns_correct_class() -> None:
    http = HTTPClient(base_url="https://mock")
    try:
        adapter = build_adapter(
            provider="greenhouse",
            http=http,
            config={"board_token": "stripe"},
            company_slug="stripe",
        )
        assert isinstance(adapter, GreenhouseAdapter)
        assert adapter.company_slug == "stripe"
        assert adapter.config == {"board_token": "stripe"}
    finally:
        await http.close()


def test_build_adapter_unknown_provider_raises() -> None:
    with pytest.raises(AdapterNotRegisteredError):
        build_adapter(
            provider="does-not-exist",
            http=None,  # type: ignore[arg-type]
            config={},
            company_slug="stripe",
        )


def test_register_rejects_class_without_provider() -> None:
    class Bad(JobSourceAdapter):  # no provider attribute
        async def discover(self):
            return []

        async def get_job(self, source_job_id):
            raise NotImplementedError

        def normalize(self, raw):
            raise NotImplementedError

    with pytest.raises(TypeError):
        register(Bad)
