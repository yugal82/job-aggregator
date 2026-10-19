"""Runtime settings.

Env-var sources, in increasing precedence:
    1. ``server/.env``         — local-dev defaults (docker-compose + pytest)
    2. ``<repo-root>/.env.local`` — written by ``neon env pull`` / ``neon deploy``
       so the Neon-provisioned ``DATABASE_URL`` / ``DATABASE_URL_UNPOOLED``
       land here automatically whenever we re-run deploy
    3. Real process environment (Vercel, GitHub Actions, Docker Compose)

Naming matches Neon's convention:

    DATABASE_URL           — pooled (PgBouncer) — the one the API serves
                              traffic from. Also the only URL on local
                              docker-compose (there's no pooler there, but
                              the URL is still "the connection to use").
    DATABASE_URL_UNPOOLED  — direct — only set on Neon; Alembic migrations
                              and other DDL-ish work use it so they get a
                              dedicated session.

Neon's URL ships in libpq form:
    postgresql://user:pw@host/db?channel_binding=require&sslmode=require

SQLAlchemy's async engine needs the ``postgresql+asyncpg://`` dialect, and
asyncpg doesn't recognize ``channel_binding``/``sslmode`` as URL params. We
rewrite the URL in a validator so (a) the raw Neon vars stay untouched for
future ``neon env pull`` cycles, and (b) consumers of ``settings.*`` get a
URL asyncpg accepts.
"""
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVER_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _SERVER_DIR.parent


_ASYNCPG_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+psycopg",
    "postgresql+psycopg2",
}

# asyncpg takes `ssl=prefer|require|verify-ca|verify-full` on the URL (or via
# connect_args). It does NOT understand `sslmode` or `channel_binding`.
_LIBPQ_SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def _to_asyncpg_url(raw: str | None) -> str | None:
    """Rewrite a Neon-style libpq URL into one SQLAlchemy's asyncpg dialect
    accepts. No-op if the URL is already in asyncpg form or if it's None."""
    if not raw:
        return raw

    parsed = urlsplit(raw)
    scheme = parsed.scheme
    if scheme not in _ASYNCPG_SCHEMES:
        # Already `postgresql+asyncpg` (or something else we don't own).
        return raw

    # Rewrite query: drop channel_binding, translate sslmode → ssl.
    new_params: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower == "channel_binding":
            # asyncpg negotiates channel binding automatically over TLS;
            # the libpq-level knob is noise here.
            continue
        if key_lower == "sslmode":
            if value in _LIBPQ_SSL_MODES:
                new_params.append(("ssl", value))
            continue
        new_params.append((key, value))

    return urlunsplit(
        (
            "postgresql+asyncpg",
            parsed.netloc,
            parsed.path,
            urlencode(new_params),
            parsed.fragment,
        )
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Tuple order = precedence: later files win over earlier ones.
        # ``server/.env`` holds local-dev defaults; ``<repo>/.env.local`` is
        # the authoritative Neon-written file.
        env_file=(
            str(_SERVER_DIR / ".env"),
            str(_REPO_ROOT / ".env.local"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = "development"
    log_level: str = "INFO"

    # Primary URL — pooled on Neon (DATABASE_URL in .env.local), direct on
    # local docker-compose. The API and sync worker both use this.
    database_url: str = Field(...)

    # Only set in Neon-backed environments: the direct (non-pooled) URL
    # Alembic uses so migrations get a full session. Falls back to
    # ``database_url`` on local dev where no separate direct URL exists.
    database_url_unpooled: str | None = None

    test_database_url: str | None = None

    llm_api_key: str | None = None

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator(
        "database_url", "database_url_unpooled", "test_database_url", mode="before"
    )
    @classmethod
    def _normalize_db_url(cls, value: str | None) -> str | None:
        return _to_asyncpg_url(value)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def runtime_database_url(self) -> str:
        """URL the runtime (API + worker) connects on. Pooled on Neon."""
        return self.database_url

    @property
    def migration_database_url(self) -> str:
        """URL Alembic uses for migrations. On Neon this is the direct URL
        so DDL/transactions don't bounce through PgBouncer. Local dev
        shares a single URL, so this falls back to ``database_url``."""
        return self.database_url_unpooled or self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
