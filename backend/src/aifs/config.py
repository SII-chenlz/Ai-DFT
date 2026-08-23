"""Deployment settings for the AIFS backend.

Settings are read from environment variables (prefix ``AIFS_``) and an
optional ``.env`` file; see ``.env.example``. The renderer joins the
deployment's ``AIFS_BASIS_SET_POOL`` with the requested basis name, so
rendered cards never contain a machine-local path and callers cannot pick a
pool root of their own.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """A deployment misconfiguration: an infrastructure failure, never a
    domain validation failure.

    Raised when the process cannot provide a setting that rendering
    requires, e.g. an unset ``AIFS_BASIS_SET_POOL``.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Settings(BaseSettings):
    """Deployment-level configuration of the AIFS backend."""

    model_config = SettingsConfigDict(
        env_prefix="AIFS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Root path of the deployed REST basis set pool.
    basis_set_pool: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the cached deployment settings."""
    return Settings()


def require_basis_set_pool() -> str:
    """Return the configured basis set pool root, or fail loudly.

    An unset pool is a deployment misconfiguration: cards rendered without it
    would carry no basis at all, so this raises instead of silently guessing.
    """
    pool = get_settings().basis_set_pool.strip()
    if not pool:
        raise ConfigurationError(
            "AIFS_BASIS_SET_POOL is not configured; the backend cannot join a "
            "basis name to a deployment root"
        )
    return pool
