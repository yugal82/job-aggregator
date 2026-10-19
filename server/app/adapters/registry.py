from typing import Any, TypeVar

from app.adapters.base import JobSourceAdapter
from app.adapters.http import HTTPClient

_REGISTRY: dict[str, type[JobSourceAdapter]] = {}

T = TypeVar("T", bound=type[JobSourceAdapter])


class AdapterNotRegisteredError(LookupError):
    pass


def register(cls: T) -> T:
    """Class decorator: `@register` on every JobSourceAdapter subclass."""
    provider = getattr(cls, "provider", None)
    if not provider:
        raise TypeError(f"{cls.__name__} must set a non-empty `provider` class attribute")
    _REGISTRY[provider] = cls
    return cls


def get_adapter_class(provider: str) -> type[JobSourceAdapter]:
    try:
        return _REGISTRY[provider]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise AdapterNotRegisteredError(
            f"no adapter registered for provider '{provider}' (known: {known})"
        ) from exc


def build_adapter(
    *,
    provider: str,
    http: HTTPClient,
    config: dict[str, Any],
    company_slug: str,
) -> JobSourceAdapter:
    cls = get_adapter_class(provider)
    return cls(http=http, config=config, company_slug=company_slug)


def registered_providers() -> list[str]:
    return sorted(_REGISTRY)
