"""Adapter package.

Importing this module registers all built-in adapters with the registry.
"""
from app.adapters.amazon import AmazonAdapter
from app.adapters.apple import AppleAdapter
from app.adapters.ashby import AshbyAdapter
from app.adapters.atlassian import AtlassianAdapter
from app.adapters.base import JobSourceAdapter
from app.adapters.greenhouse import GreenhouseAdapter
from app.adapters.http import HTTPClient
from app.adapters.lever import LeverAdapter
from app.adapters.microsoft import MicrosoftAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.netflix import NetflixAdapter
from app.adapters.workday import WorkdayAdapter
from app.adapters.registry import (
    AdapterNotRegisteredError,
    build_adapter,
    get_adapter_class,
    register,
    registered_providers,
)

__all__ = [
    "AdapterNotRegisteredError",
    "AmazonAdapter",
    "AppleAdapter",
    "AshbyAdapter",
    "AtlassianAdapter",
    "CanonicalJob",
    "CanonicalLocation",
    "GreenhouseAdapter",
    "HTTPClient",
    "JobSourceAdapter",
    "LeverAdapter",
    "MicrosoftAdapter",
    "NetflixAdapter",
    "RawJob",
    "WorkdayAdapter",
    "build_adapter",
    "get_adapter_class",
    "register",
    "registered_providers",
]
